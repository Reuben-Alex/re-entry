#!/usr/bin/env python3
"""Summarize agent-generated vs fallback rates across result JSON files."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"


def score(path: Path) -> dict:
    data = json.loads(path.read_text())
    # benchmark.json shape vs latest_run.json
    if "targets" in data and "headline" in data:
        return {
            "file": path.name,
            "headline": data.get("headline"),
            "per_target": {
                name: {
                    "agent_success_rate": t.get("agent_success_rate"),
                    "fallback_rate": t.get("fallback_rate"),
                    "total_runs": t.get("total_runs"),
                }
                for name, t in data.get("targets", {}).items()
            },
        }
    agent = fallback = failed = 0
    for name, report in data.items():
        if not isinstance(report, dict):
            continue
        v = report.get("verdict", "")
        if v == "vulnerable_agent_generated":
            agent += 1
        elif v == "vulnerable_fallback":
            fallback += 1
        else:
            failed += 1
    total = agent + fallback + failed
    return {
        "file": path.name,
        "agent_generated": agent,
        "fallback": fallback,
        "other": failed,
        "total": total,
        "headline": f"Agent-generated (no fallback): {agent}/{total}" if total else "empty",
    }


def main():
    paths = list(RESULTS.glob("*.json"))
    if not paths:
        print("No results/*.json yet — run scripts/benchmark_pipeline.py")
        sys.exit(1)
    for p in sorted(paths):
        print(json.dumps(score(p), indent=2))
        print("---")


if __name__ == "__main__":
    main()
