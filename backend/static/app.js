/**
 * PRODESK Simplified Application
 * Handles Socket.IO connection and TradingView Lightweight Charts rendering.
 */

const socket = io();

// UI State
let currentSymbol = 'NSE:NIFTY';
let currentInterval = '1';
let mainChart = null;
let candleSeries = null;
let volumeSeries = null;
let lastCandle = null;

// Indicator Series
let evwmaSeries = null;
let dynPivotSeries = null;
let swingHighSeries = null;
let swingLowSeries = null;
let srSuppSeries = null;
let srRestSeries = null;

// Replay State
let isReplayMode = false;
let fullHistory = { candles: [], volume: [] };
let replayIndex = -1;
let replayInterval = null;
let isPlaying = false;

// Settings State
const Settings = {
    theme: 'dark',
    coloredCandles: true,
    bubbles: true,
    srDots: true,
    dynPivot: true,
    evwma: true,
    swings: true,

    save() { localStorage.setItem('prodesk_settings', JSON.stringify(this)); },
    load() {
        const saved = localStorage.getItem('prodesk_settings');
        if (saved) Object.assign(this, JSON.parse(saved));
    }
};

// --- Initialization ---

function init() {
    Settings.load();
    initTimeframeUI();
    const chartContainer = document.getElementById('mainChart');
    if (chartContainer) {
        mainChart = LightweightCharts.createChart(chartContainer, {
            width: chartContainer.clientWidth,
            height: chartContainer.clientHeight,
            layout: {
                background: { type: 'solid', color: '#000000' },
                textColor: '#d1d5db',
            },
            grid: {
                vertLines: { color: '#111827' },
                horzLines: { color: '#111827' },
            },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            rightPriceScale: {
                borderColor: '#1f2937',
                autoScale: true,
                scaleMargins: {
                    top: 0.1,
                    bottom: 0.1,
                },
            },
            timeScale: { borderColor: '#1f2937', timeVisible: true, secondsVisible: false },
        });

        candleSeries = mainChart.addCandlestickSeries({
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
        });

        volumeSeries = mainChart.addHistogramSeries({
            color: '#3b82f6',
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
        });

        mainChart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 },
            visible: false,
        });

        // Initialize indicator series with autoscaleInfoProvider to ignore them for Y-axis scaling
        const indicatorOptions = { autoscaleInfoProvider: () => null };

        evwmaSeries = mainChart.addLineSeries({ color: '#10b981', lineWidth: 2, title: 'EVWMA', ...indicatorOptions });
        dynPivotSeries = mainChart.addLineSeries({ color: '#3b82f6', lineWidth: 2, title: 'DynPivot', ...indicatorOptions });
        swingHighSeries = mainChart.addLineSeries({ color: '#ef4444', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dotted, ...indicatorOptions });
        swingLowSeries = mainChart.addLineSeries({ color: '#3b82f6', lineWidth: 1, lineStyle: LightweightCharts.LineStyle.Dotted, ...indicatorOptions });

        srSuppSeries = mainChart.addLineSeries({ color: '#3b82f6', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.SparseDotted, ...indicatorOptions });
        srRestSeries = mainChart.addLineSeries({ color: '#f59e0b', lineWidth: 2, lineStyle: LightweightCharts.LineStyle.SparseDotted, ...indicatorOptions });

        window.addEventListener('resize', () => {
            mainChart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
        });

        mainChart.subscribeClick((param) => {
            if (isReplayMode && param.time && replayIndex === -1) {
                const index = fullHistory.candles.findIndex(c => c.time === param.time);
                if (index !== -1) {
                    replayIndex = index;
                    stepReplay(0);
                    document.getElementById('replayPlayBtn').disabled = false;
                    document.getElementById('replayNextBtn').disabled = false;
                    document.getElementById('replayPrevBtn').disabled = false;
                }
            }
        });
    }

    initSocket();
    initSearch();
    initZoomControls();
    initReplayControls();
    initSettingsUI();
    applyTheme();
    switchSymbol(currentSymbol);
}

