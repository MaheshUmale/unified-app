import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        await page.goto('http://localhost:5051')
        await page.wait_for_selector('select >> nth=1')

        # Select FINNIFTY
        await page.select_option('select >> nth=1', value='FINNIFTY')

        await asyncio.sleep(10)
        await page.screenshot(path='/home/jules/verification/finnifty_verify_v4.png', full_page=True)
        await browser.close()

asyncio.run(main())
