import asyncio
import pandas as pd
import re
from playwright.async_api import async_playwright

EMAIL_REGEX = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
KEYWORDS = ("career", "careers", "jobs", "hr", "recruit", "talent")

CONCURRENCY = 8
semaphore = asyncio.Semaphore(CONCURRENCY)


def normalize_company(name: str) -> str:
    return re.sub(r"\s+", " ", name.lower().strip())


async def get_company_emails(browser, company):
    search_url = f"https://www.bing.com/search?q={company}+careers+email"

    async with semaphore:
        page = await browser.new_page()
        try:
            await page.goto(search_url, timeout=60000)
            content = await page.content()

            emails = set(re.findall(EMAIL_REGEX, content))

            filtered = [
                e for e in emails
                if any(k in e.lower() for k in KEYWORDS)
            ]

            if not filtered and emails:
                filtered = [next(iter(emails))]

            return ", ".join(filtered)

        except Exception as e:
            print(f"[ERROR] {company}: {e}")
            return ""

        finally:
            await page.close()


async def process_csv():
    df = pd.read_csv("test4.csv")

    # clean company names
    df["company"] = (
        df["company"]
        .astype(str)
        .str.replace(r"\n\d+\.?\d*\s+Reviews?", "", regex=True)
        .str.strip()
    )

    df["company_norm"] = df["company"].apply(normalize_company)
    df["career_email"] = ""

    # 🔑 UNIQUE companies only
    unique_companies = df["company_norm"].unique()
    print(f"Unique companies: {len(unique_companies)}")

    email_cache = {}  # company_norm -> email

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,
            args=["--disable-blink-features=AutomationControlled"]
        )

        tasks = {
            company: asyncio.create_task(
                get_company_emails(browser, company)
            )
            for company in unique_companies
        }

        for company, task in tasks.items():
            email_cache[company] = await task
            print(f"Fetched [{company}]: {email_cache[company]}")

        await browser.close()

    # 🔁 map back to all rows
    df["career_email"] = df["company_norm"].map(email_cache)

    df.drop(columns=["company_norm"], inplace=True)
    df.to_csv("output_with_emails_2.csv", index=False)

    print("✅ Done. No duplicate searches performed.")


if __name__ == "__main__":
    asyncio.run(process_csv())
