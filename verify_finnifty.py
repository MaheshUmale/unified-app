import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        await page.goto('http://localhost:5051')
        await asyncio.sleep(5)

        # Select FINNIFTY from the dropdown
        await page.click('select >> nth=0') # Select index dropdown
        await page.select_option('select >> nth=0', label='NIFTY FIN SERVICE')

        await asyncio.sleep(5)
        await page.screenshot(path='/home/jules/verification/finnifty_verify.png', full_page=True)
        await browser.close()

asyncio.run(main())
