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

    document.getElementById('buyCallBtn').addEventListener('click', () => executeTrade('CALL'));
    document.getElementById('buyPutBtn').addEventListener('click', () => executeTrade('PUT'));
    document.getElementById('closeAllBtn').addEventListener('click', () => closeAllPositions());

    document.querySelectorAll('.strike-toggle').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.strike-toggle').forEach(b => b.classList.remove('active', 'bg-gray-700', 'text-cyan-400', 'border-cyan-400/50'));
            document.querySelectorAll('.strike-toggle').forEach(b => b.classList.add('bg-gray-800', 'text-gray-400'));

            btn.classList.add('active', 'bg-gray-700', 'text-cyan-400', 'border-cyan-400/50');
            btn.classList.remove('bg-gray-800', 'text-gray-400');
        });
    });

    document.querySelectorAll('.qty-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            document.querySelectorAll('.qty-btn').forEach(b => b.classList.remove('active', 'bg-cyan-500/20', 'text-cyan-400', 'border-cyan-400/50'));
            btn.classList.add('active', 'bg-cyan-500/20', 'text-cyan-400', 'border-cyan-400/50');
        });
    });
}

async function executeTrade(side) {
    const offset = parseInt(document.querySelector('.strike-toggle.active')?.dataset.offset || 0);
    const qty = document.querySelector('.qty-btn.active')?.dataset.qty || 100;

    console.log(`Executing ${side} trade: Offset ${offset}, Qty ${qty}`);

    // In a real app, this would call /api/scalper/start or a direct execution endpoint
    await fetch(`/api/scalper/start?underlying=${currentUnderlying}`, { method: 'POST' });
    loadAllData(); // Refresh UI
}

async function closeAllPositions() {
    if (confirm("Confirm CLOSE ALL positions?")) {
        console.log("Closing all positions...");
        await fetch('/api/scalper/stop', { method: 'POST' });
        loadAllData();
    }
}

async function closePosition(symbol) {
    console.log(`Closing position: ${symbol}`);
    // Simulated close
    await fetch('/api/scalper/stop', { method: 'POST' });
    loadAllData();
}

function updateTime() {
    const now = new Date();
    document.getElementById('currentTime').textContent = now.toLocaleTimeString('en-IN', { hour12: false });
}

async function loadAllData() {
    console.log("Starting loadAllData for", currentUnderlying);

    // Immediately render simulation data so the UI isn't empty while waiting for potentially slow backend
    const mock = generateSimulationData();
    updatePCRGauge(mock.pcrRes);
    updateOIStrikeChart(mock.oiRes);
    updateOIDivergenceChart(mock.pcrRes);
    updateGenieData(mock.genieRes);
    renderLiquidityHeatmap(mock.srRes);
    updatePositionsTable([]);

    try {
        const fetchWithTimeout = async (url, timeout = 5000) => {
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
            if (data.sr_levels) renderLiquidityHeatmap(data.sr_levels);

            if (data.spot_price) {
                spotPrice = data.spot_price;
                document.getElementById('spotPrice').textContent = spotPrice.toLocaleString(undefined, { minimumFractionDigits: 2 });
            }
        }

        // Still need scalper status separately as it's more dynamic
        const scalperRes = await fetchWithTimeout('/api/scalper/status');
        if (scalperRes && scalperRes.active_trades) updatePositionsTable(scalperRes.active_trades);

        console.log("Triggering Chart Data load...");
        loadChartData();

    } catch (err) {
        console.warn("Non-critical error in loadAllData fetch sequence:", err);
    }
}

