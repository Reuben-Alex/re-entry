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
- Three Nemotron tiers on Token Factory with distinct roles (Nano recon / Ultra exploit+patch / Super report).
- Compile-retry loop; revert-reason → Tavily research → revised proposal.
- Honest verdicts: `vulnerable_agent_generated` vs labeled ABI `vulnerable_fallback` vs `no_exploit_found`.
- Benchmarked: Ultra agent-generated success **3/3** on VulnerableVault and VulnerableTreasury with **0 fallbacks**.

### Design
- Live dashboard Story / Decision log / Solution / Exploit / Research tabs.
- One-command `scripts/demo.sh`; Docker deploy under `deploy/`.
- 15–25s `/brag` launch clip + ≤3 min submission walkthrough.

### Potential Impact
- Template for agentic “prove then patch” tooling that auditors and protocol teams could run in CI sandboxes.
- Comparable coverage scores on attributed benchmark tier; blind claims reserved for authored held-out (e.g. VulnerableBlind).

### Quality of the Idea
- Proof-by-execution, not lint rules.
- Patch verify closes the loop against the **same** winning exploit.
- Hybrid corpus: authored honesty anchor + attributed benchmarks + OpenZeppelin canonical fix patterns + OWASP SC Top 10 labels.

## Built with
Nebius Token Factory · NVIDIA Nemotron 3 · Tavily · Foundry/Anvil · web3.py · FastAPI · (optional) Nebius Sandboxes / Contree

## Links
- Public repo (MIT)
- Demo URL (dashboard)
- YouTube ≤3 min (audio names Token Factory + Nemotron at each step)
- Best Use of Tavily writeup: [docs/TAVILY.md](TAVILY.md)
