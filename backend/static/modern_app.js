/**
 * PRODESK Modern Option Buyer Dashboard
 * High-performance, single-screen tactical command center.
 */

const socket = io();
let currentUnderlying = 'NSE:NIFTY';
let charts = {};
let spotPrice = 0;

// Colors matching requirements
const COLORS = {
    bull: '#00FFC2',
    bear: '#FF3366',
    neutral: '#475569',
    liquidity: '#3b82f6',
    text: '#e5e7eb',
    muted: '#94a3b8',
    bg: '#1e1e1e'
};

let currentATMStrike = 0;
let currentOptionSymbol = null;
let aggregatedCandles = []; // For footprint

document.addEventListener('DOMContentLoaded', () => {
    initLeftPanelCharts();
    initCenterPanel();
    setupEventListeners();
    loadAllData();
    updateTime();
    setInterval(updateTime, 1000);
});

socket.on('connect', () => {
    console.log("Connected to server, subscribing to feeds...");
    if (currentUnderlying) {
        socket.emit('subscribe', { instrumentKeys: [currentUnderlying], interval: '1' });
        socket.emit('subscribe_options', { underlying: currentUnderlying });
    }
});

function setupEventListeners() {
    document.getElementById('assetSelector').addEventListener('change', (e) => {
        const old = currentUnderlying;
        currentUnderlying = e.target.value;

        socket.emit('unsubscribe', { instrumentKeys: [old], interval: '1' });
        socket.emit('unsubscribe_options', { underlying: old });

        socket.emit('subscribe', { instrumentKeys: [currentUnderlying], interval: '1' });
        socket.emit('subscribe_options', { underlying: currentUnderlying });

        loadAllData();
    });
}

function updateTime() {
    const now = new Date();
    const options = {
        timeZone: 'Asia/Kolkata',
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    };
    const formatter = new Intl.DateTimeFormat('en-IN', options);
    document.getElementById('currentTime').textContent = formatter.format(now) + " IST";
}

async function loadAllData() {
    console.log("Starting loadAllData for", currentUnderlying);

    try {
        const fetchWithTimeout = async (url, timeout = 10000) => {
            const controller = new AbortController();
            const id = setTimeout(() => controller.abort(), timeout);
            try {
                const response = await fetch(url, { signal: controller.signal });
                clearTimeout(id);
                if (!response.ok) return null;
                return await response.json();
            } catch (e) {
                clearTimeout(id);
                console.warn(`Fetch timeout or error for ${url}`);
                return null;
            }
        };

        console.log("Fetching consolidated data...");
        const data = await fetchWithTimeout(`/api/modern/data/${encodeURIComponent(currentUnderlying)}`);

        if (data && !data.error) {
            // Update with real data
            if (data.pcr_trend && data.pcr_trend.length > 0) {
                updatePCRGauge({ history: data.pcr_trend });
                updateOIDivergenceChart({ history: data.pcr_trend });
            }

            // Map OI data for the chart
            if (data.oi_buildup && data.oi_buildup.strikes) {
                const oiFormatted = { data: data.oi_buildup.strikes.map(s => ({
                    strike: s.strike,
                    call_oi: s.call_oi,
                    put_oi: s.put_oi
                }))};
                updateOIStrikeChart(oiFormatted);
            }

            if (data.genie) updateGenieData(data.genie);

            if (data.spot_price) {
                spotPrice = data.spot_price;
                document.getElementById('spotPrice').textContent = spotPrice.toLocaleString(undefined, { minimumFractionDigits: 2 });
            }

            if (data.expiries) {
                updateExpirySelector(data.expiries);
            }

            // Identify ATM Strike and Symbol for Chart consistency
            if (data.spot_price && data.chain && data.chain.length > 0) {
                const closest = data.chain.reduce((prev, curr) =>
                    Math.abs(curr.strike - data.spot_price) < Math.abs(prev.strike - data.spot_price) ? curr : prev
                );
                currentATMStrike = closest.strike;

                // Find ATM Call symbol
                const atmCall = data.chain.find(c => c.strike === currentATMStrike && c.option_type === 'call');
                if (atmCall) {
                    currentOptionSymbol = atmCall.symbol;
                    document.getElementById('optionTypeLabel').textContent = `${currentATMStrike} CE`;
                }
            }
        }

        console.log("Triggering Chart Data load...");
        loadChartData();

    } catch (err) {
        console.error("Critical error in loadAllData:", err);
    }
}

// ==================== LEFT PANEL WIDGETS ====================