function initTimeframeUI() {
    const btns = document.querySelectorAll('.tf-btn');
    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.dataset.interval === currentInterval) return;

            btns.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');

            currentInterval = btn.dataset.interval;
            switchSymbol(currentSymbol);
        });
    });
}

function initSettingsUI() {
    const settingsBtn = document.getElementById('settingsBtn');
    const settingsPanel = document.getElementById('settingsPanel');
    const closeSettingsBtn = document.getElementById('closeSettingsBtn');
    const themeToggleBtn = document.getElementById('themeToggleBtn');

    settingsBtn.addEventListener('click', () => settingsPanel.classList.toggle('hidden'));
    closeSettingsBtn.addEventListener('click', () => settingsPanel.classList.add('hidden'));

    themeToggleBtn.addEventListener('click', () => {
        Settings.theme = Settings.theme === 'dark' ? 'light' : 'dark';
        applyTheme();
        Settings.save();
        renderIndicators();
    });

    const toggles = [
        { id: 'checkColoredCandles', key: 'coloredCandles' },
        { id: 'checkBubbles', key: 'bubbles' },
        { id: 'checkSRDots', key: 'srDots' },
        { id: 'checkDynPivot', key: 'dynPivot' },
        { id: 'checkEVWMA', key: 'evwma' },
        { id: 'checkSwings', key: 'swings' }
    ];

    toggles.forEach(t => {
        const el = document.getElementById(t.id);
        el.checked = Settings[t.key];
        el.addEventListener('change', (e) => {
            Settings[t.key] = e.target.checked;
            Settings.save();
            renderIndicators();
        });
    });
}

function applyTheme() {
    const isDark = Settings.theme === 'dark';
    const colors = isDark ? {
        bg: '#000000', text: '#d1d5db', grid: '#111827', border: '#1f2937'
    } : {
        bg: '#ffffff', text: '#111827', grid: '#f3f4f6', border: '#e5e7eb'
    };

    if (mainChart) {
        mainChart.applyOptions({
            layout: { background: { color: colors.bg }, textColor: colors.text },
            grid: { vertLines: { color: colors.grid }, horzLines: { color: colors.grid } },
        });
        mainChart.priceScale('right').applyOptions({ borderColor: colors.border });
        mainChart.timeScale().applyOptions({ borderColor: colors.border });
    }
    document.body.classList.toggle('light-theme', !isDark);
    const btn = document.getElementById('themeToggleBtn');
    if (btn) btn.innerText = isDark ? 'DARK MODE' : 'LIGHT MODE';
}

function initSearch() {
    const searchInput = document.getElementById('symbolSearch');
    const resultsDiv = document.getElementById('searchResults');
    let debounceTimer;

    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const text = e.target.value.trim();
        if (text.length < 2) { resultsDiv.classList.add('hidden'); return; }

        debounceTimer = setTimeout(async () => {
            try {
                const res = await fetch(`/api/tv/search?text=${encodeURIComponent(text)}`);
                const data = await res.json();
                if (data && data.symbols) displaySearchResults(data.symbols);
            } catch (err) { console.error("Search failed:", err); }
        }, 300);
    });

    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) resultsDiv.classList.add('hidden');
    });
}

