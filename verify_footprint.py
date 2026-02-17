import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        print("Opening Orderflow Terminal for Footprint check...")
        try:
            await page.goto("http://localhost:3000/orderflow", timeout=10000)

            # Wait for LIVE
            await page.wait_for_selector("text=LIVE", timeout=15000)

            # Zoom in using mouse wheel or keyboard
            # Alternatively, use the API to set barSpacing if possible,
            # but zooming in manually on the canvas/chart area is better.
            await page.mouse.move(800, 400)
            for _ in range(20):
                await page.keyboard.press("Control++") # Some charts use this
                await page.mouse.wheel(0, -100) # Zoom in
                await asyncio.sleep(0.1)

            await asyncio.sleep(2)
            await page.screenshot(path="orderflow_footprint.png")
            print("Footprint screenshot saved.")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
