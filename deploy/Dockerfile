# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl git ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

# Foundry (anvil + cast)
RUN curl -L https://foundry.paradigm.xyz | bash \
    && /root/.foundry/bin/foundryup \
    && ln -sf /root/.foundry/bin/anvil /usr/local/bin/anvil \
    && ln -sf /root/.foundry/bin/cast /usr/local/bin/cast \
    && ln -sf /root/.foundry/bin/forge /usr/local/bin/forge

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt uvicorn
# solcx looks up this path. GitHub is used because solc-bin.ethereum.org
# does not resolve from every build network.
RUN mkdir -p /root/.solcx \
    && curl -fsSL -o /root/.solcx/solc-v0.8.19 \
      https://github.com/ethereum/solidity/releases/download/v0.8.19/solc-static-linux \
    && chmod +x /root/.solcx/solc-v0.8.19

COPY . .

ENV PYTHONUNBUFFERED=1 \
    SANDBOX_MODE=local \
    LOCAL_RPC_URL=http://127.0.0.1:8545 \
    ENABLE_PATCH_VERIFY=true

EXPOSE 8000

COPY deploy/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
CMD ["/entrypoint.sh"]
