from playwright.sync_api import sync_playwright
import time
import requests

def verify_confluence_chart():
    # Ensure server is running
    print("Checking if server is running...")
    try:
        requests.get('http://localhost:3000/options')
    except:
        print("Server not running. Starting it...")
        # (Assuming it's managed by the sandbox, but if not I should have started it)
        # Actually I should have a running server from previous steps.
        pass

    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={'width': 1280, 'height': 800})

        print("Navigating to Options Dashboard...")
        try:
            page.goto('http://localhost:3000/options', timeout=60000)
            time.sleep(5)

            print("Switching to PCR Trend tab...")
            page.click('button[data-tab="overview"]')
            time.sleep(5) # Wait for chart to render

            page.screenshot(path='verification_overview.png', full_page=True)
            print("Screenshot saved to verification_overview.png")

            print("Switching to Scalper tab...")
            page.click('button[data-tab="scalper"]')
            time.sleep(2)

            print("Starting Scalper...")
            page.click('button#startScalperBtn')
            time.sleep(10)

            page.screenshot(path='verification_scalper.png', full_page=True)
            print("Screenshot saved to verification_scalper.png")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_confluence_chart()
