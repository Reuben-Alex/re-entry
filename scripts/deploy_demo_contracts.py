"""
Deploys challenge contracts from manifest to a local Anvil node.
"""
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from ensure_venv import ensure_project_python

ensure_project_python()

sys.path.insert(0, str(_SCRIPTS.parent))

from web3 import Web3

from orchestrator import config
from orchestrator import challenges
from orchestrator.chain import compile_contract_path, deploy, get_web3


def _fund_contract(w3, contract, depositors, amount_wei):
    for depositor in depositors:
        tx_hash = contract.functions.deposit().transact(
            {"from": depositor, "value": amount_wei}
        )
        w3.eth.wait_for_transaction_receipt(tx_hash)


def main():
    w3 = get_web3(config.LOCAL_RPC_URL)
    deployer = w3.eth.accounts[0]
    depositors = w3.eth.accounts[1:4]
    amount = Web3.to_wei(1, "ether")

    deployed = {}
    for target in challenges.list_deployable():
        try:
            source_path = challenges.resolve_source_path(target)
        except FileNotFoundError as exc:
            if target.tier == "held_out_live":
                print(f"Skipping {target.name} — {exc}")
                continue
            raise
        cname = target.solidity_contract_name
        abi, bytecode = compile_contract_path(source_path, cname)
        contract = deploy(w3, abi, bytecode, deployer)
        print(f"Deployed {target.name} at {contract.address}")

        _fund_contract(w3, contract, depositors, amount)
        balance = w3.from_wei(contract.functions.getBalance().call(), "ether")
        print(f"  funded with {len(depositors)} deposits, total: {balance} ETH")

        deployed[target.name] = {"address": contract.address, "abi": abi}

    out_path = Path(config.PROJECT_ROOT) / "deployed_contracts.json"
    out_path.write_text(json.dumps(deployed, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
