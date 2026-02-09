import asyncio
from playwright.async_api import async_playwright
import os

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Verify DB Viewer
        print("Navigating to DB Viewer...")
        await page.goto("http://localhost:5051/db-viewer")
        await page.wait_for_timeout(2000)
        await page.screenshot(path="verification/db_viewer.png")
        print("DB Viewer screenshot saved.")

        # Verify Main Dashboard
        print("Navigating to Main Dashboard...")
        await page.goto("http://localhost:5051/")
        await page.wait_for_timeout(2000)
        await page.screenshot(path="verification/dashboard.png")
        print("Dashboard screenshot saved.")

        await browser.close()

if __name__ == "__main__":
    if not os.path.exists("verification"):
        os.makedirs("verification")
    asyncio.run(main())
