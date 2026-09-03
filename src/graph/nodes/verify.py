import logging
from typing import Dict, Any
from src.graph.state import FinFlowState
from src.schemas.validation import MathVerificationResult

logger = logging.getLogger(__name__)


async def verify_node(state: FinFlowState) -> Dict[str, Any]:
    """
    Performs deterministic mathematical and arithmetic verification on invoice line items,
    subtotals, taxes, discounts, and final totals.
    """
    invoice = state.get("invoice")
    if not invoice:
        return {
            "errors": ["Cannot run verification: No invoice object found in state."],
            "decision": "REJECTED",
            "audit_trail": [{
                "step": "verify",
                "status": "FAILED",
                "reason": "Missing invoice"
            }]
        }

    line_item_errors = []
    notes = []
    calculated_subtotal = 0.0

    # 1. Line Item Verification
    for idx, item in enumerate(invoice.line_items):
        expected_line_total = round(item.quantity * item.unit_price, 2)
        diff = abs(expected_line_total - item.total_amount)
        if diff > 0.01:
            line_item_errors.append(
                f"Line {idx + 1} ('{item.description}'): qty ({item.quantity}) * unit_price (${item.unit_price:.2f}) = ${expected_line_total:.2f}, but reported ${item.total_amount:.2f} (diff: ${diff:.2f})"
            )
        calculated_subtotal += item.total_amount

    calculated_subtotal = round(calculated_subtotal, 2)
    subtotal_delta = round(abs(calculated_subtotal - invoice.subtotal), 2)
    if subtotal_delta > 0.01:
        line_item_errors.append(
            f"Subtotal mismatch: Sum of line items is ${calculated_subtotal:,.2f}, but invoice reports subtotal ${invoice.subtotal:,.2f} (diff: ${subtotal_delta:,.2f})"
        )

    # 2. Tax & Total Verification
    calculated_total = round(invoice.subtotal + invoice.tax_amount - invoice.discount_amount, 2)
    total_delta = round(abs(calculated_total - invoice.total_amount), 2)
    if total_delta > 0.01:
        line_item_errors.append(
            f"Grand total mismatch: Subtotal (${invoice.subtotal:,.2f}) + Tax (${invoice.tax_amount:,.2f}) - Discount (${invoice.discount_amount:,.2f}) = ${calculated_total:,.2f}, but invoice reports ${invoice.total_amount:,.2f} (diff: ${total_delta:,.2f})"
        )

    # Tax sanity check
    tax_check_passed = True
    if invoice.tax_amount < 0:
        tax_check_passed = False
        line_item_errors.append("Negative tax amount reported.")

    is_valid = len(line_item_errors) == 0

    if is_valid:
        notes.append("All arithmetic and tax calculations passed with zero discrepancy.")
    else:
        notes.append(f"Found {len(line_item_errors)} mathematical discrepancies.")

    result = MathVerificationResult(
        is_valid=is_valid,
        calculated_subtotal=calculated_subtotal,
        reported_subtotal=invoice.subtotal,
        subtotal_delta=subtotal_delta,
        calculated_total=calculated_total,
        reported_total=invoice.total_amount,
        total_delta=total_delta,
        line_item_errors=line_item_errors,
        tax_check_passed=tax_check_passed,
        notes=notes
    )

    log_msg = "Math verification PASSED" if is_valid else f"Math verification FAILED with {len(line_item_errors)} errors"
    logger.info(f"Verify Node: {log_msg}")

    return {
        "math_verification": result,
        "messages": [log_msg],
        "audit_trail": [{
            "step": "verify",
            "is_valid": is_valid,
            "calculated_total": calculated_total,
            "reported_total": invoice.total_amount,
            "error_count": len(line_item_errors)
        }]
    }
