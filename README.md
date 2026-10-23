# Re-entry

**An agent that proves smart-contract vulnerabilities by exploiting them in a
sandbox — then writes the fix and proves *that* works too.**

Built for the Nebius x NVIDIA Global AI Hackathon, Coding & Agentic
Engineering track. Powered by NVIDIA Nemotron (Nano / Super / Ultra) on
Nebius Token Factory, with Tavily for exploit-precedent grounding.

Static analyzers and audits catch known bug *patterns*. They don't prove
exploitability, and they don't chain a bug into a working attack — the step
that separates a theoretical finding from a drained contract. Re-entry
compiles a target into a local EVM sandbox, has an LLM **write a fresh
exploit contract from scratch**, actually executes it, and — when it fails —
feeds the real on-chain revert reason back into the next attempt. It only
reports a vulnerability once it has proven it by draining the funds itself,
with a reproducible transaction trace as evidence. Then it generates a
minimal patch, redeploys, and replays the same exploit to confirm the fix
holds.

**Lifecycle: find → prove → fix → verify.**

The exploit prompt is one generic brief. It receives the source, the ABI, Nano's ranked hypotheses, Tavily notes, and the previous revert plus an Anvil call trace. It does not name the target's functions. A run counts as success when the attacker gains ETH or a tracked token, or the target's ETH balance falls. A patch is verified only when that same exploit no longer profits and a normal deposit and withdraw still work.

MIT licensed. See [LICENSE](./LICENSE).

---

## Scope and ethics (read first)

This is a **self-contained, educational** smart-contract security demo.

- Every contract — the vulnerable target, its patched twin, and the exploit
  contract — is either **authored by us** or a **permissively-licensed public
  teaching benchmark** (attributed below). Nothing here is a real, deployed,
  value-holding protocol.
- Everything runs only on a **local/sandboxed EVM** (Anvil, or a Nebius
  Sandboxes / Contree fork). There is a hard localhost guard on the RPC
  connection ([`orchestrator/chain.py`](orchestrator/chain.py) `get_web3`).
- There is **no interaction with any real chain, real funds, real user, or
  third-party infrastructure**. Nothing here can reach mainnet or a public
  testnet.
- The purpose is demonstrating well-known, widely-taught vulnerability
  classes (reentrancy — the 2016 DAO pattern — access control, escrow logic)
  as a proof-of-concept for agentic security tooling, not building attack
  capability against real systems.

Terms like "attacker," "exploit," and "drain" refer only to our own toy
contracts (and clearly-attributed teaching benchmarks) in an isolated
sandbox.

---

## 1. Status — scoreboard is the JSON

The pipeline runs against real Nemotron models on Nebius Token Factory. The numbers judges should trust are in [`results/benchmark.json`](results/benchmark.json), from one pass of:

```bash
python scripts/benchmark_pipeline.py 1
```

Headline: **agent-generated 5/13** on non-control runs, **fallback 2**, **other 6**. Fallback wins are not agent successes. All **13/13** control contracts were `no_exploit_found`.

An attempt counts only when the attacker nets ETH or a tracked token (or a declared invariant breaks). A vault balance drop from an honest withdraw or borrow does not count. The hand-written ABI fallback is scored on its own and does not chain privilege escalation, cross-function reentrancy, signature replay, or the flash-loan spot manipulation.

| Target | Outcome |
|---|---|
| VulnerableTreasury, VulnerableBlind, HookVault | agent |
| FallbackBank, NaiveFeeVault (attributed) | agent |
| VulnerableVault, VulnerableEscrow | labeled ABI fallback |
| VulnerableOracleVault, CrossFunctionVault, InflatingVault, OpenProxy, ReplayVault, SpotLending | no exploit this run |

The misses are published on purpose. `tests/test_new_targets.py` still shows a hand-written exploit for the cross-function, hook, inflation, proxy, replay, and spot-lending bugs. The agent found the hook and missed the others in this single pass.

**Model split:** Nano (ranked hypotheses) → Ultra (exploit + patch, generic prompt) → Super (evidence report)