function generateSimulationData() {
    const now = Date.now();
    const history = [];
    let price = 22150.50;
    let oi = 100000000;

    for (let i = 0; i < 60; i++) {
        const trend = Math.sin(i / 10) * 50; // Add some wavy trend
        price += (Math.random() - 0.5) * 15 + trend / 10;
        oi += (Math.random() - 0.5) * 800000;
        history.push({
            timestamp: new Date(now - (60 - i) * 60000).toISOString(),
            pcr_oi: 0.85 + Math.sin(i / 5) * 0.2 + (Math.random() * 0.1),
            spot_price: price,
            underlying_price: price,
            total_oi: oi
        });
    }

    const strikes = [22000, 22050, 22100, 22150, 22200, 22250, 22300];
    const oiData = strikes.map((s, idx) => {
        // More realistic OI distribution (bell curve near ATM)
        const dist = Math.exp(-Math.pow(idx - 3, 2) / 4);
        return {
            strike: s,
            call_oi: Math.floor((Math.random() * 5000000 + 2000000) * dist),
            put_oi: Math.floor((Math.random() * 5000000 + 2000000) * dist)
        };
    });

    spotPrice = price;
    document.getElementById('spotPrice').textContent = spotPrice.toLocaleString(undefined, { minimumFractionDigits: 2 });

    return {
        pcrRes: { history },
        oiRes: { data: oiData },
        genieRes: { max_pain: 22100, atm_straddle: 145.50, iv_rank: 45 },
        srRes: {
            resistance_levels: [{ strike: 22200, oi: 2500000 }, { strike: 22300, oi: 1800000 }],
            support_levels: [{ strike: 22100, oi: 2200000 }, { strike: 22000, oi: 1500000 }]
        }
    };
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

    // Populate Expiry if empty
    const selector = document.getElementById('expirySelector');
    if (selector.options.length === 0) {
        const dates = ['20-FEB-2026', '27-FEB-2026', '06-MAR-2026'];
        dates.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.textContent = d;
            selector.appendChild(opt);
        });
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
    const fetchWithTimeout = async (url, timeout = 5000) => {
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

    let res = await fetchWithTimeout(`/api/tv/intraday/${encodeURIComponent(currentUnderlying)}?interval=1`);

    if (!res) res = {};
    if (!res.candles || res.candles.length < 5) {
        // Mock historical candles
        const now = Math.floor(Date.now() / 1000);
        let p = 22150;
        res.candles = [];
        for (let i = 0; i < 200; i++) {
            const o = p + (Math.random() - 0.5) * 5;
            const c = o + (Math.random() - 0.5) * 5;
            res.candles.push([ (now - (200 - i) * 60), o, Math.max(o,c) + 2, Math.min(o,c) - 2, c, Math.random() * 1000 ]);
            p = c;
        }
        res.indicators = [
            { type: 'price_line', title: 'VWAP', data: { price: 22145, color: '#3b82f6' } },
            { type: 'price_line', title: 'PDH', data: { price: 22210, color: COLORS.bear } }
        ];
    }

    if (res.candles && res.candles.length > 0) {
        // Sort candles ascending for Lightweight Charts
        const sortedCandles = [...res.candles].sort((a, b) => a[0] - b[0]);
        const formatted = sortedCandles.map(c => ({ time: c[0], open: c[1], high: c[2], low: c[3], close: c[4] }));
        charts.indexCandles.setData(formatted);

        // Mock data for option chart
        charts.optionCandles.setData(formatted.map(c => ({
            time: c.time,
            open: (c.open % 500) + 100,
            high: (c.high % 500) + 105,
            low: (c.low % 500) + 95,
            close: (c.close % 500) + 102
        })));

        charts.indexChart.timeScale().applyOptions({ barSpacing: 60 });

        updateCVDFromCandles(formatted);
        updateLevels(res);

        // Populate aggregatedCandles for Footprint visualization
        aggregatedCandles = formatted.map(c => ({
            ...c,
            footprint: generateMockFootprint(c.low, c.high)
        }));
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

// ==================== RIGHT PANEL WIDGETS ====================

function renderLiquidityHeatmap(res) {
    const canvas = document.getElementById('heatmapCanvas');
    const ctx = canvas.getContext('2d');
    const scale = document.getElementById('heatmapPriceScale');

    const container = canvas.parentElement;
    canvas.width = container.clientWidth;
    canvas.height = container.clientHeight;

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    scale.innerHTML = '';

    const levels = [
        ...(res.resistance_levels || []).map(l => ({ ...l, type: 'RES' })),
        ...(res.support_levels || []).map(l => ({ ...l, type: 'SUP' }))
    ].sort((a, b) => b.strike - a.strike);

    if (levels.length === 0) return;

    const maxStrike = levels[0].strike + 100;
    const minStrike = levels[levels.length - 1].strike - 100;
    const range = maxStrike - minStrike;

    // Draw scale
    for (let i = 0; i <= 5; i++) {
        const s = maxStrike - (i * range / 5);
        const div = document.createElement('div');
        div.textContent = Math.round(s);
        scale.appendChild(div);
    }

    levels.forEach(l => {
        const y = ((maxStrike - l.strike) / range) * canvas.height;
        const weight = Math.min(l.oi / 2000000, 1.0);

        const gradient = ctx.createLinearGradient(0, y - 10, 0, y + 10);
        const color = l.type === 'RES' ? '255, 51, 102' : '0, 255, 194';
        gradient.addColorStop(0, `rgba(${color}, 0)`);
        gradient.addColorStop(0.5, `rgba(${color}, ${0.1 + weight * 0.4})`);
        gradient.addColorStop(1, `rgba(${color}, 0)`);

        ctx.fillStyle = gradient;
        ctx.fillRect(0, y - 15, canvas.width, 30);

        // Bright line in center
        ctx.strokeStyle = `rgba(${color}, ${0.3 + weight * 0.7})`;
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, y);
        ctx.lineTo(canvas.width, y);
        ctx.stroke();
    });
}

function updatePositionsTable(trades) {
    const body = document.getElementById('positionsBody');
    body.innerHTML = '';

    if (!trades || trades.length === 0) {
        body.innerHTML = '<tr><td colspan="4" class="py-10 text-center text-gray-600 uppercase font-black text-[8px]">No active raids</td></tr>';
        return;
    }

    trades.forEach(t => {
        const pnl = (t.last_price - t.entry_price) * t.quantity;
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-white/5 transition-colors';
        tr.innerHTML = `
            <td class="py-2 px-2 font-bold text-gray-300 uppercase">${t.symbol.split(':').pop()}</td>
            <td class="py-2 px-2 text-right font-black ${pnl >= 0 ? 'text-bull' : 'text-bear'}">${pnl.toFixed(2)}</td>
            <td class="py-2 px-2 text-right text-gray-400">0.00</td>
            <td class="py-2 px-2 text-center">
                <button class="text-bear hover:bg-bear/20 p-1 rounded close-pos-btn" data-symbol="${t.symbol}">
                    <svg class="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="3" d="M6 18L18 6M6 6l12 12"/></svg>
                </button>
            </td>
        `;
        body.appendChild(tr);
    });

    body.querySelectorAll('.close-pos-btn').forEach(btn => {
        btn.addEventListener('click', () => closePosition(btn.dataset.symbol));
    });
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
    if (data.instrumentKey === currentUnderlying && data.ohlcv && data.ohlcv.length > 0) {
        const candle = data.ohlcv[0];
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
});

socket.on('options_quote_update', (data) => {
    // Update options chart live
    if (data && data.ohlcv && data.ohlcv.length > 0) {
        const candle = data.ohlcv[0];
        const formatted = {
            time: candle[0],
            open: candle[1],
            high: candle[2],
            low: candle[3],
            close: candle[4]
        };
        charts.optionCandles.update(formatted);
    }
});

socket.on('scalper_metrics', (data) => {
    if (data.active_trades) {
        updatePositionsTable(data.active_trades);
    }
});
