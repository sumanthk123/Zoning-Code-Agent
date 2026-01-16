# Zoning Code Agent - Walkthrough Examples

This document provides step-by-step examples of using the Zoning Code Agent system. Use this as a reference for your meeting with Dan.

---

## Setup (One-Time)

```bash
# 1. Navigate to backend directory
cd backend

# 2. Create virtual environment (if not done)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install browser for automation
uvx browser-use install

# 5. Configure environment (create .env file)
cat > .env << 'EOF'
OPENROUTER_API_KEY=your_key_here
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet
DEFAULT_NAME=Research Team
DEFAULT_EMAIL=research@university.edu
DEFAULT_ADDRESS=123 University Ave, City, State 12345
DEFAULT_PHONE=555-123-4567
DEFAULT_PASSWORD=SecurePassword123
EOF
```

---

## Example 1: Explore the CSV Data

**Goal:** Understand what's in the input CSV before processing.

```bash
$ python batch_processor.py ../sample_30_forms.csv --stats
```

**Expected Output:**
```
============================================================
CSV FILE STATISTICS
============================================================
Total Entries:          47
Unique Municipalities:  30

By Form Type:
  CIVICPLUS: 5
  GENERIC_WEB: 12
  GOVQA: 3
  JUSTFOIA: 6
  NEXTREQUEST: 4
  PDF: 9
  STATE_PORTAL: 4
  OFFICE365: 2
  OPRAMACHINE: 1
  CIVICWEB: 1

By State:
  PA: 8
  TX: 7
  CA: 6
  IL: 4
  KY: 3
  ...
```

**What This Tells You:**
- 30 unique municipalities with 47 total form options (some have multiple ranks)
- 9 PDF forms that will need manual email after filling
- 4 NextRequest portals that support two-step login
- 6 JustFOIA portals that are typically straightforward
- 12 generic web forms that use the default browser automation

---

## Example 2: Process a Single Form Type (NextRequest)

**Goal:** Test the system with a specific, known portal type.

```bash
$ python batch_processor.py ../sample_30_forms.csv --type NEXTREQUEST --limit 2
```

**Expected Output:**
```
2024-01-15 10:30:00 - batch_processor - INFO - Starting batch a1b2c3d4
2024-01-15 10:30:00 - batch_processor - INFO - Loaded 47 form entries from CSV
2024-01-15 10:30:00 - batch_processor - INFO - Filtered to type NEXTREQUEST: 4 entries
2024-01-15 10:30:00 - batch_processor - INFO - Limited to 2 entries

[1/2] Processing: Los Gatos, CA (Rank 1)
2024-01-15 10:30:01 - batch_processor - INFO -   URL: https://losgatosca.nextrequest.com/requests/new
2024-01-15 10:30:01 - batch_processor - INFO -   Type: NEXTREQUEST
2024-01-15 10:30:01 - batch_processor - INFO -   Handler: nextrequest
2024-01-15 10:30:01 - handlers.nextrequest - INFO - Starting submission for Los Gatos, CA (Rank 1)
2024-01-15 10:30:01 - handlers.nextrequest - INFO - Context: Direct NextRequest submission page...

[Browser opens, navigates to form, fills fields...]

2024-01-15 10:32:15 - batch_processor - INFO -   RESULT: success
2024-01-15 10:32:15 - batch_processor - INFO -   Form submitted successfully

[2/2] Processing: Bell Gardens, CA (Rank 1)
...

============================================================
BATCH PROCESSING COMPLETE
============================================================
Batch ID:     a1b2c3d4
Processed:    2
Success:      2
Failed:       0
Success Rate: 100.0%

By Status:
  success: 2
```

**What Happened:**
1. System filtered to only NextRequest forms
2. For each form, it:
   - Selected the NextRequestHandler (knows two-step login)
   - Passed the CSV description as context to the agent
   - Browser automation filled the form
   - Captured the confirmation
3. Results stored in SQLite database

---

## Example 3: Process PDF Forms

**Goal:** Download and fill PDF forms (no email).

```bash
$ python batch_processor.py ../sample_30_forms.csv --type PDF --limit 2
```

