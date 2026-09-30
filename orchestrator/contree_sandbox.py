"""
Nebius Contree sandbox — isolated EVM execution with Git-like branching.

Anvil runs inside the Contree container; exploit attempts execute via
in-sandbox Python. Checkpoint/rollback maps to Contree image UUIDs.
"""
import json
import logging
import tarfile
from io import BytesIO
from pathlib import Path

from contree_sdk import ContreeSync
from contree_sdk.auth import IAMAuth
from contree_sdk.config import ContreeConfig

from orchestrator import config
from orchestrator.exceptions import ConfigurationError
from orchestrator.proposer import ExploitProposal
from contree_sdk.sdk.exceptions import NotFoundError
from contree_sdk.sdk.exceptions.api import ForbiddenError

from orchestrator.sandbox import ExecutionResult

logger = logging.getLogger(__name__)

CONTREE_WORKDIR = "/workspace/re-entry"
ANVIL_RPC = "http://127.0.0.1:8545"
BOOTSTRAP_TAG = "re-entry-bootstrap"


class ContreeSandbox:
    """
    Contree-backed sandbox with branching checkpoints.

    Uses the same Nemotron/Tavily pipeline on the host; only EVM execution
    and state rollback run inside Nebius Sandboxes.
    """

    def __init__(self):
        token, project_id = _resolve_contree_credentials()
        auth = IAMAuth(token=token, project_id=project_id)
        self._client = ContreeSync(ContreeConfig(auth=auth))
        info = self._client.get_token_info()
        logger.info("Contree connected — token %s", info.token_uuid)

        self._image = None
        self._checkpoint_uuid: str | None = None
        self._bootstrap()

    @property
    def deployer(self) -> str:
        """Return Anvil account[0] inside the Contree container."""
        result = (
            self._image.run(
                shell=(
                    f"cast rpc eth_accounts --rpc-url {ANVIL_RPC} "
                    "| python3 -c \"import sys,json; print(json.load(sys.stdin)[0])\""
                ),
                disposable=False,
                timeout=60,
            )
            .wait()
        )
        stdout = result.stdout if isinstance(result.stdout, str) else ""
        return stdout.strip()

    def get_deployed_contracts(self) -> dict:
        """Return deployed demo contract addresses from the sandbox."""
        raw = self._image.read(f"{CONTREE_WORKDIR}/deployed_contracts.json")
        if isinstance(raw, bytes):
            raw = raw.decode()
        return json.loads(raw)

    def fork_checkpoint(self):
        """Save current Contree image UUID for rollback."""
        if self._image is None or self._image.uuid is None:
            raise RuntimeError("Contree image not initialized")
        self._checkpoint_uuid = str(self._image.uuid)
        return self._checkpoint_uuid

    def rollback(self):
        """Restore the last saved Contree checkpoint."""
        if self._checkpoint_uuid is None:
            return
        self._image = self._client.images.use(self._checkpoint_uuid)
        self._checkpoint_uuid = None

    def get_balance(self, address: str) -> int:
        """Read balance via in-container cast (Anvil runs in sandbox)."""
        result = (
            self._image.run(
                shell=(
                    f"cast balance {address} --rpc-url {ANVIL_RPC} 2>/dev/null "
                    "|| echo 0"
                ),
                disposable=False,
                timeout=60,
            )
            .wait()
        )
        stdout = result.stdout if isinstance(result.stdout, str) else "0"
        return int(stdout.strip() or "0")

    def send_tx(self, contract, fn_name, args=None, value=0, sender=None):
        """Not used — Contree path uses execute_attempt instead."""
        raise NotImplementedError(
            "ContreeSandbox uses execute_attempt(); send_tx is not supported"
        )

    def execute_attempt(
        self,
        vault_address: str,
        vault_abi: list,
        proposal: ExploitProposal | None = None,
    ) -> ExecutionResult:
        """Deploy and run one exploit attempt inside the Contree container."""
        payload = {
            "rpc_url": ANVIL_RPC,
            "vault_address": vault_address,
            "vault_abi": vault_abi,
        }
        if proposal is None:
            payload["mode"] = "fallback"
        else:
            payload["mode"] = "proposal"
            payload["proposal"] = {
                "solidity_source": proposal.solidity_source,
                "contract_name": proposal.contract_name,
                "entry_function": proposal.entry_function,
                "entry_value_wei": proposal.entry_value_wei,
            }

        payload_path = f"{CONTREE_WORKDIR}/payload.json"
        self._image = (
            self._image.apply_files({payload_path: json.dumps(payload).encode()})
            .run(
                command="python3",
                args=[f"{CONTREE_WORKDIR}/scripts/contree_execute_attempt.py"],
                disposable=False,
                timeout=300,
                cwd=CONTREE_WORKDIR,
            )
            .wait()
        )

        stdout = self._image.stdout
        if not isinstance(stdout, str) or not stdout.strip():
            raise RuntimeError(
                f"Contree execute returned no output: {self._image.stderr}"
            )

        data = json.loads(stdout.strip().splitlines()[-1])
        return ExecutionResult(
            success=data["success"],
            attacker_balance_before=data["attacker_balance_before"],
            attacker_balance_after=data["attacker_balance_after"],
            vault_balance_before=data["vault_balance_before"],
            vault_balance_after=data["vault_balance_after"],
            revert_reason=data.get("revert_reason"),
            raw_tx_hashes=data.get("raw_tx_hashes", []),
            attacker_address=data.get("attacker_address"),
        )

    def _bootstrap(self) -> None:
        """Build or reuse a Contree image with Anvil + project files."""
        try:
            self._image = self._client.images.use(BOOTSTRAP_TAG, strict=True)
            logger.info("Reusing Contree bootstrap image %s", self._image.uuid)
            return
        except NotFoundError:
            pass
        except ForbiddenError as exc:
            raise ConfigurationError(
                "Contree Sandboxes returned 403 Forbidden. Your token may be "
                "valid for Token Factory but not Sandboxes, or CONTREE_PROJECT_ID "
                "is wrong (not 'default-project'). Get the real Project ID from "
                "console.nebius.com, or request access at https://contree.dev"
            ) from exc

        logger.info("Bootstrapping Contree EVM environment (first run is slow)…")
        try:
            base = self._client.images.use("ubuntu:22.04")
        except ForbiddenError as exc:
            raise ConfigurationError(
                "Contree Sandboxes returned 403 Forbidden. Verify Sandboxes "
                "beta access and set CONTREE_PROJECT_ID to your Nebius project ID."
            ) from exc
        steps = [
            "export DEBIAN_FRONTEND=noninteractive && "
            "apt-get update -qq && apt-get install -y -qq "
            "curl python3 python3-pip git ca-certificates > /dev/null",
            "curl -L https://foundry.paradigm.xyz | bash && "
            "/root/.foundry/bin/foundryup",
            "pip3 install -q web3 py-solc-x python-dotenv",
            "mkdir -p /root/.solcx && "
            "cp /root/.foundry/bin/solc /root/.solcx/solc-v0.8.19 2>/dev/null "
            "|| true",
            f"mkdir -p {CONTREE_WORKDIR}",
            "nohup /root/.foundry/bin/anvil --host 127.0.0.1 --port 8545 "
            "> /tmp/anvil.log 2>&1 & sleep 3 && "
            "cast block-number --rpc-url http://127.0.0.1:8545",
        ]
        image = base
        for cmd in steps:
            image = image.run(shell=cmd, disposable=False, timeout=600).wait()

        archive = _project_tarball()
        image = image.apply_files(
            {f"{CONTREE_WORKDIR}/project.tar.gz": archive}
        ).run(
            shell=f"cd {CONTREE_WORKDIR} && tar xzf project.tar.gz && rm project.tar.gz",
            disposable=False,
            timeout=120,
        ).wait()

        image = image.run(
            command="python3",
            args=["scripts/deploy_demo_contracts.py"],
            cwd=CONTREE_WORKDIR,
            disposable=False,
            timeout=300,
        ).wait()

        self._image = image.tag_as(BOOTSTRAP_TAG)
        logger.info("Contree bootstrap complete — image %s", self._image.uuid)


