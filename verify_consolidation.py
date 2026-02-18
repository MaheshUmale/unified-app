from playwright.sync_api import sync_playwright
import time

def test_consolidation(page):
    print("Testing Options Dashboard...")
    page.goto("http://localhost:3000/options")
    time.sleep(5)

    # Check if PCR Gauge is present
    is_gauge_present = page.evaluate("() => !!document.getElementById('pcrGauge')")
    print(f"PCR Gauge Present: {is_gauge_present}")

    # Check if OI Divergence chart is present
    is_div_present = page.evaluate("() => !!document.getElementById('oiPriceDivergenceChart')")
    print(f"OI Divergence Chart Present: {is_div_present}")

    # Check if Net Delta/IV Rank cards are GONE
    is_delta_present = page.evaluate("() => !!document.getElementById('netDelta')")
    print(f"Net Delta Card Present: {is_delta_present}")

    page.screenshot(path="/home/jules/verification/options_consolidated.png")

    print("Testing Orderflow Terminal...")
    page.goto("http://localhost:3000/orderflow")
    time.sleep(5)

    # Check if sidebar elements are GONE
    is_sentiment_present = page.evaluate("() => !!document.getElementById('sentiment-value')")
    print(f"Sentiment Sidebar Present: {is_sentiment_present}")

    page.screenshot(path="/home/jules/verification/orderflow_consolidated.png")

if __name__ == "__main__":
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            test_consolidation(page)
        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()
