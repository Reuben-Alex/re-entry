"""
Compilation + web3 connection helpers.
"""
import os
import re
import urllib.parse
from pathlib import Path

from solcx import compile_source, get_installed_solc_versions, install_solc
from web3 import Web3

SOLC_VERSION = "0.8.19"
CONTRACTS_DIR = Path(__file__).parent.parent / "contracts"
PRAGMA_LINE = "pragma solidity ^0.8.19;"


def ensure_solc():
    """Install solc 0.8.19 if not already present."""
    if SOLC_VERSION not in [str(v) for v in get_installed_solc_versions()]:
        install_solc(SOLC_VERSION)


def normalize_pragma(source_code: str) -> str:
    """Normalize or inject pragma line to avoid version drift compile failures."""
    pragma_pattern = re.compile(
        r"^\s*pragma\s+solidity\s+[^;]+;",
        re.MULTILINE | re.IGNORECASE,
    )
    if pragma_pattern.search(source_code):
        return pragma_pattern.sub(PRAGMA_LINE, source_code, count=1)
    return f"// SPDX-License-Identifier: MIT\n{PRAGMA_LINE}\n{source_code}"


def _extract_contract(source_code: str, contract_name: str) -> tuple[list, str]:
    """Compile normalized source and return ABI + bytecode for contract_name."""
    compiled = compile_source(
        source_code,
        output_values=["abi", "bin"],
        solc_version=SOLC_VERSION,
    )
    for key, iface in compiled.items():
        if key.endswith(f":{contract_name}"):
            return iface["abi"], iface["bin"]
    available = [k.split(":")[-1] for k in compiled.keys()]
    raise ValueError(
        f"contract {contract_name} not found in generated source. "
        f"Available: {available}"
    )


def compile_contract(filename: str, contract_name: str) -> tuple[list, str]:
    """
    Compile a .sol file from the contracts/ directory.
    Returns (abi, bytecode).
    """
    ensure_solc()
    source_path = CONTRACTS_DIR / filename
    source = source_path.read_text()
    return _extract_contract(normalize_pragma(source), contract_name)


def compile_contract_path(source_path: Path, contract_name: str) -> tuple[list, str]:
    """Compile a .sol file at an arbitrary path. Returns (abi, bytecode)."""
    ensure_solc()
    source = source_path.read_text()
    return _extract_contract(normalize_pragma(source), contract_name)


def compile_source_code(source_code: str, contract_name: str) -> tuple[list, str]:
    """Compile raw Solidity source (not from file). Returns (abi, bytecode)."""
    ensure_solc()
    normalized = normalize_pragma(source_code)
    return _extract_contract(normalized, contract_name)


def get_web3(rpc_url: str) -> Web3:
    """Connect to an EVM RPC endpoint with localhost guard by default."""
    parsed = urllib.parse.urlparse(rpc_url)
    if parsed.hostname not in ("127.0.0.1", "localhost", "0.0.0.0"):
        allow_remote = os.environ.get("ALLOW_REMOTE_RPC", "").lower() == "true"
        if not allow_remote:
            raise ValueError(
                f"Refusing to connect to non-local RPC {rpc_url}. "
                "Set ALLOW_REMOTE_RPC=true to override."
            )
    w3 = Web3(Web3.HTTPProvider(rpc_url))
    if not w3.is_connected():
        raise ConnectionError(
            f"could not connect to {rpc_url} — is anvil running? (run: anvil)"
        )
    return w3


def deploy(
    w3: Web3,
    abi: list,
    bytecode: str,
    account: str,
    constructor_args: list | None = None,
):
    """Deploy a compiled contract, return the deployed web3 Contract object."""
    contract_cls = w3.eth.contract(abi=abi, bytecode=bytecode)
    args = constructor_args or []
    tx_hash = contract_cls.constructor(*args).transact({"from": account})
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
    return w3.eth.contract(address=receipt.contractAddress, abi=abi)
