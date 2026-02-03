/**
 * PRODESK Main Application
 * Handles Socket.IO connection, data orchestration, and ECharts rendering.
 */

const socket = io();

// UI State
let currentIndex = 'NIFTY';
let currentAtm = 0;
let expiryDate = '';
let isReplay = false;
let replayDate = '';

// Data Buffers
let indexData = [];
let ceData = [];
let peData = [];
let pcrData = [];
let mtf5Data = [];
let mtf15Data = [];
let atmKeys = { ce: '', pe: '' };

// Charts
let charts = {
    index: null,
    ce: null,
    pe: null,
    pcr: null
};

// --- Initialization ---

function init() {
    charts.index = echarts.init(document.getElementById('indexChart'));
    charts.ce = echarts.init(document.getElementById('ceChart'));
    charts.pe = echarts.init(document.getElementById('peChart'));
    charts.pcr = echarts.init(document.getElementById('pcrChart'));

    window.addEventListener('resize', () => {
        Object.values(charts).forEach(c => c && c.resize());
    });

    document.getElementById('indexSelect').addEventListener('change', (e) => {
        switchIndex(e.target.value);
    });

    loadInitialData();
    initSocket();
    fetchReplayDates();
    initFullscreen();
    initTabs();
}

function initTabs() {
    const tabIndexBtn = document.getElementById('tabIndexBtn');
    const tabOptionsBtn = document.getElementById('tabOptionsBtn');
    const tabIndexContent = document.getElementById('tabIndexContent');
    const tabOptionsContent = document.getElementById('tabOptionsContent');

    tabIndexBtn.addEventListener('click', () => {
        tabIndexContent.classList.remove('hidden');
        tabOptionsContent.classList.add('hidden');

        tabIndexBtn.classList.add('bg-blue-600', 'text-white');
        tabIndexBtn.classList.remove('bg-gray-900', 'text-gray-400');

        tabOptionsBtn.classList.add('bg-gray-900', 'text-gray-400');
        tabOptionsBtn.classList.remove('bg-blue-600', 'text-white');

        // Resize charts when they become visible
        setTimeout(() => {
            charts.index && charts.index.resize();
            charts.pcr && charts.pcr.resize();
        }, 50);
    });

    tabOptionsBtn.addEventListener('click', () => {
        tabOptionsContent.classList.remove('hidden');
        tabIndexContent.classList.add('hidden');

        tabOptionsBtn.classList.add('bg-blue-600', 'text-white');
        tabOptionsBtn.classList.remove('bg-gray-900', 'text-gray-400');

        tabIndexBtn.classList.add('bg-gray-900', 'text-gray-400');
        tabIndexBtn.classList.remove('bg-blue-600', 'text-white');

        // Resize charts when they become visible
        setTimeout(() => {
            charts.ce && charts.ce.resize();
            charts.pe && charts.pe.resize();
        }, 50);
    });
}

function initFullscreen() {
    document.querySelectorAll('.maximize-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const container = btn.closest('.chart-container');
            const chartKey = container.dataset.chart;
            container.classList.toggle('fullscreen-chart');
            // Small delay to allow CSS transition if any, though fixed position is instant
            setTimeout(() => {
                if (charts[chartKey]) charts[chartKey].resize();
            }, 50);
        });
    });
}

async function loadInitialData() {
    setLoading(true);
    try {
        // 1. Fetch Expiry
        const expRes = await fetch(`/api/trendlyne/expiry/${currentIndex}`);
        const expiries = await expRes.json();
        if (expiries && expiries.length > 0) expiryDate = expiries[0].date;

        // 2. Load Index & MTF
        const [i1m, i5m, i15m, pcr] = await Promise.all([
            fetchIntraday(currentIndex, '1'),
            fetchIntraday(currentIndex, '5'),
            fetchIntraday(currentIndex, '15'),
            fetchHistoricalPcr(currentIndex)
        ]);

        indexData = i1m;
        mtf5Data = i5m;
        mtf15Data = i15m;
        pcrData = pcr;

        if (indexData.length > 0) {
            const last = indexData[indexData.length - 1];
            updateAtmStrike(last.close);
            renderChart(charts.index, 'INDEX', indexData, { mtf5: mtf5Data, mtf15: mtf15Data });
        }
        renderPcrChart();

        if (expiryDate && currentAtm > 0) {
            await loadOptionsData();
            syncIndexVolume();
            renderChart(charts.index, 'INDEX', indexData, { mtf5: mtf5Data, mtf15: mtf15Data });
        }
    } catch (e) {
        console.error("Init Data Fail:", e);
    } finally {
        setLoading(false);
    }
}

