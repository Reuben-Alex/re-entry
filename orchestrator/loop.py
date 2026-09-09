"""
The main propose -> execute -> retry loop.
"""
import dataclasses
import time

from orchestrator import config, executor, outcome, precedent, proposer, recon, report
from orchestrator.exceptions import CompilationFailed
from orchestrator.proposer import ExploitProposal


def run_pipeline(
    target_name: str,
    abi: list,
    source_code: str,
    sandbox,
    vault_address: str,
    deployer: str,
) -> dict:
    """Run full agent pipeline against one target contract."""
    pipeline_start = time.time()
    step_timings = []

    function_summaries = recon.map_functions(abi)
    risk_flags, recon_timing = recon.flag_risk_patterns(
        function_summaries, source_code
    )
    step_timings.append(recon_timing)
    if not risk_flags:
        risk_flags = [
            {
                "function_name": "unknown",
                "risk_pattern": "general",
                "confidence": 0.0,
            }
        ]

    precedent_results = precedent.find_precedent(risk_flags[0]["risk_pattern"])
    step_timings.append(
        {"step": "precedent", "results_count": len(precedent_results)}
    )

    attempt_history = []
    prior_failure = None
    used_fallback = False
    winning_proposal = None

    for attempt in range(config.MAX_RETRY_ATTEMPTS):
        sandbox.fork_checkpoint()
        proposal = None
        propose_timing = {}
        exec_timing = {}

        try:
            proposal, propose_timing = proposer.propose_exploit(
                source_code, risk_flags, precedent_results, prior_failure
            )
            result, exec_timing = executor.execute_proposal(
                sandbox, proposal, vault_address, abi, deployer
            )
        except CompilationFailed:
            used_fallback = True
            result, exec_timing = executor.fallback_exploit(
                sandbox, vault_address, abi, deployer
            )

        attempt_entry = {
            "attempt": attempt,
            "generated_source": (
                proposal.solidity_source if proposal else "FALLBACK"
            ),
            "used_fallback_this_attempt": proposal is None,
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

        if result.success:
            winning_proposal = proposal
            outcome_summary = outcome.summarize(
                result.vault_balance_before,
                result.vault_balance_after,
                result.attacker_balance_before,
                result.attacker_balance_after,
            )
            report_data = report.generate_report(
                target_name,
                success=True,
                proposal=winning_proposal,
                outcome_summary=outcome_summary,
                precedent_results=precedent_results,
                attempt_history=attempt_history,
                used_fallback=used_fallback or proposal is None,
                risk_flags=risk_flags,
            )
            report_data["total_pipeline_s"] = time.time() - pipeline_start
            report_data["step_timings"] = step_timings
            return report_data

        sandbox.rollback()
        fix_research = precedent.find_fix_for_error(
            result.revert_reason or "unknown"
        )
        prior_failure = {
            "revert_reason": result.revert_reason,
            "research": fix_research,
        }

    report_data = report.generate_report(
        target_name,
        success=False,
        proposal=None,
        outcome_summary={},
        precedent_results=precedent_results,
        attempt_history=attempt_history,
        used_fallback=used_fallback,
        risk_flags=risk_flags,
    )
    report_data["total_pipeline_s"] = time.time() - pipeline_start
    report_data["step_timings"] = step_timings
    return report_data
