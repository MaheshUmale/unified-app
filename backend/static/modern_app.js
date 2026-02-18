/**
 * PRODESK Modern Option Buyer Dashboard
 * High-performance, single-screen tactical command center.
 * Implements advanced order flow visualization, multi-chart synchronization,
 * and real-time options analytics.
 */

/**
 * System-wide color configuration for consistency across components.
 * @constant
 */
const COLORS = {
    bull: '#00FFC2',
    bear: '#FF3366',
    neutral: '#475569',
    liquidity: '#3b82f6',
    text: '#e5e7eb',
    muted: '#94a3b8',
    bg: '#1e1e1e'
};

/**
 * DataManager - Handles Socket.IO connectivity and REST API interactions.
 * Centralizes state for current instrument and coordinates data distribution.
 */
class DataManager {
    /**
     * @param {ModernDashboard} dashboard - Reference to the main controller.
     */
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.socket = io();
        this.currentUnderlying = 'NSE:NIFTY';
        this.spotPrice = 0;
        this.currentATMStrike = 0;
        this.currentOptionSymbol = null;
        this.aggregatedCandles = [];
        this.setupSocket();
    }

    /**
     * Initializes Socket.IO event listeners and handle real-time updates.
     */
    setupSocket() {
        this.socket.on('connect', () => {
            console.log("Connected to server, subscribing to feeds...");
            this.subscribe(this.currentUnderlying);
        });

        this.socket.on('raw_tick', (data) => {
            const key = this.currentUnderlying.toUpperCase();
            if (data[key]) {
                const tick = data[key];
                this.updateSpotPrice(tick.last_price || tick.price);
            }
        });

        this.socket.on('chart_update', (data) => {
            if (data && (data.instrumentKey === this.currentUnderlying || data.instrument_key === this.currentUnderlying)) {
                const ohlcv = data.ohlcv || data.data?.ohlcv || data.data;
                if (ohlcv && Array.isArray(ohlcv) && ohlcv.length > 0) {
                    const candle = ohlcv[0];
                    this.updateSpotPrice(candle[4]);
                    this.dashboard.charts.updateIndexChart(candle);
                }
            }
        });

        this.socket.on('options_quote_update', (data) => {
            if (data && data.symbol === this.currentOptionSymbol && data.lp !== undefined && data.lp !== null) {
                this.dashboard.charts.updateOptionChart(data.lp);
            }
        });
    }

    /**
     * Subscribes to real-time feeds for a specific instrument.
     * @param {string} underlying
     */
    subscribe(underlying) {
        this.socket.emit('subscribe', { instrumentKeys: [underlying], interval: '1' });
        this.socket.emit('subscribe_options', { underlying: underlying });
    }

    /**
     * Unsubscribes from real-time feeds.
     * @param {string} underlying
     */
    unsubscribe(underlying) {
        this.socket.emit('unsubscribe', { instrumentKeys: [underlying], interval: '1' });
        this.socket.emit('unsubscribe_options', { underlying: underlying });
    }

    /**
     * Switches the active instrument and reloads all dashboard data.
     * @param {string} newUnderlying
     */
    async switchUnderlying(newUnderlying) {
        if (newUnderlying === this.currentUnderlying) return;
        const old = this.currentUnderlying;
        this.currentUnderlying = newUnderlying;
        this.unsubscribe(old);
        this.subscribe(this.currentUnderlying);
        await this.loadAllData();
    }

    /**
     * Updates the spot price and triggers UI updates.
     * @param {number} price
     */
    updateSpotPrice(price) {
        if (!price || price === this.spotPrice) return;
        const oldPrice = this.spotPrice;
        this.spotPrice = price;
        if (this.dashboard.ui) {
            this.dashboard.ui.updateSpotPrice(this.spotPrice);
        }

        // Auto ATM Logic
        if (this.dashboard.ui.elements.autoAtmToggle?.checked && this.fullChain) {
            const closest = this.fullChain.reduce((prev, curr) =>
                Math.abs(curr.strike - this.spotPrice) < Math.abs(prev.strike - this.spotPrice) ? curr : prev
            );
            if (closest.strike !== this.currentATMStrike) {
                this.currentATMStrike = closest.strike;
                this.setOption(this.currentATMStrike, this.dashboard.ui.elements.optionTypeSelector.value);
            }
        }
    }

    /**
     * Sets the active option to display on the chart.
     * @param {number} strike
     * @param {string} type
     */
    async setOption(strike, type) {
        if (!this.fullChain) return;
        const option = this.fullChain.find(o => o.strike === strike && o.option_type === type);
        if (option && option.symbol !== this.currentOptionSymbol) {
            this.currentOptionSymbol = option.symbol;
            this.dashboard.ui.updateOptionSelection(strike, type);
            this.dashboard.ui.updateOptionLabel(`${strike} ${type === 'call' ? 'CE' : 'PE'}`);

            // Load historical data for new option
            const optRes = await this.fetchWithTimeout(`/api/tv/intraday/${encodeURIComponent(this.currentOptionSymbol)}?interval=1`);
            if (optRes && optRes.candles && optRes.candles.length > 0) {
                const formattedOpt = optRes.candles
                    .sort((a, b) => a[0] - b[0])
                    .map(c => ({ time: c[0], open: c[1], high: c[2], low: c[3], close: c[4] }));
                this.dashboard.charts.setOptionData(formattedOpt);
            }
        }
    }

    /**
     * Fetches consolidated analytics data and triggers chart updates.
     */
    async loadAllData() {
        this.dashboard.ui.setLoading(true);
        try {
            const data = await this.fetchWithTimeout(`/api/modern/data/${encodeURIComponent(this.currentUnderlying)}`);

            if (data && !data.error) {
                if (data.pcr_trend && data.pcr_trend.length > 0) {
                    this.dashboard.charts.updateAnalytics(data);
                }
                if (data.genie) this.dashboard.ui.updateGenieData(data.genie);
                if (data.spot_price) this.updateSpotPrice(data.spot_price);
                if (data.expiries) this.dashboard.ui.updateExpirySelector(data.expiries);
                this.identifyATM(data);
            }
            await this.loadChartData();
        } catch (err) {
            console.error("Critical error in loadAllData:", err);
        } finally {
            setTimeout(() => this.dashboard.ui.setLoading(false), 500);
        }
    }

    /**
     * Identifies the At-The-Money (ATM) strike and corresponding option symbol.
     * @param {Object} data
     */
    identifyATM(data) {
        if (data.spot_price && data.chain && data.chain.length > 0) {
            this.fullChain = data.chain;
            const closest = data.chain.reduce((prev, curr) =>
                Math.abs(curr.strike - data.spot_price) < Math.abs(prev.strike - data.spot_price) ? curr : prev
            );
            this.currentATMStrike = closest.strike;

            this.dashboard.ui.populateStrikes(data.chain);

            if (this.dashboard.ui.elements.autoAtmToggle.checked) {
                this.setOption(this.currentATMStrike, this.dashboard.ui.elements.optionTypeSelector.value);
            } else {
                // Keep current selection if manually set
                this.setOption(parseFloat(this.dashboard.ui.elements.strikeSelector.value), this.dashboard.ui.elements.optionTypeSelector.value);
            }
        }
    }

    /**
     * Loads historical candle data for primary and secondary (option) charts.
     */
    async loadChartData() {
        const indexRes = await this.fetchWithTimeout(`/api/tv/intraday/${encodeURIComponent(this.currentUnderlying)}?interval=1`);
        if (indexRes && indexRes.candles && indexRes.candles.length > 0) {
            const formattedIndex = indexRes.candles
                .sort((a, b) => a[0] - b[0])
                .map(c => ({ time: c[0], open: c[1], high: c[2], low: c[3], close: c[4] }));

            this.dashboard.charts.setIndexData(formattedIndex);
            this.dashboard.charts.updateLevels(indexRes.indicators);

            // Populate footprint cache with improved simulation
            this.aggregatedCandles = formattedIndex.map(c => ({
                ...c,
                ...this.dashboard.renderer.generateMockFootprint(c.low, c.high)
            }));
            this.dashboard.renderer.render();
        }

        if (this.currentOptionSymbol) {
            const optRes = await this.fetchWithTimeout(`/api/tv/intraday/${encodeURIComponent(this.currentOptionSymbol)}?interval=1`);
            if (optRes && optRes.candles && optRes.candles.length > 0) {
                const formattedOpt = optRes.candles
                    .sort((a, b) => a[0] - b[0])
                    .map(c => ({ time: c[0], open: c[1], high: c[2], low: c[3], close: c[4] }));
                this.dashboard.charts.setOptionData(formattedOpt);
            }
        }
    }

    /**
     * Utility for fetch with timeout to prevent hung requests.
     */
    async fetchWithTimeout(url, timeout = 10000) {
        const controller = new AbortController();
        const id = setTimeout(() => controller.abort(), timeout);
        try {
            const response = await fetch(url, { signal: controller.signal });
            clearTimeout(id);
            return response.ok ? await response.json() : null;
        } catch (e) {
            clearTimeout(id);
            return null;
        }
    }
}

