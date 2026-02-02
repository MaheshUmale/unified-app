import asyncio
from playwright.async_api import async_playwright

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto('http://localhost:5051')
        await page.wait_for_selector('select')

        # Print all selects' options
        selects_count = await page.locator('select').count()
        for i in range(selects_count):
            options = await page.eval_on_selector_all(f'select >> nth={i} >> option', 'elements => elements.map(e => e.innerText)')
            print(f"Select {i} Options: {options}")

        await browser.close()

asyncio.run(main())
