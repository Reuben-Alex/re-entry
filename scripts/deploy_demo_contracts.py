"""
Deploys demo contracts to a local Anvil node and funds vaults/treasuries.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from web3 import Web3

from orchestrator import config
from orchestrator.chain import compile_contract, deploy, get_web3


CONTRACTS = [
    ("VulnerableVault.sol", "VulnerableVault"),
    ("SafeVault.sol", "SafeVault"),
    ("VulnerableTreasury.sol", "VulnerableTreasury"),
    ("SafeTreasury.sol", "SafeTreasury"),
]


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
    for filename, name in CONTRACTS:
        abi, bytecode = compile_contract(filename, name)
        contract = deploy(w3, abi, bytecode, deployer)
        print(f"Deployed {name} at {contract.address}")

        _fund_contract(w3, contract, depositors, amount)
        balance = w3.from_wei(contract.functions.getBalance().call(), "ether")
        print(f"  funded with {len(depositors)} deposits, total: {balance} ETH")

        deployed[name] = {"address": contract.address, "abi": abi}

    out_path = Path(config.PROJECT_ROOT) / "deployed_contracts.json"
    out_path.write_text(json.dumps(deployed, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
