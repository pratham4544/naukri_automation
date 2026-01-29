from playwright.async_api import async_playwright
import asyncio
import json
from datetime import datetime
import random
import os
from typing import Dict

# =========================
# CONFIG
# =========================
SEARCH_URL = (
    "https://www.naukri.com/ai-engineer-jobs-in-remote-2"
    "?k=ai+engineer&l=pune%2C+remote&experience=2"
)

START_PAGE = 5
END_PAGE = 20
MAX_JOBS_TO_PROCESS = 1200   # safety cap

OUTPUT_FILE = None


# =========================
# SAFE FILE HANDLING
# =========================
def init_output_file():
    global OUTPUT_FILE
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    OUTPUT_FILE = f"naukri_jobs_with_jd_and_apply_{ts}.json"

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump([], f, indent=2)

    print(f"📄 Output file initialized: {OUTPUT_FILE}")


def append_result_to_file(record: Dict):
    with open(OUTPUT_FILE, "r+", encoding="utf-8") as f:
        data = json.load(f)
        data.append(record)
        f.seek(0)
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.truncate()

    print("📄 Saved job to file")


# =========================
# SCRAPE JOBS FROM SEARCH (XHR)
# =========================
async def scrape_jobs_from_search(page, search_url, start_page, end_page):
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

        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(random.uniform(4, 7))

        print(f"   → Jobs collected so far: {len(jobs)}")

    return jobs


# =========================
# EXTRACT FULL JD (SAFE)
# =========================
async def extract_full_jd(page):
    return await page.evaluate("""
    () => {
        const textIncludes = (selector, keyword) => {
            const els = Array.from(document.querySelectorAll(selector));
            const el = els.find(e => e.innerText.includes(keyword));
            return el ? el.innerText.trim() : null;
        };

        const getText = (sel) =>
            document.querySelector(sel)?.innerText?.trim() || null;

        const getAllText = (sel) =>
            Array.from(document.querySelectorAll(sel))
                .map(e => e.innerText.trim())
                .filter(Boolean);

        return {
            title: getText('h1'),
            company: getText('.styles_jd-header-comp-name__MvqAI, .jd-header-comp-name'),
            experience: getText('.styles_jhc__exp'),
            salary: getText('.styles_jhc__salary'),
            location: getText('.styles_jhc__location'),
            posted: textIncludes('span', 'Posted'),
            openings: textIncludes('span', 'Opening'),
            applicants: textIncludes('span', 'Applicants'),
            description:
                document.querySelector('.styles_JDC__dang-inner-html__h0K4t, .job-desc')
                    ?.innerText?.trim() || null,
            skills: getAllText(
                '.styles_key-skill__GIPn_, .key-skill, a[href*="skills"]'
            )
        };
    }
    """)


# =========================
# MAIN SCRIPT
# =========================
async def extract_jobs_with_jd_and_apply():
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

        popup_page = None

        def handle_popup(popup):
            nonlocal popup_page
            popup_page = popup
            print(f"🔗 Popup detected: {popup.url}")

        page.on("popup", handle_popup)

        # =========================
        # MANUAL LOGIN
        # =========================
        print("🔐 Opening Naukri login page...")
        await page.goto("https://www.naukri.com/nlogin/login", timeout=60000)

        print("\n" + "=" * 60)
        print("MANUAL LOGIN REQUIRED")
        print("1. Login in browser")
        print("2. Solve CAPTCHA if any")
        print("3. Reach dashboard")
        print("=" * 60)

        while True:
            if input("Type 'done' after login: ").strip().lower() == "done":
                break

        print("✅ Login confirmed\n")
        await asyncio.sleep(2)

        # =========================
        # INIT OUTPUT FILE
        # =========================
        init_output_file()

        # =========================
        # SCRAPE JOB LIST
        # =========================
        jobs = await scrape_jobs_from_search(
            page, SEARCH_URL, START_PAGE, END_PAGE
        )

        print(f"\n✅ Total unique jobs collected: {len(jobs)}\n")

        # =========================
        # PROCESS EACH JOB
        # =========================
        for idx, job in enumerate(jobs[:MAX_JOBS_TO_PROCESS], 1):
            print(
                f"\n[{idx}/{min(len(jobs), MAX_JOBS_TO_PROCESS)}] "
                f"{job.get('title')} at {job.get('companyName')}"
            )

            job_url = f"https://www.naukri.com{job.get('jdURL')}"
            popup_page = None

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)

                jd_data = await extract_full_jd(page)

                apply_link = None
                apply_type = None

                apply_button = None
                selectors = [
                    'button:has-text("Apply")',
                    'a:has-text("Apply")',
                    '#apply-button',
                    '.apply-button',
                    'button[class*="apply"]',
                    'a[class*="apply"]'
                ]

                for sel in selectors:
                    if await page.locator(sel).count() > 0:
                        apply_button = await page.locator(sel).first.element_handle()
                        break

                if not apply_button:
                    apply_type = "no_apply_button"

                else:
                    href = await page.evaluate(
                        "(el) => el.href || el.getAttribute('href')",
                        apply_button
                    )

                    if href and href.startswith("http"):
                        apply_link = href
                        apply_type = "external" if "naukri.com" not in href else "internal"

                    else:
                        current_url = page.url
                        await apply_button.click()
                        await asyncio.sleep(3)

                        if popup_page:
                            apply_link = popup_page.url
                            apply_type = (
                                "external_popup"
                                if "naukri.com" not in apply_link
                                else "internal_popup"
                            )
                            await popup_page.close()

                        elif page.url != current_url:
                            apply_link = page.url
                            apply_type = (
                                "external"
                                if "naukri.com" not in apply_link
                                else "internal"
                            )

                        else:
                            iframe = await page.query_selector(
                                'iframe[src*="apply"], iframe[src*="career"]'
                            )
                            if iframe:
                                apply_link = await iframe.get_attribute("src")
                                apply_type = "iframe"
                            else:
                                apply_type = "inline_apply"
                                apply_link = job_url

                append_result_to_file({
                    "job_id": job.get("jobId"),
                    "job_url": job_url,
                    "apply_type": apply_type,
                    "apply_link": apply_link,
                    "job_details": jd_data
                })

            except Exception as e:
                print(f"❌ Error: {str(e)[:120]}")
                append_result_to_file({
                    "job_id": job.get("jobId"),
                    "job_url": job_url,
                    "apply_type": "error",
                    "error": str(e)[:200]
                })

            await asyncio.sleep(random.uniform(3, 6))

        await browser.close()
        print(f"\n✅ Scraping completed. Data saved in {OUTPUT_FILE}")


if __name__ == "__main__":
    asyncio.run(extract_jobs_with_jd_and_apply())
