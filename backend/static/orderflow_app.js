/**
 * PRODESK Advanced Order Flow Terminal
 * Implementing Volume Footprint, CVD Divergence, and AIP Strategy.
 */

const socket = io();
let currentSymbol = 'NSE:NIFTY';
let charts = {};
let aggregator;
let aggregatedCandles = [];
let historicalTicks = [];
let cachedMarkers = [];
let renderRequested = false;
let lastSignalUpdate = 0;

const COLORS = {
    bull: '#00ffc2',
    bear: '#ff3366',
    bullTransparent: 'rgba(0, 255, 194, 0.2)',
    bearTransparent: 'rgba(255, 51, 102, 0.2)',
    poc: '#fbbf24',
    va: 'rgba(255, 255, 255, 0.1)',
    text: '#e6edf3',
    muted: '#7d8590'
};

document.addEventListener('DOMContentLoaded', () => {
    const urlParams = new URLSearchParams(window.location.search);
    currentSymbol = (urlParams.get('symbol') || 'NSE:NIFTY').toUpperCase();
    document.getElementById('display-symbol').textContent = currentSymbol;

    const ticksInput = document.getElementById('ticks-input');
    ticksInput.value = urlParams.get('ticks') || 100;
    aggregator.tpc = parseInt(ticksInput.value);

    initCharts();
    setupSocket();
    loadHistory();
    loadSentiment();
    setupUIListeners();
});

function setupUIListeners() {
    document.getElementById('ticks-input').addEventListener('change', (e) => {
        const tpc = parseInt(e.target.value) || 100;
        aggregator.setTicksPerCandle(tpc);
        loadHistory();
    });

    document.getElementById('replay-btn').addEventListener('click', () => {
        const tpc = document.getElementById('ticks-input').value;
        window.location.href = `/tick?symbol=${currentSymbol}&ticks=${tpc}`;
    });

    // Auto-resize charts
    const resizeObserver = new ResizeObserver(() => {
        if (charts.main) {
            const mainEl = document.getElementById('main-chart');
            charts.main.applyOptions({ width: mainEl.clientWidth, height: mainEl.clientHeight });
        }
        if (charts.cvd) {
            const cvdEl = document.getElementById('cvd-chart');
            charts.cvd.applyOptions({ width: cvdEl.clientWidth, height: cvdEl.clientHeight });
        }
        const canvas = document.getElementById('footprint-canvas');
        if (canvas) {
            const wrapper = document.getElementById('chart-wrapper');
            canvas.width = wrapper.clientWidth;
            canvas.height = wrapper.clientHeight;
            renderFootprint(canvas, canvas.getContext('2d'));
        }
    });
    resizeObserver.observe(document.getElementById('chart-wrapper'));
    resizeObserver.observe(document.getElementById('cvd-chart'));
}

class TickAggregator {
    constructor(tpc) {
        this.tpc = tpc;
        this.currentTickCount = 0;
        this.currentCandle = null;
        this.lastTime = 0;
        this.lastPrice = 0;
        this.lastSide = 1;
        this.cvd = 0;
    }

    setTicksPerCandle(tpc) {
        this.tpc = tpc;
        this.currentTickCount = 0;
        this.currentCandle = null;
    }

