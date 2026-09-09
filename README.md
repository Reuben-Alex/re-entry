# PoCForge

An agent that proves smart-contract vulnerabilities exist by exploiting them
in a forked sandbox — not by reading code for known patterns. Built for the
Nebius x NVIDIA Global AI Hackathon, Coding & Agentic Engineering track.

Static analyzers and audits catch known bug *patterns*. They don't prove
exploitability, and they don't chain a bug into a working attack — the step
that separates a theoretical finding from a drained protocol. PoCForge forks
real chain state into a sandbox, proposes an exploit chain grounded in real
historical precedent (via Tavily), actually executes it, and — when it
fails — feeds the real on-chain error back into the next attempt. It only
reports a vulnerability once it has proven it by draining the funds itself,
with a fully reproducible transaction trace as evidence.

MIT licensed. See [LICENSE](./LICENSE).

---

## 1. What's built

| Piece | Status |
|---|---|
| `contracts/*.sol` | **Complete.** Reentrancy vault pair, access-control treasury pair, fallback attacker. |
| `orchestrator/chain.py` | **Complete.** Compile, deploy, localhost RPC guard, dynamic Solidity compile. |
| `orchestrator/sandbox.py` | **Complete.** LocalSandbox (Anvil snapshot/revert) + ContreeSandbox wrapper. |
| `orchestrator/recon.py` | **Complete.** ABI mapping + Nano risk flagging (regex fallback). |
| `orchestrator/precedent.py` | **Complete.** Tavily critical path — precedent + revert research. |
| `orchestrator/proposer.py` | **Complete.** Ultra generates Solidity exploit contracts + compile retry. |
| `orchestrator/executor.py` | **Complete.** Deploy + execute generated exploits + Attacker.sol fallback. |
| `orchestrator/loop.py` | **Complete.** Full propose → compile → execute → retry pipeline. |
| `orchestrator/report.py` | **Complete.** Super evidence reports with honest verdict distinction. |
| `scripts/run_pipeline.py` | **Complete.** Runs pipeline against all demo contracts. |
| `scripts/benchmark_pipeline.py` | **Complete.** Measures fallback rate + timing (run before demo). |
| `dashboard/app.py` | **Complete.** FastAPI + Jinja2 results dashboard. |

**Verdict values:** `vulnerable_agent_generated` | `vulnerable_fallback` | `no_exploit_found`

**Model split:** Nano (recon) → Ultra (exploit generation) → Super (report)

---

## 2. Setup

