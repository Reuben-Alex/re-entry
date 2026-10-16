"""
Re-entry web dashboard — full-site UI with live pipeline runs.
"""
import asyncio
import json
import sys
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.runner import (
    TARGETS,
    check_anvil,
    deploy_contracts,
    get_session,
    load_all_results,
    start_custom_run,
    start_run,
    start_suite,
)
from orchestrator import challenges, config
from orchestrator.contree_sandbox import check_contree

app = FastAPI(title="Re-entry")
_templates_dir = str(Path(__file__).resolve().parent / "templates")
templates = Jinja2Templates(directory=_templates_dir)
templates.env.cache = None

VERDICT_META = {
    "vulnerable_agent_generated": {
        "label": "Exploit confirmed",
        "sub": "Agent-generated contract drained the vault",
        "status": "success",
        "icon": "✓",
    },
    "vulnerable_fallback": {
        "label": "Safety-net fallback",
        "sub": "ABI safety net fired after agent retries — not the primary claim",
        "status": "warn",
        "icon": "⚠",
    },
    "no_exploit_found": {
        "label": "No exploit found",
        "sub": "Agent exhausted retries without draining funds",
        "status": "fail",
        "icon": "✗",
    },
    "unfunded_target": {
        "label": "Target unfunded",
        "sub": "Contract had no ETH — redeploy required",
        "status": "fail",
        "icon": "✗",
    },
    "infra_error": {
        "label": "Infrastructure error",
        "sub": "Sandbox or deployment failure",
        "status": "fail",
        "icon": "✗",
    },
}


def _load_benchmark() -> dict | None:
    path = Path(config.RESULTS_DIR) / "benchmark.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _load_held_out() -> dict | None:
    path = Path(config.RESULTS_DIR) / "held_out_run.json"
    if path.exists():
        return json.loads(path.read_text())
    return None


def _run_summary(raw: dict) -> dict:
    agent = fallback = failed = 0
    for report in raw.values():
        verdict = report.get("verdict", "no_exploit_found")
        if verdict == "vulnerable_agent_generated":
            agent += 1
        elif verdict == "vulnerable_fallback":
            fallback += 1
        else:
            failed += 1
    total = agent + fallback + failed
    return {
        "agent": agent,
        "fallback": fallback,
        "failed": failed,
        "total": total,
        "headline": (
            f"Agent-generated (no fallback): {agent}/{total}"
            if total
            else "No runs yet"
        ),
    }


def _eth(wei: int | float) -> str:
    return f"{float(wei) / 1e18:.4f}"


def _parse_citation(citation: str) -> list[dict]:
    if not citation:
        return []
    for sep in (" – ", " - "):
        if sep in citation:
            title, url = citation.split(sep, 1)
            return [
                {"title": title.strip(), "url": url.strip(), "content": citation}
            ]
    return [{"title": "Citation", "url": "", "content": citation}]


def _enrich(name: str, report: dict) -> dict:
    verdict = report.get("verdict", "no_exploit_found")
    meta = VERDICT_META.get(verdict, VERDICT_META["no_exploit_found"])
    sources = report.get("precedent_sources", [])
    if not sources and report.get("precedent_citation"):
        sources = _parse_citation(report["precedent_citation"])

    return {
        **report,
        "contract_name": name,
        "verdict_label": meta["label"],
        "verdict_sub": meta["sub"],
        "verdict_status": meta["status"],
        "verdict_icon": meta["icon"],
        "drain_eth": _eth(report.get("drain_amount_wei", 0)),
        "gain_eth": _eth(report.get("attacker_gain_wei", 0)),
        "total_s": round(report.get("total_pipeline_s", 0), 1),
        "precedent_sources": sources,
        "risk_primary": report.get("risk_flags", [{}])[0]
        if report.get("risk_flags")
        else {},
        "has_foundry_poc": bool(report.get("foundry_poc")),
        "has_patch": bool(report.get("patch") or report.get("patch_diff")),
        "patch_verified": report.get("patch_verified", False),
        "patch_status": report.get("patch_status", "skipped"),
        "lifecycle_story": report.get("lifecycle_story"),
    }


class RunRequest(BaseModel):
    target: str


class RunSuiteRequest(BaseModel):
    tier: str = "held_out_sealed"


class CustomRunRequest(BaseModel):
    source: str
    contract_name: str | None = None


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    raw = load_all_results()
    targets = [_enrich(name, r) for name, r in raw.items()]
    anvil = check_anvil()
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "targets": targets,
            "target_list": TARGETS,
            "challenge_groups": challenges.manifest_summary(),
            "anvil": anvil,
            "contree": check_contree(),
            "sandbox_mode": config.SANDBOX_MODE,
            "has_results": bool(targets),
            "benchmark": _load_benchmark(),
            "summary": _run_summary(raw),
            "held_out": _load_held_out(),
        },
    )