    processTick(tick, deferAnalytics = false) {
        // Round price to 0.05 step and fix to 2 decimals to avoid floating point noise in object keys
        const price = Number((Math.round(Number(tick.price) / 0.05) * 0.05).toFixed(2));
        const qty = Number(tick.qty || 0);
        let ts = Math.floor(tick.ts_ms / 1000);

        let side = this.lastSide;
        if (price > this.lastPrice) side = 1;
        else if (price < this.lastPrice) side = -1;

        const delta = side * qty;
        this.cvd += delta;
        this.lastPrice = price;
        this.lastSide = side;

        if (!this.currentCandle || this.currentTickCount >= this.tpc) {
            // Finalize previous candle
            if (this.currentCandle) {
                this.calculateAnalytics(this.currentCandle);
            }

            if (ts <= this.lastTime) ts = this.lastTime + 1;
            this.lastTime = ts;

            this.currentCandle = {
                time: ts,
                open: price, high: price, low: price, close: price,
                volume: qty, delta: delta, cvd: this.cvd,
                footprint: {}
            };
            this.updateFootprint(this.currentCandle, price, side, qty, deferAnalytics);
            this.currentTickCount = 1;
            return { type: 'new', candle: this.currentCandle };
        } else {
            this.currentCandle.high = Math.max(this.currentCandle.high, price);
            this.currentCandle.low = Math.min(this.currentCandle.low, price);
            this.currentCandle.close = price;
            this.currentCandle.volume += qty;
            this.currentCandle.delta += delta;
            this.currentCandle.cvd = this.cvd;
            this.updateFootprint(this.currentCandle, price, side, qty, deferAnalytics);
            this.currentTickCount++;
            return { type: 'update', candle: this.currentCandle };
        }
    }

    updateFootprint(candle, price, side, qty, deferAnalytics = false) {
        if (!candle.footprint[price]) {
            candle.footprint[price] = { buy: 0, sell: 0 };
        }
        if (side === 1) candle.footprint[price].buy += qty;
        else candle.footprint[price].sell += qty;

        if (deferAnalytics) return;

        // Throttle calculation to avoid doing it on every micro-tick
        const now = Date.now();
        if (!candle._lastCalc || now - candle._lastCalc > 200) {
            this.calculateAnalytics(candle);
            candle._lastCalc = now;
        }
    }

    calculateAnalytics(candle) {
        const priceLevels = Object.keys(candle.footprint).map(Number).sort((a,b) => a-b);
        if (priceLevels.length === 0) return;

        let maxVol = 0;
        let totalVol = 0;
        let poc = priceLevels[0];
        for (let p of priceLevels) {
            let vol = candle.footprint[p].buy + candle.footprint[p].sell;
            totalVol += vol;
            if (vol > maxVol) {
                maxVol = vol;
                poc = p;
            }
        }
        candle.poc = poc;

        let vaVol = totalVol * 0.7;
        let currentVaVol = maxVol;
        let lowerIdx = priceLevels.indexOf(poc);
        let upperIdx = lowerIdx;

        while (currentVaVol < vaVol && (lowerIdx > 0 || upperIdx < priceLevels.length - 1)) {
            let lVol = lowerIdx > 0 ? (candle.footprint[priceLevels[lowerIdx - 1]].buy + candle.footprint[priceLevels[lowerIdx - 1]].sell) : 0;
            let uVol = upperIdx < priceLevels.length - 1 ? (candle.footprint[priceLevels[upperIdx + 1]].buy + candle.footprint[priceLevels[upperIdx + 1]].sell) : 0;
            if (lVol >= uVol) { currentVaVol += lVol; lowerIdx--; }
            else { currentVaVol += uVol; upperIdx++; }
        }
        candle.vah = priceLevels[upperIdx];
        candle.val = priceLevels[lowerIdx];

        candle.imbalances = [];
        for (let i = 0; i < priceLevels.length; i++) {
            const p = priceLevels[i];
            const buyV = candle.footprint[p].buy;
            const sellV = candle.footprint[p].sell;
            if (i > 0) {
                const prevSellV = candle.footprint[priceLevels[i-1]].sell;
                if (buyV >= prevSellV * 3 && buyV > 0 && prevSellV > 0) candle.imbalances.push({ price: p, side: 'buy' });
            }
            if (i < priceLevels.length - 1) {
                const nextBuyV = candle.footprint[priceLevels[i+1]].buy;
                if (sellV >= nextBuyV * 3 && sellV > 0 && nextBuyV > 0) candle.imbalances.push({ price: p, side: 'sell' });
            }
        }
    }
}