function initLeftPanelCharts() {
    // Widget 1: PCR Gauge
    const pcrCtx = document.getElementById('pcrGauge').getContext('2d');
    charts.pcrGauge = new Chart(pcrCtx, {
        type: 'doughnut',
        data: {
            labels: ['Bearish', 'Neutral', 'Bullish'],
            datasets: [{
                data: [0.7, 0.4, 0.9],
                backgroundColor: [COLORS.bear + '44', COLORS.neutral + '44', COLORS.bull + '44'],
                borderWidth: 1,
                borderColor: 'rgba(255,255,255,0.05)',
                needleValue: 1.0
            }]
        },
        options: {
            circumference: 180,
            rotation: 270,
            cutout: '85%',
            aspectRatio: 1.8,
            plugins: {
                legend: { display: false },
                tooltip: { enabled: false }
            }
        },
        plugins: [{
            id: 'needle',
            afterDraw: (chart) => {
                const { ctx, chartArea } = chart;
                if (!chartArea || !chart._metasets[0]) return;
                const { width, height } = chartArea;

                ctx.save();
                const needleValue = chart.config.data.datasets[0].needleValue;
                // Map PCR 0-2 to gauge range
                const angle = Math.PI + (Math.min(Math.max(needleValue, 0), 2) / 2) * Math.PI;
                const cx = width / 2;
                const cy = chart._metasets[0].data[0].y;

                // Draw Needle
                ctx.translate(cx, cy);
                ctx.rotate(angle);
                ctx.beginPath();
                ctx.moveTo(0, -2);
                ctx.lineTo(height * 0.8, 0);
                ctx.lineTo(0, 2);
                ctx.fillStyle = COLORS.text;
                ctx.fill();

                // Center circle
                ctx.beginPath();
                ctx.arc(0, 0, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.restore();
            }
        }]
    });

    // PCR Trend Sparkline
    const trendCtx = document.getElementById('pcrTrendChart').getContext('2d');
    charts.pcrTrend = new Chart(trendCtx, {
        type: 'line',
        data: { labels: [], datasets: [{ data: [], borderColor: COLORS.bull, borderWidth: 2, pointRadius: 0, fill: true, backgroundColor: COLORS.bull + '11' }] },
        options: {
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { display: false }, y: { display: false } }
        }
    });

    // Widget 2: Multi-Strike OI split-bar
    const oiCtx = document.getElementById('oiStrikeChart').getContext('2d');
    charts.oiStrike = new Chart(oiCtx, {
        type: 'bar',
        data: { labels: [], datasets: [
            { label: 'Call OI', data: [], backgroundColor: COLORS.bear, borderRadius: 2 },
            { label: 'Put OI', data: [], backgroundColor: COLORS.bull, borderRadius: 2 }
        ]},
        options: {
            indexAxis: 'y',
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: COLORS.muted, font: { size: 9 } } },
                y: { grid: { display: false }, ticks: { color: COLORS.text, font: { size: 10, weight: 'bold' } } }
            }
        }
    });

    // Widget 3: OI Divergence Chart
    const divCtx = document.getElementById('oiPriceDivergenceChart').getContext('2d');
    charts.oiPriceDiv = new Chart(divCtx, {
        data: {
            labels: [],
            datasets: [
                { type: 'line', label: 'Price', data: [], borderColor: '#fbbf24', borderWidth: 2, yAxisID: 'yPrice', pointRadius: 0 },
                { type: 'line', label: 'Total OI', data: [], borderColor: '#a855f7', backgroundColor: '#a855f722', fill: true, borderWidth: 1, yAxisID: 'yOI', pointRadius: 0 }
            ]
        },
        options: {
            maintainAspectRatio: false,
            interaction: { mode: 'index', intersect: false },
            plugins: { legend: { display: false } },
            scales: {
                x: { display: false },
                yPrice: { position: 'left', grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#fbbf24', font: { size: 8 } } },
                yOI: { position: 'right', grid: { display: false }, ticks: { color: '#a855f7', font: { size: 8 } } }
            }
        }
    });
}

