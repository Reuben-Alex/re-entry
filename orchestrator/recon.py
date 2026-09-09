"""
Recon + attack-surface ranking — Nemotron Nano.
"""
import json
import re
import time

from openai import OpenAI

from orchestrator import config

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.NEBIUS_API_KEY:
            raise ValueError("NEBIUS_API_KEY is required for recon")
        _client = OpenAI(
            api_key=config.NEBIUS_API_KEY,
            base_url=config.NEBIUS_BASE_URL,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    return _client


def map_functions(abi: list) -> list[dict]:
    """Extract function signatures + mutability from the ABI."""
    summaries = []
    for entry in abi:
        if entry.get("type") != "function":
            continue
        mutability = entry.get("stateMutability", "nonpayable")
        inputs = [
            {"name": i.get("name", ""), "type": i.get("type", "")}
            for i in entry.get("inputs", [])
        ]
        outputs = [
            {"name": o.get("name", ""), "type": o.get("type", "")}
            for o in entry.get("outputs", [])
        ]
        summaries.append(
            {
                "name": entry.get("name", ""),
                "inputs": inputs,
                "outputs": outputs,
                "stateMutability": mutability,
                "state_changing": mutability in ("nonpayable", "payable"),
                "payable": mutability == "payable",
            }
        )
    return summaries


def _heuristic_risk_flags(source_code: str) -> list[dict]:
    """Regex fallback when Nano is unavailable."""
    flags = []
    if re.search(r"\.call\{value:", source_code):
        if re.search(r"balances\[.*\]\s*=\s*0", source_code):
            flags.append(
                {
                    "function_name": "withdraw",
                    "risk_pattern": "reentrancy",
                    "confidence": 0.5,
                    "reasoning": (
                        "Heuristic: external call before balance zeroing detected"
                    ),
                }
            )
    if re.search(r"function\s+withdrawAll\s*\(", source_code):
        if "onlyOwner" not in source_code and "msg.sender == owner" not in source_code:
            flags.append(
                {
                    "function_name": "withdrawAll",
                    "risk_pattern": "access_control",
                    "confidence": 0.6,
                    "reasoning": (
                        "Heuristic: withdrawAll without owner check"
                    ),
                }
            )
    return flags


def flag_risk_patterns(
    function_summaries: list[dict],
    source_code: str,
) -> tuple[list[dict], dict]:
    """
    Call Nano to flag risk patterns. Returns (flags, timing_info).
    """
    timing = {"step": "recon", "duration_s": 0.0, "model": config.MODEL_NANO}
    start = time.time()

    if not config.MODEL_NANO or not config.NEBIUS_API_KEY:
        timing["duration_s"] = time.time() - start
        timing["fallback"] = True
        return _heuristic_risk_flags(source_code), timing

    prompt = f"""Analyze this Solidity contract and flag vulnerability patterns.

FUNCTION SUMMARIES:
{json.dumps(function_summaries, indent=2)}

SOURCE CODE:
{source_code}

Return JSON: {{"risk_flags": [{{"function_name": "...", "risk_pattern": "reentrancy|access_control|oracle_manipulation|...", "confidence": 0.0-1.0, "reasoning": "..."}}]}}
"""
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=config.MODEL_NANO,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a smart contract security auditor. "
                        "Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        content = response.choices[0].message.content or "{}"
        parsed = json.loads(content)
        flags = parsed.get("risk_flags", parsed if isinstance(parsed, list) else [])
        if not isinstance(flags, list):
            flags = []
        timing["duration_s"] = time.time() - start
        return flags, timing
    except Exception:
        timing["duration_s"] = time.time() - start
        timing["fallback"] = True
        return _heuristic_risk_flags(source_code), timing