/**
 * UIManager - Manages DOM interactions, global timers, and status indicators.
 */
class UIManager {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.elements = {
            assetSelector: document.getElementById('assetSelector'),
            expirySelector: document.getElementById('expirySelector'),
            spotPrice: document.getElementById('spotPrice'),
            currentTime: document.getElementById('currentTime'),
            maxPainValue: document.getElementById('maxPainValue'),
            straddleValue: document.getElementById('straddleValue'),
            ivRankValue: document.getElementById('ivRankValue'),
            optionTypeLabel: document.getElementById('optionTypeLabel'),
            statusDot: document.getElementById('statusDot'),
            pcrValue: document.getElementById('pcrValue'),
            pcrLabel: document.getElementById('pcrLabel'),
            loadingOverlay: document.getElementById('loadingOverlay'),
            strikeSelector: document.getElementById('strikeSelector'),
            optionTypeSelector: document.getElementById('optionTypeSelector'),
            autoAtmToggle: document.getElementById('autoAtmToggle')
        };
        this.setupListeners();
        this.startTimeUpdate();
    }

    /**
     * Configures primary UI event listeners.
     */
    setupListeners() {
        this.elements.assetSelector?.addEventListener('change', (e) => this.dashboard.data.switchUnderlying(e.target.value));

        this.elements.strikeSelector?.addEventListener('change', (e) => {
            this.elements.autoAtmToggle.checked = false;
            this.dashboard.data.setOption(parseFloat(e.target.value), this.elements.optionTypeSelector.value);
        });

        this.elements.optionTypeSelector?.addEventListener('change', (e) => {
            this.dashboard.data.setOption(parseFloat(this.elements.strikeSelector.value), e.target.value);
        });

        this.elements.autoAtmToggle?.addEventListener('change', (e) => {
            if (e.target.checked) {
                this.dashboard.data.setOption(this.dashboard.data.currentATMStrike, this.elements.optionTypeSelector.value);
            }
        });
    }

    /**
     * Starts the global IST clock for dashboard synchronization.
     */
    startTimeUpdate() {
        const update = () => {
            const now = new Date();
            const formatter = new Intl.DateTimeFormat('en-IN', {
                timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit'
            });
            if (this.elements.currentTime) this.elements.currentTime.textContent = formatter.format(now) + " IST";
        };
        update();
        setInterval(update, 1000);
    }

    /**
     * Updates the main spot price display.
     * @param {number} price
     */
    updateSpotPrice(price) {
        if (this.elements.spotPrice) {
            this.elements.spotPrice.textContent = price.toLocaleString(undefined, { minimumFractionDigits: 2 });
        }
    }

    /**
     * Updates Genie Insights panel data.
     * @param {Object} res
     */
    updateGenieData(res) {
        if (this.elements.maxPainValue) this.elements.maxPainValue.textContent = res.max_pain || '-';
        if (this.elements.straddleValue && res.atm_straddle) this.elements.straddleValue.textContent = res.atm_straddle.toFixed(2);
        if (this.elements.ivRankValue && res.iv_rank !== undefined) this.elements.ivRankValue.textContent = res.iv_rank + '%';
    }

    /**
     * Populates the strike selector with available strikes from the chain.
     * @param {Array} chain
     */
    populateStrikes(chain) {
        const selector = this.elements.strikeSelector;
        if (!selector) return;
        const currentVal = selector.value;
        const strikes = [...new Set(chain.map(o => o.strike))].sort((a, b) => a - b);

        selector.innerHTML = '';
        strikes.forEach(s => {
            const opt = document.createElement('option');
            opt.value = s; opt.textContent = s;
            selector.appendChild(opt);
        });

        if (currentVal && strikes.includes(parseFloat(currentVal))) {
            selector.value = currentVal;
        }
    }

    /**
     * Updates the selected values in strike and type selectors.
     */
    updateOptionSelection(strike, type) {
        if (this.elements.strikeSelector) this.elements.strikeSelector.value = strike;
        if (this.elements.optionTypeSelector) this.elements.optionTypeSelector.value = type;
    }

    /**
     * Updates the expiry selector dropdown.
     * @param {Array} expiries
     */
    updateExpirySelector(expiries) {
        const selector = this.elements.expirySelector;
        if (!selector) return;
        const currentVal = selector.value;
        selector.innerHTML = '';
        expiries.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d; opt.textContent = d;
            selector.appendChild(opt);
        });
        if (currentVal && expiries.includes(currentVal)) selector.value = currentVal;
    }

    /**
     * Updates the option chart label (e.g., Strike + Type).
     */
    updateOptionLabel(text) {
        if (this.elements.optionTypeLabel) {
            this.elements.optionTypeLabel.textContent = text;
        }
    }

    /**
     * Visualizes the current loading or live state via status indicators and overlay.
     * @param {boolean} isLoading
     */
    setLoading(isLoading) {
        const dot = this.elements.statusDot;
        if (dot) {
            dot.classList.toggle('animate-pulse', isLoading);
            dot.style.backgroundColor = isLoading ? '#fbbf24' : '#00FFC2';
        }
        if (this.elements.loadingOverlay) {
            this.elements.loadingOverlay.classList.toggle('active', isLoading);
        }
    }
}

