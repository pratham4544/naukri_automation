"""
Naukri Job Automation - Streamlit App
Pipeline: Scrape Jobs -> Extract Emails -> Send Applications
"""

import streamlit as st
import pandas as pd
import asyncio
import os
import sys
import re
import csv
import smtplib
import subprocess
import time
import tempfile
import random
from datetime import datetime
from pathlib import Path
from email.message import EmailMessage
from typing import Optional, Dict, List, Set
from io import StringIO

# Playwright imports
from playwright.async_api import async_playwright

# For email sender LLM functionality
try:
    from dotenv import load_dotenv
    from langchain_groq import ChatGroq
    from langchain_community.document_loaders import PyPDFLoader
    from langchain_core.prompts import PromptTemplate
    HAS_LLM_DEPS = True
except ImportError:
    HAS_LLM_DEPS = False

# Page config
st.set_page_config(
    page_title="Naukri Job Automation",
    page_icon="💼",
    layout="wide",
    initial_sidebar_state="expanded"
)

# =============================================================================
# SESSION STATE INITIALIZATION
# =============================================================================

if 'scraper_df' not in st.session_state:
    st.session_state.scraper_df = None
if 'email_extractor_df' not in st.session_state:
    st.session_state.email_extractor_df = None
if 'email_sender_df' not in st.session_state:
    st.session_state.email_sender_df = None
if 'scraper_running' not in st.session_state:
    st.session_state.scraper_running = False
if 'extractor_running' not in st.session_state:
    st.session_state.extractor_running = False
if 'sender_running' not in st.session_state:
    st.session_state.sender_running = False

# =============================================================================
# CONSTANTS
# =============================================================================

CSV_HEADERS = [
    "job_id", "title", "company", "experience", "salary", "location",
    "posted_date", "openings", "applicants", "job_description", "skills",
    "job_url", "apply_type", "apply_link", "application_status", "questions_asked"
]

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
EMAIL_KEYWORDS = ("career", "careers", "jobs", "hr", "recruit", "talent")

DEFAULT_COVER_LETTER = """Dear Hiring Manager,

I am writing to express my interest in the {position} position at {company}. I am an AI/ML Engineer with over 2.5 years of hands-on experience in designing, developing, and deploying production-grade AI systems.

My professional experience includes working extensively with Large Language Models (LLMs), RAG pipelines, model fine-tuning, and semantic search systems. I have built scalable AI solutions using Python, Hugging Face, LangChain, FastAPI, and TensorFlow.

I believe my technical background and practical experience would allow me to contribute effectively to your team. Please find my resume attached for your review.

Thank you for your time and consideration.

Kind regards,
{sender_name}
Email: {sender_email}
"""

# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_download_button(df: pd.DataFrame, filename: str, label: str):
    """Generate a download button for a DataFrame"""
    csv_data = df.to_csv(index=False)
    st.download_button(
        label=label,
        data=csv_data,
        file_name=filename,
        mime="text/csv",
        use_container_width=True
    )

def normalize_company(name: str) -> str:
    """Normalize company name for comparison"""
    if pd.isna(name):
        return ""
    return re.sub(r"\s+", " ", str(name).lower().strip())

# =============================================================================
# SCRAPER FUNCTIONS (Adapted for Streamlit with Concurrency & Apply Button)
# =============================================================================

# Delays (in seconds)
DELAY_BETWEEN_JOBS = (2, 4)
DELAY_BETWEEN_PAGES = (4, 7)
DELAY_AFTER_APPLY_CLICK = 5


async def scrape_jobs_from_search_streamlit(page, search_url: str, start_page: int, end_page: int,
                                             progress_bar, status_text) -> List[Dict]:
    """Scrape job listings from search results via XHR interception"""
    jobs = []
    seen_ids = set()

    async def handle_response(response):
        if "jobapi/v3/search" in response.url:
            try:
                data = await response.json()
                for job in data.get("jobDetails", []):
                    jid = job.get("jobId")
                    if jid and jid not in seen_ids:
                        seen_ids.add(jid)
                        jobs.append(job)
            except:
                pass

    page.on("response", handle_response)

    total_pages = end_page - start_page + 1

    for i, page_no in enumerate(range(start_page, end_page + 1)):
        url = f"{search_url}&pageNo={page_no}"
        status_text.text(f"Loading search page {page_no}...")

        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(*DELAY_BETWEEN_PAGES))
            progress_bar.progress((i + 1) / total_pages)
            status_text.text(f"Page {page_no}: Collected {len(jobs)} jobs so far")
        except Exception as e:
            status_text.text(f"Error on page {page_no}: {str(e)[:50]}")
            continue

    page.remove_listener("response", handle_response)
    return jobs