async function loadOptionsData() {
    try {
        const chainRes = await fetch(`/api/upstox/option_chain/${encodeURIComponent(currentIndex)}/${expiryDate}`);
        const chain = await chainRes.json();
        const atmItem = chain.find(i => i.strike_price === currentAtm);
        if (atmItem) {
            atmKeys.ce = atmItem.call_options.instrument_key;
            atmKeys.pe = atmItem.put_options.instrument_key;

            const [ceCandles, peCandles] = await Promise.all([
                fetchIntraday(atmKeys.ce),
                fetchIntraday(atmKeys.pe)
            ]);
            ceData = ceCandles;
            peData = peCandles;

            renderChart(charts.ce, 'ATM CE', ceData);
            renderChart(charts.pe, 'ATM PE', peData);

            // Subscribe to options via socket
            socket.emit('subscribe', { instrumentKeys: [currentIndex, atmKeys.ce, atmKeys.pe] });
        }
    } catch (e) {
        console.error("Load Options Fail:", e);
    }
}

async function fetchIntraday(key, interval = '1') {
    let url = `/api/upstox/intraday/${encodeURIComponent(key)}?interval=${interval}`;
    if (isReplay && replayDate) url += `&date=${replayDate}`;
    const res = await fetch(url);
    const data = await res.json();
    if (data && data.candles) {
        return data.candles.map(c => ({
            timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
        })).reverse();
    }
    return [];
}

async function fetchHistoricalPcr(symbol) {
    let url = `/api/analytics/pcr/${symbol}`;
    if (isReplay && replayDate) url += `?date=${replayDate}`;
    const res = await fetch(url);
    return await res.json();
}

// --- Socket Handlers ---

function initSocket() {
    socket.on('connect', () => {
        document.getElementById('socketStatus').innerHTML = '<div class="w-1.5 h-1.5 bg-green-500 rounded-full"></div> CONNECTED';
        socket.emit('subscribe', { instrumentKeys: [currentIndex] });
    });

    socket.on('disconnect', () => {
        document.getElementById('socketStatus').innerHTML = '<div class="w-1.5 h-1.5 bg-red-500 rounded-full"></div> DISCONNECTED';
    });

    socket.on('raw_tick', (data) => {
        const rawData = typeof data === 'string' ? JSON.parse(data) : data;
        handleTickUpdate(rawData);
    });

    socket.on('oi_update', (msg) => {
        if (msg.symbol === currentIndex) {
            pcrData.push({ timestamp: msg.timestamp, pcr: msg.pcr });
            if (pcrData.length > 1000) pcrData.shift();
            document.getElementById('pcrInfo').innerText = `PCR: ${msg.pcr.toFixed(2)}`;
            renderPcrChart();
        }
    });

    socket.on('replay_status', (status) => {
        isReplay = !!status.active;
        replayDate = status.date || '';
        if (status.is_new) {
            indexData = []; ceData = []; peData = []; pcrData = [];
        }
    });
}

function handleTickUpdate(quotes) {
    let indexUpdated = false, ceUpdated = false, peUpdated = false;

    if (quotes[currentIndex] && quotes[currentIndex].last_price) {
        indexData = updateCandle(indexData, quotes[currentIndex]);
        mtf5Data = updateCandleMTF(mtf5Data, quotes[currentIndex], 5);
        mtf15Data = updateCandleMTF(mtf15Data, quotes[currentIndex], 15);
        indexUpdated = true;
        document.getElementById('spotPrice').innerText = quotes[currentIndex].last_price.toFixed(2);
    }
    if (atmKeys.ce && quotes[atmKeys.ce] && quotes[atmKeys.ce].last_price) {
        ceData = updateCandle(ceData, quotes[atmKeys.ce]);
        ceUpdated = true;
    }
    if (atmKeys.pe && quotes[atmKeys.pe] && quotes[atmKeys.pe].last_price) {
        peData = updateCandle(peData, quotes[atmKeys.pe]);
        peUpdated = true;
    }

    // Sync Index Volume as sum of ATM CE + PE
    if (ceUpdated || peUpdated) {
        syncIndexVolume();
        indexUpdated = true; // Force re-render of index chart to show new volume
    }

    if (indexUpdated) renderChart(charts.index, 'INDEX', indexData, { mtf5: mtf5Data, mtf15: mtf15Data });
    if (ceUpdated) renderChart(charts.ce, 'ATM CE', ceData);
    if (peUpdated) renderChart(charts.pe, 'ATM PE', peData);
}

