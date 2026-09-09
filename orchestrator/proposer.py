"""
Exploit contract generation — Nemotron Ultra writes Solidity from scratch.
"""
import json
import time
from dataclasses import dataclass, field

from openai import OpenAI

from orchestrator import chain, config
from orchestrator.exceptions import CompilationFailed

_client = None

SYSTEM_PROMPT = """You are a smart contract security researcher. Your task is to write a
Solidity exploit contract that demonstrates a vulnerability in a target
contract deployed on a local test chain.

CONSTRAINTS:
- Copy this line verbatim as the first line of your contract:
  pragma solidity ^0.8.19;
- Your contract MUST have: constructor(address target) and a payable
  function named attack() that initiates the exploit.
- You may include receive() or fallback() if needed for callbacks.
- The exploit runs in an Anvil sandbox with unlimited gas and ETH.
- Do NOT import external libraries. Use only inline interface definitions.
- Return your response as JSON with these exact keys:
  {
    "solidity_source": "<complete .sol file as a string>",
    "contract_name": "<name of your exploit contract>",
    "entry_function": "attack",
    "entry_value_wei": <integer, wei to send with attack() call>,
    "reasoning": "<1-2 sentences explaining the vulnerability and strategy>"
  }
"""


@dataclass
class ExploitProposal:
    solidity_source: str
    contract_name: str
    entry_function: str
    entry_value_wei: int
    reasoning: str
    abi: list = field(default_factory=list)
    bytecode: str = ""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.NEBIUS_API_KEY:
            raise ValueError("NEBIUS_API_KEY is required for proposer")
        _client = OpenAI(
            api_key=config.NEBIUS_API_KEY,
            base_url=config.NEBIUS_BASE_URL,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    return _client


def _format_precedent(precedent_results: list[dict]) -> str:
    if not precedent_results:
        return "No Tavily results returned (search ran but empty)."
    lines = []
    for item in precedent_results:
        lines.append(
            f"- {item.get('title', 'Unknown')}: {item.get('url', '')}\n"
            f"  {item.get('content', '')[:500]}"
        )
    return "\n".join(lines)


def _call_ultra(messages: list[dict]) -> tuple[ExploitProposal, str, float]:
    """Call Ultra and parse JSON response. Returns proposal, raw, duration."""
    start = time.time()
    client = _get_client()
    response = client.chat.completions.create(
        model=config.MODEL_ULTRA,
        messages=messages,
        response_format={"type": "json_object"},
    )
    duration = time.time() - start
    raw = response.choices[0].message.content or "{}"
    parsed = json.loads(raw)
    proposal = ExploitProposal(
        solidity_source=parsed["solidity_source"],
        contract_name=parsed["contract_name"],
        entry_function=parsed.get("entry_function", "attack"),
        entry_value_wei=int(parsed.get("entry_value_wei", 10**18)),
        reasoning=parsed.get("reasoning", ""),
    )
    return proposal, raw, duration


def propose_exploit(
    source_code: str,
    risk_flags: list[dict],
    precedent_results: list[dict],
    prior_failure: dict | None = None,
) -> tuple[ExploitProposal, dict]:
    """
    Generate and compile an exploit contract via Ultra.

    Returns (proposal, timing_info).
    """
    timing = {
        "step": "propose",
        "model": config.MODEL_ULTRA,
        "compile_attempts": [],
        "llm_calls": [],
    }

    if prior_failure:
        user_content = f"""Your previous exploit compiled and deployed but failed:
Revert reason: {prior_failure.get('revert_reason', 'unknown')}
Research on this error:
{_format_precedent(prior_failure.get('research', []))}

TARGET CONTRACT SOURCE:
{source_code}

SECURITY ANALYSIS FLAGS:
{json.dumps(risk_flags, indent=2)}

Write a revised exploit contract that avoids this failure mode.
"""
    else:
        user_content = f"""TARGET CONTRACT SOURCE:
{source_code}

SECURITY ANALYSIS FLAGS:
{json.dumps(risk_flags, indent=2)}

HISTORICAL PRECEDENT (Tavily):
{_format_precedent(precedent_results)}

Write an exploit contract that drains ETH from this target.
"""

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    last_error = None
    for attempt in range(config.MAX_COMPILE_RETRIES):
        proposal, raw, llm_duration = _call_ultra(messages)
        timing["llm_calls"].append({"attempt": attempt, "duration_s": llm_duration})
        compile_start = time.time()
        try:
            abi, bytecode = chain.compile_source_code(
                proposal.solidity_source, proposal.contract_name
            )
            proposal.abi = abi
            proposal.bytecode = bytecode
            timing["compile_attempts"].append(
                {
                    "attempt": attempt,
                    "success": True,
                    "duration_s": time.time() - compile_start,
                }
            )
            return proposal, timing
        except Exception as compile_err:
            last_error = str(compile_err)
            timing["compile_attempts"].append(
                {
                    "attempt": attempt,
                    "success": False,
                    "error": last_error,
                    "duration_s": time.time() - compile_start,
                }
            )
            messages.append({"role": "assistant", "content": raw})
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your previous Solidity code failed to compile:\n"
                        f"{last_error}\n\nFix the compilation error and "
                        "return the corrected contract."
                    ),
                }
            )

    raise CompilationFailed(
        f"Ultra failed to produce compilable Solidity after "
        f"{config.MAX_COMPILE_RETRIES} attempts: {last_error}"
    )