**Expected Output:**
```
2024-01-15 11:00:00 - batch_processor - INFO - Starting batch b2c3d4e5
2024-01-15 11:00:00 - batch_processor - INFO - Loaded 47 form entries from CSV
2024-01-15 11:00:00 - batch_processor - INFO - Filtered to type PDF: 9 entries
2024-01-15 11:00:00 - batch_processor - INFO - Limited to 2 entries

[1/2] Processing: Township of Salisbury, PA (Rank 1)
2024-01-15 11:00:01 - batch_processor - INFO -   URL: https://salisburylehighpa.gov/.../RTKRequestForm.pdf
2024-01-15 11:00:01 - batch_processor - INFO -   Type: PDF
2024-01-15 11:00:01 - batch_processor - INFO -   Handler: pdf_form
2024-01-15 11:00:02 - handlers.pdf_form - INFO - Downloading PDF...
2024-01-15 11:00:03 - handlers.pdf_form - INFO - Downloaded PDF to data/downloads/174540_1_Township_of_Salisbury.pdf
2024-01-15 11:00:03 - handlers.pdf_form - INFO - Attempting to fill PDF form
2024-01-15 11:00:04 - handlers.pdf_form - INFO - Found 6 form fields in PDF
2024-01-15 11:00:04 - batch_processor - INFO -   RESULT: pdf_downloaded
2024-01-15 11:00:04 - batch_processor - INFO -   PDF downloaded and filled. Filled 4 fields

[2/2] Processing: City of Collinsville, IL (Rank 1)
...

============================================================
BATCH PROCESSING COMPLETE
============================================================
Batch ID:     b2c3d4e5
Processed:    2
Success:      2
Failed:       0
Success Rate: 100.0%

By Status:
  pdf_downloaded: 2
```

**Files Created:**
```
backend/data/
├── downloads/
│   ├── 174540_1_Township_of_Salisbury.pdf    # Original PDF
│   └── 173130_1_City_of_Collinsville.pdf
└── filled_pdfs/
    ├── 174540_1_filled.pdf                    # Filled PDF (ready to email)
    └── 173130_1_filled.pdf
```

**Next Step for Your Email Pipeline:**
These filled PDFs need to be emailed to the municipalities. Query the database:

```python
from result_store import ResultStore

store = ResultStore("data/results.db")
for r in store.get_all_results():
    if r.status.value == "pdf_downloaded":
        print(f"Email {r.pdf_filled_path} to {r.municipality}, {r.state}")
```

---

## Example 4: Process Best Options Only (Rank 1)

**Goal:** First pass - try the best form option for each municipality.

```bash
$ python batch_processor.py ../sample_30_forms.csv --rank 1 --limit 5
```

**Expected Output:**
```
2024-01-15 12:00:00 - batch_processor - INFO - Starting batch c3d4e5f6
2024-01-15 12:00:00 - batch_processor - INFO - Loaded 47 form entries from CSV
2024-01-15 12:00:00 - batch_processor - INFO - Filtered to rank 1: 30 entries
2024-01-15 12:00:00 - batch_processor - INFO - Limited to 5 entries

[1/5] Processing: Township of Salisbury, PA (Rank 1)
  Type: PDF → pdf_downloaded

[2/5] Processing: Los Gatos, CA (Rank 1)
  Type: NEXTREQUEST → success

[3/5] Processing: City of Redmond, OR (Rank 1)
  Type: JUSTFOIA → success

[4/5] Processing: City of Maplewood, MO (Rank 1)
  Type: CIVICPLUS → success

[5/5] Processing: City of Erlanger, KY (Rank 1)
  Type: JUSTFOIA → captcha_blocked

============================================================
BATCH PROCESSING COMPLETE
============================================================
Batch ID:     c3d4e5f6
Processed:    5
Success:      4
Failed:       1
Success Rate: 80.0%

By Status:
  success: 3
  pdf_downloaded: 1
  captcha_blocked: 1

Failure Reasons:
  captcha: 1
```

**What This Shows:**
- 4 out of 5 succeeded
- 1 PDF was downloaded (needs manual email)
- 1 hit a CAPTCHA (can try rank 2 option or manual)

---

## Example 5: Resume After Interruption

**Goal:** Continue processing after stopping.

```bash
# First run - process 10 forms, then stop
$ python batch_processor.py ../sample_30_forms.csv --rank 1 --limit 10
^C  # Ctrl+C to interrupt

# Second run - automatically skips processed forms
$ python batch_processor.py ../sample_30_forms.csv --rank 1
```

**Expected Output (second run):**
```
2024-01-15 13:00:00 - batch_processor - INFO - Starting batch d4e5f6g7
2024-01-15 13:00:00 - batch_processor - INFO - Loaded 47 form entries from CSV
2024-01-15 13:00:00 - batch_processor - INFO - Filtered to rank 1: 30 entries
2024-01-15 13:00:00 - batch_processor - INFO - Resume mode: 10 already processed

[1/30] Skipping already processed: Township of Salisbury, PA (Rank 1)
[2/30] Skipping already processed: Los Gatos, CA (Rank 1)
...
[10/30] Skipping already processed: City of Nappanee, IN (Rank 1)

[11/30] Processing: City of Sheridan, WY (Rank 1)
  Type: NEXTREQUEST → success
...
```

