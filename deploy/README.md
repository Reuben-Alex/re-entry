# Deploying the Re-entry dashboard

Judges need an HTTPS URL. The demo is this container: Anvil on
`127.0.0.1:8545`, the demo contracts, and the dashboard on port 8000.
`SANDBOX_MODE=local`. Nemotron calls go to Nebius Token Factory. Contree is
not used.

Nebius Serverless AI endpoints are long-lived container VMs. Each HTTP port
gets a managed `https://` URL, so a public IP is optional. Auth stays `none`
so a Devpost link opens with no header.

## Local

```bash
anvil --port 8545 &
source .venv/bin/activate
python scripts/deploy_demo_contracts.py
uvicorn dashboard.app:app --host 0.0.0.0 --port 8000
```

Open http://127.0.0.1:8000

## Image

Build from the repo root. `.dockerignore` keeps `.env` out of the image.

```bash
docker build -t re-entry-dashboard -f deploy/Dockerfile .
docker run --rm -p 8000:8000 \
  -e NEBIUS_API_KEY \
  -e TAVILY_API_KEY \
  -e SANDBOX_MODE=local \
  re-entry-dashboard
```

The entrypoint exits if Anvil or contract deploy fails. Stopping the
container drops chain state; the next start redeploys.

## Nebius Serverless AI endpoint

Requires the `nebius` CLI, logged into the hackathon project.

1. Create a Container Registry. Log Docker in with a short-lived token:

```bash
nebius iam get-access-token | docker login "cr.${REGION}.nebius.cloud" \
  --username iam --password-stdin
```

2. Build and push. Do not pass API keys as build args.

```bash
docker build --platform linux/amd64 \
  -t "cr.${REGION}.nebius.cloud/${REGISTRY}/re-entry:demo" \
  -f deploy/Dockerfile .
docker push "cr.${REGION}.nebius.cloud/${REGISTRY}/re-entry:demo"
```

3. Store `NEBIUS_API_KEY` and `TAVILY_API_KEY` in SecretStash. Create an
   on-demand CPU endpoint (about 4 vCPU / 16 GB). No GPU. Not preemptible.

```bash
nebius ai endpoint create \
  --name re-entry \
  --image "cr.${REGION}.nebius.cloud/${REGISTRY}/re-entry:demo" \
  --platform cpu-d3 \
  --preset 4vcpu-16gb \
  --container-port 8000 \
  --auth none \
  --on-demand \
  --env SANDBOX_MODE=local \
  --env-secret NEBIUS_API_KEY=<secret> \
  --env-secret TAVILY_API_KEY=<secret> \
  --subnet-id <subnet_ID>
```

4. The HTTPS URL is in `status.public_endpoints`. Check it:

```bash
curl -fsS "https://<endpoint-host>/health"
```

Expect `{"status":"ok"}`. Then open the URL and run VulnerableTreasury until
the Story tab finishes a live pipeline.

5. Stop the endpoint after judging. Compute billing runs while it is up.
   Anyone with the URL can click Run and spend Token Factory quota. Rotate
   the keys after the deadline.

## Health

`GET /health` returns `{"status":"ok"}`.

`GET /api/status` reports Anvil, sandbox mode, and whether a results file exists.
