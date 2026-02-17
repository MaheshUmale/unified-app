import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        print("Opening Orderflow Terminal...")
        try:
            # Connect to the local server (assuming it's running or we'll start it)
            await page.goto("http://localhost:3000/orderflow", timeout=10000)

            # Wait for "Live" or "Connected" status
            await page.wait_for_selector("#status-text", timeout=15000)
            status = await page.inner_text("#status-text")
            print(f"Initial Status: {status}")

            # Check for canvas
            canvas = await page.query_selector("#footprint-canvas")
            if canvas:
                print("Canvas detected.")
            else:
                print("Canvas NOT detected.")

            # Wait for some time to see if it stays responsive
            await asyncio.sleep(3)
            status = await page.inner_text("#status-text")
            print(f"Status after 3s: {status}")

            # Take a screenshot
            await page.screenshot(path="orderflow_verify.png")
            print("Screenshot saved to orderflow_verify.png")

        except Exception as e:
            print(f"Error during verification: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
