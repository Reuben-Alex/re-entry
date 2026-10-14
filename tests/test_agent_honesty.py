"""Checks that do not need a funded chain or an API key."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from orchestrator.outcome import DRAIN_THRESHOLD_WEI, is_profitable
from orchestrator.proposer import GENERIC_EXPLOIT_PROMPT
from orchestrator.recon import _rank_flags

LEAKED_RECIPES = (
    "withdrawAll",
    "changeOwner",
    "flashFee",
    "setPrice",
    "tokensReceived",
    "deposit()",
    "release(address",
)


def test_generic_prompt_does_not_name_target_functions():
    for recipe in LEAKED_RECIPES:
        assert recipe not in GENERIC_EXPLOIT_PROMPT


def test_profit_oracle_counts_eth_token_and_invariant():
    assert is_profitable(DRAIN_THRESHOLD_WEI + 1)
    assert not is_profitable(DRAIN_THRESHOLD_WEI)
    assert is_profitable(0, token_gain=1)
    assert not is_profitable(-10**18, token_gain=5)
    assert is_profitable(-10**18, invariant_broken=True)


def test_hypotheses_are_ranked_by_confidence():
    ranked = _rank_flags(
        [
            {"function_name": "b", "confidence": 0.2},
            {"function_name": "a", "confidence": 0.9},
        ]
    )
    assert [flag["function_name"] for flag in ranked] == ["a", "b"]
    assert ranked[0]["rank"] == 1
