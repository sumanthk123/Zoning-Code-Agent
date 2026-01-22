# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zoning Code Agent** - Automated submission of public records requests to U.S. municipalities for historical zoning codes (1940 or first post-1940 adoption).

### Standard Request Text
"Could you please send me {municipality}'s municipal zoning code as of 1940? If a zoning code didn't exist then, could you send me the first post 1940 adoption of the zoning code?"

## Commands

### Backend (Python)
```bash
source venv/bin/activate              # Activate virtual environment
pip install -r backend/requirements.txt

# Main batch processor (recommended)
python backend/batch_processor.py sample_30_forms.csv --stats    # View statistics
python backend/batch_processor.py sample_30_forms.csv --limit 5  # Process 5 forms
python backend/batch_processor.py sample_30_forms.csv --type PDF # Process PDFs only

# Demo script (no real submissions)
python backend/demo.py

# Legacy single-form script
python backend/form_filler.py
```

## Architecture

### System Overview
```
batch_processor.py          # Main CLI orchestrator
├── csv_reader.py           # Parses CSV, auto-classifies URLs
├── result_store.py         # SQLite storage for results
├── utils/
│   ├── url_classifier.py   # URL → FormType mapping
│   └── rate_limiter.py     # Async rate limiting
├── models/
│   ├── enums.py            # FormType, SubmissionStatus, FailureReason
│   ├── form_entry.py       # Input data model
│   └── submission_result.py # Output data model
└── handlers/
    ├── base_handler.py     # Abstract base class
    ├── web_form_handler.py # Browser-use Cloud API integration
    ├── nextrequest_handler.py
    ├── justfoia_handler.py
    ├── govqa_handler.py
    ├── civicplus_handler.py
    └── pdf_form_handler.py # Downloads & fills PDFs
```

### Core Flow
1. **CSV Reader** parses input file, auto-classifies each URL into a FormType
2. **Batch Processor** selects appropriate handler for each form
3. **Handler** executes submission via browser-use Cloud API (or PDF download)
4. **Result Store** saves outcome to SQLite for tracking/resume
5. **PDF forms** are downloaded and filled locally (no email - manual step)

### Handler Selection
| URL Pattern | FormType | Handler |
|-------------|----------|---------|
| `*.nextrequest.com` | NEXTREQUEST | NextRequestHandler |
| `*.justfoia.com` | JUSTFOIA | JustFOIAHandler |
| `*.govqa.us` | GOVQA | GovQAHandler |
| `/FormCenter/` | CIVICPLUS | CivicPlusHandler |
| `*.pdf` | PDF | PDFFormHandler |
| (other) | GENERIC_WEB | WebFormHandler |

## Configuration

### Environment Variables (`backend/.env`)
```
# Browser-use Cloud API (get key at https://cloud.browser-use.com)
BROWSER_USE_API_KEY=your_key_here

# Default contact info for form filling
DEFAULT_NAME=Your Name
DEFAULT_EMAIL=you@email.com
DEFAULT_ADDRESS=123 Main St, City, State ZIP
DEFAULT_PHONE=555-1234
DEFAULT_PASSWORD=password  # For sites requiring login
```

### CLI Options
```
python batch_processor.py <csv_file> [options]

--stats           Show CSV statistics only
--type TYPE       Process only this form type (NEXTREQUEST, PDF, etc.)
--rank N          Process only forms with this rank (1 = best)
--limit N         Maximum forms to process
--rate-limit N    Seconds between submissions (default: 30)
--no-resume       Don't skip already-processed forms
--export FILE     Export results to CSV
--retry-failed    Retry previously failed submissions
```

## Data Format

### Input: `sample_30_forms.csv`
| Column | Description |
|--------|-------------|
| `census_id` | Unique municipality identifier |
| `municipality` | Municipality name |
| `state` | State abbreviation |
| `rank` | URL priority (1 = best option) |
| `url` | Form URL |
| `description` | Context passed to agent for navigation |

### Output: SQLite Database (`backend/data/results.db`)
| Field | Description |
|-------|-------------|
| `form_entry_id` | Links to CSV entry |
| `status` | SUCCESS, PDF_DOWNLOADED, FAILED, CAPTCHA_BLOCKED |
| `confirmation_number` | If portal provided one |
| `pdf_downloaded_path` | Where PDF was saved |
| `pdf_filled_path` | Where filled PDF was saved |
| `error_message` | Details if failed |

## Form Types Handled
- **Web forms**: NextRequest, JustFOIA, GovQA, CivicPlus FormCenter
- **PDF forms**: Downloaded and auto-filled (requires manual email)
- **Generic web**: Any other form using browser automation

## Agent Behavior
- Fills ALL fields, makes educated guesses for missing info
- Handles date fields by typing MM/DD/YYYY first, falls back to calendar
- Closes pop-ups/cookie banners automatically
- Stops on CAPTCHA (reports CAPTCHA_BLOCKED status)
- PDF forms: Downloads, fills fields, saves to `data/filled_pdfs/`
- For historical zoning, uses date range 01/01/1940 to 12/31/1945

## Key Integration Points

### For Email Pipeline
```python
from result_store import ResultStore

store = ResultStore("data/results.db")
for r in store.get_all_results():
    if r.status.value == "pdf_downloaded":
        # This PDF needs to be emailed to municipality
        print(f"Email {r.pdf_filled_path} to {r.municipality}")
```

### Files for Reference
- `README.md` - Full documentation with architecture diagrams
- `docs/WALKTHROUGH.md` - Step-by-step examples
- `backend/demo.py` - Demo script showing system capabilities
