
import { test, expect } from '@playwright/test';

test('verify unified dashboard', async ({ page }) => {
  await page.goto('http://localhost:5000');
  await page.waitForTimeout(5000); // Wait for initial render
  await page.screenshot({ path: 'verification/debug_final.png', fullPage: true });

  await expect(page.locator('text=RECOMMENDED ACTION')).toBeVisible({ timeout: 15000 });
});