aggregator = new TickAggregator(100);

function initCharts() {
    const mainEl = document.getElementById('main-chart');
    charts.main = LightweightCharts.createChart(mainEl, {
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: COLORS.muted },
        grid: { vertLines: { color: 'rgba(255,255,255,0.03)' }, horzLines: { color: 'rgba(255,255,255,0.03)' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true, secondsVisible: true },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' }
    });

    charts.candles = charts.main.addCandlestickSeries({
        upColor: COLORS.bull, downColor: COLORS.bear, borderVisible: false, wickUpColor: COLORS.bull, wickDownColor: COLORS.bear
    });

    const cvdEl = document.getElementById('cvd-chart');
    charts.cvd = LightweightCharts.createChart(cvdEl, {
        layout: { background: { type: 'solid', color: 'transparent' }, textColor: COLORS.muted },
        grid: { vertLines: { color: 'rgba(255,255,255,0.03)' }, horzLines: { color: 'rgba(255,255,255,0.03)' } },
        timeScale: { visible: false },
        rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' }
    });

    charts.cvdSeries = charts.cvd.addAreaSeries({
        lineColor: '#3b82f6', topColor: 'rgba(59, 130, 246, 0.3)', bottomColor: 'transparent', lineWidth: 2
    });

    // Sync CVD with Main
    charts.main.timeScale().subscribeVisibleLogicalRangeChange(range => {
        charts.cvd.timeScale().setVisibleLogicalRange(range);
    });

    initFootprintCanvas();

    // Toggle candle transparency based on zoom
    charts.main.timeScale().subscribeVisibleLogicalRangeChange(() => {
        const spacing = charts.main.timeScale().options().barSpacing;
        if (spacing > 50) {
            charts.candles.applyOptions({
                upColor: 'rgba(0, 255, 194, 0.05)',
                downColor: 'rgba(255, 51, 102, 0.05)',
                wickUpColor: 'rgba(0, 255, 194, 0.2)',
                wickDownColor: 'rgba(255, 51, 102, 0.2)',
            });
        } else {
            charts.candles.applyOptions({
                upColor: COLORS.bull,
                downColor: COLORS.bear,
                wickUpColor: COLORS.bull,
                wickDownColor: COLORS.bear,
            });
        }
    });
}

function initFootprintCanvas() {
    const canvas = document.getElementById('footprint-canvas');
    const ctx = canvas.getContext('2d');
    const resize = () => {
        const wrapper = document.getElementById('chart-wrapper');
        canvas.width = wrapper.clientWidth;
        canvas.height = wrapper.clientHeight;
    };
    window.addEventListener('resize', resize);
    resize();
    charts.main.timeScale().subscribeVisibleLogicalRangeChange(() => renderFootprint(canvas, ctx));
}