function updatePCRGauge(res) {
    const history = res.history || [];
    if (history.length === 0) return;
    const latest = history[history.length - 1];
    const pcr = latest.pcr_oi || 0;

    document.getElementById('pcrValue').textContent = pcr.toFixed(2);
    charts.pcrGauge.data.datasets[0].needleValue = pcr;

    const label = document.getElementById('pcrLabel');
    if (pcr > 1.1) { label.textContent = 'Bullish'; label.className = 'text-[8px] font-bold text-bull uppercase tracking-tighter'; }
    else if (pcr < 0.7) { label.textContent = 'Bearish'; label.className = 'text-[8px] font-bold text-bear uppercase tracking-tighter'; }
    else { label.textContent = 'Neutral'; label.className = 'text-[8px] font-bold text-gray-500 uppercase tracking-tighter'; }

    charts.pcrGauge.update();

    // Trend sparkline
    charts.pcrTrend.data.labels = history.map((_, i) => i);
    charts.pcrTrend.data.datasets[0].data = history.map(h => h.pcr_oi);
    charts.pcrTrend.data.datasets[0].borderColor = pcr >= history[0].pcr_oi ? COLORS.bull : COLORS.bear;
    charts.pcrTrend.update();
}

function updateOIStrikeChart(res) {
    const data = res.data || [];
    // Filter top 7 strikes near spot
    const sorted = [...data].sort((a,b) => b.call_oi + b.put_oi - (a.call_oi + a.put_oi)).slice(0, 7);
    sorted.sort((a,b) => a.strike - b.strike);

    charts.oiStrike.data.labels = sorted.map(d => d.strike);
    charts.oiStrike.data.datasets[0].data = sorted.map(d => -d.call_oi); // Negative for left side
    charts.oiStrike.data.datasets[1].data = sorted.map(d => d.put_oi);
    charts.oiStrike.update();
}

function updateOIDivergenceChart(res) {
    const history = res.history || [];
    charts.oiPriceDiv.data.labels = history.map(h => h.timestamp);
    charts.oiPriceDiv.data.datasets[0].data = history.map(h => h.spot_price || h.underlying_price);
    charts.oiPriceDiv.data.datasets[1].data = history.map(h => h.total_oi);
    charts.oiPriceDiv.update();
}

function updateGenieData(res) {
    document.getElementById('maxPainValue').textContent = res.max_pain || '-';
    // ATM Straddle and IV Rank
    if (res.atm_straddle) {
        document.getElementById('straddleValue').textContent = res.atm_straddle.toFixed(2);
    }
    if (res.iv_rank !== undefined) {
        document.getElementById('ivRankValue').textContent = res.iv_rank + '%';
    }
}

function updateExpirySelector(expiries) {
    const selector = document.getElementById('expirySelector');
    const currentVal = selector.value;
    selector.innerHTML = '';
    expiries.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d;
        opt.textContent = d;
        selector.appendChild(opt);
    });
    if (currentVal && expiries.includes(currentVal)) {
        selector.value = currentVal;
    }
}

// ==================== CENTER PANEL WIDGETS ====================

function initCenterPanel() {
    const chartOptions = {
        layout: { background: { type: 'solid', color: '#1e1e1e' }, textColor: COLORS.muted },
        grid: { vertLines: { color: 'rgba(255,255,255,0.05)' }, horzLines: { color: 'rgba(255,255,255,0.05)' } },
        crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
        timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true, secondsVisible: false }
    };

    // 1. Index Chart
    charts.indexChart = LightweightCharts.createChart(document.getElementById('indexChart'), chartOptions);
    charts.indexCandles = charts.indexChart.addCandlestickSeries({
        upColor: COLORS.bull, downColor: COLORS.bear, borderVisible: false, wickUpColor: COLORS.bull, wickDownColor: COLORS.bear
    });

    // 2. Option Chart
    charts.optionChart = LightweightCharts.createChart(document.getElementById('optionChart'), chartOptions);
    charts.optionCandles = charts.optionChart.addCandlestickSeries({
        upColor: COLORS.bull, downColor: COLORS.bear, borderVisible: false, wickUpColor: COLORS.bull, wickDownColor: COLORS.bear
    });

    // 3. CVD Chart
    charts.cvdChart = LightweightCharts.createChart(document.getElementById('cvdChart'), {
        ...chartOptions,
        timeScale: { ...chartOptions.timeScale, visible: false }
    });
    charts.cvdSeries = charts.cvdChart.addAreaSeries({
        lineColor: COLORS.liquidity, topColor: COLORS.liquidity + '44', bottomColor: 'transparent', lineWidth: 2, priceFormat: { type: 'volume' }
    });

    // Sync charts
    const sync = (master, slaves) => {
        master.timeScale().subscribeVisibleLogicalRangeChange(range => {
            slaves.forEach(s => s.timeScale().setVisibleLogicalRange(range));
        });
    };
    sync(charts.indexChart, [charts.optionChart, charts.cvdChart]);
    sync(charts.optionChart, [charts.indexChart, charts.cvdChart]);

    initFootprintCanvas();

    // Force resize after a small delay to ensure layout is ready
    setTimeout(() => {
        Object.values(charts).forEach(c => {
            if (c && typeof c.resize === 'function') {
                const container = c.autoSizeContainer || c._container; // Lightweight Charts internal
                if (!container) {
                    // Manual resize for Lightweight Charts
                    if (c.timeScale) {
                        const div = document.getElementById(
                            c === charts.indexChart ? 'indexChart' :
                            c === charts.optionChart ? 'optionChart' :
                            c === charts.cvdChart ? 'cvdChart' : ''
                        );
                        if (div) c.applyOptions({ width: div.clientWidth, height: div.clientHeight });
                    }
                }
            }
        });
    }, 100);
}

