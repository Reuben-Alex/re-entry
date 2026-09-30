#!/usr/bin/env python3
"""
Run one exploit attempt inside a Contree container against local Anvil.

Reads JSON payload from argv[1] or /tmp/re-entry_payload.json and prints
ExecutionResult JSON to stdout.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from orchestrator import chain, outcome  # noqa: E402

ATTACK_VALUE_WEI = 10**18
PAYLOAD_PATH = Path("/tmp/re-entry_payload.json")


def _load_payload() -> dict:
    if len(sys.argv) > 1:
        return json.loads(Path(sys.argv[1]).read_text())
    return json.loads(PAYLOAD_PATH.read_text())


def _run_proposal(w3, payload: dict) -> dict:
    proposal = payload["proposal"]
    vault_address = payload["vault_address"]
    vault_abi = payload["vault_abi"]
    deployer = w3.eth.accounts[0]

    vault_before = w3.eth.get_balance(vault_address)
    attacker_before = 0
    attacker_address = None
    raw_tx_hashes = []
    revert_reason = None

    try:
        abi, bytecode = chain.compile_source_code(
            proposal["solidity_source"], proposal["contract_name"]
        )
        attacker = chain.deploy(
            w3,
            abi,
            bytecode,
            deployer,
            constructor_args=[vault_address],
        )
        attacker_address = attacker.address
        attacker_before = w3.eth.get_balance(attacker_address)

        fn = attacker.functions[proposal["entry_function"]]()
        tx_hash = fn.transact(
            {
                "from": deployer,
                "value": int(proposal.get("entry_value_wei", ATTACK_VALUE_WEI)),
            }
        )
        w3.eth.wait_for_transaction_receipt(tx_hash)
        raw_tx_hashes.append(tx_hash.hex())
    except Exception as exc:
        revert_reason = str(exc)

    vault_after = w3.eth.get_balance(vault_address)
    attacker_after = (
        w3.eth.get_balance(attacker_address) if attacker_address else 0
    )
    success = outcome.is_drained(vault_before, vault_after) and not revert_reason

    return {
        "success": success,
        "attacker_balance_before": attacker_before,
        "attacker_balance_after": attacker_after,
        "vault_balance_before": vault_before,
        "vault_balance_after": vault_after,
        "revert_reason": revert_reason,
        "raw_tx_hashes": raw_tx_hashes,
        "attacker_address": attacker_address,
    }


def _is_treasury(target_name: str) -> bool:
    return "Treasury" in (target_name or "")


def _run_fallback(w3, payload: dict) -> dict:
    vault_address = payload["vault_address"]
    deployer = w3.eth.accounts[0]
    target_name = payload.get("target_name", "VulnerableVault")

    vault_before = w3.eth.get_balance(vault_address)
    attacker_before = 0
    attacker_address = None
    raw_tx_hashes = []
    revert_reason = None

    try:
        if _is_treasury(target_name):
            vault_abi = payload["vault_abi"]
            treasury = w3.eth.contract(address=vault_address, abi=vault_abi)
            attacker_address = deployer
            attacker_before = w3.eth.get_balance(deployer)
            tx_hash = treasury.functions.withdrawAll().transact({"from": deployer})
        else:
            abi, bytecode = chain.compile_contract("Attacker.sol", "Attacker")
            attacker = chain.deploy(
                w3, abi, bytecode, deployer, constructor_args=[vault_address]
            )
            attacker_address = attacker.address
            attacker_before = w3.eth.get_balance(attacker_address)
            tx_hash = attacker.functions.attack().transact(
                {"from": deployer, "value": ATTACK_VALUE_WEI}
            )
        w3.eth.wait_for_transaction_receipt(tx_hash)
        raw_tx_hashes.append(tx_hash.hex())
    except Exception as exc:
        revert_reason = str(exc)

    vault_after = w3.eth.get_balance(vault_address)
    attacker_after = (
        w3.eth.get_balance(attacker_address) if attacker_address else 0
    )
    success = outcome.is_drained(vault_before, vault_after) and not revert_reason

    return {
        "success": success,
        "attacker_balance_before": attacker_before,
        "attacker_balance_after": attacker_after,
        "vault_balance_before": vault_before,
        "vault_balance_after": vault_after,
        "revert_reason": revert_reason,
        "raw_tx_hashes": raw_tx_hashes,
        "attacker_address": attacker_address,
    }


def main() -> None:
    payload = _load_payload()
    rpc = payload.get("rpc_url", "http://127.0.0.1:8545")
    w3 = chain.get_web3(rpc)

    if payload.get("mode") == "fallback":
        result = _run_fallback(w3, payload)
    else:
        result = _run_proposal(w3, payload)

    print(json.dumps(result))


if __name__ == "__main__":
    main()
