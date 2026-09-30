"""
Tavily-grounded exploit precedent search — critical path dependency.
"""
from orchestrator import config
from orchestrator.exceptions import ConfigurationError

_client = None


def _demo_precedent_stub(risk_pattern: str) -> list[dict]:
    """Stub precedent for local demo when Tavily key is not configured."""
    return [
        {
            "title": "The DAO hack reentrancy postmortem (demo stub)",
            "url": "https://ethereum.org/en/developers/docs/smart-contracts/security/",
            "content": (
                f"Classic reentrancy pattern for {risk_pattern}: external call "
                "before state update allows recursive withdrawal via receive()."
            ),
        }
    ]


def _get_client():
    global _client
    if _client is None:
        if not config.TAVILY_API_KEY:
            if config.DEMO_SKIP_TAVILY:
                return None
            raise ConfigurationError(
                "TAVILY_API_KEY required — Tavily is a critical path dependency "
                "(or set DEMO_SKIP_TAVILY=true for local demo only)"
            )
        from tavily import TavilyClient

        _client = TavilyClient(api_key=config.TAVILY_API_KEY)
    return _client


def _format_results(results: list[dict]) -> list[dict]:
    """Normalize Tavily result shape."""
    formatted = []
    for item in results:
        formatted.append(
            {
                "title": item.get("title", ""),
                "url": item.get("url", ""),
                "content": item.get("content", ""),
            }
        )
    return formatted


def find_precedent(risk_pattern: str, max_results: int = 5) -> list[dict]:
    """
    Search for real historical exploits matching a flagged risk pattern.
    Returns a list of {title, url, content} dicts.
    """
    client = _get_client()
    if client is None:
        return _demo_precedent_stub(risk_pattern)
    try:
        results = client.search(
            query=(
                f"DeFi smart contract exploit postmortem {risk_pattern} "
                "attack writeup"
            ),
            max_results=max_results,
            search_depth="advanced",
        )
        return _format_results(results.get("results", []))
    except Exception:
        return []


def find_fix_for_error(revert_reason: str, max_results: int = 3) -> list[dict]:
    """
    Search using a specific on-chain revert reason from a failed attempt.
    """
    client = _get_client()
    if client is None:
        return [
            {
                "title": f"Revert '{revert_reason}' — demo stub",
                "url": "https://docs.soliditylang.org/",
                "content": "Check require conditions and reentrancy guards.",
            }
        ]
    try:
        results = client.search(
            query=(
                f"Solidity revert error '{revert_reason}' fix workaround"
            ),
            max_results=max_results,
            search_depth="basic",
        )
        return _format_results(results.get("results", []))
    except Exception:
        return []
