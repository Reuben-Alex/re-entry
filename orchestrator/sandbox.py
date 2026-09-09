"""
Sandbox orchestration — local Anvil and optional Contree execution.
"""
from dataclasses import dataclass, field

from web3.exceptions import ContractLogicError

from orchestrator import config
from orchestrator.chain import get_web3


@dataclass
class ExecutionResult:
    success: bool
    attacker_balance_before: int
    attacker_balance_after: int
    vault_balance_before: int
    vault_balance_after: int
    revert_reason: str | None
    raw_tx_hashes: list[str] = field(default_factory=list)
    attacker_address: str | None = None


class LocalSandbox:
    """Anvil-backed sandbox for local development."""

    def __init__(self, rpc_url: str = config.LOCAL_RPC_URL):
        self.w3 = get_web3(rpc_url)
        self._snapshot_id = None

    def fork_checkpoint(self):
        """Snapshot current Anvil state."""
        response = self.w3.provider.make_request("evm_snapshot", [])
        self._snapshot_id = response["result"]
        return self._snapshot_id

    def rollback(self):
        """Revert to the last snapshot."""
        if self._snapshot_id is None:
            return
        self.w3.provider.make_request("evm_revert", [self._snapshot_id])
        self._snapshot_id = None

    def get_balance(self, address: str) -> int:
        """Return account balance in wei."""
        return self.w3.eth.get_balance(address)

    def send_tx(
        self,
        contract,
        fn_name: str,
        args: list | None = None,
        value: int = 0,
        sender: str | None = None,
    ) -> str:
        """
        Send a contract transaction. Returns tx hash or raises with
        revert reason attached.
        """
        args = args or []
        sender = sender or self.w3.eth.accounts[0]
        fn = contract.functions[fn_name](*args)
        try:
            tx_hash = fn.transact({"from": sender, "value": value})
            self.w3.eth.wait_for_transaction_receipt(tx_hash)
            return tx_hash.hex()
        except ContractLogicError as exc:
            raise RuntimeError(str(exc)) from exc


class ContreeSandbox(LocalSandbox):
    """
    Nebius Contree sandbox — delegates to local Anvil RPC when Contree
    exposes one, otherwise uses LOCAL_RPC_URL as configured endpoint.

    Contree SDK is beta; this class validates credentials and reuses the
    LocalSandbox interface so the pipeline stays mode-agnostic.
    """

    def __init__(self, rpc_url: str | None = None):
        if not config.CONTREE_API_TOKEN:
            raise ValueError(
                "CONTREE_API_TOKEN required when SANDBOX_MODE=contree"
            )
        if not config.CONTREE_PROJECT_ID:
            raise ValueError(
                "CONTREE_PROJECT_ID required when SANDBOX_MODE=contree"
            )
        self._contree = None
        try:
            from contree_sdk import Contree

            self._contree = Contree(api_token=config.CONTREE_API_TOKEN)
        except ImportError as exc:
            raise ImportError(
                "contree-sdk is required for SANDBOX_MODE=contree"
            ) from exc
        endpoint = rpc_url or config.LOCAL_RPC_URL
        super().__init__(rpc_url=endpoint)


def create_sandbox():
    """Factory: return LocalSandbox or ContreeSandbox based on config."""
    if config.SANDBOX_MODE.lower() == "contree":
        return ContreeSandbox()
    return LocalSandbox()
