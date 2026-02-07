/**
 * PRODESK Multi-Chart Application
 * Handles Socket.IO connection and multiple TradingView Lightweight Charts instances.
 */

const socket = io();

// --- ChartInstance Class ---
class ChartInstance {
    constructor(containerId, index) {
        this.containerId = containerId;
        this.index = index;
        this.symbol = 'NSE:NIFTY';
        this.interval = '1';
        this.chart = null;
        this.candleSeries = null;
        this.volumeSeries = null;
        this.indicatorSeries = {};
        this.lastCandle = null;
        this.fullHistory = { candles: [], volume: [] };
        this.drawings = [];
        this.markers = [];
        this.showIndicators = true;
        this.hiddenPlots = new Set();

        // Replay State
        this.isReplayMode = false;
        this.replayIndex = -1;
        this.isPlaying = false;
        this.replayInterval = null;

        this.initChart();
    }

    initChart() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        this.chart = LightweightCharts.createChart(container, {
            layout: { background: { type: 'solid', color: '#000000' }, textColor: '#d1d5db' },
            grid: { vertLines: { color: '#111827' }, horzLines: { color: '#111827' } },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            localization: {
                locale: 'en-IN',
                timeFormatter: (ts) => new Intl.DateTimeFormat('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(ts * 1000))
            },
            rightPriceScale: { borderColor: '#1f2937', autoScale: true, scaleMargins: { top: 0.1, bottom: 0.1 } },
            timeScale: { borderColor: '#1f2937', timeVisible: true, secondsVisible: false }
        });

        this.candleSeries = this.chart.addCandlestickSeries({
            upColor: '#22c55e', downColor: '#ef4444', borderVisible: true, wickUpColor: '#22c55e', wickDownColor: '#ef4444'
        });

        this.volumeSeries = this.chart.addHistogramSeries({
            color: '#3b82f6', priceFormat: { type: 'volume' }, priceScaleId: 'volume'
        });

        this.chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 }, visible: false
        });

        this.chart.subscribeClick((param) => {
            if (this.isReplayMode && param.time && this.replayIndex === -1) {
                const idx = this.fullHistory.candles.findIndex(c => c.time === param.time);
                if (idx !== -1) {
                    this.replayIndex = idx;
                    this.stepReplay(0);
                    updateReplayUI(this);
                }
            } else if (param.price) {
                const hlineBtn = document.getElementById('drawingToolBtn');
                const isHlineActive = hlineBtn && hlineBtn.classList.contains('bg-blue-600');
                if (isHlineActive || (window.event && window.event.shiftKey)) {
                    this.addHorizontalLine(param.price);
                }
            }
        });

        // Handle focus
        container.parentElement.addEventListener('mousedown', () => {
            setActiveChart(this);
        });
    }

    async switchSymbol(symbol, interval = null) {
        if (symbol) this.symbol = symbol;
        if (interval) this.interval = interval;

        this.lastCandle = null;
        this.fullHistory = { candles: [], volume: [] };

        this.candleSeries.setData([]);
        this.volumeSeries.setData([]);
        this.candleSeries.setMarkers([]);
        Object.values(this.indicatorSeries).forEach(s => this.chart.removeSeries(s));
        this.indicatorSeries = {};

        setLoading(true);
        try {
            const resData = await fetchIntraday(this.symbol, this.interval);
            let candles = resData.candles || [];

            // Filter market hours for NSE
            if (candles.length > 0 && this.symbol.startsWith('NSE:') && !['D', 'W'].includes(this.interval)) {
                const todayIST = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: 'numeric', day: 'numeric' }).format(new Date());
                candles = candles.filter(c => {
                    const ts = typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000);
                    const date = new Date(ts * 1000);
                    const dateIST = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: 'numeric', day: 'numeric' }).format(date);
                    if (dateIST !== todayIST) return true;
                    const istTime = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', hour: 'numeric', minute: 'numeric', hourCycle: 'h23' }).format(date);
                    const [h, m] = istTime.split(':').map(Number);
                    const mins = h * 60 + m;
                    return mins >= 555 && mins <= 930;
                });
            }

            if (candles.length > 0) {
                const chartData = candles.map(c => ({
                    time: typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000),
                    open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close), volume: Number(c.volume)
                })).filter(c => !isNaN(c.open) && c.open > 0).sort((a, b) => a.time - b.time);

                this.fullHistory.candles = chartData;
                this.lastCandle = chartData[chartData.length - 1];

                const volData = candles.map(c => ({
                    time: typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000),
                    value: Number(c.volume),
                    color: Number(c.close) >= Number(c.open) ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                })).sort((a, b) => a.time - b.time);
                this.fullHistory.volume = volData;

                this.renderData();

                const lastIdx = this.fullHistory.candles.length - 1;
                this.chart.timeScale().setVisibleLogicalRange({ from: lastIdx - 100, to: lastIdx + 5 });
            }

            if (resData.indicators) {
                this.handleChartUpdate({ indicators: resData.indicators });
                Object.values(this.indicatorSeries).forEach(s => s.applyOptions({ visible: this.showIndicators }));
            }

            socket.emit('subscribe', { instrumentKeys: [this.symbol], interval: this.interval });
            updateActiveChartLabel();
        } catch (e) {
            console.error("Switch symbol failed:", e);
        } finally {
            setLoading(false);
            saveLayout();
        }
    }

    renderData() {
        if (this.fullHistory.candles.length === 0) return;
        let displayCandles = [...this.fullHistory.candles].sort((a, b) => a.time - b.time);
        if (!displayCandles.some(c => c.hasExplicitColor)) {
            displayCandles = applyRvolColoring(displayCandles);
        }
        this.candleSeries.setData(displayCandles);
        this.volumeSeries.setData([...this.fullHistory.volume].sort((a, b) => a.time - b.time));
    }

    updateRealtimeCandle(quote) {
        if (!this.candleSeries || this.isReplayMode) return;
        const intervalMap = { '1': 60, '5': 300, '15': 900, '30': 1800, '60': 3600, 'D': 86400 };
        const duration = intervalMap[this.interval] || 60;
        const tickTime = Math.floor(quote.ts_ms / 1000);
        const candleTime = tickTime - (tickTime % duration);
        const price = Number(quote.last_price);
        if (isNaN(price) || price <= 0) return;
        const ltq = Number(quote.ltq || 0);

        if (!this.lastCandle || candleTime > this.lastCandle.time) {
            if (this.lastCandle && !this.fullHistory.candles.some(c => c.time === this.lastCandle.time)) {
                this.fullHistory.candles.push({ ...this.lastCandle });
                this.fullHistory.volume.push({
                    time: this.lastCandle.time, value: this.lastCandle.volume,
                    color: this.lastCandle.close >= this.lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                });
            }
            this.lastCandle = { time: candleTime, open: price, high: price, low: price, close: price, volume: ltq };
            this.candleSeries.update(this.lastCandle);
            this.volumeSeries.update({ time: candleTime, value: ltq, color: 'rgba(59, 130, 246, 0.5)' });
        } else if (candleTime === this.lastCandle.time) {
            this.lastCandle.close = price;
            this.lastCandle.high = Math.max(this.lastCandle.high, price);
            this.lastCandle.low = Math.min(this.lastCandle.low, price);
            this.lastCandle.volume += ltq;
            this.candleSeries.update(this.lastCandle);
            this.volumeSeries.update({
                time: this.lastCandle.time, value: this.lastCandle.volume,
                color: this.lastCandle.close >= this.lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
            });
        }
    }

    handleChartUpdate(data) {
        if (data.ohlcv && data.ohlcv.length > 0) {
            const isTimestamp = data.ohlcv[0][0] > 1e9;
            if (isTimestamp) {
                const candles = data.ohlcv.map(v => ({
                    time: Math.floor(v[0]), open: Number(v[1]), high: Number(v[2]), low: Number(v[3]), close: Number(v[4])
                })).filter(c => !isNaN(c.open) && c.open > 0);
                const vol = data.ohlcv.map(v => ({
                    time: Math.floor(v[0]), value: Number(v[5]),
                    color: Number(v[4]) >= Number(v[1]) ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                }));

                if (candles.length > 1) {
                    this.fullHistory.candles = candles;
                    this.fullHistory.volume = vol;
                    this.lastCandle = { ...candles[candles.length - 1], volume: data.ohlcv[data.ohlcv.length - 1][5] };
                    this.renderData();
                } else if (candles.length === 1) {
                    const newCandle = candles[0];
                    const newVol = vol[0];
                    if (this.lastCandle && newCandle.time >= this.lastCandle.time) {
                        this.candleSeries.update(newCandle);
                        this.volumeSeries.update(newVol);
                        const idx = this.fullHistory.candles.findIndex(c => c.time === newCandle.time);
                        if (idx !== -1) { this.fullHistory.candles[idx] = newCandle; this.fullHistory.volume[idx] = newVol; }
                        else { this.fullHistory.candles.push(newCandle); this.fullHistory.volume.push(newVol); }
                        this.lastCandle = { ...newCandle, volume: newVol.value };
                    }
                }
            }
        }
        if (data.indicators && data.indicators.length > 0) {
            this.processIndicators(data.indicators);
        }
    }

    processIndicators(indicators) {
        const markers = [];
        const seriesUpdates = {};

        indicators.forEach(row => {
            const time = Math.floor(row.timestamp);
            if (row.Bar_Color !== undefined) {
                const candle = this.fullHistory.candles.find(c => c.time === time);
                if (candle) {
                    const color = tvColorToRGBA(row.Bar_Color);
                    candle.color = color; candle.wickColor = color; candle.borderColor = color; candle.hasExplicitColor = true;
                }
            }
            Object.entries(row).forEach(([key, val]) => {
                if (['timestamp', 'Bar_Color'].includes(key) || key.endsWith('_meta') || key.endsWith('_color')) return;
                if (val === null || val === undefined) return;

                const meta = row[`${key}_meta`];
                const color = tvColorToRGBA(row[`${key}_color`] || (meta ? meta.color : null)) || '#3b82f6';

                // Only treat as markers if explicitly a Bubble or identified marker type
                // The image shows that Support/Resistance levels (S/R) are being forced to markers
                // Let's only use markers for Bubble and things that aren't numeric levels if possible
                // Actually, if it has a numeric value, it's better as a line or scatter segment.

                if (meta && meta.title.includes('Bubble')) {
                    markers.push({ time, position: 'aboveBar', color, shape: 'circle', size: 2, text: '' });
                } else {
                    if (!seriesUpdates[key]) seriesUpdates[key] = { points: [], meta, color };
                    seriesUpdates[key].points.push({ time, value: val, color });
                }
            });
        });

        this.markers = markers;
        if (this.markers.length > 0) {
            this.markers.sort((a, b) => a.time - b.time);
        }
        this.candleSeries.setMarkers(this.showIndicators ? this.markers : []);

        let newlyAdded = false;
        Object.entries(seriesUpdates).forEach(([key, data]) => {
            if (!this.indicatorSeries[key]) {
                const meta = data.meta;
                const title = meta ? meta.title : key;
                this.indicatorSeries[key] = this.chart.addLineSeries({
                    title: title,
                    color: data.color,
                    lineWidth: meta ? (meta.linewidth || 1) : 1,
                    lineStyle: meta && meta.linestyle === 1 ? LightweightCharts.LineStyle.Dashed : LightweightCharts.LineStyle.Solid,
                    priceScaleId: 'right',
                    autoscaleInfoProvider: () => null,
                    visible: this.showIndicators && !this.hiddenPlots.has(key),
                    axisLabelVisible: false
                });
                newlyAdded = true;
            }
            data.points.sort((a, b) => a.time - b.time);
            this.indicatorSeries[key].setData(data.points);
        });

        if (newlyAdded && this.index === activeChartIndex) {
            if (!document.getElementById('indicatorPanel').classList.contains('hidden')) {
                populateIndicatorList();
            }
        }
    }

    stepReplay(delta) {
        const newIdx = this.replayIndex + delta;
        if (newIdx >= 0 && newIdx < this.fullHistory.candles.length) {
            this.replayIndex = newIdx;
            const vC = this.fullHistory.candles.slice(0, this.replayIndex + 1);
            const vV = this.fullHistory.volume.slice(0, this.replayIndex + 1);
            this.candleSeries.setData(vC);
            this.volumeSeries.setData(vV);
            this.lastCandle = { ...vC[vC.length - 1] };
        }
    }

    addHorizontalLine(price, color = '#3b82f6') {
        const line = this.candleSeries.createPriceLine({
            price: price, color: color, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: true, title: 'HLINE'
        });
        this.drawings.push({ type: 'hline', price, color, line });
        saveLayout();
    }

    clearDrawings() {
        this.drawings.forEach(d => {
            if (d.line) this.candleSeries.removePriceLine(d.line);
        });
        this.drawings = [];
        saveLayout();
    }

    destroy() {
        if (this.chart) {
            this.chart.remove();
            this.chart = null;
        }
    }
}

