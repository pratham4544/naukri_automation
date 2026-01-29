from playwright.async_api import async_playwright
import asyncio
import json
from datetime import datetime


SEARCH_URL = "https://www.naukri.com/ai-engineer-jobs-in-pune?k=ai%20engineer&l=pune%2C%20remote&experience=2"
MAX_PAGES = 3          # 3 pages ≈ 60 jobs (safe)
MAX_JOBS = 30          # limit apply-link extraction


# =========================
# SCRAPE JOBS FROM SEARCH (XHR)
# =========================
async def scrape_jobs_from_search(page, search_url, max_pages):
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

    for page_no in range(1, max_pages + 1):
        url = f"{search_url}&pageNo={page_no}"
        print(f"🔍 Loading search page {page_no}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        await asyncio.sleep(5)  # allow API to fire

    return jobs


# =========================
# MAIN APPLY LINK EXTRACTION
# =========================
async def extract_apply_links():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
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
            print(f"    🔗 Popup detected: {popup.url}")

        page.on("popup", handle_popup)

        # =========================
        # MANUAL LOGIN
        # =========================
        print("Opening Naukri login page...")
        await page.goto("https://www.naukri.com/nlogin/login", timeout=60000)

        print("\n" + "=" * 60)
        print("PLEASE LOGIN MANUALLY")
        print("1. Enter email/password")
        print("2. Solve CAPTCHA if any")
        print("3. Click Login")
        print("=" * 60)

        while True:
            if input("Type 'done' after successful login: ").strip().lower() == "done":
                break

        print("\n✓ Login confirmed\n")
        await asyncio.sleep(2)

        # =========================
        # SCRAPE JOB LIST
        # =========================
        jobs = await scrape_jobs_from_search(page, SEARCH_URL, MAX_PAGES)
        print(f"\n✓ Collected {len(jobs)} jobs from search\n")

        results = []

        # =========================
        # PROCESS EACH JOB
        # =========================
        for i, job in enumerate(jobs[:MAX_JOBS], 1):
            print(f"\n[{i}/{min(len(jobs), MAX_JOBS)}] {job.get('title')} at {job.get('companyName')}")

            job_url = f"https://www.naukri.com{job.get('jdURL')}"
            popup_page = None

            apply_link = None
            apply_type = None

            try:
                await page.goto(job_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(4)

                # Already applied?
                already_applied = False
                try:
                    already_applied = (
                        await page.locator('text=/already applied/i').count() > 0 or
                        await page.locator('.applied').count() > 0
                    )
                except:
                    pass

                if already_applied:
                    apply_type = "already_applied"
                    print("  ⚠ Already applied")

                else:
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
                        print("  ❌ No apply button found")

                    else:
                        # Check direct href
                        href = await page.evaluate(
                            "(el) => el.href || el.getAttribute('href')",
                            apply_button
                        )

                        if href and href.startswith("http"):
                            apply_link = href
                            apply_type = "external" if "naukri.com" not in href else "internal"
                            print(f"  ✓ Apply type: {apply_type}")
                            print(f"  ✓ Link: {apply_link}")

                        else:
                            current_url = page.url
                            await apply_button.click()
                            await asyncio.sleep(3)

                            if popup_page:
                                apply_link = popup_page.url
                                apply_type = "external_popup" if "naukri.com" not in apply_link else "internal_popup"
                                print(f"  ✓ Apply type: {apply_type}")
                                print(f"  ✓ Link: {apply_link}")
                                await popup_page.close()

                            elif page.url != current_url:
                                apply_link = page.url
                                apply_type = "external" if "naukri.com" not in apply_link else "internal"
                                print(f"  ✓ Apply type: {apply_type}")
                                print(f"  ✓ Link: {apply_link}")
                                await page.goto(job_url, wait_until="domcontentloaded")

                            else:
                                iframe = await page.query_selector(
                                    'iframe[src*="apply"], iframe[src*="career"]'
                                )
                                if iframe:
                                    apply_link = await iframe.get_attribute("src")
                                    apply_type = "iframe"
                                    print(f"  ✓ Apply type: iframe")
                                    print(f"  ✓ Link: {apply_link}")
                                else:
                                    apply_type = "inline_or_unknown"
                                    apply_link = job_url
                                    print("  ⚠ Apply inside Naukri (no external link)")

                results.append({
                    "job_id": job.get("jobId"),
                    "title": job.get("title"),
                    "company": job.get("companyName"),
                    "job_url": job_url,
                    "apply_type": apply_type,
                    "apply_link": apply_link
                })

            except Exception as e:
                print(f"  ❌ Error: {str(e)[:120]}")
                results.append({
                    "job_id": job.get("jobId"),
                    "title": job.get("title"),
                    "company": job.get("companyName"),
                    "job_url": job_url,
                    "apply_type": "error",
                    "error": str(e)[:200]
                })

            await asyncio.sleep(3)

        await browser.close()

        # =========================
        # SAVE OUTPUT
        # =========================
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = f"naukri_apply_links_{ts}.json"

        with open(output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2, ensure_ascii=False)

        print("\n" + "=" * 60)
        print("SUMMARY")
        print("=" * 60)

        counts = {}
        for r in results:
            t = r.get("apply_type", "unknown")
            counts[t] = counts.get(t, 0) + 1

        for k, v in sorted(counts.items()):
            print(f"{k}: {v}")

        print(f"\n✓ Saved to {output}")


if __name__ == "__main__":
    asyncio.run(extract_apply_links())
