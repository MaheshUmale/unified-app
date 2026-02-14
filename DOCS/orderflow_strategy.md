# Order Flow Strategy Summary
**Video:** [The ONLY Orderflow Guide You'll EVER NEED](https://www.youtube.com/watch?v=ljk9BovCSqI) by TradingLab

## Key Components

### 1. Volume Footprint
- **Displays:** Sell (Bid) on the left, Buy (Ask) on the right at specific price levels.
- **Diagonal Imbalances:** A "Buy Imbalance" occurs when the Buy Volume at a price level is **3x (300%)** greater than the Sell Volume at the price level directly below it.
- **Value Area:** The zone where **70%** of the candle's total volume occurred.
- **Point of Control (POC):** The price level within a candle that has the highest total volume.

### 2. Cumulative Volume Delta (CVD)
- **Calculation:** Running total of (Buy Volume - Sell Volume).
- **CVD Divergence:**
    - **Bullish:** Price makes a lower low, but CVD makes a higher low (indicates absorption of selling pressure).
    - **Bearish:** Price makes a higher high, but CVD makes a lower high.

### 3. Absorption-Initiation Pattern (AIP)
- **Step 1: Absorption Candle:**
    - Typically occurs in a Demand Zone.
    - Shows **Sell Imbalances** (aggressive selling), yet the candle **closes ABOVE** those imbalances. This proves buyers absorbed the selling pressure.
- **Step 2: Initiation Candle:**
    - The following candle prints **Buy Imbalances** (aggressive buying).
    - The candle **closes ABOVE** these imbalances, confirming the move has started.

## Visual Indicators to Implement
- [x] Bid/Ask Volume Footprint
- [x] Diagonal Imbalance Detection (300%)
- [x] POC Highlighting
- [x] CVD Area Chart
- [ ] Value Area (VAH/VAL) Visualization
- [ ] Imbalance Highlighting (Colored Rectangles)
- [ ] AIP Signal Detection (Absorption -> Initiation sequence)
- [ ] CVD Divergence Markers (Bullish/Bearish)
