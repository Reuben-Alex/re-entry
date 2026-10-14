"""
Exploit contract generation — Nemotron Ultra writes Solidity from scratch.

One generic prompt. It receives source, ABI, ranked hypotheses, precedent,
and the previous revert or trace. It does not name target functions.
"""
import json
import time
from dataclasses import dataclass, field

from openai import OpenAI

from orchestrator import chain, config
from orchestrator.exceptions import CompilationFailed
from orchestrator.recon import map_functions
from orchestrator.revert import clean_revert_reason

_client = None

GENERIC_EXPLOIT_PROMPT = """You are a smart contract security researcher writing an exploit for a local sandbox. The target is the contract source in the user message. Do not assume a public network.

CONSTRAINTS:
- First line: pragma solidity ^0.8.19;
- constructor(address target) stores the primary contract
- function attack() external payable is the only entry the sandbox calls
- You may add receive(), extra functions, and helper contracts in the same source
- If the sandbox notes say it will call another function on your contract after attack(), include that function
- No external imports; inline interfaces only
- Call only functions that exist on the target. Read the source and the ABI.
- Ranked hypotheses are clues from recon, not a recipe
- Abstract classes you may recognize while reading the source:
  - state updated after an external call
  - a second function that moves the same balance while that call is in progress
  - a privileged action with no caller check
  - a payment sent to the caller instead of the recorded account
  - a price or share calculation the caller can move inside one transaction
  - a setup function that can be called again
  - a signed authorization with no nonce, so one signature can be reused
- If ETH may arrive at your contract, include receive() external payable {}
- Return JSON: solidity_source, contract_name, entry_function, entry_value_wei, reasoning

entry_value_wei is the ETH the sandbox attaches to attack(). Use 0 when the exploit needs none.
"""

OWASP_TAXONOMY = (
    "Label risk_pattern using OWASP Smart Contract Top 10 (2025) where possible: "
    "reentrancy (SC05), access_control (SC01), logic|escrow, oracle_manipulation, "
    "unchecked_call, or general."
)


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


def _format_abi_summary(abi: list) -> str:
    summaries = map_functions(abi)
    return json.dumps(summaries, indent=2)


def _parse_proposal(raw: str) -> ExploitProposal:
    """Parse Ultra JSON response into ExploitProposal."""
    if not raw or not raw.strip():
        raise ValueError("Empty response from Ultra")
    parsed = json.loads(raw)
    required = ("solidity_source", "contract_name")
    missing = [k for k in required if k not in parsed]
    if missing:
        raise ValueError(f"Missing keys in Ultra response: {missing}")
    return ExploitProposal(
        solidity_source=parsed["solidity_source"],
        contract_name=parsed["contract_name"],
        entry_function=parsed.get("entry_function", "attack"),
        entry_value_wei=int(parsed.get("entry_value_wei", 10**18)),
        reasoning=parsed.get("reasoning", ""),
    )


def _message_text(message) -> str:
    """Prefer the JSON content. Fall back to a JSON object in the reasoning trace."""
    content = (message.content or "").strip()
    if content:
        return content
    reasoning = getattr(message, "reasoning_content", None) or ""
    start = reasoning.rfind("{")
    end = reasoning.rfind("}")
    if start != -1 and end > start:
        return reasoning[start : end + 1]
    return ""


def _call_ultra(messages: list[dict]) -> tuple[ExploitProposal, str, float]:
    """Call Ultra and parse JSON response. Returns proposal, raw, duration."""
    start = time.time()
    client = _get_client()
    last_err = None
    raw = ""
    for _attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=config.MODEL_ULTRA,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=16384,
            )
            raw = _message_text(response.choices[0].message)
            proposal = _parse_proposal(raw)
            duration = time.time() - start
            return proposal, raw, duration
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_err = exc
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Your response was invalid ({exc}). "
                        "Return valid JSON with solidity_source, contract_name, "
                        "entry_function, entry_value_wei, reasoning. "
                        "Put the JSON in the message content."
                    ),
                }
            )
    raise CompilationFailed(
        f"Ultra returned invalid JSON after retries: {last_err}"
    )


def propose_exploit(
    source_code: str,
    risk_flags: list[dict],
    precedent_results: list[dict],
    prior_failure: dict | None = None,
    abi: list | None = None,
    target_name: str = "",
    sandbox_notes: str = "",
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
    abi_block = _format_abi_summary(abi or [])
    notes_block = sandbox_notes.strip() or "None."

    if prior_failure:
        prev_src = prior_failure.get("previous_source", "")
        trace = prior_failure.get("trace") or ""
        user_content = f"""Your previous exploit failed.

Revert reason: {clean_revert_reason(prior_failure.get('revert_reason'))}
Call trace:
{trace or '(no trace)'}
Research on this error:
{_format_precedent(prior_failure.get('research', []))}

Previous exploit source (revise this):
{prev_src[:3000] if prev_src else 'N/A'}

TARGET: {target_name}
TARGET CONTRACT SOURCE:
{source_code}

TARGET ABI (callable functions):
{abi_block}

RANKED HYPOTHESES:
{json.dumps(risk_flags, indent=2)}

SANDBOX NOTES:
{notes_block}

Write a revised exploit contract that avoids this failure mode.
"""
    else:
        user_content = f"""TARGET: {target_name}
TARGET CONTRACT SOURCE:
{source_code}

TARGET ABI (callable functions):
{abi_block}

RANKED HYPOTHESES:
{json.dumps(risk_flags, indent=2)}

HISTORICAL PRECEDENT (Tavily — use these to shape strategy):
{_format_precedent(precedent_results)}

SANDBOX NOTES:
{notes_block}

Write an exploit contract that takes value from this target in the local sandbox.
"""

    messages = [
        {"role": "system", "content": GENERIC_EXPLOIT_PROMPT},
        {"role": "user", "content": user_content},
    ]

    last_error = None
    for attempt in range(config.MAX_COMPILE_RETRIES):
        proposal, raw, llm_duration = _call_ultra(messages)
        timing["llm_calls"].append({"attempt": attempt, "duration_s": llm_duration})
        compile_start = time.time()
        try:
            abi_out, bytecode = chain.compile_source_code(
                proposal.solidity_source, proposal.contract_name
            )
            proposal.abi = abi_out
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
