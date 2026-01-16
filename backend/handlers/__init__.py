"""Form handlers for different portal types."""

from .base_handler import BaseFormHandler
from .web_form_handler import WebFormHandler
from .nextrequest_handler import NextRequestHandler
from .justfoia_handler import JustFOIAHandler
from .govqa_handler import GovQAHandler
from .civicplus_handler import CivicPlusHandler
from .pdf_form_handler import PDFFormHandler

__all__ = [
    'BaseFormHandler',
    'WebFormHandler',
    'NextRequestHandler',
    'JustFOIAHandler',
    'GovQAHandler',
    'CivicPlusHandler',
    'PDFFormHandler',
]
