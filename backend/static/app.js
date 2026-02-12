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
        this.hrn = '';
        this.chart = null;
        this.candleSeries = null;
        this.volumeSeries = null;
        this.indicatorSeries = {};
        this.lastCandle = null;
        this.fullHistory = {
            candles: new Map(), // Use Map for efficient merging by timestamp
            volume: new Map(),
            indicators: {}
        };
        this.drawings = [];
        this.markers = [];
        // Disable EMA indicators and Markers for Chart 2 (index 1) by default
        this.showIndicators = index === 1 ? false : true;
        this.hiddenPlots = new Set();
        this.colorOverrides = {}; // Keyed by indicator title or marker text
        this.oiData = null;
        this.showOiProfile = document.getElementById('oiProfileToggle')?.checked || false;
        this.lastUpdatedTime = 0;

        // Replay State
        this.isReplayMode = false;
        this.replayIndex = -1;
        this.replayHistory = {
            pcr: [],
            snapshots: new Map() // timestamp -> strike data
        };
        this.isPlaying = false;
        this.replayInterval = null;

        this.initChart();
    }

    initChart() {
        const container = document.getElementById(this.containerId);
        if (!container) return;

        this.chart = LightweightCharts.createChart(container, {
            layout: { background: { type: 'solid', color: '#ffffff' }, textColor: '#191919' },
            grid: { vertLines: { color: '#f0f3fa' }, horzLines: { color: '#f0f3fa' } },
            crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
            localization: {
                locale: 'en-IN',
                timeFormatter: (ts) => {
                    return new Intl.DateTimeFormat('en-IN', {
                        timeZone: 'Asia/Kolkata',
                        hour: '2-digit',
                        minute: '2-digit',
                        second: '2-digit',
                        hour12: false
                    }).format(new Date(ts * 1000));
                }
            },
            rightPriceScale: { borderColor: '#f0f3fa', autoScale: true, scaleMargins: { top: 0.2, bottom: 0.2 } },
            timeScale: {
                borderColor: '#f0f3fa',
                timeVisible: true,
                secondsVisible: false,
                rightOffset: 10,
                tickMarkFormatter: (time, tickMarkType, locale) => {
                    const date = new Date(time * 1000);
                    const options = { timeZone: 'Asia/Kolkata', hour12: false };
                    if (tickMarkType >= 3) {
                        options.hour = '2-digit';
                        options.minute = '2-digit';
                    } else if (tickMarkType === 2) {
                        options.day = '2-digit';
                        options.month = 'short';
                    } else if (tickMarkType === 1) {
                        options.month = 'short';
                    } else {
                        options.year = 'numeric';
                    }
                    return new Intl.DateTimeFormat('en-IN', options).format(date);
                }
            }
        });

        this.candleSeries = this.chart.addCandlestickSeries({
            upColor: '#22c55e', downColor: '#ef4444', borderVisible: true, wickUpColor: '#22c55e', wickDownColor: '#ef4444',
            lastValueVisible: false,
            priceLineVisible: false
        });

        this.volumeSeries = this.chart.addHistogramSeries({
            color: '#3b82f6', priceFormat: { type: 'volume' }, priceScaleId: 'volume',
            lastValueVisible: false,
            priceLineVisible: false
        });

        this.chart.priceScale('volume').applyOptions({
            scaleMargins: { top: 0.8, bottom: 0 }, visible: false
        });

        // OI Profile Canvas
        const wrapper = container.parentElement;
        this.oiCanvas = document.createElement('canvas');
        this.oiCanvas.className = 'oi-profile-canvas';
        wrapper.appendChild(this.oiCanvas);
        this.syncOiCanvas();

        this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => {
            if (this.showOiProfile) this.renderOiProfile();
        });

        this.chart.subscribeCrosshairMove((param) => {
            if (!this.showOiProfile || !this.oiData || !param.point) {
                if (this.tooltip) this.tooltip.style.display = 'none';
                return;
            }

            const price = this.candleSeries.coordinateToPrice(param.point.y);
            if (!price) return;

            const closest = this.oiData.reduce((prev, curr) => {
                return (Math.abs(curr.strike - price) < Math.abs(prev.strike - price) ? curr : prev);
            });

            if (closest && Math.abs(closest.strike - price) / closest.strike < 0.01) {
                if (!this.tooltip) {
                    this.tooltip = document.createElement('div');
                    this.tooltip.style.position = 'absolute';
                    this.tooltip.style.display = 'none';
                    this.tooltip.style.padding = '8px';
                    this.tooltip.style.boxSizing = 'border-box';
                    this.tooltip.style.fontSize = '10px';
                    this.tooltip.style.zIndex = '1000';
                    this.tooltip.style.top = '12px';
                    this.tooltip.style.left = '12px';
                    this.tooltip.style.pointerEvents = 'none';
                    this.tooltip.style.borderRadius = '4px';
                    this.tooltip.style.border = '1px solid rgba(255, 255, 255, 0.1)';
                    this.tooltip.style.background = 'rgba(15, 23, 42, 0.9)';
                    this.tooltip.style.backdropFilter = 'blur(4px)';
                    this.tooltip.style.color = '#f8fafc';
                    this.tooltip.style.boxShadow = '0 10px 15px -3px rgba(0, 0, 0, 0.1)';
                    container.parentElement.appendChild(this.tooltip);
                }

                // Only show if mouse is on the right side (where the profile is)
                if (param.point.x > container.clientWidth * 0.7) {
                    this.tooltip.style.display = 'block';
                    this.tooltip.innerHTML = `
                        <div style="font-weight: 800; color: #3b82f6; margin-bottom: 4px;">STRIKE: ${closest.strike}</div>
                        <div style="display: flex; justify-content: space-between; gap: 12px;">
                            <span style="color: #ef4444; font-weight: 600;">CALL OI:</span>
                            <span>${closest.call_oi.toLocaleString()}</span>
                        </div>
                        <div style="display: flex; justify-content: space-between; gap: 12px;">
                            <span style="color: #22c55e; font-weight: 600;">PUT OI:</span>
                            <span>${closest.put_oi.toLocaleString()}</span>
                        </div>
                    `;
                    this.tooltip.style.left = (param.point.x - 140) + 'px';
                    this.tooltip.style.top = (param.point.y - 60) + 'px';
                } else {
                    this.tooltip.style.display = 'none';
                }
            } else {
                if (this.tooltip) this.tooltip.style.display = 'none';
            }
        });

        this.chart.subscribeClick((param) => {
            if (this.isReplayMode && param.time && this.replayIndex === -1) {
                 // Convert Map keys to an Array and find the index of the timestamp
                const keys = Array.from(this.fullHistory.candles.keys());
                const idx = keys.indexOf(param.time);

                if (idx !== -1) {
                    console.log("Found at index:", idx);
                }
                // const idx = this.fullHistory.candles.findIndex(c => c.time === param.time);
                if (idx !== -1) {
                    this.replayIndex = idx;
                    this.stepReplay(0);
                    updateReplayUI(this);
                }
            } else {
                const price = param.point ? this.candleSeries.coordinateToPrice(param.point.y) : null;
                if (price) {
                    const hlineBtn = document.getElementById('drawingToolBtn');
                    const isHlineActive = hlineBtn && hlineBtn.classList.contains('bg-blue-600');
                    const isShiftKey = param.sourceEvent && param.sourceEvent.shiftKey;
                    if (isHlineActive || isShiftKey) {
                        this.addHorizontalLine(price);
                    }
                }
            }
        });

        // Handle focus
        container.parentElement.addEventListener('mousedown', () => {
            setActiveChart(this);
        });
    }

    syncOiCanvas() {
        if (!this.oiCanvas) return;
        const container = document.getElementById(this.containerId);
        if (!container) return;
        this.oiCanvas.width = container.clientWidth;
        this.oiCanvas.height = container.clientHeight;
        if (this.showOiProfile) this.renderOiProfile();
    }

    async fetchOiProfile() {
        if (!this.showOiProfile) return;
        try {
            const res = await fetch(`/api/options/oi-analysis/${encodeURIComponent(this.symbol)}`);
            const data = await res.json();
            this.oiData = data.data || [];
            this.renderOiProfile();
        } catch (e) { console.error("Fetch OI failed:", e); }
    }

    renderOiProfile() {
        const ctx = this.oiCanvas.getContext('2d');
        ctx.clearRect(0, 0, this.oiCanvas.width, this.oiCanvas.height);
        if (!this.showOiProfile || !this.oiData || this.oiData.length === 0) return;

        const width = this.oiCanvas.width;
        const height = this.oiCanvas.height;
        const profileWidth = width * 0.25;

        const sortedData = [...this.oiData].sort((a,b) => a.strike - b.strike);
        const maxOI = Math.max(...sortedData.map(d => Math.max(d.call_oi, d.put_oi)));
        if (maxOI === 0) return;

        sortedData.forEach(d => {
            const y = this.candleSeries.priceToCoordinate(d.strike);
            if (y === null || y < 0 || y > height) return;

            const callW = (d.call_oi / maxOI) * profileWidth;
            const putW = (d.put_oi / maxOI) * profileWidth;

            // Call OI (Red)
            ctx.fillStyle = 'rgba(239, 68, 68, 0.5)';
            ctx.fillRect(width - callW, y - 4, callW, 3);

            // Put OI (Green)
            ctx.fillStyle = 'rgba(34, 197, 94, 0.5)';
            ctx.fillRect(width - putW, y + 1, putW, 3);

            // Strike Label
            if (callW > 20 || putW > 20) {
                ctx.fillStyle = '#64748b';
                ctx.font = '8px "Plus Jakarta Sans"';
                ctx.textAlign = 'right';
                ctx.fillText(d.strike, width - 5, y + 3);
            }
        });
    }

    async switchSymbol(symbol, interval = null) {
        const oldSymbol = this.symbol;
        const oldInterval = this.interval;

        if (symbol) this.symbol = symbol.toUpperCase();
        if (interval) this.interval = interval;

        // Unsubscribe from old symbol/interval if changed
        if (oldSymbol !== this.symbol || oldInterval !== this.interval) {
            socket.emit('unsubscribe', { instrumentKeys: [oldSymbol], interval: oldInterval });
        }

        this.lastCandle = null;
        this.hrn = '';
        this.fullHistory = {
            candles: new Map(),
            volume: new Map(),
            indicators: {}
        };

        this.candleSeries.setData([]);
        this.volumeSeries.setData([]);
        this.candleSeries.setMarkers([]);
        Object.values(this.indicatorSeries).forEach(s => this.chart.removeSeries(s));
        this.indicatorSeries = {};

        if (this.priceLines) {
            Object.values(this.priceLines).forEach(l => this.candleSeries.removePriceLine(l));
            this.priceLines = {};
        }

        setLoading(true);
        try {
            const resData = await fetchIntraday(this.symbol, this.interval);
            if (resData.hrn) this.hrn = resData.hrn;
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

                chartData.forEach(c => this.fullHistory.candles.set(c.time, c));
                this.lastCandle = chartData[chartData.length - 1];

                candles.forEach(c => {
                    const ts = typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000);
                    this.fullHistory.volume.set(ts, {
                        time: ts,
                        value: Number(c.volume),
                        color: Number(c.close) >= Number(c.open) ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                    });
                });

                this.renderData();

                const lastIdx = chartData.length - 1;
                if (!isNaN(lastIdx) && lastIdx >= 0) {
                    this.chart.timeScale().setVisibleLogicalRange({ from: lastIdx - 100, to: lastIdx + 10 });
                }
            }

            if (resData.indicators) {
                this.handleChartUpdate({ indicators: resData.indicators });
                Object.entries(this.indicatorSeries).forEach(([key, s]) => {
                    s.applyOptions({
                        visible: this.showIndicators && !this.hiddenPlots.has(key),
                        lastValueVisible: false,
                        priceLineVisible: false
                    });
                });
                this.candleSeries.setMarkers(this.showIndicators && !this.hiddenPlots.has('__markers__') ? this.markers : []);
            }

            if (this.showOiProfile) this.fetchOiProfile();

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
        if (this.fullHistory.candles.size === 0) return;
        let displayCandles = Array.from(this.fullHistory.candles.values()).sort((a, b) => a.time - b.time);
        if (!displayCandles.some(c => c.hasExplicitColor)) {
            displayCandles = applyRvolColoring(displayCandles);
        }
        this.candleSeries.setData(displayCandles);
        this.volumeSeries.setData(Array.from(this.fullHistory.volume.values()).sort((a, b) => a.time - b.time));

        if (displayCandles.length > 0) {
            this.lastUpdatedTime = displayCandles[displayCandles.length - 1].time;
        }

        // Restore indicators
        Object.entries(this.fullHistory.indicators).forEach(([id, data]) => {
            if (this.indicatorSeries[id]) {
                this.indicatorSeries[id].setData(data);
                this.indicatorSeries[id].applyOptions({ lastValueVisible: false, priceLineVisible: false });
            }
        });

        // Restore markers
        this.candleSeries.setMarkers(this.showIndicators && !this.hiddenPlots.has('__markers__') ? this.markers : []);
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
            if (this.lastCandle) {
                this.fullHistory.candles.set(this.lastCandle.time, { ...this.lastCandle });
                this.fullHistory.volume.set(this.lastCandle.time, {
                    time: this.lastCandle.time, value: this.lastCandle.volume,
                    color: this.lastCandle.close >= this.lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                });
            }
            this.lastCandle = { time: candleTime, open: price, high: price, low: price, close: price, volume: ltq };
            this.candleSeries.update(this.lastCandle);
            this.lastUpdatedTime = candleTime;
            this.volumeSeries.update({ time: candleTime, value: ltq, color: 'rgba(59, 130, 246, 0.5)' });
        } else if (candleTime === this.lastCandle.time) {
            this.lastCandle.close = price;
            this.lastCandle.high = Math.max(this.lastCandle.high, price);
            this.lastCandle.low = Math.min(this.lastCandle.low, price);
            this.lastCandle.volume += ltq;
            this.candleSeries.update(this.lastCandle);
            this.lastUpdatedTime = candleTime;
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

                candles.forEach((c, idx) => {
                    this.fullHistory.candles.set(c.time, c);
                    this.fullHistory.volume.set(vol[idx].time, vol[idx]);
                });

                // Maintain history limit
                if (this.fullHistory.candles.size > 2000) {
                    const keys = Array.from(this.fullHistory.candles.keys()).sort((a,b) => a-b);
                    const toDelete = keys.slice(0, keys.length - 2000);
                    toDelete.forEach(k => {
                        this.fullHistory.candles.delete(k);
                        this.fullHistory.volume.delete(k);
                    });
                }

                if (candles.length > 0) {
                    this.lastCandle = { ...candles[candles.length - 1], volume: vol[vol.length - 1].value };
                    if (!this.isReplayMode) {
                        if (candles.length > 10) this.renderData();
                        else {
                            candles.forEach((c, idx) => {
                                if (c.time >= this.lastUpdatedTime) {
                                    this.candleSeries.update(c);
                                    this.volumeSeries.update(vol[idx]);
                                    this.lastUpdatedTime = Math.max(this.lastUpdatedTime, c.time);
                                }
                            });
                        }
                    }
                }
            }
        }

        if (data.bar_colors) {
            this.applyBarColors(data.bar_colors);
        }

        if (data.indicators) {
            this.applyIndicators(data.indicators);
        }
    }

    applyBarColors(barColors) {
        barColors.forEach(bc => {
            const time = Math.floor(bc.time);
            const candle = this.fullHistory.candles.get(time);
            if (candle) {
                const color = tvColorToRGBA(bc.color);
                candle.color = color; candle.wickColor = color; candle.borderColor = color; candle.hasExplicitColor = true;
            }
        });
        this.renderData();
    }

    applyIndicators(indicators) {
        // Enforce no indicators/markers for Chart 2 (index 1)
        if (this.index === 1) return;

        let newlyAdded = false;
        const allMarkers = [];

        indicators.forEach(ind => {
            const { id, type, title, style, data } = ind;

            if (type === 'markers') {
                data.forEach(m => {
                    const mText = m.text || '';
                    allMarkers.push({
                        time: m.time,
                        position: m.position || 'aboveBar',
                        color: this.colorOverrides[mText] || tvColorToRGBA(m.color) || '#3b82f6',
                        shape: m.shape || 'circle',
                        size: m.size || 1,
                        text: mText
                    });
                });
                return;
            }

            if (type === 'price_line') {
                this.addPriceLine(id, data);
                return;
            }

            if (type === 'trade') {
                this.addTradePlot(id, data);
                return;
            }

            // Standard Series: line, area, histogram
            if (!this.indicatorSeries[id]) {
                const options = {
                    title: '', // Hide title on scale
                    color: this.colorOverrides[title] || tvColorToRGBA(style?.color) || '#3b82f6',
                    lineWidth: style?.lineWidth || 1,
                    lineStyle: this._mapLineStyle(style?.lineStyle),
                    visible: this.showIndicators && !this.hiddenPlots.has(id),
                    lastValueVisible: false,
                    priceLineVisible: false,
                    priceScaleId: 'right',
                    priceFormat: { type: 'custom', formatter: val => '' },
                    autoscaleInfoProvider: () => null
                };

                if (type === 'area') {
                    this.indicatorSeries[id] = this.chart.addAreaSeries(options);
                } else if (type === 'histogram') {
                    this.indicatorSeries[id] = this.chart.addHistogramSeries(options);
                } else {
                    this.indicatorSeries[id] = this.chart.addLineSeries(options);
                }
                this.indicatorSeries[id]._backendTitle = title;
                newlyAdded = true;
            }

            if (data && data.length > 0) {
                const formattedData = data.map(d => ({
                    time: d.time,
                    value: d.value,
                    color: d.color ? tvColorToRGBA(d.color) : undefined
                })).sort((a, b) => a.time - b.time);

                this.fullHistory.indicators[id] = formattedData;

                if (!this.isReplayMode) {
                    this.indicatorSeries[id].setData(formattedData);
                    // Force hide labels on every update and ensure visibility matches state
                    this.indicatorSeries[id].applyOptions({
                        visible: this.showIndicators && !this.hiddenPlots.has(id),
                        lastValueVisible: false,
                        priceLineVisible: false,
                        color: this.colorOverrides[title] || tvColorToRGBA(style?.color) || '#3b82f6'
                    });
                }
            }
        });

        // Handle merged markers
        if (allMarkers.length > 0 || (Array.isArray(indicators) && indicators.some(i => i.type === 'markers'))) {
            // Deduplicate markers by time and text
            const uniqueMarkers = [];
            const seen = new Set();
            allMarkers.sort((a, b) => a.time - b.time).forEach(m => {
                const key = `${m.time}_${m.text}`;
                if (!seen.has(key)) {
                    uniqueMarkers.push(m);
                    seen.add(key);
                }
            });

            this.markers = uniqueMarkers;
            if (!this.isReplayMode) {
                this.candleSeries.setMarkers(this.showIndicators && !this.hiddenPlots.has('__markers__') ? this.markers : []);
            }
        }

        if (newlyAdded && this.index === activeChartIndex) {
            if (!document.getElementById('indicatorPanel').classList.contains('hidden')) {
                populateIndicatorList();
            }
        }
    }

    _mapLineStyle(style) {
        if (style === 1) return LightweightCharts.LineStyle.Dashed;
        if (style === 2) return LightweightCharts.LineStyle.Dotted;
        if (style === 3) return LightweightCharts.LineStyle.LargeDashed;
        if (style === 4) return LightweightCharts.LineStyle.SparseDotted;
        return LightweightCharts.LineStyle.Solid;
    }

    addPriceLine(id, data) {
        // Enforce no price lines for Chart 2 (index 1)
        if (this.index === 1) return;
        if (!this.priceLines) this.priceLines = {};
        if (this.priceLines[id]) {
            this.candleSeries.removePriceLine(this.priceLines[id]);
        }
        const title = data.title || id;
        this.priceLines[id] = this.candleSeries.createPriceLine({
            price: data.price,
            color: this.colorOverrides[title] || tvColorToRGBA(data.color) || '#3b82f6',
            lineWidth: data.lineWidth || 2,
            lineStyle: this._mapLineStyle(data.lineStyle || 2),
            axisLabelVisible: false,
            title: title
        });
    }

    addTradePlot(id, data) {
        const { entry, sl, target, entryColor, slColor, targetColor } = data;
        if (entry) this.addPriceLine(`${id}_entry`, { price: entry, color: entryColor || '#fff', title: 'ENTRY', lineStyle: 0 });
        if (sl) this.addPriceLine(`${id}_sl`, { price: sl, color: slColor || '#ef4444', title: 'SL', lineStyle: 2 });
        if (target) this.addPriceLine(`${id}_target`, { price: target, color: targetColor || '#22c55e', title: 'TARGET', lineStyle: 2 });
    }

    async loadReplayHistory() {
        if (!this.symbol) return;
        try {
            const res = await fetch(`/api/options/full-history/${encodeURIComponent(this.symbol)}`);
            const data = await res.json();

            this.replayHistory.pcr = data.pcr_history || [];
            this.replayHistory.snapshots = new Map();

            if (data.snapshots) {
                data.snapshots.forEach(s => {
                    const ts = Math.floor(new Date(s.timestamp).getTime() / 1000);
                    if (!this.replayHistory.snapshots.has(ts)) {
                        this.replayHistory.snapshots.set(ts, []);
                    }
                    this.replayHistory.snapshots.get(ts).push(s);
                });
            }
        } catch (e) { console.error("Replay history load failed:", e); }
    }

    stepReplay(delta) {
        const newIdx = this.replayIndex + delta;
        const allCandles = Array.from(this.fullHistory.candles.values()).sort((a,b) => a.time - b.time);
        const allVolume = Array.from(this.fullHistory.volume.values()).sort((a,b) => a.time - b.time);

        if (newIdx >= 0 && newIdx < allCandles.length) {
            this.replayIndex = newIdx;
            const vC = allCandles.slice(0, this.replayIndex + 1);
            const vV = allVolume.slice(0, this.replayIndex + 1);
            const currentTime = vC[vC.length - 1].time;

            this.candleSeries.setData(vC);
            this.volumeSeries.setData(vV);
            if (vC.length > 0) this.lastUpdatedTime = vC[vC.length - 1].time;

            // Subset indicators
            Object.entries(this.fullHistory.indicators).forEach(([id, data]) => {
                const series = this.indicatorSeries[id];
                if (series) {
                    const subset = data.filter(d => d.time <= currentTime);
                    series.setData(subset);
                }
            });

            // Subset markers
            const visibleMarkers = this.markers.filter(m => m.time <= currentTime);
            this.candleSeries.setMarkers(this.showIndicators && !this.hiddenPlots.has('__markers__') ? visibleMarkers : []);

            this.lastCandle = { ...vC[vC.length - 1] };

            // Synchronize Options Data
            this.syncReplayOptions(currentTime);
        }
    }

    syncReplayOptions(currentTime) {
        // Find nearest PCR data
        const pcrList = this.replayHistory.pcr;
        let activePCR = null;
        if (pcrList.length > 0) {
            // PCR timestamps are in ISO or UTC. Map to unix.
            const pcrUnix = pcrList.map(p => ({ ...p, unix: Math.floor(new Date(p.timestamp).getTime() / 1000) }));
            const relevant = pcrUnix.filter(p => p.unix <= currentTime);
            if (relevant.length > 0) activePCR = relevant[relevant.length - 1];
        }

        // Find nearest Snapshot
        const snapshotTimestamps = Array.from(this.replayHistory.snapshots.keys()).sort((a, b) => a - b);
        const relevantSnapTs = snapshotTimestamps.filter(ts => ts <= currentTime);
        if (relevantSnapTs.length > 0) {
            const nearestTs = relevantSnapTs[relevantSnapTs.length - 1];
            this.oiData = this.replayHistory.snapshots.get(nearestTs);
            if (this.showOiProfile) this.renderOiProfile();
        }

        // Update Sidebar if active
        if (showAnalysisSidebar && activeChartIndex === this.index) {
            this.renderReplaySidebar(activePCR);
        }
    }
    
    renderReplaySidebar(pcrData) {
        if (!pcrData) return;

        const pcrEl = document.getElementById('side-pcr');
        const powerEl = document.getElementById('side-power');
        if (pcrEl) pcrEl.textContent = pcrData.pcr_oi?.toFixed(2) || "-";
        if (powerEl) powerEl.textContent = (pcrData.total_oi_change > 500000 ? "STRONG" : pcrData.total_oi_change > 100000 ? "MODERATE" : "WEAK");

        // Update Logs with replay info
        const logList = document.getElementById('sideLogsList');
        const msg = `[REPLAY] ${formatIST(pcrData.timestamp)} | PCR: ${pcrData.pcr_oi} | Spot: ${pcrData.spot_price || pcrData.underlying_price}`;
        const p = document.createElement('p');
        p.className = 'border-b border-black/5 last:border-0 py-1 text-blue-500 font-bold';
        p.textContent = msg;
        logList.prepend(p);
        if (logList.children.length > 50) logList.lastElementChild.remove();
    }

    addHorizontalLine(price, color = '#3b82f6') {
        const line = this.candleSeries.createPriceLine({
            price: price, color: color, lineWidth: 2, lineStyle: LightweightCharts.LineStyle.Dotted, axisLabelVisible: false, title: 'HLINE'
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

let showAnalysisSidebar = false;

function init() {
    loadLayout();
    initLayoutSelector();
    initFullscreen();
    initIndicatorPanel();
    initDrawingControls();
    initTimeframeUI();
    initSearch();
    initZoomControls();
    initReplayControls();
    initAnalysisSidebar();
    initTheme();
    initSocket();

    window.addEventListener('resize', () => {
        charts.forEach(c => {
            const container = document.getElementById(c.containerId);
            if (container) {
                c.chart.resize(container.clientWidth, container.clientHeight);
                c.syncOiCanvas();
            }
        });
    });

    // Auto refresh sidebar every 60s
    setInterval(updateAnalysisSidebar, 60000);
}

function initAnalysisSidebar() {
    const toggle = document.getElementById('analysisToggle');
    const sidebar = document.getElementById('analysisSidebar');
    const closeBtn = document.getElementById('closeAnalysisBtn');
    const oiToggle = document.getElementById('oiProfileToggle');

    toggle.addEventListener('change', () => {
        showAnalysisSidebar = toggle.checked;
        sidebar.classList.toggle('hidden', !showAnalysisSidebar);
        if (showAnalysisSidebar) updateAnalysisSidebar();
    });

    closeBtn.addEventListener('click', () => {
        toggle.checked = false;
        sidebar.classList.add('hidden');
        showAnalysisSidebar = false;
    });

    oiToggle.addEventListener('change', () => {
        charts.forEach(c => {
            c.showOiProfile = oiToggle.checked;
            if (c.showOiProfile) c.fetchOiProfile();
            else c.renderOiProfile();
        });
    });
}

async function updateAnalysisSidebar() {
    if (!showAnalysisSidebar) return;
    const chart = charts[activeChartIndex];
    if (!chart) return;

    try {
        const [genie, buildup] = await Promise.all([
            fetch(`/api/options/genie-insights/${encodeURIComponent(chart.symbol)}`).then(r => r.json()),
            fetch(`/api/options/oi-buildup/${encodeURIComponent(chart.symbol)}`).then(r => r.json())
        ]);

        renderSidebarGenie(genie);
        renderSidebarBuildup(buildup);
    } catch (e) { console.error("Sidebar update failed:", e); }
}

function renderSidebarGenie(data) {
    const controlEl = document.getElementById('genieControl');
    const statusEl = document.getElementById('genieStatus');
    const rangeEl = document.getElementById('genieRange');
    const pcrEl = document.getElementById('sideCurrentPcr');

    controlEl.textContent = (data.control || "").replace(/_/g, ' ');
    if (data.control === 'BUYERS_IN_CONTROL') controlEl.className = 'text-xs font-black text-green-600 uppercase';
    else if (data.control === 'SELLERS_IN_CONTROL') controlEl.className = 'text-xs font-black text-red-600 uppercase';
    else controlEl.className = 'text-xs font-black text-gray-800 uppercase';

    statusEl.textContent = data.distribution?.status || "-";
    rangeEl.textContent = `RANGE: ${data.boundaries?.lower || "-"} - ${data.boundaries?.upper || "-"}`;

    if (pcrEl) {
        const pcr = data.pcr || 0;
        pcrEl.textContent = pcr.toFixed(2);
        pcrEl.className = `text-[9px] font-black ${pcr > 1.3 ? 'text-red-500' : pcr > 1.1 ? 'text-red-400' : pcr < 0.7 ? 'text-green-500' : pcr < 0.9 ? 'text-green-400' : 'text-blue-500'}`;
    }
}

function renderSidebarBuildup(data) {
    const container = document.getElementById('buildupSummary');
    container.innerHTML = '';
    const patterns = data.summary?.pattern_distribution || {};

    Object.entries(patterns).forEach(([p, count]) => {
        const div = document.createElement('div');
        div.className = 'p-2 bg-gray-100 rounded border border-black/5 text-center';
        let color = 'text-gray-500';
        if (p.includes('Long Buildup')) color = 'text-green-600';
        if (p.includes('Short Buildup')) color = 'text-red-600';
        if (p.includes('Short Covering')) color = 'text-blue-600';
        if (p.includes('Long Unwinding')) color = 'text-orange-600';

        div.innerHTML = `
            <div class="text-[7px] text-gray-400 uppercase font-black truncate">${p}</div>
            <div class="text-xs font-black ${color}">${count}</div>
        `;
        container.appendChild(div);
    });
}

function setActiveChart(chartInstance) {
    activeChartIndex = chartInstance.index;
    document.querySelectorAll('.chart-wrapper').forEach(w => w.classList.remove('active'));
    const activeWrapper = document.getElementById(chartInstance.containerId).parentElement;
    activeWrapper.classList.add('active');

    // Update header UI to reflect active chart state
    updateHeaderUI();
    if (showAnalysisSidebar) updateAnalysisSidebar();
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

function setLayout(n, overrideSymbol = null, overrideInterval = null) {
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

        if (i === 0 && overrideSymbol) {
            chartInstance.switchSymbol(overrideSymbol, overrideInterval || '1');
        } else {
            const saved = JSON.parse(localStorage.getItem(`chart_config_${i}`));
            if (saved) {
                chartInstance.symbol = saved.symbol || 'NSE:NIFTY';
                chartInstance.interval = saved.interval || '1';
                chartInstance.showIndicators = saved.showIndicators !== undefined ? saved.showIndicators : true;
                chartInstance.hiddenPlots = new Set(saved.hiddenPlots || []);
                chartInstance.colorOverrides = saved.colorOverrides || {};
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

    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            const symbol = searchInput.value.trim().toUpperCase();
            if (symbol) {
                const chart = charts[activeChartIndex];
                if (chart) chart.switchSymbol(symbol);
                resultsDiv.classList.add('hidden');
            }
        }
    });

    document.addEventListener('click', (e) => { if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) resultsDiv.classList.add('hidden'); });
}

function formatIST(ts) {
    if (!ts) return '-';
    const date = new Date(ts);
    return new Intl.DateTimeFormat('en-IN', {
        timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    }).format(date);
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
            const incomingKey = key.toUpperCase();
            charts.forEach(c => {
                // Strict match on technical instrument key to avoid data mixups
                if (c.symbol && c.symbol.toUpperCase() === incomingKey) {
                    c.updateRealtimeCandle(quote);
                }
            });
        }
    });

    socket.on('scalper_metrics', (data) => {
        if (!showAnalysisSidebar) return;
        const sideScalper = document.getElementById('sidebarScalper');
        sideScalper.classList.remove('hidden');

        document.getElementById('side-pcr').textContent = data.pcr;
        document.getElementById('side-power').textContent = data.oi_power;

        const updateDot = (id, active) => {
            const dot = document.getElementById(id);
            if (!dot) return;
            if (active) {
                dot.classList.remove('bg-gray-200');
                dot.classList.add('bg-blue-500');
            } else {
                dot.classList.add('bg-gray-200');
                dot.classList.remove('bg-blue-500');
            }
        };
        updateDot('conf-lvl-dot', data.confluence.lvl);
        updateDot('conf-pcr-dot', data.confluence.pcr);
        updateDot('conf-oi-dot', data.confluence.oi);
        updateDot('conf-brk-dot', data.confluence.opt_brk);
        updateDot('conf-inv-dot', data.confluence.inv_dwn);
    });

    socket.on('scalper_log', (data) => {
        const logList = document.getElementById('sideLogsList');
        const msg = data.message || `[${data.time}] ${data.signal} @ ${data.underlying_level}`;
        const p = document.createElement('p');
        p.className = 'border-b border-black/5 last:border-0 py-1';
        if (msg.includes('BUY')) p.className += ' text-green-600 font-bold';
        else if (msg.includes('CLOSED')) p.className += ' text-blue-600';
        else p.className += ' text-gray-500';

        p.textContent = msg;
        logList.prepend(p);
        if (logList.children.length > 50) logList.lastElementChild.remove();
    });

    socket.on('chart_update', (data) => {
        const updateKey = (data.instrumentKey || "").toUpperCase();
        const updateInterval = String(data.interval || "");
        charts.forEach(c => {
            // Strict match on technical instrument key and interval
            if (c.symbol && c.symbol.toUpperCase() === updateKey && String(c.interval) === updateInterval) {
                c.handleChartUpdate(data);
            }
        });
    });
}

