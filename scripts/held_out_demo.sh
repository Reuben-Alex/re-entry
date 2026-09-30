#!/usr/bin/env bash
# Held-out demo: run sealed (or live) manifest targets without printing source.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source .venv/bin/activate

ANVIL_BIN="${ANVIL_BIN:-$(command -v anvil || echo /opt/homebrew/bin/anvil)}"
TIER="${TIER:-held_out_sealed}"

if ! curl -sf http://127.0.0.1:8545 >/dev/null 2>&1; then
  echo "Starting Anvil…"
  "$ANVIL_BIN" --port 8545 >/tmp/re-entry-anvil.log 2>&1 &
  sleep 2
fi

python scripts/deploy_demo_contracts.py

echo ""
echo "=== Held-out demo (tier=${TIER}, source not printed) ==="
echo ""

python - <<PY
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(".").resolve()))

from orchestrator import challenges
from orchestrator.loop import run_pipeline
from orchestrator.sandbox import create_sandbox

tier = "${TIER}"
names = challenges.list_pipeline_targets(tier)
if not names:
    print(f"No targets for tier {tier}", file=sys.stderr)
    sys.exit(1)

deployed = json.loads(Path("deployed_contracts.json").read_text())
sandbox = create_sandbox()
deployer = sandbox.w3.eth.accounts[0]

def deploy_fn():
    import subprocess
    subprocess.run([sys.executable, "scripts/deploy_demo_contracts.py"], check=True)

results = {}
for target in names:
    print(f"Target: {target} @ {deployed[target]['address']}")
    print("Running pipeline (internals not shown)…")
    source = challenges.resolve_source(target)
    report = run_pipeline(
        target,
        deployed[target]["abi"],
        source,
        sandbox,
        deployed[target]["address"],
        deployer,
        deploy_fn=deploy_fn,
    )
    verdict = report.get("verdict", "unknown")
    drain = report.get("drain_amount_wei", 0) / 1e18
    patch_ok = report.get("patch_verified", False)
    patch_status = report.get("patch_status", "skipped")
    print(f"  Verdict:        {verdict}")
    print(f"  Drain:          {drain:.2f} ETH")
    print(f"  Patch status:   {patch_status}")
    print(f"  Patch verified: {patch_ok}")
    if report.get("patch_diff"):
        n = len(report["patch_diff"].splitlines())
        print(f"  Patch diff:     {n} lines (see dashboard)")
    print("")
    results[target] = report

out = Path("results/held_out_run.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(results, indent=2))
print(f"Wrote {out}")
PY

echo "Dashboard: http://127.0.0.1:8000 (Held-out group · Run held-out suite)"