@app.get("/api/status")
async def api_status():
    anvil = check_anvil()
    deployed = {}
    deployed_path = Path(config.PROJECT_ROOT) / "deployed_contracts.json"
    if deployed_path.exists():
        deployed = json.loads(deployed_path.read_text())
    return {
        "anvil": anvil,
        "contree": check_contree(),
        "sandbox_mode": config.SANDBOX_MODE,
        "deployed": list(deployed.keys()),
        "results": list(load_all_results().keys()),
        "benchmark": _load_benchmark(),
        "held_out": _load_held_out(),
    }


@app.get("/api/benchmark")
async def api_benchmark():
    data = _load_benchmark()
    if data is None:
        raise HTTPException(status_code=404, detail="No benchmark.json yet")
    return data


@app.get("/api/patch/{target}")
async def api_patch_diff(target: str):
    raw = load_all_results()
    if target not in raw:
        raise HTTPException(status_code=404, detail="No results for target")
    patch_diff = raw[target].get("patch_diff") or raw[target].get("patch", {}).get(
        "diff"
    )
    patched_source = raw[target].get("patch", {}).get("patched_source")
    body = patch_diff or patched_source
    if not body:
        raise HTTPException(status_code=404, detail="No patch for this run")
    filename = f"{target}_patch.diff" if patch_diff else f"{target}_patched.sol"
    return PlainTextResponse(
        body,
        media_type="text/plain",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/api/foundry/{target}")
async def api_foundry_poc(target: str):
    raw = load_all_results()
    if target not in raw:
        raise HTTPException(status_code=404, detail="No results for target")
    poc = raw[target].get("foundry_poc")
    if not poc:
        raise HTTPException(status_code=404, detail="No Foundry PoC for this run")
    return PlainTextResponse(
        poc,
        media_type="text/plain",
        headers={
            "Content-Disposition": f'attachment; filename="{target}_Exploit.t.sol"'
        },
    )


@app.post("/api/deploy")
async def api_deploy():
    try:
        deployed = deploy_contracts()
        return {"ok": True, "contracts": list(deployed.keys())}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/challenges")
async def api_challenges():
    return challenges.manifest_summary()


@app.post("/api/run-suite")
async def api_run_suite(body: RunSuiteRequest):
    if config.SANDBOX_MODE.lower() != "contree":
        anvil = check_anvil()
        if not anvil.get("connected"):
            raise HTTPException(
                status_code=503,
                detail="Anvil not running. Start: anvil --port 8545",
            )
    try:
        session = start_suite(body.tier)
        return {"run_id": session.run_id, "tier": body.tier}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/run-custom")
async def api_run_custom(body: CustomRunRequest):
    if config.SANDBOX_MODE.lower() != "contree":
        anvil = check_anvil()
        if not anvil.get("connected"):
            raise HTTPException(
                status_code=503,
                detail="Anvil not running. Start: anvil --port 8545",
            )
    try:
        session = start_custom_run(body.source, body.contract_name)
        return {"run_id": session.run_id, "target": session.target}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.post("/api/run")
async def api_run(body: RunRequest):
    if config.SANDBOX_MODE.lower() != "contree":
        anvil = check_anvil()
        if not anvil.get("connected"):
            raise HTTPException(
                status_code=503,
                detail="Anvil not running. Start: anvil --port 8545",
            )
    try:
        session = start_run(body.target)
        return {"run_id": session.run_id, "target": session.target}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/api/runs/{run_id}/stream")
async def api_stream(run_id: str):
    session = get_session(run_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Run not found")

    async def event_generator():
        sent = 0
        last_yield = time.monotonic()
        while True:
            while sent < len(session.events):
                yield f"data: {json.dumps(session.events[sent])}\n\n"
                sent += 1
                last_yield = time.monotonic()
            if session.done:
                payload = {
                    "type": "__done__",
                    "error": session.error,
                    "report": session.report,
                }
                yield f"data: {json.dumps(payload)}\n\n"
                break
            if time.monotonic() - last_yield >= 15:
                yield ": keepalive\n\n"
                last_yield = time.monotonic()
            await asyncio.sleep(0.25)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/api/results")
async def api_results():
    raw = load_all_results()
    return {name: _enrich(name, r) for name, r in raw.items()}


@app.get("/health")
async def health():
    return {"status": "ok"}
