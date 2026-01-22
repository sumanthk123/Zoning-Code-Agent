"""Generic web form handler using browser-use Cloud API."""

import asyncio
import os
import re
import aiohttp
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

from .base_handler import BaseFormHandler
from models.form_entry import FormEntry
from models.submission_result import SubmissionResult
from models.enums import SubmissionStatus, FailureReason, FormType, SubmissionConfidence
import logging

load_dotenv()
logger = logging.getLogger(__name__)

# Browser-use Cloud API configuration
BROWSER_USE_API_BASE = "https://api.browser-use.com/api/v2"


class WebFormHandler(BaseFormHandler):
    """
    Generic web form handler using browser-use Cloud API.
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
        headless: bool = False,  # Not used in Cloud API, kept for compatibility
        max_steps: int = 30,
    ):
        super().__init__(name, email, address, phone, password)
        self.headless = headless
        self.max_steps = max_steps
        self.api_key = os.getenv('BROWSER_USE_API_KEY')
        if not self.api_key:
            raise ValueError("BROWSER_USE_API_KEY environment variable is required")

    def _get_headers(self) -> Dict[str, str]:
        """Get headers for browser-use Cloud API requests."""
        return {
            "X-Browser-Use-API-Key": self.api_key,
            "Content-Type": "application/json"
        }

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

    async def _create_task(self, task_prompt: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Create a task in browser-use Cloud."""
        url = f"{BROWSER_USE_API_BASE}/tasks"
        payload = {
            "task": task_prompt,
            "maxSteps": self.max_steps,
        }

        async with session.post(url, headers=self._get_headers(), json=payload) as response:
            if response.status not in [200, 201, 202]:
                error_text = await response.text()
                raise Exception(f"Failed to create task: {response.status} - {error_text}")
            return await response.json()

    async def _get_task_status(self, task_id: str, session: aiohttp.ClientSession) -> Dict[str, Any]:
        """Get task status from browser-use Cloud."""
        url = f"{BROWSER_USE_API_BASE}/tasks/{task_id}"

        async with session.get(url, headers=self._get_headers()) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"Failed to get task status: {response.status} - {error_text}")
            return await response.json()

    async def _stop_session(self, session_id: str, session: aiohttp.ClientSession) -> None:
        """Stop a browser-use Cloud session."""
        url = f"{BROWSER_USE_API_BASE}/sessions/{session_id}"
        payload = {"action": "stop"}

        try:
            async with session.patch(url, headers=self._get_headers(), json=payload) as response:
                if response.status != 200:
                    logger.warning(f"Failed to stop session {session_id}: {response.status}")
        except Exception as e:
            logger.warning(f"Error stopping session {session_id}: {e}")

    async def _wait_for_task_completion(
        self,
        task_id: str,
        session: aiohttp.ClientSession,
        timeout: int = 900,  # 15 minutes max (Cloud session limit)
        poll_interval: int = 5
    ) -> Dict[str, Any]:
        """Poll for task completion."""
        start_time = datetime.now()

        while True:
            elapsed = (datetime.now() - start_time).total_seconds()
            if elapsed > timeout:
                raise asyncio.TimeoutError(f"Task {task_id} timed out after {timeout} seconds")

            task_data = await self._get_task_status(task_id, session)
            status = task_data.get("status", "")

            logger.info(f"Task {task_id} status: {status}")

            # Check for terminal states
            if status in ["finished", "completed", "done"]:
                return task_data
            elif status in ["failed", "error", "stopped"]:
                return task_data
            elif status == "paused":
                # Task is paused, might need manual intervention
                logger.warning(f"Task {task_id} is paused")
                return task_data

            # Log live URL if available
            live_url = task_data.get("live_url") or task_data.get("liveUrl")
            if live_url and elapsed < 10:  # Only log once at the beginning
                logger.info(f"Live preview: {live_url}")

            await asyncio.sleep(poll_interval)

    async def submit(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None,
    ) -> SubmissionResult:
        """Submit using browser-use Cloud API."""

        if not await self.pre_submit_hook(form_entry):
            return self.create_result(
                form_entry,
                SubmissionStatus.SKIPPED,
                failure_reason=FailureReason.NONE
            )

        started_at = datetime.now()
        session_id = None

        try:
            task_prompt = self.build_task_prompt(form_entry, additional_fields)

            async with aiohttp.ClientSession() as session:
                # Create task
                logger.info(f"Creating browser-use Cloud task for {form_entry.display_name}")
                task_response = await self._create_task(task_prompt, session)

                task_id = task_response.get("id") or task_response.get("task_id") or task_response.get("taskId")
                session_id = task_response.get("session_id") or task_response.get("sessionId")

                if not task_id:
                    raise Exception(f"No task ID in response: {task_response}")

                logger.info(f"Task created: {task_id}, Session: {session_id}")

                # Log live URL if available
                live_url = task_response.get("live_url") or task_response.get("liveUrl")
                if live_url:
                    logger.info(f"Live preview: {live_url}")

                # Wait for completion
                final_result = await self._wait_for_task_completion(task_id, session)

                # Parse result
                result = self._parse_cloud_result(form_entry, final_result, started_at)

                # Stop session to free resources
                if session_id:
                    await self._stop_session(session_id, session)

                await self.post_submit_hook(form_entry, result)
                return result

        except asyncio.TimeoutError:
            return self.create_result(
                form_entry,
                SubmissionStatus.FAILED,
                failure_reason=FailureReason.TIMEOUT,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message="Task timed out"
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

    def _parse_cloud_result(
        self,
        form_entry: FormEntry,
        task_data: Dict[str, Any],
        started_at: datetime
    ) -> SubmissionResult:
        """
        Parse the browser-use Cloud task result using agent behavior detection.

        Detection logic based on what actions the agent actually took:
        1. If task status = failed/error → FAILED
        2. If failure_indicators found → FAILED
        3. If submit_action + navigation evidence → SUCCESS (HIGH confidence)
        4. If submit_action OR navigation evidence → SUCCESS (MEDIUM confidence)
        5. If completion_indicators found → NEEDS_VERIFICATION (LOW confidence)
        6. Default → NEEDS_VERIFICATION (UNKNOWN confidence)
        """

        status = task_data.get("status", "")
        output = task_data.get("output") or task_data.get("result") or ""

        # Convert output to string for parsing
        if isinstance(output, dict):
            output_text = str(output.get("text", "")) or str(output)
        else:
            output_text = str(output)

        output_lower = output_text.lower()

        # ============================================================
        # STEP 1: Check task status first (API-level failure)
        # ============================================================
        if status in ["failed", "error"]:
            error_msg = task_data.get("error") or task_data.get("message") or "Task failed"
            return self.create_result(
                form_entry,
                SubmissionStatus.FAILED,
                failure_reason=FailureReason.UNKNOWN,
                confidence=SubmissionConfidence.HIGH,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=output_text[:5000],
                error_message=str(error_msg)
            )

        # ============================================================
        # STEP 2: Check for failure indicators in agent output
        # ============================================================
        failure_indicators = [
            # Submission failures
            'could not submit', 'failed to submit', 'submission failed',
            'unable to submit', 'submit button not found', 'cannot submit',
            # General errors
            'error occurred', 'error:', 'failed:', 'unable to complete',
            'could not complete', 'task failed',
            # Form issues
            'form not found', 'no form found', 'required field missing',
            'validation error', 'invalid input', 'form_not_found',
            # Access issues
            'captcha detected', 'captcha_detected', 'blocked by captcha',
            'login required', 'login_required', 'access denied',
            'permission denied', 'unauthorized',
            # Navigation issues
            'page not found', '404 error', 'timeout', 'connection error',
            'site unavailable', 'server error',
        ]

        for indicator in failure_indicators:
            if indicator in output_lower:
                # Determine specific failure reason
                if 'captcha' in indicator:
                    return self.create_result(
                        form_entry,
                        SubmissionStatus.CAPTCHA_BLOCKED,
                        failure_reason=FailureReason.CAPTCHA,
                        confidence=SubmissionConfidence.HIGH,
                        started_at=started_at,
                        completed_at=datetime.now(),
                        agent_output=output_text[:5000],
                        error_message=f"Detected: {indicator}"
                    )
                elif 'login' in indicator:
                    return self.create_result(
                        form_entry,
                        SubmissionStatus.LOGIN_REQUIRED,
                        failure_reason=FailureReason.LOGIN_REQUIRED,
                        confidence=SubmissionConfidence.HIGH,
                        started_at=started_at,
                        completed_at=datetime.now(),
                        agent_output=output_text[:5000],
                        error_message=f"Detected: {indicator}"
                    )
                elif 'form not found' in indicator or 'form_not_found' in indicator:
                    return self.create_result(
                        form_entry,
                        SubmissionStatus.FAILED,
                        failure_reason=FailureReason.FORM_NOT_FOUND,
                        confidence=SubmissionConfidence.HIGH,
                        started_at=started_at,
                        completed_at=datetime.now(),
                        agent_output=output_text[:5000],
                        error_message=f"Detected: {indicator}"
                    )
                else:
                    return self.create_result(
                        form_entry,
                        SubmissionStatus.FAILED,
                        failure_reason=FailureReason.UNKNOWN,
                        confidence=SubmissionConfidence.HIGH,
                        started_at=started_at,
                        completed_at=datetime.now(),
                        agent_output=output_text[:5000],
                        error_message=f"Detected: {indicator}"
                    )

        # Check for PDF download (special case - not failure, but different flow)
        if 'pdf_download' in output_lower or 'downloaded pdf' in output_lower:
            return self.create_result(
                form_entry,
                SubmissionStatus.PDF_DOWNLOADED,
                failure_reason=FailureReason.NONE,
                confidence=SubmissionConfidence.HIGH,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=output_text[:5000]
            )

        # ============================================================
        # STEP 3: Check for submit action evidence
        # ============================================================
        submit_action_indicators = [
            # Direct click actions
            'clicked submit', 'clicked the submit button', 'clicked "submit"',
            "clicked 'submit'", 'clicked make request', 'clicked send request',
            'clicked "make request"', 'pressed submit', 'hit submit',
            'clicking submit', 'clicking the submit',
            # Form submission actions
            'form submitted', 'submitted the form', 'submitted the request',
            'submission complete', 'request submitted', 'form was submitted',
            'successfully submitted',
        ]

        has_submit_action = any(ind in output_lower for ind in submit_action_indicators)

        # Also check for regex patterns
        submit_patterns = [
            r'click(?:ed|ing)?\s+(?:on\s+)?(?:the\s+)?submit',
            r'submit\s+button\s+(?:was\s+)?click',
            r'press(?:ed|ing)?\s+submit',
        ]
        if not has_submit_action:
            for pattern in submit_patterns:
                if re.search(pattern, output_lower):
                    has_submit_action = True
                    break

        # ============================================================
        # STEP 4: Check for navigation/confirmation page evidence
        # ============================================================
        navigation_indicators = [
            # Page change indicators
            'navigated to confirmation', 'redirected to', 'page changed',
            'new page loaded', 'loaded confirmation', 'taken to',
            # Confirmation page indicators
            'confirmation page', 'thank you page', 'success page',
            'receipt page', 'acknowledgment page', 'confirmation screen',
            # URL change indicators
            '/confirmation', '/thank', '/success', '/receipt',
            '/submitted', '/complete',
            # Visual confirmation
            'confirmation message', 'success message', 'thank you for',
            'request has been received', 'we have received your',
            'your submission has been', 'your request was received',
        ]

        has_navigation_evidence = any(ind in output_lower for ind in navigation_indicators)

        # ============================================================
        # STEP 5: Check for completion indicators (weaker evidence)
        # ============================================================
        completion_indicators = [
            # Task completion
            'task completed successfully', 'successfully completed',
            'request has been submitted', 'your request was sent',
            'completed successfully',
            # Form completion
            'all fields filled', 'form complete', 'filled all required fields',
            'completed the form', 'finished filling',
            # Generic success
            'done', 'finished', 'completed',
        ]

        has_completion_evidence = any(ind in output_lower for ind in completion_indicators)

        # ============================================================
        # STEP 6: Extract confirmation number if present (bonus info)
        # ============================================================
        confirmation_number = None
        confirmation_patterns = [
            r'request\s*#?\s*:?\s*([A-Za-z0-9-]{4,})',
            r'confirmation\s*#?\s*:?\s*([A-Za-z0-9-]{4,})',
            r'reference\s*#?\s*:?\s*([A-Za-z0-9-]{4,})',
            r'ticket\s*#?\s*:?\s*([A-Za-z0-9-]{4,})',
            r'tracking\s*#?\s*:?\s*([A-Za-z0-9-]{4,})',
            r'case\s*#?\s*:?\s*([A-Za-z0-9-]{4,})',
            r'#(\d{4,})',
        ]

        for pattern in confirmation_patterns:
            match = re.search(pattern, output_text, re.IGNORECASE)
            if match:
                confirmation_number = match.group(1)
                break

        # ============================================================
        # STEP 7: Determine final status based on evidence
        # ============================================================

        # HIGH confidence: Both submit action AND navigation evidence
        if has_submit_action and has_navigation_evidence:
            return self.create_result(
                form_entry,
                SubmissionStatus.SUCCESS,
                failure_reason=FailureReason.NONE,
                confidence=SubmissionConfidence.HIGH,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=output_text[:5000],
                confirmation_number=confirmation_number,
                confirmation_message="Form submitted - agent clicked submit and navigated to confirmation"
            )

        # MEDIUM confidence: Submit action OR navigation evidence (one but not both)
        if has_submit_action or has_navigation_evidence:
            evidence = "clicked submit" if has_submit_action else "navigated to confirmation"
            return self.create_result(
                form_entry,
                SubmissionStatus.SUCCESS,
                failure_reason=FailureReason.NONE,
                confidence=SubmissionConfidence.MEDIUM,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=output_text[:5000],
                confirmation_number=confirmation_number,
                confirmation_message=f"Form likely submitted - agent {evidence}"
            )

        # LOW confidence: Completion indicators but no submit/navigation proof
        if has_completion_evidence:
            return self.create_result(
                form_entry,
                SubmissionStatus.NEEDS_VERIFICATION,
                failure_reason=FailureReason.NONE,
                confidence=SubmissionConfidence.LOW,
                started_at=started_at,
                completed_at=datetime.now(),
                agent_output=output_text[:5000],
                confirmation_number=confirmation_number,
                confirmation_message="Task completed but no submit action detected - verify manually"
            )

        # UNKNOWN confidence: Task finished but minimal evidence
        # Default to NEEDS_VERIFICATION to avoid false positives
        return self.create_result(
            form_entry,
            SubmissionStatus.NEEDS_VERIFICATION,
            failure_reason=FailureReason.NONE,
            confidence=SubmissionConfidence.UNKNOWN,
            started_at=started_at,
            completed_at=datetime.now(),
            agent_output=output_text[:5000],
            confirmation_number=confirmation_number,
            confirmation_message="Task finished but unclear if form was submitted - verify manually"
        )
