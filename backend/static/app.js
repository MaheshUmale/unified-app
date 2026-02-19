/**
 * PRODESK Multi-Chart Engine v3.0
 * High-performance coordination of multiple TradingView Lightweight Charts.
 */

/**
 * @typedef {Object} ChartConfig
 * @property {string} symbol
 * @property {string} interval
 * @property {boolean} showIndicators
 * @property {string[]} hiddenPlots
 * @property {Object} colorOverrides
 * @property {string} chartType
 * @property {Array} drawings
 */

class DataManager {
    constructor(engine) {
        this.engine = engine;
        this.socket = io({ reconnectionAttempts: 5, timeout: 10000 });
        this.setupSocket();
    }

    setupSocket() {
        this.socket.on('connect', () => {
            console.log("[DataManager] Socket connected");
            this.engine.charts.forEach(c => this.subscribe(c.symbol, c.interval));
        });

        this.socket.on('raw_tick', (data) => {
            for (const [key, quote] of Object.entries(data)) {
                this.engine.charts.forEach(c => {
                    if (c.symbol.toUpperCase() === key.toUpperCase()) {
                        c.updateRealtimeCandle(quote);
                    }
                });
            }
        });

        this.socket.on('chart_update', (data) => {
            const key = (data.instrumentKey || "").toUpperCase();
            const interval = String(data.interval || "");
            this.engine.charts.forEach(c => {
                if (c.symbol.toUpperCase() === key && String(c.interval) === interval) {
                    c.handleChartUpdate(data);
                }
            });
        });
    }

    subscribe(symbol, interval) {
        this.socket.emit('subscribe', { instrumentKeys: [symbol], interval });
    }

    unsubscribe(symbol, interval) {
        this.socket.emit('unsubscribe', { instrumentKeys: [symbol], interval });
    }

    async fetchOIProfile(symbol) {
        try {
            const res = await fetch(`/api/options/chain/${encodeURIComponent(symbol)}/with-greeks`);
            return await res.json();
        } catch (e) {
            console.error("[DataManager] OI fetch failed:", e);
            return null;
        }
    }

    async fetchHistory(symbol, interval) {
        try {
            const res = await fetch(`/api/tv/intraday/${encodeURIComponent(symbol)}?interval=${interval}`);
            const data = await res.json();
            if (data && data.candles) {
                // API returns [ts, o, h, l, c, v] in descending or ascending order?
                // backend/api_server.py: data.candles.map(...).reverse() - wait, no.
                // In my refactored backend: sorted(tv_candles, key=lambda x: x[0])
                // So it's already sorted.
                return {
                    hrn: data.hrn || '',
                    candles: data.candles.map(c => ({
                        time: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
                    })),
                    indicators: data.indicators || []
                };
            }
        } catch (e) {
            console.error("[DataManager] Fetch failed:", e);
        }
        return { candles: [], indicators: [] };
    }
}

class ChartInstance {
    constructor(id, index, engine) {
        this.id = id;
        this.index = index;
        this.engine = engine;
        this.container = document.getElementById(id);

        // State
        this.symbol = 'NSE:NIFTY';
        this.interval = '1';
        this.chartType = 'candles';
        this.showIndicators = false;
        this.hiddenPlots = new Set();
        this.colorOverrides = {};
        this.fullHistory = { candles: new Map(), volume: new Map(), indicators: {} };
        this.markers = [];
        this.drawings = [];
        this.lastCandle = null;
        this.showOIProfile = false;
        this.oiLines = [];

        this.initChart();
    }

