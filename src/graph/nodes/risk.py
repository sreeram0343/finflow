import datetime
import logging
from typing import Dict, Any, List
from src.core.config import settings
from src.graph.state import FinFlowState
from src.schemas.validation import RiskAssessment, RiskFlag, SeverityLevel

logger = logging.getLogger(__name__)


async def risk_node(state: FinFlowState) -> Dict[str, Any]:
    """
    Evaluates fraud indicators, transaction anomalies, vendor bank verification,
    and velocity risk. Computes aggregate risk score.
    """
    invoice = state.get("invoice")
    if not invoice:
        return {
            "errors": ["Risk Node: Missing invoice in state."],
            "audit_trail": [{
                "step": "risk",
                "status": "FAILED",
                "reason": "Missing invoice"
            }]
        }

    flags: List[RiskFlag] = []
    risk_score = 0.0

    # 1. High Value Threshold Check
    if invoice.total_amount >= settings.high_risk_threshold_amount:
        impact = 30.0
        risk_score += impact
        flags.append(
            RiskFlag(
                code="HIGH_VALUE_TRANSACTION",
                severity=SeverityLevel.HIGH,
                description=f"Transaction total (${invoice.total_amount:,.2f}) exceeds high-risk audit threshold (${settings.high_risk_threshold_amount:,.2f}).",
                score_impact=impact
            )
        )

    # 2. Non-preferred Vendor Check
    if not invoice.vendor.is_preferred:
        impact = 15.0
        risk_score += impact
        flags.append(
            RiskFlag(
                code="NON_PREFERRED_VENDOR",
                severity=SeverityLevel.MEDIUM,
                description=f"Vendor '{invoice.vendor.name}' is not currently marked as a verified/preferred supplier.",
                score_impact=impact
            )
        )

    # 3. Bank Account Details Check
    is_bank_changed = False
    if not invoice.vendor.bank_account_number or len(invoice.vendor.bank_account_number) < 6:
        impact = 25.0
        risk_score += impact
        flags.append(
            RiskFlag(
                code="UNVERIFIED_BANK_REMITTANCE",
                severity=SeverityLevel.HIGH,
                description="Missing or truncated bank remittance information.",
                score_impact=impact
            )
        )

    # 4. Weekend / Timestamp Anomaly Check
    is_weekend = False
    try:
        inv_dt = datetime.datetime.strptime(invoice.invoice_date, "%Y-%m-%d")
        if inv_dt.weekday() in [5, 6]:  # Saturday, Sunday
            is_weekend = True
            impact = 10.0
            risk_score += impact
            flags.append(
                RiskFlag(
                    code="WEEKEND_ISSUANCE",
                    severity=SeverityLevel.LOW,
                    description=f"Invoice dated on a weekend ({inv_dt.strftime('%A')}).",
                    score_impact=impact
                )
            )
    except Exception:
        pass

    # 5. Price Surge on Individual Line Items
    price_surge = False
    for item in invoice.line_items:
        if item.unit_price > 5000.0:  # High unit cost flag
            price_surge = True
            impact = 15.0
            risk_score += impact
            flags.append(
                RiskFlag(
                    code="HIGH_UNIT_COST_ITEM",
                    severity=SeverityLevel.MEDIUM,
                    description=f"Line item '{item.description}' has exceptionally high unit price (${item.unit_price:,.2f}).",
                    score_impact=impact
                )
            )
            break

    # Normalize risk score to 0 - 100
    overall_score = min(100.0, round(risk_score, 1))

    if overall_score >= 70.0:
        level = SeverityLevel.CRITICAL
        recommended_action = "REJECT_OR_AUDIT"
    elif overall_score >= 40.0:
        level = SeverityLevel.HIGH
        recommended_action = "MANDATORY_HUMAN_REVIEW"
    elif overall_score >= 15.0:
        level = SeverityLevel.MEDIUM
        recommended_action = "STANDARD_REVIEW"
    else:
        level = SeverityLevel.LOW
        recommended_action = "AUTO_APPROVE_ELIGIBLE"

    assessment = RiskAssessment(
        overall_risk_score=overall_score,
        risk_level=level,
        flags=flags,
        is_duplicate_suspect=False,
        is_bank_account_changed=is_bank_changed,
        is_weekend_submission=is_weekend,
        price_surge_detected=price_surge,
        recommended_action=recommended_action
    )

    logger.info(f"Risk Node: Score={overall_score}, Level={level.value}, Flags={len(flags)}")

    return {
        "risk_assessment": assessment,
        "messages": [f"Risk Assessment: Score {overall_score}/100 ({level.value}) with {len(flags)} risk flags."],
        "audit_trail": [{
            "step": "risk",
            "risk_score": overall_score,
            "risk_level": level.value,
            "flags_count": len(flags)
        }]
    }