// --- Global State & Managers ---

let charts = [];
let activeChartIndex = 0;
let currentLayout = 1;

function init() {
    loadLayout();
    initLayoutSelector();
    initIndicatorPanel();
    initDrawingControls();
    initTimeframeUI();
    initSearch();
    initZoomControls();
    initReplayControls();
    initSocket();

    window.addEventListener('resize', () => {
        charts.forEach(c => c.chart.resize(document.getElementById(c.containerId).clientWidth, document.getElementById(c.containerId).clientHeight));
    });
}

function setActiveChart(chartInstance) {
    activeChartIndex = chartInstance.index;
    document.querySelectorAll('.chart-wrapper').forEach(w => w.classList.remove('active'));
    const activeWrapper = document.getElementById(chartInstance.containerId).parentElement;
    activeWrapper.classList.add('active');

    // Update header UI to reflect active chart state
    updateHeaderUI();
}

function updateHeaderUI() {
    const chart = charts[activeChartIndex];
    if (!chart) return;

    // Update timeframe buttons
    document.querySelectorAll('.tf-btn').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.interval === chart.interval);
    });

    // Update symbol search
    document.getElementById('symbolSearch').value = chart.symbol;

    // Update replay UI
    updateReplayUI(chart);
    updateActiveChartLabel();

    // Update indicator toggle button
    const indBtn = document.getElementById('toggleIndicatorsBtn');
    if (indBtn) {
        indBtn.innerText = chart.showIndicators ? 'HIDE ALL' : 'SHOW ALL';
        indBtn.classList.toggle('bg-blue-600', chart.showIndicators);
        indBtn.classList.toggle('bg-gray-800', !chart.showIndicators);
    }

    // Refresh indicator list if panel is open
    if (!document.getElementById('indicatorPanel').classList.contains('hidden')) {
        populateIndicatorList();
    }
}