function initFootprintCanvas() {
    const canvas = document.getElementById('footprintCanvas');
    const ctx = canvas.getContext('2d');

    const resize = () => {
        const container = canvas.parentElement;
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;
    };
    window.addEventListener('resize', resize);
    resize();

    charts.indexChart.timeScale().subscribeVisibleLogicalRangeChange(() => renderOverlays(canvas, ctx));
}

function renderOverlays(canvas, ctx) {
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    renderOrderBlocks(canvas, ctx);
    renderFootprint(canvas, ctx);
}

function renderOrderBlocks(canvas, ctx) {
    // Requirements: "Order Blocks (OB): Translucent boxes extending to the right. Red boxes above price (Bearish), Green boxes below price (Bullish)."
    const timeScale = charts.indexChart.timeScale();
    const visibleRange = timeScale.getVisibleLogicalRange();
    if (!visibleRange) return;

    // Simulated/Real OBs
    const obs = [
        { type: 'BEAR', top: 22215, bottom: 22210, startTime: aggregatedCandles[0]?.time || 0 },
        { type: 'BULL', top: 22175, bottom: 22170, startTime: aggregatedCandles[0]?.time || 0 }
    ];

    obs.forEach(ob => {
        const yTop = charts.indexCandles.priceToCoordinate(ob.top);
        const yBottom = charts.indexCandles.priceToCoordinate(ob.bottom);
        if (yTop === null || yBottom === null) return;

        const xStart = timeScale.timeToCoordinate(ob.startTime) || 0;

        ctx.fillStyle = ob.type === 'BEAR' ? 'rgba(255, 51, 102, 0.25)' : 'rgba(0, 255, 194, 0.25)';
        ctx.strokeStyle = ob.type === 'BEAR' ? 'rgba(255, 51, 102, 0.4)' : 'rgba(0, 255, 194, 0.4)';
        ctx.fillRect(Math.max(xStart, 0), yTop, canvas.width, yBottom - yTop);
        ctx.strokeRect(Math.max(xStart, 0), yTop, canvas.width, yBottom - yTop);
    });
}