/**
 * ChartManager - Orchestrates multiple charting systems (Chart.js and Lightweight Charts).
 * Handles synchronization, live updates, and analytical visualizations.
 */
class ChartManager {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.analytics = {};
        this.price = {};
        this.series = {};
        this.init();
    }

    init() {
        this.initAnalytics();
        this.initPriceCharts();
    }

    /**
     * Initializes Chart.js instances for analytics widgets.
     */
    initAnalytics() {
        const commonOptions = { maintainAspectRatio: false, plugins: { legend: { display: false } } };

        // PCR Gauge with custom Needle plugin
        const pcrCtx = document.getElementById('pcrGauge')?.getContext('2d');
        if (pcrCtx) {
            this.analytics.pcrGauge = new Chart(pcrCtx, {
                type: 'doughnut',
                data: {
                    labels: ['Bearish', 'Neutral', 'Bullish'],
                    datasets: [{
                        data: [0.7, 0.4, 0.9],
                        backgroundColor: [COLORS.bear + '44', COLORS.neutral + '44', COLORS.bull + '44'],
                        borderWidth: 1, borderColor: 'rgba(255,255,255,0.05)', needleValue: 1.0
                    }]
                },
                options: {
                    circumference: 180, rotation: 270, cutout: '85%', aspectRatio: 1.8,
                    plugins: { legend: { display: false }, tooltip: { enabled: false } }
                },
                plugins: [{
                    id: 'needle',
                    afterDraw: (chart) => {
                        const { ctx, chartArea } = chart;
                        if (!chartArea || !chart._metasets[0]) return;
                        ctx.save();
                        const needleValue = chart.config.data.datasets[0].needleValue;
                        const angle = Math.PI + (Math.min(Math.max(needleValue, 0), 2) / 2) * Math.PI;
                        const cx = chartArea.width / 2, cy = chart._metasets[0].data[0].y;
                        ctx.translate(cx, cy); ctx.rotate(angle);
                        ctx.beginPath(); ctx.moveTo(0, -2); ctx.lineTo(chartArea.height * 0.8, 0); ctx.lineTo(0, 2);
                        ctx.fillStyle = COLORS.text; ctx.fill();
                        ctx.beginPath(); ctx.arc(0, 0, 5, 0, Math.PI * 2); ctx.fill();
                        ctx.restore();
                    }
                }]
            });
        }

        // PCR Trend Sparkline
        const trendCtx = document.getElementById('pcrTrendChart')?.getContext('2d');
        if (trendCtx) {
            this.analytics.pcrTrend = new Chart(trendCtx, {
                type: 'line',
                data: { labels: [], datasets: [{ data: [], borderColor: COLORS.bull, borderWidth: 2, pointRadius: 0, fill: true, backgroundColor: COLORS.bull + '11' }] },
                options: { ...commonOptions, scales: { x: { display: false }, y: { display: false } } }
            });
        }

        // Multi-Strike OI Distribution
        const oiCtx = document.getElementById('oiStrikeChart')?.getContext('2d');
        if (oiCtx) {
            this.analytics.oiStrike = new Chart(oiCtx, {
                type: 'bar',
                data: { labels: [], datasets: [
                    { label: 'Call OI', data: [], backgroundColor: COLORS.bear, borderRadius: 2 },
                    { label: 'Put OI', data: [], backgroundColor: COLORS.bull, borderRadius: 2 }
                ]},
                options: {
                    ...commonOptions, indexAxis: 'y',
                    scales: {
                        x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: COLORS.muted, font: { size: 9 } } },
                        y: { grid: { display: false }, ticks: { color: COLORS.text, font: { size: 10, weight: 'bold' } } }
                    }
                }
            });
        }

        // OI vs Price Divergence Spotter
        const divCtx = document.getElementById('oiPriceDivergenceChart')?.getContext('2d');
        if (divCtx) {
            this.analytics.oiPriceDiv = new Chart(divCtx, {
                data: {
                    labels: [],
                    datasets: [
                        { type: 'line', label: 'Price', data: [], borderColor: '#fbbf24', borderWidth: 2, yAxisID: 'yPrice', pointRadius: 0 },
                        { type: 'line', label: 'Total OI', data: [], borderColor: '#a855f7', backgroundColor: '#a855f722', fill: true, borderWidth: 1, yAxisID: 'yOI', pointRadius: 0 }
                    ]
                },
                options: {
                    ...commonOptions, interaction: { mode: 'index', intersect: false },
                    scales: {
                        x: { display: false },
                        yPrice: { position: 'left', grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#fbbf24', font: { size: 8 } } },
                        yOI: { position: 'right', grid: { display: false }, ticks: { color: '#a855f7', font: { size: 8 } } }
                    }
                }
            });
        }
    }

    /**
     * Initializes Lightweight Charts for real-time price action.
     */
    initPriceCharts() {
        const chartOptions = {
            layout: { background: { type: 'solid', color: '#1e1e1e' }, textColor: COLORS.muted },
            grid: { vertLines: { color: 'rgba(255,255,255,0.05)' }, horzLines: { color: 'rgba(255,255,255,0.05)' } },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            timeScale: {
                borderColor: 'rgba(255,255,255,0.1)',
                timeVisible: true,
                secondsVisible: false,
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
            }
        };

        const createS = (id, type = 'candle') => {
            const el = document.getElementById(id);
            if (!el) return { chart: null, series: null };
            const chart = LightweightCharts.createChart(el, chartOptions);
            const series = type === 'candle' ? chart.addCandlestickSeries({
                upColor: COLORS.bull, downColor: COLORS.bear, borderVisible: false, wickUpColor: COLORS.bull, wickDownColor: COLORS.bear
            }) : chart.addAreaSeries({
                lineColor: COLORS.liquidity, topColor: COLORS.liquidity + '44', bottomColor: 'transparent', lineWidth: 2, priceFormat: { type: 'volume' }
            });
            return { chart, series };
        };

        const idx = createS('indexChart');
        this.price.index = idx.chart; this.series.index = idx.series;

        const opt = createS('optionChart');
        this.price.option = opt.chart; this.series.option = opt.series;

        const cvd = createS('cvdChart', 'area');
        this.price.cvd = cvd.chart; this.series.cvd = cvd.series;

        this.syncPriceCharts();
        window.addEventListener('resize', () => this.resizePriceCharts());
    }

    /**
     * Synchronizes time scales across all price-related charts.
     */
    syncPriceCharts() {
        if (!this.price.index || !this.price.option || !this.price.cvd) return;
        const sync = (m, ss) => m.timeScale().subscribeVisibleLogicalRangeChange(r => ss.forEach(s => s.timeScale().setVisibleLogicalRange(r)));
        sync(this.price.index, [this.price.option, this.price.cvd]);
        sync(this.price.option, [this.price.index, this.price.cvd]);
    }

    /**
     * Resizes all chart instances to match their container dimensions.
     */
    resizePriceCharts() {
        ['index', 'option', 'cvd'].forEach(k => {
            const el = document.getElementById(`${k}Chart`);
            if (el && this.price[k]) this.price[k].applyOptions({ width: el.clientWidth, height: el.clientHeight });
        });
        this.dashboard.renderer?.resize();
    }

    /**
     * Updates all analytics widgets with new data.
     */
    updateAnalytics(data) {
        const history = data.pcr_trend || [];
        const latest = history[history.length - 1];
        const pcr = latest?.pcr_oi || 0;

        // Update PCR Gauge
        if (this.analytics.pcrGauge) {
            this.analytics.pcrGauge.data.datasets[0].needleValue = pcr;
            this.analytics.pcrGauge.update();
            const label = this.dashboard.ui.elements.pcrLabel;
            if (label) {
                label.textContent = pcr > 1.1 ? 'Bullish' : pcr < 0.7 ? 'Bearish' : 'Neutral';
                label.className = `text-[8px] font-bold uppercase tracking-tighter ${pcr > 1.1 ? 'text-bull' : pcr < 0.7 ? 'text-bear' : 'text-gray-500'}`;
                if (this.dashboard.ui.elements.pcrValue) this.dashboard.ui.elements.pcrValue.textContent = pcr.toFixed(2);
            }
        }

        // Update PCR Trend Sparkline
        if (this.analytics.pcrTrend) {
            this.analytics.pcrTrend.data.labels = history.map((_, i) => i);
            this.analytics.pcrTrend.data.datasets[0].data = history.map(h => h.pcr_oi);
            this.analytics.pcrTrend.data.datasets[0].borderColor = pcr >= (history[0]?.pcr_oi || 0) ? COLORS.bull : COLORS.bear;
            this.analytics.pcrTrend.update();
        }

        // Update OI Strike Chart from Chain data
        if (this.analytics.oiStrike && data.chain) {
            const grouped = {};
            data.chain.forEach(opt => {
                if (!grouped[opt.strike]) grouped[opt.strike] = { strike: opt.strike, call_oi: 0, put_oi: 0 };
                if (opt.option_type === 'call') grouped[opt.strike].call_oi = opt.oi;
                else grouped[opt.strike].put_oi = opt.oi;
            });
            const sorted = Object.values(grouped)
                .sort((a,b) => (b.call_oi + b.put_oi) - (a.call_oi + a.put_oi))
                .slice(0, 7)
                .sort((a,b) => a.strike - b.strike);

            this.analytics.oiStrike.data.labels = sorted.map(d => d.strike);
            this.analytics.oiStrike.data.datasets[0].data = sorted.map(d => -d.call_oi);
            this.analytics.oiStrike.data.datasets[1].data = sorted.map(d => d.put_oi);
            this.analytics.oiStrike.update();
        }

        // Update Divergence Chart
        if (this.analytics.oiPriceDiv) {
            this.analytics.oiPriceDiv.data.labels = history.map(h => h.timestamp);
            this.analytics.oiPriceDiv.data.datasets[0].data = history.map(h => h.spot_price || h.underlying_price);
            this.analytics.oiPriceDiv.data.datasets[1].data = history.map(h => h.total_oi);
            this.analytics.oiPriceDiv.update();
        }
    }

    /**
     * Sets historical data for the index chart.
     */
    setIndexData(data) {
        if (this.series.index) {
            this.series.index.setData(data);
            this.updateCVD(data);
        }
    }

    /**
     * Sets historical data for the option chart.
     */
    setOptionData(data) {
        if (this.series.option) this.series.option.setData(data);
    }

    /**
     * Live update for index chart.
     */
    updateIndexChart(candle) {
        if (this.series.index) {
            this.series.index.update({ time: candle[0], open: candle[1], high: candle[2], low: candle[3], close: candle[4] });
        }
    }

    /**
     * Live update for option chart.
     */
    updateOptionChart(lp) {
        if (this.series.option) {
            const bar = { time: Math.floor(Date.now() / 60000) * 60, open: lp, high: lp, low: lp, close: lp };
            this.series.option.update(bar);
        }
    }

    /**
     * Calculates and updates Cumulative Volume Delta.
     */
    updateCVD(candles) {
        if (!this.series.cvd) return;
        let cvd = 0;
        this.series.cvd.setData(candles.map(c => { cvd += (c.close - c.open) * 100; return { time: c.time, value: cvd }; }));
    }

    /**
     * Updates analytical levels (Support/Resistance/Markers).
     */
    updateLevels(indicators) {
        if (!indicators || !this.series.index) return;
        indicators.forEach(ind => {
            if (ind.type === 'price_line') {
                this.series.index.createPriceLine({ price: ind.data.price, color: ind.data.color || COLORS.muted, axisLabelVisible: true, title: ind.title });
            } else if (ind.type === 'markers') {
                this.series.index.setMarkers(ind.data);
            }
        });
    }
}

