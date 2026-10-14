"""
Minimal patch generation — Nemotron Ultra closes the specific exploited hole.
"""
import difflib
import json
import re
import time
from dataclasses import dataclass, field

from openai import OpenAI

from orchestrator import chain, config
from orchestrator.exceptions import CompilationFailed
from orchestrator.proposer import ExploitProposal

_client = None

PATCH_PROMPT = """You are a smart contract security auditor writing a MINIMAL patch.

RULES:
- Return the FULL patched contract source — not a diff, not pseudocode
- Keep the same contract name and public interface (function signatures unchanged)
- Make the SMALLEST change that blocks the provided exploit
- First line: pragma solidity ^0.8.19;
- Do NOT rewrite unrelated code
- Do NOT assume a reference Safe* or patched twin contract exists in the repo
- Prefer patterns that match audited OpenZeppelin Contracts conventions
  (ReentrancyGuard/nonReentrant, Ownable/onlyOwner, AccessControl, checks-effects-interactions).
  Do NOT import OpenZeppelin — inline the equivalent minimal pattern.

PATTERN FIXES (apply only what the source and the exploit show):
- external call before state update: update state first, or share one lock across every function that moves the same balance
- missing caller check: restrict the privileged action to the recorded owner, and let a setup function succeed only once
- payment to the caller: pay the recorded account
- price or share math the caller can move: reject zero-share deposits and do not trust a same-transaction spot price
- signature with no nonce: bind the digest to the caller and a nonce, and store used digests
Honest users must still be able to deposit and withdraw their own funds.

In reasoning, name the OpenZeppelin-equivalent pattern you matched (e.g. "Ownable.onlyOwner",
"ReentrancyGuard / CEI").

Return JSON: patched_source, contract_name, reasoning, oz_pattern
"""


@dataclass
class PatchProposal:
    patched_source: str
    contract_name: str
    reasoning: str
    oz_pattern: str = ""
    abi: list = field(default_factory=list)
    bytecode: str = ""


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.NEBIUS_API_KEY:
            raise ValueError("NEBIUS_API_KEY is required for patcher")
        _client = OpenAI(
            api_key=config.NEBIUS_API_KEY,
            base_url=config.NEBIUS_BASE_URL,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    return _client


def _infer_contract_name(source_code: str, target_name: str) -> str:
    match = re.search(r"contract\s+(\w+)", source_code)
    if match:
        return match.group(1)
    return target_name


def _format_exploit_block(
    proposal: ExploitProposal | None,
    used_fallback: bool,
    target_name: str,
) -> str:
    if proposal:
        return (
            f"Agent-generated exploit ({proposal.contract_name}):\n"
            f"{proposal.solidity_source[:3000]}\n"
            f"Entry: {proposal.entry_function}() value={proposal.entry_value_wei} wei"
        )
    if used_fallback:
        if "Treasury" in target_name:
            return "Fallback: direct withdrawAll() from EOA (no attacker contract)"
        return "Fallback: Attacker.sol reentrancy pattern (deposit → withdraw → receive re-enter)"
    return "Unknown exploit path"


def _parse_patch(raw: str, default_name: str) -> PatchProposal:
    parsed = json.loads(raw)
    required = ("patched_source", "contract_name")
    missing = [k for k in required if k not in parsed]
    if missing:
        raise ValueError(f"Missing keys in Ultra patch response: {missing}")
    return PatchProposal(
        patched_source=parsed["patched_source"],
        contract_name=parsed.get("contract_name", default_name),
        reasoning=parsed.get("reasoning", ""),
        oz_pattern=parsed.get("oz_pattern", ""),
    )


def _call_ultra_patch(messages: list[dict], default_name: str) -> tuple[PatchProposal, float]:
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
                max_tokens=8192,
            )
            raw = response.choices[0].message.content or ""
            proposal = _parse_patch(raw, default_name)
            return proposal, time.time() - start
        except (json.JSONDecodeError, ValueError, KeyError) as exc:
            last_err = exc
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Invalid JSON ({exc}). Return patched_source, "
                        "contract_name, reasoning."
                    ),
                }
            )
    raise ValueError(f"Ultra patch invalid after retries: {last_err}")


