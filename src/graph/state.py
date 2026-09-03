import operator
from typing import TypedDict, Optional, List, Dict, Any, Annotated
from pydantic import BaseModel

from src.schemas.document import Invoice, PurchaseOrder
from src.schemas.validation import (
    MathVerificationResult,
    MatchResult,
    RiskAssessment,
    PolicyEvaluation
)


class FinFlowState(TypedDict, total=False):
    # Identifiers
    document_id: str
    thread_id: str
    
    # Input payloads
    raw_text: Optional[str]
    file_url: Optional[str]
    
    # Extracted data
    invoice: Optional[Invoice]
    purchase_order: Optional[PurchaseOrder]
    
    # Agent Analysis Results
    math_verification: Optional[MathVerificationResult]
    match_result: Optional[MatchResult]
    risk_assessment: Optional[RiskAssessment]
    policy_evaluation: Optional[PolicyEvaluation]
    
    # Routing & Gatekeeper decisions
    decision: str  # "PENDING", "APPROVED", "REJECTED", "REQUIRES_REVIEW", "OVERRIDDEN"
    requires_human_review: bool
    review_task_id: Optional[str]
    
    # Human In The Loop inputs
    human_action: Optional[str]  # "APPROVE", "REJECT", "OVERRIDE"
    human_reviewer_id: Optional[str]
    human_comments: Optional[str]
    adjusted_amount: Optional[float]
    
    # Channeled list accumulators
    audit_trail: Annotated[List[Dict[str, Any]], operator.add]
    messages: Annotated[List[str], operator.add]
    errors: Annotated[List[str], operator.add]
