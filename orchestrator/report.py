"""
Evidence report generation — Nemotron Super.
"""
import json
import time

from openai import OpenAI

from orchestrator import config
from orchestrator.proposer import ExploitProposal

VERDICT_EXPLANATIONS = {
    "vulnerable_agent_generated": (
        "Vulnerability confirmed: exploit contract generated and executed "
        "autonomously by the agent"
    ),
    "vulnerable_fallback": (
        "Confirmed via labeled ABI safety-net fallback after agent retries; "
        "prefer agent-generated verdicts for judging"
    ),
    "no_exploit_found": (
        "No viable exploit found after exhausting all attempts"
    ),
    "unfunded_target": (
        "Pipeline aborted: target contract had insufficient ETH to drain"
    ),
    "infra_error": (
        "Pipeline aborted: sandbox or deployment infrastructure error"
    ),
}

_client = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        if not config.NEBIUS_API_KEY:
            raise ValueError("NEBIUS_API_KEY is required for report")
        _client = OpenAI(
            api_key=config.NEBIUS_API_KEY,
            base_url=config.NEBIUS_BASE_URL,
            timeout=config.LLM_TIMEOUT_SECONDS,
        )
    return _client


def _determine_verdict(success: bool, used_fallback: bool) -> str:
    if not success:
        return "no_exploit_found"
    if used_fallback:
        return "vulnerable_fallback"
    return "vulnerable_agent_generated"


def _format_precedent(precedent_results: list[dict]) -> str:
    if not precedent_results:
        return "Tavily search returned no results."
    parts = []
    for item in precedent_results:
        parts.append(
            f"{item.get('title', 'Unknown')} ({item.get('url', 'no url')})"
        )
    return "; ".join(parts)


