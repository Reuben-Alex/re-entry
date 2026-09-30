#!/usr/bin/env bash
set -euo pipefail
cd /app

anvil --host 127.0.0.1 --port 8545 >/tmp/anvil.log 2>&1 &
for i in $(seq 1 30); do
  if cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1; then
    break
  fi
  sleep 0.5
done

python scripts/deploy_demo_contracts.py || true
exec uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