function syncIndexVolume() {
    if (!indexData.length) return;
    const ceMap = new Map(ceData.map(d => [d.timestamp, d.volume]));
    const peMap = new Map(peData.map(d => [d.timestamp, d.volume]));

    indexData.forEach(d => {
        const cv = ceMap.get(d.timestamp) || 0;
        const pv = peMap.get(d.timestamp) || 0;
        d.volume = cv + pv;
    });
}

function updateCandleMTF(prev, quote, minutes) {
    const tickTime = new Date(quote.ts_ms);
    const intervalMs = minutes * 60 * 1000;
    const tickInterval = new Date(Math.floor(tickTime.getTime() / intervalMs) * intervalMs);
    const ltq = quote.ltq || 0;

    if (!prev.length) {
        return [{
            timestamp: tickInterval.toISOString(),
            open: quote.last_price, high: quote.last_price, low: quote.last_price, close: quote.last_price, volume: ltq
        }];
    }

    const last = { ...prev[prev.length - 1] };
    const lastTime = new Date(last.timestamp);

    if (tickInterval.getTime() > lastTime.getTime()) {
        return [...prev.slice(-100), {
            timestamp: tickInterval.toISOString(),
            open: quote.last_price, high: quote.last_price, low: quote.last_price, close: quote.last_price, volume: ltq
        }];
    } else {
        last.close = quote.last_price;
        last.high = Math.max(last.high, quote.last_price);
        last.low = Math.min(last.low, quote.last_price);
        last.volume += ltq;
        return [...prev.slice(0, -1), last];
    }
}

function updateCandle(prev, quote) {
    const tickTime = new Date(quote.ts_ms);
    const tickMinute = new Date(tickTime.setSeconds(0, 0, 0));
    const ltq = quote.ltq || 0;

    if (!prev.length) {
        return [{
            timestamp: tickMinute.toISOString(),
            open: quote.last_price, high: quote.last_price, low: quote.last_price, close: quote.last_price, volume: ltq
        }];
    }

    const last = { ...prev[prev.length - 1] };
    const lastMinute = new Date(new Date(last.timestamp).setSeconds(0, 0, 0));

    if (tickMinute.getTime() > lastMinute.getTime()) {
        return [...prev.slice(-499), {
            timestamp: tickMinute.toISOString(),
            open: quote.last_price, high: quote.last_price, low: quote.last_price, close: quote.last_price, volume: ltq
        }];
    } else {
        last.close = quote.last_price;
        last.high = Math.max(last.high, quote.last_price);
        last.low = Math.min(last.low, quote.last_price);
        last.volume += ltq;
        return [...prev.slice(0, -1), last];
    }
}

// --- Rendering ---

