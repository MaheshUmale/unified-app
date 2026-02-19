
import asyncio
from playwright.async_api import async_playwright

async def run_verification():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        print("Capturing Main Chart (Initial)...")
        await page.goto("http://localhost:3000/")
        await asyncio.sleep(10)
        await page.screenshot(path="verification_index_raw.png")

        print("Toggling Analysis...")
        await page.click("#analysisToggle")
        await asyncio.sleep(2)
        await page.screenshot(path="verification_index_analysis.png")

        print("Toggling OI Profile...")
        await page.click("#oiProfileToggle")
        await asyncio.sleep(5)
        await page.screenshot(path="verification_index_full.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run_verification())
