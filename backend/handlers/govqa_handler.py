"""Handler for GovQA portal forms."""

from typing import Optional, Dict, Any

from .web_form_handler import WebFormHandler
from models.form_entry import FormEntry
from models.enums import FormType


class GovQAHandler(WebFormHandler):
    """Handler for GovQA portal forms (*.govqa.us)."""

    SUPPORTED_FORM_TYPES = [FormType.GOVQA]
    HANDLER_NAME = "govqa"

    def build_task_prompt(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> str:
        """GovQA-specific prompt."""

        request_text = self.get_request_text(form_entry.municipality)

        # Include description context
        context_section = ""
        if form_entry.description:
            context_section = f"""
    CONTEXT FROM DATABASE:
    {form_entry.description}
    """

        return f"""
    Navigate to {form_entry.url} - this is a GovQA portal for {form_entry.municipality}, {form_entry.state}.
    {context_section}
    GOVQA PORTAL SPECIFICS:
    GovQA is a public records/information request platform. It typically has:
    - A support home page with options to submit a new request
    - May require creating an account or allow guest submissions
    - Forms organized by request type (Public Records, Information Request, etc.)

    NAVIGATION:
    1. Look for "Submit a Request", "New Request", or "Public Records Request"
    2. If you see a list of request types, select "Public Records Request" or "Open Records"
    3. If login is required:
       - Try to find a "Guest" or "Continue without signing in" option first
       - If login is mandatory:
         - Email: {self.email}
         - Password: {self.password}
       - If you need to create an account, use:
         - Name: {self.name}
         - Email: {self.email}
         - Password: {self.password}

    FORM FILLING:
    - Name/Requester: {self.name}
    - Email: {self.email}
    - Address: {self.address}
    - Phone: {self.phone if self.phone else "(optional)"}
    - Request Description: {request_text}
    - Request Type: "Public Records" or "Open Records" if dropdown exists
    - Date Range: 01/01/1940 to 12/31/1945 (if asked)

    For department selection, prefer:
    - "Planning", "Zoning", "City Clerk", or "Records"

    SUBMISSION:
    - Submit the request
    - Capture any ticket/case number
    - Report confirmation details

    STOP CONDITIONS:
    - CAPTCHA: Report "CAPTCHA_DETECTED"
    - Can't proceed without login: Report "LOGIN_REQUIRED"
    """
