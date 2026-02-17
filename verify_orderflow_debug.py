import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
        page.on("pageerror", lambda exc: print(f"PAGE ERROR: {exc}"))

        print("Opening Orderflow Terminal...")
        try:
            await page.goto("http://localhost:3000/orderflow", timeout=10000)

            # Wait for history to load
            await asyncio.sleep(5)

            status = await page.inner_text("#status-text")
            print(f"Status after 5s: {status}")

            # Check if charts are rendered
            canvas_data = await page.evaluate("document.getElementById('footprint-canvas').toDataURL()")
            print(f"Canvas Data length: {len(canvas_data)}")

            await page.screenshot(path="orderflow_debug.png")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
