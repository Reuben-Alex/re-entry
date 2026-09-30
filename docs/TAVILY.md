# Best Use of Tavily — Re-entry

Tavily is on the **critical path**, not a decorative citation dump.

## Where it runs

1. **Precedent search** (`orchestrator/precedent.py` → `find_precedent`)  
   After Nano flags a risk pattern (e.g. `reentrancy`, `access_control`), Tavily
   searches for DeFi exploit postmortems. Results are injected into Ultra’s
   exploit-proposal prompt so the generated Solidity is grounded in real
   historical strategy, not only static source pattern matching.

2. **Revert-error research** (`find_fix_for_error`)  
   When an agent-generated exploit reverts on-chain, the cleaned revert reason
   is sent to Tavily. Those snippets feed the **next** Ultra attempt — closing
   the plan → write → test → iterate loop judges want in Coding & Agentic
   Engineering.

## Why this is a strong Tavily use

- Search queries are **tied to live agent state** (risk pattern, then concrete
  revert strings), not a one-shot “search for smart contract security” call.
- Results appear in the dashboard Research tab and in Super’s evidence report
  (`precedent_citation`), so judges can see the grounding.
- Measured runs already return real sources (OWASP SC05, Nethermind, Pessimistic,
  etc.) in `results/latest_run.json`.

## Demo one-liner

“Tavily doesn’t decorate the README — it shapes the exploit Ultra writes, and
it shapes the retry after Anvil tells us why the last attempt failed.”
