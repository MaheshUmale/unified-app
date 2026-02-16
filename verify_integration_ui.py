from playwright.sync_api import sync_playwright
import time
import requests
import os

def verify_integrated_system():
    print("Checking if server is running on port 3000...")
    try:
        requests.get('http://localhost:3000/health')
        print("Server is up!")
    except Exception as e:
        print(f"Server not running: {e}")
        return

    # Create verification directory
    os.makedirs('verification', exist_ok=True)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1600, 'height': 1000})

        # 1. Main Terminal
        print("Navigating to Main Terminal...")
        try:
            page.goto('http://localhost:3000/', timeout=60000)
            time.sleep(10) # Wait for chart initialization
            page.screenshot(path='verification/integrated_terminal_chart.png')
            print("Captured Terminal Chart")

            # 2. Options Dashboard
            print("Navigating to Options Dashboard...")
            page.goto('http://localhost:3000/options', timeout=60000)
            time.sleep(5)
            page.screenshot(path='verification/integrated_options_dashboard.png')
            print("Captured Options Dashboard")

            # 3. System Tab
            print("Switching to System Tab...")
            page.click('button[data-tab="system"]')
            time.sleep(3)
            page.screenshot(path='verification/integrated_system_tab.png')
            print("Captured System Monitoring Tab")

            # 4. Scalper Tab
            print("Switching to Scalper Tab...")
            page.click('button[data-tab="scalper"]')
            time.sleep(2)
            page.screenshot(path='verification/integrated_scalper_tab.png')
            print("Captured Scalper Tab")

        except Exception as e:
            print(f"Error during verification: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_integrated_system()
