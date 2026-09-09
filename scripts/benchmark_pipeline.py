"""
Benchmark pipeline reliability: run N times, measure fallback rate + timing.
"""
import json
import sys
import time
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import config
from orchestrator.loop import run_pipeline
from orchestrator.sandbox import create_sandbox

CONTRACTS_DIR = Path(config.PROJECT_ROOT) / "contracts"
DEFAULT_RUNS = 25
TARGET = "VulnerableVault"


def main():
    runs = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_RUNS

    deployed_path = Path(config.PROJECT_ROOT) / "deployed_contracts.json"
    with open(deployed_path) as f:
        deployed = json.load(f)

    source_code = (CONTRACTS_DIR / f"{TARGET}.sol").read_text()
    abi = deployed[TARGET]["abi"]
    vault_address = deployed[TARGET]["address"]

    results_dir = Path(config.RESULTS_DIR)
    results_dir.mkdir(parents=True, exist_ok=True)

    agent_success = 0
    fallback_success = 0
    total_fail = 0
    timings = []
    per_run = []

    for i in range(runs):
        sandbox = create_sandbox()
        deployer = sandbox.w3.eth.accounts[0]
        start = time.time()
        report = run_pipeline(
            TARGET, abi, source_code, sandbox, vault_address, deployer
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
                "step_timings": report.get("step_timings", []),
            }
        )
        print(f"Run {i + 1}/{runs}: {verdict} ({elapsed:.1f}s)")

    agent_times = [
        r["total_time_s"]
        for r in per_run
        if r["verdict"] == "vulnerable_agent_generated"
    ]

    summary = {
        "target": TARGET,
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

    out_path = results_dir / "benchmark.json"
    out_path.write_text(json.dumps(summary, indent=2))

    print("\n" + "=" * 50)
    print(f"Agent-generated success: {agent_success}/{runs} ({100 * agent_success / runs:.0f}%)")
    print(f"Fallback success:         {fallback_success}/{runs} ({100 * fallback_success / runs:.0f}%)")
    print(f"Total failure:            {total_fail}/{runs} ({100 * total_fail / runs:.0f}%)")
    if agent_times:
        print(f"Avg time (agent success): {mean(agent_times):.1f}s")
    print(f"Avg time (all runs):      {mean(timings):.1f}s")
    print(f"Max time:                 {max(timings):.1f}s")
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
