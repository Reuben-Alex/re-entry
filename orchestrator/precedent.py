"""
Tavily-grounded exploit precedent search — critical path dependency.
"""
from orchestrator import config
from orchestrator.exceptions import ConfigurationError

_client = None


def _get_client():
    global _client
    if _client is None:
        if not config.TAVILY_API_KEY:
            raise ConfigurationError(
                "TAVILY_API_KEY required — Tavily is a critical path dependency"
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
