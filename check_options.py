import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('http://localhost:5051')
        await page.wait_for_selector('select')
        options = await page.eval_on_selector_all('select >> nth=0 >> option', 'elements => elements.map(e => e.innerText)')
        print(f"Options: {options}")
        await browser.close()

asyncio.run(main())