function displaySearchResults(symbols) {
    const resultsDiv = document.getElementById('searchResults');
    resultsDiv.innerHTML = '';
    if (symbols.length === 0) { resultsDiv.classList.add('hidden'); return; }
    symbols.forEach(s => {
        const item = document.createElement('div');
        item.className = 'search-item px-3 py-2 hover:bg-gray-800 cursor-pointer border-b border-gray-800 last:border-0';
        item.innerHTML = `
            <div class="text-[10px] font-black text-blue-400">${s.symbol}</div>
            <div class="text-[8px] text-gray-500 uppercase truncate">${s.description} | ${s.exchange}</div>
        `;
        item.addEventListener('click', () => {
            const cleanSymbol = s.symbol.replace(/<\/?[^>]+(>|$)/g, "");
            const fullSymbol = s.exchange ? `${s.exchange}:${cleanSymbol}` : cleanSymbol;
            document.getElementById('symbolSearch').value = cleanSymbol;
            resultsDiv.classList.add('hidden');
            switchSymbol(fullSymbol);
        });
        resultsDiv.appendChild(item);
    });
    resultsDiv.classList.remove('hidden');
}

async function switchSymbol(symbol) {
    currentSymbol = symbol;
    lastCandle = null;
    setLoading(true);
    try {
        const candles = await fetchIntraday(currentSymbol, currentInterval);
        console.log(`Fetched ${candles ? candles.length : 0} candles for ${currentSymbol}`);
        if (candles && candles.length > 0) {
            const chartData = candles.map(c => ({
                time: Math.floor(new Date(c.timestamp).getTime() / 1000),
                open: c.open, high: c.high, low: c.low, close: c.close
            })).sort((a, b) => a.time - b.time);
            const volData = candles.map(c => ({
                time: Math.floor(new Date(c.timestamp).getTime() / 1000),
                value: c.volume,
                color: c.close >= c.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
            })).sort((a, b) => a.time - b.time);
            fullHistory = { candles: chartData, volume: volData };
            if (!isReplayMode) {
                renderIndicators();
                lastCandle = chartData[chartData.length - 1];
                lastCandle.volume = candles[candles.length - 1].volume;
            } else document.getElementById('exitReplayBtn').click();

            // Set visible range to last 100 bars instead of fitContent
            const lastIndex = chartData.length - 1;
            mainChart.timeScale().setVisibleLogicalRange({
                from: lastIndex - 100,
                to: lastIndex + 5,
            });
        } else {
            console.warn("No candles returned, generating mock data for demo.");
            generateMockData();
            renderIndicators();
        }
        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    } catch (e) {
        console.error("Switch symbol failed:", e);
        if (currentSymbol === 'NSE:NIFTY' || currentSymbol.includes('BTCUSD')) {
            generateMockData(); renderIndicators();
        }
    } finally { setLoading(false); }
}

function generateMockData() {
    const now = Math.floor(Date.now() / 1000);
    const mockCandles = []; const mockVolume = []; let price = 25000;
    for (let i = 0; i < 200; i++) {
        const t = now - (200 - i) * 60;
        const o = price + Math.random() * 20 - 10;
        const c = o + Math.random() * 20 - 10;
        const h = Math.max(o, c) + Math.random() * 5;
        const l = Math.min(o, c) - Math.random() * 5;
        mockCandles.push({ time: t, open: o, high: h, low: l, close: c });
        mockVolume.push({ time: t, value: Math.random() * 10000, color: c >= o ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)' });
        price = c;
    }
    fullHistory = { candles: mockCandles, volume: mockVolume };
}

async function fetchIntraday(key, interval = '1') {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    let url = `/api/tv/intraday/${encodeURIComponent(key)}?interval=${interval}`;
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timeoutId);
    const data = await res.json();
    if (data && data.candles) {
        return data.candles.map(c => ({
            timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
        })).reverse();
    }
    return [];
}

function initSocket() {
    socket.on('connect', () => socket.emit('subscribe', { instrumentKeys: [currentSymbol] }));
    socket.on('raw_tick', (data) => handleTickUpdate(typeof data === 'string' ? JSON.parse(data) : data));
}

function handleTickUpdate(quotes) {
    const currentNorm = normalizeSymbol(currentSymbol);
    for (const [key, quote] of Object.entries(quotes)) {
        if (normalizeSymbol(key) === currentNorm) { updateRealtimeCandle(quote); break; }
    }
}

