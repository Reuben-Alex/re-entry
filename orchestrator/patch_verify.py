"""
Deploy patched contract and replay winning exploit to prove fix works.
"""
import dataclasses
import time
from dataclasses import dataclass

from web3 import Web3

from orchestrator import chain, executor, outcome
from orchestrator.patcher import PatchProposal
from orchestrator.proposer import ExploitProposal

FUND_DEPOSITORS = 3
FUND_AMOUNT_WEI = Web3.to_wei(1, "ether")


@dataclass
class ReplayDescriptor:
    kind: str  # agent_proposal | fallback_reentrancy | fallback_treasury_direct
    proposal: ExploitProposal | None
    target_name: str


@dataclass
class PatchVerification:
    compiles: bool
    deployed_address: str | None
    replay_success: bool
    exploit_blocked: bool
    revert_reason: str | None
    vault_balance_before: int
    vault_balance_after: int
    duration_s: float
    benign_ok: bool = False
    benign_error: str | None = None
    verified: bool = False


def build_replay_descriptor(
    target_name: str,
    winning_proposal: ExploitProposal | None,
    used_fallback: bool,
) -> ReplayDescriptor:
    """Capture how to replay the attack that succeeded."""
    if winning_proposal is not None:
        return ReplayDescriptor(
            kind="agent_proposal",
            proposal=winning_proposal,
            target_name=target_name,
        )
    return ReplayDescriptor(
        kind="fallback",
        proposal=None,
        target_name=target_name,
    )


def _fund_patched_contract(w3, contract, deployer: str) -> None:
    """Fund patched contract via deposit() like deploy_demo_contracts."""
    depositors = w3.eth.accounts[1 : 1 + FUND_DEPOSITORS]
    for depositor in depositors:
        tx_hash = contract.functions.deposit().transact(
            {"from": depositor, "value": FUND_AMOUNT_WEI}
        )
        w3.eth.wait_for_transaction_receipt(tx_hash)


def _run_benign(sandbox, contract) -> tuple[bool, str | None]:
    """Honest deposit/withdraw steps must still succeed on the patched contract."""
    steps = (getattr(sandbox, "run_context", None) or {}).get("benign") or []
    if not steps:
        return True, None
    from orchestrator.setup import _call_step

    try:
        for step in steps:
            _call_step(sandbox.w3, contract, step, {}, "")
        return True, None
    except Exception as exc:
        return False, str(exc)


def _deploy_patched(sandbox, patch: PatchProposal, deployer: str):
    plan = (getattr(sandbox, "run_context", None) or {}).get("deploy_plan")
    if plan:
        from orchestrator.setup import redeploy_from_source

        return redeploy_from_source(
            sandbox.w3, patch.patched_source, plan, deployer
        )
    patched = chain.deploy(
        sandbox.w3,
        patch.abi,
        patch.bytecode,
        deployer,
        constructor_args=[],
    )
    _fund_patched_contract(sandbox.w3, patched, deployer)
    return patched


def verify_patch(
    sandbox,
    replay: ReplayDescriptor,
    patch: PatchProposal,
    deployer: str,
) -> PatchVerification:
    """
    Deploy the patched contract, replay the exploit, then run the benign script.

    A patch is verified only when the exploit no longer profits and honest use
    still succeeds.
    """
    start = time.time()
    sandbox.fork_checkpoint()

    w3 = sandbox.w3
    revert_reason = None
    replay_success = False
    deployed_address = None
    vault_before = 0
    vault_after = 0
    benign_ok = False
    benign_error = None

    try:
        patched = _deploy_patched(sandbox, patch, deployer)
        deployed_address = patched.address
        vault_before = sandbox.get_balance(deployed_address)
        snap = w3.provider.make_request("evm_snapshot", [])["result"]
        benign_ok, benign_error = _run_benign(sandbox, patched)
        w3.provider.make_request("evm_revert", [snap])
        replay_sender = w3.eth.accounts[5]

        if replay.kind == "agent_proposal" and replay.proposal:
            result, _ = executor.execute_proposal(
                sandbox,
                replay.proposal,
                deployed_address,
                patch.abi,
                deployer,
                sender=replay_sender,
            )
        else:
            result, _ = executor.fallback_exploit(
                sandbox,
                deployed_address,
                patch.abi,
                deployer,
                target_name=replay.target_name,
                sender=replay_sender,
            )
        replay_success = result.success
        revert_reason = result.revert_reason
        vault_after = result.vault_balance_after
    except Exception as exc:
        revert_reason = str(exc)
        vault_after = (
            sandbox.get_balance(deployed_address) if deployed_address else vault_before
        )

    exploit_blocked = not replay_success
    verified = exploit_blocked and benign_ok

    return PatchVerification(
        compiles=True,
        deployed_address=deployed_address,
        replay_success=replay_success,
        exploit_blocked=exploit_blocked,
        revert_reason=revert_reason,
        vault_balance_before=vault_before,
        vault_balance_after=vault_after,
        duration_s=time.time() - start,
        benign_ok=benign_ok,
        benign_error=benign_error,
        verified=verified,
    )


def verification_to_dict(verification: PatchVerification) -> dict:
    return dataclasses.asdict(verification)