**How Resume Works:**
- SQLite database tracks all submissions
- On restart, checks which `form_entry_id` values already succeeded
- Skips those and continues with remaining forms

---

## Example 6: Export Results for Your Pipeline

**Goal:** Get results in CSV format for integration.

```bash
$ python batch_processor.py ../sample_30_forms.csv --export results.csv
```

**Created file: `results.csv`**
```csv
form_entry_id,census_id,municipality,state,url,status,failure_reason,confirmation_number,confirmation_message,pdf_downloaded_path,pdf_filled_path,error_message
174540_1,174540,Township of Salisbury,PA,https://...,pdf_downloaded,none,,PDF downloaded and filled,data/downloads/174540_1.pdf,data/filled_pdfs/174540_1_filled.pdf,
062807_1,062807,Los Gatos,CA,https://...,success,none,REQ-12345,Form submitted successfully,,,
```

**Using This in Your Email Pipeline:**

```python
import csv

# Read results
with open('results.csv') as f:
    results = list(csv.DictReader(f))

# Find PDFs that need email
pdfs_to_email = [r for r in results if r['status'] == 'pdf_downloaded']
print(f"Found {len(pdfs_to_email)} PDFs to email")

for pdf in pdfs_to_email:
    print(f"  {pdf['municipality']}, {pdf['state']}: {pdf['pdf_filled_path']}")

# Find failures to retry
failures = [r for r in results if r['status'] == 'failed']
print(f"Found {len(failures)} failures to investigate")
```

---

## Example 7: Retry Failed Submissions

**Goal:** Retry forms that failed on first attempt.

```bash
$ python batch_processor.py ../sample_30_forms.csv --retry-failed
```

**Expected Output:**
```
2024-01-15 14:00:00 - batch_processor - INFO - Found 3 failed submissions to retry

[1/3] Retrying: City of Erlanger, KY (Rank 1)
  Previous failure: captcha
  RESULT: captcha_blocked (still failing)

[2/3] Retrying: City of Woodward, OK (Rank 1)
  Previous failure: timeout
  RESULT: success (worked this time!)
...
```

---

## Integration with Your Email Pipeline

### Option 1: Query Database After Each Batch

```python
# integration_example.py
from result_store import ResultStore
from models.enums import SubmissionStatus

def get_pdfs_needing_email():
    store = ResultStore("data/results.db")
    results = store.get_all_results()

    for r in results:
        if r.status == SubmissionStatus.PDF_DOWNLOADED:
            yield {
                'municipality': r.municipality,
                'state': r.state,
                'pdf_path': r.pdf_filled_path,
                'census_id': r.census_id,
            }

# Use in your pipeline
for pdf_info in get_pdfs_needing_email():
    print(f"Queue email for {pdf_info['municipality']}: {pdf_info['pdf_path']}")
    # your_email_system.queue(pdf_info)
```

### Option 2: Hook Into BatchProcessor

```python
# In batch_processor.py, modify _process_entry():

async def _process_entry(self, entry: FormEntry) -> SubmissionResult:
    # ... existing code ...

    result = await handler.submit(entry)
    self.result_store.save_result(result, batch_id=self.batch_id)

    # 🔌 YOUR INTEGRATION POINT
    if result.status == SubmissionStatus.PDF_DOWNLOADED:
        # Call your email pipeline
        await your_email_pipeline.queue_pdf(
            pdf_path=result.pdf_filled_path,
            municipality=result.municipality,
            state=result.state,
            census_id=result.census_id
        )

    return result
```

---

## Summary Table

| Command | What It Does |
|---------|--------------|
| `--stats` | Show CSV statistics without processing |
| `--type NEXTREQUEST` | Process only NextRequest forms |
| `--type PDF` | Process only PDF downloads |
| `--rank 1` | Process only best option per municipality |
| `--limit 5` | Process max 5 forms |
| `--export results.csv` | Export results to CSV |
| `--retry-failed` | Retry previously failed submissions |
| `--no-resume` | Don't skip already-processed forms |
| `--headless` | Run browser without visible window |

---

## Questions for Dan Meeting

1. **Email Pipeline Integration:**
   - Should we hook directly into BatchProcessor, or query the database separately?
   - What format does your email system need?

2. **PDF Handling:**
   - Do you have municipality contact emails, or do we need to scrape them?
   - Should we store the email address in the CSV?

3. **Error Handling:**
   - How should CAPTCHAs be handled? Manual queue?
   - Should we automatically try rank 2 when rank 1 fails?

4. **Scheduling:**
   - Should this run on a schedule (cron) or on-demand?
   - Rate limiting concerns with municipalities?
