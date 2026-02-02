import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('http://localhost:5051')
        await page.wait_for_selector('select >> nth=1')
        values = await page.eval_on_selector_all('select >> nth=1 >> option', 'elements => elements.map(e => e.value)')
        print(f"Values: {values}")
        await browser.close()

asyncio.run(main())