function updateRealtimeCandle(quote) {
    if (!candleSeries || isReplayMode) return;

    // Map interval to duration in seconds
    const intervalMap = { '1': 60, '5': 300, '15': 900, '30': 1800, '60': 3600, 'D': 86400, 'W': 604800 };
    const duration = intervalMap[currentInterval] || 60;

    const tickTime = Math.floor(quote.ts_ms / 1000);
    const candleTime = tickTime - (tickTime % duration);
    const price = quote.last_price;
    const ltq = quote.ltq || 0;

    if (!lastCandle || candleTime > lastCandle.time) {
        if (lastCandle) {
            fullHistory.candles.push({...lastCandle});
            fullHistory.volume.push({
                time: lastCandle.time, value: lastCandle.volume,
                color: lastCandle.close >= lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
            });
        }
        lastCandle = { time: candleTime, open: price, high: price, low: price, close: price, volume: ltq };
        renderIndicators();
    } else {
        lastCandle.close = price;
        lastCandle.high = Math.max(lastCandle.high, price);
        lastCandle.low = Math.min(lastCandle.low, price);
        lastCandle.volume += ltq;
        candleSeries.update(lastCandle);
        volumeSeries.update({
            time: lastCandle.time, value: lastCandle.volume,
            color: lastCandle.close >= lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
        });
    }
}

// --- Indicators Engine ---

const Indicators = {
    sma(data, period) {
        let results = []; let sum = 0;
        for (let i = 0; i < data.length; i++) {
            sum += data[i]; if (i >= period) sum -= data[i - period];
            results.push(i >= period - 1 ? sum / period : null);
        }
        return results;
    },
    stdev(data, period) {
        let smas = this.sma(data, period); let results = [];
        for (let i = 0; i < data.length; i++) {
            if (smas[i] === null) { results.push(null); continue; }
            let sumSq = 0;
            for (let j = i - period + 1; j <= i; j++) sumSq += Math.pow(data[j] - smas[i], 2);
            results.push(Math.sqrt(sumSq / period));
        }
        return results;
    },
    calc(candles, volume) {
        const closes = candles.map(c => c.close);
        const opens = candles.map(c => c.open);
        const highs = candles.map(c => c.high);
        const lows = candles.map(c => c.low);
        const vols = volume.map(v => v.value);

        // 1. Colored Candles
        const volSma20 = this.sma(vols, 20);
        const candleColors = candles.map((c, i) => {
            if (!Settings.coloredCandles) return null;
            const volPercent = volSma20[i] ? vols[i] / volSma20[i] : 1;
            const up = c.close >= c.open;
            if (volPercent >= 3) return up ? '#007504' : '#890101';
            if (volPercent >= 2) return up ? '#03b309' : '#d30101';
            if (volPercent >= 1.6) return up ? '#03b309e6' : '#d30101e6';
            if (volPercent >= 1.2) return up ? '#03b309b3' : '#d30101b3';
            if (volPercent >= 0.8) return up ? '#03b30966' : '#d3010166';
            return up ? '#03b30933' : '#d3010133';
        });

        // 2. EVWMA (Length 5) - Fixed to handle zero volume and initial bars
        const evwma = [];
        let prevEv = candles[0]?.close || null;
        const evLen = 5;
        for (let i = 0; i < candles.length; i++) {
            let sumV = 0;
            for (let j = Math.max(0, i - evLen + 1); j <= i; j++) sumV += vols[j];

            if (sumV > 0 && vols[i] > 0) {
                if (prevEv === null) prevEv = candles[i].close;
                prevEv = (prevEv * (sumV - vols[i]) / sumV) + (vols[i] * candles[i].close / sumV);
            }

            if (prevEv !== null) {
                evwma.push({ time: candles[i].time, value: prevEv });
            }
        }

        // 3. Dynamic Pivot (Force 20, Pivot 10)
        const dynPivot = [];
        const pivotLen = 10;
        const baseP = this.sma(highs.map((h, i) => candles[i].close >= candles[i].open ? h : lows[i]), pivotLen);
        for (let i = 0; i < candles.length; i++) {
            dynPivot.push({ time: candles[i].time, value: baseP[i] });
        }

        // 4. Swing Detection (Left 5, Right 2)
        const swingHighs = [], swingLows = [];
        for (let i = 5; i < candles.length - 2; i++) {
            let isH = true, isL = true;
            for (let j = i - 5; j <= i + 2; j++) {
                if (j === i) continue;
                if (highs[j] > highs[i]) isH = false;
                if (lows[j] < lows[i]) isL = false;
            }
            if (isH) swingHighs.push({ time: candles[i].time, value: highs[i] });
            if (isL) swingLows.push({ time: candles[i].time, value: lows[i] });
        }

        // 5. Bubbles & S/R
        const markers = []; const srSupp = []; const srRest = [];
        const volAvg100 = this.sma(vols, 100);
        const volAvg10 = this.sma(vols, 10);
        const volStd48 = this.stdev(vols, 48);
        const volAvg48 = this.sma(vols, 48);

        let lastSupp = null, lastRest = null;

        for (let i = 0; i < candles.length; i++) {
            // Bubbles
            if (Settings.bubbles) {
                const refV = (volAvg100[i] + volAvg10[i]) / 2;
                const bSize = vols[i] / (refV || 1);
                if (bSize > 2.5) {
                    markers.push({
                        time: candles[i].time,
                        position: candles[i].close > candles[i].open ? 'belowBar' : 'aboveBar',
                        color: candles[i].close > candles[i].open ? '#22c55e' : '#ef4444',
                        shape: 'circle', size: bSize > 5 ? 2 : 1
                    });
                }
            }
            // S/R Dots
            const cond = (vols[i] - volAvg48[i]) > 4 * volStd48[i];
            if (cond) {
                if (candles[i].close > candles[i].open) lastSupp = lows[i];
                else if (candles[i].close < candles[i].open) lastRest = highs[i];
            }
            if (lastSupp !== null) srSupp.push({ time: candles[i].time, value: lastSupp });
            if (lastRest !== null) srRest.push({ time: candles[i].time, value: lastRest });
        }

        return { candleColors, evwma, dynPivot, swingHighs, swingLows, markers, srSupp, srRest };
    }
};

