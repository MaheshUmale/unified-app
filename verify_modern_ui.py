import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        # Go to the modern dashboard
        print("Navigating to http://localhost:3000/modern")
        await page.goto("http://localhost:3000/modern")

        # Wait for some elements to load
        await asyncio.sleep(5)

        # Take a screenshot
        await page.screenshot(path="modern_dashboard_verify.png")
        print("Screenshot saved to modern_dashboard_verify.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
