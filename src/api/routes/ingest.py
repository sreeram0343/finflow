import json
import uuid
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session, DocumentRecord, ReviewTaskRecord
from src.schemas.api import IngestRequest, IngestResponse
from src.schemas.document import PurchaseOrder
from src.services.storage import storage_service
from src.services.ledger import ledger_service
from src.graph.workflow import finflow_app

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ingest", tags=["Document Ingestion"])


@router.post("", response_model=IngestResponse)
async def ingest_document(
    request: IngestRequest,
    session: AsyncSession = Depends(get_db_session)
):
    """
    Ingests financial document text or structured payload and initiates the
    multi-agent validation, matching, risk, and policy pipeline.
    """
    document_id = f"doc_{uuid.uuid4().hex[:12]}"
    thread_id = f"th_{uuid.uuid4().hex[:12]}"
    file_bytes = (request.document_text or "").encode("utf-8")

    file_hash, file_url = await storage_service.upload_document(
        file_bytes=file_bytes,
        filename=request.filename or "invoice.txt",
        content_type="text/plain"
    )

    doc_record = DocumentRecord(
        id=document_id,
        filename=request.filename or "invoice.txt",
        file_hash=file_hash,
        file_url=file_url,
        doc_type="invoice",
        status="PROCESSING"
    )
    session.add(doc_record)
    await session.flush()

    # Initial state for LangGraph
    initial_state = {
        "document_id": document_id,
        "thread_id": thread_id,
        "raw_text": request.document_text,
        "file_url": file_url,
        "purchase_order": request.po_reference,
        "messages": [],
        "audit_trail": [],
        "errors": []
    }

    config = {"configurable": {"thread_id": thread_id}}

    try:
        final_state = await finflow_app.ainvoke(initial_state, config=config)
    except Exception as e:
        logger.error(f"Workflow execution failed: {e}", exc_info=True)
        doc_record.status = "FAILED"
        await session.commit()
        raise HTTPException(status_code=500, detail=f"Pipeline error: {str(e)}")

    invoice = final_state.get("invoice")
    decision = final_state.get("decision", "PENDING")
    requires_human = final_state.get("requires_human_review", False)
    risk_res = final_state.get("risk_assessment")

    # Update Document Record
    if invoice:
        doc_record.extracted_data = invoice.model_dump_json()

    if requires_human:
        doc_record.status = "REQUIRES_REVIEW"
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        review_task = ReviewTaskRecord(
            id=task_id,
            document_id=document_id,
            thread_id=thread_id,
            status="PENDING_REVIEW",
            risk_score=risk_res.overall_risk_score if risk_res else 0.0,
            risk_flags=json.dumps([f.model_dump() for f in risk_res.flags]) if risk_res else "[]",
            policy_violations=json.dumps([v.model_dump() for v in final_state.get("policy_evaluation").violations]) if final_state.get("policy_evaluation") else "[]",
            match_discrepancies=json.dumps([d.model_dump() for d in final_state.get("match_result").discrepancies]) if final_state.get("match_result") else "[]",
        )
        session.add(review_task)
    else:
        doc_record.status = decision

    # Record Immutable Ledger Block
    await ledger_service.record_event(
        session=session,
        event_type="PIPELINE_RUN_COMPLETED",
        agent_name="FinFlowWorkflow",
        state_snapshot={
            "document_id": document_id,
            "decision": decision,
            "requires_human_review": requires_human,
            "invoice_total": invoice.total_amount if invoice else None,
            "risk_score": risk_res.overall_risk_score if risk_res else None,
            "audit_trail": final_state.get("audit_trail", [])
        },
        document_id=document_id,
        thread_id=thread_id
    )

    await session.commit()

    summary_msg = final_state.get("messages", ["Processed successfully."])[-1]

    return IngestResponse(
        document_id=document_id,
        thread_id=thread_id,
        status=doc_record.status,
        decision=decision,
        total_amount=invoice.total_amount if invoice else None,
        vendor_name=invoice.vendor.name if invoice else None,
        risk_score=risk_res.overall_risk_score if risk_res else None,
        requires_human_review=requires_human,
        summary=summary_msg
    )


@router.post("/upload", response_model=IngestResponse)
async def upload_file_and_ingest(
    file: UploadFile = File(...),
    po_number: Optional[str] = Form(None),
    session: AsyncSession = Depends(get_db_session)
):
    """Multipart file upload endpoint for PDF, image, or text financial documents."""
    content_bytes = await file.read()
    text_content = content_bytes.decode("utf-8", errors="ignore")

    req = IngestRequest(
        document_text=text_content,
        filename=file.filename or "uploaded_invoice.pdf"
    )
    return await ingest_document(request=req, session=session)
