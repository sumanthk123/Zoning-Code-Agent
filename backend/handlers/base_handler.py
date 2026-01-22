"""Abstract base class for all form handlers."""

from abc import ABC, abstractmethod
from typing import Optional, Dict, Any, List
import os
import logging

from models.form_entry import FormEntry
from models.submission_result import SubmissionResult
from models.enums import SubmissionStatus, FailureReason, FormType, SubmissionConfidence

logger = logging.getLogger(__name__)


class BaseFormHandler(ABC):
    """Abstract base class for all form handlers."""

    # Class-level attributes to be overridden
    SUPPORTED_FORM_TYPES: List[FormType] = []
    HANDLER_NAME: str = "base"

    def __init__(
        self,
        name: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize handler with contact information.

        Args:
            name: Requester name
            email: Requester email
            address: Requester address
            phone: Requester phone (optional)
            password: Password for authenticated portals (optional)
        """
        self.name = name or os.getenv('DEFAULT_NAME', 'John Doe')
        self.email = email or os.getenv('DEFAULT_EMAIL', 'test@example.com')
        self.address = address or os.getenv('DEFAULT_ADDRESS', '123 Main St, City, State 12345')
        self.phone = phone or os.getenv('DEFAULT_PHONE', '')
        self.password = password or os.getenv('DEFAULT_PASSWORD', '')

    @classmethod
    def can_handle(cls, form_type: FormType) -> bool:
        """Check if this handler can process the given form type."""
        return form_type in cls.SUPPORTED_FORM_TYPES

    @abstractmethod
    async def submit(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None,
    ) -> SubmissionResult:
        """
        Submit the form and return the result.

        Args:
            form_entry: The form entry to process (includes description for context)
            additional_fields: Extra fields to fill

        Returns:
            SubmissionResult with status and details
        """
        pass

    def get_request_text(self, municipality: str) -> str:
        """Generate the standard request text."""
        return (
            f"Could you please send me {municipality}'s municipal zoning code as of 1940? "
            f"If a zoning code didn't exist then, could you send me the first post 1940 "
            f"adoption of the zoning code?"
        )

    def create_result(
        self,
        form_entry: FormEntry,
        status: SubmissionStatus,
        failure_reason: FailureReason = FailureReason.NONE,
        confidence: SubmissionConfidence = SubmissionConfidence.UNKNOWN,
        **kwargs
    ) -> SubmissionResult:
        """Create a SubmissionResult for the given form entry."""
        return SubmissionResult(
            form_entry_id=form_entry.unique_id,
            census_id=form_entry.census_id,
            municipality=form_entry.municipality,
            state=form_entry.state,
            url=form_entry.url,
            status=status,
            failure_reason=failure_reason,
            confidence=confidence,
            form_type=form_entry.form_type.name if form_entry.form_type else None,
            **kwargs
        )

    async def pre_submit_hook(self, form_entry: FormEntry) -> bool:
        """
        Hook called before submission. Override to add pre-processing.

        Returns:
            True to continue, False to skip this submission
        """
        logger.info(f"[{self.HANDLER_NAME}] Starting submission for {form_entry.display_name}")
        logger.info(f"[{self.HANDLER_NAME}] URL: {form_entry.url}")
        if form_entry.description:
            logger.info(f"[{self.HANDLER_NAME}] Context: {form_entry.description[:100]}...")
        return True

    async def post_submit_hook(self, form_entry: FormEntry, result: SubmissionResult):
        """Hook called after submission. Override to add post-processing."""
        logger.info(
            f"[{self.HANDLER_NAME}] Completed {form_entry.display_name}: "
            f"{result.status.value}"
        )
