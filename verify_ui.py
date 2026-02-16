import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        try:
            print("Navigating to dashboard...")
            await page.goto("http://localhost:3000/options", timeout=30000)
            print("Dashboard loaded. Waiting for data...")
            await asyncio.sleep(10)
            await page.screenshot(path="dashboard_screenshot.png")
            print("Screenshot saved to dashboard_screenshot.png")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

asyncio.run(main())
