from playwright.sync_api import sync_playwright, expect
import time

def test_modern_features(page):
    page.on("console", lambda msg: print(f"CONSOLE: {msg.text}"))
    page.on("pageerror", lambda exc: print(f"PAGE ERROR: {exc}"))

    print("Navigating to Modern Dashboard...")
    page.goto("http://localhost:3000/modern")

    # Wait for the synchronizing overlay to disappear or timeout
    try:
        page.wait_for_selector("#loadingOverlay:not(.active)", timeout=15000)
    except:
        print("Timeout waiting for overlay to disappear")

    # Wait for strike selector to have options
    try:
        page.wait_for_selector("#strikeSelector option", timeout=5000)
    except:
        print("Strike selector still empty")

    strikes = page.locator("#strikeSelector option")
    print(f"Strike options: {strikes.count()}")

    # Check timezone on chart (hard to check text in canvas, but we can check if charts initialized)
    is_chart_init = page.evaluate("() => !!window.prodesk.charts.price.index")
    print(f"Index Chart Initialized: {is_chart_init}")

    page.screenshot(path="/home/jules/verification/modern_final_debug.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            test_modern_features(page)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()