async def extract_job_details(page) -> Dict:
    """Extract full job details from job description page"""
    return await page.evaluate("""
    () => {
        const getText = (sel) =>
            document.querySelector(sel)?.innerText?.trim() || null;

        const getAllText = (sel) =>
            Array.from(document.querySelectorAll(sel))
                .map(e => e.innerText.trim())
                .filter(Boolean);

        const textIncludes = (selector, keyword) => {
            const els = Array.from(document.querySelectorAll(selector));
            const el = els.find(e => e.innerText.includes(keyword));
            return el ? el.innerText.trim() : null;
        };

        return {
            title: getText('h1'),
            company: getText('.styles_jd-header-comp-name__MvqAI, .jd-header-comp-name'),
            experience: getText('.styles_jhc__exp, .exp'),
            salary: getText('.styles_jhc__salary, .salary'),
            location: getText('.styles_jhc__location, .location'),
            posted: textIncludes('span', 'Posted') || textIncludes('span', 'days ago'),
            openings: textIncludes('span', 'Opening'),
            applicants: textIncludes('span', 'Applicants'),
            description: getText('.styles_JDC__dang-inner-html__h0K4t, .job-desc'),
            skills: getAllText('.styles_key-skill__GIPn_, .key-skill, a[href*="skills"]')
        };
    }
    """)


async def detect_application_questions(page) -> bool:
    """Check if application form has questions"""
    try:
        question_selectors = [
            'input[type="text"]:not([name*="email"]):not([name*="phone"])',
            'textarea',
            'select:not([name*="experience"]):not([name*="location"])',
            '.question',
            '[class*="question"]',
            'form input[required]',
        ]

        for selector in question_selectors:
            count = await page.locator(selector).count()
            if count > 2:
                return True

        has_questions = await page.evaluate("""
        () => {
            const text = document.body.innerText.toLowerCase();
            const keywords = [
                'why are you interested',
                'tell us about',
                'describe your',
                'what makes you',
                'why should we',
                'notice period',
                'current ctc',
                'expected ctc'
            ];
            return keywords.some(k => text.includes(k));
        }
        """)

        return has_questions
    except:
        return False


