from playwright.sync_api import sync_playwright
import time
import os

def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 800})

        try:
            page.goto('http://localhost:3000/options')
            time.sleep(5) # Wait for load

            # Switch to Scalper tab
            page.click('button[data-tab="scalper"]')
            time.sleep(2)

            # Take screenshot of the whole page to see state
            page.screenshot(path='verification_final.png')
            print("Final verification screenshot saved.")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    run()
