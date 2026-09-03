import json
import logging
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db_session
from src.schemas.api import LedgerBlockResponse, LedgerVerifyResponse
from src.services.ledger import ledger_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/ledger", tags=["Immutable Decision Ledger"])


@router.get("/history", response_model=List[LedgerBlockResponse])
async def get_ledger_history(
    document_id: Optional[str] = Query(None, description="Filter by Document ID"),
    thread_id: Optional[str] = Query(None, description="Filter by LangGraph Thread ID"),
    limit: int = Query(50, ge=1, le=500),
    session: AsyncSession = Depends(get_db_session)
):
    """Retrieves immutable audit blocks from the decision ledger."""
    records = await ledger_service.get_history(
        session=session,
        document_id=document_id,
        thread_id=thread_id,
        limit=limit
    )

    responses = []
    for r in records:
        try:
            snapshot = json.loads(r.state_snapshot)
        except Exception:
            snapshot = {"raw": r.state_snapshot}

        responses.append(
            LedgerBlockResponse(
                index=r.index,
                timestamp=r.timestamp,
                document_id=r.document_id,
                thread_id=r.thread_id,
                event_type=r.event_type,
                agent_name=r.agent_name,
                payload_hash=r.payload_hash,
                previous_hash=r.previous_hash,
                block_hash=r.block_hash,
                state_snapshot=snapshot
            )
        )

    return responses


@router.get("/verify", response_model=LedgerVerifyResponse)
async def verify_ledger_integrity(
    session: AsyncSession = Depends(get_db_session)
):
    """
    Performs full cryptographic audit of all blocks in the ledger,
    verifying sequential block hash integrity and tamper-evidence.
    """
    is_valid, total_blocks, details = await ledger_service.verify_chain_integrity(session)
    return LedgerVerifyResponse(
        is_valid=is_valid,
        total_blocks=total_blocks,
        details=details
    )