function renderIndicators() {
    if (fullHistory.candles.length === 0) return;
    const data = Indicators.calc(fullHistory.candles, fullHistory.volume);

    const coloredData = fullHistory.candles.map((c, i) => ({
        ...c, color: data.candleColors[i] || undefined, wickColor: data.candleColors[i] || undefined,
    }));
    candleSeries.setData(coloredData);
    volumeSeries.setData(fullHistory.volume);

    evwmaSeries.setData(Settings.evwma ? data.evwma : []);
    dynPivotSeries.setData(Settings.dynPivot ? data.dynPivot : []);
    swingHighSeries.setData(Settings.swings ? data.swingHighs : []);
    swingLowSeries.setData(Settings.swings ? data.swingLows : []);
    srSuppSeries.setData(Settings.srDots ? data.srSupp : []);
    srRestSeries.setData(Settings.srDots ? data.srRest : []);
    candleSeries.setMarkers(data.markers);
}

// --- Utils & Controls ---

function normalizeSymbol(sym) {
    if (!sym) return "";
    let s = sym.toUpperCase().trim();
    if (s.includes(':')) s = s.split(':')[1];
    if (s.includes('|')) s = s.split('|')[1];
    if (s === "NIFTY 50") return "NIFTY";
    if (s === "BANK NIFTY") return "BANKNIFTY";
    if (s === "FIN NIFTY") return "FINNIFTY";
    if (s === "CNXFINANCE") return "FINNIFTY";
    return s.split(' ')[0];
}