async def process_single_job_with_apply(context, job: Dict, index: int, total: int,
                                         status_text, semaphore) -> Dict:
    """Process a single job with full apply button clicking logic"""

    async with semaphore:
        job_id = job.get("jobId")
        job_url = f"https://www.naukri.com{job.get('jdURL')}"

        page = await context.new_page()
        popup_tracker = {"popup_page": None}

        def handle_popup(popup):
            popup_tracker["popup_page"] = popup

        page.on("popup", handle_popup)

        record = {
            "job_id": job_id,
            "job_url": job_url,
            "apply_type": None,
            "apply_link": None,
            "application_status": "not_processed",
            "questions_asked": "no"
        }

        try:
            status_text.text(f"[{index}/{total}] Processing: {job.get('title', 'Unknown')} at {job.get('companyName', 'Unknown')}")

            await page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(3)

            # Extract job details
            details = await extract_job_details(page)
            record.update({
                "title": details.get("title"),
                "company": details.get("company"),
                "experience": details.get("experience"),
                "salary": details.get("salary"),
                "location": details.get("location"),
                "posted_date": details.get("posted"),
                "openings": details.get("openings"),
                "applicants": details.get("applicants"),
                "job_description": details.get("description"),
                "skills": " | ".join(details.get("skills", [])) if details.get("skills") else None
            })

            # Check if already applied
            already_applied = False
            try:
                already_applied = (
                    await page.locator('text=/already applied/i').count() > 0 or
                    await page.locator('.applied').count() > 0 or
                    await page.locator('[class*="applied"]').count() > 0
                )
            except:
                pass

            if already_applied:
                record["application_status"] = "already_applied"
                record["apply_type"] = "already_applied"
                await page.close()
                return record

            # Find apply button
            apply_button = None
            selectors = [
                'button:has-text("Apply")',
                'a:has-text("Apply")',
                'button[id*="apply" i]',
                'a[id*="apply" i]',
                'button[class*="apply" i]',
                'a[class*="apply" i]'
            ]

            for sel in selectors:
                if await page.locator(sel).count() > 0:
                    apply_button = await page.locator(sel).first.element_handle()
                    break

            if not apply_button:
                record["apply_type"] = "no_apply_button"
                record["application_status"] = "no_button_found"
                await page.close()
                return record

            # Check if button has direct external link
            href = await page.evaluate(
                "(el) => el.href || el.getAttribute('href')",
                apply_button
            )

            if href and href.startswith("http"):
                record["apply_link"] = href
                record["apply_type"] = "external" if "naukri.com" not in href else "internal"
                record["application_status"] = "link_extracted"
                await page.close()
                return record

            # Click apply button and observe behavior
            current_url = page.url

            await apply_button.click()
            await asyncio.sleep(DELAY_AFTER_APPLY_CLICK)

            # Check for popup (external company site)
            if popup_tracker["popup_page"]:
                apply_url = popup_tracker["popup_page"].url
                record["apply_link"] = apply_url
                record["apply_type"] = "external_popup" if "naukri.com" not in apply_url else "internal_popup"
                record["application_status"] = "popup_detected"

                # Check for questions in popup
                try:
                    has_questions = await detect_application_questions(popup_tracker["popup_page"])
                    record["questions_asked"] = "yes" if has_questions else "no"
                except:
                    pass

                try:
                    await popup_tracker["popup_page"].close()
                except:
                    pass

            # Check for navigation to new page (redirect to company site)
            elif page.url != current_url:
                apply_url = page.url
                record["apply_link"] = apply_url
                record["apply_type"] = "external" if "naukri.com" not in apply_url else "internal"
                record["application_status"] = "redirected"

                has_questions = await detect_application_questions(page)
                record["questions_asked"] = "yes" if has_questions else "no"

            # Check for iframe
            else:
                iframe = await page.query_selector('iframe[src*="apply"], iframe[src*="career"]')
                if iframe:
                    iframe_src = await iframe.get_attribute("src")
                    record["apply_link"] = iframe_src
                    record["apply_type"] = "iframe"
                    record["application_status"] = "iframe_detected"
                else:
                    # Inline form on Naukri
                    has_questions = await detect_application_questions(page)
                    record["apply_type"] = "inline_apply"
                    record["apply_link"] = job_url
                    record["application_status"] = "inline_form"
                    record["questions_asked"] = "yes" if has_questions else "no"

        except Exception as e:
            record["application_status"] = "error"
            record["apply_type"] = "error"
        finally:
            try:
                await page.close()
            except:
                pass

        # Random delay between jobs
        await asyncio.sleep(random.uniform(*DELAY_BETWEEN_JOBS))

        return record


async def process_jobs_batch_concurrent(context, jobs: List[Dict], semaphore,
                                         status_text, progress_bar, start_idx: int) -> List[Dict]:
    """Process a batch of jobs concurrently"""
    total = len(jobs)

    async def process_with_progress(job, idx):
        record = await process_single_job_with_apply(context, job, start_idx + idx, start_idx + total - 1, status_text, semaphore)
        progress_bar.progress((start_idx + idx) / (start_idx + total))
        return record

    tasks = [
        process_with_progress(job, idx)
        for idx, job in enumerate(jobs, 1)
    ]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter out exceptions and return valid records
    valid_records = []
    for r in results:
        if isinstance(r, dict):
            valid_records.append(r)
        elif isinstance(r, Exception):
            # Create error record
            valid_records.append({
                "job_id": "error",
                "job_url": "",
                "apply_type": "error",
                "apply_link": None,
                "application_status": f"error: {str(r)[:50]}",
                "questions_asked": "no"
            })

    return valid_records