function renderFootprint(canvas, ctx) {
    if (!ctx || !charts.main || aggregatedCandles.length === 0) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);

    const timeScale = charts.main.timeScale();
    const barSpacing = timeScale.options().barSpacing;
    if (barSpacing < 50) return; // Only show footprint when zoomed in

    const logicalRange = timeScale.getVisibleLogicalRange();
    if (!logicalRange) return;

    // Use binary search to find visible candles efficiently
    const findIndex = (time) => {
        let low = 0, high = aggregatedCandles.length - 1;
        while (low <= high) {
            let mid = (low + high) >> 1;
            if (aggregatedCandles[mid].time < time) low = mid + 1;
            else high = mid - 1;
        }
        return low;
    };

    // Expand range slightly to handle half-visible candles
    const startTime = timeScale.coordinateToTime(0);
    const endTime = timeScale.coordinateToTime(canvas.width);

    if (!startTime || !endTime) return;

    const startIdx = Math.max(0, findIndex(startTime) - 1);
    const endIdx = Math.min(aggregatedCandles.length - 1, findIndex(endTime) + 1);

    for (let i = startIdx; i <= endIdx; i++) {
        const candle = aggregatedCandles[i];
        const x = timeScale.timeToCoordinate(candle.time);
        if (x === null || x < -barSpacing || x > canvas.width + barSpacing) continue;

        const footprint = candle.footprint || {};
        const priceLevels = Object.keys(footprint).map(Number).sort((a,b) => b-a);
        const halfWidth = (barSpacing / 2) * 0.9;

        // Draw Value Area Box
        if (candle.vah && candle.val) {
            const vahY = charts.candles.priceToCoordinate(candle.vah);
            const valY = charts.candles.priceToCoordinate(candle.val);
            if (vahY !== null && valY !== null) {
                ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
                ctx.setLineDash([2, 2]);
                ctx.strokeRect(x - halfWidth - 2, vahY - 6, halfWidth * 2 + 4, valY - vahY + 12);
                ctx.setLineDash([]);
            }
        }

        // Calculate Max Delta in this candle for Heatmap scaling
        let maxCandleDelta = 1;
        priceLevels.forEach(p => {
            const d = Math.abs(footprint[p].buy - footprint[p].sell);
            if (d > maxCandleDelta) maxCandleDelta = d;
        });

        priceLevels.forEach(p => {
            const y = charts.candles.priceToCoordinate(p);
            if (y === null || y < 0 || y > canvas.height) return;

            const data = footprint[p];
            const buy = data.buy;
            const sell = data.sell;
            const delta = buy - sell;

            // Heatmap Effect: Opacity based on delta intensity
            const intensity = Math.min(Math.abs(delta) / maxCandleDelta, 1.0);

            // Imbalance Detection
            const isBuyImbalance = candle.imbalances.some(imb => imb.price === p && imb.side === 'buy');
            const isSellImbalance = candle.imbalances.some(imb => imb.price === p && imb.side === 'sell');

            // Cell Background
            if (isBuyImbalance) {
                ctx.fillStyle = `rgba(0, 255, 194, ${0.1 + intensity * 0.4})`;
                ctx.fillRect(x, y - 6, halfWidth, 12);
            } else if (isSellImbalance) {
                ctx.fillStyle = `rgba(255, 51, 102, ${0.1 + intensity * 0.4})`;
                ctx.fillRect(x - halfWidth, y - 6, halfWidth, 12);
            } else {
                // Normal background
                const isVA = p >= candle.val && p <= candle.vah;
                ctx.fillStyle = isVA ? `rgba(255,255,255,${0.05 + intensity * 0.1})` : `rgba(255,255,255,0.02)`;
                ctx.fillRect(x - halfWidth, y - 6, halfWidth * 2, 12);
            }

            // POC Highlight
            if (p === candle.poc) {
                ctx.strokeStyle = COLORS.poc;
                ctx.lineWidth = 1.5;
                ctx.strokeRect(x - halfWidth, y - 6, halfWidth * 2, 12);
                ctx.lineWidth = 1;
            }

            // Draw Numbers
            ctx.font = 'bold 8px "IBM Plex Mono"';

            // Sell Volume (Left)
            ctx.textAlign = 'right';
            ctx.fillStyle = isSellImbalance ? COLORS.bear : (delta < 0 ? '#ff99aa' : COLORS.muted);
            ctx.fillText(sell, x - 4, y + 3);

            // Buy Volume (Right)
            ctx.textAlign = 'left';
            ctx.fillStyle = isBuyImbalance ? COLORS.bull : (delta > 0 ? '#99ffdd' : COLORS.muted);
            ctx.fillText(buy, x + 4, y + 3);

            // Center Separator
            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.beginPath();
            ctx.moveTo(x, y - 4);
            ctx.lineTo(x, y + 4);
            ctx.stroke();
        });
    }
}

