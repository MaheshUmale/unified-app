const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();
  const baseUrl = 'http://localhost:3000';

  const routes = [
    { name: 'main_index', path: '/' },
    { name: 'options_dashboard', path: '/options' },
    { name: 'tick_chart', path: '/tick' },
    { name: 'renko_chart', path: '/renko' },
    { name: 'db_viewer', path: '/db-viewer' },
    { name: 'modern_dashboard', path: '/modern' }
  ];

  for (const route of routes) {
    console.log(`Capturing ${route.name} at ${route.path}...`);
    try {
      await page.goto(`${baseUrl}${route.path}`, { waitUntil: 'networkidle', timeout: 30000 });
      await page.waitForTimeout(5000); // Wait for data population
      await page.screenshot({ path: `screenshot_${route.name}.png`, fullPage: true });
    } catch (e) {
      console.error(`Failed to capture ${route.name}: ${e.message}`);
    }
  }

  await browser.close();
  console.log('All captures complete.');
})();
