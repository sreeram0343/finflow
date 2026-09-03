from typing import List, Optional
from enum import Enum
from pydantic import BaseModel, Field


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class MathVerificationResult(BaseModel):
    is_valid: bool = Field(..., description="Whether mathematical arithmetic is fully consistent")
    calculated_subtotal: float = Field(..., description="Calculated sum of all line item totals")
    reported_subtotal: float = Field(..., description="Subtotal reported on invoice document")
    subtotal_delta: float = Field(default=0.0, description="Difference between reported and calculated subtotal")
    calculated_total: float = Field(..., description="Subtotal + Tax - Discounts calculated")
    reported_total: float = Field(..., description="Total amount reported on invoice")
    total_delta: float = Field(default=0.0, description="Difference between reported and calculated total")
    line_item_errors: List[str] = Field(default_factory=list, description="Specific line items with calculation mismatches")
    tax_check_passed: bool = Field(default=True, description="Whether tax arithmetic checks passed")
    notes: List[str] = Field(default_factory=list, description="General observations")


class MatchStatus(str, Enum):
    EXACT_MATCH = "EXACT_MATCH"
    TOLERANCE_MATCH = "TOLERANCE_MATCH"
    MISMATCH = "MISMATCH"
    PO_NOT_FOUND = "PO_NOT_FOUND"
    NO_PO_REFERENCED = "NO_PO_REFERENCED"


class MatchDiscrepancy(BaseModel):
    item_id: Optional[str] = None
    description: str
    po_qty: Optional[float] = None
    inv_qty: float
    po_unit_price: Optional[float] = None
    inv_unit_price: float
    variance_pct: float
    reason: str


class MatchResult(BaseModel):
    status: MatchStatus = Field(..., description="Overall reconciliation outcome")
    po_number: Optional[str] = None
    total_po_amount: Optional[float] = None
    total_invoice_amount: float
    amount_variance: float = Field(default=0.0, description="Difference between invoice and PO total")
    discrepancies: List[MatchDiscrepancy] = Field(default_factory=list, description="Line item mismatches")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class RiskFlag(BaseModel):
    code: str = Field(..., description="Identifier code for risk rule (e.g. DUP_INV, PRICE_SPIKE)")
    severity: SeverityLevel = Field(..., description="Severity classification")
    description: str = Field(..., description="Human-readable explanation of risk trigger")
    score_impact: float = Field(default=10.0, description="Points added to overall risk score")


class RiskAssessment(BaseModel):
    overall_risk_score: float = Field(..., ge=0.0, le=100.0, description="Combined risk score (0-100)")
    risk_level: SeverityLevel = Field(..., description="Risk tier")
    flags: List[RiskFlag] = Field(default_factory=list, description="List of triggered risk items")
    is_duplicate_suspect: bool = Field(default=False, description="Duplicate invoice check outcome")
    is_bank_account_changed: bool = Field(default=False, description="Whether vendor bank details differ from profile")
    is_weekend_submission: bool = Field(default=False, description="Flag for unusual submission timestamps")
    price_surge_detected: bool = Field(default=False, description="Historical price surge flag")
    recommended_action: str = Field(default="PROCEED", description="AUTO_APPROVE, REVIEW, REJECT")


class PolicyViolation(BaseModel):
    rule_id: str
    rule_name: str
    severity: SeverityLevel
    threshold: Optional[str] = None
    actual_value: Optional[str] = None
    description: str


class PolicyEvaluation(BaseModel):
    is_compliant: bool = Field(..., description="Whether transaction satisfies all corporate spending policies")
    violations: List[PolicyViolation] = Field(default_factory=list, description="Identified policy violations")
    approval_tier_required: str = Field(default="TIER_1", description="Required authority tier (TIER_1, TIER_2, EXECUTIVE)")
    requires_two_signatories: bool = Field(default=False, description="Whether dual signoff is required")
    category_allowed: bool = Field(default=True, description="Whether expense category is permitted")
    notes: List[str] = Field(default_factory=list)