function updateActiveChartLabel() {
    charts.forEach(c => {
        const wrapper = document.getElementById(c.containerId).parentElement;
        let label = wrapper.querySelector('.chart-label');
        if (!label) {
            label = document.createElement('div');
            label.className = 'chart-label';
            wrapper.appendChild(label);
        }
        label.innerText = `${c.symbol} (${c.interval}m)`;
    });
}

function setLayout(n) {
    currentLayout = n;
    const container = document.getElementById('chartsContainer');
    container.innerHTML = '';

    charts.forEach(c => c.destroy());
    charts = [];

    const rows = n === 4 ? 2 : 1;
    const cols = n === 1 ? 1 : 2;
    container.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
    container.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;

    for (let i = 0; i < n; i++) {
        const wrapper = document.createElement('div');
        wrapper.className = 'chart-wrapper';
        const chartDiv = document.createElement('div');
        chartDiv.id = `chart-${i}`;
        chartDiv.className = 'chart-container';
        wrapper.appendChild(chartDiv);
        container.appendChild(wrapper);

        const chartInstance = new ChartInstance(`chart-${i}`, i);
        charts.push(chartInstance);

        const saved = JSON.parse(localStorage.getItem(`chart_config_${i}`));
        if (saved) {
            chartInstance.symbol = saved.symbol || 'NSE:NIFTY';
            chartInstance.interval = saved.interval || '1';
            chartInstance.showIndicators = saved.showIndicators !== undefined ? saved.showIndicators : true;
            chartInstance.hiddenPlots = new Set(saved.hiddenPlots || []);
            chartInstance.switchSymbol(chartInstance.symbol, chartInstance.interval).then(() => {
                if (saved.drawings) {
                    saved.drawings.forEach(d => {
                        if (d.type === 'hline') chartInstance.addHorizontalLine(d.price, d.color);
                    });
                }
            });
        } else {
            chartInstance.switchSymbol('NSE:NIFTY', '1');
        }
    }

    setActiveChart(charts[0]);
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.classList.toggle('active', parseInt(btn.dataset.layout) === n);
    });
    saveLayout();
}

