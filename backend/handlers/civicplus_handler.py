"""Handler for CivicPlus FormCenter forms."""

from typing import Optional, Dict, Any

from .web_form_handler import WebFormHandler
from models.form_entry import FormEntry
from models.enums import FormType


class CivicPlusHandler(WebFormHandler):
    """Handler for CivicPlus FormCenter forms (/FormCenter/, civicplus.com)."""

    SUPPORTED_FORM_TYPES = [FormType.CIVICPLUS]
    HANDLER_NAME = "civicplus"

    def build_task_prompt(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> str:
        """CivicPlus FormCenter-specific prompt."""

        request_text = self.get_request_text(form_entry.municipality)

        # Include description context
        context_section = ""
        if form_entry.description:
            context_section = f"""
    CONTEXT FROM DATABASE:
    {form_entry.description}
    """

        return f"""
    Navigate to {form_entry.url} - this is a CivicPlus FormCenter page for {form_entry.municipality}, {form_entry.state}.
    {context_section}
    CIVICPLUS FORMCENTER SPECIFICS:
    CivicPlus is a popular municipal website platform. FormCenter pages:
    - Usually have embedded web forms directly on the page
    - May have multiple form sections that expand
    - Sometimes link to a PDF form as an alternative
    - Typically don't require login

    NAVIGATION:
    1. If you land on an info page, look for "Online Form", "Submit Online", or "Fill Out Form"
    2. If there's both online and PDF options, use the online form
    3. The form may be embedded or open in a new section

    FORM FILLING:
    Fill all visible fields:
    - Name: {self.name}
    - Email: {self.email}
    - Address: {self.address}
    - Phone: {self.phone if self.phone else "(leave blank if optional)"}
    - Request/Description: {request_text}

    For date fields:
    - Try typing MM/DD/YYYY format: 01/01/1940
    - If there's a date range, use 01/01/1940 to 12/31/1945

    For dropdowns:
    - Request Type: "Public Records", "FOIA", or "Open Records"
    - Department: "Planning", "Zoning", "City Clerk", or "Records"
    - Delivery: "Email" if available

    Common CivicPlus field names to watch for:
    - "Field1", "Field2" etc. - generic field names, fill based on labels
    - "Comments" or "Additional Information" - put request text here if no description field

    SUBMISSION:
    - Look for "Submit" button (usually at bottom)
    - Wait for confirmation page
    - Report any reference number

    STOP CONDITIONS:
    - CAPTCHA: Report "CAPTCHA_DETECTED"
    - PDF download only (no web form): Report "PDF_DOWNLOAD"
    - Form not found: Report "FORM_NOT_FOUND"
    """