async function fetchIntraday(key, interval) {
    try {
        const res = await fetch(`/api/tv/intraday/${encodeURIComponent(key)}?interval=${interval}`);
        const data = await res.json();
        if (data && data.candles) {
            data.candles = data.candles.map(c => ({
                timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
            })).reverse();
            return data;
        }
        return { hrn: '', candles: [], indicators: [] };
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
            colorOverrides: c.colorOverrides,
            drawings: c.drawings.map(d => ({ type: d.type, price: d.price, color: d.color }))
        };
        localStorage.setItem(`chart_config_${i}`, JSON.stringify(config));
    });
}

function loadLayout() {
    const params = new URLSearchParams(window.location.search);
    const urlSymbol = params.get('symbol');
    const urlInterval = params.get('interval');

    if (urlSymbol) {
        setLayout(1, urlSymbol.toUpperCase(), urlInterval);
    } else {
        const savedLayout = localStorage.getItem('prodesk_layout');
        setLayout(savedLayout ? parseInt(savedLayout) : 1);
    }
}

// --- Utils ---

function normalizeSymbol(sym) {
    if (!sym) return "";
    let s = String(sym).toUpperCase().trim();
    if (s.includes(':')) s = s.split(':')[1];
    if (s.includes('|')) s = s.split('|')[1];
    return s.split(' ')[0].replace("NIFTY 50", "NIFTY").replace("BANK NIFTY", "BANKNIFTY").replace("FIN NIFTY", "FINNIFTY");
}

