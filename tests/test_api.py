import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from src.core.database import Base, get_db_session
from src.api.main import app

# Test database in memory
test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
db_session_factory = async_sessionmaker(bind=test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db_session():
    async with db_session_factory() as session:
        yield session


app.dependency_overrides[get_db_session] = override_get_db_session


@pytest.fixture(autouse=True)
async def setup_test_db():
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.mark.asyncio
async def test_health_check():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_ingest_and_review_lifecycle():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Ingest High Risk / High Amount Invoice (triggers review)
        payload = {
            "document_text": """
            Invoice: INV-TEST-API-99
            Date: 2026-09-01
            Vendor: Apex Cloud Systems
            Bank Account: US9876543210
            - Large Datacenter Hardware | 1 x $45000 = $45000
            Subtotal: $45000
            Tax: $4500
            Total: $49500
            """,
            "filename": "apex_invoice.txt"
        }

        resp = await client.post("/api/v1/ingest", json=payload)
        assert resp.status_code == 200
        data = resp.json()
        assert data["requires_human_review"] is True
        doc_id = data["document_id"]

        # 2. Check Review Queue
        queue_resp = await client.get("/api/v1/review/queue")
        assert queue_resp.status_code == 200
        queue_items = queue_resp.json()
        assert len(queue_items) >= 1
        task_id = queue_items[0]["task_id"]

        # 3. Submit Review Action
        action_payload = {
            "action": "APPROVE",
            "reviewer_id": "cfo@finflow.com",
            "comments": "Special CapEx approval granted."
        }
        action_resp = await client.post(f"/api/v1/review/{task_id}/action", json=action_payload)
        assert action_resp.status_code == 200
        assert action_resp.json()["decision"] == "APPROVED"

        # 4. Check Ledger History
        ledger_resp = await client.get("/api/v1/ledger/history")
        assert ledger_resp.status_code == 200
        blocks = ledger_resp.json()
        assert len(blocks) >= 2  # Pipeline run block + Human action block

        # 5. Verify Ledger Chain Integrity
        verify_resp = await client.get("/api/v1/ledger/verify")
        assert verify_resp.status_code == 200
        assert verify_resp.json()["is_valid"] is True
