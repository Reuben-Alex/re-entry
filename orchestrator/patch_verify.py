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
    if "Treasury" in target_name and not target_name.startswith("Safe"):
        return ReplayDescriptor(
            kind="fallback_treasury_direct",
            proposal=None,
            target_name=target_name,
        )
    if "Escrow" in target_name and not target_name.startswith("Safe"):
        return ReplayDescriptor(
            kind="fallback_escrow_release",
            proposal=None,
            target_name=target_name,
        )
    return ReplayDescriptor(
        kind="fallback_reentrancy",
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


def verify_patch(
    sandbox,
    replay: ReplayDescriptor,
    patch: PatchProposal,
    deployer: str,
) -> PatchVerification:
    """
    Deploy patched contract, fund it, replay winning exploit.

    Pass when exploit no longer drains the patched contract.
    """
    start = time.time()
    sandbox.fork_checkpoint()

    w3 = sandbox.w3
    revert_reason = None
    replay_success = False
    deployed_address = None
    vault_before = 0
    vault_after = 0

    try:
        patched = chain.deploy(
            w3,
            patch.abi,
            patch.bytecode,
            deployer,
            constructor_args=[],
        )
        deployed_address = patched.address
        _fund_patched_contract(w3, patched, deployer)
        vault_before = sandbox.get_balance(deployed_address)

        # Non-owner account proves access-control patches block unauthorized drain.
        replay_sender = deployer
        if replay.target_name.startswith("Safe"):
            replay_sender = deployer
        elif "Treasury" in replay.target_name or "Escrow" in replay.target_name:
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
            replay_success = result.success
            revert_reason = result.revert_reason
            vault_after = result.vault_balance_after
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

    exploit_blocked = not outcome.is_drained(vault_before, vault_after)

    return PatchVerification(
        compiles=True,
        deployed_address=deployed_address,
        replay_success=replay_success,
        exploit_blocked=exploit_blocked,
        revert_reason=revert_reason,
        vault_balance_before=vault_before,
        vault_balance_after=vault_after,
        duration_s=time.time() - start,
    )


def verification_to_dict(verification: PatchVerification) -> dict:
    return dataclasses.asdict(verification)
