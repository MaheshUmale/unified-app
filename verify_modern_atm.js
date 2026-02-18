const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  await page.goto('http://localhost:3000/modern');

  // Wait for data to load
  await page.waitForTimeout(5000);

  // Take screenshot
  await page.screenshot({ path: '/home/jules/verification/modern_atm_ui.png', fullPage: true });

  // Check if strike selector is present and has options
  const strikeCount = await page.locator('#strikeSelector option').count();
  console.log('Strike selector options:', strikeCount);

  // Check if autoAtmToggle is checked
  const isAutoAtmChecked = await page.isChecked('#autoAtmToggle');
  console.log('Auto ATM checked:', isAutoAtmChecked);

  await browser.close();
})();