    initChart() {
        const isLight = document.body.classList.contains('light-theme');
        this.chart = LightweightCharts.createChart(this.container, {
            layout: {
                background: { type: 'solid', color: isLight ? '#f8fafc' : '#0f172a' },
                textColor: isLight ? '#1e293b' : '#d1d5db'
            },
            grid: {
                vertLines: { color: isLight ? '#f1f5f9' : 'rgba(255,255,255,0.05)' },
                horzLines: { color: isLight ? '#f1f5f9' : 'rgba(255,255,255,0.05)' }
            },
            timeScale: {
                rightOffset: 20,
                timeVisible: true,
                secondsVisible: false,
                borderColor: isLight ? '#e2e8f0' : 'rgba(255,255,255,0.1)',
                tickMarkFormatter: (time, tickMarkType, locale) => {
                    const date = new Date(time * 1000);
                    return date.toLocaleTimeString('en-IN', {
                        timeZone: 'Asia/Kolkata',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false
                    });
                }
            },
            localization: {
                timeFormatter: (time) => {
                    const date = new Date(time * 1000);
                    return date.toLocaleTimeString('en-IN', {
                        timeZone: 'Asia/Kolkata',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        hour12: false
                    });
                }
            },
            rightPriceScale: { borderColor: isLight ? '#e2e8f0' : 'rgba(255,255,255,0.1)' },
            crosshair: { mode: 0 }
        });

        this.setChartType(this.chartType);
        this.volumeSeries = this.chart.addHistogramSeries({
            priceFormat: { type: 'volume' },
            priceScaleId: 'volume',
            lastValueVisible: false,
            priceLineVisible: false
        });
        this.chart.priceScale('volume').applyOptions({ scaleMargins: { top: 0.8, bottom: 0 }, visible: false });

        this.container.addEventListener('mousedown', () => this.engine.setActiveChart(this.index));
        this.addLocalControls();

        // Horizontal line drawing support (Shift+Click)
        this.chart.subscribeClick((param) => {
            if (param.time && param.point) {
                const isHlineActive = document.getElementById('drawingToolBtn')?.classList.contains('bg-blue-600');
                if (isHlineActive || (param.sourceEvent && param.sourceEvent.shiftKey)) {
                    const price = this.mainSeries.coordinateToPrice(param.point.y);
                    if (price) this.addHorizontalLine(price);
                }
            }
        });
    }

    setChartType(type) {
        this.chartType = type;
        const data = Array.from(this.fullHistory.candles.values()).sort((a,b) => a.time - b.time);
        if (this.mainSeries) this.chart.removeSeries(this.mainSeries);

        const options = { lastValueVisible: false, priceLineVisible: false };
        if (type === 'candles') this.mainSeries = this.chart.addCandlestickSeries({ ...options, upColor: '#22c55e', downColor: '#ef4444' });
        else if (type === 'bars') this.mainSeries = this.chart.addBarSeries({ ...options, upColor: '#22c55e', downColor: '#ef4444' });
        else if (type === 'area') this.mainSeries = this.chart.addAreaSeries({ ...options, lineColor: '#3b82f6', topColor: 'rgba(59, 130, 246, 0.4)', bottomColor: 'transparent' });
        else this.mainSeries = this.chart.addLineSeries({ ...options, color: '#3b82f6' });

        if (data.length > 0) this.mainSeries.setData(data);
        this.applyMarkers();
    }

    async switchSymbol(symbol, interval) {
        if (this.symbol && this.interval) {
            this.engine.dataManager.unsubscribe(this.symbol, this.interval);
        }

        this.symbol = symbol.toUpperCase();
        this.interval = interval || this.interval;
        this.fullHistory = { candles: new Map(), volume: new Map(), indicators: {} };
        this.markers = [];
        this.indicatorSeries = this.indicatorSeries || {};
        Object.values(this.indicatorSeries).forEach(s => this.chart.removeSeries(s));
        this.indicatorSeries = {};

        this.engine.setLoading(true);
        const data = await this.engine.dataManager.fetchHistory(this.symbol, this.interval);
        this.engine.setLoading(false);

        if (data.candles.length > 0) {
            data.candles.forEach(c => this.fullHistory.candles.set(c.time, c));
            this.lastCandle = data.candles[data.candles.length - 1];
            this.renderData();
            this.chart.timeScale().fitContent();
        }

        if (data.indicators) {
            this.fullHistory.indicators_raw = data.indicators;
            this.applyIndicators(data.indicators);
        }
        if (this.showOIProfile) this.toggleOIProfile(true);

        this.engine.dataManager.subscribe(this.symbol, this.interval);
        this.engine.updateUI();
    }

    renderData() {
        const candles = Array.from(this.fullHistory.candles.values()).sort((a,b) => a.time - b.time);
        this.mainSeries.setData(candles);

        const volumes = candles.map(c => ({
            time: c.time, value: c.volume,
            color: c.close >= c.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
        }));
        this.volumeSeries.setData(volumes);
    }