function setLoading(show) {
    const loadingDom = document.getElementById('loading');
    if (loadingDom) loadingDom.classList.toggle('hidden', !show);
}

function initZoomControls() {
    const btns = { in: 'zoomInBtn', out: 'zoomOutBtn', res: 'resetZoomBtn' };
    document.getElementById(btns.in).addEventListener('click', () => {
        const ts = mainChart.timeScale(); ts.applyOptions({ barSpacing: ts.options().barSpacing * 1.2 });
    });
    document.getElementById(btns.out).addEventListener('click', () => {
        const ts = mainChart.timeScale(); ts.applyOptions({ barSpacing: ts.options().barSpacing * 0.8 });
    });
    document.getElementById(btns.res).addEventListener('click', () => mainChart.timeScale().fitContent());
}

function initReplayControls() {
    const btns = { mode: 'replayModeBtn', exit: 'exitReplayBtn', play: 'replayPlayBtn', next: 'replayNextBtn', prev: 'replayPrevBtn' };
    const panels = { norm: 'normalControls', rep: 'replayControls' };

    document.getElementById(btns.mode).addEventListener('click', () => {
        isReplayMode = true;
        document.getElementById(panels.norm).classList.add('hidden');
        document.getElementById(panels.rep).classList.remove('hidden');
        document.getElementById('replayStatus').innerText = 'SELECT START POINT';
        [btns.play, btns.next, btns.prev].forEach(b => document.getElementById(b).disabled = true);
    });

    document.getElementById(btns.exit).addEventListener('click', () => {
        stopReplay(); isReplayMode = false;
        document.getElementById(panels.rep).classList.add('hidden');
        document.getElementById(panels.norm).classList.remove('hidden');
        renderIndicators();
    });

    document.getElementById(btns.next).addEventListener('click', () => stepReplay(1));
    document.getElementById(btns.prev).addEventListener('click', () => stepReplay(-1));
    document.getElementById(btns.play).addEventListener('click', () => isPlaying ? pauseReplay() : startReplay());
}

function startReplay() {
    isPlaying = true;
    document.getElementById('playIcon').classList.add('hidden');
    document.getElementById('pauseIcon').classList.remove('hidden');
    replayInterval = setInterval(() => replayIndex < fullHistory.candles.length - 1 ? stepReplay(1) : pauseReplay(), 1000);
}

function pauseReplay() {
    isPlaying = false;
    document.getElementById('playIcon').classList.remove('hidden');
    document.getElementById('pauseIcon').classList.add('hidden');
    if (replayInterval) clearInterval(replayInterval);
}

function stopReplay() { pauseReplay(); replayIndex = -1; }

function stepReplay(delta) {
    const newIndex = replayIndex + delta;
    if (newIndex >= 0 && newIndex < fullHistory.candles.length) {
        replayIndex = newIndex;
        const vC = fullHistory.candles.slice(0, replayIndex + 1);
        const vV = fullHistory.volume.slice(0, replayIndex + 1);
        const data = Indicators.calc(vC, vV);
        const coloredData = vC.map((c, i) => ({ ...c, color: data.candleColors[i] || undefined, wickColor: data.candleColors[i] || undefined }));
        candleSeries.setData(coloredData);
        volumeSeries.setData(vV);
        evwmaSeries.setData(Settings.evwma ? data.evwma : []);
        dynPivotSeries.setData(Settings.dynPivot ? data.dynPivot : []);
        swingHighSeries.setData(Settings.swings ? data.swingHighs : []);
        swingLowSeries.setData(Settings.swings ? data.swingLows : []);
        candleSeries.setMarkers(data.markers);
        lastCandle = {...vC[vC.length - 1]};
        document.getElementById('replayStatus').innerText = `BAR ${replayIndex + 1} / ${fullHistory.candles.length}`;
    }
}

try { init(); } catch (e) { console.error("Initialization failed:", e); }
