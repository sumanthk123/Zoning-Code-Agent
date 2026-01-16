"""URL classification utility for determining form portal types."""

import re
from typing import Tuple
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models.enums import FormType


class URLClassifier:
    """Classify form URLs into known portal types."""

    # URL pattern rules (order matters - more specific first)
    PATTERNS = [
        # NextRequest portals
        (r'\.nextrequest\.com', FormType.NEXTREQUEST),

        # JustFOIA portals
        (r'\.justfoia\.com', FormType.JUSTFOIA),

        # GovQA portals
        (r'\.govqa\.us', FormType.GOVQA),

        # Office 365 Forms
        (r'forms\.office\.com', FormType.OFFICE365),

        # CivicWeb portals
        (r'\.civicweb\.net', FormType.CIVICWEB),

        # OPRAMachine
        (r'opramachine\.com', FormType.OPRAMACHINE),

        # State-level portals
        (r'openrecords\.pa\.gov', FormType.STATE_PORTAL),
        (r'texasattorneygeneral\.gov', FormType.STATE_PORTAL),

        # CivicPlus FormCenter (check path patterns)
        (r'/FormCenter/', FormType.CIVICPLUS),
        (r'\.civicplus\.com', FormType.CIVICPLUS),
        (r'/forms\.aspx', FormType.CIVICPLUS),

        # PDF forms (extension check)
        (r'\.pdf(\?|$|#)', FormType.PDF),
    ]

    @classmethod
    def classify(cls, url: str) -> FormType:
        """
        Classify a URL into a form type.

        Args:
            url: The form URL to classify

        Returns:
            FormType enum value
        """
        url_lower = url.lower()

        for pattern, form_type in cls.PATTERNS:
            if re.search(pattern, url_lower):
                return form_type

        # Default to generic web form
        return FormType.GENERIC_WEB

    @classmethod
    def classify_with_confidence(cls, url: str, description: str = "") -> Tuple[FormType, float]:
        """
        Classify with confidence score based on URL and description.

        Returns:
            Tuple of (FormType, confidence 0.0-1.0)
        """
        form_type = cls.classify(url)

        # Higher confidence for explicit matches
        if form_type != FormType.GENERIC_WEB:
            return (form_type, 0.95)

        # Check description for hints
        description_lower = description.lower()
        description_hints = {
            'pdf': FormType.PDF,
            'fillable': FormType.PDF,
            'download': FormType.PDF,
            'nextrequest': FormType.NEXTREQUEST,
            'justfoia': FormType.JUSTFOIA,
            'govqa': FormType.GOVQA,
            'civicplus': FormType.CIVICPLUS,
            'formcenter': FormType.CIVICPLUS,
        }

        for hint, hint_type in description_hints.items():
            if hint in description_lower:
                return (hint_type, 0.7)

        return (FormType.GENERIC_WEB, 0.5)
