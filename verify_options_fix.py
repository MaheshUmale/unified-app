from playwright.sync_api import sync_playwright
import time

def test_options_ui(page):
    print("Navigating to Options Dashboard...")
    page.goto("http://localhost:3000/options")
    time.sleep(5)

    # Check if OI Trend chart is present
    is_chart_present = page.evaluate("() => !!document.getElementById('oiTrendMergedChart')")
    print(f"OI Trend Chart Present: {is_chart_present}")

    # Check if SR levels are filtered (hard to check exact logic, but check if content exists)
    sr_count = page.locator("#supportResistance > div").count()
    print(f"SR Levels count: {sr_count}")

    page.screenshot(path="/home/jules/verification/options_fixed.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            test_options_ui(page)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()
