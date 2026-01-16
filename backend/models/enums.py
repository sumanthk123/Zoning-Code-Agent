"""Enums for form types and submission statuses."""

from enum import Enum, auto


class FormType(Enum):
    """Classification of form portal types."""
    NEXTREQUEST = auto()      # *.nextrequest.com
    JUSTFOIA = auto()         # *.justfoia.com
    GOVQA = auto()            # *.govqa.us
    CIVICPLUS = auto()        # /FormCenter paths, civicplus.com
    PDF = auto()              # .pdf extensions
    OFFICE365 = auto()        # forms.office.com
    CIVICWEB = auto()         # *.civicweb.net
    OPRAMACHINE = auto()      # opramachine.com
    STATE_PORTAL = auto()     # openrecords.pa.gov, texasattorneygeneral.gov
    GENERIC_WEB = auto()      # Default fallback for unknown web forms


class SubmissionStatus(Enum):
    """Status of a form submission attempt."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    CAPTCHA_BLOCKED = "captcha_blocked"
    LOGIN_REQUIRED = "login_required"
    PDF_DOWNLOADED = "pdf_downloaded"
    EMAIL_SENT = "email_sent"
    SKIPPED = "skipped"


class FailureReason(Enum):
    """Detailed failure classification."""
    NONE = "none"
    CAPTCHA = "captcha"
    LOGIN_REQUIRED = "login_required"
    TIMEOUT = "timeout"
    NETWORK_ERROR = "network_error"
    FORM_NOT_FOUND = "form_not_found"
    SUBMISSION_ERROR = "submission_error"
    PDF_FILL_ERROR = "pdf_fill_error"
    EMAIL_SEND_ERROR = "email_send_error"
    UNKNOWN = "unknown"