async def run_scraper(search_urls: List[str], start_page: int, end_page: int,
                      max_jobs: int, max_concurrent: int, num_contexts: int,
                      progress_container) -> pd.DataFrame:
    """Main scraper function for Streamlit with concurrency"""

    all_records = []

    progress_bar = progress_container.progress(0)
    status_text = progress_container.empty()

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)

        # Create multiple browser contexts for parallel processing
        contexts = []
        for i in range(num_contexts):
            context = await browser.new_context(
                viewport={"width": 1920, "height": 1080},
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/120.0.0.0 Safari/537.36"
                )
            )
            contexts.append(context)

        # Use first context for login and search
        login_context = contexts[0]
        page = await login_context.new_page()

        # Navigate to login
        status_text.text("Opening Naukri login page...")
        await page.goto("https://www.naukri.com/nlogin/login", timeout=60000)

        # Wait for user to login
        status_text.text("⏳ Please login to Naukri in the browser window. Waiting for login...")

        login_detected = False
        for _ in range(180):  # Wait up to 3 minutes
            await asyncio.sleep(1)
            current_url = page.url
            if "nlogin" not in current_url and "login" not in current_url:
                login_detected = True
                break

        if not login_detected:
            status_text.text("❌ Login timeout. Please try again.")
            await browser.close()
            return pd.DataFrame()

        status_text.text("✅ Login detected! Starting scraping...")
        await asyncio.sleep(2)

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(max_concurrent)

        # Process each search URL
        all_jobs = []
        for url_idx, search_url in enumerate(search_urls):
            status_text.text(f"Scraping search URL {url_idx + 1}/{len(search_urls)}...")
            jobs = await scrape_jobs_from_search_streamlit(
                page, search_url, start_page, end_page, progress_bar, status_text
            )
            all_jobs.extend(jobs[:max_jobs])

        status_text.text(f"Collected {len(all_jobs)} jobs. Now extracting details with {max_concurrent} concurrent jobs...")

        # Process jobs in batches using round-robin across contexts
        batch_size = max_concurrent
        context_idx = 0

        for i in range(0, len(all_jobs), batch_size):
            batch = all_jobs[i:i + batch_size]

            # Use contexts in round-robin fashion
            context = contexts[context_idx % len(contexts)]
            context_idx += 1

            status_text.text(f"Processing batch {i // batch_size + 1} ({len(batch)} jobs concurrently)...")

            batch_records = await process_jobs_batch_concurrent(
                context, batch, semaphore, status_text, progress_bar, i
            )
            all_records.extend(batch_records)

        # Close all contexts
        for context in contexts:
            await context.close()

        await browser.close()

    status_text.text(f"✅ Scraping complete! {len(all_records)} jobs processed.")

    if all_records:
        df = pd.DataFrame(all_records)
        # Reorder columns to match CSV_HEADERS
        for col in CSV_HEADERS:
            if col not in df.columns:
                df[col] = None
        return df[CSV_HEADERS]
    return pd.DataFrame()


# =============================================================================
# EMAIL EXTRACTOR FUNCTIONS
# =============================================================================

async def get_company_emails(browser, company: str, semaphore) -> str:
    """Search for company career emails using Bing"""
    search_url = f"https://www.bing.com/search?q={company}+careers+email"

    async with semaphore:
        page = await browser.new_page()
        try:
            await page.goto(search_url, timeout=60000)
            content = await page.content()

            emails = set(re.findall(EMAIL_REGEX, content))

            filtered = [
                e for e in emails
                if any(k in e.lower() for k in EMAIL_KEYWORDS)
            ]

            if not filtered and emails:
                filtered = [next(iter(emails))]

            return ", ".join(filtered)
        except Exception as e:
            return ""
        finally:
            await page.close()


async def run_email_extractor(df: pd.DataFrame, concurrency: int, progress_container) -> pd.DataFrame:
    """Extract emails for companies in the DataFrame"""

    progress_bar = progress_container.progress(0)
    status_text = progress_container.empty()

    # Clean company names
    df = df.copy()
    df["company"] = (
        df["company"]
        .astype(str)
        .str.replace(r"\n\d+\.?\d*\s+Reviews?", "", regex=True)
        .str.strip()
    )

    df["company_norm"] = df["company"].apply(normalize_company)
    df["career_email"] = ""

    unique_companies = df["company_norm"].unique()
    status_text.text(f"Finding emails for {len(unique_companies)} unique companies...")

    email_cache = {}
    semaphore = asyncio.Semaphore(concurrency)

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )

        for idx, company in enumerate(unique_companies):
            email_cache[company] = await get_company_emails(browser, company, semaphore)
            progress_bar.progress((idx + 1) / len(unique_companies))
            status_text.text(f"[{idx + 1}/{len(unique_companies)}] {company}: {email_cache[company] or 'No email found'}")

        await browser.close()

    # Map emails back to all rows
    df["career_email"] = df["company_norm"].map(email_cache)
    df.drop(columns=["company_norm"], inplace=True)

    # Count stats
    emails_found = df["career_email"].notna() & (df["career_email"] != "")
    status_text.text(f"✅ Done! Found emails for {emails_found.sum()}/{len(df)} jobs")

    return df


