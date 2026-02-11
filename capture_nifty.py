import asyncio
from playwright.async_api import async_playwright
import os

async def capture_nifty_screens():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})

        try:
            print("Navigating to http://localhost:3000/options...")
            await page.goto("http://localhost:3000/options")

            # Wait for data to load
            await page.wait_for_timeout(10000)

            # Select NIFTY
            await page.select_option('#underlyingSelect', 'NSE:NIFTY')
            await page.wait_for_timeout(5000)

            tabs = [
                ('chain', '1_option_chain.png'),
                ('oi-analysis', '2_oi_analysis.png'),
                ('pcr-trend', '3_pcr_trend.png'),
                ('greeks', '4_greeks.png'),
                ('buildup', '5_oi_buildup.png'),
                ('strategies', '6_strategies.png'),
                ('alerts', '7_alerts.png')
            ]

            for tab_id, filename in tabs:
                print(f"Capturing {tab_id}...")
                await page.click(f'button[data-tab="{tab_id}"]')
                await page.wait_for_timeout(2000)
                await page.screenshot(path=filename, full_page=False)

            print("Screenshots captured successfully.")

        except Exception as e:
            print(f"Error during capture: {e}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(capture_nifty_screens())