| Piece | What it does |
|---|---|
| `contracts/*.sol` | Vulnerable/patched pairs + exploit contracts (reentrancy, access control, escrow logic). |
| `orchestrator/recon.py` | ABI mapping + Nano risk flagging (regex fallback). |
| `orchestrator/precedent.py` | Tavily precedent + revert-error research. |
| `orchestrator/proposer.py` | Ultra writes Solidity exploits from scratch, with compile-retry. |
| `orchestrator/executor.py` | Deploys + runs generated exploits; hand-written fallback as safety net. |
| `orchestrator/loop.py` | Full propose → compile → execute → retry → fallback pipeline. |
| `orchestrator/patcher.py` | Ultra generates a minimal patch + unified diff. |
| `orchestrator/patch_verify.py` | Redeploys the patch, replays the exploit, and requires a benign deposit/withdraw to still succeed. |
| `orchestrator/report.py` | Super evidence report with lifecycle story. |
| `orchestrator/sandbox.py` / `contree_sandbox.py` | LocalSandbox (Anvil snapshot/revert) + Contree wrapper. |
| `dashboard/app.py` | FastAPI + Jinja2 live results dashboard. |
| `scripts/benchmark_pipeline.py` | Measures agent success rate + timing (run before demo). |

---

## 2. How it works

```
recon (Nano) → risk ranking → precedent search (Tavily)
   → exploit proposal (Ultra) → sandbox execution (Anvil/Contree)
   → outcome check → [fail: retry with real revert reason + Tavily, bounded]
   → [success: patch (Ultra) → redeploy → replay blocked and benign use still works]
   → evidence report (Super) → dashboard
```

Why one piece *must* be Solidity: reentrancy hijacks execution mid-transaction
the instant ETH arrives, via a contract's `receive()`. Off-chain Python
cannot inject itself into an in-flight transaction — only another contract
can. Everything else (deploy, call, read balances, decide success) is Python
via `web3.py`.

One-command local demo:

```bash
bash scripts/demo.sh
```

---

## 3. The vulnerability corpus (hybrid)

Re-entry runs against a tiered corpus so judges can see both honesty and
breadth:

- **Authored targets (the honesty anchor).** Our own vulnerable/patched
  pairs, including a freshly-written **held-out** contract the model has never
  seen — this is what proves the agent reasons rather than pattern-matches a
  memorized answer.
