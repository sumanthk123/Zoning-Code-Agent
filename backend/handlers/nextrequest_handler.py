"""Handler for NextRequest portal forms."""

from typing import Optional, Dict, Any

from .web_form_handler import WebFormHandler
from models.form_entry import FormEntry
from models.enums import FormType


class NextRequestHandler(WebFormHandler):
    """Handler for NextRequest portal forms (*.nextrequest.com)."""

    SUPPORTED_FORM_TYPES = [FormType.NEXTREQUEST]
    HANDLER_NAME = "nextrequest"

    def build_task_prompt(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> str:
        """NextRequest-specific prompt with portal navigation guidance."""

        request_text = self.get_request_text(form_entry.municipality)

        # Include description context
        context_section = ""
        if form_entry.description:
            context_section = f"""
    CONTEXT FROM DATABASE:
    {form_entry.description}
    """

        return f"""
    Navigate to {form_entry.url} - this is a NextRequest portal for {form_entry.municipality}, {form_entry.state}.
    {context_section}
    NEXTREQUEST PORTAL SPECIFICS:
    NextRequest is a common public records request platform. It typically has:
    - A "New Request" or "Submit Request" button
    - Optional login (you can often submit without logging in)
    - Form sections for: Contact Info, Request Details, Attachments

    STEP 1 - CHECK FOR LOGIN REQUIREMENT:
    - If there's a "Sign In" button and you can proceed without signing in, skip login
    - If login is required:
      1. Click Sign In
      2. Enter email: {self.email}
      3. Click Continue (NextRequest uses a two-step login - password comes after email)
      4. Wait for password field to appear
      5. Enter password: {self.password}
      6. Click Sign In
    - If no account exists, click "Sign Up" and create one with:
      - Name: {self.name}
      - Email: {self.email}
      - Password: {self.password}

    STEP 2 - FILL THE REQUEST FORM:
    - Name: {self.name}
    - Email: {self.email}
    - Address: {self.address}
    - Phone: {self.phone if self.phone else "(leave blank if optional)"}
    - Request Description: {request_text}

    For any date range fields:
    - Start Date: 01/01/1940
    - End Date: 12/31/1945

    For department/category dropdowns, select:
    - "Planning" or "Community Development" if available
    - Otherwise "City Clerk" or "General"

    STEP 3 - SUBMIT AND CAPTURE CONFIRMATION:
    - Click Submit Request
    - Wait for confirmation page
    - Capture the Request ID/Number if shown
    - Report the confirmation message

    STOP CONDITIONS:
    - CAPTCHA detected: Report "CAPTCHA_DETECTED"
    - Can't log in or create account: Report "LOGIN_REQUIRED"
    """
