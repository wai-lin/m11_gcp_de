1. Prerequisites & Installation

You cannot use standard Cloud Functions for this (they lack the browser dependencies). Use Cloud Run with a custom Docker container.

```Bash
# Install the library and the stealth plugin
pip install playwright playwright-stealth
# Install the browser binaries (only for local testing)
playwright install chromium
```

2. The Stealth Implementation (Python)

The playwright-stealth plugin patches specific leaks (like the HeadlessChrome string and navigator.webdriver flag) that TikTok's bot-detection systems look for first.

```Python
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import stealth_async

async def scrape_tiktok(profile_url):
    async with async_playwright() as p:
        # 1. Launch a browser (use 'headless=True' for your final GCP deployment)
        browser = await p.chromium.launch(headless=True)

        # 2. Create a new context
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        # 3. Create page and APPLY STEALTH
        page = await context.new_page()
        await stealth_async(page)

        # 4. Navigate and wait for content
        await page.goto(profile_url)

        # TikTok is JS-heavy; wait for the "universal data" script or a specific element
        await page.wait_for_selector('[data-e2e="user-post-item-list"]')

        # 5. Extract data (Example: Get the follower count)
        follower_count = await page.inner_text('[data-e2e="followers-count"]')

        print(f"Followers: {follower_count}")
        await browser.close()
        return follower_count

# Run it
asyncio.run(scrape_tiktok("https://www.tiktok.com/@khaby.lame"))
```

3. The "Docker Secret" (Crucial for GCP)

To run this on Google Cloud Run, your Dockerfile must include the system-level dependencies for Chromium. If you don't do this, your code will crash immediately.

```Dockerfile
# Use the official Playwright image (includes browsers and OS dependencies)
FROM mcr.microsoft.com/playwright/python:v1.40.0-focal

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Cloud Run listens on 8080
CMD ["python", "main.py"]
```

4. Pro-Tips for your Demo

Avoid "Headless" Detection: Even with stealth, headless browsers sometimes fail. If TikTok still blocks you, try setting a realistic viewport size in your new_context() (e.g., viewport={'width': 1280, 'height': 720}).

The "Rehydration" Shortcut: Instead of scraping the UI, use Playwright to grab the content of the <script id="__UNIVERSAL_DATA_FOR_REHYDRATION__"> tag. It contains a massive JSON object with all the profile stats, which is much faster than parsing HTML elements.

Randomize Your Timing: Don't just goto() and scrape. Add a await asyncio.sleep(random.uniform(1, 3)) to simulate a human-like pause before extracting the data.
