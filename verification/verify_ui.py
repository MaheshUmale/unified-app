from playwright.sync_api import sync_playwright
import time

def verify_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.on("console", lambda msg: print(f"CONSOLE: {msg.type}: {msg.text}"))
        try:
            print("Navigating...")
            # Use a huge timeout
            page.goto("http://localhost:3000/", timeout=120000, wait_until="domcontentloaded")
            print("DOM loaded.")
            time.sleep(10)
            page.screenshot(path="verification/ui_screenshot.png")
            print("Screenshot taken.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_ui()