function setupSocket() {
    socket.on('connect', () => {
        console.log("Connected to OrderFlow Stream");
        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
        updateStatus('Connected', 'bg-[#00ffc2]');
    });

    socket.on('raw_tick', (data) => {
        if (data[currentSymbol]) {
            processNewTick(data[currentSymbol]);
        }
    });
}

function updateStatus(text, colorClass) {
    const dot = document.getElementById('status-dot');
    const label = document.getElementById('status-text');
    label.textContent = text;
    dot.className = `w-2 h-2 rounded-full ${colorClass}`;
}

function processNewTick(tick) {
    const result = aggregator.processTick({
        price: tick.last_price,
        qty: tick.ltq,
        ts_ms: tick.ts_ms
    });

    charts.candles.update(result.candle);
    charts.cvdSeries.update({ time: result.candle.time, value: result.candle.cvd });

    if (result.type === 'new') {
        // When a new candle is formed, move markers for the COMPLETED candle to cache
        if (aggregatedCandles.length > 0) {
            updateMarkersForCandle(aggregatedCandles.length - 1);
        }
        aggregatedCandles.push({ ...result.candle });
    } else {
        aggregatedCandles[aggregatedCandles.length - 1] = { ...result.candle };
    }

    // Throttle signal updates to 2 times per second
    const now = Date.now();
    if (now - lastSignalUpdate > 500) {
        updateSignals();
        lastSignalUpdate = now;
    }

    // Use requestAnimationFrame for rendering
    requestRender();
    updatePriceUI(result.candle);
}

function requestRender() {
    if (renderRequested) return;
    renderRequested = true;
    requestAnimationFrame(() => {
        const canvas = document.getElementById('footprint-canvas');
        if (canvas) renderFootprint(canvas, canvas.getContext('2d'));
        renderRequested = false;
    });
}

function updatePriceUI(candle) {
    document.getElementById('last-price').textContent = candle.close.toLocaleString(undefined, { minimumFractionDigits: 2 });
    const deltaSummary = document.getElementById('delta-summary');
    deltaSummary.textContent = `DELTA: ${Math.round(candle.delta)} | CVD: ${Math.round(candle.cvd)}`;
    deltaSummary.className = `text-[11px] font-bold mt-1 ${candle.delta >= 0 ? 'text-[#00ffc2]' : 'text-[#ff3366]'}`;
}

function updateMarkersForCandle(i) {
    if (i < 1 || i >= aggregatedCandles.length) return;

    // Remove existing markers for this time to avoid duplicates
    const time = aggregatedCandles[i].time;
    cachedMarkers = cachedMarkers.filter(m => m.time !== time);

    const candles = aggregatedCandles;
    const c = candles[i];
    const p = candles[i-1];
    const buyImbs = (c.imbalances || []).filter(imb => imb.side === 'buy');
    const sellImbs = (c.imbalances || []).filter(imb => imb.side === 'sell');

    if (buyImbs.length >= 3) {
        cachedMarkers.push({ time: c.time, position: 'belowBar', color: COLORS.bull, shape: 'arrowUp', text: 'STACKED BUY' });
    } else if (sellImbs.length >= 3) {
        cachedMarkers.push({ time: c.time, position: 'aboveBar', color: COLORS.bear, shape: 'arrowDown', text: 'STACKED SELL' });
    }

    if (c.low < p.low && c.cvd > p.cvd) {
        cachedMarkers.push({ time: c.time, position: 'belowBar', color: '#3b82f6', shape: 'circle', text: 'BULL DIV' });
    } else if (c.high > p.high && c.cvd < p.cvd) {
        cachedMarkers.push({ time: c.time, position: 'aboveBar', color: '#3b82f6', shape: 'circle', text: 'BEAR DIV' });
    }

    const isAbsorption = sellImbs.length > 0 && c.close > Math.max(...sellImbs.map(imb => imb.price));
    if (isAbsorption) {
        cachedMarkers.push({ time: c.time, position: 'belowBar', color: COLORS.poc, shape: 'circle', text: 'ABSORPTION' });
    }

    // AIP Entry check (if previous was absorption and this is initiation)
    const prevSellImbs = (p.imbalances || []).filter(imb => imb.side === 'sell');
    const wasPrevAbs = prevSellImbs.length > 0 && p.close > Math.max(...prevSellImbs.map(imb => imb.price));
    const isInitiation = buyImbs.length > 0 && c.close > Math.max(...buyImbs.map(imb => imb.price));
    if (wasPrevAbs && isInitiation) {
        cachedMarkers.push({ time: c.time, position: 'belowBar', color: COLORS.bull, shape: 'arrowUp', text: 'AIP ENTRY' });
    }
}

