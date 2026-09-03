import datetime
import hashlib
import json
import logging
from typing import List, Dict, Any, Optional, Tuple
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import LedgerBlockRecord

logger = logging.getLogger(__name__)


class DecisionLedgerService:
    """
    Immutable Decision Ledger implementing cryptographic SHA-256 block chaining
    for auditability, regulatory compliance, and tamper-detection.
    """

    @staticmethod
    def compute_sha256(data: str) -> str:
        return hashlib.sha256(data.encode("utf-8")).hexdigest()

    @staticmethod
    def compute_block_hash(
        index: int,
        timestamp_str: str,
        previous_hash: str,
        payload_hash: str,
        agent_name: str,
        event_type: str
    ) -> str:
        raw_header = f"{index}|{timestamp_str}|{previous_hash}|{payload_hash}|{agent_name}|{event_type}"
        return hashlib.sha256(raw_header.encode("utf-8")).hexdigest()

    async def record_event(
        self,
        session: AsyncSession,
        event_type: str,
        agent_name: str,
        state_snapshot: Dict[str, Any],
        document_id: Optional[str] = None,
        thread_id: Optional[str] = None
    ) -> LedgerBlockRecord:
        """Appends a new cryptographically chained audit block to the ledger."""
        # Retrieve latest block for chaining
        query = select(LedgerBlockRecord).order_by(LedgerBlockRecord.index.desc()).limit(1)
        result = await session.execute(query)
        latest_block = result.scalars().first()

        now = datetime.datetime.utcnow()
        timestamp_str = now.isoformat()

        if latest_block is None:
            # Genesis Block
            index = 0
            previous_hash = "0" * 64
        else:
            index = latest_block.index + 1
            previous_hash = latest_block.block_hash

        # Serialize payload cleanly
        snapshot_json = json.dumps(state_snapshot, sort_keys=True, default=str)
        payload_hash = self.compute_sha256(snapshot_json)
        block_hash = self.compute_block_hash(
            index=index,
            timestamp_str=timestamp_str,
            previous_hash=previous_hash,
            payload_hash=payload_hash,
            agent_name=agent_name,
            event_type=event_type
        )

        record = LedgerBlockRecord(
            index=index,
            timestamp=now,
            document_id=document_id,
            thread_id=thread_id,
            event_type=event_type,
            agent_name=agent_name,
            payload_hash=payload_hash,
            previous_hash=previous_hash,
            block_hash=block_hash,
            state_snapshot=snapshot_json
        )

        session.add(record)
        await session.flush()
        logger.info(f"Immutable Ledger Block #{index} ({event_type}) recorded with hash {block_hash[:12]}...")
        return record

    async def get_history(
        self,
        session: AsyncSession,
        document_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        limit: int = 100
    ) -> List[LedgerBlockRecord]:
        """Retrieves audit blocks filtered by document or thread."""
        query = select(LedgerBlockRecord)
        if document_id:
            query = query.where(LedgerBlockRecord.document_id == document_id)
        if thread_id:
            query = query.where(LedgerBlockRecord.thread_id == thread_id)

        query = query.order_by(LedgerBlockRecord.index.asc()).limit(limit)
        result = await session.execute(query)
        return list(result.scalars().all())

    async def verify_chain_integrity(self, session: AsyncSession) -> Tuple[bool, int, str]:
        """
        Validates all blocks in sequence, ensuring previous_hash links
        and payload hashes have not been altered.
        """
        query = select(LedgerBlockRecord).order_by(LedgerBlockRecord.index.asc())
        result = await session.execute(query)
        blocks = list(result.scalars().all())

        if not blocks:
            return True, 0, "Ledger is empty (valid)."

        expected_prev_hash = "0" * 64

        for i, block in enumerate(blocks):
            # 1. Verify index sequence
            if block.index != i:
                return False, len(blocks), f"Index mismatch at block ID {block.id}: expected {i}, got {block.index}"

            # 2. Verify previous hash link
            if block.previous_hash != expected_prev_hash:
                return False, len(blocks), f"Chain break at block index {block.index}: expected previous_hash {expected_prev_hash}, got {block.previous_hash}"

            # 3. Verify payload hash
            actual_payload_hash = self.compute_sha256(block.state_snapshot)
            if actual_payload_hash != block.payload_hash:
                return False, len(blocks), f"Payload tampering detected in block index {block.index}"

            # 4. Verify block header hash
            recalculated_block_hash = self.compute_block_hash(
                index=block.index,
                timestamp_str=block.timestamp.isoformat(),
                previous_hash=block.previous_hash,
                payload_hash=block.payload_hash,
                agent_name=block.agent_name,
                event_type=block.event_type
            )
            if recalculated_block_hash != block.block_hash:
                return False, len(blocks), f"Block hash tampering detected in block index {block.index}"

            expected_prev_hash = block.block_hash

        return True, len(blocks), f"All {len(blocks)} blocks cryptographically verified and intact."


ledger_service = DecisionLedgerService()
