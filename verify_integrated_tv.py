import asyncio
import os
import subprocess
import time
from playwright.async_api import async_playwright

async def verify_system():
    # Start the server
    print("Starting API server...")
    server_process = subprocess.Popen(
        ["python3", "backend/api_server.py"],
        env={**os.environ, "PORT": "3000"}
    )

    # Wait for server to start
    time.sleep(10)

    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page()

        try:
            # 1. Check Options Dashboard
            print("Checking Options Dashboard...")
            await page.goto("http://localhost:3000/options")
            await page.wait_for_timeout(5000)
            await page.screenshot(path="verification/integrated_options_dashboard.png")

            # 2. Check System Tab
            print("Checking System Tab...")
            await page.click("button[data-tab='system']")
            await page.wait_for_timeout(2000)
            await page.screenshot(path="verification/integrated_system_tab.png")

            # 3. Check Scalper Tab
            print("Checking Scalper Tab...")
            await page.click("button[data-tab='scalper']")
            await page.wait_for_timeout(2000)
            await page.screenshot(path="verification/integrated_scalper_tab.png")

            # 4. Check Terminal (Chart with Indicators)
            print("Checking Terminal Chart...")
            await page.goto("http://localhost:3000/")
            await page.wait_for_timeout(5000)
            await page.screenshot(path="verification/integrated_terminal_chart.png")

            print("Verification screenshots captured in verification/ folder.")

        except Exception as e:
            print(f"Error during verification: {e}")
        finally:
            await browser.close()
            server_process.terminate()
            server_process.wait()

if __name__ == "__main__":
    if not os.path.exists("verification"):
        os.makedirs("verification")
    asyncio.run(verify_system())