function updateSignals() {
    if (aggregatedCandles.length < 2) return;

    // Update the last 2 candles (current and previous which might have changed)
    updateMarkersForCandle(aggregatedCandles.length - 2);
    updateMarkersForCandle(aggregatedCandles.length - 1);

    charts.candles.setMarkers(cachedMarkers);
}

async function loadHistory() {
    updateStatus('Loading History...', 'bg-yellow-500');
    try {
        const res = await fetch(`/api/ticks/history/${encodeURIComponent(currentSymbol)}?limit=10000`);
        const data = await res.json();
        let ticks = data.history || [];

        if (ticks.length < 50) {
            console.log("History low, supplementing with simulated data...");
            ticks = [...generateSimulatedHistory(), ...ticks];
        }

        const candles = [];
        aggregator.cvd = 0;
        aggregator.currentCandle = null;
        aggregator.currentTickCount = 0;

        const BATCH_SIZE = 500;
        let currentIdx = 0;

        const processBatch = () => {
            const endIdx = Math.min(currentIdx + BATCH_SIZE, ticks.length);
            for (let i = currentIdx; i < endIdx; i++) {
                const result = aggregator.processTick(ticks[i], true);
                if (result.type === 'new') {
                    if (candles.length > 0) aggregator.calculateAnalytics(candles[candles.length - 1]);
                    candles.push({ ...result.candle });
                } else if (candles.length > 0) {
                    candles[candles.length - 1] = { ...result.candle };
                }
            }
            currentIdx = endIdx;

            const progress = Math.round((currentIdx / ticks.length) * 100);
            updateStatus(`Loading ${progress}%`, 'bg-yellow-500');

            if (currentIdx < ticks.length) {
                setTimeout(processBatch, 0);
            } else {
                finishLoading();
            }
        };

        const finishLoading = () => {
            if (candles.length > 0) aggregator.calculateAnalytics(candles[candles.length - 1]);

            charts.candles.setData(candles);
            charts.cvdSeries.setData(candles.map(c => ({ time: c.time, value: c.cvd })));
            aggregatedCandles = candles;

            if (candles.length > 0) {
                charts.main.timeScale().applyOptions({ barSpacing: 60 });
                updatePriceUI(candles[candles.length - 1]);
            }

            // Build historical markers
            cachedMarkers = [];
            for (let i = 1; i < candles.length; i++) {
                updateMarkersForCandle(i);
            }
            charts.candles.setMarkers(cachedMarkers);

            setTimeout(() => {
                requestRender();
            }, 50);

            updateStatus('Live', 'bg-[#00ffc2]');
        };

        processBatch();
    } catch (e) {
        console.error("History load failed", e);
        updateStatus('Error', 'bg-red-500');
    }
}

function generateSimulatedHistory() {
    const now = Date.now();
    const ticks = [];
    let price = 25740.00;
    // Generate 500 ticks
    for (let i = 0; i < 500; i++) {
        price += (Math.random() - 0.5) * 2;
        ticks.push({
            ts_ms: now - (500 - i) * 1000,
            price: price,
            qty: Math.floor(Math.random() * 500) + 100
        });
    }
    return ticks;
}

