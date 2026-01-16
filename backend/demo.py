#!/usr/bin/env python3
"""
Demo script for Zoning Code Agent.

Run this to demonstrate the system's capabilities without processing real forms.
Shows: CSV parsing, URL classification, handler selection, and database operations.
"""

import asyncio
import sys
import os

# Add current directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv()

from csv_reader import CSVReader
from result_store import ResultStore
from utils.url_classifier import URLClassifier
from models.enums import FormType, SubmissionStatus, FailureReason
from models.submission_result import SubmissionResult
from datetime import datetime


def print_header(title: str):
    """Print a formatted header."""
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def demo_csv_parsing(csv_path: str):
    """Demonstrate CSV parsing and classification."""
    print_header("1. CSV PARSING & URL CLASSIFICATION")

    reader = CSVReader(csv_path)
    entries = reader.read_all()

    print(f"\nLoaded {len(entries)} form entries from CSV")
    print("\nFirst 5 entries with auto-classification:\n")

    for i, entry in enumerate(entries[:5], 1):
        print(f"  [{i}] {entry.municipality}, {entry.state}")
        print(f"      URL: {entry.url[:60]}...")
        print(f"      Detected Type: {entry.form_type.name}")
        print(f"      Description: {entry.description[:50]}..." if entry.description else "")
        print()

    return entries


def demo_statistics(csv_path: str):
    """Demonstrate statistics gathering."""
    print_header("2. CSV STATISTICS")

    reader = CSVReader(csv_path)
    stats = reader.get_statistics()

    print(f"\nTotal Entries: {stats['total_entries']}")
    print(f"Unique Municipalities: {stats['unique_municipalities']}")

    print("\nBy Form Type:")
    for form_type, count in sorted(stats['by_form_type'].items()):
        print(f"  {form_type}: {count}")

    print("\nBy State (top 5):")
    sorted_states = sorted(stats['by_state'].items(), key=lambda x: -x[1])
    for state, count in sorted_states[:5]:
        print(f"  {state}: {count}")


def demo_url_classifier():
    """Demonstrate URL classification logic."""
    print_header("3. URL CLASSIFICATION EXAMPLES")

    test_urls = [
        ("https://losgatosca.nextrequest.com/requests/new", "NextRequest portal"),
        ("https://redmond-or.justfoia.com/", "JustFOIA portal"),
        ("https://drippingspringstx.govqa.us/", "GovQA portal"),
        ("https://city.com/FormCenter/PublicRecords", "CivicPlus FormCenter"),
        ("https://salisbury.gov/forms/RTKRequestForm.pdf", "PDF download"),
        ("https://forms.office.com/abc123", "Office 365 Form"),
        ("https://random-city.gov/contact-us", "Generic website"),
    ]

    print("\nURL Classification Results:\n")
    for url, description in test_urls:
        form_type = URLClassifier.classify(url)
        print(f"  {description}")
        print(f"    URL: {url}")
        print(f"    → Classified as: {form_type.name}")
        print()


def demo_handler_selection():
    """Demonstrate handler selection based on form type."""
    print_header("4. HANDLER SELECTION")

    handler_map = {
        FormType.NEXTREQUEST: "NextRequestHandler - Handles two-step login (email → password)",
        FormType.JUSTFOIA: "JustFOIAHandler - Direct form with department dropdown",
        FormType.GOVQA: "GovQAHandler - Handles guest/login options",
        FormType.CIVICPLUS: "CivicPlusHandler - Embedded FormCenter forms",
        FormType.PDF: "PDFFormHandler - Downloads and fills PDF (no browser)",
        FormType.GENERIC_WEB: "WebFormHandler - Generic browser automation",
    }

    print("\nForm Type → Handler Mapping:\n")
    for form_type, handler_desc in handler_map.items():
        print(f"  {form_type.name}")
        print(f"    → {handler_desc}")
        print()


