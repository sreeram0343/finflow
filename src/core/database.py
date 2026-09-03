import datetime
import json
from typing import AsyncGenerator, Any
from sqlalchemy import Column, String, Integer, Float, DateTime, Text, Boolean, ForeignKey
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship

from src.core.config import settings

# Engine & Session Setup
engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True
)

async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

Base = declarative_base()


class DocumentRecord(Base):
    __tablename__ = "documents"

    id = Column(String(64), primary_key=True, index=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)
    file_url = Column(String(512), nullable=True)
    doc_type = Column(String(50), default="invoice")
    status = Column(String(50), default="PENDING", index=True)  # PENDING, PROCESSING, APPROVED, REJECTED, REQUIRES_REVIEW
    extracted_data = Column(Text, nullable=True)  # JSON string
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    # Relationships
    reviews = relationship("ReviewTaskRecord", back_populates="document", cascade="all, delete-orphan")
    ledger_entries = relationship("LedgerBlockRecord", back_populates="document", cascade="all, delete-orphan")


class ReviewTaskRecord(Base):
    __tablename__ = "review_tasks"

    id = Column(String(64), primary_key=True, index=True)
    document_id = Column(String(64), ForeignKey("documents.id"), nullable=False, index=True)
    thread_id = Column(String(64), nullable=False, index=True)
    status = Column(String(50), default="PENDING_REVIEW", index=True)  # PENDING_REVIEW, APPROVED, REJECTED, OVERRIDDEN
    risk_score = Column(Float, default=0.0)
    risk_flags = Column(Text, nullable=True)  # JSON array
    policy_violations = Column(Text, nullable=True)  # JSON array
    match_discrepancies = Column(Text, nullable=True)  # JSON array
    decision = Column(String(50), nullable=True)
    reviewed_by = Column(String(100), nullable=True)
    comments = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.datetime.utcnow, onupdate=datetime.datetime.utcnow)

    document = relationship("DocumentRecord", back_populates="reviews")


class LedgerBlockRecord(Base):
    __tablename__ = "ledger_blocks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    index = Column(Integer, unique=True, index=True, nullable=False)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow, nullable=False)
    document_id = Column(String(64), ForeignKey("documents.id"), nullable=True, index=True)
    thread_id = Column(String(64), nullable=True, index=True)
    event_type = Column(String(100), nullable=False, index=True)
    agent_name = Column(String(100), nullable=False)
    payload_hash = Column(String(64), nullable=False)
    previous_hash = Column(String(64), nullable=False)
    block_hash = Column(String(64), unique=True, nullable=False, index=True)
    state_snapshot = Column(Text, nullable=False)  # JSON string

    document = relationship("DocumentRecord", back_populates="ledger_entries")


async def init_db() -> None:
    """Initialize database tables."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Dependency for providing database session to FastAPI routes."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