function renderFootprint(canvas, ctx) {
    const timeScale = charts.indexChart.timeScale();
    const barSpacing = timeScale.options().barSpacing;
    if (barSpacing < 50) return;

    aggregatedCandles.forEach(candle => {
        const x = timeScale.timeToCoordinate(candle.time);
        if (x === null || x < 0 || x > canvas.width) return;

        const footprint = candle.footprint || {};
        const prices = Object.keys(footprint).map(Number).sort((a, b) => b - a);
        const halfWidth = (barSpacing / 2) * 0.9;

        // 1. Draw Value Area (VA) Box
        if (candle.vah && candle.val) {
            const vahY = charts.indexCandles.priceToCoordinate(candle.vah);
            const valY = charts.indexCandles.priceToCoordinate(candle.val);
            if (vahY !== null && valY !== null) {
                ctx.strokeStyle = 'rgba(59, 130, 246, 0.5)';
                ctx.setLineDash([2, 2]);
                ctx.strokeRect(x - halfWidth - 2, vahY - 6, halfWidth * 2 + 4, valY - vahY + 12);
                ctx.setLineDash([]);
            }
        }

        prices.forEach((p, i) => {
            const y = charts.indexCandles.priceToCoordinate(p);
            if (y === null || y < 0 || y > canvas.height) return;

            const data = footprint[p];
            const buy = data.buy || 0;
            const sell = data.sell || 0;
            const delta = buy - sell;

            // 2. Diagonal Imbalance Detection (3:1 Ratio)
            let isBuyImbalance = false;
            let isSellImbalance = false;

            if (i < prices.length - 1) {
                const nextP = prices[i+1];
                const prevSell = footprint[nextP]?.sell || 0;
                if (buy >= prevSell * 3 && buy > 0 && prevSell > 0) isBuyImbalance = true;
            }
            if (i > 0) {
                const prevP = prices[i-1];
                const nextBuy = footprint[prevP]?.buy || 0;
                if (sell >= nextBuy * 3 && sell > 0 && nextBuy > 0) isSellImbalance = true;
            }

            // Cell Background
            if (isBuyImbalance) {
                ctx.fillStyle = 'rgba(0, 255, 194, 0.3)';
                ctx.fillRect(x, y - 6, halfWidth, 12);
            } else if (isSellImbalance) {
                ctx.fillStyle = 'rgba(255, 51, 102, 0.3)';
                ctx.fillRect(x - halfWidth, y - 6, halfWidth, 12);
            } else {
                ctx.fillStyle = (p >= candle.val && p <= candle.vah) ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.03)';
                ctx.fillRect(x - halfWidth, y - 6, halfWidth * 2, 12);
            }

            // 3. Point of Control (POC) Highlight
            if (p === candle.poc) {
                ctx.strokeStyle = '#fbbf24';
                ctx.lineWidth = 2;
                ctx.strokeRect(x - halfWidth, y - 6, halfWidth * 2, 12);
                ctx.lineWidth = 1;
            }

            // Numbers
            ctx.font = (isBuyImbalance || isSellImbalance) ? 'bold 7px "IBM Plex Mono"' : '6px "IBM Plex Mono"';
            ctx.textAlign = 'right';
            ctx.fillStyle = isSellImbalance ? COLORS.bear : COLORS.muted;
            ctx.fillText(sell, x - 4, y + 3);

            ctx.textAlign = 'left';
            ctx.fillStyle = isBuyImbalance ? COLORS.bull : COLORS.muted;
            ctx.fillText(buy, x + 4, y + 3);

            // Center Split
            ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            ctx.beginPath(); ctx.moveTo(x, y - 4); ctx.lineTo(x, y + 4); ctx.stroke();
        });
    });
}

let priceLines = [];

async function loadChartData() {
    const fetchWithTimeout = async (url, timeout = 10000) => {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), timeout);
        try {
            const response = await fetch(url, { signal: controller.signal });
            clearTimeout(id);
            if (!response.ok) return null;
            return await response.json();
        } catch (e) {
            clearTimeout(id);
            return null;
        }
    };

    // Load Index History
    console.log("Loading Index History for", currentUnderlying);
    let indexRes = await fetchWithTimeout(`/api/tv/intraday/${encodeURIComponent(currentUnderlying)}?interval=1`);

    if (indexRes && indexRes.candles && indexRes.candles.length > 0) {
        const sortedIndex = [...indexRes.candles].sort((a, b) => a[0] - b[0]);
        const formattedIndex = sortedIndex.map(c => ({ time: c[0], open: c[1], high: c[2], low: c[3], close: c[4] }));
        charts.indexCandles.setData(formattedIndex);

        charts.indexChart.timeScale().applyOptions({ barSpacing: 60 });
        updateCVDFromCandles(formattedIndex);
        updateLevels(indexRes);

        // Footprint simulation based on real OHLC
        aggregatedCandles = formattedIndex.map(c => ({
            ...c,
            footprint: generateMockFootprint(c.low, c.high)
        }));
    }

    // Load Option History for fixed ATM symbol to ensure consistency
    if (currentOptionSymbol) {
        console.log("Loading Option History for", currentOptionSymbol);
        let optRes = await fetchWithTimeout(`/api/tv/intraday/${encodeURIComponent(currentOptionSymbol)}?interval=1`);
        if (optRes && optRes.candles && optRes.candles.length > 0) {
            const sortedOpt = [...optRes.candles].sort((a, b) => a[0] - b[0]);
            const formattedOpt = sortedOpt.map(c => ({ time: c[0], open: c[1], high: c[2], low: c[3], close: c[4] }));
            charts.optionCandles.setData(formattedOpt);
        }
    }
}

