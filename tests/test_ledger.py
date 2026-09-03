import pytest
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.core.database import Base, LedgerBlockRecord
from src.services.ledger import DecisionLedgerService


@pytest.fixture
async def test_db_session():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session


@pytest.mark.asyncio
async def test_ledger_genesis_and_chaining(test_db_session):
    ledger = DecisionLedgerService()

    # 1. Record Block 0 (Genesis)
    b0 = await ledger.record_event(
        session=test_db_session,
        event_type="GENESIS",
        agent_name="SystemInit",
        state_snapshot={"msg": "Genesis block"},
        document_id="doc_0",
        thread_id="th_0"
    )
    assert b0.index == 0
    assert b0.previous_hash == "0" * 64

    # 2. Record Block 1
    b1 = await ledger.record_event(
        session=test_db_session,
        event_type="EXTRACTION_COMPLETED",
        agent_name="ExtractAgent",
        state_snapshot={"invoice_number": "INV-100", "total": 500.0},
        document_id="doc_0",
        thread_id="th_0"
    )
    assert b1.index == 1
    assert b1.previous_hash == b0.block_hash

    # 3. Record Block 2
    b2 = await ledger.record_event(
        session=test_db_session,
        event_type="GATEKEEPER_DECISION",
        agent_name="GatekeeperAgent",
        state_snapshot={"decision": "APPROVED"},
        document_id="doc_0",
        thread_id="th_0"
    )
    assert b2.index == 2
    assert b2.previous_hash == b1.block_hash

    # 4. Verify Integrity
    is_valid, count, msg = await ledger.verify_chain_integrity(test_db_session)
    assert is_valid is True
    assert count == 3


@pytest.mark.asyncio
async def test_ledger_tamper_detection(test_db_session):
    ledger = DecisionLedgerService()

    # Record 2 blocks
    b0 = await ledger.record_event(
        session=test_db_session,
        event_type="BLOCK_0",
        agent_name="Agent0",
        state_snapshot={"data": 100}
    )
    b1 = await ledger.record_event(
        session=test_db_session,
        event_type="BLOCK_1",
        agent_name="Agent1",
        state_snapshot={"data": 200}
    )

    # Tamper with Block 0 state_snapshot
    b0.state_snapshot = '{"data": 999999}'
    await test_db_session.flush()

    # Integrity check should detect tampering
    is_valid, count, msg = await ledger.verify_chain_integrity(test_db_session)
    assert is_valid is False
    assert "tampering detected" in msg.lower()
