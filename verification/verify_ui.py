from playwright.sync_api import sync_playwright, expect

def verify_ui():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            # 1. Go to the app
            page.goto("http://localhost:3000")
            page.wait_for_load_state("networkidle")

            # 2. Check for key UI elements
            expect(page.locator("#symbolSearch")).to_be_visible()
            # It has 5 buttons: 1m, 5m, 15m, 1h, 1d
            expect(page.locator(".tf-btn")).to_have_count(5)
            expect(page.locator("#mainChart")).to_be_visible()

            # 3. Take a screenshot
            page.screenshot(path="/home/jules/verification/terminal_view.png", full_page=True)
            print("Screenshot saved to /home/jules/verification/terminal_view.png")

        except Exception as e:
            print(f"Verification failed: {e}")
            page.screenshot(path="/home/jules/verification/failed.png")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_ui()