def _resolve_contree_credentials() -> tuple[str, str]:
    """Resolve Contree IAM token + project ID from env."""
    token = config.CONTREE_API_TOKEN or config.NEBIUS_API_KEY
    project_id = config.CONTREE_PROJECT_ID
    if not token:
        raise ConfigurationError(
            "Contree token required. Set CONTREE_API_TOKEN or NEBIUS_API_KEY. "
            "Get access: https://contree.dev (early access) or use your "
            "Nebius Token Factory API key from console.nebius.com"
        )
    if not project_id:
        raise ConfigurationError(
            "Contree project ID required. Set CONTREE_PROJECT_ID or "
            "NEBIUS_PROJECT_ID (Nebius console → your project → Project ID)"
        )
    return token, project_id


def check_contree() -> dict:
    """Return Contree connectivity status for dashboard/API."""
    try:
        token, project_id = _resolve_contree_credentials()
        auth = IAMAuth(token=token, project_id=project_id)
        client = ContreeSync(ContreeConfig(auth=auth))
        info = client.get_token_info()
        return {
            "configured": True,
            "connected": True,
            "token_uuid": info.token_uuid,
            "project_id": project_id,
            "mode": config.SANDBOX_MODE,
        }
    except Exception as exc:
        return {
            "configured": bool(
                config.CONTREE_API_TOKEN
                or config.NEBIUS_API_KEY
            ),
            "connected": False,
            "error": str(exc),
            "mode": config.SANDBOX_MODE,
        }


def _project_tarball() -> bytes:
    """Pack orchestrator, contracts, and scripts for upload to Contree."""
    root = Path(config.PROJECT_ROOT)
    include_dirs = ("orchestrator", "contracts", "scripts")
    include_files = ("requirements.txt",)

    buf = BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for name in include_files:
            path = root / name
            if path.exists():
                tar.add(path, arcname=name)
        for dirname in include_dirs:
            dirpath = root / dirname
            if not dirpath.exists():
                continue
            for file in dirpath.rglob("*"):
                if file.is_file() and "__pycache__" not in str(file):
                    arcname = file.relative_to(root)
                    tar.add(file, arcname=str(arcname))
    return buf.getvalue()