function renderChart(chart, title, data, mtf = {}) {
    if (!data.length) return;

    // 1. Indicators Logic
    const volumes = data.map(d => d.volume);
    const avgVol20 = Indicators.sma(volumes, 20);
    const colors = data.map((d, i) => Indicators.getBarColor(d.open, d.close, d.volume, avgVol20[i]));
    const bubbles = Indicators.getBubbleData(data, 100, 2.5, 0.75);
    const evwma = Indicators.evwma(data.map(d => d.close), volumes, 5);

    let cumPV = 0, cumV = 0;
    const vwap = data.map(d => {
        const typical = (d.high + d.low + d.close) / 3;
        cumPV += typical * (d.volume || 0);
        cumV += (d.volume || 0);
        return cumV > 0 ? cumPV / cumV : typical;
    });

    const dataWithVwap = data.map((d, i) => ({ ...d, vwap: vwap[i] }));
    const dynPivot = Indicators.dynamicPivot(dataWithVwap, 20, 10);
    const highs = data.map(d => d.high);
    const lows = data.map(d => d.low);
    const swings = Indicators.swingDetection(highs, lows, 5, 2);
    const mtfData = Indicators.getMTFData(data); // 1m MTF (S/R Lines)

    // BgColor Logic (Swing Breaks)
    const areas = [];
    data.forEach((d, i) => {
        const isAbove = d.close > swings.lastSH[i];
        const isBelow = d.close < swings.lastSL[i];
        if (isAbove || isBelow) {
            areas.push({
                xAxis: i,
                itemStyle: { color: isAbove ? 'rgba(34, 197, 94, 0.05)' : 'rgba(239, 68, 68, 0.05)' }
            });
        }
    });

    // 2. MTF Dots Logic
    let mtf2Dots = [], mtf3Dots = [];
    if (mtf.mtf5) {
        const d5 = Indicators.getMTFData(mtf.mtf5);
        // Map 5m S/R to 1m timeline
        mtf2Dots = mapMTFTo1M(data, mtf.mtf5, d5);
    }
    if (mtf.mtf15) {
        const d15 = Indicators.getMTFData(mtf.mtf15);
        mtf3Dots = mapMTFTo1M(data, mtf.mtf15, d15);
    }

    const timeLabels = data.map(d => new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }));

    const options = {
        backgroundColor: 'transparent',
        animation: false,
        tooltip: {
            trigger: 'axis', axisPointer: { type: 'cross' },
            backgroundColor: '#111827', borderColor: '#374151',
            textStyle: { color: '#e5e7eb', fontSize: 10 }
        },
        axisPointer: { link: { xAxisIndex: 'all' } },
        dataZoom: [
            { type: 'inside', xAxisIndex: [0, 1], start: 70, end: 100 },
            {
                type: 'slider', xAxisIndex: [0, 1],
                top: '92%', height: 16, borderColor: 'transparent',
                textStyle: { color: '#4b5563', fontSize: 8 },
                handleSize: '80%',
                start: 70, end: 100
            }
        ],
        grid: [
            { top: 10, left: 5, right: 45, height: '60%', containLabel: true },
            { top: '72%', left: 5, right: 45, height: '18%', containLabel: true }
        ],
        xAxis: [
            {
                type: 'category', gridIndex: 0, data: timeLabels,
                axisLine: { lineStyle: { color: '#1f2937' } },
                axisLabel: { show: false }
            },
            {
                type: 'category', gridIndex: 1, data: timeLabels,
                axisLine: { lineStyle: { color: '#1f2937' } },
                axisLabel: { color: '#4b5563', fontSize: 8 }
            }
        ],
        yAxis: [
            {
                scale: true, position: 'right', gridIndex: 0,
                splitLine: { lineStyle: { color: '#111827' } },
                axisLabel: { color: '#6b7280', fontSize: 9 },
                boundaryGap: ['5%', '5%']
            },
            {
                scale: false, min: 0, position: 'right', gridIndex: 1,
                splitLine: { show: false },
                axisLabel: { show: false }
            }
        ],
        series: [
            {
                type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
                markArea: {
                    silent: true,
                    data: areas.map(a => [{ xAxis: a.xAxis }, { xAxis: a.xAxis + 1, itemStyle: a.itemStyle }])
                },
                data: data.map(d => [d.open, d.close, d.low, d.high]),
                itemStyle: {
                    // Apply RVOL-based colors to candles (Requirement #2)
                    color: (p) => colors[p.dataIndex],
                    color0: (p) => colors[p.dataIndex],
                    borderColor: (p) => colors[p.dataIndex],
                    borderColor0: (p) => colors[p.dataIndex]
                }
            },
            {
                name: 'Volume', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
                data: volumes,
                itemStyle: {
                    color: (p) => colors[p.dataIndex],
                    opacity: 0.8
                }
            },
            {
                name: 'EVWMA', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: evwma, showSymbol: false,
                lineStyle: { width: 1, color: '#3b82f6', opacity: 0.8 }
            },
            {
                name: 'DynPivot', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: dynPivot, showSymbol: false,
                lineStyle: { width: 1, color: '#ef4444', opacity: 0.8 }
            },
            {
                name: 'SwingHigh', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: swings.lastSH, showSymbol: false,
                lineStyle: { width: 1, type: 'dotted', color: '#f87171', opacity: 0.5 }
            },
            {
                name: 'SwingLow', type: 'line', xAxisIndex: 0, yAxisIndex: 0, data: swings.lastSL, showSymbol: false,
                lineStyle: { width: 1, type: 'dotted', color: '#4ade80', opacity: 0.5 }
            },
            {
                type: 'scatter', xAxisIndex: 0, yAxisIndex: 0, data: mtf2Dots.supp, symbol: 'circle', symbolSize: 4,
                itemStyle: { color: 'rgba(59, 130, 246, 0.6)' }
            },
            {
                type: 'scatter', xAxisIndex: 0, yAxisIndex: 0, data: mtf2Dots.rest, symbol: 'circle', symbolSize: 4,
                itemStyle: { color: 'rgba(249, 115, 22, 0.6)' }
            },
            {
                type: 'scatter', xAxisIndex: 0, yAxisIndex: 0, data: mtf3Dots.supp, symbol: 'diamond', symbolSize: 6,
                itemStyle: { color: 'rgba(59, 130, 246, 0.9)' }
            },
            {
                type: 'scatter', xAxisIndex: 0, yAxisIndex: 0, data: mtf3Dots.rest, symbol: 'diamond', symbolSize: 6,
                itemStyle: { color: 'rgba(249, 115, 22, 0.9)' }
            },
            {
                type: 'scatter', xAxisIndex: 0, yAxisIndex: 0,
                data: bubbles.map(b => [b.index, b.isUp ? data[b.index].low : data[b.index].high]),
                symbolSize: (v, p) => {
                    const b = bubbles.find(x => x.index === p.dataIndex);
                    return b ? b.size * 5 : 0;
                },
                itemStyle: {
                    color: (p) => {
                        const b = bubbles.find(x => x.index === p.dataIndex);
                        return b && b.isUp ? 'rgba(59, 130, 246, 0.4)' : 'rgba(239, 68, 68, 0.4)';
                    }
                }
            }
        ],
        markLine: {
            symbol: 'none',
            data: mtfData.lines.map(l => ({
                yAxis: l.price,
                lineStyle: { color: l.isUp ? 'rgba(59, 130, 246, 0.3)' : 'rgba(239, 68, 68, 0.3)', width: l.step >= 8 ? 2 : 1 }
            }))
        }
    };

    chart.setOption(options);
}

