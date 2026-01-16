# Zoning Code Agent

**Automated submission of public records requests to U.S. municipalities for historical zoning codes.**

This system automates the process of submitting public records requests to municipal websites, handling various form types (web portals, PDFs) across different platforms (NextRequest, JustFOIA, GovQA, CivicPlus, etc.).

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Quick Start](#quick-start)
4. [Usage Examples](#usage-examples)
5. [How It Works](#how-it-works)
6. [Integration Points](#integration-points)
7. [Configuration](#configuration)
8. [Form Types Supported](#form-types-supported)
9. [Data Flow](#data-flow)
10. [Extending the System](#extending-the-system)

---

## Overview

### What It Does

1. **Reads a CSV file** containing municipality form URLs and metadata
2. **Classifies each URL** into a form type (NextRequest, JustFOIA, PDF, etc.)
3. **Selects the appropriate handler** for each form type
4. **Submits the request** using browser automation (for web forms) or PDF filling
5. **Tracks results** in a SQLite database for reporting and resume capability

### The Standard Request

Every submission uses this standardized text:

> "Could you please send me {municipality}'s municipal zoning code as of 1940? If a zoning code didn't exist then, could you send me the first post 1940 adoption of the zoning code?"

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         BATCH PROCESSOR                              │
│                      (batch_processor.py)                            │
│  - Orchestrates the entire process                                   │
│  - Handles rate limiting, resume, error tracking                     │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                           CSV READER                                 │
│                        (csv_reader.py)                               │
│  - Parses input CSV file                                             │
│  - Auto-classifies URLs → FormType                                   │
│  - Creates FormEntry objects with all metadata                       │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         HANDLER SELECTION                            │
│                                                                      │
│   URL contains...           →    Handler Used                        │
│   ─────────────────────────────────────────────                      │
│   *.nextrequest.com         →    NextRequestHandler                  │
│   *.justfoia.com            →    JustFOIAHandler                     │
│   *.govqa.us                →    GovQAHandler                        │
│   /FormCenter/              →    CivicPlusHandler                    │
│   *.pdf                     →    PDFFormHandler                      │
│   (other)                   →    WebFormHandler (generic)            │
└─────────────────────────────────────────────────────────────────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    ▼                              ▼
┌─────────────────────────────┐    ┌─────────────────────────────┐
│      WEB FORM HANDLERS      │    │      PDF FORM HANDLER       │
│                             │    │                             │
│  Uses browser-use agent     │    │  1. Downloads PDF           │
│  to fill web forms          │    │  2. Fills form fields       │
│                             │    │  3. Saves filled PDF        │
│  - Handles login flows      │    │                             │
│  - Fills all fields         │    │  (No email - manual step)   │
│  - Submits form             │    │                             │
└─────────────────────────────┘    └─────────────────────────────┘
                    │                              │
                    └──────────────┬──────────────┘
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                          RESULT STORE                                │
│                        (result_store.py)                             │
│                                                                      │
│  SQLite database tracking:                                           │
│  - Success/failure status                                            │
│  - Confirmation numbers                                              │
│  - Error messages                                                    │
│  - PDF file paths                                                    │
│  - Timestamps                                                        │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Quick Start

### 1. Install Dependencies

```bash
cd backend
pip install -r requirements.txt
```

### 2. Configure Environment

Create `backend/.env`:

```env
# LLM Configuration (OpenRouter)
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet

# Default Contact Information (used for all submissions)
DEFAULT_NAME=Your Name
DEFAULT_EMAIL=your.email@example.com
DEFAULT_ADDRESS=123 Main St, City, State 12345
DEFAULT_PHONE=555-123-4567
DEFAULT_PASSWORD=your_portal_password
```

### 3. Install Browser

```bash
uvx browser-use install
```

### 4. Run

```bash
# See what's in the CSV
python batch_processor.py ../sample_30_forms.csv --stats

# Process forms
python batch_processor.py ../sample_30_forms.csv --limit 3
```

---

## Usage Examples

### Example 1: View CSV Statistics

```bash
$ python batch_processor.py ../sample_30_forms.csv --stats

============================================================
CSV FILE STATISTICS
============================================================
Total Entries:          47
Unique Municipalities:  30

By Form Type:
  CIVICPLUS: 8
  GENERIC_WEB: 12
  GOVQA: 3
  JUSTFOIA: 6
  NEXTREQUEST: 4
  PDF: 10
  STATE_PORTAL: 4

By State:
  PA: 8
  TX: 7
  CA: 6
  ...
```

### Example 2: Process Only NextRequest Forms

```bash
$ python batch_processor.py ../sample_30_forms.csv --type NEXTREQUEST

2024-01-15 10:30:00 - INFO - Starting batch a1b2c3d4
2024-01-15 10:30:00 - INFO - Loaded 47 form entries from CSV
2024-01-15 10:30:00 - INFO - Filtered to type NEXTREQUEST: 4 entries

[1/4] Processing: Los Gatos, CA (Rank 1)
  URL: https://losgatosca.nextrequest.com/requests/new
  Type: NEXTREQUEST
  Handler: nextrequest
  RESULT: success
  Form submitted successfully

[2/4] Processing: Bell Gardens, CA (Rank 1)
  ...

============================================================
BATCH PROCESSING COMPLETE
============================================================
Batch ID:     a1b2c3d4
Processed:    4
Success:      3
Failed:       1
Success Rate: 75.0%
```

### Example 3: Process Rank 1 Forms Only (Best Option per Municipality)

```bash
$ python batch_processor.py ../sample_30_forms.csv --rank 1 --limit 5
```

### Example 4: Process PDF Forms

```bash
$ python batch_processor.py ../sample_30_forms.csv --type PDF --limit 2

[1/2] Processing: Township of Salisbury, PA (Rank 1)
  URL: https://salisburylehighpa.gov/.../RTKRequestForm.pdf
  Type: PDF
  Handler: pdf_form
  RESULT: pdf_downloaded
  PDF downloaded and filled. Filled 4 fields

# PDFs saved to:
#   backend/data/downloads/174540_1_Township_of_Salisbury.pdf
#   backend/data/filled_pdfs/174540_1_filled.pdf
```

### Example 5: Resume After Interruption

```bash
# First run (interrupted after 10 forms)
$ python batch_processor.py ../sample_30_forms.csv
^C  # Ctrl+C to stop

# Resume - automatically skips already-processed forms
$ python batch_processor.py ../sample_30_forms.csv
2024-01-15 11:00:00 - INFO - Resume mode: 10 already processed
[11/47] Processing: Next Municipality...
```

### Example 6: Export Results

```bash
$ python batch_processor.py ../sample_30_forms.csv --export results.csv

# Creates results.csv with columns:
# form_entry_id, municipality, state, status, confirmation_number,
# pdf_downloaded_path, pdf_filled_path, error_message, ...
```

---

## How It Works

### Step-by-Step Process

```
1. INPUT
   ┌─────────────────────────────────────────────────────────────┐
   │ sample_30_forms.csv                                         │
   │                                                             │
   │ census_id | municipality        | state | rank | url        │
   │ ─────────────────────────────────────────────────────────── │
   │ 174540    | Township of Salisbury | PA   | 1    | https://...│
   │ 174540    | Township of Salisbury | PA   | 2    | https://...│
   │ 062807    | Los Gatos            | CA   | 1    | https://...│
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
2. CLASSIFICATION
   ┌─────────────────────────────────────────────────────────────┐
   │ URLClassifier analyzes each URL:                            │
   │                                                             │
   │ "losgatosca.nextrequest.com"  →  NEXTREQUEST               │
   │ "salisburylehighpa.gov/...pdf" →  PDF                       │
   │ "redmond-or.justfoia.com"     →  JUSTFOIA                  │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
3. HANDLER DISPATCH
   ┌─────────────────────────────────────────────────────────────┐
   │ Each FormType gets its specialized handler:                 │
   │                                                             │
   │ NEXTREQUEST → NextRequestHandler                            │
   │   - Knows about two-step login (email → password)           │
   │   - Knows NextRequest form structure                        │
   │                                                             │
   │ PDF → PDFFormHandler                                        │
   │   - Downloads the PDF file                                  │
   │   - Attempts to fill form fields                            │
   │   - Saves filled PDF for manual email                       │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
4. FORM SUBMISSION (Web Forms)
   ┌─────────────────────────────────────────────────────────────┐
   │ Browser-use agent receives detailed prompt:                 │
   │                                                             │
   │ "Navigate to https://losgatosca.nextrequest.com/...        │
   │                                                             │
   │  CONTEXT FROM DATABASE:                                     │
   │  Direct NextRequest submission page for Los Gatos.          │
   │                                                             │
   │  Fill with:                                                 │
   │  - Name: John Doe                                           │
   │  - Email: john@example.com                                  │
   │  - Request: Could you please send me Los Gatos's...        │
   │  ..."                                                       │
   │                                                             │
   │ Agent autonomously:                                         │
   │ 1. Navigates to URL                                         │
   │ 2. Handles login if needed                                  │
   │ 3. Fills all form fields                                    │
   │ 4. Submits and captures confirmation                        │
   └─────────────────────────────────────────────────────────────┘
                              │
                              ▼
5. RESULT STORAGE
   ┌─────────────────────────────────────────────────────────────┐
   │ SQLite database (data/results.db):                          │
   │                                                             │
   │ form_entry_id: "062807_1"                                   │
   │ municipality: "Los Gatos"                                   │
   │ status: "success"                                           │
   │ confirmation_message: "Request #12345 submitted"            │
   │ completed_at: "2024-01-15T10:35:22"                         │
   └─────────────────────────────────────────────────────────────┘
```

---

## Integration Points

### Where Email Pipeline Connects

The system is designed with clear integration points for your email pipeline:

```
┌─────────────────────────────────────────────────────────────────────┐
│                      YOUR EMAIL PIPELINE                             │
└─────────────────────────────────────────────────────────────────────┘
                              │
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
   ┌───────────┐       ┌───────────┐       ┌───────────┐
   │  OPTION A │       │  OPTION B │       │  OPTION C │
   │           │       │           │       │           │
   │  Query    │       │  Read     │       │  Hook     │
   │  SQLite   │       │  Export   │       │  Into     │
   │  Database │       │  CSV      │       │  Handler  │
   └───────────┘       └───────────┘       └───────────┘
```

#### Option A: Query the SQLite Database Directly

```python
from result_store import ResultStore

store = ResultStore("data/results.db")

# Get all successful submissions
results = store.get_all_results()
for r in results:
    if r.status.value == "success":
        print(f"{r.municipality}: {r.confirmation_message}")

# Get PDFs that need manual email
pdf_results = [r for r in results if r.status.value == "pdf_downloaded"]
for r in pdf_results:
    print(f"Email {r.pdf_filled_path} to {r.municipality}")
```

#### Option B: Use the Exported CSV

```bash
python batch_processor.py sample_30_forms.csv --export results.csv
```

Then read `results.csv` in your pipeline:

```python
import csv

with open('results.csv') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row['status'] == 'pdf_downloaded':
            # This PDF needs to be emailed
            pdf_path = row['pdf_filled_path']
            municipality = row['municipality']
            # ... your email code here
```

#### Option C: Add a Post-Processing Hook

Modify `batch_processor.py` to call your email function:

```python
# In BatchProcessor._process_entry()

result = await handler.submit(entry)
self.result_store.save_result(result, batch_id=self.batch_id)

# INTEGRATION POINT: Call your email pipeline here
if result.status == SubmissionStatus.PDF_DOWNLOADED:
    # Your email function
    your_email_pipeline.queue_pdf_email(
        pdf_path=result.pdf_filled_path,
        municipality=result.municipality,
        state=result.state
    )
```

### Key Objects for Integration

#### SubmissionResult

Every form submission returns a `SubmissionResult` with these fields:

```python
@dataclass
class SubmissionResult:
    # Identification
    form_entry_id: str      # e.g., "174540_1"
    census_id: str          # e.g., "174540"
    municipality: str       # e.g., "Township of Salisbury"
    state: str              # e.g., "PA"
    url: str                # The form URL

    # Status
    status: SubmissionStatus  # SUCCESS, FAILED, PDF_DOWNLOADED, etc.
    failure_reason: FailureReason  # CAPTCHA, TIMEOUT, etc.

    # Results
    confirmation_number: str  # If the portal gave one
    confirmation_message: str # Success message

    # PDF-specific (for your email pipeline)
    pdf_downloaded_path: str  # e.g., "data/downloads/174540_1.pdf"
    pdf_filled_path: str      # e.g., "data/filled_pdfs/174540_1_filled.pdf"

    # Debugging
    error_message: str
    agent_output: str  # Full agent response
```

#### Status Values

```python
class SubmissionStatus(Enum):
    SUCCESS = "success"           # Web form submitted successfully
    PDF_DOWNLOADED = "pdf_downloaded"  # PDF downloaded (needs email)
    FAILED = "failed"             # Something went wrong
    CAPTCHA_BLOCKED = "captcha_blocked"  # Hit a CAPTCHA
    LOGIN_REQUIRED = "login_required"    # Couldn't authenticate
    SKIPPED = "skipped"           # Intentionally skipped
```

---

## Configuration

### Environment Variables

| Variable | Description | Example |
|----------|-------------|---------|
| `OPENROUTER_API_KEY` | API key for LLM | `sk-or-...` |
| `OPENROUTER_MODEL` | Model to use | `anthropic/claude-3.5-sonnet` |
| `DEFAULT_NAME` | Name for all submissions | `John Doe` |
| `DEFAULT_EMAIL` | Email for all submissions | `john@example.com` |
| `DEFAULT_ADDRESS` | Address for all submissions | `123 Main St, City, ST 12345` |
| `DEFAULT_PHONE` | Phone (optional) | `555-123-4567` |
| `DEFAULT_PASSWORD` | Password for authenticated portals | `password123` |

### CLI Options

```
python batch_processor.py <csv_file> [options]

Options:
  --stats           Show CSV statistics and exit
  --rank N          Only process forms with this rank (1=best)
  --type TYPE       Only process this form type (NEXTREQUEST, PDF, etc.)
  --census-id ID    Only process this specific municipality
  --limit N         Maximum forms to process
  --rate-limit N    Seconds between submissions (default: 30)
  --no-resume       Don't skip already-processed forms
  --headless        Run browser without visible window
  --export FILE     Export results to CSV
  --retry-failed    Retry previously failed submissions
```

---

## Form Types Supported

| Type | Platform | How Detected | Handler |
|------|----------|--------------|---------|
| `NEXTREQUEST` | NextRequest.com | `*.nextrequest.com` | Handles two-step login |
| `JUSTFOIA` | JustFOIA.com | `*.justfoia.com` | Direct form fill |
| `GOVQA` | GovQA.us | `*.govqa.us` | Handles guest/login options |
| `CIVICPLUS` | CivicPlus FormCenter | `/FormCenter/` in URL | Embedded form detection |
| `PDF` | PDF Downloads | `.pdf` extension | Download + fill + save |
| `OFFICE365` | Microsoft Forms | `forms.office.com` | Generic web handling |
| `STATE_PORTAL` | State records portals | `openrecords.pa.gov`, etc. | Generic web handling |
| `GENERIC_WEB` | Everything else | Default | Generic browser automation |

---

## Data Flow

```
┌──────────────────┐
│ sample_30_forms  │
│     .csv         │
└────────┬─────────┘
         │
         ▼
┌──────────────────┐     ┌──────────────────┐
│   CSVReader      │────▶│   FormEntry      │
│                  │     │   objects        │
└──────────────────┘     └────────┬─────────┘
                                  │
                                  ▼
                         ┌──────────────────┐
                         │ BatchProcessor   │
                         │                  │
                         │ For each entry:  │
                         │ 1. Rate limit    │
                         │ 2. Get handler   │
                         │ 3. Submit        │
                         │ 4. Store result  │
                         └────────┬─────────┘
                                  │
              ┌───────────────────┼───────────────────┐
              ▼                   ▼                   ▼
     ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
     │ Web Handler  │    │ PDF Handler  │    │ Result Store │
     │              │    │              │    │              │
     │ browser-use  │    │ Download &   │    │ SQLite DB    │
     │ agent fills  │    │ fill PDF     │    │              │
     │ web form     │    │              │    │ Track status │
     └──────────────┘    └──────┬───────┘    └──────────────┘
                                │
                                ▼
                       ┌──────────────────┐
                       │ data/filled_pdfs │
                       │                  │
                       │ PDFs ready for   │
                       │ manual email     │
                       └──────────────────┘
```

---

## Extending the System

### Adding a New Portal Handler

1. Create `backend/handlers/newportal_handler.py`:

```python
from .web_form_handler import WebFormHandler
from models.enums import FormType

class NewPortalHandler(WebFormHandler):
    SUPPORTED_FORM_TYPES = [FormType.NEWPORTAL]
    HANDLER_NAME = "newportal"

    def build_task_prompt(self, form_entry, additional_fields=None):
        return f"""
        Navigate to {form_entry.url} - this is a NewPortal site.

        CONTEXT: {form_entry.description}

        [Portal-specific instructions...]

        Fill with:
        - Name: {self.name}
        - Email: {self.email}
        ...
        """
```

2. Add to `models/enums.py`:

```python
class FormType(Enum):
    ...
    NEWPORTAL = auto()
```

3. Add pattern to `utils/url_classifier.py`:

```python
PATTERNS = [
    ...
    (r'\.newportal\.com', FormType.NEWPORTAL),
]
```

4. Register in `handlers/__init__.py` and `batch_processor.py`

---

## File Reference

```
backend/
├── batch_processor.py    # Main CLI entry point
├── csv_reader.py         # Parses input CSV
├── result_store.py       # SQLite result storage
├── form_filler.py        # Original single-form script (legacy)
├── requirements.txt      # Python dependencies
├── .env                  # Configuration (not in git)
│
├── models/
│   ├── enums.py          # FormType, SubmissionStatus, FailureReason
│   ├── form_entry.py     # FormEntry dataclass
│   └── submission_result.py  # SubmissionResult dataclass
│
├── handlers/
│   ├── base_handler.py       # Abstract base class
│   ├── web_form_handler.py   # Generic browser automation
│   ├── nextrequest_handler.py
│   ├── justfoia_handler.py
│   ├── govqa_handler.py
│   ├── civicplus_handler.py
│   └── pdf_form_handler.py
│
├── utils/
│   ├── url_classifier.py  # URL → FormType mapping
│   └── rate_limiter.py    # Async rate limiting
│
└── data/
    ├── results.db         # SQLite database
    ├── downloads/         # Raw downloaded PDFs
    └── filled_pdfs/       # Filled PDFs ready to email
```

---

## Questions?

This system is designed to be modular and extensible. The key integration point for your email pipeline is the `SubmissionResult` object and the `ResultStore` database.

For PDFs specifically, after running the batch processor:
1. Check `data/filled_pdfs/` for filled PDFs
2. Query the database for `status = 'pdf_downloaded'`
3. Email those PDFs to the appropriate municipality contacts
