import pytest
from src.graph.workflow import finflow_app
from src.schemas.document import Invoice, VendorInfo, LineItem, PurchaseOrder


@pytest.mark.asyncio
async def test_workflow_happy_path_auto_approve():
    """Tests full pipeline run resulting in Straight-Through-Processing (STP) Auto-Approval."""
    raw_invoice = """
    Invoice: INV-2026-HAPPY
    Date: 2026-09-01
    Vendor: Cloud Tech Solutions
    Bank Account: US99887766
    PO: PO-HAPPY-01
    - Cloud Compute Standard | 4 x $500 = $2000
    Subtotal: $2000
    Tax: $200
    Total: $2200
    """
    po = PurchaseOrder(
        po_number="PO-HAPPY-01",
        po_date="2026-08-25",
        vendor_name="Cloud Tech Solutions",
        line_items=[
            LineItem(
                description="Cloud Compute Standard",
                quantity=4.0,
                unit_price=500.0,
                total_amount=2000.0
            )
        ],
        subtotal=2000.0,
        tax_amount=200.0,
        total_amount=2200.0
    )

    initial_state = {
        "document_id": "doc_happy_01",
        "thread_id": "th_happy_01",
        "raw_text": raw_invoice,
        "purchase_order": po,
        "messages": [],
        "audit_trail": [],
        "errors": []
    }

    config = {"configurable": {"thread_id": "th_happy_01"}}
    final_state = await finflow_app.ainvoke(initial_state, config=config)

    assert final_state["decision"] == "APPROVED"
    assert final_state["requires_human_review"] is False
    assert final_state["math_verification"].is_valid is True
    assert final_state["match_result"].status.value == "EXACT_MATCH"


@pytest.mark.asyncio
async def test_workflow_high_risk_hitl_interrupt():
    """Tests pipeline run for high-value invoice ($50k) triggering Human Review."""
    raw_invoice = """
    Invoice: INV-2026-EXPENSIVE
    Date: 2026-09-01
    Vendor: High Roller Enterprise
    Bank Account: US111222333
    - Supercomputer Cluster | 1 x $50000 = $50000
    Subtotal: $50000
    Tax: $5000
    Total: $55000
    """

    initial_state = {
        "document_id": "doc_exp_01",
        "thread_id": "th_exp_01",
        "raw_text": raw_invoice,
        "messages": [],
        "audit_trail": [],
        "errors": []
    }

    config = {"configurable": {"thread_id": "th_exp_01"}}
    state_after_run = await finflow_app.ainvoke(initial_state, config=config)

    assert state_after_run["requires_human_review"] is True
    assert state_after_run["decision"] == "REQUIRES_REVIEW"

    # Simulate Human In The Loop approval resumption
    resume_state = {
        "human_action": "APPROVE",
        "human_reviewer_id": "finance_director@corp.com",
        "human_comments": "Authorized under Q3 CapEx budget allocation."
    }
    final_state = await finflow_app.ainvoke(resume_state, config=config)

    assert final_state["decision"] == "APPROVED"
    assert final_state["requires_human_review"] is False