function rgbaToHex(rgba) {
    if (!rgba) return '#3b82f6';
    if (rgba.startsWith('#')) return rgba;
    const parts = rgba.match(/[\d.]+/g);
    if (!parts || parts.length < 3) return '#3b82f6';
    const r = parseInt(parts[0]);
    const g = parseInt(parts[1]);
    const b = parseInt(parts[2]);
    return "#" + ((1 << 24) + (r << 16) + (g << 8) + b).toString(16).slice(1);
}

function tvColorToRGBA(color) {
    if (color === null || color === undefined) return null;
    if (typeof color === 'string') return color;
    if (typeof color === 'number') {
        // TradingView colors can be ARGB or similar packed integers.
        const uColor = color >>> 0;
        const a = ((uColor >> 24) & 0xFF) / 255;
        const r = (uColor >> 16) & 0xFF;
        const g = (uColor >> 8) & 0xFF;
        const b = uColor & 0xFF;
        // If alpha component is 0 in the bitmask, it's often intended to be opaque (1.0)
        // unless explicitly a transparency-based indicator.
        const alpha = ((uColor >> 24) & 0xFF) === 0 ? 1.0 : a;
        return `rgba(${r}, ${g}, ${b}, ${alpha})`;
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

function initTheme() {
    const btn = document.getElementById('themeToggleBtn');
    if (btn) {
        btn.addEventListener('click', () => {
            const isLight = document.body.classList.contains('light-theme');
            applyTheme(isLight ? 'dark' : 'light');
        });
    }
    applyTheme(localStorage.getItem('theme') || 'light');
}

function applyTheme(theme) {
    localStorage.setItem('theme', theme);
    const isLight = theme === 'light';

    if (isLight) {
        document.body.classList.add('light-theme');
        document.getElementById('sunIcon')?.classList.add('hidden');
        document.getElementById('moonIcon')?.classList.remove('hidden');
    } else {
        document.body.classList.remove('light-theme');
        document.getElementById('sunIcon')?.classList.remove('hidden');
        document.getElementById('moonIcon')?.classList.add('hidden');
    }

    const chartBg = isLight ? '#f8fafc' : '#0f172a';
    const chartText = isLight ? '#191919' : '#d1d5db';
    const gridColor = isLight ? '#f0f3fa' : 'rgba(255,255,255,0.05)';

    charts.forEach(c => {
        if (c.chart) {
            c.chart.applyOptions({
                layout: { background: { color: chartBg }, textColor: chartText },
                grid: { vertLines: { color: gridColor }, horzLines: { color: gridColor } },
                rightPriceScale: { borderColor: gridColor },
                timeScale: { borderColor: gridColor }
            });
            if (c.showOiProfile) c.renderOiProfile();
        }
    });
}

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
        const lastIdx = chart.fullHistory.candles.size - 1;
        if (lastIdx >= 0) chart.chart.timeScale().setVisibleLogicalRange({ from: lastIdx - 100, to: lastIdx + 10 });
    });
}