def demo_result_storage():
    """Demonstrate result storage operations."""
    print_header("5. RESULT STORAGE (SQLite)")

    # Use in-memory database for demo
    store = ResultStore(":memory:")

    # Create sample results
    sample_results = [
        SubmissionResult(
            form_entry_id="174540_1",
            census_id="174540",
            municipality="Township of Salisbury",
            state="PA",
            url="https://salisbury.gov/form.pdf",
            status=SubmissionStatus.PDF_DOWNLOADED,
            pdf_downloaded_path="data/downloads/174540_1.pdf",
            pdf_filled_path="data/filled_pdfs/174540_1_filled.pdf",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        ),
        SubmissionResult(
            form_entry_id="062807_1",
            census_id="062807",
            municipality="Los Gatos",
            state="CA",
            url="https://losgatosca.nextrequest.com/",
            status=SubmissionStatus.SUCCESS,
            confirmation_number="REQ-12345",
            confirmation_message="Request submitted successfully",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        ),
        SubmissionResult(
            form_entry_id="123456_1",
            census_id="123456",
            municipality="Example City",
            state="TX",
            status=SubmissionStatus.CAPTCHA_BLOCKED,
            url="https://example.gov/",
            failure_reason=FailureReason.CAPTCHA,
            error_message="CAPTCHA detected on form",
            started_at=datetime.now(),
            completed_at=datetime.now(),
        ),
    ]

    # Save results
    print("\nSaving sample results to database...")
    for result in sample_results:
        store.save_result(result, batch_id="demo-batch")
        print(f"  Saved: {result.municipality} ({result.status.value})")

    # Get statistics
    print("\nDatabase Statistics:")
    stats = store.get_statistics()
    print(f"  Total records: {stats['total']}")
    print(f"  By status: {stats['by_status']}")

    # Query for PDFs
    print("\nQuerying for PDFs that need email:")
    for r in store.get_all_results():
        if r.status == SubmissionStatus.PDF_DOWNLOADED:
            print(f"  → {r.municipality}: {r.pdf_filled_path}")


def demo_integration_points():
    """Show integration points for email pipeline."""
    print_header("6. INTEGRATION POINTS FOR EMAIL PIPELINE")

    print("""
Your email pipeline can integrate in these ways:

OPTION A - Query SQLite Database:
─────────────────────────────────
    from result_store import ResultStore

    store = ResultStore("data/results.db")
    for r in store.get_all_results():
        if r.status.value == "pdf_downloaded":
            your_email_system.queue(
                pdf_path=r.pdf_filled_path,
                municipality=r.municipality
            )

OPTION B - Read Exported CSV:
─────────────────────────────
    Run: python batch_processor.py data.csv --export results.csv

    import csv
    with open('results.csv') as f:
        for row in csv.DictReader(f):
            if row['status'] == 'pdf_downloaded':
                # Process row['pdf_filled_path']

OPTION C - Hook Into BatchProcessor:
────────────────────────────────────
    Modify batch_processor.py:

    result = await handler.submit(entry)
    if result.status == SubmissionStatus.PDF_DOWNLOADED:
        your_email_pipeline.queue(result)
    """)


def main():
    """Run all demos."""
    print("\n" + "=" * 60)
    print("       ZONING CODE AGENT - DEMO")
    print("=" * 60)

    csv_path = "../sample_30_forms.csv"

    # Check if CSV exists
    if not os.path.exists(csv_path):
        csv_path = "sample_30_forms.csv"
    if not os.path.exists(csv_path):
        print(f"\nWarning: CSV file not found. Using mock data for demo.")
        csv_path = None

    if csv_path:
        demo_csv_parsing(csv_path)
        demo_statistics(csv_path)

    demo_url_classifier()
    demo_handler_selection()
    demo_result_storage()
    demo_integration_points()

    print_header("DEMO COMPLETE")
    print("""
To run the actual batch processor:

    # Process all forms
    python batch_processor.py ../sample_30_forms.csv

    # Process specific type
    python batch_processor.py ../sample_30_forms.csv --type NEXTREQUEST

    # View statistics only
    python batch_processor.py ../sample_30_forms.csv --stats

    # Export results
    python batch_processor.py ../sample_30_forms.csv --export results.csv
    """)


if __name__ == "__main__":
    main()
