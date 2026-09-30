"""Background pipeline runner for live dashboard sessions."""
import json
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from queue import Empty, Queue
from typing import Any

from web3 import Web3

from orchestrator import challenges, config
from orchestrator.chain import compile_contract_path, deploy, get_web3
from orchestrator.loop import run_pipeline
from orchestrator.preflight import load_deployed
from orchestrator.sandbox import create_sandbox

DEPLOYED_PATH = Path(config.PROJECT_ROOT) / "deployed_contracts.json"
RESULTS_PATH = Path(config.RESULTS_DIR) / "latest_run.json"


def all_targets() -> list[str]:
    return [t.name for t in challenges.list_for_dashboard()]


TARGETS = all_targets()


@dataclass
class RunSession:
    """Tracks a live pipeline run and its streamed events."""

    run_id: str
    target: str
    events: list[dict] = field(default_factory=list)
    done: bool = False
    error: str | None = None
    report: dict | None = None
    _queue: Queue = field(default_factory=Queue)

    def emit(self, event_type: str, **data: Any) -> None:
        event = {"type": event_type, **data}
        self.events.append(event)
        self._queue.put(event)

    def drain_queue(self) -> list[dict]:
        drained = []
        while True:
            try:
                drained.append(self._queue.get_nowait())
            except Empty:
                break
        return drained


# Session TTL cleanup for hosted demos
_SESSION_TTL_S = 3600
_sessions: dict[str, RunSession] = {}
_lock = threading.Lock()
_session_created: dict[str, float] = {}


def _purge_stale_sessions() -> None:
    now = time.time()
    with _lock:
        stale = [
            rid
            for rid, created in _session_created.items()
            if now - created > _SESSION_TTL_S and _sessions.get(rid) and _sessions[rid].done
        ]
        for rid in stale:
            _sessions.pop(rid, None)
            _session_created.pop(rid, None)


def check_anvil() -> dict:
    """Return Anvil connectivity status."""
    try:
        w3 = get_web3(config.LOCAL_RPC_URL)
        block = w3.eth.block_number
        return {"connected": True, "block": block, "rpc": config.LOCAL_RPC_URL}
    except Exception as exc:
        return {"connected": False, "error": str(exc), "rpc": config.LOCAL_RPC_URL}


def deploy_contracts() -> dict:
    """Deploy all manifest contracts to local Anvil."""
    w3 = get_web3(config.LOCAL_RPC_URL)
    deployer = w3.eth.accounts[0]
    depositors = w3.eth.accounts[1:4]
    amount = Web3.to_wei(1, "ether")

    deployed = {}
    for target in challenges.list_deployable():
        try:
            source_path = challenges.resolve_source_path(target)
        except FileNotFoundError:
            if target.tier == "held_out_live":
                continue
            raise
        cname = target.solidity_contract_name
        abi, bytecode = compile_contract_path(source_path, cname)
        contract = deploy(w3, abi, bytecode, deployer)
        for depositor in depositors:
            tx = contract.functions.deposit().transact(
                {"from": depositor, "value": amount}
            )
            w3.eth.wait_for_transaction_receipt(tx)
        deployed[target.name] = {"address": contract.address, "abi": abi}

    DEPLOYED_PATH.write_text(json.dumps(deployed, indent=2))
    return deployed


