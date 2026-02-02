import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        await page.goto('http://localhost:5051')
        await asyncio.sleep(10)  # Wait for data to load
        await page.screenshot(path='/home/jules/verification/live_fix_verify.png', full_page=True)
        await browser.close()

asyncio.run(main())
