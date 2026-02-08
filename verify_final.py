
import asyncio
from playwright.async_api import async_playwright
import time

async def verify():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))

        # Go to app
        await page.goto("http://localhost:5051")
        await page.wait_for_selector("#chart-0")

        # Clear localStorage and reload
        await page.evaluate("localStorage.clear();")
        await page.reload()
        await page.wait_for_selector("#chart-0")

        # Wait for indicators to load
        await asyncio.sleep(10)

        # Take screenshot
        await page.screenshot(path="/home/jules/verification/final_no_labels_test_v3.png")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(verify())
