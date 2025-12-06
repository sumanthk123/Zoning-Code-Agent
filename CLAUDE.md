# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Zoning Code Agent** - An automated tool for submitting public records requests to U.S. municipalities to obtain historical zoning codes.

### Objective
Automate the process of filling out and submitting public records request forms across different municipal websites to request zoning codes from 1940 or the earliest post-1940 adoption.

### Standard Request Text
"Could you please send me {municipality}'s municipal zoning code as of 1940? If a zoning code didn't exist then, could you send me the first post 1940 adoption of the zoning code?"

## Architecture Overview

The system is designed with a progressive complexity approach:

### Phase 1: Baseline - Simple Forms
Handle the simplest case: direct links to online forms with no login requirement.

**Three-stage pipeline:**
1. **Form Conversion**: Convert web forms to markdown representation
2. **Form Filling**: Populate form fields with appropriate data
3. **Form Submission**: Submit the completed form

### Phase 2: Advanced Tools
Build specialized tools to handle edge cases and failures:
- ReCAPTCHA solving/handling
- Login/authentication with third-party services (e.g., NextRequest.com)
- Municipal website account creation
- Non-standard form formats (PDF forms, email-based submissions)
- Error recovery and retry logic

## Form Types Encountered

1. **Simple web forms**: Direct HTML forms with submit buttons (no login)
2. **Third-party platforms**: NextRequest.com, Laserfiche portals
3. **PDF forms**: Downloadable forms requiring email submission
4. **Authenticated forms**: Requiring login to municipal or third-party systems

## Test Cases

Known public records request form URLs for testing:
1. https://portal.laserfiche.com/n6789/forms/PRA - Laserfiche portal
2. https://www.townofblackstone.org/688/Public-Records-Request - Town of Blackstone
3. https://losgatosca.nextrequest.com/requests/new - Los Gatos (NextRequest)
4. https://peachtreecitygapolice.nextrequest.com/requests/new - Peachtree City (NextRequest)
5. https://www.leawood.org/DocumentCenter/View/358/Open-Record-Request-Form-PDF - Leawood (PDF)

## Form Field Population

**Default contact information:**
- Use Claude Code operator's email addresses for submissions
- Names and addresses can be generated/mocked as needed

**Request description:** Auto-populated with the standard request text (see above), replacing {municipality} with the appropriate municipality name.

## Implementation Approach

This project uses **browser-use** (https://github.com/browser-use/browser-use) - a browser automation agent framework that enables AI-controlled web browsing.

### Why browser-use?

Browser-use provides an AI agent that can:
- Navigate web pages autonomously
- Understand and interact with web forms
- Handle dynamic content and JavaScript-heavy sites
- Adapt to different form layouts and structures
- Recover from errors and unexpected page states

This approach is ideal for handling the variety of municipal form types without requiring custom scrapers for each municipality.

## Project Structure

```
/
├── backend/           # Python backend with browser-use agent
│   ├── agent.py      # Main browser automation logic
│   ├── requirements.txt
│   └── .env          # API keys and config (not committed)
├── app/              # Next.js frontend
├── package.json      # Node.js dependencies
└── CLAUDE.md         # This file
```

## Development Setup

### Backend (Python - Browser Agent)

**Prerequisites:**
- Python 3.11+
- An API key for an LLM provider (see options below)

**Installation:**
```bash
# Create virtual environment (if not already created)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r backend/requirements.txt

# Install Chromium browser for browser-use
uvx browser-use install

# Configure environment
cp backend/.env.example backend/.env
# Edit backend/.env and add your API key and contact information
```

**API Key Options** (choose one):
- **OpenRouter** (Recommended): Free models available! Get key at https://openrouter.ai/keys
  - Supports many models including free options like `openai/gpt-oss-20b:free`
- **Browser Use**: Get $10 free credits at https://cloud.browser-use.com/new-api-key
- **Google Gemini**: Free tier at https://aistudio.google.com/app/apikey
- **OpenAI**: Requires paid API key
- **Anthropic Claude**: Requires paid API key

**Test basic setup:**
```bash
# Test the basic agent module
python backend/agent.py

# Test browser automation (requires API key)
python backend/test_browser.py
```

## Usage

### Fill a Single Form

```bash
python backend/form_filler.py
```

This will test with the Town of Blackstone form by default.

### Test All Forms

```bash
# Test all 5 forms sequentially
python backend/test_forms.py

# Test a specific form (1-5)
python backend/test_forms.py 1
```

### In Your Own Code

```python
from backend.form_filler import fill_and_submit_form

result = await fill_and_submit_form(
    form_url="https://example.com/records-request",
    municipality="Example City",
    name="Your Name",        # Optional, uses .env default
    email="you@email.com",   # Optional, uses .env default
    address="Your Address"   # Optional, uses .env default
)

print(f"Success: {result['success']}")
```

### Frontend (Next.js)

**Installation:**
```bash
# Already installed if node_modules exists
npm install

# Run development server
npm run dev
```

Access at http://localhost:3000

## Testing

To be documented once tests are implemented.
