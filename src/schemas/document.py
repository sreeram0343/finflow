import datetime
from typing import Optional, List
from pydantic import BaseModel, Field


class VendorInfo(BaseModel):
    name: str = Field(..., description="Vendor legal business name")
    tax_id: Optional[str] = Field(None, description="Vendor Tax ID / VAT number")
    address: Optional[str] = Field(None, description="Physical/Billing address")
    email: Optional[str] = Field(None, description="Vendor contact email")
    bank_account_number: Optional[str] = Field(None, description="Bank account number for remittances")
    bank_routing_number: Optional[str] = Field(None, description="Routing or SWIFT/BIC code")
    is_preferred: bool = Field(default=False, description="Whether the vendor is on corporate approved list")


class PaymentDetails(BaseModel):
    payment_terms: Optional[str] = Field(default="Net 30", description="e.g. Net 30, Due on Receipt")
    due_date: Optional[str] = Field(None, description="Invoice payment due date (YYYY-MM-DD)")
    currency: str = Field(default="USD", description="3-letter ISO currency code")
    payment_method: Optional[str] = Field(None, description="ACH, Wire, Check, Credit Card")
    bank_account_number: Optional[str] = Field(None, description="Target bank account")


class LineItem(BaseModel):
    item_id: Optional[str] = Field(None, description="Product/SKU or Item number")
    description: str = Field(..., description="Description of goods or services")
    quantity: float = Field(..., description="Quantity delivered/billed", ge=0)
    unit_price: float = Field(..., description="Price per individual unit", ge=0)
    total_amount: float = Field(..., description="Line total before tax (qty * unit_price)", ge=0)
    tax_rate: Optional[float] = Field(default=0.0, description="Tax rate applied (e.g. 0.10 for 10%)")
    tax_amount: Optional[float] = Field(default=0.0, description="Calculated tax for line item")
    po_line_ref: Optional[int] = Field(None, description="Corresponding line index on Purchase Order")


class TaxSummary(BaseModel):
    tax_rate: float = Field(default=0.0, description="Effective tax rate")
    taxable_amount: float = Field(default=0.0, description="Portion of subtotal subject to tax")
    tax_amount: float = Field(default=0.0, description="Total tax applied")


class Invoice(BaseModel):
    invoice_number: str = Field(..., description="Unique invoice identification number")
    invoice_date: str = Field(..., description="Date invoice was issued (YYYY-MM-DD)")
    due_date: Optional[str] = Field(None, description="Date payment is due (YYYY-MM-DD)")
    vendor: VendorInfo = Field(..., description="Vendor billing details")
    customer_name: Optional[str] = Field(None, description="Customer / Billing recipient entity name")
    currency: str = Field(default="USD", description="3-letter ISO currency code")
    line_items: List[LineItem] = Field(default_factory=list, description="Itemized billing breakdown")
    subtotal: float = Field(..., description="Subtotal before taxes and discounts", ge=0)
    tax_amount: float = Field(default=0.0, description="Total tax amount", ge=0)
    discount_amount: float = Field(default=0.0, description="Any discounts applied", ge=0)
    total_amount: float = Field(..., description="Grand total payable", ge=0)
    purchase_order_number: Optional[str] = Field(None, description="Associated PO number if referenced")
    payment_details: Optional[PaymentDetails] = Field(None, description="Remittance details")
    expense_category: Optional[str] = Field(default="General Corporate", description="Expense classification")
    confidence_score: float = Field(default=1.0, description="Extraction confidence score (0.0 to 1.0)", ge=0.0, le=1.0)


class PurchaseOrder(BaseModel):
    po_number: str = Field(..., description="Unique PO number")
    po_date: str = Field(..., description="Date PO was authorized")
    vendor_name: str = Field(..., description="Vendor name authorized on PO")
    buyer_name: Optional[str] = Field(None, description="Department or employee buyer name")
    currency: str = Field(default="USD", description="3-letter currency code")
    line_items: List[LineItem] = Field(default_factory=list, description="Authorized line items")
    subtotal: float = Field(..., description="Authorized subtotal", ge=0)
    tax_amount: float = Field(default=0.0, description="Authorized tax", ge=0)
    total_amount: float = Field(..., description="Authorized grand total", ge=0)
    approved_by: Optional[str] = Field(None, description="Authorizing manager / signatory")
    status: str = Field(default="OPEN", description="OPEN, CLOSED, PARTIALLY_FULFILLED")