function mapMTFTo1M(data1m, dataMTF, mtfRes) {
    const supp = [], rest = [];
    data1m.forEach((d, i) => {
        const ts = new Date(d.timestamp).getTime();
        // Find latest MTF candle BEFORE or AT this timestamp
        let latestIdx = -1;
        for (let j = 0; j < dataMTF.length; j++) {
            if (new Date(dataMTF[j].timestamp).getTime() <= ts) latestIdx = j;
            else break;
        }
        if (latestIdx !== -1) {
            if (mtfRes.supp[latestIdx]) supp.push([i, mtfRes.supp[latestIdx]]);
            if (mtfRes.rest[latestIdx]) rest.push([i, mtfRes.rest[latestIdx]]);
        }
    });
    return { supp, rest };
}

function renderPcrChart() {
    if (!pcrData.length) return;
    const options = {
        backgroundColor: 'transparent',
        animation: false,
        dataZoom: [
            { type: 'inside' },
            { type: 'slider', bottom: 0, height: 16 }
        ],
        grid: { top: 10, left: 10, right: 50, bottom: 30, containLabel: true },
        xAxis: {
            type: 'category',
            data: pcrData.map(d => new Date(d.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })),
            axisLine: { lineStyle: { color: '#374151' } },
            axisLabel: { color: '#6b7280', fontSize: 9 }
        },
        yAxis: {
            scale: true,
            position: 'right',
            splitLine: { lineStyle: { color: '#111827' } },
            axisLabel: { color: '#6b7280', fontSize: 9 }
        },
        series: [{
            type: 'line',
            data: pcrData.map(d => d.pcr),
            smooth: true,
            showSymbol: false,
            lineStyle: { color: '#8b5cf6', width: 2 },
            areaStyle: {
                color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
                    { offset: 0, color: 'rgba(139, 92, 246, 0.3)' },
                    { offset: 1, color: 'rgba(139, 92, 246, 0)' }
                ])
            }
        }]
    };
    charts.pcr.setOption(options);
}

// --- Helpers ---

function setLoading(show) {
    document.getElementById('loading').classList.toggle('hidden', !show);
}

function updateAtmStrike(price) {
    const step = currentIndex === 'NIFTY' ? 50 : 100;
    currentAtm = Math.round(price / step) * step;
    document.getElementById('atmStrike').innerText = currentAtm;
}

function switchIndex(val) {
    currentIndex = val;
    currentAtm = 0;
    indexData = []; ceData = []; peData = []; pcrData = [];
    atmKeys = { ce: '', pe: '' };
    loadInitialData();
}

async function fetchReplayDates() {
    const res = await fetch('/api/replay/dates');
    const dates = await res.json();
    const select = document.getElementById('replayDateSelect');
    dates.forEach(d => {
        const opt = document.createElement('option');
        opt.value = d;
        opt.innerText = d;
        select.appendChild(opt);
    });

    select.addEventListener('change', (e) => {
        if (e.target.value) {
            isReplay = true;
            replayDate = e.target.value;
            switchIndex(currentIndex);
        } else {
            isReplay = false;
            replayDate = '';
            socket.emit('stop_replay', {});
            switchIndex(currentIndex);
        }
    });
}

document.getElementById('replayBtn').addEventListener('click', () => {
    if (isReplay && replayDate) {
        socket.emit('start_replay', { date: replayDate, instrument_keys: [currentIndex], speed: 2.0 });
    }
});

init();
