from playwright.sync_api import sync_playwright
import time

def verify_orderflow_params():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Test URL with specific parameters
        target_url = "http://localhost:3000/orderflow?symbol=NSE:NIFTY260224P25700&ticks=50&step=1"
        page.goto(target_url)
        time.sleep(2)

        # Verify symbol display
        symbol_text = page.locator("#display-symbol").inner_text()
        print(f"Displayed Symbol: {symbol_text}")

        # Verify TPC input
        tpc_val = page.locator("#ticks-input").input_value()
        print(f"TPC Input Value: {tpc_val}")

        # Verify Step input
        step_val = page.locator("#step-input").input_value()
        print(f"Step Input Value: {step_val}")

        page.screenshot(path="verification_orderflow_params.png")

        browser.close()

if __name__ == "__main__":
    verify_orderflow_params()