function initLayoutSelector() {
    document.querySelectorAll('.layout-btn').forEach(btn => {
        btn.addEventListener('click', () => setLayout(parseInt(btn.dataset.layout)));
    });
}

function initTimeframeUI() {
    document.querySelectorAll('.tf-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const chart = charts[activeChartIndex];
            if (chart && btn.dataset.interval !== chart.interval) {
                chart.switchSymbol(chart.symbol, btn.dataset.interval);
                updateHeaderUI();
            }
        });
    });
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
                const symbols = data.symbols || [];

                if (symbols.length > 0) displaySearchResults(symbols);
            } catch (err) { console.error("Search failed:", err); }
        }, 300);
    });
    document.addEventListener('click', (e) => { if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) resultsDiv.classList.add('hidden'); });
}

function displaySearchResults(symbols) {
    const resultsDiv = document.getElementById('searchResults');
    resultsDiv.innerHTML = '';
    if (symbols.length === 0) { resultsDiv.classList.add('hidden'); return; }
    symbols.forEach(s => {
        const item = document.createElement('div');
        item.className = 'search-item px-3 py-2 cursor-pointer border-b border-white/5 last:border-0';
        const isOption = s.type === 'option' || s.symbol.includes('CE') || s.symbol.includes('PE');
        item.innerHTML = `
            <div class="flex items-center justify-between">
                <div class="text-[11px] font-black text-blue-400 tracking-tight">${s.symbol}</div>
                ${isOption ? '<span class="text-[8px] bg-blue-500/20 text-blue-400 px-1 rounded">OPTION</span>' : ''}
            </div>
            <div class="text-[9px] text-gray-300 uppercase truncate mt-0.5 font-semibold">${s.description} <span class="text-gray-500 mx-1">|</span> <span class="text-blue-500/80">${s.exchange}</span></div>
        `;
        item.addEventListener('click', () => {
            const cleanSymbol = s.symbol.replace(/<\/?[^>]+(>|$)/g, "");
            const fullSymbol = s.exchange ? `${s.exchange}:${cleanSymbol}` : cleanSymbol;
            document.getElementById('symbolSearch').value = cleanSymbol;
            resultsDiv.classList.add('hidden');
            const chart = charts[activeChartIndex];
            if (chart) chart.switchSymbol(fullSymbol);
        });
        resultsDiv.appendChild(item);
    });
    resultsDiv.classList.remove('hidden');
}

