import pytest
from src.schemas.document import Invoice, VendorInfo, LineItem, PurchaseOrder, PaymentDetails
from src.schemas.validation import MatchStatus, SeverityLevel
from src.graph.nodes import (
    extract_node,
    verify_node,
    match_node,
    risk_node,
    policy_node,
    gatekeeper_node
)


@pytest.fixture
def sample_invoice():
    return Invoice(
        invoice_number="INV-2026-101",
        invoice_date="2026-09-01",
        vendor=VendorInfo(
            name="Acme Tech Supplies",
            bank_account_number="US987654321",
            is_preferred=True
        ),
        line_items=[
            LineItem(
                description="Server Rack Units",
                quantity=2.0,
                unit_price=1000.0,
                total_amount=2000.0
            ),
            LineItem(
                description="Network Switch",
                quantity=1.0,
                unit_price=500.0,
                total_amount=500.0
            )
        ],
        subtotal=2500.0,
        tax_amount=250.0,
        discount_amount=0.0,
        total_amount=2750.0,
        purchase_order_number="PO-7700",
        expense_category="IT Equipment"
    )


@pytest.fixture
def sample_po():
    return PurchaseOrder(
        po_number="PO-7700",
        po_date="2026-08-25",
        vendor_name="Acme Tech Supplies",
        line_items=[
            LineItem(
                description="Server Rack Units",
                quantity=2.0,
                unit_price=1000.0,
                total_amount=2000.0
            ),
            LineItem(
                description="Network Switch",
                quantity=1.0,
                unit_price=500.0,
                total_amount=500.0
            )
        ],
        subtotal=2500.0,
        tax_amount=250.0,
        total_amount=2750.0
    )


@pytest.mark.asyncio
async def test_extract_node_with_text():
    raw_text = """
    Invoice: INV-9901
    Date: 2026-09-02
    Vendor: Global Logistics Ltd
    Bank Account: US11223344
    - Courier Shipping | 5 x $100 = $500
    Subtotal: $500
    Tax: $50
    Total: $550
    """
    state = {
        "document_id": "doc_test_1",
        "raw_text": raw_text,
        "messages": [],
        "audit_trail": [],
        "errors": []
    }
    result = await extract_node(state)
    assert "invoice" in result
    assert result["invoice"].invoice_number == "INV-9901"
    assert result["invoice"].total_amount == 550.0


@pytest.mark.asyncio
async def test_verify_node_valid(sample_invoice):
    state = {
        "document_id": "doc_test_2",
        "invoice": sample_invoice,
        "messages": [],
        "audit_trail": []
    }
    result = await verify_node(state)
    assert result["math_verification"].is_valid is True
    assert result["math_verification"].calculated_total == 2750.0


@pytest.mark.asyncio
async def test_verify_node_math_mismatch(sample_invoice):
    # Corrupt subtotal
    corrupt_inv = sample_invoice.model_copy()
    corrupt_inv.total_amount = 3999.00
    state = {
        "document_id": "doc_test_3",
        "invoice": corrupt_inv,
        "messages": [],
        "audit_trail": []
    }
    result = await verify_node(state)
    assert result["math_verification"].is_valid is False
    assert len(result["math_verification"].line_item_errors) > 0


@pytest.mark.asyncio
async def test_match_node_exact(sample_invoice, sample_po):
    state = {
        "invoice": sample_invoice,
        "purchase_order": sample_po,
        "messages": [],
        "audit_trail": []
    }
    result = await match_node(state)
    assert result["match_result"].status == MatchStatus.EXACT_MATCH
    assert len(result["match_result"].discrepancies) == 0


@pytest.mark.asyncio
async def test_match_node_price_mismatch(sample_invoice, sample_po):
    # Change PO price
    mismatch_po = sample_po.model_copy(deep=True)
    mismatch_po.line_items[0].unit_price = 500.0  # Invoice billed at 1000.0 (100% variance)

    state = {
        "invoice": sample_invoice,
        "purchase_order": mismatch_po,
        "messages": [],
        "audit_trail": []
    }
    result = await match_node(state)
    assert result["match_result"].status == MatchStatus.MISMATCH
    assert len(result["match_result"].discrepancies) > 0


@pytest.mark.asyncio
async def test_risk_node_scoring(sample_invoice):
    # High value & non-preferred
    risky_inv = sample_invoice.model_copy(deep=True)
    risky_inv.total_amount = 45000.0
    risky_inv.vendor.is_preferred = False
    risky_inv.vendor.bank_account_number = None

    state = {
        "invoice": risky_inv,
        "messages": [],
        "audit_trail": []
    }
    result = await risk_node(state)
    risk_assessment = result["risk_assessment"]
    assert risk_assessment.overall_risk_score >= 50.0
    assert risk_assessment.risk_level in [SeverityLevel.HIGH, SeverityLevel.CRITICAL]


@pytest.mark.asyncio
async def test_policy_node_prohibited_category(sample_invoice):
    prohibited_inv = sample_invoice.model_copy(deep=True)
    prohibited_inv.expense_category = "Cryptocurrency & Speculation"

    state = {
        "invoice": prohibited_inv,
        "messages": [],
        "audit_trail": []
    }
    result = await policy_node(state)
    assert result["policy_evaluation"].is_compliant is False
    assert len(result["policy_evaluation"].violations) > 0


@pytest.mark.asyncio
async def test_gatekeeper_stp_auto_approve(sample_invoice, sample_po):
    from src.schemas.validation import MathVerificationResult, MatchResult, RiskAssessment, PolicyEvaluation
    state = {
        "invoice": sample_invoice,
        "math_verification": MathVerificationResult(
            is_valid=True,
            calculated_subtotal=2500.0,
            reported_subtotal=2500.0,
            calculated_total=2750.0,
            reported_total=2750.0
        ),
        "match_result": MatchResult(
            status=MatchStatus.EXACT_MATCH,
            total_invoice_amount=2750.0
        ),
        "risk_assessment": RiskAssessment(
            overall_risk_score=5.0,
            risk_level=SeverityLevel.LOW
        ),
        "policy_evaluation": PolicyEvaluation(
            is_compliant=True,
            approval_tier_required="TIER_1_STANDARD"
        ),
        "messages": [],
        "audit_trail": []
    }
    result = await gatekeeper_node(state)
    assert result["decision"] == "APPROVED"
    assert result["requires_human_review"] is False