/**
 * FootprintRenderer - High-performance canvas overlays for Volume Footprints and Order Blocks.
 */
class FootprintRenderer {
    constructor(dashboard) {
        this.dashboard = dashboard;
        this.canvas = document.getElementById('footprintCanvas');
        this.ctx = this.canvas?.getContext('2d');
        if (this.canvas) {
            this.resize();
            if (this.dashboard.charts && this.dashboard.charts.price.index) {
                this.dashboard.charts.price.index.timeScale().subscribeVisibleLogicalRangeChange(() => this.render());
            }
        }
    }

    /**
     * Resizes the canvas and re-renders overlays.
     */
    resize() {
        if (!this.canvas) return;
        this.canvas.width = this.canvas.parentElement.clientWidth;
        this.canvas.height = this.canvas.parentElement.clientHeight;
        this.render();
    }

    /**
     * Orchestrates the rendering of all canvas overlays.
     */
    render() {
        if (!this.ctx) return;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        this.renderOrderBlocks();
        this.renderFootprint();
    }

    /**
     * Renders Order Blocks (OB) based on current price discovery.
     */
    renderOrderBlocks() {
        if (!this.dashboard.data || !this.dashboard.charts.price.index) return;
        const ts = this.dashboard.charts.price.index.timeScale();
        const obs = [
            { type: 'BEAR', top: this.dashboard.data.spotPrice * 1.002, bottom: this.dashboard.data.spotPrice * 1.001 },
            { type: 'BULL', top: this.dashboard.data.spotPrice * 0.999, bottom: this.dashboard.data.spotPrice * 0.998 }
        ];
        obs.forEach(ob => {
            const yt = this.dashboard.charts.series.index.priceToCoordinate(ob.top);
            const yb = this.dashboard.charts.series.index.priceToCoordinate(ob.bottom);
            if (yt !== null && yb !== null) {
                this.ctx.fillStyle = ob.type === 'BEAR' ? 'rgba(255, 51, 102, 0.2)' : 'rgba(0, 255, 194, 0.2)';
                this.ctx.fillRect(0, yt, this.canvas.width, yb - yt);
            }
        });
    }

