import asyncio
from playwright.async_api import async_playwright

async def run():
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))

        print("Opening Orderflow Terminal...")
        try:
            await page.goto("http://localhost:3000/orderflow", timeout=15000)

            # Wait for some status change
            print("Waiting for status change...")
            await page.wait_for_selector("#status-text", timeout=10000)

            # Wait until it says LIVE or CONNECTED
            for _ in range(20):
                status = await page.inner_text("#status-text")
                print(f"Current Status: {status}")
                if status in ["LIVE", "CONNECTED", "Live", "Connected"]:
                    break
                await asyncio.sleep(1)

            print("Changing TPC to 20...")
            await page.fill("#ticks-input", "20")
            await page.keyboard.press("Enter")

            # Check if it goes into re-aggregating
            await asyncio.sleep(0.5)
            status = await page.inner_text("#status-text")
            print(f"Status after change: {status}")

            # Wait for it to finish re-aggregating
            for _ in range(20):
                status = await page.inner_text("#status-text")
                if status in ["LIVE", "CONNECTED", "Live", "Connected"]:
                    print(f"Finished Re-aggregating. Status: {status}")
                    break
                await asyncio.sleep(1)

            await page.screenshot(path="tpc_responsiveness.png")
            print("Screenshot saved.")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(run())