    updateRealtimeCandle(quote) {
        const price = parseFloat(quote.last_price);
        if (isNaN(price) || price <= 0) return;

        const ts = Math.floor(quote.ts_ms / 1000);
        const duration = this.getIntervalSeconds();
        const candleTime = ts - (ts % duration);

        let ltq = parseInt(quote.ltq || 0);
        if (ltq < 0) ltq = 0;

        // Safeguard against extreme volume spikes (e.g. > 1M in a single tick for indices)
        const isIndex = this.symbol.includes('NIFTY') || this.symbol.includes('SENSEX') || this.symbol.includes('BANKEX');
        if (isIndex && ltq > 1000000) {
            console.warn(`[Chart] Extreme volume spike detected for ${this.symbol}: ${ltq}. Clamping to 0.`);
            ltq = 0;
        }

        if (!this.lastCandle || candleTime > this.lastCandle.time) {
            this.lastCandle = { time: candleTime, open: price, high: price, low: price, close: price, volume: ltq };
        } else {
            this.lastCandle.close = price;
            this.lastCandle.high = Math.max(this.lastCandle.high, price);
            this.lastCandle.low = Math.min(this.lastCandle.low, price);
            this.lastCandle.volume += ltq;
        }

        this.fullHistory.candles.set(this.lastCandle.time, { ...this.lastCandle });
        this.mainSeries.update(this.lastCandle);
        this.volumeSeries.update({
            time: this.lastCandle.time, value: this.lastCandle.volume,
            color: this.lastCandle.close >= this.lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
        });
    }

    handleChartUpdate(data) {
        if (data.ohlcv) {
            data.ohlcv.forEach(v => {
                const c = { time: v[0], open: v[1], high: v[2], low: v[3], close: v[4], volume: v[5] };
                this.fullHistory.candles.set(c.time, c);
                this.mainSeries.update(c);

                this.volumeSeries.update({
                    time: c.time, value: c.volume,
                    color: c.close >= c.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                });

                // Update lastCandle reference if this is a newer or current candle
                if (!this.lastCandle || c.time >= this.lastCandle.time) {
                    this.lastCandle = c;
                }
            });
        }
        if (data.indicators) {
            this.fullHistory.indicators_raw = data.indicators;
            this.applyIndicators(data.indicators);
        }
    }

    applyIndicators(indicators) {
        indicators.forEach(ind => {
            if (ind.type === 'markers') {
                const newMarkers = ind.data.map(m => ({
                    time: m.time, position: m.position, color: m.color, shape: m.shape, text: m.text
                }));

                // Merge markers, avoiding exact duplicates
                const existingTimes = new Set(this.markers.map(m => `${m.time}_${m.text}`));
                newMarkers.forEach(m => {
                    if (!existingTimes.has(`${m.time}_${m.text}`)) {
                        this.markers.push(m);
                    }
                });

                this.markers.sort((a, b) => a.time - b.time);
                this.applyMarkers();
                return;
            }

            if (!this.indicatorSeries[ind.id]) {
                const options = {
                    color: ind.style?.color || '#3b82f6',
                    lineWidth: ind.style?.lineWidth || 1,
                    lastValueVisible: false, priceLineVisible: false
                };
                this.indicatorSeries[ind.id] = this.chart.addLineSeries(options);
            }
            this.indicatorSeries[ind.id].setData(ind.data);
            this.indicatorSeries[ind.id].applyOptions({ visible: this.showIndicators && !this.hiddenPlots.has(ind.id) });
        });
    }

    applyMarkers() {
        this.mainSeries.setMarkers(this.showIndicators && !this.hiddenPlots.has('__markers__') ? this.markers : []);
    }

    addHorizontalLine(price, color = '#3b82f6') {
        const line = this.mainSeries.createPriceLine({
            price, color, lineWidth: 2, lineStyle: 2, axisLabelVisible: true, title: 'HLINE'
        });
        this.drawings.push({ price, color, line });
        this.engine.saveLayout();
    }

    getIntervalSeconds() {
        const m = {
            '1': 60, '3': 180, '5': 300, '15': 900, '30': 1800,
            '60': 3600, '120': 7200, '240': 14400, 'D': 86400, 'W': 604800
        };
        return m[this.interval] || 60;
    }

