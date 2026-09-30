"""Basic contract compile, deploy, and manual exploit tests."""
import json
import sys
from pathlib import Path

import pytest
from web3 import Web3

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import config
from orchestrator.chain import compile_contract, deploy, get_web3, normalize_pragma
from orchestrator.outcome import is_drained

CONTRACT_NAMES = [
    ("VulnerableVault.sol", "VulnerableVault"),
    ("SafeVault.sol", "SafeVault"),
    ("VulnerableTreasury.sol", "VulnerableTreasury"),
    ("SafeTreasury.sol", "SafeTreasury"),
    ("VulnerableBlind.sol", "VulnerableBlind"),
    ("SafeBlind.sol", "SafeBlind"),
    ("VulnerableOracleVault.sol", "VulnerableOracleVault"),
    ("SafeOracleVault.sol", "SafeOracleVault"),
    ("Attacker.sol", "Attacker"),
]


def _anvil_available() -> bool:
    try:
        w3 = get_web3(config.LOCAL_RPC_URL)
        return w3.is_connected()
    except Exception:
        return False


@pytest.mark.parametrize("filename,contract_name", CONTRACT_NAMES)
def test_compile_contracts(filename, contract_name):
    abi, bytecode = compile_contract(filename, contract_name)
    assert isinstance(abi, list)
    assert len(bytecode) > 0


def test_normalize_pragma_injects_when_missing():
    source = "contract Foo {}"
    normalized = normalize_pragma(source)
    assert "pragma solidity ^0.8.19;" in normalized


@pytest.mark.skipif(not _anvil_available(), reason="Anvil not running")
def test_deploy_vulnerable_vault():
    w3 = get_web3(config.LOCAL_RPC_URL)
    deployer = w3.eth.accounts[0]
    abi, bytecode = compile_contract("VulnerableVault.sol", "VulnerableVault")
    contract = deploy(w3, abi, bytecode, deployer)
    assert contract.address.startswith("0x")


@pytest.mark.skipif(not _anvil_available(), reason="Anvil not running")
def test_manual_exploit_drains_vault():
    w3 = get_web3(config.LOCAL_RPC_URL)
    deployer = w3.eth.accounts[0]
    attacker_account = w3.eth.accounts[5]

    vault_abi, vault_bytecode = compile_contract(
        "VulnerableVault.sol", "VulnerableVault"
    )
    vault = deploy(w3, vault_abi, vault_bytecode, deployer)

    for depositor in w3.eth.accounts[1:4]:
        tx = vault.functions.deposit().transact(
            {"from": depositor, "value": Web3.to_wei(1, "ether")}
        )
        w3.eth.wait_for_transaction_receipt(tx)

    vault_before = vault.functions.getBalance().call()

    attacker_abi, attacker_bytecode = compile_contract("Attacker.sol", "Attacker")
    attacker = deploy(
        w3,
        attacker_abi,
        attacker_bytecode,
        attacker_account,
        constructor_args=[vault.address],
    )

    tx = attacker.functions.attack().transact(
        {"from": attacker_account, "value": Web3.to_wei(1, "ether")}
    )
    w3.eth.wait_for_transaction_receipt(tx)

    vault_after = vault.functions.getBalance().call()
    assert is_drained(vault_before, vault_after)
