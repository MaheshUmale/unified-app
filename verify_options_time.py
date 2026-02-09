import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        # Go to options dashboard
        await page.goto('http://localhost:5051/options')
        await page.wait_for_timeout(5000)

        # Check last update time
        last_update = await page.inner_text('#lastUpdateTime')
        print(f"Last Update Time in UI: {last_update}")

        await page.screenshot(path='/home/jules/verification/options_ist_time.png')

        # Switch to PCR Trend to check chart labels
        await page.click('#tab-pcr')
        await page.wait_for_timeout(3000)
        await page.screenshot(path='/home/jules/verification/pcr_trend_ist_time.png')

        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