function initFullscreen() {
    const btn = document.getElementById('maximizeBtn');
    if (btn) {
        btn.addEventListener('click', () => {
            const chart = charts[activeChartIndex];
            if (chart) {
                const url = `${window.location.origin}${window.location.pathname}?symbol=${encodeURIComponent(chart.symbol)}&interval=${encodeURIComponent(chart.interval)}`;
                window.open(url, '_blank');
            }
        });
    }
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
    plotsHeader.innerText = 'Plots & Indicators';
    list.appendChild(plotsHeader);

    // Marker Toggle (Global for markers)
    if (chart.markers.length > 0) {
        const item = document.createElement('div');
        item.className = 'flex items-center justify-between bg-white/5 p-2 rounded-lg mb-2';
        const isHidden = chart.hiddenPlots.has('__markers__');
        item.innerHTML = `
            <span class="text-[10px] font-bold text-gray-300 truncate mr-2 italic">Global Markers Toggle</span>
            <button class="toggle-plot-btn text-[9px] font-black px-2 py-1 rounded ${isHidden ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}" data-key="__markers__">
                ${isHidden ? 'HIDDEN' : 'VISIBLE'}
            </button>
        `;
        item.querySelector('.toggle-plot-btn').addEventListener('click', () => {
            if (chart.hiddenPlots.has('__markers__')) {
                chart.hiddenPlots.delete('__markers__');
            } else {
                chart.hiddenPlots.add('__markers__');
            }
            chart.candleSeries.setMarkers(chart.showIndicators && !chart.hiddenPlots.has('__markers__') ? chart.markers : []);
            populateIndicatorList();
            saveLayout();
        });
        list.appendChild(item);

        // Unique marker types for color overriding
        const uniqueLabels = [...new Set(chart.markers.map(m => m.text).filter(t => t))];
        uniqueLabels.forEach(label => {
            const mItem = document.createElement('div');
            mItem.className = 'flex items-center justify-between bg-white/5 p-2 rounded-lg mb-1 ml-2';
            const sampleMarker = chart.markers.find(m => m.text === label);
            const currentColor = sampleMarker ? sampleMarker.color : '#3b82f6';

            mItem.innerHTML = `
                <div class="flex items-center truncate mr-2">
                    <input type="color" class="indicator-color-picker w-4 h-4 rounded cursor-pointer mr-2 border-0 bg-transparent" value="${rgbaToHex(currentColor)}">
                    <span class="text-[9px] font-bold text-gray-400 truncate">${label}</span>
                </div>
            `;
            mItem.querySelector('.indicator-color-picker').addEventListener('input', (e) => {
                const newColor = e.target.value;
                chart.colorOverrides[label] = newColor;
                chart.markers = chart.markers.map(m => m.text === label ? { ...m, color: newColor } : m);
                chart.candleSeries.setMarkers(chart.showIndicators && !chart.hiddenPlots.has('__markers__') ? chart.markers : []);
                saveLayout();
            });
            list.appendChild(mItem);
        });
    }

    Object.entries(chart.indicatorSeries).forEach(([key, series]) => {
        const title = series._backendTitle || key;
        const item = document.createElement('div');
        item.className = 'flex items-center justify-between bg-white/5 p-2 rounded-lg';

        const isHidden = chart.hiddenPlots.has(key);
        const currentColor = series.options().color;

        item.innerHTML = `
            <div class="flex items-center truncate mr-2">
                <input type="color" class="indicator-color-picker w-4 h-4 rounded cursor-pointer mr-2 border-0 bg-transparent" value="${rgbaToHex(currentColor)}">
                <span class="text-[10px] font-bold text-gray-300 truncate">${title}</span>
            </div>
            <button class="toggle-plot-btn text-[9px] font-black px-2 py-1 rounded ${isHidden ? 'bg-red-500/20 text-red-400' : 'bg-green-500/20 text-green-400'}" data-key="${key}">
                ${isHidden ? 'HIDDEN' : 'VISIBLE'}
            </button>
        `;

        item.querySelector('.indicator-color-picker').addEventListener('input', (e) => {
            const newColor = e.target.value;
            chart.colorOverrides[title] = newColor;
            series.applyOptions({ color: newColor });
            saveLayout();
        });

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

    if (chart.priceLines) {
        Object.entries(chart.priceLines).forEach(([key, line]) => {
            const title = line.options().title || key;
            const item = document.createElement('div');
            item.className = 'flex items-center justify-between bg-white/5 p-2 rounded-lg mt-1';
            const currentColor = line.options().color;

            item.innerHTML = `
                <div class="flex items-center truncate mr-2">
                    <input type="color" class="indicator-color-picker w-4 h-4 rounded cursor-pointer mr-2 border-0 bg-transparent" value="${rgbaToHex(currentColor)}">
                    <span class="text-[10px] font-bold text-blue-300 truncate">${title}</span>
                </div>
                <span class="text-[8px] text-gray-500 uppercase font-black">Line</span>
            `;

            item.querySelector('.indicator-color-picker').addEventListener('input', (e) => {
                const newColor = e.target.value;
                chart.colorOverrides[title] = newColor;
                line.applyOptions({ color: newColor });
                saveLayout();
            });
            list.appendChild(item);
        });
    }

    if (Object.keys(chart.indicatorSeries).length === 0 && (!chart.priceLines || Object.keys(chart.priceLines).length === 0)) {
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
        chart.candleSeries.setMarkers(chart.showIndicators && !chart.hiddenPlots.has('__markers__') ? chart.markers : []);
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
        chart.loadReplayHistory(); // Load historical options data
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
                if (chart.replayIndex < chart.fullHistory.candles.size - 1) chart.stepReplay(1);
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
        document.getElementById('replayStatus').innerText = `BAR ${chart.replayIndex + 1} / ${chart.fullHistory.candles.size}`;
    }
}

init();
