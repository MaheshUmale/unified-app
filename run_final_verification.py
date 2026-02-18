
import asyncio
from playwright.async_api import async_playwright
import time

async def run_verification():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        # 1. Index Chart
        print("Capturing Index Chart...")
        await page.goto("http://localhost:8000/")
        await asyncio.sleep(5) # Wait for data load
        await page.screenshot(path="verification_index_final.png")

        # 2. Modern Dashboard
        print("Capturing Modern Dashboard...")
        await page.goto("http://localhost:8000/modern")
        await asyncio.sleep(5)
        await page.screenshot(path="verification_modern_final.png")

        # 3. Options Dashboard
        print("Capturing Options Dashboard...")
        await page.goto("http://localhost:8000/options")
        await asyncio.sleep(5)
        await page.screenshot(path="verification_options_final.png")

        # 4. Orderflow Chart
        print("Capturing Orderflow Chart...")
        await page.goto("http://localhost:8000/orderflow")
        await asyncio.sleep(5)
        await page.screenshot(path="verification_orderflow_final.png")

        await browser.close()
        print("Verification screenshots captured.")

if __name__ == "__main__":
    asyncio.run(run_verification())