def compute_patch_diff(original: str, patched: str) -> str:
    """Unified diff for judge-facing report."""
    original_lines = original.splitlines(keepends=True)
    patched_lines = patched.splitlines(keepends=True)
    diff = difflib.unified_diff(
        original_lines,
        patched_lines,
        fromfile="vulnerable",
        tofile="patched",
        lineterm="",
    )
    return "".join(diff)


def infer_oz_pattern(patched_source: str) -> str:
    """Heuristic match to OpenZeppelin-audited conventions."""
    src = patched_source.lower()
    hits = []
    if "onlyowner" in src or "require(msg.sender == owner" in src:
        hits.append("Ownable.onlyOwner")
    if "nonreentrant" in src or ("locked" in src and "mutex" in src):
        hits.append("ReentrancyGuard.nonReentrant")
    # CEI: balance zeroed before .call{value
    if re.search(
        r"balances?\[[^\]]+\]\s*=\s*0;[\s\S]{0,200}\.call\{value",
        patched_source,
    ):
        hits.append("checks-effects-interactions (CEI)")
    if "accesscontrol" in src or "hasrole" in src:
        hits.append("AccessControl")
    return ", ".join(hits) if hits else "custom minimal fix"


def propose_patch(
    source_code: str,
    target_name: str,
    risk_flags: list[dict],
    proposal: ExploitProposal | None,
    used_fallback: bool,
    attempt_history: list[dict],
) -> tuple[PatchProposal, dict]:
    """
    Generate and compile a minimal patched contract via Ultra.

    Returns (patch_proposal, timing_info).
    """
    timing = {"step": "patch", "model": config.MODEL_ULTRA, "compile_attempts": []}
    contract_name = _infer_contract_name(source_code, target_name)
    pattern = (
        risk_flags[0].get("risk_pattern", "general") if risk_flags else "general"
    )
    attempts_summary = []
    for a in attempt_history[-5:]:
        result = a.get("result") or {}
        revert = result.get("revert_reason") or ""
        attempts_summary.append(
            {
                "attempt": a.get("attempt"),
                "success": result.get("success"),
                "revert": str(revert)[:120],
            }
        )

    user_content = f"""TARGET: {target_name}
CONTRACT NAME (must preserve): {contract_name}
VULNERABILITY: {pattern}

ORIGINAL SOURCE:
{source_code}

EXPLOIT THAT SUCCEEDED (block THIS specifically):
{_format_exploit_block(proposal, used_fallback, target_name)}

ATTEMPT HISTORY:
{json.dumps(attempts_summary, indent=2)}

Write the minimal patched contract that prevents this exploit while keeping the same public API.
"""

    messages = [
        {"role": "system", "content": PATCH_PROMPT},
        {"role": "user", "content": user_content},
    ]

    last_error = None
    for attempt in range(config.MAX_COMPILE_RETRIES):
        patch, llm_duration = _call_ultra_patch(messages, contract_name)
        timing["llm_duration_s"] = llm_duration
        compile_start = time.time()
        try:
            abi, bytecode = chain.compile_source_code(
                patch.patched_source, patch.contract_name
            )
            patch.abi = abi
            patch.bytecode = bytecode
            timing["compile_attempts"].append(
                {
                    "attempt": attempt,
                    "success": True,
                    "duration_s": time.time() - compile_start,
                }
            )
            return patch, timing
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
            messages.append(
                {
                    "role": "user",
                    "content": (
                        f"Patch failed to compile:\n{last_error}\n\n"
                        "Fix compilation and return corrected patched_source."
                    ),
                }
            )

    raise CompilationFailed(
        f"Ultra failed to produce compilable patch after "
        f"{config.MAX_COMPILE_RETRIES} attempts: {last_error}"
    )
