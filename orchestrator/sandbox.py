"""
Sandbox orchestration — local Anvil and Nebius Contree execution.
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
    trace: str = ""
    token_gain: int = 0


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


def create_sandbox():
    """Factory: return LocalSandbox or ContreeSandbox based on config."""
    if config.SANDBOX_MODE.lower() == "contree":
        from orchestrator.contree_sandbox import ContreeSandbox

        return ContreeSandbox()
    return LocalSandbox()
