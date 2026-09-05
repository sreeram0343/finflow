import operator
from typing import Annotated, Any, Dict, List, Optional
from typing_extensions import TypedDict
from src.schemas.invoice import ExtractedInvoice

class RiskFlag(TypedDict):
    severity: str  # "LOW", "MEDIUM", "HIGH", "CRITICAL"
    code: str      # e.g., "BANK_ACCOUNT_MISMATCH", "DUPLICATE_INVOICE"
    description: str
    evidence: Dict[str, Any]

class DecisionLedgerEntry(TypedDict):
    step: str
    timestamp: str
    agent: str
    status: str
    rationale: str
    metadata: Dict[str, Any]

class InvoiceState(TypedDict):
    """
    The shared state dictionary passed between all nodes in the LangGraph workflow.
    """
    # Raw Inputs
    invoice_id: str
    file_path: str
    
    # Extracted & Verified Data
    extracted_data: Optional[ExtractedInvoice]
    vendor_verified: bool
    vendor_id: Optional[str]
    
    # Reconciliation
    po_matched: bool
    # operator.add ensures nodes append to the list rather than overwrite it
    matching_discrepancies: Annotated[List[str], operator.add]
    
    # Risk & Policy
    risk_score: float  # 0.0 to 1.0
    risk_flags: Annotated[List[RiskFlag], operator.add]
    policy_passed: bool
    policy_failures: Annotated[List[str], operator.add]
    
    # Workflow Control
    status: str  # "PROCESSING", "PENDING_REVIEW", "AUTO_APPROVED", "REJECTED"
    human_decision: Optional[str]  # Populated when resuming from an interrupt()
    human_notes: Optional[str]
    
    # Traceability
    audit_trail: Annotated[List[DecisionLedgerEntry], operator.add]