    async toggleOIProfile(visible) {
        this.showOIProfile = visible;
        this.oiLines.forEach(l => this.mainSeries.removePriceLine(l));
        this.oiLines = [];

        if (visible) {
            const data = await this.engine.dataManager.fetchOIProfile(this.symbol);
            if (data && data.chain && data.spot_price) {
                const spot = data.spot_price;
                const strikes = [...new Set(data.chain.map(c => c.strike))].sort((a, b) => a - b);

                let atmIdx = 0;
                let minDiff = Infinity;
                strikes.forEach((s, i) => {
                    const diff = Math.abs(s - spot);
                    if (diff < minDiff) { minDiff = diff; atmIdx = i; }
                });

                const start = Math.max(0, atmIdx - 10);
                const end = Math.min(strikes.length, atmIdx + 11);
                const targetStrikes = strikes.slice(start, end);

                targetStrikes.forEach(strike => {
                    const call = data.chain.find(c => c.strike === strike && c.option_type === 'call');
                    const put = data.chain.find(c => c.strike === strike && c.option_type === 'put');

                    if (call && call.oi > 0) {
                        this.oiLines.push(this.mainSeries.createPriceLine({
                            price: strike, color: 'rgba(239, 68, 68, 0.4)', lineWidth: 1, lineStyle: 0,
                            axisLabelVisible: true, title: `C-OI: ${(call.oi/1000000).toFixed(1)}M`
                        }));
                    }
                    if (put && put.oi > 0) {
                        this.oiLines.push(this.mainSeries.createPriceLine({
                            price: strike, color: 'rgba(34, 197, 94, 0.4)', lineWidth: 1, lineStyle: 0,
                            axisLabelVisible: true, title: `P-OI: ${(put.oi/1000000).toFixed(1)}M`
                        }));
                    }
                });
            }
        }
    }

    addLocalControls() {
        const wrapper = this.container.parentElement;
        const controls = document.createElement('div');
        controls.className = 'chart-controls';

        const zoomOut = document.createElement('button');
        zoomOut.className = 'chart-ctrl-btn';
        zoomOut.title = 'Zoom Out';
        zoomOut.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M20 12H4"/></svg>`;
        zoomOut.onclick = (e) => {
            e.stopPropagation();
            const ts = this.chart.timeScale();
            ts.applyOptions({ barSpacing: Math.max(0.5, ts.options().barSpacing / 1.2) });
        };

        const zoomIn = document.createElement('button');
        zoomIn.className = 'chart-ctrl-btn';
        zoomIn.title = 'Zoom In';
        zoomIn.innerHTML = `<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4"/></svg>`;
        zoomIn.onclick = (e) => {
            e.stopPropagation();
            const ts = this.chart.timeScale();
            ts.applyOptions({ barSpacing: Math.min(50, ts.options().barSpacing * 1.2) });
        };

        const reset = document.createElement('button');
        reset.className = 'chart-ctrl-btn';
        reset.title = 'Fit Content';
        reset.innerHTML = `<span class="text-[9px] font-black px-1">FIT</span>`;
        reset.onclick = (e) => { e.stopPropagation(); this.chart.timeScale().fitContent(); };

        controls.appendChild(zoomOut);
        controls.appendChild(reset);
        controls.appendChild(zoomIn);
        wrapper.appendChild(controls);
    }

    destroy() {
        if (this.chart) this.chart.remove();
    }
}

class ReplayController {
    constructor(engine) {
        this.engine = engine;
        this.isActive = false;
        this.isPlaying = false;
        this.currentIndex = 0;
        this.fullData = [];
        this.intervalId = null;
    }

    start(data) {
        this.isActive = true;
        this.fullData = data;
        this.currentIndex = Math.floor(data.length / 2);
        this.engine.charts[this.engine.activeIdx].mainSeries.setData(this.fullData.slice(0, this.currentIndex));
        this.updateUI();
    }

    togglePlay() {
        this.isPlaying = !this.isPlaying;
        if (this.isPlaying) {
            this.intervalId = setInterval(() => this.next(), 1000);
        } else {
            clearInterval(this.intervalId);
        }
        this.updateUI();
    }