# =============================================================================
# EMAIL SENDER FUNCTIONS
# =============================================================================

# LLM Cover Letter Template
COVER_LETTER_LLM_TEMPLATE = """
Given the following resume and job description, generate a tailored cover letter that highlights relevant skills and experiences from the resume to match the job requirements.

Make it professional, concise, and engaging. Include:
1. A strong opening that mentions the specific position and company name
2. 2-3 paragraphs highlighting relevant experience and skills
3. A closing paragraph expressing enthusiasm and call to action
4. End with the sender's name and contact details

Resume: {resume_text}
Job Description: {job_description}
Position: {position}
Company: {company}
Sender Name: {sender_name}
Sender Email: {sender_email}

Cover Letter:
"""


def load_resume_text(resume_path: str) -> Optional[str]:
    """Load and extract text from resume PDF"""
    if not HAS_LLM_DEPS:
        return None
    try:
        loader = PyPDFLoader(resume_path)
        docs = loader.load()
        return " ".join([doc.page_content for doc in docs])
    except Exception:
        return None


def generate_personalized_cover_letter(
    job_description: str,
    position: str,
    company: str,
    resume_text: str,
    sender_name: str,
    sender_email: str,
    groq_api_key: str
) -> Optional[str]:
    """Generate a personalized cover letter using Groq LLM"""
    if not HAS_LLM_DEPS or not groq_api_key:
        return None

    try:
        llm = ChatGroq(
            model="llama-3.1-8b-instant",
            temperature=0,
            max_tokens=None,
            timeout=30,
            max_retries=2,
            api_key=groq_api_key
        )

        prompt = PromptTemplate(
            template=COVER_LETTER_LLM_TEMPLATE,
            input_variables=["resume_text", "job_description", "position", "company", "sender_name", "sender_email"]
        )

        chain = prompt | llm
        result = chain.invoke({
            "resume_text": resume_text,
            "job_description": job_description or "Not provided",
            "position": position,
            "company": company,
            "sender_name": sender_name,
            "sender_email": sender_email
        })

        return result.content
    except Exception as e:
        return None


def send_single_email(receiver_email: str, subject: str, body: str,
                      resume_path: str, smtp_config: dict) -> tuple:
    """Send a single email with resume attachment"""
    try:
        msg = EmailMessage()
        msg["From"] = smtp_config["sender_email"]
        msg["To"] = receiver_email
        msg["Subject"] = subject
        msg.set_content(body)

        # Attach resume
        with open(resume_path, "rb") as f:
            file_data = f.read()
            file_name = os.path.basename(resume_path)

        msg.add_attachment(
            file_data,
            maintype="application",
            subtype="pdf",
            filename=file_name
        )

        # Send
        with smtplib.SMTP(smtp_config["server"], smtp_config["port"], timeout=30) as server:
            server.starttls()
            server.login(smtp_config["sender_email"], smtp_config["app_password"])
            server.send_message(msg)

        return True, "Sent successfully"

    except smtplib.SMTPAuthenticationError:
        return False, "SMTP authentication failed"
    except Exception as e:
        return False, str(e)


