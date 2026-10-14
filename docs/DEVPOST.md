# Devpost — Re-entry

**Track:** Coding & Agentic Engineering  
**Stack:** NVIDIA Nemotron Nano / Super / Ultra on Nebius Token Factory · Tavily · Anvil / Nebius Sandboxes · FastAPI dashboard

## Elevator pitch

Static analyzers guess. Audits pattern-match. **Re-entry proves** a smart-contract bug by having an agent **write a fresh exploit contract, execute it in a local sandbox, then generate a minimal patch and prove the same exploit no longer works.** Lifecycle: find → prove → fix → verify.

## What / why / how

**What.** An agentic security demo that maps ABI + source (Nemotron Nano), grounds strategy in historical exploit writeups (Tavily), generates Solidity exploits (Nemotron Ultra), executes them on Anvil (or Contree), retries on real revert reasons, and closes with Super-written evidence plus OpenZeppelin-aligned patches.

**Why.** The gap between “looks like reentrancy” and “here is the transaction that drained 3 ETH, and here is the fix that blocks it” is exactly where agentic engineering earns its keep — and where Coding & Agentic Engineering judges look for plan → write → test → iterate loops.

**How (demo path).** Local Anvil only — never mainnet. All targets are authored educational contracts or attributed MIT teaching miniatures (Ethernaut / Damn Vulnerable DeFi–inspired). Localhost RPC guard refuses remote endpoints unless explicitly overridden.

## Judging criteria mapping

### Technological Implementation
- Three Nemotron tiers on Token Factory with distinct roles (Nano ranked hypotheses / Ultra exploit+patch / Super report).
- One generic Ultra prompt: source, ABI, hypotheses, Tavily, and the prior revert plus Anvil call trace. It does not name target functions.
- Honest verdicts: `vulnerable_agent_generated` vs labeled ABI `vulnerable_fallback` vs `no_exploit_found`. Fallback is excluded from the agent-success rate.
- One recorded pass (`python scripts/benchmark_pipeline.py 1`): **agent-generated 5/13** non-control runs, **fallback 2** (VulnerableVault, VulnerableEscrow), **other 6**. Controls: **13/13** `no_exploit_found`.
- Agent wins in that pass: VulnerableTreasury, VulnerableBlind, HookVault, plus attributed FallbackBank and NaiveFeeVault. Published misses: cross-function reentrancy, share inflation, uninitialized proxy, signature replay, flash-loan spot price, and the oracle vault. Hand-written exploits in `tests/test_new_targets.py` still prove those bugs.
- A patch is verified only when the replay no longer profits and a benign deposit/withdraw still succeeds.
- Scoreboard: `results/benchmark.json`. Headline: agent-generated 5/13 on non-control runs; fallback 2; other 6. Controls are scored separately and were clean.

### Design
- Live dashboard Story / Decision log / Solution / Exploit / Research tabs.
- "Run my contract" pastes Solidity onto the local sandbox and streams the same loop.
- One-command `scripts/demo.sh`; Docker deploy under `deploy/`.
- 15–25s `/brag` launch clip + ≤3 min submission walkthrough.

### Potential Impact
- Auditors and protocol teams can point the same loop at a contract they paste in, inside a sandbox, before anything is deployed.
- Comparable coverage scores on the attributed benchmark tier. Blind claims are reserved for the authored held-out set (cross-function reentrancy, token hook, share inflation, uninitialized proxy, signature replay, flash-loan spot price).

### Quality of the Idea
- Proof-by-execution, not lint rules.
- Patch verify closes the loop against the **same** winning exploit.
- Hybrid corpus: authored honesty anchor + attributed benchmarks + OpenZeppelin canonical fix patterns + OWASP SC Top 10 labels.

## Built with
Nebius Token Factory · NVIDIA Nemotron 3 · Tavily · Foundry/Anvil · web3.py · FastAPI · (optional) Nebius Sandboxes / Contree

## Links
- Public repo (MIT): https://github.com/Reuben-Alex-66/re-entry
- Demo URL: run `deploy/Dockerfile` on a Nebius VM (see [deploy/README.md](../deploy/README.md)); local dashboard is http://127.0.0.1:8000
- YouTube ≤3 min: record from [docs/DEMO_SCRIPT.md](DEMO_SCRIPT.md); audio names Token Factory + Nemotron at each step
- Best Use of Tavily writeup: [docs/TAVILY.md](TAVILY.md)
- Token Factory feedback: [docs/FEEDBACK.md](FEEDBACK.md)
