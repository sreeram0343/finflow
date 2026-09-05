from pydantic import model_validator
from typing import List, Optional 
from pydantic import BaseModel, Field

class InvoiceItem(BaseModel):
    description: Optional[str] = None
    quantity: float = None 
    unit_price: float = None
    total: float = None 


class ExtractedInvoice(BaseModel):
    invoice_number: str = None
    invoice_date: str = None
    vendor_name: str= None
    vendor_tax_id: str = None
    items: List[InvoiceItem]
    due_date: Optional[str] = None
    remittance_bank_account: Optional[str] = None
    po_number: Optional[str] = None
    sub_total: float = None
    tax_amount: float = None
    total_amount: float = None


    @model_validator(mode='after')
    def validate_math(self) -> 'ExtractedInvoice':
        calculated_subtotal = 0.0

        #Validate line item totals
        for item in self.items:
            expected_total = round(item.quantity * item.unit_price, 2)
            if abs(expected_total - item.total) > 0.01:
                raise ValueError(f"Line item math mismatch: {item.quantity} * {item.unit_price} != {item.total}")

            calculated_subtotal += item.total


        #Validate Subtotal
        if abs(calculated_subtotal - self.subtotal) > 0.05:
            raise ValueError(f"Subtotal mismatch: Line items sum to {calculated_subtotal}, but invoice subtotal is {self.subtotal}")

        #Validate total
        expected_total_amount = round(self.subtotal + self.tax_amount, 2)
        if abs(expected_total_amount - self.total_amount) > 0.05:
            raise ValueError(f"Total mismatch: Subtotal ({self.subtotal}) + Tax ({self.tax_amount}) != Total ({self.total_amount})")


        return self
        
            