def _run_target(session: RunSession) -> None:
    try:
        sandbox_mode = config.SANDBOX_MODE.lower()
        sandbox = create_sandbox()

        if hasattr(sandbox, "get_deployed_contracts"):
            session.emit(
                "log",
                level="info",
                message="Using Nebius Contree sandbox (bootstrapping if first run)…",
            )
            deployed = sandbox.get_deployed_contracts()
            deployer = sandbox.deployer
            deploy_fn = None
        else:
            deployed = load_deployed()
            if not deployed:
                session.emit(
                    "log", level="info", message="Deploying fresh contracts…"
                )
                deployed = deploy_contracts()
            deployer = sandbox.w3.eth.accounts[0]
            deploy_fn = deploy_contracts

        target = session.target
        if target not in deployed:
            raise ValueError(f"Unknown target: {target}")

        source = challenges.resolve_source(target)

        session.emit(
            "log",
            level="cmd",
            message=f"re-entry run --target {target} --sandbox {sandbox_mode}",
        )

        report = run_pipeline(
            target,
            deployed[target]["abi"],
            source,
            sandbox,
            deployed[target]["address"],
            deployer,
            on_event=session.emit,
            deploy_fn=deploy_fn,
        )

        if deploy_fn is not None:
            deployed = load_deployed()
            if target in deployed:
                report["target_address"] = deployed[target]["address"]

        ct = challenges.get_target(target)
        if ct:
            report["challenge_tier"] = ct.tier
            report["vuln_class"] = ct.vuln_class

        session.report = report
        _save_result(target, report)
        session.done = True
    except Exception as exc:
        session.error = str(exc)
        session.emit("error", message=str(exc))
        session.done = True


def _run_suite(session: RunSession, tier: str) -> None:
    """Run multiple targets sequentially in one SSE session."""
    try:
        names = challenges.list_pipeline_targets(tier)
        if not names:
            raise ValueError(f"No targets for tier {tier}")
        session.emit("suite_start", tier=tier, targets=names)
        for name in names:
            session.target = name
            session.emit("suite_target", target=name)
            sub = RunSession(run_id=session.run_id, target=name)

            def forward(event_type: str, **data):
                session.emit(event_type, **data)

            sandbox = create_sandbox()
            deployed = load_deployed()
            if not deployed:
                deployed = deploy_contracts()
            deployer = sandbox.w3.eth.accounts[0]
            source = challenges.resolve_source(name)
            report = run_pipeline(
                name,
                deployed[name]["abi"],
                source,
                sandbox,
                deployed[name]["address"],
                deployer,
                on_event=forward,
                deploy_fn=deploy_contracts,
            )
            _save_result(name, report)
            session.emit("suite_target_done", target=name, verdict=report.get("verdict"))
        session.emit("suite_done", tier=tier)
        session.done = True
    except Exception as exc:
        session.error = str(exc)
        session.emit("error", message=str(exc))
        session.done = True


def _save_result(target: str, report: dict) -> None:
    Path(config.RESULTS_DIR).mkdir(parents=True, exist_ok=True)
    existing = {}
    if RESULTS_PATH.exists():
        existing = json.loads(RESULTS_PATH.read_text())
    existing[target] = report
    RESULTS_PATH.write_text(json.dumps(existing, indent=2))


def start_run(target: str) -> RunSession:
    _purge_stale_sessions()
    if target not in TARGETS:
        raise ValueError(f"Invalid target. Choose from: {TARGETS}")
    run_id = uuid.uuid4().hex[:12]
    session = RunSession(run_id=run_id, target=target)
    with _lock:
        _sessions[run_id] = session
        _session_created[run_id] = time.time()
    thread = threading.Thread(target=_run_target, args=(session,), daemon=True)
    thread.start()
    return session


def start_suite(tier: str) -> RunSession:
    _purge_stale_sessions()
    run_id = uuid.uuid4().hex[:12]
    session = RunSession(run_id=run_id, target=f"suite:{tier}")
    with _lock:
        _sessions[run_id] = session
        _session_created[run_id] = time.time()
    thread = threading.Thread(target=_run_suite, args=(session, tier), daemon=True)
    thread.start()
    return session


def get_session(run_id: str) -> RunSession | None:
    with _lock:
        return _sessions.get(run_id)


def load_all_results() -> dict:
    if RESULTS_PATH.exists():
        raw = json.loads(RESULTS_PATH.read_text())
    else:
        raw = {}
    held_path = Path(config.RESULTS_DIR) / "held_out_run.json"
    if held_path.exists():
        held = json.loads(held_path.read_text())
        for name, report in held.items():
            if report.get("patch_verified") and (
                name not in raw or not raw[name].get("patch_verified")
            ):
                raw[name] = report
    return raw
