const { chromium } = require('playwright');

(async () => {
    const browser = await chromium.launch();
    const page = await browser.newPage();
    await page.setViewportSize({ width: 1920, height: 1080 });

    try {
        console.log("Navigating to Modern Dashboard...");
        await page.goto('http://localhost:3000/modern', { waitUntil: 'networkidle', timeout: 30000 });

        console.log("Waiting for data to load...");
        await page.waitForTimeout(5000); // Wait for some data to populate

        await page.screenshot({ path: 'modern_dashboard_v2.png', fullPage: true });
        console.log("Screenshot saved as modern_dashboard_v2.png");

        // Verify components are gone
        const heatmap = await page.$('#heatmapCanvas');
        const buyBtn = await page.$('#buyCallBtn');
        const raidScoreboard = await page.getByText('Active Raid Scoreboard');

        if (!heatmap) console.log("SUCCESS: Liquidity Heatmap is gone.");
        else console.log("FAILURE: Liquidity Heatmap STILL EXISTS.");

        if (!buyBtn) console.log("SUCCESS: Fast Order Execution is gone.");
        else console.log("FAILURE: Fast Order Execution STILL EXISTS.");

        const count = await raidScoreboard.count();
        if (count === 0) console.log("SUCCESS: Active Raid Scoreboard is gone.");
        else console.log("FAILURE: Active Raid Scoreboard STILL EXISTS.");

        // Check Max Pain
        const maxPain = await page.locator('#maxPainValue').innerText();
        console.log("Current Max Pain:", maxPain);

    } catch (e) {
        console.error("Error during verification:", e);
    } finally {
        await browser.close();
    }
})();
