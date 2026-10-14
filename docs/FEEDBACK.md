# Feedback — Nebius Token Factory, Nemotron, hosting

Written while building Re-entry for the Nebius x NVIDIA Global AI Hackathon.

## What worked

- The OpenAI-compatible endpoint at `https://api.tokenfactory.nebius.com/v1` dropped into the official OpenAI Python client with `base_url` and one API key. Nano, Super, and Ultra were callable as three model IDs with `response_format: json_object`.
- Splitting roles across Nemotron 3 Nano (ranked hypotheses), Ultra (exploit and patch), and Super (the evidence writeup) kept the cheap calls off the big model.
- Tavily plus the Anvil revert trace gave Ultra something concrete to revise, which is the loop we wanted for the Coding and Agentic Engineering track.
- Local Anvil inside the Docker image is enough to satisfy "runs on Token Factory and uses an NVIDIA open model." We did not need Contree for the demo.

## What got in the way

- Model IDs are case-sensitive and do not match a single pattern. Nano is `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, Super is `nvidia/nemotron-3-super-120b-a12b`, Ultra is `nvidia/Nemotron-3-Ultra-550b-a55b`. Copying the catalog ID is mandatory. A typo fails at call time, not at config load.
- Ultra sometimes returns an empty `message.content` after spending the token budget on `reasoning_content`. A 60 second client timeout and `max_tokens` of 8192 was too small for a full Solidity file. We raised the timeout to 180 seconds and `max_tokens` to 16384, and if content is empty we salvage a JSON object from `reasoning_content`. A `finish_reason` of `length` with an empty content field would be easier to diagnose if the API returned that state more explicitly in the error body.
- Hosting the demo wants a long-lived Anvil process next to the dashboard. A Serverless Endpoint that expects a request/response model is an awkward fit for a sandbox node that must stay up between "Run" clicks. We ship the Docker image so it can run on a Nebius VM. If Serverless cannot hold that process, that is the feedback: sandboxed agent demos need a long-running workload, not only a stateless completion endpoint.
- Contree Sandboxes stayed optional. Early access is easy to miss, and a 403 during a live demo would sink the submission. Documenting the local fallback next to the Contree path is what made the project submittable.

## Suggestion

Publish a one-page "agent workload" recipe: Token Factory for the model calls, a VM or a long-running container for the sandbox, and a note that reasoning models may leave `content` empty when `max_tokens` is consumed by the trace. That would have saved us a day.