    /**
     * Renders detailed Volume Footprint overlays for visible candles.
     */
    renderFootprint() {
        if (!this.dashboard.data || !this.dashboard.charts.price.index) return;
        const ts = this.dashboard.charts.price.index.timeScale();
        const spacing = ts.options().barSpacing;
        if (spacing < 50) return;

        this.dashboard.data.aggregatedCandles.forEach(candle => {
            const x = ts.timeToCoordinate(candle.time);
            if (x === null || x < 0 || x > this.canvas.width) return;

            const footprint = candle.footprint || {};
            const prices = Object.keys(footprint).map(Number).sort((a, b) => b - a);
            const halfWidth = (spacing / 2) * 0.9;

            // 1. Draw Value Area (VA) Box
            if (candle.vah && candle.val) {
                const vahY = this.dashboard.charts.series.index.priceToCoordinate(candle.vah);
                const valY = this.dashboard.charts.series.index.priceToCoordinate(candle.val);
                if (vahY !== null && valY !== null) {
                    this.ctx.strokeStyle = 'rgba(59, 130, 246, 0.5)';
                    this.ctx.setLineDash([2, 2]);
                    this.ctx.strokeRect(x - halfWidth - 2, vahY - 6, halfWidth * 2 + 4, valY - vahY + 12);
                    this.ctx.setLineDash([]);
                }
            }

            prices.forEach((p, i) => {
                const y = this.dashboard.charts.series.index.priceToCoordinate(p);
                if (y === null || y < 0 || y > this.canvas.height) return;

                const data = footprint[p];
                const buy = data.buy || 0;
                const sell = data.sell || 0;

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
                    this.ctx.fillStyle = 'rgba(0, 255, 194, 0.3)';
                    this.ctx.fillRect(x, y - 6, halfWidth, 12);
                } else if (isSellImbalance) {
                    this.ctx.fillStyle = 'rgba(255, 51, 102, 0.3)';
                    this.ctx.fillRect(x - halfWidth, y - 6, halfWidth, 12);
                } else {
                    this.ctx.fillStyle = (p >= candle.val && p <= candle.vah) ? 'rgba(255, 255, 255, 0.08)' : 'rgba(255, 255, 255, 0.03)';
                    this.ctx.fillRect(x - halfWidth, y - 6, halfWidth * 2, 12);
                }

                // 3. Point of Control (POC) Highlight
                if (p === candle.poc) {
                    this.ctx.strokeStyle = '#fbbf24';
                    this.ctx.lineWidth = 2;
                    this.ctx.strokeRect(x - halfWidth, y - 6, halfWidth * 2, 12);
                    this.ctx.lineWidth = 1;
                }

                // Numbers (formatted to K/M)
                const formatV = (v) => {
                    if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
                    if (v >= 1000) return (v / 1000).toFixed(1) + 'K';
                    return v;
                };

                this.ctx.font = (isBuyImbalance || isSellImbalance) ? 'bold 7px "IBM Plex Mono"' : '6px "IBM Plex Mono"';
                this.ctx.textAlign = 'right';
                this.ctx.fillStyle = isSellImbalance ? COLORS.bear : COLORS.muted;
                this.ctx.fillText(formatV(sell), x - 4, y + 3);
                this.ctx.textAlign = 'left';
                this.ctx.fillStyle = isBuyImbalance ? COLORS.bull : COLORS.muted;
                this.ctx.fillText(formatV(buy), x + 4, y + 3);

                // Center Split
                this.ctx.strokeStyle = 'rgba(255,255,255,0.1)';
                this.ctx.beginPath(); this.ctx.moveTo(x, y - 4); this.ctx.lineTo(x, y + 4); this.ctx.stroke();
            });
        });
    }

    /**
     * Generates simulated footprint data for visualization.
     */
    generateMockFootprint(low, high) {
        const footprint = {};
        const step = 0.5;
        let totalVol = 0, maxVol = 0, poc = low;
        const prices = [];
        for (let p = low; p <= high; p += step) {
            const price = parseFloat(p.toFixed(2));
            const dist = 1.0 - (Math.abs(price - (low + high) / 2) / (high - low || 1));
            const buy = Math.floor((Math.random() * 1500 + 500) * dist);
            const sell = Math.floor((Math.random() * 1500 + 500) * dist);
            const vol = buy + sell;
            footprint[price] = { buy: Math.max(1, buy), sell: Math.max(1, sell) };
            totalVol += vol;
            if (vol > maxVol) { maxVol = vol; poc = price; }
            prices.push(price);
        }
        const vaVol = totalVol * 0.7;
        let currentVaVol = maxVol;
        let sortedPrices = prices.sort((a, b) => a - b);
        let lIdx = sortedPrices.indexOf(poc), uIdx = lIdx;
        while (currentVaVol < vaVol && (lIdx > 0 || uIdx < sortedPrices.length - 1)) {
            let lVol = lIdx > 0 ? (footprint[sortedPrices[lIdx-1]].buy + footprint[sortedPrices[lIdx-1]].sell) : 0;
            let uVol = uIdx < sortedPrices.length - 1 ? (footprint[sortedPrices[uIdx+1]].buy + footprint[sortedPrices[uIdx+1]].sell) : 0;
            if (lVol >= uVol) { currentVaVol += lVol; lIdx--; }
            else { currentVaVol += uVol; uIdx++; }
        }
        return { footprint, poc, vah: sortedPrices[uIdx], val: sortedPrices[lIdx] };
    }
}

/**
 * ModernDashboard - Root controller that bootstraps all application modules.
 */
class ModernDashboard {
    constructor() {
        this.ui = new UIManager(this);
        this.charts = new ChartManager(this);
        this.data = new DataManager(this);
        this.renderer = new FootprintRenderer(this);
        this.data.loadAllData();
    }
}

// Global bootstrap on DOM completion
document.addEventListener('DOMContentLoaded', () => window.prodesk = new ModernDashboard());
