# Deploying the Re-entry dashboard

The hackathon requires a **working demo URL**. Local Anvil + Token Factory already
satisfies the “runs on Nebius Token Factory + NVIDIA open model” rule. Hosting
makes judging frictionless.

## Option A — local (demo / video recording)

```bash
anvil --port 8545 &
source .venv/bin/activate
python scripts/deploy_demo_contracts.py
uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000

## Option B — Docker (any cloud / Nebius VM)

```bash
docker build -t re-entry-dashboard -f deploy/Dockerfile .
docker run --rm -p 8000:8000 \
  -e NEBIUS_API_KEY \
  -e TAVILY_API_KEY \
  -e SANDBOX_MODE=local \
  re-entry-dashboard
```

The container starts Anvil, deploys demo contracts, and serves the dashboard on
port 8000. Point a Nebius Serverless Endpoint, Cloudflare Tunnel, or reverse
proxy at that port for the public Devpost URL.

## Option C — Nebius Serverless Endpoint

1. Build and push the image to a registry Nebius can pull.
2. Create a Serverless Endpoint that runs the image with `NEBIUS_API_KEY` and
   `TAVILY_API_KEY` as secrets.
3. Paste the HTTPS URL into Devpost as the demo link.
4. If Contree Sandboxes access is approved, set `SANDBOX_MODE=contree` and
   `CONTREE_PROJECT_ID`; otherwise keep `local` (Anvil in-container).

## Health check

`GET /health` → `{"status":"ok"}`

`GET /api/status` → anvil / contree / sandbox_mode / results summary
