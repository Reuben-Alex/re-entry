"""
Benchmark pipeline reliability: run N times, measure fallback rate + timing.
"""
import json
import sys
import time
from pathlib import Path
from statistics import mean

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from ensure_venv import ensure_project_python

ensure_project_python()

sys.path.insert(0, str(_SCRIPTS.parent))

import os

os.environ.setdefault("ENABLE_PATCH_VERIFY", "false")

from orchestrator import challenges, config
from orchestrator.loop import run_pipeline
from orchestrator.sandbox import create_sandbox

DEFAULT_RUNS = 10
BENCHMARK_TIERS = ("train", "held_out_sealed")


def _benchmark_targets() -> list[str]:
    names: list[str] = []
    for tier in BENCHMARK_TIERS:
        names.extend(challenges.list_pipeline_targets(tier))
    return names


def _deploy_all():
    import subprocess

    script = Path(__file__).resolve().parent / "deploy_demo_contracts.py"
    subprocess.run([sys.executable, str(script)], check=True)
    with open(Path(config.PROJECT_ROOT) / "deployed_contracts.json") as f:
        return json.load(f)


def _run_benchmark(target: str, runs: int, deployed: dict) -> dict:
    source_code = challenges.resolve_source(target)
    abi = deployed[target]["abi"]
    vault_address = deployed[target]["address"]

    agent_success = 0
    fallback_success = 0
    total_fail = 0
    timings = []
    per_run = []

    for i in range(runs):
        sandbox = create_sandbox()
        if hasattr(sandbox, "get_deployed_contracts"):
            deployed = sandbox.get_deployed_contracts()
            deployer = sandbox.deployer
            deploy_fn = None
            vault_address = deployed[target]["address"]
        else:
            deployed = _deploy_all()
            deployer = sandbox.w3.eth.accounts[0]
            deploy_fn = _deploy_all
            vault_address = deployed[target]["address"]

        start = time.time()
        report = run_pipeline(
            target,
            abi,
            source_code,
            sandbox,
            vault_address,
            deployer,
            deploy_fn=deploy_fn,
        )
        elapsed = time.time() - start
        timings.append(elapsed)
        verdict = report.get("verdict", "no_exploit_found")

        if verdict == "vulnerable_agent_generated":
            agent_success += 1
        elif verdict == "vulnerable_fallback":
            fallback_success += 1
        else:
            total_fail += 1

        per_run.append(
            {
                "run": i + 1,
                "verdict": verdict,
                "used_fallback": report.get("used_fallback", False),
                "total_time_s": elapsed,
                "attempts": report.get("attempts", 0),
            }
        )
        print(f"  Run {i + 1}/{runs}: {verdict} ({elapsed:.1f}s)")

    agent_times = [
        r["total_time_s"]
        for r in per_run
        if r["verdict"] == "vulnerable_agent_generated"
    ]

    return {
        "target": target,
        "total_runs": runs,
        "agent_success": agent_success,
        "fallback_success": fallback_success,
        "total_fail": total_fail,
        "agent_success_rate": agent_success / runs if runs else 0,
        "fallback_rate": fallback_success / runs if runs else 0,
        "avg_time_all_s": mean(timings) if timings else 0,
        "avg_time_agent_success_s": mean(agent_times) if agent_times else 0,
        "max_time_s": max(timings) if timings else 0,
        "per_run": per_run,
    }


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RUNS

    results_dir = Path(config.RESULTS_DIR)
    results_dir.mkdir(parents=True, exist_ok=True)

    print("Deploying demo contracts for benchmark…")
    deployed = _deploy_all()

    targets = _benchmark_targets()
    summaries = {}
    for target in targets:
        print(f"\nBenchmarking {target} ({runs} runs)…")
        summaries[target] = _run_benchmark(target, runs, deployed)

    vault_key = "VulnerableVault"
    vault = summaries.get(vault_key, {})
    agent_n = vault.get("agent_success", 0)
    out = {
        "runs_per_target": runs,
        "tiers": list(BENCHMARK_TIERS),
        "targets": summaries,
        "headline": (
            f"Ultra succeeds without fallback in {agent_n}/{runs} "
            f"{vault_key} runs"
        ),
    }

    out_path = results_dir / "benchmark.json"
    out_path.write_text(json.dumps(out, indent=2))

    print("\n" + "=" * 50)
    print(out["headline"])
    for name, row in summaries.items():
        if name == vault_key:
            continue
        print(
            f"{name}: {row['agent_success']}/{runs} agent, "
            f"{row['fallback_success']}/{runs} fallback"
        )
    if vault:
        print(f"Avg time ({vault_key}): {vault['avg_time_all_s']:.1f}s")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