async function loadSentiment() {
    try {
        const res = await fetch(`/api/modern/data/${encodeURIComponent(currentSymbol)}`);
        const data = await res.json();
        if (data && !data.error) {
            updateSentimentUI(data);
        }
    } catch (e) {
        console.warn("Sentiment load failed", e);
    }
}

function updateSentimentUI(data) {
    const pcr = data.genie?.pcr || 1.0;
    const sentimentValue = document.getElementById('sentiment-value');
    const pcrLabel = document.getElementById('pcr-value');

    if (pcr > 1.1) {
        sentimentValue.textContent = 'BULLISH';
        sentimentValue.className = 'text-3xl font-black italic text-[#00ffc2]';
    } else if (pcr < 0.9) {
        sentimentValue.textContent = 'BEARISH';
        sentimentValue.className = 'text-3xl font-black italic text-[#ff3366]';
    } else {
        sentimentValue.textContent = 'NEUTRAL';
        sentimentValue.className = 'text-3xl font-black italic text-gray-500';
    }

    const oiChange = data.oi_buildup?.total_oi_change || 0;
    const oiStr = oiChange >= 0 ? `+${(oiChange/1000000).toFixed(1)}M` : `${(oiChange/1000000).toFixed(1)}M`;
    pcrLabel.textContent = `PCR: ${pcr.toFixed(2)} | OI: ${oiStr} | PAIN: ${data.genie?.max_pain || '-'}`;
}

function logSignal(type, message, hexColor) {
    const list = document.getElementById('signals-list');
    const time = new Date().toLocaleTimeString('en-IN', { hour12: false });

    const div = document.createElement('div');
    div.className = 'bg-black/20 p-2 rounded border-l-2';
    div.style.borderLeftColor = hexColor;
    div.innerHTML = `
        <div class="flex justify-between items-center mb-1">
            <span class="signal-badge" style="background-color: ${hexColor}33; color: ${hexColor}">${type}</span>
            <span class="text-[8px] text-gray-600 mono">${time}</span>
        </div>
        <p class="text-[10px] text-gray-400 leading-tight">${message}</p>
    `;

    list.prepend(div);
    if (list.childNodes.length > 50) list.lastChild.remove();
}

// Override updateSignals to also log to sidebar
const originalUpdateSignals = updateSignals;
updateSignals = function() {
    originalUpdateSignals();

    const lastCandle = aggregatedCandles[aggregatedCandles.length - 1];
    if (!lastCandle) return;

    // Detect new signals to log
    if (lastCandle._lastLogged) return;

    const buyImbs = (lastCandle.imbalances || []).filter(imb => imb.side === 'buy');
    const sellImbs = (lastCandle.imbalances || []).filter(imb => imb.side === 'sell');

    if (buyImbs.length >= 3) {
        logSignal('STRATEGY', 'Stacked Buy Imbalance detected. Aggressive buying confirmed.', COLORS.bull);
        lastCandle._lastLogged = true;
    } else if (sellImbs.length >= 3) {
        logSignal('STRATEGY', 'Stacked Sell Imbalance detected. Aggressive selling pressure.', COLORS.bear);
        lastCandle._lastLogged = true;
    }

    // AIP Detection in log
    if (aggregatedCandles.length > 1) {
        const prev = aggregatedCandles[aggregatedCandles.length - 2];
        const prevSellImbs = (prev.imbalances || []).filter(imb => imb.side === 'sell');
        const wasPrevAbs = prevSellImbs.length > 0 && prev.close > Math.max(...prevSellImbs.map(imb => imb.price));

        if (wasPrevAbs && buyImbs.length > 0 && lastCandle.close > Math.max(...buyImbs.map(imb => imb.price))) {
            logSignal('AIP', 'Absorption-Initiation Pattern confirmed. High probability long entry.', COLORS.bull);
            lastCandle._lastLogged = true;
        }
    }
};
