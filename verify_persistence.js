
const { chromium } = require('playwright');
const path = require('path');

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();

    // 1. Load the page
    await page.goto('http://localhost:5051');
    await page.waitForTimeout(2000); // Wait for initial load

    // 2. Change layout to 2 charts
    console.log('Switching to 2-chart layout...');
    await page.click('button:has-text("2")');
    await page.waitForTimeout(1000);

    // 3. Change symbol for chart 0 to BTCUSD
    console.log('Changing Chart 0 symbol to BTCUSD...');
    await page.click('.chart-container:nth-child(1)'); // Click first chart to focus
    await page.fill('#symbol-search', 'BINANCE:BTCUSDT');
    await page.press('#symbol-search', 'Enter');
    await page.waitForTimeout(2000);

    // 4. Change interval for chart 1 to 5m
    console.log('Changing Chart 1 interval to 5m...');
    await page.click('.chart-container:nth-child(2)'); // Click second chart to focus
    await page.click('.timeframe-btn:has-text("5m")');
    await page.waitForTimeout(1000);

    // 5. Reload the page
    console.log('Reloading page...');
    await page.reload();
    await page.waitForTimeout(3000);

    // 6. Verify layout
    const chartCount = await page.locator('.chart-container').count();
    console.log(`Charts after reload: ${chartCount}`);

    // 7. Take screenshot
    await page.screenshot({ path: '/home/jules/verification/persistence_test.png', fullPage: true });

    await browser.close();
    console.log('Persistence test complete.');
})();
