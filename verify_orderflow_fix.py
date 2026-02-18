from playwright.sync_api import sync_playwright
import time

def test_orderflow_ui(page):
    print("Navigating to Orderflow Terminal...")
    page.goto("http://localhost:3000/orderflow")
    time.sleep(5)

    # Check if Zoom buttons are present
    is_zoom_in = page.is_visible("#zoomInBtn")
    is_zoom_out = page.is_visible("#zoomOutBtn")
    print(f"Zoom In Button: {is_zoom_in}")
    print(f"Zoom Out Button: {is_zoom_out}")

    page.screenshot(path="/home/jules/verification/orderflow_fixed.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            test_orderflow_ui(page)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()
