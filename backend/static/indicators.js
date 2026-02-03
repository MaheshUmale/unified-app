/**
 * PRODESK Trading Indicators
 * Translation of Pine Script v6 strategy to Javascript for ECharts integration.
 */

const Indicators = {
    sma: (data, period) => {
        const res = new Array(data.length).fill(null);
        let sum = 0;
        let count = 0;
        for (let i = 0; i < data.length; i++) {
            const val = data[i];
            if (val !== null && val !== undefined && !isNaN(val)) {
                sum += val;
                count++;
            }
            if (i >= period) {
                const oldVal = data[i - period];
                if (oldVal !== null && oldVal !== undefined && !isNaN(oldVal)) {
                    sum -= oldVal;
                    count--;
                }
                res[i] = count > 0 ? sum / count : null;
            } else {
                res[i] = count > 0 ? sum / count : null;
            }
        }
        return res;
    },

    stdev: (data, period) => {
        const res = new Array(data.length).fill(null);
        const sma = Indicators.sma(data, period);
        for (let i = period - 1; i < data.length; i++) {
            let sumSq = 0;
            for (let j = 0; j < period; j++) {
                sumSq += Math.pow(data[i - j] - sma[i], 2);
            }
            res[i] = Math.sqrt(sumSq / period);
        }
        return res;
    },

    ema: (data, period) => {
        const res = new Array(data.length).fill(null);
        const k = 2 / (period + 1);
        let prevEma = data[0];
        res[0] = prevEma;
        for (let i = 1; i < data.length; i++) {
            res[i] = data[i] * k + prevEma * (1 - k);
            prevEma = res[i];
        }
        return res;
    },

    dema: (data, period) => {
        const ema1 = Indicators.ema(data, period);
        const ema2 = Indicators.ema(ema1.filter(v => v !== null), period);
        const res = new Array(data.length).fill(null);
        let ema2Idx = 0;
        for (let i = 0; i < data.length; i++) {
            if (ema1[i] !== null && ema2[ema2Idx] !== undefined) {
                res[i] = 2 * ema1[i] - ema2[ema2Idx];
                ema2Idx++;
            }
        }
        return res;
    },

    evwma: (prices, volumes, length) => {
        const res = new Array(prices.length).fill(null);
        let sumVol = 0;
        const volWindow = [];

        let prevEvwma = prices[0];
        res[0] = prevEvwma;

        for (let i = 1; i < prices.length; i++) {
            volWindow.push(volumes[i]);
            sumVol += volumes[i];
            if (volWindow.length > length) {
                sumVol -= volWindow.shift();
            }

            if (sumVol === 0) {
                res[i] = prevEvwma;
            } else {
                res[i] = (prevEvwma * (sumVol - volumes[i]) + volumes[i] * prices[i]) / sumVol;
            }
            prevEvwma = res[i];
        }
        return res;
    },

    dynamicPivot: (data, forceLen, pivotLen) => {
        // data = array of {open, high, low, close, volume, vwap}
        const res = new Array(data.length).fill(null);
        const pC = data.map(d => d.close - d.open);
        const absPC = pC.map(v => Math.abs(v));

        // mB = highest(absPC, forceLen)
        const mB = new Array(data.length).fill(0);
        for(let i=forceLen-1; i<data.length; i++) {
            let max = 0;
            for(let j=0; j<forceLen; j++) max = Math.max(max, absPC[i-j]);
            mB[i] = max;
        }

        const sc = data.map((d, i) => Math.abs(d.close - d.open) / (mB[i] === 0 ? 1 : mB[i]));
        const uF = data.map((d, i) => (d.close - d.open) > 0 ? d.volume * sc[i] * (d.close > d.vwap ? 1.5 : 1.0) : 0);
        const dF = data.map((d, i) => (d.close - d.open) < 0 ? d.volume * sc[i] * (d.close < d.vwap ? 1.5 : 1.0) : 0);

        const sU = Indicators.sma(uF, forceLen);
        const sD = Indicators.sma(dF, forceLen);
        const netF = sU.map((u, i) => (u || 0) - (sD[i] || 0));

        const baseP = Indicators.sma(data.map((d, i) => pC[i] > 0 ? d.high : d.low), pivotLen);

        const diffClose = new Array(data.length).fill(0);
        for(let i=1; i<data.length; i++) diffClose[i] = Math.abs(data[i].close - data[i-1].close);
        const fS = Indicators.sma(diffClose.map((v, i) => v / (data[i].close || 1)), pivotLen);

        const hN = new Array(data.length).fill(0);
        for(let i=pivotLen-1; i<data.length; i++) {
            let max = 0;
            for(let j=0; j<pivotLen; j++) max = Math.max(max, Math.abs(netF[i-j]));
            hN[i] = max;
        }

        const fA = netF.map((nf, i) => nf / (hN[i] === 0 ? 1 : hN[i]));

        for(let i=0; i<data.length; i++) {
            if (baseP[i] !== null) {
                res[i] = baseP[i] + (fA[i] * data[i].close * (fS[i] || 0));
            }
        }
        return res;
    },

    swingDetection: (highs, lows, left, right) => {
        // Returns { highs: [], lows: [], isAbove: [], isBelow: [] }
        const sh = new Array(highs.length).fill(null);
        const sl = new Array(lows.length).fill(null);

        for (let i = left; i < highs.length - right; i++) {
            let isHigh = true;
            let isLow = true;
            for (let j = 1; j <= left; j++) {
                if (highs[i] <= highs[i - j]) isHigh = false;
                if (lows[i] >= lows[i - j]) isLow = false;
            }
            for (let j = 1; j <= right; j++) {
                if (highs[i] < highs[i + j]) isHigh = false;
                if (lows[i] > lows[i + j]) isLow = false;
            }
            if (isHigh) sh[i + right] = highs[i];
            if (isLow) sl[i + right] = lows[i];
        }

        const lastSH = new Array(highs.length).fill(null);
        const lastSL = new Array(lows.length).fill(null);
        let currSH = null, currSL = null;

        for (let i = 0; i < highs.length; i++) {
            if (sh[i] !== null) currSH = sh[i];
            if (sl[i] !== null) currSL = sl[i];
            lastSH[i] = currSH;
            lastSL[i] = currSL;
        }

        return { lastSH, lastSL };
    },

    /**
     * Requirement #2: Candle coloring based on RVOL
     */
    getBarColor: (open, close, volume, avgVol) => {
        const rvol = volume / (avgVol || 1);
        const isUp = close >= open;

        // RVOL Breakout Color (Yellow)
        if (rvol >= 2.5) return '#fbbf24';

        if (isUp) {
            if (rvol >= 1.5) return '#22c55e'; // Vibrant Up
            if (rvol >= 0.8) return '#16a34a'; // Normal Up
            return '#14532d'; // Low Vol Up
        } else {
            if (rvol >= 1.5) return '#ef4444'; // Vibrant Down
            if (rvol >= 0.8) return '#dc2626'; // Normal Down
            return '#7f1d1d'; // Low Vol Down
        }
    },

    getBubbleData: (data, period, size, delta) => {
        const volumes = data.map(d => d.volume);
        const smaVolLong = Indicators.sma(volumes, period);
        const smaVolShort = Indicators.sma(volumes, 10);
        const demaVol = Indicators.dema(volumes, 3);

        const bubbles = [];
        for (let i = 0; i < data.length; i++) {
            const avgV = (smaVolLong[i] + smaVolShort[i]) / 2;
            if (!avgV) continue;

            const bSize = Math.max(volumes[i] / avgV, demaVol[i] / avgV);

            if (bSize > size) {
                let sizeIdx = 1;
                if (bSize > size + 8 * delta) sizeIdx = 5;
                else if (bSize > size + 4 * delta) sizeIdx = 4;
                else if (bSize > size + 2 * delta) sizeIdx = 3;
                else if (bSize > size + delta) sizeIdx = 2;

                bubbles.push({
                    index: i,
                    size: sizeIdx,
                    value: data[i].close,
                    isUp: data[i].close > data[i].open
                });
            }
        }
        return bubbles;
    },

    getMTFData: (data, stdDevPeriod = 48, stdMultiplier = 4) => {
        const n = data.length;
        const supp = new Array(n).fill(null);
        const rest = new Array(n).fill(null);
        const lines = [];

        if (n < stdDevPeriod) return { supp, rest, lines };

        const volumes = data.map(d => d.volume);
        const stdDev = Indicators.stdev(volumes, stdDevPeriod);
        const avgV = Indicators.sma(volumes, stdDevPeriod);

        let lastSupp = null, lastRest = null;

        for (let i = stdDevPeriod; i < n; i++) {
            const sumV2 = volumes[i] + volumes[i-1];
            const cond = (sumV2/2 - avgV[i]) > stdMultiplier * stdDev[i] || (volumes[i] - avgV[i]) > stdMultiplier * stdDev[i];

            if (cond) {
                if (data[i].close > data[i - stdMultiplier]?.open) {
                    lastSupp = data[i].low;
                } else if (data[i].close < data[i - stdMultiplier]?.open) {
                    lastRest = data[i].high;
                }

                // Horizontal lines logic (ProcessLines)
                const v_avg = (avgV[i] + Indicators.sma(volumes, 10)[i]) / 2;
                const v_norm = volumes[i] / (v_avg || 1);
                const step = (v_norm - 2.5) / 0.75;
                if (step >= 4) {
                    lines.push({
                        price: (data[i].high + data[i].low + data[i].close + data[i].open) / 4,
                        index: i,
                        step: step,
                        isUp: data[i].close > data[i].open
                    });
                }
            }
            supp[i] = lastSupp;
            rest[i] = lastRest;
        }
        return { supp, rest, lines: lines.slice(-20) }; // Just show most recent 20
    }
};
