# Third-party benchmark attribution

Re-entry’s **authored** contracts live under `contracts/` and `challenges/`.
The `benchmarks/` tree holds **original educational miniatures** inspired by
well-known teaching challenges. They are **not** verbatim copies of production
protocol code and are **not** used against live chains.

| Contract | Inspiration | Upstream license | Notes |
|----------|-------------|------------------|-------|
| `FallbackBank.sol` | [OpenZeppelin Ethernaut — Fallback](https://github.com/OpenZeppelin/ethernaut) | MIT | Ownership-via-receive pattern, rewritten for Anvil demo |
| `NaiveFeeVault.sol` | [Damn Vulnerable DeFi — Naive receiver](https://github.com/theredguild/damn-vulnerable-defi) | MIT | Permissionless fee pull, rewritten for Anvil demo |

Canonical **safe** patch targets follow [OpenZeppelin Contracts](https://github.com/OpenZeppelin/openzeppelin-contracts) conventions (`Ownable`, `ReentrancyGuard` / checks-effects-interactions, `AccessControl`). Re-entry inlines equivalent minimal patterns rather than importing the full OZ package in generated patches.

Findings are labeled against the [OWASP Smart Contract Top 10 (2025)](https://owasp.org/www-project-smart-contract-top-10/) where applicable (e.g. SC01 access control, SC05 reentrancy).

**Honest evaluation note:** classic Ethernaut / DVD patterns are widely published and may appear in LLM training data. Treat `benchmark` tier results as **coverage** metrics. Use authored `held_out_sealed` targets (especially `VulnerableBlind`) for blind-reasoning claims.