function initSocket() {
    socket.on('connect', () => {
        console.log("Socket connected");
        charts.forEach(c => socket.emit('subscribe', { instrumentKeys: [c.symbol], interval: c.interval }));
    });
    socket.on('raw_tick', (data) => {
        for (const [key, quote] of Object.entries(data)) {
            const norm = normalizeSymbol(key);
            charts.forEach(c => {
                if (normalizeSymbol(c.symbol) === norm || c.symbol.toUpperCase() === key.toUpperCase()) {
                    c.updateRealtimeCandle(quote);
                }
            });
        }
    });
    socket.on('chart_update', (data) => {
        const updateHRN = data.instrumentKey;
        const updateInterval = data.interval;
        charts.forEach(c => {
            const matchesSymbol = !updateHRN || normalizeSymbol(c.symbol) === normalizeSymbol(updateHRN);
            const matchesInterval = !updateInterval || String(c.interval) === String(updateInterval);
            if (matchesSymbol && matchesInterval) {
                c.handleChartUpdate(data);
            }
        });
    });
}

async function fetchIntraday(key, interval) {
    try {
        const res = await fetch(`/api/tv/intraday/${encodeURIComponent(key)}?interval=${interval}`);
        const data = await res.json();
        if (data && data.candles && data.candles.length > 0) {
            data.candles = data.candles.map(c => ({
                timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
            })).reverse();
            return data;
        }
        return { candles: [], indicators: [] };
    } catch (err) {
        console.warn("Fetch intraday failed:", err);
        return { candles: [], indicators: [] };
    }
}

