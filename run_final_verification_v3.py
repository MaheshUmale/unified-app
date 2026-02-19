
import asyncio
from playwright.async_api import async_playwright
import time

async def run_verification():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        # 1. Index Chart + OI Profile + Analysis
        print("Capturing Index Chart with OI & Analysis...")
        await page.goto("http://localhost:3000/")
        await asyncio.sleep(5) # Wait for data load

        # Toggle Analysis
        await page.click("#analysisToggle")
        # Toggle OI
        await page.click("#oiProfileToggle")
        await asyncio.sleep(3)
        await page.screenshot(path="verification_index_with_oi.png")

        # 2. Modern Dashboard (wait, if it doesn't exist I'll skip it or check other ones)
        # In my memory it exists, but I couldn't find the template.
        # Let's try /options and /orderflow

        # 3. Options Dashboard
        print("Capturing Options Dashboard...")
        await page.goto("http://localhost:3000/options")
        await asyncio.sleep(5)
        await page.screenshot(path="verification_options_v3.png")

        # 4. Orderflow Chart
        print("Capturing Orderflow Chart...")
        await page.goto("http://localhost:3000/orderflow")
        await asyncio.sleep(5)
        await page.screenshot(path="verification_orderflow_v3.png")

        await browser.close()
        print("Verification screenshots captured.")

if __name__ == "__main__":
    asyncio.run(run_verification())