def run_email_sender(df: pd.DataFrame, resume_path: str, smtp_config: dict,
                     sender_name: str, cover_letter_template: str,
                     delay_between_emails: int, progress_container,
                     use_llm: bool = False, groq_api_key: str = None) -> pd.DataFrame:
    """Send emails to all companies in the DataFrame"""

    progress_bar = progress_container.progress(0)
    status_text = progress_container.empty()

    # Filter for valid emails
    df_filtered = df[df['career_email'].notna() & (df['career_email'] != '')].copy()
    df_unique = df_filtered.drop_duplicates(subset=['career_email'], keep='first')

    # Load resume text if using LLM
    resume_text = None
    if use_llm and groq_api_key:
        status_text.text("Loading resume for LLM personalization...")
        resume_text = load_resume_text(resume_path)
        if resume_text:
            status_text.text(f"Resume loaded. Sending personalized emails to {len(df_unique)} unique addresses...")
        else:
            status_text.text(f"Could not load resume text. Falling back to template. Sending to {len(df_unique)} addresses...")
            use_llm = False
    else:
        status_text.text(f"Sending emails to {len(df_unique)} unique addresses...")

    results = []
    successful = 0
    failed = 0
    personalized_count = 0

    for idx, (_, row) in enumerate(df_unique.iterrows()):
        email_address = str(row['career_email']).split(',')[0].strip()
        company = row.get('company', 'Company')
        position = row.get('title', 'Position')
        job_description = row.get('job_description', '')

        cover_letter = None
        used_llm = False

        # Try LLM-based personalization first
        if use_llm and resume_text and groq_api_key:
            status_text.text(f"[{idx + 1}/{len(df_unique)}] Generating personalized email for {company}...")
            cover_letter = generate_personalized_cover_letter(
                job_description=job_description,
                position=position,
                company=company,
                resume_text=resume_text,
                sender_name=sender_name,
                sender_email=smtp_config["sender_email"],
                groq_api_key=groq_api_key
            )
            if cover_letter:
                used_llm = True
                personalized_count += 1

        # Fallback to template if LLM failed or not enabled
        if not cover_letter:
            cover_letter = cover_letter_template.format(
                position=position,
                company=company,
                sender_name=sender_name,
                sender_email=smtp_config["sender_email"]
            )

        subject = f"Application for {position} at {company}"

        status_text.text(f"[{idx + 1}/{len(df_unique)}] Sending to {email_address}{'(personalized)' if used_llm else ''}...")

        success, message = send_single_email(
            email_address, subject, cover_letter, resume_path, smtp_config
        )

        result = {
            'company': company,
            'title': position,
            'email': email_address,
            'status': 'sent' if success else 'failed',
            'message': message,
            'personalized': used_llm,
            'timestamp': datetime.now().isoformat()
        }
        results.append(result)

        if success:
            successful += 1
        else:
            failed += 1

        progress_bar.progress((idx + 1) / len(df_unique))
        time.sleep(delay_between_emails)

    status_text.text(f"Done! Sent: {successful}, Failed: {failed}, Personalized: {personalized_count}")

    return pd.DataFrame(results)


# =============================================================================
# STREAMLIT UI
# =============================================================================

