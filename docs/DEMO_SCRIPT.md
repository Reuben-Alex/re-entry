# Submission demo script (≤3 minutes)

Record this with screen capture + live narration. **Audio must explicitly name
Nebius Token Factory and Nemotron Nano / Ultra / Super** at the moments below.

## Setup before record

```bash
anvil
source .venv/bin/activate
python scripts/deploy_demo_contracts.py
uvicorn dashboard.app:app --port 8000
```

Open http://127.0.0.1:8000 (or your public demo URL).

## Shot list (~170s)

| Time | Visual | Say this |
|------|--------|----------|
| 0:00–0:15 | README / logo | “This is Re-entry — an agent that proves smart-contract bugs by exploiting them in a sandbox, then patching and verifying the fix. Everything runs on a local Anvil EVM — never a public chain.” |
| 0:15–0:35 | Dashboard Challenges | “On Nebius Token Factory we use three NVIDIA Nemotron models: Nano for recon, Ultra for exploit and patch generation, and Super for the evidence report.” |
| 0:35–1:10 | Run VulnerableVault live | “Nano flags reentrancy. Tavily pulls historical DAO-style precedent. Ultra writes a fresh Solidity exploit — not our hand-written Attacker.sol — and Anvil executes it. Watch the vault drain.” |
| 1:10–1:35 | Story + Solution tabs | “Verdict is vulnerable_agent_generated — agent-generated, no fallback. Ultra then emits a minimal patch aligned with OpenZeppelin checks-effects-interactions. We redeploy and replay the same exploit; it fails. Find, prove, fix, verify.” |
| 1:35–2:10 | Held-out VulnerableBlind | “Blind held-out target: missing access control on changeOwner. Our ABI safety-net fallback will not chain privilege escalation — Ultra has to write the multi-step exploit itself.” |
| 2:10–2:35 | SafeVault control | “Control case SafeVault — correctly reports no_exploit_found. The agent isn’t just pattern-matching function names.” |
| 2:35–2:55 | Benchmark note / Decision log | “Attributed Ethernaut- and Damn-Vulnerable-DeFi-inspired benchmarks measure coverage; authored held-out contracts measure blind reasoning. Decision log shows Nano → Tavily → Ultra → execute → patch.” |
| 2:55–3:00 | End card | “Re-entry — prove the bug, prove the fix, on Token Factory with Nemotron.” |

## Checklist

- [ ] Public YouTube unlisted/public link
- [ ] Audio says **Token Factory** and **Nemotron Nano/Ultra/Super** by name
- [ ] Show agent-generated verdict (not only fallback)
- [ ] Show patch verified
- [ ] Mention sandbox / educational scope once