// --- Persistence ---

function saveLayout() {
    localStorage.setItem('prodesk_layout', currentLayout);
    charts.forEach((c, i) => {
        const config = {
            symbol: c.symbol,
            interval: c.interval,
            showIndicators: c.showIndicators,
            hiddenPlots: Array.from(c.hiddenPlots),
            drawings: c.drawings.map(d => ({ type: d.type, price: d.price, color: d.color }))
        };
        localStorage.setItem(`chart_config_${i}`, JSON.stringify(config));
    });
}

function loadLayout() {
    const savedLayout = localStorage.getItem('prodesk_layout');
    setLayout(savedLayout ? parseInt(savedLayout) : 1);
}

// --- Utils ---

function normalizeSymbol(sym) {
    if (!sym) return "";
    let s = String(sym).toUpperCase().trim();
    if (s.includes(':')) s = s.split(':')[1];
    if (s.includes('|')) s = s.split('|')[1];
    return s.split(' ')[0].replace("NIFTY 50", "NIFTY").replace("BANK NIFTY", "BANKNIFTY").replace("FIN NIFTY", "FINNIFTY");
}

function tvColorToRGBA(color) {
    if (color === null || color === undefined) return null;
    if (typeof color === 'string') return color;
    if (typeof color === 'number') {
        // TradingView uses ARGB or similar. If it's a negative number, it's often a bitmask.
        // Convert to unsigned
        const uColor = color >>> 0;
        const a = ((uColor >> 24) & 0xFF) / 255;
        const r = (uColor >> 16) & 0xFF;
        const g = (uColor >> 8) & 0xFF;
        const b = uColor & 0xFF;
        return `rgba(${r}, ${g}, ${b}, ${a === 0 ? 1 : a})`;
    }
    return null;
}

function applyRvolColoring(candles) {
    if (candles.length < 2) return candles;
    const volumes = candles.map(c => c.volume || 0);
    const period = Math.min(20, candles.length);
    const sma = [];
    for (let i = 0; i < candles.length; i++) {
        if (i < period - 1) { sma.push(null); continue; }
        let sum = 0; for (let j = 0; j < period; j++) sum += volumes[i - j];
        sma.push(sum / period);
    }
    return candles.map((c, i) => {
        const s = sma[i];
        if (!s || s === 0) return c;
        const volPct = c.volume / s;
        const isUp = c.close >= c.open;
        let cCol;
        if (volPct >= 3) cCol = isUp ? '#007504' : 'rgb(137, 1, 1)';
        else if (volPct >= 2) cCol = isUp ? 'rgb(3, 179, 9)' : '#d30101';
        else {
            let op = volPct >= 1.6 ? 0.9 : volPct >= 1.2 ? 0.7 : volPct >= 0.8 ? 0.4 : volPct >= 0.5 ? 0.2 : 0.1;
            cCol = `rgba(${isUp ? 3 : 211}, ${isUp ? 179 : 1}, ${isUp ? 9 : 1}, ${op})`;
        }
        return { ...c, color: cCol, wickColor: cCol, borderColor: cCol };
    });
}

