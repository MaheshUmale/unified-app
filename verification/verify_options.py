from playwright.sync_api import sync_playwright
import time

def verify_options():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            print("Navigating to http://localhost:3000/options...")
            page.goto("http://localhost:3000/options", timeout=60000, wait_until="domcontentloaded")
            print("Title:", page.title())
            time.sleep(10)
            page.screenshot(path="verification/options_screenshot.png")
            print("Screenshot taken.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_options()
