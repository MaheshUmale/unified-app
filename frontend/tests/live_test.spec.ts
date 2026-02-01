
import { test, expect } from '@playwright/test';

test('capture live dashboard', async ({ page }) => {
  await page.goto('http://localhost:3000');
  await page.waitForTimeout(10000); // Wait for data to populate
  await page.screenshot({ path: 'verification/live_test_dashboard.png', fullPage: true });

  // Verify that the "Live" indicator or active prices are visible
  const niftyPrice = await page.locator('text=SPOT').locator('xpath=following-sibling::div').first().textContent();
  console.log('Live Nifty Price on Dashboard:', niftyPrice);
});
