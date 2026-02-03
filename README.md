# Naukri Job Automation Pipeline

Automated job hunting pipeline that scrapes jobs from Naukri.com, extracts HR emails, and sends personalized job applications.

## Pipeline Overview

```
┌─────────────────┐    ┌──────────────────┐    ┌─────────────────┐
│  1. SCRAPER     │ -> │ 2. EMAIL FINDER  │ -> │ 3. EMAIL SENDER │
│  Naukri Jobs    │    │  HR/Career Emails│    │  Applications   │
└─────────────────┘    └──────────────────┘    └─────────────────┘
        ↓                      ↓                       ↓
   jobs.csv            jobs_with_emails.csv    send_results.csv
```

## Requirements

### System Dependencies

```bash
# Install Playwright browsers
pip install playwright
playwright install chromium

# For PDF resume generation (optional - for LLM mode)
sudo apt-get install pandoc texlive-xetex
```

### Python Dependencies

```bash
pip install -r requirements.txt
```

## Configuration

### 1. Gmail App Password (Required for Email Sending)

1. Go to [Google Account Security](https://myaccount.google.com/security)
2. Enable 2-Factor Authentication
3. Go to App Passwords → Generate new app password
4. Use this 16-character password in the app

### 2. GROQ API Key (Optional - for LLM-powered cover letters)

1. Sign up at [Groq Console](https://console.groq.com/)
2. Create an API key
3. Add to `.env` file:

```env
GROQ_API_KEY=your_groq_api_key_here
```

### 3. Resume PDF

Prepare your resume as a PDF file to attach with applications.

## Quick Start

### Option 1: Run with Docker

```bash
docker pull paddy4544/naukri_automation:latest
docker run -p 8501:8501 paddy4544/naukri_automation:latest
```

Then open http://localhost:8501 in your browser.

### Option 2: Run Locally

```bash
streamlit run app.py
```

### Configure in Sidebar:
- **Sender Email**: Your Gmail address
- **App Password**: Gmail app password (not regular password)
- **Your Name**: Name for cover letter
- **Resume**: Upload PDF resume

## Features

### Tab 1: Job Scraper
- Scrapes jobs from Naukri.com search URLs
- Concurrent processing (configurable)
- Clicks apply button to capture external company URLs
- Detects application questions
- Download CSV after scraping

### Tab 2: Email Extractor
- Searches Bing for company HR/career emails
- Filters for relevant emails (careers@, hr@, jobs@, etc.)
- Concurrent searches
- Download CSV with emails

### Tab 3: Email Sender
- Sends job applications via Gmail SMTP
- Customizable cover letter template
- Attaches resume PDF
- Rate limiting to avoid spam detection
- Download send results CSV

## Apply Types Detected

| Type | Description |
|------|-------------|
| `external` | Direct link to company career site |
| `external_popup` | Company site opens in popup |
| `internal` | Naukri internal apply |
| `inline_apply` | Form on Naukri page |
| `already_applied` | Already applied to job |

## File Structure

```
naukri_automation/
├── app.py                    # Streamlit app (main)
├── requirements.txt          # Python dependencies
├── .env                      # API keys (create this)
├── naukri_scrapper/
│   └── naukri_scraper_async.py   # Standalone scraper
├── email_extractor/
│   └── email_extractor.py        # Standalone email finder
└── send_emails_hr/
    └── email_sender.py           # Standalone email sender
```

## Key Credentials Summary

| Credential | Required For | How to Get |
|------------|--------------|------------|
| Gmail Email | Email Sending | Your Gmail address |
| Gmail App Password | Email Sending | Google Account → Security → App Passwords |
| GROQ API Key | LLM Cover Letters (optional) | console.groq.com |
| Naukri Account | Scraping | Manual login in browser |

## Usage Tips

1. **Start with fewer pages** (1-3) to test the pipeline
2. **Download CSV at each stage** to avoid data loss
3. **Use 2-5 concurrent jobs** to balance speed and stability
4. **Check email send results** for failed deliveries
5. **Customize cover letter** with `{position}`, `{company}`, `{sender_name}`, `{sender_email}` placeholders

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Login timeout | Increase wait time, check internet |
| No emails found | Company may not have public HR email |
| SMTP auth failed | Check app password, not regular password |
| Playwright error | Run `playwright install chromium` |

## Disclaimer

Use responsibly. Respect rate limits and terms of service of websites.