### Prerequisites
- Python 3.10+
- [Foundry](https://book.getfoundry.sh/getting-started/installation) (gives you the `anvil` local EVM node)
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
# fill in NEBIUS_API_KEY, TAVILY_API_KEY in .env
```

### First run — local development loop

```bash
# terminal 1
anvil

# terminal 2
python scripts/deploy_demo_contracts.py     # deploys + funds VulnerableVault and SafeVault
python scripts/manual_exploit_check.py      # confirms the bug is real, no LLM involved
```

If `manual_exploit_check.py` prints `CONFIRMED: exploit drains the vault`,
you're ready to start building the agent pipeline against a target you know
is genuinely exploitable.

---

## 3. Environment variables

All in `.env` — see `.env.example` for the full list with comments. The two
you must fill in before anything works: `NEBIUS_API_KEY`, `TAVILY_API_KEY`.
`CONTREE_API_TOKEN` / `CONTREE_PROJECT_ID` can stay blank until you move
from local Anvil to real Contree sandboxes (see `orchestrator/sandbox.py`).

Confirm the exact Nemotron model identifiers in `.env.example`
(`MODEL_NANO` / `MODEL_SUPER` / `MODEL_ULTRA`) against the current Nebius
Token Factory model catalog before running — these are placeholders and the
exact strings may differ.

---

## 4. The Solidity you need to understand (written for a Python-first reader)

You don't need to become a Solidity expert to finish this project — the
three contracts in `contracts/` are **already written and working**. This
section explains what they do and why, so you're not flying blind when you
build the agent that reasons about them.

### Why Solidity has to exist in this project at all

Everything else in this repo is Python. Solidity shows up in exactly two
places, both unavoidable:

1. **The target contracts** (`VulnerableVault.sol` / `SafeVault.sol`) —
   this is what your agent is trying to exploit. It has to be real,
   deployed bytecode on a real (forked/local) chain, because the whole
   point of the project is *proving* exploitability by execution, not by
   reading source and guessing.
2. **The attacker contract** (`Attacker.sol`) — this is the one piece that
   genuinely cannot be Python. Reentrancy exploits work by hijacking
   execution *in the middle of* another transaction, the instant ETH
   arrives at an address. Only a smart contract's `receive()` function can
   be triggered automatically like that by the EVM itself — Python code
   outside the chain has no way to insert itself mid-transaction.

Everything else — deploying these contracts, calling their functions,
checking balances before/after, deciding whether an attack worked — is
driven entirely from Python via `web3.py`. You are not expected to write
more Solidity than what's already here for the demo target; if you later
want to test the agent against different vulnerability types, that's where
you'd add more contracts, following the same pattern.

### `VulnerableVault.sol` — the bug, in plain terms

A "vault" that lets anyone deposit ETH and withdraw what they deposited.
The bug: when you withdraw, the contract **sends you the ETH before it
updates its own record of your balance**. If the withdrawer is a contract
(not a wallet), sending it ETH automatically triggers that contract's code
— and if that code calls `withdraw()` again *before* the first call
finishes, the vault still thinks you have your original balance, and pays
out again. Repeat until the vault is empty. This is the exact bug shape
behind the 2016 DAO hack and a large share of reentrancy exploits since.

### `SafeVault.sol` — the fix

Identical contract, one line moved: the balance is set to zero **before**
sending the ETH, not after. Now a repeat call sees a zero balance and stops
immediately. This is the standard "checks-effects-interactions" pattern —
check your conditions, update your own state, *then* talk to the outside
world. This is your agent's control case: it should try, fail, and
correctly conclude "no exploit found" against this contract.

### `Attacker.sol` — the exploit

A small contract that: (1) deposits into the vault, (2) calls `withdraw()`
to start the exploit, and (3) has a `receive()` function that automatically
fires when ETH arrives — which calls `withdraw()` again, exploiting the bug
above, as many times as the vault's remaining balance allows.

### What you do NOT need to write yourself

For the hackathon's core demo, all three contracts above are done. You
won't need to write new Solidity unless you choose to extend the project to
new vulnerability types (oracle manipulation, access control bugs, etc.) as
a stretch goal — if you do, follow the same "vulnerable / patched / (if
needed) attacker" pattern established here.

### Compiling and deploying — already handled

You don't hand-compile anything. `orchestrator/chain.py`'s
`compile_contract()` calls `py-solc-x` to turn a `.sol` file into an ABI +
bytecode pair, and `deploy()` sends that to whatever RPC endpoint you point
it at (local Anvil, or later, a Contree sandbox running Anvil). See
`scripts/deploy_demo_contracts.py` for a complete working example.

---

## 5. Architecture recap

```
recon (Nano) -> risk ranking (Nano) -> precedent search (Tavily)
   -> exploit proposal (Ultra) -> sandbox execution (Contree/Anvil)
   -> outcome check -> [fail: retry via Tavily + Ultra, bounded attempts]
   -> [success: evidence report (Super)] -> dashboard (Serverless Endpoint)
```

Full architecture rationale, judging-criteria mapping, and demo script are
in the project plan doc (kept alongside this repo / shared with the team
separately) — this README is the "how do I actually build it" companion to
that doc.

---

## 6. Moving from local Anvil to Nebius Sandboxes (Contree)

Develop and debug everything against plain local `anvil` first — it's
faster to iterate on and has no external dependencies. Once the full
pipeline works end-to-end locally:

1. Read `/mnt/skills` — n/a here; instead see the Contree SDK examples at
   https://github.com/nebius/contree-sdk (the `examples/` directory covers
   session management, image operations, and branching workflows
   specifically).
2. Build an OCI base image with Anvil + this repo's Python deps
   pre-installed.
3. Implement `ContreeSandbox` in `orchestrator/sandbox.py` against the same
   interface `LocalSandbox` already exposes (`fork_checkpoint`,
   `run_tx_sequence`, `rollback`) — the checkpoint/branch model maps
   directly onto that retry loop: fork before each attempt, roll back
   instantly on failure instead of re-deploying.
4. Keep `LocalSandbox` as a fallback path. Sandboxes/Contree is currently
   in **Beta** — don't let it be a single point of failure minutes before a
   demo.

---

## 7. Submission checklist (Devpost)

- [ ] Working project using ≥1 NVIDIA open source model on Token Factory ✅ (Nemotron Nano/Ultra/Super)
- [ ] Category: Coding & Agentic Engineering
- [ ] Project description (what/why/how)
- [ ] Working demo URL — `dashboard/app.py` deployed as a Nebius Serverless Endpoint
- [ ] Demo video, ≤3 min, public YouTube, **audio must explicitly name how Token Factory and Nemotron were used** at the relevant moments
- [ ] Public repo with OSS license visible at the top (this repo ships with MIT — see `LICENSE`)
- [ ] README with setup instructions (this file) — highlight Nemotron/Token Factory/Contree/Tavily usage (done above)
- [ ] Feedback on Token Factory / AI Cloud / NVIDIA tools — jot friction points as you hit them during the build, don't leave this to the last minute
- [ ] Consider Tavily-specific writeup for the separate Best Use of Tavily prize
