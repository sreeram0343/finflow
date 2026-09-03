import logging
from typing import Dict, Any, List
from src.core.config import settings
from src.graph.state import FinFlowState
from src.schemas.validation import PolicyEvaluation, PolicyViolation, SeverityLevel

logger = logging.getLogger(__name__)


async def policy_node(state: FinFlowState) -> Dict[str, Any]:
    """
    Enforces corporate spend governance rules, approval authority tiers,
    restricted expense categories, and dual-signatory mandates.
    """
    invoice = state.get("invoice")
    if not invoice:
        return {
            "errors": ["Policy Node: Missing invoice in state."],
            "audit_trail": [{
                "step": "policy",
                "status": "FAILED",
                "reason": "Missing invoice"
            }]
        }

    violations: List[PolicyViolation] = []
    notes: List[str] = []

    # 1. Approval Authority Tier Mapping
    total = invoice.total_amount
    if total <= settings.max_auto_approve_amount:
        tier = "TIER_1_STANDARD"
        requires_two_signatories = False
        notes.append(f"Amount (${total:,.2f}) within Tier 1 limit (${settings.max_auto_approve_amount:,.2f}).")
    elif total <= settings.high_risk_threshold_amount:
        tier = "TIER_2_DIRECTOR"
        requires_two_signatories = False
        notes.append(f"Amount (${total:,.2f}) requires Tier 2 (Director) authorization.")
    else:
        tier = "TIER_3_EXECUTIVE"
        requires_two_signatories = True
        notes.append(f"Amount (${total:,.2f}) exceeds $25,000; requires Tier 3 Executive authorization and dual sign-off.")

    # 2. Restricted Expense Category Verification
    category_allowed = True
    category = invoice.expense_category or ""
    for restricted in settings.restricted_categories:
        if restricted.lower() in category.lower():
            category_allowed = False
            violations.append(
                PolicyViolation(
                    rule_id="POL-001",
                    rule_name="RESTRICTED_EXPENSE_CATEGORY",
                    severity=SeverityLevel.CRITICAL,
                    threshold="Non-restricted corporate expenses only",
                    actual_value=category,
                    description=f"Transaction categorized under restricted expense category: '{category}'."
                )
            )

    # Check line item descriptions for prohibited terms
    for item in invoice.line_items:
        for restricted in settings.restricted_categories:
            if restricted.lower() in item.description.lower():
                category_allowed = False
                violations.append(
                    PolicyViolation(
                        rule_id="POL-002",
                        rule_name="PROHIBITED_ITEM_DESCRIPTION",
                        severity=SeverityLevel.HIGH,
                        threshold="No restricted goods",
                        actual_value=item.description,
                        description=f"Line item '{item.description}' matches restricted category rule '{restricted}'."
                    )
                )

    is_compliant = len(violations) == 0

    evaluation = PolicyEvaluation(
        is_compliant=is_compliant,
        violations=violations,
        approval_tier_required=tier,
        requires_two_signatories=requires_two_signatories,
        category_allowed=category_allowed,
        notes=notes
    )

    logger.info(f"Policy Node: compliant={is_compliant}, Tier={tier}, Violations={len(violations)}")

    return {
        "policy_evaluation": evaluation,
        "messages": [f"Policy Evaluation: {'COMPLIANT' if is_compliant else 'NON-COMPLIANT'} (Authority: {tier}, {len(violations)} violations)"],
        "audit_trail": [{
            "step": "policy",
            "is_compliant": is_compliant,
            "approval_tier": tier,
            "violations_count": len(violations)
        }]
    }
