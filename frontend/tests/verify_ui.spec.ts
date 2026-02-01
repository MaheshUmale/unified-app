
import { test, expect } from '@playwright/test';

test('verify all ui components', async ({ page }) => {
  await page.goto('http://localhost:3000');

  // 1. Strategy Dashboard (Top)
  await expect(page.locator('text=RECOMMENDED ACTION')).toBeVisible({ timeout: 15000 });
  await page.screenshot({ path: 'verification/01_strategy_dashboard.png' });

  // 2. Execution Terminal (Middle)
  await expect(page.locator('text=EXECUTION TERMINAL')).toBeVisible();
  const terminal = page.locator('text=EXECUTION TERMINAL').locator('xpath=..');
  await terminal.screenshot({ path: 'verification/02_execution_terminal.png' });

  // 3. Market DNA (Bottom Left)
  await expect(page.locator('text=MARKET DNA')).toBeVisible();
  const dna = page.locator('text=MARKET DNA').locator('xpath=..');
  await dna.screenshot({ path: 'verification/03_market_dna.png' });

  // 4. Sentiment Convergence (Bottom Center)
  await expect(page.locator('text=SENTIMENT CONVERGENCE')).toBeVisible();
  const sentiment = page.locator('text=SENTIMENT CONVERGENCE').locator('xpath=..');
  await sentiment.screenshot({ path: 'verification/04_sentiment_convergence.png' });

  // 5. Live OI Flow (Bottom Right)
  await expect(page.locator('text=LIVE OI FLOW')).toBeVisible();
  const flow = page.locator('text=LIVE OI FLOW').locator('xpath=..');
  await flow.screenshot({ path: 'verification/05_live_oi_flow.png' });

  // 6. Full Page for layout verification
  await page.screenshot({ path: 'verification/00_full_layout.png', fullPage: true });

  console.log('UI verification screenshots captured in verification/ directory.');
});
