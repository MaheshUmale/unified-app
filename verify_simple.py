import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("http://localhost:3000/orderflow")
        await asyncio.sleep(5)
        status = await page.evaluate("document.getElementById('status-text').textContent")
        print(f"Status: {status}")

        # Test change TPC
        await page.evaluate("document.getElementById('ticks-input').value = 50")
        await page.evaluate("document.getElementById('ticks-input').dispatchEvent(new Event('change'))")
        await asyncio.sleep(1)
        status = await page.evaluate("document.getElementById('status-text').textContent")
        print(f"Status after change: {status}")

        await asyncio.sleep(5)
        status = await page.evaluate("document.getElementById('status-text').textContent")
        print(f"Final Status: {status}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