    next() {
        if (this.currentIndex < this.fullData.length) {
            const candle = this.fullData[this.currentIndex++];
            this.engine.charts[this.engine.activeIdx].mainSeries.update(candle);
        } else {
            this.isPlaying = false;
            clearInterval(this.intervalId);
        }
        this.updateUI();
    }

    prev() {
        if (this.currentIndex > 1) {
            this.currentIndex--;
            this.engine.charts[this.engine.activeIdx].mainSeries.setData(this.fullData.slice(0, this.currentIndex));
        }
        this.updateUI();
    }

    exit() {
        this.isActive = false;
        this.isPlaying = false;
        clearInterval(this.intervalId);
        this.engine.charts[this.engine.activeIdx].renderData();
        this.updateUI();
    }

    updateUI() {
        const controls = document.getElementById('replayControls');
        const normal = document.getElementById('normalControls');
        controls.classList.toggle('hidden', !this.isActive);
        normal.classList.toggle('hidden', this.isActive);

        document.getElementById('playIcon').classList.toggle('hidden', this.isPlaying);
        document.getElementById('pauseIcon').classList.toggle('hidden', !this.isPlaying);
        document.getElementById('replayStatus').innerText = `REPLAY: ${this.currentIndex}/${this.fullData.length}`;

        ['replayPrevBtn', 'replayPlayBtn', 'replayNextBtn'].forEach(id => {
            const btn = document.getElementById(id);
            if (btn) btn.disabled = !this.isActive;
        });
    }
}

class MultiChartEngine {
    constructor() {
        this.charts = [];
        this.activeIdx = 0;
        this.layout = 1;
        this.dataManager = new DataManager(this);
        this.replay = new ReplayController(this);
        this.init();
    }

    init() {
        this.setupEventListeners();
        this.setupSearch();
        this.loadLayout();
        window.addEventListener('resize', () => {
            this.charts.forEach(c => c.chart.resize(c.container.clientWidth, c.container.clientHeight));
        });
    }

