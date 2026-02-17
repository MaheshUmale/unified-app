const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage();

  page.on('console', msg => console.log('BROWSER CONSOLE:', msg.text()));
  page.on('pageerror', err => {
    console.log('BROWSER PAGE ERROR:', err.message);
    process.exit(1);
  });

  try {
    console.log('Navigating to /modern...');
    await page.goto('http://localhost:3000/modern', { waitUntil: 'networkidle', timeout: 60000 });

    console.log('Checking for syntax errors (presence of main elements)...');
    const title = await page.title();
    console.log('Page title:', title);

    const header = await page.waitForSelector('header', { timeout: 10000 });
    if (header) {
        console.log('Dashboard loaded successfully, no blocking JS errors found.');
    }

    await page.screenshot({ path: 'final_verification.png', fullPage: true });
    console.log('Screenshot saved to final_verification.png');

  } catch (error) {
    console.error('Verification failed:', error);
    process.exit(1);
  } finally {
    await browser.close();
  }
})();