function setLoading(show) {
    const loadingDom = document.getElementById('loading');
    if (loadingDom) loadingDom.classList.toggle('hidden', !show);
}

// --- Controls ---

function initZoomControls() {
    document.getElementById('zoomInBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (!chart) return;
        const ts = chart.chart.timeScale();
        ts.applyOptions({ barSpacing: Math.min(50, ts.options().barSpacing * 1.2) });
    });
    document.getElementById('zoomOutBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (!chart) return;
        const ts = chart.chart.timeScale();
        ts.applyOptions({ barSpacing: Math.max(0.1, ts.options().barSpacing / 1.2) });
    });
    document.getElementById('resetZoomBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (!chart) return;
        chart.chart.timeScale().reset();
        const lastIdx = chart.fullHistory.candles.length - 1;
        if (lastIdx >= 0) chart.chart.timeScale().setVisibleLogicalRange({ from: lastIdx - 100, to: lastIdx + 5 });
    });
}

function initIndicatorPanel() {
    document.getElementById('manageIndicatorsBtn').addEventListener('click', () => {
        const panel = document.getElementById('indicatorPanel');
        panel.classList.toggle('hidden');
        if (!panel.classList.contains('hidden')) {
            populateIndicatorList();
        }
    });
    document.getElementById('closeIndicatorPanel').addEventListener('click', () => {
        document.getElementById('indicatorPanel').classList.add('hidden');
    });
}

function populateIndicatorList() {
    const chart = charts[activeChartIndex];
    if (!chart) return;
    const list = document.getElementById('indicatorList');
    list.innerHTML = '';

    // Plots section
    const plotsHeader = document.createElement('div');
    plotsHeader.className = 'text-[9px] font-black text-gray-500 mb-2 mt-2 uppercase tracking-tighter';
    plotsHeader.innerText = 'Plots';
    list.appendChild(plotsHeader);

    Object.entries(chart.indicatorSeries).forEach(([key, series]) => {
        const title = series.options().title || key;
        const item = document.createElement('div');
        item.className = 'flex items-center justify-between bg-white/5 p-2 rounded-lg';

        const isHidden = chart.hiddenPlots.has(key);

        item.innerHTML = `
            <span class="text-[10px] font-bold text-gray-300 truncate mr-2">${title}</span>
            <button class="toggle-plot-btn text-[9px] font-black px-2 py-1 rounded ${isHidden ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}" data-key="${key}">
                ${isHidden ? 'HIDDEN' : 'VISIBLE'}
            </button>
        `;

        item.querySelector('.toggle-plot-btn').addEventListener('click', (e) => {
            if (chart.hiddenPlots.has(key)) {
                chart.hiddenPlots.delete(key);
                series.applyOptions({ visible: chart.showIndicators });
            } else {
                chart.hiddenPlots.add(key);
                series.applyOptions({ visible: false });
            }
            populateIndicatorList();
            saveLayout();
        });

        list.appendChild(item);
    });

    if (Object.keys(chart.indicatorSeries).length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-[10px] text-gray-500 italic mb-4';
        empty.innerText = 'No indicators loaded';
        list.appendChild(empty);
    }

    // Drawings section
    const drawingsHeader = document.createElement('div');
    drawingsHeader.className = 'text-[9px] font-black text-gray-500 mb-2 mt-4 uppercase tracking-tighter';
    drawingsHeader.innerText = 'Drawings';
    list.appendChild(drawingsHeader);

    chart.drawings.forEach((d, i) => {
        const item = document.createElement('div');
        item.className = 'flex items-center justify-between bg-white/5 p-2 rounded-lg mb-2';
        item.innerHTML = `
            <span class="text-[10px] font-bold text-blue-400 truncate mr-2">HLINE @ ${d.price.toFixed(2)}</span>
            <button class="remove-draw-btn text-[9px] font-black px-2 py-1 rounded bg-red-500/20 text-red-400">
                REMOVE
            </button>
        `;
        item.querySelector('.remove-draw-btn').addEventListener('click', () => {
            if (d.line) chart.candleSeries.removePriceLine(d.line);
            chart.drawings.splice(i, 1);
            populateIndicatorList();
            saveLayout();
        });
        list.appendChild(item);
    });

    if (chart.drawings.length === 0) {
        const empty = document.createElement('div');
        empty.className = 'text-[10px] text-gray-500 italic';
        empty.innerText = 'No drawings';
        list.appendChild(empty);
    }
}

