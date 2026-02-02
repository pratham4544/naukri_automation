from playwright.async_api import async_playwright
import asyncio
import csv
import os
from datetime import datetime
import random
from typing import Dict, List, Set


# =========================
# CONFIGURATION
# =========================
SEARCH_URLS = [
    "https://www.naukri.com/ai-engineer-jobs-in-pune?k=ai%20engineer&l=pune%2C%20remote&experience=2",
    "https://www.naukri.com/machine-learning-engineer-jobs?k=machine%20learning%20engineer&experience=2",
    # Add more search URLs here
]

START_PAGE = 1
END_PAGE = 3
MAX_JOBS_PER_SEARCH = 500  # Safety limit per search URL

# Delays (in seconds)
DELAY_BETWEEN_JOBS = (3, 6)
DELAY_BETWEEN_PAGES = (4, 7)
DELAY_AFTER_APPLY_CLICK = 5  # Wait to detect questions/forms

# Output
OUTPUT_CSV = None  # Will be auto-generated with timestamp


# =========================
# CSV HANDLING
# =========================
CSV_HEADERS = [
    "job_id", "title", "company", "experience", "salary", "location",
    "posted_date", "openings", "applicants", "job_description", "skills",
    "job_url", "apply_type", "apply_link", "application_status", "questions_asked"
]


def init_csv_file() -> str:
    """Initialize CSV file with headers"""
    global OUTPUT_CSV
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_CSV = f"naukri_jobs_{ts}.csv"
    
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writeheader()
    
    print(f"📄 CSV initialized: {OUTPUT_CSV}\n")
    return OUTPUT_CSV


