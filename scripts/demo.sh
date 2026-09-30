#!/usr/bin/env bash
# One-command Re-entry demo: Anvil + deploy + dashboard + sample run hint
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [ ! -d .venv ]; then
  echo "Create venv first: python -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt"
  exit 1
fi
source .venv/bin/activate

ANVIL_BIN="${ANVIL_BIN:-$(command -v anvil || echo /opt/homebrew/bin/anvil)}"

if ! curl -sf http://127.0.0.1:8545 >/dev/null 2>&1; then
  echo "Starting Anvil on :8545…"
  "$ANVIL_BIN" --port 8545 >/tmp/re-entry-anvil.log 2>&1 &
  sleep 2
fi

echo "Deploying demo contracts…"
python scripts/deploy_demo_contracts.py

if ! curl -sf http://127.0.0.1:8000/health >/dev/null 2>&1; then
  echo "Starting dashboard on :8000…"
  uvicorn dashboard.app:app --port 8000 >/tmp/re-entry-dashboard.log 2>&1 &
  sleep 2
fi

echo ""
echo "Re-entry demo ready:"
echo "  Dashboard:  http://127.0.0.1:8000"
echo ""
echo "Recommended demo order:"
echo "  1. VulnerableVault   — reentrancy (train target)"
echo "  2. VulnerableTreasury — access-control (held-out)"
echo "  3. SafeVault           — control (should fail)"
echo ""
echo "  Held-out script:  bash scripts/held_out_demo.sh"
echo "  Full CLI:         python scripts/run_pipeline.py   (uses .venv automatically)"
echo "  Benchmark:        python scripts/benchmark_pipeline.py 5"
echo ""
echo "  Tip: activate venv first — source .venv/bin/activate"
echo "       or use .venv/bin/python instead of system python3"