function initDrawingControls() {
    document.getElementById('toggleIndicatorsBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (!chart) return;
        chart.showIndicators = !chart.showIndicators;
        Object.values(chart.indicatorSeries).forEach(s => {
            const key = Object.keys(chart.indicatorSeries).find(k => chart.indicatorSeries[k] === s);
            s.applyOptions({ visible: chart.showIndicators && !chart.hiddenPlots.has(key) });
        });
        chart.candleSeries.setMarkers(chart.showIndicators ? chart.markers : []);
        updateHeaderUI();
        saveLayout();
    });
    document.getElementById('drawingToolBtn').addEventListener('click', () => {
        const btn = document.getElementById('drawingToolBtn');
        const isActive = btn.classList.toggle('bg-blue-600');
        btn.classList.toggle('text-white', isActive);
        btn.classList.toggle('bg-gray-800', !isActive);
        btn.classList.toggle('text-gray-300', !isActive);
    });
    document.getElementById('clearDrawingsBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (chart) chart.clearDrawings();
    });
}

function initReplayControls() {
    document.getElementById('replayModeBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (!chart) return;
        chart.isReplayMode = true;
        document.getElementById('normalControls').classList.add('hidden');
        document.getElementById('replayControls').classList.remove('hidden');
        document.getElementById('replayStatus').innerText = 'SELECT START POINT';
        ['replayPlayBtn', 'replayNextBtn', 'replayPrevBtn'].forEach(id => document.getElementById(id).disabled = true);
    });
    document.getElementById('exitReplayBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (!chart) return;
        chart.isPlaying = false; chart.isReplayMode = false; chart.replayIndex = -1;
        if (chart.replayInterval) clearInterval(chart.replayInterval);
        document.getElementById('replayControls').classList.add('hidden');
        document.getElementById('normalControls').classList.remove('hidden');
        chart.renderData();
    });
    document.getElementById('replayNextBtn').addEventListener('click', () => charts[activeChartIndex].stepReplay(1));
    document.getElementById('replayPrevBtn').addEventListener('click', () => charts[activeChartIndex].stepReplay(-1));
    document.getElementById('replayPlayBtn').addEventListener('click', () => {
        const chart = charts[activeChartIndex];
        if (chart.isPlaying) {
            chart.isPlaying = false;
            if (chart.replayInterval) clearInterval(chart.replayInterval);
        } else {
            chart.isPlaying = true;
            chart.replayInterval = setInterval(() => {
                if (chart.replayIndex < chart.fullHistory.candles.length - 1) chart.stepReplay(1);
                else { chart.isPlaying = false; clearInterval(chart.replayInterval); updateReplayUI(chart); }
            }, 1000);
        }
        updateReplayUI(chart);
    });
}

function updateReplayUI(chart) {
    if (chart.index !== activeChartIndex) return;
    const isRep = chart.isReplayMode;
    document.getElementById('replayPlayBtn').disabled = !isRep || chart.replayIndex === -1;
    document.getElementById('replayNextBtn').disabled = !isRep || chart.replayIndex === -1;
    document.getElementById('replayPrevBtn').disabled = !isRep || chart.replayIndex === -1;
    document.getElementById('playIcon').classList.toggle('hidden', chart.isPlaying);
    document.getElementById('pauseIcon').classList.toggle('hidden', !chart.isPlaying);
    if (chart.replayIndex !== -1) {
        document.getElementById('replayStatus').innerText = `BAR ${chart.replayIndex + 1} / ${chart.fullHistory.candles.length}`;
    }
}

init();
