"""
Pre-run checks: ensure target contracts are funded before exploit attempts.
"""
import json
from pathlib import Path

from web3 import Web3

from orchestrator import config

MIN_BALANCE_WEI = Web3.to_wei(1, "ether")
DEPLOYED_PATH = Path(config.PROJECT_ROOT) / "deployed_contracts.json"


class PreflightError(Exception):
    """Target is not ready for pipeline execution."""

    def __init__(self, message: str, verdict: str = "infra_error"):
        super().__init__(message)
        self.verdict = verdict


def _get_balance(sandbox, address: str) -> int:
    if hasattr(sandbox, "get_balance"):
        return sandbox.get_balance(address)
    return sandbox.w3.eth.get_balance(address)


def load_deployed() -> dict:
    if not DEPLOYED_PATH.exists():
        return {}
    return json.loads(DEPLOYED_PATH.read_text())


def ensure_target_funded(
    sandbox,
    target_name: str,
    vault_address: str,
    deploy_fn,
    min_wei: int | None = None,
) -> dict:
    """
    Verify target holds at least MIN_BALANCE_WEI; redeploy all demos if not.

    Returns:
        dict with keys: balance_wei, redeployed, address

    Raises:
        PreflightError: if still unfunded after redeploy
    """
    balance = _get_balance(sandbox, vault_address)
    redeployed = False
    threshold = MIN_BALANCE_WEI if min_wei is None else min_wei

    if threshold <= 0:
        return {
            "balance_wei": balance,
            "redeployed": False,
            "address": vault_address,
        }

    if balance < threshold:
        deploy_fn()
        redeployed = True
        deployed = load_deployed()
        if target_name not in deployed:
            raise PreflightError(
                f"Target {target_name} missing after redeploy",
                verdict="infra_error",
            )
        vault_address = deployed[target_name]["address"]
        balance = _get_balance(sandbox, vault_address)

    if balance < threshold:
        raise PreflightError(
            f"Target {target_name} at {vault_address} has {balance} wei "
            f"(need ≥ {threshold}). Redeploy Anvil and run deploy_demo_contracts.",
            verdict="unfunded_target",
        )

    return {
        "balance_wei": balance,
        "redeployed": redeployed,
        "address": vault_address,
    }
