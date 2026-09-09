"""
Deploy and execute LLM-generated exploit contracts in the sandbox.
"""
import time

from orchestrator import chain, outcome
from orchestrator.proposer import ExploitProposal
from orchestrator.sandbox import ExecutionResult, LocalSandbox

ATTACK_VALUE_WEI = 10**18


def _extract_revert_reason(exc: Exception) -> str:
    return str(exc)


def execute_proposal(
    sandbox: LocalSandbox,
    proposal: ExploitProposal,
    vault_address: str,
    vault_abi: list,
    deployer: str,
) -> tuple[ExecutionResult, dict]:
    """
    Deploy generated attacker and run attack(). Returns result + timing.
    """
    timing = {"step": "execute", "duration_s": 0.0}
    start = time.time()
    w3 = sandbox.w3
    vault = w3.eth.contract(address=vault_address, abi=vault_abi)

    vault_before = sandbox.get_balance(vault_address)
    attacker_before = 0

    raw_tx_hashes = []
    revert_reason = None
    attacker_address = None

    try:
        attacker = chain.deploy(
            w3,
            proposal.abi,
            proposal.bytecode,
            deployer,
            constructor_args=[vault_address],
        )
        attacker_address = attacker.address
        attacker_before = sandbox.get_balance(attacker_address)

        tx_hash = sandbox.send_tx(
            attacker,
            proposal.entry_function,
            args=[],
            value=proposal.entry_value_wei,
            sender=deployer,
        )
        raw_tx_hashes.append(tx_hash)
    except Exception as exc:
        revert_reason = _extract_revert_reason(exc)

    vault_after = sandbox.get_balance(vault_address)
    attacker_after = (
        sandbox.get_balance(attacker_address) if attacker_address else 0
    )

    success = outcome.is_drained(vault_before, vault_after) and not revert_reason
    timing["duration_s"] = time.time() - start

    return (
        ExecutionResult(
            success=success,
            attacker_balance_before=attacker_before,
            attacker_balance_after=attacker_after,
            vault_balance_before=vault_before,
            vault_balance_after=vault_after,
            revert_reason=revert_reason,
            raw_tx_hashes=raw_tx_hashes,
            attacker_address=attacker_address,
        ),
        timing,
    )


def fallback_exploit(
    sandbox: LocalSandbox,
    vault_address: str,
    vault_abi: list,
    deployer: str,
) -> tuple[ExecutionResult, dict]:
    """Last resort: use the hand-written Attacker.sol."""
    timing = {"step": "execute_fallback", "duration_s": 0.0}
    start = time.time()
    w3 = sandbox.w3
    vault = w3.eth.contract(address=vault_address, abi=vault_abi)

    vault_before = sandbox.get_balance(vault_address)
    raw_tx_hashes = []
    revert_reason = None
    attacker_address = None
    attacker_before = 0
    attacker_after = 0

    try:
        abi, bytecode = chain.compile_contract("Attacker.sol", "Attacker")
        attacker = chain.deploy(
            w3, abi, bytecode, deployer, constructor_args=[vault_address]
        )
        attacker_address = attacker.address
        attacker_before = sandbox.get_balance(attacker_address)

        tx_hash = sandbox.send_tx(
            attacker,
            "attack",
            args=[],
            value=ATTACK_VALUE_WEI,
            sender=deployer,
        )
        raw_tx_hashes.append(tx_hash)
    except Exception as exc:
        revert_reason = _extract_revert_reason(exc)

    vault_after = sandbox.get_balance(vault_address)
    if attacker_address:
        attacker_after = sandbox.get_balance(attacker_address)

    success = outcome.is_drained(vault_before, vault_after) and not revert_reason
    timing["duration_s"] = time.time() - start

    return (
        ExecutionResult(
            success=success,
            attacker_balance_before=attacker_before,
            attacker_balance_after=attacker_after,
            vault_balance_before=vault_before,
            vault_balance_after=vault_after,
            revert_reason=revert_reason,
            raw_tx_hashes=raw_tx_hashes,
            attacker_address=attacker_address,
        ),
        timing,
    )
