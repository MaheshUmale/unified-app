from playwright.sync_api import sync_playwright
import time

def run_smoke_test(page, url, name):
    print(f"Testing {name} at {url}...")
    response = page.goto(url)
    if response.status != 200:
        print(f"{name} failed with status {response.status}")
        return False
    time.sleep(5)
    page.screenshot(path=f"/home/jules/verification/smoke_{name.lower()}.png")
    print(f"{name} loaded successfully.")
    return True

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            run_smoke_test(page, "http://localhost:3000/options", "Options")
            run_smoke_test(page, "http://localhost:3000/orderflow", "Orderflow")
        except Exception as e:
            print(f"Smoke test failed: {e}")
        finally:
            browser.close()
