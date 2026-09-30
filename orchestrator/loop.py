"""
The main propose -> execute -> retry loop.
"""
import dataclasses
import time

from orchestrator import config, executor, outcome, precedent, proposer, recon, report
from orchestrator.events import EmitFn, emit
from orchestrator.exceptions import CompilationFailed
from orchestrator.foundry_export import export_foundry_poc
from orchestrator import patcher
from orchestrator.patch_verify import (
    build_replay_descriptor,
    verify_patch,
    verification_to_dict,
)
from orchestrator.preflight import PreflightError, ensure_target_funded
from orchestrator.revert import clean_revert_reason


def _run_patch_verify(
    on_event,
    target_name: str,
    source_code: str,
    sandbox,
    deployer: str,
    risk_flags: list,
    winning_proposal,
    used_fallback: bool,
    attempt_history: list,
    report_data: dict,
    step_timings: list,
) -> dict:
    """Generate patch, redeploy, replay exploit; attach results to report."""
    if not config.ENABLE_PATCH_VERIFY:
        report_data["patch_status"] = "skipped"
        return report_data

    emit(on_event, "patch_start", target=target_name)
    try:
        patch_proposal, patch_timing = patcher.propose_patch(
            source_code,
            target_name,
            risk_flags,
            winning_proposal,
            used_fallback,
            attempt_history,
        )
        step_timings.append(patch_timing)
        emit(
            on_event,
            "patch_propose_done",
            reasoning=(patch_proposal.reasoning or "")[:300],
            contract_name=patch_proposal.contract_name,
        )

        replay = build_replay_descriptor(
            target_name, winning_proposal, used_fallback
        )
        verification = verify_patch(sandbox, replay, patch_proposal, deployer)
        emit(
            on_event,
            "patch_verify_done",
            verified=verification.exploit_blocked,
            replay_success=verification.replay_success,
        )

        report_data["patch"] = {
            "diff": patcher.compute_patch_diff(
                source_code, patch_proposal.patched_source
            ),
            "patched_source": patch_proposal.patched_source,
            "reasoning": patch_proposal.reasoning,
            "oz_pattern": getattr(patch_proposal, "oz_pattern", "")
            or patcher.infer_oz_pattern(patch_proposal.patched_source),
            "verification": verification_to_dict(verification),
            "patch_verified": verification.exploit_blocked,
        }
        report_data["patch_verified"] = verification.exploit_blocked
        report_data["patch_diff"] = report_data["patch"]["diff"]
        report_data["patch_reasoning"] = patch_proposal.reasoning
        report_data["patch_status"] = (
            "verified" if verification.exploit_blocked else "failed"
        )
    except Exception as exc:
        emit(on_event, "patch_failed", message=str(exc))
        report_data["patch_status"] = "failed"
        report_data["patch_verified"] = False
        report_data["patch"] = {"error": str(exc)}

    emit(
        on_event,
        "patch_done",
        verified=report_data.get("patch_verified", False),
        status=report_data.get("patch_status", "failed"),
    )
    return report_data


def _empty_failure_report(
    target_name: str,
    verdict: str,
    explanation: str,
    vault_address: str,
    sandbox,
    pipeline_start: float,
    risk_flags: list | None = None,
) -> dict:
    balance = 0
    try:
        if hasattr(sandbox, "get_balance"):
            balance = sandbox.get_balance(vault_address)
        elif hasattr(sandbox, "w3") and sandbox.w3:
            balance = sandbox.w3.eth.get_balance(vault_address)
    except Exception:
        pass

    return {
        "target_name": target_name,
        "verdict": verdict,
        "verdict_explanation": explanation,
        "used_fallback": False,
        "attempts": 0,
        "drain_amount_wei": 0,
        "attacker_gain_wei": 0,
        "generated_exploit_source": "",
        "precedent_citation": "",
        "precedent_sources": [],
        "risk_flags": risk_flags or [],
        "attempt_history": [],
        "outcome_summary": {},
        "vault_balance_before": balance,
        "total_pipeline_s": time.time() - pipeline_start,
        "step_timings": [],
        "summary": explanation,
        "vulnerability_class": "unknown",
        "evidence": explanation,
        "reproduction_steps": "Fix preflight and redeploy demo contracts.",
    }