    setupSearch() {
        const searchInput = document.getElementById('symbolSearch');
        const resultsDiv = document.getElementById('searchResults');
        let debounceTimer;
        let selectedIndex = -1;

        searchInput.addEventListener('input', (e) => {
            clearTimeout(debounceTimer);
            const query = e.target.value.trim();
            if (query.length < 2) {
                resultsDiv.classList.add('hidden');
                return;
            }

            debounceTimer = setTimeout(async () => {
                try {
                    const res = await fetch(`/api/tv/search?text=${encodeURIComponent(query)}`);
                    const data = await res.json();
                    this.renderSearchResults(data.symbols || []);
                    selectedIndex = -1;
                } catch (err) {
                    console.error("[Search] Failed:", err);
                }
            }, 300);
        });

        searchInput.addEventListener('keydown', async (e) => {
            const items = resultsDiv.querySelectorAll('.search-item');

            if (e.key === 'ArrowDown') {
                e.preventDefault();
                selectedIndex = Math.min(selectedIndex + 1, items.length - 1);
                this.updateSearchSelection(items, selectedIndex);
            } else if (e.key === 'ArrowUp') {
                e.preventDefault();
                selectedIndex = Math.max(selectedIndex - 1, 0);
                this.updateSearchSelection(items, selectedIndex);
            } else if (e.key === 'Enter') {
                if (selectedIndex >= 0 && items[selectedIndex]) {
                    items[selectedIndex].click();
                } else {
                    const sym = searchInput.value.trim().toUpperCase();
                    if (sym) {
                        await this.charts[this.activeIdx].switchSymbol(sym);
                        this.saveLayout();
                        resultsDiv.classList.add('hidden');
                    }
                }
            } else if (e.key === 'Escape') {
                resultsDiv.classList.add('hidden');
            }
        });

        document.addEventListener('click', (e) => {
            if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
                resultsDiv.classList.add('hidden');
            }
        });
    }

    renderSearchResults(symbols) {
        const resultsDiv = document.getElementById('searchResults');
        if (!symbols.length) {
            resultsDiv.classList.add('hidden');
            return;
        }

        resultsDiv.innerHTML = symbols.map((s, i) => `
            <div class="search-item p-3 flex items-center justify-between cursor-pointer border-b border-white/5 hover:bg-blue-500/10 transition-colors"
                 data-symbol="${s.symbol}" data-exchange="${s.exchange}">
                <div class="flex flex-col">
                    <span class="text-xs font-black text-white">${s.symbol}</span>
                    <span class="text-[10px] text-gray-500 truncate max-w-[250px]">${s.description || ''}</span>
                </div>
                <div class="flex items-center gap-2">
                    <span class="text-[9px] font-bold px-1.5 py-0.5 rounded bg-gray-800 text-gray-400 uppercase border border-white/5">${s.exchange}</span>
                    <span class="text-[9px] font-black text-blue-500/70 uppercase italic tracking-tighter">${s.type || ''}</span>
                </div>
            </div>
        `).join('');

        resultsDiv.querySelectorAll('.search-item').forEach(item => {
            item.addEventListener('click', async () => {
                const sym = item.dataset.symbol;
                const exch = item.dataset.exchange;
                const fullSym = exch ? `${exch}:${sym}` : sym;

                document.getElementById('symbolSearch').value = fullSym;
                await this.charts[this.activeIdx].switchSymbol(fullSym);
                this.saveLayout();
                resultsDiv.classList.add('hidden');
            });
        });

        resultsDiv.classList.remove('hidden');
    }

    updateSearchSelection(items, index) {
        items.forEach((item, i) => {
            item.classList.toggle('bg-blue-500/20', i === index);
            if (i === index) item.scrollIntoView({ block: 'nearest' });
        });
    }

    setupEventListeners() {
        document.querySelectorAll('.layout-btn').forEach(btn => {
            btn.addEventListener('click', () => this.setLayout(parseInt(btn.dataset.layout)));
        });

        document.querySelectorAll('.tf-btn').forEach(btn => {
            btn.addEventListener('click', async () => {
                const c = this.charts[this.activeIdx];
                if (c) {
                    // Visual feedback
                    document.querySelectorAll('.tf-btn').forEach(b => b.classList.remove('active'));
                    btn.classList.add('active');
                    await c.switchSymbol(c.symbol, btn.dataset.interval);
                    this.saveLayout();
                }
            });
        });


        document.getElementById('chartTypeSelector').addEventListener('change', (e) => {
            this.charts[this.activeIdx].setChartType(e.target.value);
            this.saveLayout();
        });

        document.getElementById('oiProfileToggle').addEventListener('change', (e) => {
            this.charts.forEach(c => c.toggleOIProfile(e.target.checked));
        });

        document.getElementById('analysisToggle').addEventListener('change', (e) => {
            this.charts.forEach(c => {
                c.showIndicators = e.target.checked;
                if (c.fullHistory.indicators_raw) c.applyIndicators(c.fullHistory.indicators_raw);
                c.applyMarkers();
            });
        });


        document.getElementById('themeToggleBtn').addEventListener('click', () => {
            const isLight = document.body.classList.toggle('light-theme');
            localStorage.setItem('theme', isLight ? 'light' : 'dark');
            this.applyTheme();
        });

        // Replay Controls
        document.getElementById('replayModeBtn').addEventListener('click', async () => {
            const c = this.charts[this.activeIdx];
            const data = Array.from(c.fullHistory.candles.values()).sort((a,b) => a.time - b.time);
            this.replay.start(data);
        });

        document.getElementById('replayPlayBtn').addEventListener('click', () => this.replay.togglePlay());
        document.getElementById('replayNextBtn').addEventListener('click', () => this.replay.next());
        document.getElementById('replayPrevBtn').addEventListener('click', () => this.replay.prev());
        document.getElementById('exitReplayBtn').addEventListener('click', () => this.replay.exit());

        document.getElementById('maximizeBtn')?.addEventListener('click', () => {
            const c = this.charts[this.activeIdx];
            if (c) {
                const url = `/?symbol=${encodeURIComponent(c.symbol)}&interval=${c.interval}`;
                window.open(url, '_blank');
            }
        });
    }

    saveLayout() {
        if (window.INITIAL_CONFIG && window.INITIAL_CONFIG.symbol && window.INITIAL_CONFIG.symbol !== "None" && window.INITIAL_CONFIG.symbol !== "") {
            return; // Don't save if in single chart pop-out mode
        }
        localStorage.setItem('prodesk_layout', this.layout);
        this.charts.forEach((c, i) => {
            localStorage.setItem(`chart_config_${i}`, JSON.stringify({
                symbol: c.symbol, interval: c.interval, chartType: c.chartType
            }));
        });
    }

    setLayout(n) {
        this.layout = n;
        const container = document.getElementById('chartsContainer');
        container.innerHTML = '';
        this.charts.forEach(c => c.destroy());
        this.charts = [];

        const rows = n === 4 ? 2 : 1;
        const cols = n === 1 ? 1 : 2;
        container.style.gridTemplateRows = `repeat(${rows}, 1fr)`;
        container.style.gridTemplateColumns = `repeat(${cols}, 1fr)`;

        for (let i = 0; i < n; i++) {
            const wrapper = document.createElement('div');
            wrapper.className = 'chart-wrapper';
            const div = document.createElement('div');
            div.id = `chart-${i}`;
            div.className = 'chart-container';
            wrapper.appendChild(div);
            container.appendChild(wrapper);

            const c = new ChartInstance(div.id, i, this);
            this.charts.push(c);

            const saved = JSON.parse(localStorage.getItem(`chart_config_${i}`));
            if (i === 0 && window.INITIAL_CONFIG && window.INITIAL_CONFIG.symbol !== "None") {
                // Use URL params for the primary chart
                c.switchSymbol(window.INITIAL_CONFIG.symbol, window.INITIAL_CONFIG.interval);
            } else if (saved) {
                c.symbol = saved.symbol;
                c.interval = saved.interval;
                c.chartType = saved.chartType;
                c.switchSymbol(c.symbol, c.interval);
            } else {
                c.switchSymbol('NSE:NIFTY', '1');
            }
        }
        this.setActiveChart(0);
        this.saveLayout();
    }

    setActiveChart(idx) {
        this.activeIdx = idx;
        document.querySelectorAll('.chart-wrapper').forEach((w, i) => {
            w.classList.toggle('active', i === idx);
        });
        this.updateUI();
    }

    updateUI() {
        const c = this.charts[this.activeIdx];
        if (!c) return;
        document.querySelectorAll('.tf-btn').forEach(b => b.classList.toggle('active', b.dataset.interval === c.interval));
        document.getElementById('symbolSearch').value = c.symbol;
        document.getElementById('chartTypeSelector').value = c.chartType;

        this.charts.forEach(chart => {
            const wrapper = chart.container.parentElement;
            let label = wrapper.querySelector('.chart-label');
            if (!label) {
                label = document.createElement('div');
                label.className = 'chart-label';
                wrapper.appendChild(label);
            }
            const isDailyOrWeekly = chart.interval === 'D' || chart.interval === 'W';
            const suffix = isDailyOrWeekly ? '' : 'm';
            label.innerText = `${chart.symbol} (${chart.interval}${suffix})`;
        });
    }

    applyTheme() {
        const isLight = document.body.classList.contains('light-theme');
        const bg = isLight ? '#f8fafc' : '#0f172a';
        const text = isLight ? '#1e293b' : '#d1d5db';
        const grid = isLight ? '#f1f5f9' : 'rgba(255,255,255,0.05)';

        this.charts.forEach(c => {
            c.chart.applyOptions({
                layout: { background: { color: bg }, textColor: text },
                grid: { vertLines: { color: grid }, horzLines: { color: grid } }
            });
        });
    }

    setLoading(show) {
        document.getElementById('loading').classList.toggle('hidden', !show);
    }


    loadLayout() {
        const theme = localStorage.getItem('theme') || 'dark';
        document.body.classList.toggle('light-theme', theme === 'light');

        if (window.INITIAL_CONFIG && window.INITIAL_CONFIG.symbol && window.INITIAL_CONFIG.symbol !== "None" && window.INITIAL_CONFIG.symbol !== "") {
            this.setLayout(1);
        } else {
            const saved = localStorage.getItem('prodesk_layout');
            this.setLayout(saved ? parseInt(saved) : 1);
        }
    }
}

// Bootstrap
window.addEventListener('DOMContentLoaded', () => {
    window.prodeskEngine = new MultiChartEngine();
});
