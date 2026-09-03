import logging
from typing import Dict, Any, List
from src.core.config import settings
from src.graph.state import FinFlowState
from src.schemas.validation import MatchResult, MatchStatus, MatchDiscrepancy

logger = logging.getLogger(__name__)


async def match_node(state: FinFlowState) -> Dict[str, Any]:
    """
    Performs 2-way and 3-way matching between Invoice and Purchase Order records,
    evaluating quantity and unit price variance against corporate tolerance thresholds.
    """
    invoice = state.get("invoice")
    po = state.get("purchase_order")

    if not invoice:
        return {
            "errors": ["Match Node: Missing invoice in state."],
            "audit_trail": [{
                "step": "match",
                "status": "FAILED",
                "reason": "Missing invoice"
            }]
        }

    # Case 1: No PO provided or referenced
    if not po and not invoice.purchase_order_number:
        logger.info("Match Node: No PO referenced on invoice.")
        match_result = MatchResult(
            status=MatchStatus.NO_PO_REFERENCED,
            total_invoice_amount=invoice.total_amount,
            amount_variance=0.0,
            confidence=0.9
        )
        return {
            "match_result": match_result,
            "messages": ["No PO referenced on invoice; non-PO invoice processing flow."],
            "audit_trail": [{
                "step": "match",
                "status": "NO_PO_REFERENCED",
                "invoice_total": invoice.total_amount
            }]
        }

    # Case 2: PO referenced by number but not available in state database
    if not po and invoice.purchase_order_number:
        logger.warning(f"Match Node: PO #{invoice.purchase_order_number} referenced but PO data not supplied.")
        match_result = MatchResult(
            status=MatchStatus.PO_NOT_FOUND,
            po_number=invoice.purchase_order_number,
            total_invoice_amount=invoice.total_amount,
            amount_variance=invoice.total_amount,
            confidence=0.5
        )
        return {
            "match_result": match_result,
            "messages": [f"Purchase Order #{invoice.purchase_order_number} could not be retrieved from ERP."],
            "audit_trail": [{
                "step": "match",
                "status": "PO_NOT_FOUND",
                "po_number": invoice.purchase_order_number
            }]
        }

    # Case 3: Both Invoice and PO present -> Match reconciliation
    discrepancies: List[MatchDiscrepancy] = []
    price_tol = settings.price_variance_tolerance_pct
    qty_tol = settings.quantity_variance_tolerance_pct

    # Total Amount comparison
    amount_variance = round(invoice.total_amount - po.total_amount, 2)

    # Line Item matching
    # Map PO items by description or item_id
    po_items_map = {}
    for po_item in po.line_items:
        key = po_item.item_id.strip().lower() if po_item.item_id else po_item.description.strip().lower()
        po_items_map[key] = po_item

    for inv_item in invoice.line_items:
        key = inv_item.item_id.strip().lower() if inv_item.item_id else inv_item.description.strip().lower()
        matched_po_item = po_items_map.get(key)

        if not matched_po_item:
            # Try fallback matching by description substring
            for p_key, p_item in po_items_map.items():
                if p_key in key or key in p_key:
                    matched_po_item = p_item
                    break

        if not matched_po_item:
            discrepancies.append(
                MatchDiscrepancy(
                    item_id=inv_item.item_id,
                    description=inv_item.description,
                    po_qty=None,
                    inv_qty=inv_item.quantity,
                    po_unit_price=None,
                    inv_unit_price=inv_item.unit_price,
                    variance_pct=1.0,
                    reason="Line item present on invoice but missing from Purchase Order authorization."
                )
            )
            continue

        # Check Qty variance
        if matched_po_item.quantity > 0:
            qty_var = (inv_item.quantity - matched_po_item.quantity) / matched_po_item.quantity
            if qty_var > qty_tol:
                discrepancies.append(
                    MatchDiscrepancy(
                        item_id=inv_item.item_id,
                        description=inv_item.description,
                        po_qty=matched_po_item.quantity,
                        inv_qty=inv_item.quantity,
                        po_unit_price=matched_po_item.unit_price,
                        inv_unit_price=inv_item.unit_price,
                        variance_pct=round(qty_var * 100, 2),
                        reason=f"Billed quantity ({inv_item.quantity}) exceeds PO authorized quantity ({matched_po_item.quantity})."
                    )
                )

        # Check Unit Price variance
        if matched_po_item.unit_price > 0:
            price_var = (inv_item.unit_price - matched_po_item.unit_price) / matched_po_item.unit_price
            if price_var > price_tol:
                discrepancies.append(
                    MatchDiscrepancy(
                        item_id=inv_item.item_id,
                        description=inv_item.description,
                        po_qty=matched_po_item.quantity,
                        inv_qty=inv_item.quantity,
                        po_unit_price=matched_po_item.unit_price,
                        inv_unit_price=inv_item.unit_price,
                        variance_pct=round(price_var * 100, 2),
                        reason=f"Unit price (${inv_item.unit_price:.2f}) exceeds PO price (${matched_po_item.unit_price:.2f}) by {price_var*100:.1f}% (tolerance: {price_tol*100}%)."
                    )
                )

    if len(discrepancies) == 0 and abs(amount_variance) <= 0.01:
        match_status = MatchStatus.EXACT_MATCH
    elif len(discrepancies) == 0:
        match_status = MatchStatus.TOLERANCE_MATCH
    else:
        match_status = MatchStatus.MISMATCH

    match_result = MatchResult(
        status=match_status,
        po_number=po.po_number,
        total_po_amount=po.total_amount,
        total_invoice_amount=invoice.total_amount,
        amount_variance=amount_variance,
        discrepancies=discrepancies,
        confidence=1.0 if match_status in [MatchStatus.EXACT_MATCH, MatchStatus.TOLERANCE_MATCH] else 0.7
    )

    logger.info(f"Match Node completed: status={match_status}, {len(discrepancies)} discrepancies")

    return {
        "match_result": match_result,
        "messages": [f"Matching result with PO #{po.po_number}: {match_status.value} ({len(discrepancies)} discrepancies)"],
        "audit_trail": [{
            "step": "match",
            "status": match_status.value,
            "po_number": po.po_number,
            "discrepancies_count": len(discrepancies),
            "amount_variance": amount_variance
        }]
    }
