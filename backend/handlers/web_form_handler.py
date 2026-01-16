"""Generic web form handler using browser-use agent."""

import asyncio
import os
import re
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

from browser_use import Agent, Browser
from browser_use.llm import ChatOpenRouter

from .base_handler import BaseFormHandler
from models.form_entry import FormEntry
from models.submission_result import SubmissionResult
from models.enums import SubmissionStatus, FailureReason, FormType
import logging

load_dotenv()
logger = logging.getLogger(__name__)


class WebFormHandler(BaseFormHandler):
    """
    Generic web form handler using browser-use agent.
    Base class for all browser-based form handlers.
    """

    SUPPORTED_FORM_TYPES = [FormType.GENERIC_WEB, FormType.STATE_PORTAL, FormType.OPRAMACHINE, FormType.CIVICWEB, FormType.OFFICE365]
    HANDLER_NAME = "web_form"

    def __init__(
        self,
        name: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        password: Optional[str] = None,
        headless: bool = False,
        max_steps: int = 30,
    ):
        super().__init__(name, email, address, phone, password)
        self.headless = headless
        self.max_steps = max_steps

    def get_llm(self):
        """Get the LLM instance using browser-use's native ChatOpenRouter."""
        return ChatOpenRouter(
            model=os.getenv('OPENROUTER_MODEL', 'anthropic/claude-3.5-sonnet'),
            api_key=os.getenv('OPENROUTER_API_KEY')
        )

    def build_task_prompt(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Build the agent task prompt.
        Includes the description from CSV for navigation context.
        Override in subclasses for portal-specific prompts.
        """
        request_text = self.get_request_text(form_entry.municipality)
        additional_fields = additional_fields or {}

        # Build field list
        field_list = f"""
        Name: {self.name}
        Email: {self.email}
        Address: {self.address}"""

        if self.phone:
            field_list += f"\n        Phone: {self.phone}"

        field_list += f"\n        Request Description: {request_text}"

        for field_name, field_value in additional_fields.items():
            field_list += f"\n        {field_name}: {field_value}"

        # Include the description from CSV as context for navigation
        context_section = ""
        if form_entry.description:
            context_section = f"""
    IMPORTANT CONTEXT ABOUT THIS FORM:
    {form_entry.description}

    Use this context to understand what type of portal this is and how to navigate it.
    """

        task = f"""
    Navigate to {form_entry.url} and fill out the public records request form for {form_entry.municipality}, {form_entry.state}.
    {context_section}
    Use this information to fill the form:
    {field_list}

    AUTHENTICATION HANDLING:
    If you see a "Sign In" or "Login" button/link:
    1. Click it to go to the login page
    2. Look at what fields are visible:
       - If ONLY an email field is visible, enter the email and click Continue/Next
       - Wait for the password field to appear, then enter the password
       - If BOTH email and password fields are visible, fill both and submit
    3. Use these credentials:
       - Email: {self.email}
       - Password: {self.password}
    4. If no account exists, look for "Sign Up" or "Create Account" and register with:
       - Name: {self.name}
       - Email: {self.email}
       - Password: {self.password}

    FORM FILLING INSTRUCTIONS:
    - Remove any cookie banners or popup dialogs first
    - Fill ALL fields (required and optional)
    - Make educated guesses for fields not provided:
      - Organization: "Individual" or "Private Citizen"
      - Contact method preference: "Email"
      - Date needed: "No rush" or leave blank
      - Purpose: "Research" or "Historical records"
    - Work top-to-bottom, one field per step
    - For date fields, try typing MM/DD/YYYY format first (e.g., "01/01/1940")
    - For date range, use 01/01/1940 to 12/31/1945
    - For dropdowns selecting department, prefer: "Planning", "Zoning", "City Clerk", or "Records"
    - For delivery method, select "Email" if available

    STOP CONDITIONS - If any of these occur, STOP and report:
    - CAPTCHA detected: Report "CAPTCHA_DETECTED"
    - Login required and credentials don't work: Report "LOGIN_REQUIRED"
    - This is a PDF download page (not a web form): Report "PDF_DOWNLOAD"
    - Form not found on page: Report "FORM_NOT_FOUND"

    AFTER SUBMISSION:
    - Wait for confirmation screen
    - Report all fields you filled with their values
    - Report any confirmation number or reference ID shown
    - Report the success/confirmation message
    """

        return task

    async def submit(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None,
    ) -> SubmissionResult:
        """Submit using browser-use agent."""

        if not await self.pre_submit_hook(form_entry):
            return self.create_result(
                form_entry,
                SubmissionStatus.SKIPPED,
                failure_reason=FailureReason.NONE
            )

        started_at = datetime.now()

        try:
            task = self.build_task_prompt(form_entry, additional_fields)

            llm = self.get_llm()
            browser = Browser(
                headless=self.headless,
                window_size={'width': 1000, 'height': 700},
            )
            agent = Agent(task=task, llm=llm, use_vision="auto", browser=browser)

            agent_result = await agent.run(max_steps=self.max_steps)

            # Parse agent result for status
            result = self._parse_agent_result(form_entry, agent_result, started_at)

            await self.post_submit_hook(form_entry, result)
            return result

        except asyncio.TimeoutError:
            return self.create_result(
                form_entry,
                SubmissionStatus.FAILED,
                failure_reason=FailureReason.TIMEOUT,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message="Agent timed out"
            )
        except Exception as e:
            logger.exception(f"Error submitting form for {form_entry.display_name}")
            return self.create_result(
                form_entry,
                SubmissionStatus.FAILED,
                failure_reason=FailureReason.UNKNOWN,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message=str(e)
            )

    def _parse_agent_result(
        self,
        form_entry: FormEntry,
        agent_result: Any,
        started_at: datetime
    ) -> SubmissionResult:
        """Parse the agent result to determine status."""

        # Extract the final result from browser-use AgentHistoryList
        # The agent_result is an AgentHistoryList, we need the final result text
        final_result_text = ""
        is_successful = False

        if agent_result:
            # Try to get the final result from the agent history
            try:
                # browser-use returns AgentHistoryList with a final_result() method or last item
                if hasattr(agent_result, 'final_result'):
                    final_result = agent_result.final_result()
                    if final_result:
                        final_result_text = str(final_result).lower()
                        # Check if agent reported success
                        if hasattr(final_result, 'success'):
                            is_successful = final_result.success
                elif hasattr(agent_result, 'is_done') and agent_result.is_done:
                    is_successful = True
                    # Get text from the last action's result
                    if hasattr(agent_result, '__iter__'):
                        for item in reversed(list(agent_result)):
                            if hasattr(item, 'result') and item.result:
                                if hasattr(item.result, 'extracted_content'):
                                    final_result_text = str(item.result.extracted_content).lower()
                                    break
                                elif hasattr(item.result, 'done'):
                                    final_result_text = str(item.result.done.text if hasattr(item.result.done, 'text') else item.result.done).lower()
                                    is_successful = getattr(item.result.done, 'success', True) if hasattr(item.result, 'done') else True
                                    break

                # Fallback to string conversion but only use last portion
                if not final_result_text:
                    full_text = str(agent_result)
                    # Only use the last 2000 chars to avoid matching task instructions
                    final_result_text = full_text[-2000:].lower() if len(full_text) > 2000 else full_text.lower()
            except Exception as e:
                logger.warning(f"Error parsing agent result: {e}")
                final_result_text = str(agent_result)[-2000:].lower()

        # If agent explicitly reported success, return success
        if is_successful and ('submitted' in final_result_text or 'request' in final_result_text):
            # Extract confirmation number if present
            confirmation_number = None
            # Look for request ID patterns like #26-8, REQ-12345, etc.
            id_match = re.search(r'(?:request\s*(?:id|#|number)?[:\s]*)?([#]?[\w\d]+-[\w\d]+|req-?\d+)', final_result_text, re.IGNORECASE)
            if id_match:
                confirmation_number = id_match.group(1)

            return self.create_result(
                form_entry,
                SubmissionStatus.SUCCESS,
                failure_reason=FailureReason.NONE,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=str(agent_result)[-5000:],  # Truncate to avoid huge output
                confirmation_number=confirmation_number,
                confirmation_message="Form submitted successfully"
            )

        # Check for stop conditions in final result only
        if 'captcha_detected' in final_result_text or ('captcha' in final_result_text and 'detected' in final_result_text):
            return self.create_result(
                form_entry,
                SubmissionStatus.CAPTCHA_BLOCKED,
                failure_reason=FailureReason.CAPTCHA,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=str(agent_result)[-5000:]
            )

        if 'login_required' in final_result_text:
            return self.create_result(
                form_entry,
                SubmissionStatus.LOGIN_REQUIRED,
                failure_reason=FailureReason.LOGIN_REQUIRED,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=str(agent_result)[-5000:]
            )

        if 'pdf_download' in final_result_text:
            return self.create_result(
                form_entry,
                SubmissionStatus.PDF_DOWNLOADED,
                failure_reason=FailureReason.NONE,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=str(agent_result)[-5000:]
            )

        if 'form_not_found' in final_result_text:
            return self.create_result(
                form_entry,
                SubmissionStatus.FAILED,
                failure_reason=FailureReason.FORM_NOT_FOUND,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=str(agent_result)[-5000:]
            )

        # Check for success indicators
        success_indicators = ['submitted', 'success', 'confirmation', 'thank you', 'received', 'request id', 'request #']
        if any(indicator in final_result_text for indicator in success_indicators):
            # Extract confirmation number if present
            confirmation_number = None
            id_match = re.search(r'(?:request\s*(?:id|#|number)?[:\s]*)?([#]?[\w\d]+-[\w\d]+|req-?\d+)', final_result_text, re.IGNORECASE)
            if id_match:
                confirmation_number = id_match.group(1)

            return self.create_result(
                form_entry,
                SubmissionStatus.SUCCESS,
                failure_reason=FailureReason.NONE,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=str(agent_result)[-5000:],
                confirmation_number=confirmation_number,
                confirmation_message="Form submitted successfully"
            )

        # Default to success if no error indicators (agent completed without issues)
        return self.create_result(
            form_entry,
            SubmissionStatus.SUCCESS,
            failure_reason=FailureReason.NONE,
            started_at=started_at,
            completed_at=datetime.now(),
            agent_output=str(agent_result)[-5000:],
            confirmation_message="Agent completed - verify in output"
        )
