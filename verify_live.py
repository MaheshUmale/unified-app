
import asyncio
from playwright.async_api import async_playwright
import time

async def verify_live():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Navigate to the app
        print("Navigating to http://localhost:5000")
        await page.goto("http://localhost:5000")
        await page.wait_for_load_state("networkidle")

        # Wait for Spot price to appear (confirms Socket.IO connection)
        print("Waiting for LIVE Spot Price...")
        try:
            # Look for the spot price in the header
            # <span class="text-white font-black font-mono-data text-sm">25336.45</span>
            await page.wait_for_selector("header span.font-mono-data.text-sm", timeout=20000)
            spot = await page.locator("header span.font-mono-data.text-sm").first.inner_text()
            print(f"Verified LIVE Spot Price: {spot}")

            # Wait for ATM strike
            atm = await page.locator("header span.text-brand-blue.font-mono-data.text-sm").inner_text()
            print(f"Verified LIVE ATM Strike: {atm}")

            # Check strategy dashboard
            print("Checking Strategy Dashboard...")
            await page.wait_for_selector("h2.text-3xl", timeout=10000)
            decision = await page.locator("h2.text-3xl").inner_text()
            print(f"LIVE Strategy Decision: {decision}")

            # Take a screenshot
            await page.screenshot(path="live_verification.png", full_page=True)
            print("Screenshot saved: live_verification.png")

        except Exception as e:
            print(f"Live verification failed: {e}")
            await page.screenshot(path="live_failed.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify_live())
