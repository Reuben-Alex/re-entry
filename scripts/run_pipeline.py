"""
Entry point: runs the full agent pipeline against manifest targets.
"""
import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(_SCRIPTS))
from ensure_venv import ensure_project_python

ensure_project_python()

sys.path.insert(0, str(_SCRIPTS.parent))

from orchestrator import challenges, config
from orchestrator.loop import run_pipeline
from orchestrator.sandbox import create_sandbox

VERDICT_COLORS = {
    "vulnerable_agent_generated": "\033[92m",
    "vulnerable_fallback": "\033[93m",
    "no_exploit_found": "\033[91m",
    "unfunded_target": "\033[91m",
    "infra_error": "\033[91m",
}
RESET = "\033[0m"


def _print_verdict(name: str, report: dict):
    verdict = report.get("verdict", "unknown")
    color = VERDICT_COLORS.get(verdict, "")
    print(f"\n{color}{'=' * 60}")
    print(f"  {name}: {verdict}")
    print(f"  {report.get('verdict_explanation', '')}")
    print(f"  Drain: {report.get('drain_amount_wei', 0)} wei")
    print(f"  Patch verified: {report.get('patch_verified', False)}")
    print(f"  Attempts: {report.get('attempts', 0)}")
    print(f"  Used fallback: {report.get('used_fallback', False)}")
    print(f"  Pipeline time: {report.get('total_pipeline_s', 0):.1f}s")
    print(f"{'=' * 60}{RESET}")


def _deploy_all():
    import subprocess

    script = Path(__file__).resolve().parent / "deploy_demo_contracts.py"
    subprocess.run([sys.executable, str(script)], check=True)
    with open(Path(config.PROJECT_ROOT) / "deployed_contracts.json") as f:
        return json.load(f)


def _target_names(args) -> list[str]:
    if args.tier:
        return challenges.list_pipeline_targets(args.tier)
    if args.tiers:
        names = []
        for tier in args.tiers.split(","):
            names.extend(challenges.list_pipeline_targets(tier.strip()))
        return names
    return challenges.list_pipeline_targets()


def main():
    parser = argparse.ArgumentParser(description="Run Re-entry pipeline on manifest targets")
    parser.add_argument(
        "--tier",
        help="Run only targets in this tier (train, held_out_sealed, control, …)",
    )
    parser.add_argument(
        "--tiers",
        help="Comma-separated tiers (e.g. train,held_out_sealed)",
    )
    args = parser.parse_args()

    results_dir = Path(config.RESULTS_DIR)
    results_dir.mkdir(parents=True, exist_ok=True)

    if not hasattr(create_sandbox(), "get_deployed_contracts"):
        print("Deploying demo contracts…")
        deployed = _deploy_all()
        deploy_fn = _deploy_all
        print("Sandbox: local Anvil")
    else:
        sandbox = create_sandbox()
        deployed = sandbox.get_deployed_contracts()
        deployer = sandbox.deployer
        deploy_fn = None
        print(f"Sandbox: contree (project {config.CONTREE_PROJECT_ID or 'configured'})")

    names = _target_names(args)
    results = {}
    for name in names:
        if name not in deployed:
            print(f"Skipping {name} — not in deployed_contracts.json")
            continue

        sandbox = create_sandbox()
        if hasattr(sandbox, "get_deployed_contracts"):
            deployed = sandbox.get_deployed_contracts()
            deployer = sandbox.deployer
            target_deploy_fn = None
        else:
            deployed = json.loads(
                (Path(config.PROJECT_ROOT) / "deployed_contracts.json").read_text()
            )
            deployer = sandbox.w3.eth.accounts[0]
            target_deploy_fn = _deploy_all

        try:
            source_code = challenges.resolve_source(name)
        except (ValueError, FileNotFoundError) as exc:
            print(f"Skipping {name} — {exc}")
            continue

        abi = deployed[name]["abi"]
        vault_address = deployed[name]["address"]

        print(f"\n>>> Running pipeline against {name}...")
        report = run_pipeline(
            name,
            abi,
            source_code,
            sandbox,
            vault_address,
            deployer,
            deploy_fn=target_deploy_fn,
        )
        results[name] = report
        _print_verdict(name, report)

    out_path = results_dir / "latest_run.json"
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nWrote {out_path}")


if __name__ == "__main__":
    main()
