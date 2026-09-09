"""
Outcome check — did the proposed sequence actually drain funds?

STATUS: complete / simple. This is deliberately just arithmetic — no
LLM call needed here, the loop only needs a clean before/after
balance diff to decide success or failure.
"""

# Minimum meaningful drain, in wei, to count as a real success rather
# than dust / rounding noise. 0.01 ether — tune as needed.
DRAIN_THRESHOLD_WEI = 10**16


def is_drained(vault_balance_before: int, vault_balance_after: int) -> bool:
    return (vault_balance_before - vault_balance_after) > DRAIN_THRESHOLD_WEI


def summarize(vault_before: int, vault_after: int, attacker_before: int, attacker_after: int) -> dict:
    drained_amount = vault_before - vault_after
    return {
        "drained": is_drained(vault_before, vault_after),
        "vault_drained_wei": drained_amount,
        "attacker_gain_wei": attacker_after - attacker_before,
    }
