from playwright.sync_api import sync_playwright
import time
import os

def run_verification():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={'width': 1280, 'height': 800})

        # 1. Main Page - Check per-chart zoom controls
        page = context.new_page()
        page.goto("http://localhost:3000/")
        time.sleep(2)

        # Take screenshot of main page with zoom controls
        page.screenshot(path="verification_main_v4.png")

        # 2. Options Page - Check cleaned up tabs
        page.goto("http://localhost:3000/options")
        time.sleep(2)
        page.screenshot(path="verification_options_v4.png")

        # 3. DB Viewer - Check schema
        page.goto("http://localhost:3000/db-viewer")
        time.sleep(2)
        # Click on a table if list is loaded
        try:
            page.wait_for_selector(".group.p-2", timeout=5000)
            page.click(".group.p-2")
            time.sleep(1)
        except:
            print("Could not find table list")

        page.screenshot(path="verification_db_v4.png")

        # 4. Orderflow - Check theme
        page.goto("http://localhost:3000/orderflow")
        time.sleep(2)
        page.screenshot(path="verification_orderflow_v4.png")

        browser.close()

if __name__ == "__main__":
    run_verification()
