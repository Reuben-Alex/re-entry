"""
Deploy and execute LLM-generated exploit contracts in the sandbox.
"""
import time

from orchestrator import chain, outcome
from orchestrator.proposer import ExploitProposal
from orchestrator.revert import clean_revert_reason
from orchestrator.sandbox import ExecutionResult, LocalSandbox
from orchestrator.trace import trace_call, trace_transaction

ATTACK_VALUE_WEI = 10**18

ERC20_BALANCE_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "account", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    }
]


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


def _context(sandbox) -> dict:
    return getattr(sandbox, "run_context", None) or {}


def _snapshot_eth(sandbox, addresses: list[str]) -> dict[str, int]:
    unique = []
    seen = set()
    for address in addresses:
        if address and address not in seen:
            seen.add(address)
            unique.append(address)
    return {address: sandbox.get_balance(address) for address in unique}


def _eth_sum(balances: dict[str, int]) -> int:
    return sum(balances.values())


def _token_gain(sandbox, holders: list[str], before: dict[str, int]) -> int:
    tokens = (_context(sandbox).get("tokens") or {}).values()
    if not tokens or not sandbox.w3:
        return 0
    gain = 0
    for token in tokens:
        contract = sandbox.w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
        for holder in holders:
            if not holder:
                continue
            try:
                after = contract.functions.balanceOf(holder).call()
            except Exception:
                continue
            gain += after - before.get(f"{token}:{holder}", 0)
    return gain


def _token_before(sandbox, holders: list[str]) -> dict[str, int]:
    tokens = (_context(sandbox).get("tokens") or {}).values()
    found = {}
    if not tokens or not getattr(sandbox, "w3", None):
        return found
    for token in tokens:
        contract = sandbox.w3.eth.contract(address=token, abi=ERC20_BALANCE_ABI)
        for holder in holders:
            if not holder:
                continue
            try:
                found[f"{token}:{holder}"] = contract.functions.balanceOf(holder).call()
            except Exception:
                found[f"{token}:{holder}"] = 0
    return found


def _encode_call(contract, fn_name: str, args: list, value: int, sender: str) -> dict:
    data = contract.functions[fn_name](*args)._encode_transaction_data()
    return {
        "from": sender,
        "to": contract.address,
        "data": data,
        "value": hex(value),
    }


def _capture_trace(sandbox, tx_hash: str | None = None, call: dict | None = None) -> str:
    w3 = getattr(sandbox, "w3", None)
    if w3 is None:
        return ""
    if tx_hash:
        return trace_transaction(w3, tx_hash)
    if call:
        return trace_call(w3, call)
    return ""


def _run_after_attack(sandbox, target_contract, attacker, sender: str) -> str | None:
    """Run the manifest schedule after attack(). Returns a revert string on failure."""
    steps = _context(sandbox).get("after_attack") or []
    if not steps:
        return None
    w3 = sandbox.w3
    addresses = dict(_context(sandbox).get("addresses") or {})
    abis = _context(sandbox).get("abis") or {}
    for step in steps:
        on = step.get("on", "target")
        try:
            if on == "exploit":
                if attacker is None:
                    return "schedule expected an exploit contract"
                contract = attacker
            elif on in ("target", "primary"):
                contract = target_contract
            else:
                contract = w3.eth.contract(address=addresses[on], abi=abis[on])
            from_account = step.get("from_account", 5)
            step_sender = sender if on == "exploit" else w3.eth.accounts[int(from_account)]
            args = step.get("args") or []
            value = int(step.get("value_wei", 0))
            sandbox.send_tx(contract, step["fn"], args, value, step_sender)
        except Exception as exc:
            return _extract_revert_reason(exc)
    return None


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
    raw_tx_hashes = []
    revert_reason = None
    attacker_address = None
    trace = ""
    call = None

    try:
        attacker = chain.deploy(
            w3,
            proposal.abi,
            proposal.bytecode,
            tx_sender,
            constructor_args=[vault_address],
        )
        attacker_address = attacker.address
        holders = [attacker_address, tx_sender]
        eth_before = _snapshot_eth(sandbox, holders)
        tokens_before = _token_before(sandbox, holders)
        call = _encode_call(
            attacker,
            proposal.entry_function,
            [],
            proposal.entry_value_wei,
            tx_sender,
        )
        tx_hash = sandbox.send_tx(
            attacker,
            proposal.entry_function,
            args=[],
            value=proposal.entry_value_wei,
            sender=tx_sender,
        )
        raw_tx_hashes.append(tx_hash)
        schedule_error = _run_after_attack(
            sandbox, w3.eth.contract(address=vault_address, abi=vault_abi), attacker, tx_sender
        )
        if schedule_error:
            revert_reason = schedule_error
    except Exception as exc:
        revert_reason = _extract_revert_reason(exc)
        holders = [address for address in (attacker_address, tx_sender) if address]
        eth_before = _snapshot_eth(sandbox, holders)
        tokens_before = {}
        if call is None and attacker_address:
            try:
                attacker = w3.eth.contract(address=attacker_address, abi=proposal.abi)
                call = _encode_call(
                    attacker,
                    proposal.entry_function,
                    [],
                    proposal.entry_value_wei,
                    tx_sender,
                )
            except Exception:
                call = None
        trace = _capture_trace(sandbox, call=call)

    if not trace and raw_tx_hashes and revert_reason:
        trace = _capture_trace(sandbox, tx_hash=raw_tx_hashes[-1])

    holders = [address for address in (attacker_address, tx_sender) if address]
    eth_after = _snapshot_eth(sandbox, holders)
    if "eth_before" not in locals():
        eth_before = eth_after
        tokens_before = {}
    token_delta = _token_gain(sandbox, holders, tokens_before)
    eth_gain_before = _eth_sum(eth_before)
    eth_gain_after = _eth_sum(eth_after)
    vault_after = sandbox.get_balance(vault_address)
    # Profit only. A vault balance drop from an honest withdraw or borrow
    # is not an exploit unless the attacker nets ETH, tokens, or breaks
    # a declared invariant.
    success = not revert_reason and outcome.is_profitable(
        eth_gain_after - eth_gain_before,
        token_delta,
    )
    if not success and not trace and raw_tx_hashes:
        trace = _capture_trace(sandbox, tx_hash=raw_tx_hashes[-1])
    timing["duration_s"] = time.time() - start

    attacker_before = eth_before.get(attacker_address, 0) if attacker_address else 0
    attacker_after = eth_after.get(attacker_address, 0) if attacker_address else 0
    return (
        ExecutionResult(
            success=success,
            attacker_balance_before=eth_gain_before,
            attacker_balance_after=eth_gain_after,
            vault_balance_before=vault_before,
            vault_balance_after=vault_after,
            revert_reason=revert_reason,
            raw_tx_hashes=raw_tx_hashes,
            attacker_address=attacker_address,
            trace=trace,
            token_gain=token_delta,
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
    # The deployer is the owner on these targets. Calling withdrawAll() as
    # the owner is legitimate use, not an exploit.
    tx_sender = sender or w3.eth.accounts[5]
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
