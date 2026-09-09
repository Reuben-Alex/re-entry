"""
Dashboard — FastAPI app rendering pipeline results for demo URL.
"""
import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import config

app = FastAPI(title="PoCForge Results")
templates = Jinja2Templates(
    directory=str(Path(__file__).resolve().parent / "templates")
)

RESULTS_PATH = Path(config.RESULTS_DIR) / "latest_run.json"

VERDICT_BADGE = {
    "vulnerable_agent_generated": ("VULNERABLE (Agent)", "badge-vuln"),
    "vulnerable_fallback": ("VULNERABLE (Fallback)", "badge-fallback"),
    "no_exploit_found": ("SECURE", "badge-secure"),
}


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    if not RESULTS_PATH.exists():
        raise HTTPException(
            status_code=404,
            detail="No results yet. Run scripts/run_pipeline.py first.",
        )
    with open(RESULTS_PATH) as f:
        results = json.load(f)

    enriched = {}
    for name, report in results.items():
        verdict = report.get("verdict", "no_exploit_found")
        label, css = VERDICT_BADGE.get(verdict, ("UNKNOWN", "badge-secure"))
        enriched[name] = {**report, "verdict_label": label, "verdict_css": css}

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "results": enriched},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
