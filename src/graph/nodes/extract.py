import logging
from typing import Dict, Any
from src.graph.state import FinFlowState
from src.schemas.document import Invoice
from src.services.llm import llm_service

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are an expert financial document extraction agent. 
Extract all key financial attributes from the provided document accurately into the structured Invoice schema.
Ensure item totals, subtotals, tax rates, vendor identifiers, bank accounts, and PO references are preserved."""


async def extract_node(state: FinFlowState) -> Dict[str, Any]:
    """
    Extracts structured financial invoice data from raw text or document payload.
    """
    logger.info(f"Executing extract_node for doc ID: {state.get('document_id')}")

    # Check if invoice already pre-populated
    if state.get("invoice") is not None:
        return {
            "messages": ["Invoice entity already supplied in state."],
            "audit_trail": [{
                "step": "extract",
                "status": "SKIPPED",
                "reason": "Invoice pre-populated"
            }]
        }

    raw_text = state.get("raw_text", "")
    if not raw_text:
        return {
            "errors": ["No raw text or document content provided for extraction."],
            "decision": "REJECTED",
            "audit_trail": [{
                "step": "extract",
                "status": "FAILED",
                "reason": "Empty document payload"
            }]
        }

    try:
        invoice = await llm_service.extract_structured(
            prompt=raw_text,
            response_model=Invoice,
            system_prompt=SYSTEM_PROMPT
        )

        return {
            "invoice": invoice,
            "messages": [f"Extracted invoice #{invoice.invoice_number} from vendor '{invoice.vendor.name}' (Total: ${invoice.total_amount:,.2f})"],
            "audit_trail": [{
                "step": "extract",
                "status": "SUCCESS",
                "invoice_number": invoice.invoice_number,
                "vendor": invoice.vendor.name,
                "total_amount": invoice.total_amount,
                "confidence": invoice.confidence_score
            }]
        }
    except Exception as e:
        logger.error(f"Extraction failed: {e}", exc_info=True)
        return {
            "errors": [f"Extraction error: {str(e)}"],
            "decision": "REJECTED",
            "audit_trail": [{
                "step": "extract",
                "status": "ERROR",
                "error": str(e)
            }]
        }