def main():
    st.title("💼 Naukri Job Automation Pipeline")
    st.markdown("---")

    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")

        st.subheader("📧 Email Settings")
        sender_email = st.text_input("Sender Email", value="", type="default")
        app_password = st.text_input("App Password", value="", type="password")
        sender_name = st.text_input("Your Name", value="")

        st.subheader("🔑 API Keys (Optional)")
        groq_api_key = st.text_input("GROQ API Key", value="", type="password",
                                      help="For LLM-powered cover letters")

        st.subheader("📄 Resume")
        uploaded_resume = st.file_uploader("Upload Resume (PDF)", type=["pdf"])

        if uploaded_resume:
            # Save uploaded resume to temp file
            resume_temp_path = Path(tempfile.gettempdir()) / "uploaded_resume.pdf"
            with open(resume_temp_path, "wb") as f:
                f.write(uploaded_resume.read())
            st.success(f"Resume uploaded!")
        else:
            resume_temp_path = None

    # Main content - Tabs for each stage
    tab1, tab2, tab3 = st.tabs(["🔍 1. Scrape Jobs", "📧 2. Extract Emails", "📨 3. Send Applications"])

    # =========================
    # TAB 1: SCRAPER
    # =========================
    with tab1:
        st.header("🔍 Naukri Job Scraper")
        st.markdown("Scrape job listings from Naukri.com")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Search Configuration")
            search_urls_text = st.text_area(
                "Search URLs (one per line)",
                value="https://www.naukri.com/nlp-engineer-jobs?k=nlp%20engineer",
                height=100,
                help="Enter Naukri search URLs to scrape"
            )

            col_a, col_b = st.columns(2)
            with col_a:
                start_page = st.number_input("Start Page", min_value=1, value=1)
                end_page = st.number_input("End Page", min_value=1, value=5)
            with col_b:
                max_jobs = st.number_input("Max Jobs per URL", min_value=1, value=50)

            st.subheader("⚡ Concurrency Settings")
            col_c, col_d = st.columns(2)
            with col_c:
                max_concurrent = st.slider(
                    "Concurrent Jobs",
                    min_value=1, max_value=10, value=5,
                    help="Number of jobs processed simultaneously"
                )
            with col_d:
                num_contexts = st.slider(
                    "Browser Contexts",
                    min_value=1, max_value=5, value=3,
                    help="Number of browser sessions for parallel processing"
                )

        with col2:
            st.subheader("Or Upload Existing CSV")
            uploaded_scraper_csv = st.file_uploader(
                "Upload scraped jobs CSV",
                type=["csv"],
                key="scraper_upload"
            )

            if uploaded_scraper_csv:
                st.session_state.scraper_df = pd.read_csv(uploaded_scraper_csv)
                st.success(f"Loaded {len(st.session_state.scraper_df)} jobs from CSV")

        st.markdown("---")

        # Run scraper button
        if st.button("🚀 Start Scraping", type="primary", use_container_width=True):
            if not search_urls_text.strip():
                st.error("Please enter at least one search URL")
            else:
                search_urls = [url.strip() for url in search_urls_text.strip().split('\n') if url.strip()]

                st.warning("⚠️ A browser window will open. Please login to Naukri when prompted.")
                st.info(f"⚡ Running with {max_concurrent} concurrent jobs across {num_contexts} browser contexts")

                progress_container = st.container()

                # Run async scraper
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result_df = loop.run_until_complete(
                        run_scraper(
                            search_urls, start_page, end_page, max_jobs,
                            max_concurrent, num_contexts, progress_container
                        )
                    )

                    if not result_df.empty:
                        st.session_state.scraper_df = result_df
                        st.success(f"✅ Scraped {len(result_df)} jobs!")

                        # Show apply type stats
                        if 'apply_type' in result_df.columns:
                            apply_stats = result_df['apply_type'].value_counts()
                            st.write("**Apply Type Distribution:**")
                            st.write(apply_stats)
                    else:
                        st.error("No jobs scraped. Please try again.")
                finally:
                    loop.close()

        # Display and download scraped data
        if st.session_state.scraper_df is not None and not st.session_state.scraper_df.empty:
            st.subheader("📊 Scraped Jobs")
            st.dataframe(st.session_state.scraper_df, use_container_width=True, height=400)

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            get_download_button(
                st.session_state.scraper_df,
                f"naukri_jobs_{timestamp}.csv",
                "⬇️ Download Scraped Jobs CSV"
            )

    # =========================
    # TAB 2: EMAIL EXTRACTOR
    # =========================
    with tab2:
        st.header("📧 Email Extractor")
        st.markdown("Find HR/career emails for companies")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Configuration")
            concurrency = st.slider("Concurrency", min_value=1, max_value=10, value=5,
                                   help="Number of parallel searches")

        with col2:
            st.subheader("Or Upload CSV")
            uploaded_extractor_csv = st.file_uploader(
                "Upload jobs CSV (must have 'company' column)",
                type=["csv"],
                key="extractor_upload"
            )

            if uploaded_extractor_csv:
                st.session_state.scraper_df = pd.read_csv(uploaded_extractor_csv)
                st.success(f"Loaded {len(st.session_state.scraper_df)} jobs")

        st.markdown("---")

        # Source selection
        source_df = st.session_state.scraper_df

        if source_df is not None and not source_df.empty:
            st.info(f"📊 Using {len(source_df)} jobs from scraper stage")

            if st.button("🔍 Extract Emails", type="primary", use_container_width=True):
                progress_container = st.container()

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    result_df = loop.run_until_complete(
                        run_email_extractor(source_df, concurrency, progress_container)
                    )
                    st.session_state.email_extractor_df = result_df
                    st.success("✅ Email extraction complete!")
                finally:
                    loop.close()
        else:
            st.warning("⚠️ No data available. Please scrape jobs first or upload a CSV.")

        # Display and download
        if st.session_state.email_extractor_df is not None and not st.session_state.email_extractor_df.empty:
            st.subheader("📊 Jobs with Emails")
            st.dataframe(st.session_state.email_extractor_df, use_container_width=True, height=400)

            # Stats
            emails_found = st.session_state.email_extractor_df["career_email"].notna() & \
                          (st.session_state.email_extractor_df["career_email"] != "")
            st.metric("Emails Found", f"{emails_found.sum()}/{len(st.session_state.email_extractor_df)}")

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            get_download_button(
                st.session_state.email_extractor_df,
                f"jobs_with_emails_{timestamp}.csv",
                "⬇️ Download Jobs with Emails CSV"
            )

    # =========================
    # TAB 3: EMAIL SENDER
    # =========================
    with tab3:
        st.header("📨 Send Applications")
        st.markdown("Send job application emails to HR")

        # Check prerequisites
        missing_prereqs = []
        if not sender_email:
            missing_prereqs.append("Sender Email")
        if not app_password:
            missing_prereqs.append("App Password")
        if not sender_name:
            missing_prereqs.append("Your Name")
        if resume_temp_path is None:
            missing_prereqs.append("Resume PDF")

        if missing_prereqs:
            st.error(f"⚠️ Please configure in sidebar: {', '.join(missing_prereqs)}")

        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Email Settings")
            delay_between = st.slider("Delay between emails (seconds)", 1, 10, 2)

            # LLM Personalization Toggle
            st.subheader("Personalization")
            use_llm = st.checkbox(
                "Use AI-powered personalization (Groq LLM)",
                value=False,
                help="Generate personalized cover letters using AI based on job description and your resume"
            )

            if use_llm:
                if not groq_api_key:
                    st.warning("Please enter your GROQ API key in the sidebar to use personalization")
                elif not HAS_LLM_DEPS:
                    st.error("LLM dependencies not installed. Run: pip install langchain-groq langchain-community pypdf")
                else:
                    st.success("AI personalization enabled - each email will be customized!")

            st.subheader("Cover Letter Template")
            st.caption("Used as fallback if AI personalization fails or is disabled")
            cover_letter = st.text_area(
                "Template (use {position}, {company}, {sender_name}, {sender_email})",
                value=DEFAULT_COVER_LETTER,
                height=300
            )

        with col2:
            st.subheader("Or Upload CSV")
            uploaded_sender_csv = st.file_uploader(
                "Upload CSV (must have 'career_email' column)",
                type=["csv"],
                key="sender_upload"
            )

            if uploaded_sender_csv:
                st.session_state.email_extractor_df = pd.read_csv(uploaded_sender_csv)
                st.success(f"Loaded {len(st.session_state.email_extractor_df)} jobs")

        st.markdown("---")

        # Source selection
        source_df = st.session_state.email_extractor_df

        if source_df is not None and not source_df.empty and "career_email" in source_df.columns:
            valid_emails = source_df[source_df['career_email'].notna() & (source_df['career_email'] != '')]
            unique_emails = valid_emails.drop_duplicates(subset=['career_email'])

            st.info(f"📊 Ready to send {len(unique_emails)} emails")

            if not missing_prereqs:
                # Check if LLM is requested but not available
                llm_ready = use_llm and groq_api_key and HAS_LLM_DEPS
                if use_llm and not llm_ready:
                    st.warning("LLM personalization requested but not available. Will use template instead.")

                if st.button("📨 Send Applications", type="primary", use_container_width=True):
                    smtp_config = {
                        "sender_email": sender_email,
                        "app_password": app_password,
                        "server": "smtp.gmail.com",
                        "port": 587
                    }

                    progress_container = st.container()

                    result_df = run_email_sender(
                        source_df,
                        str(resume_temp_path),
                        smtp_config,
                        sender_name,
                        cover_letter,
                        delay_between,
                        progress_container,
                        use_llm=llm_ready,
                        groq_api_key=groq_api_key if llm_ready else None
                    )

                    st.session_state.email_sender_df = result_df
                    st.success("Email sending complete!")
        else:
            st.warning("⚠️ No data with emails available. Please extract emails first or upload a CSV.")

        # Display and download results
        if st.session_state.email_sender_df is not None and not st.session_state.email_sender_df.empty:
            st.subheader("Send Results")
            st.dataframe(st.session_state.email_sender_df, use_container_width=True, height=400)

            # Stats
            col1, col2, col3 = st.columns(3)
            sent = (st.session_state.email_sender_df["status"] == "sent").sum()
            failed = (st.session_state.email_sender_df["status"] == "failed").sum()
            personalized = st.session_state.email_sender_df.get("personalized", pd.Series([False])).sum()
            col1.metric("Sent", sent)
            col2.metric("Failed", failed)
            col3.metric("Personalized", int(personalized))

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            get_download_button(
                st.session_state.email_sender_df,
                f"email_send_results_{timestamp}.csv",
                "⬇️ Download Send Results CSV"
            )

    # Footer
    st.markdown("---")
    st.markdown(
        """
        <div style='text-align: center; color: gray;'>
            💼 Naukri Job Automation Pipeline | Built with Streamlit
        </div>
        """,
        unsafe_allow_html=True
    )


if __name__ == "__main__":
    main()