def get_processed_job_ids() -> Set[str]:
    """Get already processed job IDs from CSV"""
    if not OUTPUT_CSV or not os.path.exists(OUTPUT_CSV):
        return set()
    
    processed = set()
    with open(OUTPUT_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("job_id"):
                processed.add(row["job_id"])
    
    print(f"📋 Found {len(processed)} already processed jobs")
    return processed


def append_to_csv(record: Dict):
    """Append a job record to CSV"""
    with open(OUTPUT_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_HEADERS)
        writer.writerow(record)


# =========================
# SCRAPE JOBS FROM SEARCH
# =========================
async def scrape_jobs_from_search(page, search_url: str, start_page: int, end_page: int) -> List[Dict]:
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

    for page_no in range(start_page, end_page + 1):
        url = f"{search_url}&pageNo={page_no}"
        print(f"🔍 Loading search page {page_no}")
        
        try:
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await asyncio.sleep(random.uniform(*DELAY_BETWEEN_PAGES))
            print(f"   ✓ Jobs collected: {len(jobs)}")
        except Exception as e:
            print(f"   ⚠ Error on page {page_no}: {str(e)[:100]}")
            continue

    page.remove_listener("response", handle_response)
    return jobs


# =========================
# EXTRACT JOB DETAILS
# =========================
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


# =========================
# DETECT APPLICATION QUESTIONS
# =========================
async def detect_application_questions(page) -> bool:
    """Check if application form has questions"""
    try:
        # Common selectors for Naukri application questions
        question_selectors = [
            'input[type="text"]:not([name*="email"]):not([name*="phone"])',
            'textarea',
            'select:not([name*="experience"]):not([name*="location"])',
            '.question',
            '[class*="question"]',
            'label:has-text("?")',
            'form input[required]',
        ]
        
        for selector in question_selectors:
            count = await page.locator(selector).count()
            if count > 2:  # More than basic fields = likely has questions
                return True
        
        # Check for common question keywords in page text
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


# =========================
# PROCESS SINGLE JOB
# =========================
async def process_job(page, job: Dict, popup_tracker: Dict, index: int, total: int) -> Dict:
    """Process a single job: extract details and apply info"""
    
    job_id = job.get("jobId")
    job_url = f"https://www.naukri.com{job.get('jdURL')}"
    
    print(f"\n[{index}/{total}] Processing: {job.get('title')} at {job.get('companyName')}")
    print(f"   URL: {job_url}")
    
    record = {
        "job_id": job_id,
        "job_url": job_url,
        "apply_type": None,
        "apply_link": None,
        "application_status": "not_processed",
        "questions_asked": "no"
    }
    
    try:
        # Navigate to job page
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
            print("   ⚠ Already applied")
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
            print("   ❌ No apply button found")
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
            print(f"   ✓ Apply type: {record['apply_type']}")
            print(f"   ✓ Link: {href}")
            return record
        
        # Click apply button and observe behavior
        popup_tracker["popup_page"] = None
        current_url = page.url
        
        await apply_button.click()
        await asyncio.sleep(DELAY_AFTER_APPLY_CLICK)
        
        # Check for popup
        if popup_tracker["popup_page"]:
            apply_url = popup_tracker["popup_page"].url
            record["apply_link"] = apply_url
            record["apply_type"] = "external_popup" if "naukri.com" not in apply_url else "internal_popup"
            record["application_status"] = "popup_detected"
            
            # Check for questions in popup
            has_questions = await detect_application_questions(popup_tracker["popup_page"])
            record["questions_asked"] = "yes" if has_questions else "no"
            
            print(f"   ✓ Apply type: {record['apply_type']} (popup)")
            print(f"   ✓ Link: {apply_url}")
            print(f"   ✓ Questions: {record['questions_asked']}")
            
            await popup_tracker["popup_page"].close()
            popup_tracker["popup_page"] = None
            
        # Check for navigation to new page
        elif page.url != current_url:
            apply_url = page.url
            record["apply_link"] = apply_url
            record["apply_type"] = "external" if "naukri.com" not in apply_url else "internal"
            record["application_status"] = "redirected"
            
            # Check for questions
            has_questions = await detect_application_questions(page)
            record["questions_asked"] = "yes" if has_questions else "no"
            
            print(f"   ✓ Apply type: {record['apply_type']} (redirect)")
            print(f"   ✓ Link: {apply_url}")
            print(f"   ✓ Questions: {record['questions_asked']}")
            
            # Go back to job page
            await page.goto(job_url, wait_until="domcontentloaded")
            
        # Check for iframe
        else:
            iframe = await page.query_selector('iframe[src*="apply"], iframe[src*="career"]')
            if iframe:
                iframe_src = await iframe.get_attribute("src")
                record["apply_link"] = iframe_src
                record["apply_type"] = "iframe"
                record["application_status"] = "iframe_detected"
                print(f"   ✓ Apply type: iframe")
                print(f"   ✓ Link: {iframe_src}")
            else:
                # Inline form
                has_questions = await detect_application_questions(page)
                record["apply_type"] = "inline_apply"
                record["apply_link"] = job_url
                record["application_status"] = "inline_form"
                record["questions_asked"] = "yes" if has_questions else "no"
                print(f"   ✓ Apply type: inline (Naukri portal)")
                print(f"   ✓ Questions: {record['questions_asked']}")
        
    except Exception as e:
        record["application_status"] = "error"
        record["apply_type"] = "error"
        print(f"   ❌ Error: {str(e)[:150]}")
    
    return record


# =========================
# MAIN SCRAPER
# =========================
async def scrape_naukri_jobs():
    """Main async scraper function"""
    
    # Initialize CSV
    init_csv_file()
    processed_ids = get_processed_job_ids()
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        )
        page = await context.new_page()
        
        # Popup tracker
        popup_tracker = {"popup_page": None}
        
        def handle_popup(popup):
            popup_tracker["popup_page"] = popup
            print(f"    🔗 Popup detected: {popup.url}")
        
        page.on("popup", handle_popup)
        
        # =========================
        # MANUAL LOGIN
        # =========================
        print("🔐 Opening Naukri login page...")
        await page.goto("https://www.naukri.com/nlogin/login", timeout=60000)
        
        print("\n" + "=" * 70)
        print("MANUAL LOGIN REQUIRED")
        print("1. Enter your credentials")
        print("2. Solve CAPTCHA if prompted")
        print("3. Wait until you reach the dashboard/home page")
        print("=" * 70)
        
        while True:
            user_input = input("\nType 'done' after successful login: ").strip().lower()
            if user_input == "done":
                break
        
        print("\n✅ Login confirmed. Starting scraping...\n")
        await asyncio.sleep(2)
        
        # =========================
        # PROCESS EACH SEARCH URL
        # =========================
        total_scraped = 0
        
        for url_index, search_url in enumerate(SEARCH_URLS, 1):
            print("\n" + "=" * 70)
            print(f"SEARCH URL {url_index}/{len(SEARCH_URLS)}")
            print(f"URL: {search_url}")
            print("=" * 70)
            
            # Scrape job list from search
            jobs = await scrape_jobs_from_search(page, search_url, START_PAGE, END_PAGE)
            print(f"\n✅ Collected {len(jobs)} unique jobs from search\n")
            
            # Filter out already processed jobs
            jobs_to_process = [j for j in jobs if j.get("jobId") not in processed_ids]
            jobs_to_process = jobs_to_process[:MAX_JOBS_PER_SEARCH]
            
            skipped = len(jobs) - len(jobs_to_process)
            if skipped > 0:
                print(f"⏭ Skipping {skipped} already processed jobs\n")
            
            print(f"📋 Processing {len(jobs_to_process)} new jobs\n")
            
            # Process each job
            for idx, job in enumerate(jobs_to_process, 1):
                record = await process_job(
                    page, job, popup_tracker, 
                    idx, len(jobs_to_process)
                )
                
                # Save to CSV
                append_to_csv(record)
                total_scraped += 1
                print(f"   💾 Saved to CSV (Total: {total_scraped})")
                
                # Random delay between jobs
                delay = random.uniform(*DELAY_BETWEEN_JOBS)
                await asyncio.sleep(delay)
        
        await browser.close()
        
        # =========================
        # FINAL SUMMARY
        # =========================
        print("\n" + "=" * 70)
        print("SCRAPING COMPLETED")
        print("=" * 70)
        print(f"✅ Total jobs scraped: {total_scraped}")
        print(f"📄 Output file: {OUTPUT_CSV}")
        print("=" * 70)


# =========================
# RUN SCRAPER
# =========================
if __name__ == "__main__":
    asyncio.run(scrape_naukri_jobs())