def run_pipeline(
    target_name: str,
    abi: list,
    source_code: str,
    sandbox,
    vault_address: str,
    deployer: str,
    on_event: EmitFn = None,
    deploy_fn=None,
) -> dict:
    """Run full agent pipeline against one target contract."""
    pipeline_start = time.time()
    step_timings = []
    emit(on_event, "pipeline_start", target=target_name)

    emit(on_event, "preflight_start", target=target_name)
    try:
        if deploy_fn is not None:
            preflight = ensure_target_funded(
                sandbox, target_name, vault_address, deploy_fn
            )
            vault_address = preflight["address"]
            if preflight["redeployed"]:
                emit(on_event, "preflight_redeploy", message="Contracts redeployed")
        else:
            from orchestrator.preflight import _get_balance, MIN_BALANCE_WEI

            balance = _get_balance(sandbox, vault_address)
            if balance < MIN_BALANCE_WEI:
                raise PreflightError(
                    f"Target unfunded ({balance} wei)",
                    verdict="unfunded_target",
                )
            preflight = {"balance_wei": balance, "redeployed": False}
        emit(
            on_event,
            "preflight_done",
            balance_wei=preflight["balance_wei"],
            redeployed=preflight.get("redeployed", False),
        )
    except PreflightError as exc:
        emit(on_event, "preflight_failed", message=str(exc), verdict=exc.verdict)
        report_data = _empty_failure_report(
            target_name,
            exc.verdict,
            str(exc),
            vault_address,
            sandbox,
            pipeline_start,
        )
        emit(on_event, "pipeline_done", report=report_data)
        return report_data

    emit(on_event, "recon_start", target=target_name)
    function_summaries = recon.map_functions(abi)
    risk_flags, recon_timing = recon.flag_risk_patterns(
        function_summaries, source_code
    )
    step_timings.append(recon_timing)
    emit(on_event, "recon_done", risk_flags=risk_flags, timing=recon_timing)
    if not risk_flags:
        risk_flags = [
            {
                "function_name": "unknown",
                "risk_pattern": "general",
                "confidence": 0.0,
            }
        ]

    pattern = risk_flags[0]["risk_pattern"]
    emit(on_event, "precedent_start", pattern=pattern)
    precedent_results = precedent.find_precedent(pattern)
    step_timings.append(
        {"step": "precedent", "results_count": len(precedent_results)}
    )
    emit(on_event, "precedent_done", sources=precedent_results, pattern=pattern)

    attempt_history = []
    prior_failure = None
    agent_fallback_used = False
    winning_proposal = None

    for attempt in range(config.MAX_RETRY_ATTEMPTS):
        emit(on_event, "attempt_start", attempt=attempt + 1)
        sandbox.fork_checkpoint()
        proposal = None
        propose_timing = {}
        exec_timing = {}
        attempt_used_fallback = False

        try:
            emit(on_event, "propose_start", attempt=attempt + 1)
            proposal, propose_timing = proposer.propose_exploit(
                source_code,
                risk_flags,
                precedent_results,
                prior_failure,
                abi=abi,
                target_name=target_name,
            )
            emit(
                on_event,
                "propose_done",
                attempt=attempt + 1,
                reasoning=proposal.reasoning,
                source_preview=proposal.solidity_source[:500],
                timing=propose_timing,
            )
            emit(on_event, "execute_start", attempt=attempt + 1)
            result, exec_timing = executor.execute_proposal(
                sandbox, proposal, vault_address, abi, deployer
            )
        except CompilationFailed as exc:
            emit(on_event, "compile_failed", attempt=attempt + 1, error=str(exc))
            sandbox.rollback()
            prior_failure = {
                "revert_reason": clean_revert_reason(str(exc)),
                "research": [],
                "compile_error": True,
                "previous_source": "",
            }
            attempt_history.append(
                {
                    "attempt": attempt,
                    "generated_source": "COMPILE_FAILED",
                    "used_fallback_this_attempt": False,
                    "propose_timing": propose_timing,
                    "execute_timing": {},
                    "result": {
                        "success": False,
                        "revert_reason": str(exc),
                    },
                }
            )
            continue

        attempt_entry = {
            "attempt": attempt,
            "generated_source": proposal.solidity_source,
            "used_fallback_this_attempt": attempt_used_fallback,
            "propose_timing": propose_timing,
            "execute_timing": exec_timing,
            "result": dataclasses.asdict(result),
        }
        attempt_history.append(attempt_entry)
        step_timings.append(
            {
                "step": f"attempt_{attempt}",
                "propose": propose_timing,
                "execute": exec_timing,
            }
        )
        emit(
            on_event,
            "attempt_done",
            attempt=attempt + 1,
            success=result.success,
            revert_reason=result.revert_reason,
            result=dataclasses.asdict(result),
        )

        if result.success:
            winning_proposal = proposal
            outcome_summary = outcome.summarize(
                result.vault_balance_before,
                result.vault_balance_after,
                result.attacker_balance_before,
                result.attacker_balance_after,
            )
            patch_data = _run_patch_verify(
                on_event,
                target_name,
                source_code,
                sandbox,
                deployer,
                risk_flags,
                winning_proposal,
                agent_fallback_used,
                attempt_history,
                {},
                step_timings,
            )
            report_data = report.generate_report(
                target_name,
                success=True,
                proposal=winning_proposal,
                outcome_summary=outcome_summary,
                precedent_results=precedent_results,
                attempt_history=attempt_history,
                used_fallback=agent_fallback_used,
                risk_flags=risk_flags,
                patch_info=patch_data,
            )
            report_data.update(patch_data)
            report_data["precedent_sources"] = precedent_results
            report_data["step_timings"] = step_timings
            report_data["foundry_poc"] = export_foundry_poc(
                target_name, vault_address, winning_proposal
            )
            report_data["total_pipeline_s"] = time.time() - pipeline_start
            emit(on_event, "pipeline_done", report=report_data)
            return report_data

        sandbox.rollback()
        clean_reason = clean_revert_reason(result.revert_reason)
        emit(on_event, "retry_research", revert_reason=clean_reason)
        fix_research = precedent.find_fix_for_error(clean_reason)
        emit(on_event, "retry_research_done", sources=fix_research)
        prior_failure = {
            "revert_reason": clean_reason,
            "research": fix_research,
            "previous_source": proposal.solidity_source if proposal else "",
        }

    emit(on_event, "fallback_start", attempt="final", note="ABI safety net only")
    sandbox.fork_checkpoint()
    fallback_result, fallback_timing = executor.fallback_exploit(
        sandbox, vault_address, abi, deployer, target_name=target_name
    )
    attempt_history.append(
        {
            "attempt": len(attempt_history),
            "generated_source": fallback_timing.get(
                "label", "FALLBACK: ABI safety net"
            ),
            "used_fallback_this_attempt": True,
            "execute_timing": fallback_timing,
            "result": dataclasses.asdict(fallback_result),
        }
    )
    if fallback_result.success:
        outcome_summary = outcome.summarize(
            fallback_result.vault_balance_before,
            fallback_result.vault_balance_after,
            fallback_result.attacker_balance_before,
            fallback_result.attacker_balance_after,
        )
        patch_data = _run_patch_verify(
            on_event,
            target_name,
            source_code,
            sandbox,
            deployer,
            risk_flags,
            None,
            True,
            attempt_history,
            {},
            step_timings,
        )
        report_data = report.generate_report(
            target_name,
            success=True,
            proposal=None,
            outcome_summary=outcome_summary,
            precedent_results=precedent_results,
            attempt_history=attempt_history,
            used_fallback=True,
            risk_flags=risk_flags,
            patch_info=patch_data,
        )
        report_data.update(patch_data)
        report_data["precedent_sources"] = precedent_results
        report_data["step_timings"] = step_timings
        report_data["total_pipeline_s"] = time.time() - pipeline_start
        emit(on_event, "pipeline_done", report=report_data)
        return report_data

    report_data = report.generate_report(
        target_name,
        success=False,
        proposal=None,
        outcome_summary={},
        precedent_results=precedent_results,
        attempt_history=attempt_history,
        used_fallback=False,
        risk_flags=risk_flags,
    )
    report_data["precedent_sources"] = precedent_results
    report_data["total_pipeline_s"] = time.time() - pipeline_start
    report_data["step_timings"] = step_timings
    if attempt_history:
        report_data["vault_balance_before"] = attempt_history[-1]["result"].get(
            "vault_balance_before", 0
        )
    emit(on_event, "pipeline_done", report=report_data)
    return report_data