function generateMockFootprint(low, high) {
    const footprint = {};
    const step = 0.5;
    let totalVol = 0;
    let maxVol = 0;
    let poc = low;
    const prices = [];

    for (let p = low; p <= high; p += step) {
        const price = parseFloat(p.toFixed(2));
        // More volume in the middle of the candle
        const dist = 1.0 - (Math.abs(price - (low + high) / 2) / (high - low || 1));
        const buy = Math.floor((Math.random() * 1500 + 500) * dist);
        const sell = Math.floor((Math.random() * 1500 + 500) * dist);
        const vol = buy + sell;

        footprint[price] = { buy: Math.max(1, buy), sell: Math.max(1, sell) };
        totalVol += vol;
        if (vol > maxVol) {
            maxVol = vol;
            poc = price;
        }
        prices.push(price);
    }

    // Mock Value Area (70% Volume)
    const vaVol = totalVol * 0.7;
    let currentVaVol = maxVol;
    let sortedPrices = prices.sort((a, b) => a - b);
    let lowerIdx = sortedPrices.indexOf(poc);
    let upperIdx = lowerIdx;

    while (currentVaVol < vaVol && (lowerIdx > 0 || upperIdx < sortedPrices.length - 1)) {
        let lVol = lowerIdx > 0 ? (footprint[sortedPrices[lowerIdx-1]].buy + footprint[sortedPrices[lowerIdx-1]].sell) : 0;
        let uVol = upperIdx < sortedPrices.length - 1 ? (footprint[sortedPrices[upperIdx+1]].buy + footprint[sortedPrices[upperIdx+1]].sell) : 0;
        if (lVol >= uVol) { currentVaVol += lVol; lowerIdx--; }
        else { currentVaVol += uVol; upperIdx++; }
    }

    return {
        data: footprint,
        poc: poc,
        vah: sortedPrices[upperIdx],
        val: sortedPrices[lowerIdx]
    };
}

function updateLevels(res) {
    if (!res.indicators) return;

    // Clear old lines if any (hacky way: recreate series or just add once)
    // For now, we'll just add them.
    res.indicators.forEach(ind => {
        if (ind.type === 'price_line') {
            charts.indexCandles.createPriceLine({
                price: ind.data.price,
                color: ind.data.color || COLORS.muted,
                lineWidth: 1,
                lineStyle: ind.data.lineStyle || 2,
                axisLabelVisible: true,
                title: ind.title
            });
        }
        if (ind.type === 'markers') {
            charts.indexCandles.setMarkers(ind.data);
        }
    });
}

function updateCVDFromCandles(candles) {
    let cvd = 0;
    const cvdData = candles.map(c => {
        const diff = c.close - c.open;
        cvd += diff * 100; // Simulated delta
        return { time: c.time, value: cvd };
    });
    charts.cvdSeries.setData(cvdData);
}


// Socket events
socket.on('raw_tick', (data) => {
    const key = currentUnderlying.toUpperCase();
    if (data[key]) {
        const tick = data[key];
        spotPrice = tick.last_price || tick.price;
        document.getElementById('spotPrice').textContent = spotPrice.toLocaleString(undefined, { minimumFractionDigits: 2 });
    }
});

socket.on('chart_update', (data) => {
    // Check if it's the right instrument and has data
    if (data && (data.instrumentKey === currentUnderlying || data.instrument_key === currentUnderlying)) {
        const ohlcv = data.ohlcv || data.data?.ohlcv || data.data;
        if (ohlcv && Array.isArray(ohlcv) && ohlcv.length > 0) {
            const candle = ohlcv[0];
            spotPrice = candle[4]; // Close
            document.getElementById('spotPrice').textContent = spotPrice.toLocaleString(undefined, { minimumFractionDigits: 2 });

            // Update charts live
            const formatted = {
                time: candle[0],
                open: candle[1],
                high: candle[2],
                low: candle[3],
                close: candle[4]
            };
            charts.indexCandles.update(formatted);

            // Update CVD
            const diff = formatted.close - formatted.open;
            // This is a bit simplified, but adds to live feel
            // In real app, you'd get real CVD data
        }
    }
});

socket.on('options_quote_update', (data) => {
    // Update options chart live with tick data
    if (data && data.lp !== undefined && data.lp !== null) {
        // We don't have full OHLCV here, but we can update with current price
        // Lightweight Charts will merge this into the current bar if time matches
        const formatted = {
            time: Math.floor(Date.now() / 1000),
            value: data.lp
        };
        // Option chart is a Candlestick series, it needs OHLC
        // Approximate it for the live feel
        const lastBar = {
            time: Math.floor(Date.now() / 60) * 60, // Minute bucket
            open: data.lp,
            high: data.lp,
            low: data.lp,
            close: data.lp
        };
        charts.optionCandles.update(lastBar);
    }
});
