import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()
        await page.goto("http://localhost:3000/orderflow")
        await page.wait_for_selector("text=LIVE", timeout=15000)

        # Zoom in a lot
        await page.mouse.move(800, 400)
        for _ in range(50):
            await page.mouse.wheel(0, -500)
            await asyncio.sleep(0.05)

        spacing = await page.evaluate("charts.main.timeScale().options().barSpacing")
        print(f"Final Bar Spacing: {spacing}")

        await page.screenshot(path="orderflow_zoomed.png")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
