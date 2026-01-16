"""
Main batch processing orchestrator for form submissions.

Usage:
    python batch_processor.py sample_30_forms.csv
    python batch_processor.py sample_30_forms.csv --rank 1
    python batch_processor.py sample_30_forms.csv --type NEXTREQUEST --limit 5
    python batch_processor.py sample_30_forms.csv --export results.csv
"""

import asyncio
import uuid
from datetime import datetime
from typing import List, Optional, Dict, Type
import argparse
import logging
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from models.form_entry import FormEntry
from models.submission_result import SubmissionResult
from models.enums import FormType, SubmissionStatus
from handlers.base_handler import BaseFormHandler
from handlers.web_form_handler import WebFormHandler
from handlers.nextrequest_handler import NextRequestHandler
from handlers.justfoia_handler import JustFOIAHandler
from handlers.govqa_handler import GovQAHandler
from handlers.civicplus_handler import CivicPlusHandler
from handlers.pdf_form_handler import PDFFormHandler
from csv_reader import CSVReader
from result_store import ResultStore
from utils.rate_limiter import RateLimiter

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BatchProcessor:
    """
    Orchestrates batch form submission processing.

    Features:
    - Automatic form type classification
    - Handler selection based on form type
    - Rate limiting between submissions
    - Resume capability (skip processed forms)
    - Result tracking in SQLite
    """

    # Register all available handlers (order matters - more specific first)
    HANDLERS: List[Type[BaseFormHandler]] = [
        NextRequestHandler,
        JustFOIAHandler,
        GovQAHandler,
        CivicPlusHandler,
        PDFFormHandler,
        WebFormHandler,  # Fallback - must be last
    ]

    def __init__(
        self,
        csv_path: str,
        db_path: str = "data/results.db",
        rate_limit_seconds: float = 30.0,
        max_retries: int = 3,
        resume: bool = True,
        headless: bool = False,
        name: Optional[str] = None,
        email: Optional[str] = None,
        address: Optional[str] = None,
        phone: Optional[str] = None,
        password: Optional[str] = None,
    ):
        """
        Initialize batch processor.

        Args:
            csv_path: Path to input CSV file
            db_path: Path to SQLite database
            rate_limit_seconds: Minimum seconds between submissions
            max_retries: Maximum retry attempts for failed submissions
            resume: Whether to skip already-processed forms
            headless: Run browser in headless mode
            name: Requester name (uses env default if not provided)
            email: Requester email
            address: Requester address
            phone: Requester phone
            password: Password for authenticated portals
        """
        self.csv_reader = CSVReader(csv_path)
        self.result_store = ResultStore(db_path)
        self.rate_limiter = RateLimiter(min_interval=rate_limit_seconds)
        self.max_retries = max_retries
        self.resume = resume
        self.headless = headless

        # Contact info for handlers
        self.contact_info = {
            'name': name,
            'email': email,
            'address': address,
            'phone': phone,
            'password': password,
            'headless': headless,
        }

        # Initialize handlers
        self._handlers: Dict[FormType, BaseFormHandler] = {}
        self._init_handlers()

        # Batch tracking
        self.batch_id = None
        self.processed_count = 0
        self.success_count = 0
        self.failure_count = 0

    def _init_handlers(self):
        """Initialize handler instances for each form type."""
        for handler_class in self.HANDLERS:
            # Only pass supported kwargs
            if handler_class == PDFFormHandler:
                handler = handler_class(
                    name=self.contact_info['name'],
                    email=self.contact_info['email'],
                    address=self.contact_info['address'],
                    phone=self.contact_info['phone'],
                )
            else:
                handler = handler_class(**self.contact_info)

            for form_type in handler_class.SUPPORTED_FORM_TYPES:
                if form_type not in self._handlers:
                    self._handlers[form_type] = handler
                    logger.debug(f"Registered {handler_class.HANDLER_NAME} for {form_type.name}")

    def get_handler(self, form_type: FormType) -> BaseFormHandler:
        """Get the appropriate handler for a form type."""
        handler = self._handlers.get(form_type)

        if not handler:
            # Fall back to generic web handler
            handler = self._handlers.get(FormType.GENERIC_WEB)

        return handler

    async def process_all(
        self,
        only_rank: Optional[int] = None,
        only_type: Optional[FormType] = None,
        only_census_id: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> Dict:
        """
        Process forms from CSV file.

        Args:
            only_rank: Only process forms with this rank (e.g., 1 for best only)
            only_type: Only process forms of this type
            only_census_id: Only process this specific municipality
            limit: Maximum number of forms to process

        Returns:
            Summary statistics dict
        """
        self.batch_id = str(uuid.uuid4())[:8]
        logger.info(f"Starting batch {self.batch_id}")

        # Read entries
        entries = self.csv_reader.read_all()
        logger.info(f"Loaded {len(entries)} form entries from CSV")

        # Filter entries
        if only_rank is not None:
            entries = [e for e in entries if e.rank == only_rank]
            logger.info(f"Filtered to rank {only_rank}: {len(entries)} entries")

        if only_type is not None:
            entries = [e for e in entries if e.form_type == only_type]
            logger.info(f"Filtered to type {only_type.name}: {len(entries)} entries")

        if only_census_id is not None:
            entries = [e for e in entries if e.census_id == only_census_id]
            logger.info(f"Filtered to census_id {only_census_id}: {len(entries)} entries")

        if limit is not None:
            entries = entries[:limit]
            logger.info(f"Limited to {limit} entries")

        # Get already processed IDs for resume
        processed_ids = set()
        if self.resume:
            processed_ids = self.result_store.get_processed_ids()
            logger.info(f"Resume mode: {len(processed_ids)} already processed")

        # Process entries
        total = len(entries)
        for i, entry in enumerate(entries, 1):
            if entry.unique_id in processed_ids:
                logger.info(f"[{i}/{total}] Skipping already processed: {entry.display_name}")
                continue

            logger.info(f"[{i}/{total}] Processing: {entry.display_name}")
            await self._process_entry(entry)

        # Return summary
        return self.get_summary()

    async def process_single(self, form_entry: FormEntry) -> SubmissionResult:
        """Process a single form entry."""
        self.batch_id = self.batch_id or str(uuid.uuid4())[:8]
        return await self._process_entry(form_entry)

    async def _process_entry(self, entry: FormEntry) -> SubmissionResult:
        """Process a single form entry."""
        logger.info(f"  URL: {entry.url}")
        logger.info(f"  Type: {entry.form_type.name if entry.form_type else 'UNKNOWN'}")

        # Rate limiting
        await self.rate_limiter.wait()

        # Get handler
        handler = self.get_handler(entry.form_type)
        logger.info(f"  Handler: {handler.HANDLER_NAME}")

        # Submit form
        result = await handler.submit(entry)

        # Save result
        self.result_store.save_result(result, batch_id=self.batch_id)

        # Update counters
        self.processed_count += 1
        if result.status in (SubmissionStatus.SUCCESS, SubmissionStatus.PDF_DOWNLOADED):
            self.success_count += 1
            logger.info(f"  RESULT: {result.status.value}")
            if result.confirmation_message:
                logger.info(f"  {result.confirmation_message}")
        else:
            self.failure_count += 1
            logger.warning(f"  RESULT: {result.status.value} - {result.failure_reason.value}")
            if result.error_message:
                logger.warning(f"  Error: {result.error_message}")

        return result

    async def retry_failed(self) -> Dict:
        """Retry previously failed submissions."""
        failed_ids = self.result_store.get_failed_ids(self.max_retries)
        logger.info(f"Found {len(failed_ids)} failed submissions to retry")

        entries = self.csv_reader.read_all()
        entry_map = {e.unique_id: e for e in entries}

        for form_entry_id in failed_ids:
            if form_entry_id in entry_map:
                entry = entry_map[form_entry_id]
                logger.info(f"Retrying: {entry.display_name}")
                await self._process_entry(entry)

        return self.get_summary()

    def get_summary(self) -> Dict:
        """Get processing summary."""
        db_stats = self.result_store.get_statistics(batch_id=self.batch_id)

        return {
            'batch_id': self.batch_id,
            'processed': self.processed_count,
            'success': self.success_count,
            'failed': self.failure_count,
            'success_rate': (
                self.success_count / self.processed_count * 100
                if self.processed_count > 0 else 0
            ),
            'database_stats': db_stats,
        }

    def print_summary(self):
        """Print a formatted summary."""
        summary = self.get_summary()

        print("\n" + "=" * 60)
        print("BATCH PROCESSING COMPLETE")
        print("=" * 60)
        print(f"Batch ID:     {summary['batch_id']}")
        print(f"Processed:    {summary['processed']}")
        print(f"Success:      {summary['success']}")
        print(f"Failed:       {summary['failed']}")
        print(f"Success Rate: {summary['success_rate']:.1f}%")

        if summary['database_stats']['by_status']:
            print("\nBy Status:")
            for status, count in summary['database_stats']['by_status'].items():
                print(f"  {status}: {count}")

        if summary['database_stats']['by_failure_reason']:
            print("\nFailure Reasons:")
            for reason, count in summary['database_stats']['by_failure_reason'].items():
                print(f"  {reason}: {count}")

    def export_results(self, output_path: str):
        """Export results to CSV."""
        self.result_store.export_csv(output_path, batch_id=self.batch_id)

    def show_csv_stats(self):
        """Show statistics about the CSV file."""
        stats = self.csv_reader.get_statistics()

        print("\n" + "=" * 60)
        print("CSV FILE STATISTICS")
        print("=" * 60)
        print(f"Total Entries:          {stats['total_entries']}")
        print(f"Unique Municipalities:  {stats['unique_municipalities']}")

        print("\nBy Form Type:")
        for form_type, count in sorted(stats['by_form_type'].items()):
            print(f"  {form_type}: {count}")

        print("\nBy State:")
        for state, count in sorted(stats['by_state'].items(), key=lambda x: -x[1]):
            print(f"  {state}: {count}")


async def main():
    """Command-line entry point for batch processing."""
    parser = argparse.ArgumentParser(
        description='Batch process public records request forms',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python batch_processor.py ../sample_30_forms.csv
  python batch_processor.py ../sample_30_forms.csv --rank 1
  python batch_processor.py ../sample_30_forms.csv --type NEXTREQUEST
  python batch_processor.py ../sample_30_forms.csv --stats
  python batch_processor.py ../sample_30_forms.csv --export results.csv
        """
    )

    parser.add_argument('csv_file', help='Path to input CSV file')
    parser.add_argument('--db', default='data/results.db', help='Database path')
    parser.add_argument('--rate-limit', type=float, default=30.0,
                        help='Seconds between submissions (default: 30)')
    parser.add_argument('--no-resume', action='store_true',
                        help='Process all entries, ignoring prior runs')
    parser.add_argument('--headless', action='store_true',
                        help='Hide browser window (default: browser is VISIBLE for demos)')
    parser.add_argument('--rank', type=int,
                        help='Only process entries with this rank (1=best)')
    parser.add_argument('--type', dest='form_type',
                        help='Only process this form type (e.g., NEXTREQUEST, PDF)')
    parser.add_argument('--census-id',
                        help='Only process this specific municipality')
    parser.add_argument('--limit', type=int,
                        help='Maximum number of forms to process')
    parser.add_argument('--export',
                        help='Export results to CSV file after processing')
    parser.add_argument('--stats', action='store_true',
                        help='Show CSV statistics and exit')
    parser.add_argument('--retry-failed', action='store_true',
                        help='Retry previously failed submissions')

    args = parser.parse_args()

    # Create processor
    processor = BatchProcessor(
        csv_path=args.csv_file,
        db_path=args.db,
        rate_limit_seconds=args.rate_limit,
        resume=not args.no_resume,
        headless=args.headless,
    )

    # Just show stats if requested
    if args.stats:
        processor.show_csv_stats()
        return

    # Parse form type if provided
    form_type = None
    if args.form_type:
        try:
            form_type = FormType[args.form_type.upper()]
        except KeyError:
            valid_types = [t.name for t in FormType]
            print(f"Error: Unknown form type '{args.form_type}'")
            print(f"Valid types: {', '.join(valid_types)}")
            sys.exit(1)

    # Process
    if args.retry_failed:
        await processor.retry_failed()
    else:
        await processor.process_all(
            only_rank=args.rank,
            only_type=form_type,
            only_census_id=args.census_id,
            limit=args.limit,
        )

    # Print summary
    processor.print_summary()

    # Export if requested
    if args.export:
        processor.export_results(args.export)
        print(f"\nResults exported to: {args.export}")


if __name__ == '__main__':
    asyncio.run(main())
