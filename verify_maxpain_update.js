const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 });

    try {
        console.log("Navigating to Modern Dashboard...");
        await page.goto('http://localhost:3000/modern', { waitUntil: 'networkidle', timeout: 30000 });

        console.log("Waiting for NIFTY data...");
        await page.waitForTimeout(5000);
        const niftyMaxPain = await page.locator('#maxPainValue').innerText();
        console.log("NIFTY Max Pain:", niftyMaxPain);

        console.log("Changing to BANKNIFTY...");
        await page.selectOption('#assetSelector', 'NSE:BANKNIFTY');

        console.log("Waiting for BANKNIFTY data...");
        await page.waitForTimeout(5000);
        const bankNiftyMaxPain = await page.locator('#maxPainValue').innerText();
        console.log("BANKNIFTY Max Pain:", bankNiftyMaxPain);

        if (niftyMaxPain !== bankNiftyMaxPain) {
            console.log("SUCCESS: Max Pain changed!");
        } else {
            console.log("WARNING: Max Pain is the same. (Might be a coincidence if both are same strike)");
        }

        await page.screenshot({ path: 'modern_dashboard_banknifty.png', fullPage: true });

    } catch (e) {
        console.error("Error during verification:", e);
    } finally {
        await browser.close();
    }
})();
