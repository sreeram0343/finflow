import logging
from typing import Dict, Any
from src.core.config import settings
from src.graph.state import FinFlowState
from src.schemas.validation import MatchStatus, SeverityLevel

logger = logging.getLogger(__name__)


async def gatekeeper_node(state: FinFlowState) -> Dict[str, Any]:
    """
    Final Gatekeeper decision engine. Aggregates results from math verification,
    PO matching, risk assessment, and policy compliance to determine either
    immediate straight-through processing (STP Auto-Approval), automatic rejection,
    or routing to the Human-in-the-Loop review queue.
    """
    # 1. Check if this is a post-human review resumption
    human_action = state.get("human_action")
    if human_action:
        reviewer = state.get("human_reviewer_id", "anonymous_reviewer")
        comments = state.get("human_comments", "")
        logger.info(f"Gatekeeper: Resumed with human action '{human_action}' by {reviewer}")

        if human_action.upper() in ["APPROVE", "APPROVED"]:
            decision = "APPROVED"
        elif human_action.upper() in ["OVERRIDE", "OVERRIDDEN"]:
            decision = "OVERRIDDEN"
        else:
            decision = "REJECTED"

        return {
            "decision": decision,
            "requires_human_review": False,
            "messages": [f"Human review completed by {reviewer}: {decision}. Comments: '{comments}'"],
            "audit_trail": [{
                "step": "gatekeeper",
                "status": "HUMAN_RESOLVED",
                "decision": decision,
                "reviewer": reviewer,
                "comments": comments
            }]
        }

    # 2. Automated rule evaluation
    invoice = state.get("invoice")
    math_res = state.get("math_verification")
    match_res = state.get("match_result")
    risk_res = state.get("risk_assessment")
    policy_res = state.get("policy_evaluation")

    reasons_for_review = []
    auto_rejection_reasons = []

    # Check Math
    if math_res and not math_res.is_valid:
        reasons_for_review.append(f"Mathematical discrepancies found ({len(math_res.line_item_errors)} errors).")

    # Check Policy Compliance
    if policy_res and not policy_res.is_compliant:
        for v in policy_res.violations:
            if v.severity == SeverityLevel.CRITICAL:
                auto_rejection_reasons.append(f"Critical policy violation: {v.description}")
            else:
                reasons_for_review.append(f"Policy violation: {v.description}")

    # Check Approval Tier Limits
    if invoice and invoice.total_amount > settings.max_auto_approve_amount:
        reasons_for_review.append(
            f"Invoice total (${invoice.total_amount:,.2f}) exceeds auto-approval threshold (${settings.max_auto_approve_amount:,.2f})."
        )

    # Check PO Matching
    if match_res and match_res.status == MatchStatus.MISMATCH:
        reasons_for_review.append(f"PO matching discrepancies detected ({len(match_res.discrepancies)} line variances).")
    elif match_res and match_res.status == MatchStatus.PO_NOT_FOUND:
        reasons_for_review.append(f"Referenced PO #{match_res.po_number} could not be verified.")

    # Check Risk Assessment
    if risk_res:
        if risk_res.risk_level in [SeverityLevel.HIGH, SeverityLevel.CRITICAL] or risk_res.overall_risk_score >= 40.0:
            reasons_for_review.append(f"Elevated risk score ({risk_res.overall_risk_score}/100) triggered.")

    # Determine final outcome
    if auto_rejection_reasons:
        decision = "REJECTED"
        requires_human = False
        reason_summary = "; ".join(auto_rejection_reasons)
        log_msg = f"Auto-REJECTED by Gatekeeper: {reason_summary}"
    elif reasons_for_review:
        decision = "REQUIRES_REVIEW"
        requires_human = True
        reason_summary = "; ".join(reasons_for_review)
        log_msg = f"Routed to Human-in-the-Loop Review Queue: {reason_summary}"
    else:
        decision = "APPROVED"
        requires_human = False
        reason_summary = "All automated checks, arithmetic, policy rules, and risk thresholds satisfied."
        log_msg = "Straight-Through Processing (STP) AUTO-APPROVED by Gatekeeper."

    logger.info(f"Gatekeeper Result: decision={decision}, requires_human={requires_human}")

    return {
        "decision": decision,
        "requires_human_review": requires_human,
        "messages": [log_msg],
        "audit_trail": [{
            "step": "gatekeeper",
            "decision": decision,
            "requires_human_review": requires_human,
            "reason_summary": reason_summary
        }]
    }
