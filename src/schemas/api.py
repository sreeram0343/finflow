import datetime
from typing import Optional, List, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field

from src.schemas.document import Invoice, PurchaseOrder
from src.schemas.validation import MatchResult, RiskAssessment, PolicyEvaluation, MathVerificationResult


class DocumentTypeEnum(str, Enum):
    INVOICE = "invoice"
    PURCHASE_ORDER = "purchase_order"
    RECEIPT = "receipt"


class ReviewActionEnum(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    OVERRIDE = "OVERRIDE"


class IngestRequest(BaseModel):
    document_text: Optional[str] = Field(None, description="Raw text or OCR output of document")
    filename: Optional[str] = Field(default="invoice.pdf", description="Original file name")
    file_url: Optional[str] = Field(None, description="S3 / MinIO location if pre-uploaded")
    po_reference: Optional[PurchaseOrder] = Field(None, description="Optional Purchase Order object for matching")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="Custom metadata tags")


class IngestResponse(BaseModel):
    document_id: str
    thread_id: str
    status: str
    decision: str
    total_amount: Optional[float] = None
    vendor_name: Optional[str] = None
    risk_score: Optional[float] = None
    requires_human_review: bool
    summary: str
    created_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)


class ReviewItemResponse(BaseModel):
    task_id: str
    document_id: str
    thread_id: str
    status: str
    invoice_number: Optional[str] = None
    vendor_name: Optional[str] = None
    total_amount: Optional[float] = None
    risk_score: float
    risk_flags: List[Dict[str, Any]] = Field(default_factory=list)
    policy_violations: List[Dict[str, Any]] = Field(default_factory=list)
    match_discrepancies: List[Dict[str, Any]] = Field(default_factory=list)
    math_verification: Optional[Dict[str, Any]] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime


class ReviewActionRequest(BaseModel):
    action: ReviewActionEnum = Field(..., description="APPROVE, REJECT, or OVERRIDE")
    reviewer_id: str = Field(..., description="ID / Email of reviewer making decision")
    comments: Optional[str] = Field(None, description="Audit notes or rationale")
    adjusted_amount: Optional[float] = Field(None, description="Corrected total if adjusting amount")


class ReviewActionResponse(BaseModel):
    task_id: str
    document_id: str
    thread_id: str
    status: str
    decision: str
    reviewer_id: str
    comments: Optional[str] = None
    updated_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    message: str


class LedgerBlockResponse(BaseModel):
    index: int
    timestamp: datetime.datetime
    document_id: Optional[str]
    thread_id: Optional[str]
    event_type: str
    agent_name: str
    payload_hash: str
    previous_hash: str
    block_hash: str
    state_snapshot: Dict[str, Any]


class LedgerVerifyResponse(BaseModel):
    is_valid: bool
    total_blocks: int
    verified_at: datetime.datetime = Field(default_factory=datetime.datetime.utcnow)
    details: str
