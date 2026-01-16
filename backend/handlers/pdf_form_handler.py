"""Handler for PDF form downloads - downloads and fills PDFs (no email)."""

import os
import asyncio
from pathlib import Path
from typing import Optional, Dict, Any, List
from datetime import datetime
import aiohttp
import logging

from .base_handler import BaseFormHandler
from models.form_entry import FormEntry
from models.submission_result import SubmissionResult
from models.enums import SubmissionStatus, FailureReason, FormType

logger = logging.getLogger(__name__)

# PDF library imports with fallbacks
try:
    from PyPDF2 import PdfReader, PdfWriter
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False
    logger.warning("PyPDF2 not installed - PDF filling will be limited")

try:
    from fillpdf import fillpdfs
    HAS_FILLPDF = True
except ImportError:
    HAS_FILLPDF = False
    logger.warning("fillpdf not installed - PDF filling will be limited")


class PDFFormHandler(BaseFormHandler):
    """
    Handler for PDF form downloads.
    Downloads PDF and attempts to fill form fields.
    Does NOT send email - user must manually submit.
    """

    SUPPORTED_FORM_TYPES = [FormType.PDF]
    HANDLER_NAME = "pdf_form"

    def __init__(
        self,
        name: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        download_dir: str = "data/downloads",
        filled_dir: str = "data/filled_pdfs",
        **kwargs
    ):
        super().__init__(name, email, address, phone)

        self.download_dir = Path(download_dir)
        self.filled_dir = Path(filled_dir)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.filled_dir.mkdir(parents=True, exist_ok=True)

    async def submit(
        self,
        form_entry: FormEntry,
        additional_fields: Optional[Dict[str, Any]] = None,
    ) -> SubmissionResult:
        """Download PDF and attempt to fill it."""

        started_at = datetime.now()

        try:
            # Step 1: Download PDF
            logger.info(f"Downloading PDF from {form_entry.url}")
            pdf_path = await self._download_pdf(form_entry)

            if not pdf_path:
                return self.create_result(
                    form_entry,
                    SubmissionStatus.FAILED,
                    failure_reason=FailureReason.NETWORK_ERROR,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    error_message="Failed to download PDF"
                )

            # Step 2: Try to fill PDF form fields
            logger.info(f"Attempting to fill PDF form")
            filled_path, fill_message = await self._fill_pdf(form_entry, pdf_path, additional_fields)

            if filled_path:
                return self.create_result(
                    form_entry,
                    SubmissionStatus.PDF_DOWNLOADED,
                    failure_reason=FailureReason.NONE,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    pdf_downloaded_path=str(pdf_path),
                    pdf_filled_path=str(filled_path),
                    confirmation_message=f"PDF downloaded and filled. {fill_message}"
                )
            else:
                # PDF downloaded but couldn't fill (might be non-fillable)
                return self.create_result(
                    form_entry,
                    SubmissionStatus.PDF_DOWNLOADED,
                    failure_reason=FailureReason.PDF_FILL_ERROR,
                    started_at=started_at,
                    completed_at=datetime.now(),
                    pdf_downloaded_path=str(pdf_path),
                    error_message=fill_message,
                    confirmation_message=f"PDF downloaded but could not auto-fill: {fill_message}"
                )

        except Exception as e:
            logger.exception(f"Error processing PDF form for {form_entry.display_name}")
            return self.create_result(
                form_entry,
                SubmissionStatus.FAILED,
                failure_reason=FailureReason.UNKNOWN,
                started_at=started_at,
                completed_at=datetime.now(),
                error_message=str(e)
            )

    async def _download_pdf(self, form_entry: FormEntry) -> Optional[Path]:
        """Download PDF from URL."""
        filename = f"{form_entry.census_id}_{form_entry.rank}_{form_entry.municipality.replace(' ', '_')}.pdf"
        filepath = self.download_dir / filename

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(form_entry.url, timeout=aiohttp.ClientTimeout(total=60)) as response:
                    if response.status == 200:
                        content = await response.read()

                        # Verify it's actually a PDF
                        if content[:4] == b'%PDF':
                            filepath.write_bytes(content)
                            logger.info(f"Downloaded PDF to {filepath}")
                            return filepath
                        else:
                            logger.warning(f"Downloaded content is not a PDF: {form_entry.url}")
                            return None
                    else:
                        logger.error(f"Failed to download PDF: HTTP {response.status}")
                        return None
        except Exception as e:
            logger.error(f"Error downloading PDF: {e}")
            return None

    async def _fill_pdf(
        self,
        form_entry: FormEntry,
        pdf_path: Path,
        additional_fields: Optional[Dict[str, Any]] = None
    ) -> tuple[Optional[Path], str]:
        """
        Attempt to fill PDF form fields.

        Returns:
            Tuple of (filled_path or None, message describing result)
        """
        if not HAS_FILLPDF and not HAS_PYPDF2:
            return None, "No PDF library available (install PyPDF2 or fillpdf)"

        request_text = self.get_request_text(form_entry.municipality)

        # Values to fill
        field_values = {
            'name': self.name,
            'requestor': self.name,
            'requester': self.name,
            'applicant': self.name,
            'email': self.email,
            'e-mail': self.email,
            'address': self.address,
            'street': self.address,
            'mailing': self.address,
            'phone': self.phone,
            'telephone': self.phone,
            'description': request_text,
            'request': request_text,
            'records': request_text,
            'date': datetime.now().strftime('%m/%d/%Y'),
            'today': datetime.now().strftime('%m/%d/%Y'),
        }

        if additional_fields:
            field_values.update(additional_fields)

        filled_filename = f"{form_entry.census_id}_{form_entry.rank}_filled.pdf"
        filled_path = self.filled_dir / filled_filename

        # Run in executor to not block async loop
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._fill_pdf_sync,
            pdf_path,
            filled_path,
            field_values
        )

        return result

    def _fill_pdf_sync(
        self,
        input_path: Path,
        output_path: Path,
        field_values: Dict[str, str]
    ) -> tuple[Optional[Path], str]:
        """Synchronous PDF filling."""

        # Try fillpdf first (better field detection)
        if HAS_FILLPDF:
            try:
                # Get form fields from PDF
                form_fields = fillpdfs.get_form_fields(str(input_path))

                if not form_fields:
                    return None, "PDF has no fillable form fields"

                logger.info(f"Found {len(form_fields)} form fields in PDF")

                # Map our values to PDF field names
                mapped_values = self._map_fields_to_pdf(field_values, form_fields)

                if not mapped_values:
                    return None, f"Could not map values to PDF fields. Fields found: {list(form_fields.keys())[:5]}"

                # Fill the form
                fillpdfs.write_fillable_pdf(
                    str(input_path),
                    str(output_path),
                    mapped_values,
                    flatten=False
                )

                return output_path, f"Filled {len(mapped_values)} fields"

            except Exception as e:
                logger.warning(f"fillpdf failed: {e}")

        # Fall back to PyPDF2
        if HAS_PYPDF2:
            try:
                reader = PdfReader(str(input_path))

                # Check for form fields
                if '/AcroForm' not in reader.trailer.get('/Root', {}):
                    return None, "PDF has no AcroForm (not a fillable PDF)"

                fields = reader.get_form_text_fields()
                if not fields:
                    return None, "PDF has no text form fields"

                logger.info(f"Found {len(fields)} text fields via PyPDF2")

                writer = PdfWriter()
                for page in reader.pages:
                    writer.add_page(page)

                mapped_values = self._map_fields_to_pdf(field_values, fields)

                if mapped_values:
                    writer.update_page_form_field_values(
                        writer.pages[0],
                        mapped_values
                    )

                    with open(output_path, 'wb') as f:
                        writer.write(f)

                    return output_path, f"Filled {len(mapped_values)} fields"
                else:
                    return None, f"Could not map values to PDF fields. Fields: {list(fields.keys())[:5]}"

            except Exception as e:
                logger.warning(f"PyPDF2 failed: {e}")
                return None, f"PyPDF2 error: {str(e)}"

        return None, "No PDF library succeeded"

    def _map_fields_to_pdf(
        self,
        our_values: Dict[str, str],
        pdf_fields: Dict[str, Any]
    ) -> Dict[str, str]:
        """Map our field values to actual PDF field names using fuzzy matching."""
        mapped = {}
        pdf_field_names = list(pdf_fields.keys())

        for pdf_field in pdf_field_names:
            pdf_field_lower = pdf_field.lower()

            # Try to match each of our values to this PDF field
            for our_key, our_value in our_values.items():
                if not our_value:
                    continue

                # Check if our key appears in the PDF field name
                if our_key in pdf_field_lower:
                    mapped[pdf_field] = our_value
                    break

        return mapped

    def get_field_names(self, pdf_path: Path) -> List[str]:
        """Get list of fillable field names from a PDF."""
        if HAS_FILLPDF:
            try:
                fields = fillpdfs.get_form_fields(str(pdf_path))
                return list(fields.keys()) if fields else []
            except Exception:
                pass

        if HAS_PYPDF2:
            try:
                reader = PdfReader(str(pdf_path))
                fields = reader.get_form_text_fields()
                return list(fields.keys()) if fields else []
            except Exception:
                pass

        return []
