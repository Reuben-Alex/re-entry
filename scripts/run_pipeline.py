"""
Entry point: runs the full agent pipeline against demo contracts.
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator import config
from orchestrator.loop import run_pipeline
from orchestrator.sandbox import create_sandbox

CONTRACTS_DIR = Path(config.PROJECT_ROOT) / "contracts"
TARGETS = [
    "VulnerableVault",
    "SafeVault",
    "VulnerableTreasury",
    "SafeTreasury",
]

VERDICT_COLORS = {
    "vulnerable_agent_generated": "\033[92m",  # green
    "vulnerable_fallback": "\033[93m",  # yellow
    "no_exploit_found": "\033[91m",  # red
}
RESET = "\033[0m"


def _print_verdict(name: str, report: dict):
    verdict = report.get("verdict", "unknown")
    color = VERDICT_COLORS.get(verdict, "")
    print(f"\n{color}{'=' * 60}")
    print(f"  {name}: {verdict}")
    print(f"  {report.get('verdict_explanation', '')}")
    print(f"  Drain: {report.get('drain_amount_wei', 0)} wei")
    print(f"  Attempts: {report.get('attempts', 0)}")
    print(f"  Used fallback: {report.get('used_fallback', False)}")
    print(f"  Pipeline time: {report.get('total_pipeline_s', 0):.1f}s")
    print(f"{'=' * 60}{RESET}")

    source = report.get("generated_exploit_source", "")
    if source and source != "FALLBACK: Attacker.sol":
        lines = source.splitlines()[:30]
        print("\nGenerated exploit (first 30 lines):")
        print("-" * 40)
        for line in lines:
            print(line)
        if len(source.splitlines()) > 30:
            print("... (truncated)")


def main():
    deployed_path = Path(config.PROJECT_ROOT) / "deployed_contracts.json"
    if not deployed_path.exists():
        print("deployed_contracts.json not found. Run deploy_demo_contracts.py first.")
        sys.exit(1)

    with open(deployed_path) as f:
        deployed = json.load(f)

    results_dir = Path(config.RESULTS_DIR)
    results_dir.mkdir(parents=True, exist_ok=True)

    sandbox = create_sandbox()
    deployer = sandbox.w3.eth.accounts[0]

    results = {}
    for name in TARGETS:
        if name not in deployed:
            print(f"Skipping {name} — not in deployed_contracts.json")
            continue

        source_path = CONTRACTS_DIR / f"{name}.sol"
        source_code = source_path.read_text()
        abi = deployed[name]["abi"]
        vault_address = deployed[name]["address"]

        print(f"\n>>> Running pipeline against {name}...")
        report = run_pipeline(
            name, abi, source_code, sandbox, vault_address, deployer
        )
        results[name] = report
        _print_verdict(name, report)

    out_path = results_dir / "latest_run.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
