"""Submission result data model for tracking form submission outcomes."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, Any

from .enums import SubmissionStatus, FailureReason


@dataclass
class SubmissionResult:
    """Result of a form submission attempt."""
    form_entry_id: str
    census_id: str
    municipality: str
    state: str
    url: str

    # Status tracking
    status: SubmissionStatus
    failure_reason: FailureReason = FailureReason.NONE

    # Timing
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    # Result details
    confirmation_number: Optional[str] = None
    confirmation_message: Optional[str] = None
    screenshot_path: Optional[str] = None

    # PDF-specific
    pdf_downloaded_path: Optional[str] = None
    pdf_filled_path: Optional[str] = None
    email_sent_to: Optional[str] = None
    email_sent_at: Optional[datetime] = None

    # Error details
    error_message: Optional[str] = None
    agent_output: Optional[str] = None

    # Metadata
    retry_count: int = 0
    form_type: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for storage."""
        return {
            'form_entry_id': self.form_entry_id,
            'census_id': self.census_id,
            'municipality': self.municipality,
            'state': self.state,
            'url': self.url,
            'status': self.status.value,
            'failure_reason': self.failure_reason.value,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
            'confirmation_number': self.confirmation_number,
            'confirmation_message': self.confirmation_message,
            'screenshot_path': self.screenshot_path,
            'pdf_downloaded_path': self.pdf_downloaded_path,
            'pdf_filled_path': self.pdf_filled_path,
            'email_sent_to': self.email_sent_to,
            'email_sent_at': self.email_sent_at.isoformat() if self.email_sent_at else None,
            'error_message': self.error_message,
            'agent_output': self.agent_output,
            'retry_count': self.retry_count,
            'form_type': self.form_type,
        }
