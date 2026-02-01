from playwright.sync_api import sync_playwright, expect

def verify_chart_render():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        # Use a large viewport to see the full dashboard
        page = browser.new_page(viewport={'width': 1920, 'height': 1080})

        try:
            # Navigate to the app
            page.goto("http://localhost:5000")

            # Wait for the main container
            expect(page.locator("main")).to_be_visible(timeout=10000)

            # Check for the Sentiment Convergence chart container
            # The chart is in a div with "Sentiment Convergence" title nearby
            chart_container = page.get_by_text("Sentiment Convergence").locator("xpath=..").locator(".glass-panel")
            expect(chart_container).to_be_visible()

            # Take a screenshot
            page.screenshot(path="frontend/verification/chart_verify.png", full_page=True)
            print("Screenshot saved to frontend/verification/chart_verify.png")

        except Exception as e:
            print(f"Error during verification: {e}")
            page.screenshot(path="frontend/verification/error.png")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_chart_render()
