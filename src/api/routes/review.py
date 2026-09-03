import json
import logging
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session, ReviewTaskRecord, DocumentRecord
from src.schemas.api import (
    ReviewItemResponse,
    ReviewActionRequest,
    ReviewActionResponse,
)
from src.services.ledger import ledger_service
from src.graph.workflow import finflow_app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/review", tags=["Human-in-the-Loop Review"])


@router.get("/queue", response_model=List[ReviewItemResponse])
async def get_pending_review_queue(
    session: AsyncSession = Depends(get_db_session)
):
    """Retrieves all pending review tasks requiring human oversight."""
    query = select(ReviewTaskRecord).where(ReviewTaskRecord.status == "PENDING_REVIEW").order_by(ReviewTaskRecord.created_at.desc())
    result = await session.execute(query)
    tasks = result.scalars().all()

    items = []
    for t in tasks:
        # Load associated document
        doc_res = await session.execute(select(DocumentRecord).where(DocumentRecord.id == t.document_id))
        doc = doc_res.scalars().first()

        inv_data = json.loads(doc.extracted_data) if (doc and doc.extracted_data) else {}
        items.append(
            ReviewItemResponse(
                task_id=t.id,
                document_id=t.document_id,
                thread_id=t.thread_id,
                status=t.status,
                invoice_number=inv_data.get("invoice_number"),
                vendor_name=inv_data.get("vendor", {}).get("name") if isinstance(inv_data.get("vendor"), dict) else None,
                total_amount=inv_data.get("total_amount"),
                risk_score=t.risk_score,
                risk_flags=json.loads(t.risk_flags) if t.risk_flags else [],
                policy_violations=json.loads(t.policy_violations) if t.policy_violations else [],
                match_discrepancies=json.loads(t.match_discrepancies) if t.match_discrepancies else [],
                created_at=t.created_at,
                updated_at=t.updated_at
            )
        )

    return items


@router.get("/{task_id}", response_model=ReviewItemResponse)
async def get_review_task(
    task_id: str,
    session: AsyncSession = Depends(get_db_session)
):
    """Fetches full discrepancy inspection details for a specific review task."""
    result = await session.execute(select(ReviewTaskRecord).where(ReviewTaskRecord.id == task_id))
    t = result.scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="Review task not found.")

    doc_res = await session.execute(select(DocumentRecord).where(DocumentRecord.id == t.document_id))
    doc = doc_res.scalars().first()
    inv_data = json.loads(doc.extracted_data) if (doc and doc.extracted_data) else {}

    return ReviewItemResponse(
        task_id=t.id,
        document_id=t.document_id,
        thread_id=t.thread_id,
        status=t.status,
        invoice_number=inv_data.get("invoice_number"),
        vendor_name=inv_data.get("vendor", {}).get("name") if isinstance(inv_data.get("vendor"), dict) else None,
        total_amount=inv_data.get("total_amount"),
        risk_score=t.risk_score,
        risk_flags=json.loads(t.risk_flags) if t.risk_flags else [],
        policy_violations=json.loads(t.policy_violations) if t.policy_violations else [],
        match_discrepancies=json.loads(t.match_discrepancies) if t.match_discrepancies else [],
        created_at=t.created_at,
        updated_at=t.updated_at
    )


@router.post("/{task_id}/action", response_model=ReviewActionResponse)
async def submit_review_action(
    task_id: str,
    action_req: ReviewActionRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Submits human decision (APPROVE, REJECT, or OVERRIDE) and resumes
    the LangGraph workflow to finalize ledger auditing.
    """
    result = await session.execute(select(ReviewTaskRecord).where(ReviewTaskRecord.id == task_id))
    task = result.scalars().first()
    if not task:
        raise HTTPException(status_code=404, detail="Review task not found.")

    if task.status != "PENDING_REVIEW":
        raise HTTPException(status_code=400, detail=f"Task already resolved with status '{task.status}'")

    doc_res = await session.execute(select(DocumentRecord).where(DocumentRecord.id == task.document_id))
    doc = doc_res.scalars().first()

    # Determine resolution decision
    action_str = action_req.action.value
    if action_str == "APPROVE":
        final_decision = "APPROVED"
    elif action_str == "OVERRIDE":
        final_decision = "OVERRIDDEN"
    else:
        final_decision = "REJECTED"

    task.status = final_decision
    task.decision = final_decision
    task.reviewed_by = action_req.reviewer_id
    task.comments = action_req.comments
    if doc:
        doc.status = final_decision

    # Resume LangGraph execution
    config = {"configurable": {"thread_id": task.thread_id}}
    try:
        await finflow_app.ainvoke(
            {
                "human_action": action_str,
                "human_reviewer_id": action_req.reviewer_id,
                "human_comments": action_req.comments,
                "adjusted_amount": action_req.adjusted_amount
            },
            config=config
        )
    except Exception as e:
        logger.warning(f"Graph resumption warning: {e}")

    # Record Immutable Ledger Block for human signoff
    await ledger_service.record_event(
        session=session,
        event_type="HUMAN_REVIEW_DECISION",
        agent_name=f"HumanReviewer:{action_req.reviewer_id}",
        state_snapshot={
            "task_id": task_id,
            "document_id": task.document_id,
            "action": action_str,
            "final_decision": final_decision,
            "reviewer_id": action_req.reviewer_id,
            "comments": action_req.comments,
            "adjusted_amount": action_req.adjusted_amount
        },
        document_id=task.document_id,
        thread_id=task.thread_id
    )

    await session.commit()

    return ReviewActionResponse(
        task_id=task.id,
        document_id=task.document_id,
        thread_id=task.thread_id,
        status=task.status,
        decision=final_decision,
        reviewer_id=action_req.reviewer_id,
        comments=action_req.comments,
        message=f"Review completed: Document #{task.document_id} marked as {final_decision}."
    )
