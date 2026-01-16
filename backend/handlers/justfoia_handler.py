"""Handler for JustFOIA portal forms."""

from typing import Optional, Dict, Any

from .web_form_handler import WebFormHandler
from models.form_entry import FormEntry
from models.enums import FormType


class JustFOIAHandler(WebFormHandler):
    """Handler for JustFOIA portal forms (*.justfoia.com)."""

    SUPPORTED_FORM_TYPES = [FormType.JUSTFOIA]
    HANDLER_NAME = "justfoia"

    def build_task_prompt(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> str:
        """JustFOIA-specific prompt."""

        request_text = self.get_request_text(form_entry.municipality)

        # Include description context
        context_section = ""
        if form_entry.description:
            context_section = f"""
    CONTEXT FROM DATABASE:
    {form_entry.description}
    """

        return f"""
    Navigate to {form_entry.url} - this is a JustFOIA portal for {form_entry.municipality}, {form_entry.state}.
    {context_section}
    JUSTFOIA PORTAL SPECIFICS:
    JustFOIA is a FOIA/public records platform commonly used by municipalities. It typically has:
    - A direct form without requiring login
    - Sections for: Requester Information, Request Details, Delivery Preferences
    - A recipient/department dropdown to route the request

    FORM FILLING:
    Fill in these sections:

    REQUESTER INFORMATION:
    - Name: {self.name}
    - Email: {self.email}
    - Address: {self.address}
    - Phone: {self.phone if self.phone else "(leave blank if optional)"}
    - Organization: "Individual" or "Private Citizen" (if asked)

    REQUEST DETAILS:
    - Description/Request: {request_text}
    - Date Range (if asked): 01/01/1940 to 12/31/1945

    RECIPIENT/DEPARTMENT:
    Look for a dropdown to select who receives the request. Choose in this priority order:
    1. "Planning" or "Planning Department"
    2. "Zoning"
    3. "Community Development"
    4. "City Clerk" or "Clerk's Office"
    5. "Records" or "Public Records"
    6. "Administration"

    DELIVERY PREFERENCES:
    - Delivery Method: Select "Email" if available
    - Format: "Electronic" or "Digital" if asked

    SUBMISSION:
    - Click Submit or Send Request
    - Wait for confirmation
    - Report any confirmation number or message

    STOP CONDITIONS:
    - CAPTCHA detected: Report "CAPTCHA_DETECTED"
    - Login required: Report "LOGIN_REQUIRED"
    - Form not found: Report "FORM_NOT_FOUND"
    """