- **Attributed public benchmarks (breadth).** A slice of permissively-licensed
  teaching sets — [Ethernaut](https://github.com/OpenZeppelin/ethernaut)
  (MIT), [Damn Vulnerable DeFi](https://github.com/theredguild/damn-vulnerable-defi)
  (MIT), [SmartBugs-Curated](https://github.com/smartbugs/smartbugs-curated),
  and [EVMbench](https://www.arxiv.org/pdf/2603.04915) — used to report a
  comparable, quantitative score. (Note: classic sets like Ethernaut/DVD are
  likely in the model's training data, so they measure coverage, not blind
  reasoning; the authored held-out contract is what does that.)
- **Canonical safe templates (the patch target).** Correct patches should
  converge toward the audited
  [OpenZeppelin Contracts](https://github.com/OpenZeppelin/openzeppelin-contracts)
  patterns — `ReentrancyGuard`/`nonReentrant`, `Ownable`/`AccessControl`,
  `SafeERC20`, `PullPayment`. The report highlights when the generated fix
  matches the OpenZeppelin-audited pattern.
- **Taxonomy.** Findings are labeled against the current
  [OWASP Smart Contract Top 10 (2025)](https://owasp.org/www-project-smart-contract-top-10/)
  and DASP Top 10. (The older SWC Registry is frozen — not updated since 2020
  — so it's cited only as historical reference.)

Challenge tiers ([`challenges/manifest.json`](challenges/manifest.json)):

| Tier | Examples | In repo |
|------|----------|---------|
| `train` | VulnerableVault | Full source in `contracts/` |
| `held_out_sealed` | VulnerableTreasury, VulnerableEscrow, CrossFunctionVault, HookVault, InflatingVault, OpenProxy, ReplayVault, SpotLending | Comment-free `challenges/sealed/` |
| `held_out_live` | Fresh blind contract | `.sol` in `challenges/held_out/` (gitignored until demo) |
| `control` | SafeVault and the safe twin of every held-out target | Negative tests — this run reported `no_exploit_found` on all 13 |

---

## 4. Setup

### Prerequisites
- Python 3.10+
- [Foundry](https://book.getfoundry.sh/getting-started/installation) (provides `anvil`)
- A Nebius Token Factory API key
- A Tavily API key

### Install

```bash
curl -L https://foundry.paradigm.xyz | bash
foundryup

python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env
# fill in NEBIUS_API_KEY and TAVILY_API_KEY in .env
```

### Environment variables

All in `.env` — see [`.env.example`](.env.example) for the full annotated
list. The two you must set: `NEBIUS_API_KEY`, `TAVILY_API_KEY`.
`CONTREE_API_TOKEN` / `CONTREE_PROJECT_ID` can stay blank until you move from
local Anvil to Contree sandboxes.

Nemotron model IDs (verified against the
[Nebius model catalog](https://tokenfactory.nebius.com/model-catalog.md) —
IDs are case-sensitive, use **Copy model ID** in the console):

| Role | Model | `MODEL_*` value | Region |
|------|-------|-----------------|--------|
| Recon (Nano) | Nemotron-3-Nano-30B-A3B | `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B` | eu-north1 |
| Report (Super) | Nemotron-3-Super-120B-A12B | `nvidia/nemotron-3-super-120b-a12b` | us-central1 |
| Exploit + patch (Ultra) | Nemotron-3-Ultra-550B-A55B | `nvidia/Nemotron-3-Ultra-550b-a55b` | us-central1 |

> Never commit `.env`. It is gitignored. If a key is ever exposed, rotate it
> in the Nebius / Tavily consoles.

---

## 5. Running it

```bash
# terminal 1
anvil

# terminal 2 — use the project venv (system python3 lacks solcx)
source .venv/bin/activate
pip install -r requirements.txt             # once

python scripts/deploy_demo_contracts.py     # deploys + funds demo contracts
python scripts/manual_exploit_check.py      # confirms reentrancy bug, no LLM
python scripts/run_pipeline.py              # full agent pipeline (needs API keys)
python scripts/benchmark_pipeline.py 25     # measure agent success rate before demo

# dashboard (demo URL)
uvicorn dashboard.app:app --reload --port 8000
```

If `manual_exploit_check.py` prints `CONFIRMED: exploit drains the vault`, the
sandbox target is verified. Run `benchmark_pipeline.py` before submitting and
state the result: "Ultra succeeds without fallback in N/M runs."

Run by tier:

```bash
python scripts/run_pipeline.py --tier train
python scripts/run_pipeline.py --tier held_out_sealed
python scripts/run_pipeline.py --tiers train,held_out_sealed

# blind run, source not printed
bash scripts/held_out_demo.sh
TIER=held_out_live bash scripts/held_out_demo.sh
```

**Recommended judge flow:**
1. **VulnerableVault** (`train`) — reentrancy, full lifecycle in the dashboard **Story** tab.
2. **Held-out suite** — sealed targets, including cross-function reentrancy, a token hook, share inflation, an uninitialized proxy, signature replay, and a flash-loan spot-price pool. Source is not the recipe; the prompt does not name their functions.
3. **Paste a contract** — the "Run my contract" box compiles your Solidity onto the local Anvil and runs the same loop.
4. **SafeVault** (`control`) — should report `no_exploit_found`.

---

## 6. Nebius Sandboxes (Contree) — optional cloud isolation

Re-entry supports cloud-isolated EVM execution via **Nebius Sandboxes**
(Contree). Set `SANDBOX_MODE=contree` in `.env` once credentials are set.

- **Token:** your `NEBIUS_API_KEY` (or request early access at
  [contree.dev](https://contree.dev) — Sandboxes is in beta).
- **Project ID:** Nebius console → your project → **Project ID**.
- **Verify:** `python scripts/contree_check.py`.

[`orchestrator/contree_sandbox.py`](orchestrator/contree_sandbox.py)
bootstraps an Ubuntu container with Foundry + Anvil, uploads the repo, deploys
demo contracts, and uses Contree's Git-like branching for retry rollback.
First bootstrap is slow (~5-10 min); later runs reuse the `re-entry-bootstrap`
image.

> Contree is in **beta** and can return 403 without Sandboxes access. 

Docs: [Sandboxes overview](https://docs.tokenfactory.nebius.com/sandboxes/overview.md)
| [Contree branching](https://docs.tokenfactory.nebius.com/sandboxes/sdk/python_sdk/branching.md)

---