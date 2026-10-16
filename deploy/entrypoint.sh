#!/usr/bin/env bash
set -euo pipefail
cd /app

anvil --host 127.0.0.1 --port 8545 >/tmp/anvil.log 2>&1 &
ready=0
for i in $(seq 1 30); do
  if cast block-number --rpc-url http://127.0.0.1:8545 >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 0.5
done
if [ "$ready" -ne 1 ]; then
  echo "Anvil did not start" >&2
  cat /tmp/anvil.log >&2 || true
  exit 1
fi

python scripts/deploy_demo_contracts.py
exec uvicorn dashboard.app:app --host 0.0.0.0 --port "${PORT:-8000}"