def generate_report(
    target_name: str,
    success: bool,
    proposal: ExploitProposal | None,
    outcome_summary: dict,
    precedent_results: list[dict],
    attempt_history: list[dict],
    used_fallback: bool,
    risk_flags: list[dict],
    patch_info: dict | None = None,
) -> dict:
    """
    Build evidence report. Verdict is determined by pipeline, not Super.
    """
    verdict = _determine_verdict(success, used_fallback)
    base_report = {
        "target_name": target_name,
        "verdict": verdict,
        "verdict_explanation": VERDICT_EXPLANATIONS[verdict],
        "used_fallback": used_fallback,
        "attempts": len(attempt_history),
        "drain_amount_wei": outcome_summary.get("vault_drained_wei", 0),
        "attacker_gain_wei": outcome_summary.get("attacker_gain_wei", 0),
        "generated_exploit_source": (
            proposal.solidity_source
            if proposal
            else "FALLBACK: ABI safety net (see attempt_history)"
        ),
        "precedent_citation": _format_precedent(precedent_results),
        "risk_flags": risk_flags,
        "attempt_history": attempt_history,
        "outcome_summary": outcome_summary,
    }

    if not success:
        base_report["summary"] = base_report["verdict_explanation"]
        base_report["vulnerability_class"] = (
            risk_flags[0].get("risk_pattern", "unknown") if risk_flags else "unknown"
        )
        base_report["evidence"] = (
            "No successful drain observed. See attempt_history for details."
        )
        base_report["reproduction_steps"] = (
            "Re-run after ensuring target is funded and agent retries complete."
        )
        if not config.MODEL_SUPER or not config.NEBIUS_API_KEY:
            return base_report

    if not config.MODEL_SUPER or not config.NEBIUS_API_KEY:
        base_report["summary"] = base_report["verdict_explanation"]
        base_report["vulnerability_class"] = (
            risk_flags[0].get("risk_pattern", "unknown") if risk_flags else "unknown"
        )
        base_report["evidence"] = "See risk_flags and generated_exploit_source."
        base_report["reproduction_steps"] = (
            "Deploy exploit contract, call attack() with sufficient ETH."
        )
        return base_report

    success_note = (
        "EXPLOIT SUCCEEDED — describe the confirmed drain and evidence."
        if success
        else (
            "EXPLOIT DID NOT SUCCEED — verdict is no_exploit_found. "
            "Do NOT claim funds were drained. Summarize what was tried and why "
            "it failed."
        )
    )

    patch_block = ""
    if patch_info:
        patch_block = f"""
PATCH VERIFICATION:
- patch_status: {patch_info.get('patch_status', 'unknown')}
- patch_verified (exploit blocked on patched deploy): {patch_info.get('patch_verified', False)}
- patch reasoning: {(patch_info.get('patch_reasoning') or patch_info.get('patch', {}).get('reasoning', ''))[:500]}
- diff preview: {(patch_info.get('patch_diff') or patch_info.get('patch', {}).get('diff', ''))[:800]}
Include in evidence that the agent generated a minimal fix and re-ran the same exploit against the patched contract.
If an OpenZeppelin-equivalent pattern was used (Ownable, ReentrancyGuard/CEI, AccessControl), name it explicitly in fix/evidence.
"""

    prompt = f"""Summarize this smart contract security assessment for judges.

{success_note}

VERDICT (do not change): {verdict}
TARGET: {target_name}
RISK FLAGS: {json.dumps(risk_flags, indent=2)}
OUTCOME: {json.dumps(outcome_summary, indent=2)}
PRECEDENT (must cite at least one in precedent_citation field): {_format_precedent(precedent_results)}
GENERATED EXPLOIT (truncated): {(proposal.solidity_source[:2000] if proposal else 'FALLBACK')}
ATTEMPTS: {len(attempt_history)}
USED FALLBACK: {used_fallback}
{patch_block}

Return JSON with keys: summary, vulnerability_class, evidence, reproduction_steps, precedent_citation, lifecycle_story
lifecycle_story must be an object with four string fields for judges:
- finding: what recon/Tavily indicated
- proof: how execution demonstrated the vulnerability
- fix: what the generated patch changes (plain English, not copying a Safe* twin)
- verification: replaying the same exploit against the patched deploy and that it failed
Do NOT change the verdict field — it is already determined.
"""
    start = time.time()
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model=config.MODEL_SUPER,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write concise security evidence reports. "
                        "Never contradict the VERDICT. Return only valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        parsed = json.loads(response.choices[0].message.content or "{}")
        base_report.update(parsed)
        base_report["report_generation_s"] = time.time() - start
    except Exception:
        base_report["summary"] = base_report["verdict_explanation"]
        base_report["vulnerability_class"] = (
            risk_flags[0].get("risk_pattern", "unknown") if risk_flags else "unknown"
        )
        base_report["evidence"] = "Automated report generation unavailable."
        base_report["reproduction_steps"] = (
            "Deploy exploit contract, call attack() with sufficient ETH."
        )

    base_report["verdict"] = verdict
    base_report["verdict_explanation"] = VERDICT_EXPLANATIONS[verdict]
    if not base_report.get("precedent_citation"):
        base_report["precedent_citation"] = _format_precedent(precedent_results)
    if patch_info:
        base_report["patch_status"] = patch_info.get("patch_status", "skipped")
        base_report["patch_verified"] = patch_info.get("patch_verified", False)
        if patch_info.get("patch_diff"):
            base_report["patch_diff"] = patch_info["patch_diff"]
        if patch_info.get("patch_reasoning"):
            base_report["patch_reasoning"] = patch_info["patch_reasoning"]
        if patch_info.get("patch"):
            base_report["patch"] = patch_info["patch"]
    story = base_report.get("lifecycle_story")
    if isinstance(story, dict):
        base_report["lifecycle_story"] = story
    elif success and patch_info:
        base_report["lifecycle_story"] = {
            "finding": base_report.get("summary", "")[:400],
            "proof": str(base_report.get("evidence", ""))[:400],
            "fix": (patch_info.get("patch_reasoning") or "")[:400],
            "verification": (
                "Patch verified: exploit blocked on redeploy."
                if patch_info.get("patch_verified")
                else f"Patch status: {patch_info.get('patch_status')}"
            ),
        }
    return base_report
