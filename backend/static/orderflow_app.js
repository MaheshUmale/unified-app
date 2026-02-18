/**
 * PRODESK Advanced Order Flow Terminal - REIMPLEMENTED
 */

class OrderFlowEngine {
    constructor(tpc = 100, priceStep = 0.05) {
        this.tpc = tpc;
        this.priceStep = priceStep;
        this.reset();
    }

    reset() {
        this.ticks = [];
        this.candles = [];
        this.currentCandle = null;
        this.tickCount = 0;
        this.cvd = 0;
        this.lastPrice = 0;
        this.lastSide = 1; // 1 for Buy (Up), -1 for Sell (Down)
    }

    setParams(tpc, priceStep) {
        this.tpc = tpc || this.tpc;
        this.priceStep = priceStep || this.priceStep;
    }

    processTick(tick, isReaggregating = false) {
        const rawPrice = Number(tick.price);
        if (isNaN(rawPrice) || rawPrice <= 0) return null;

        const price = Number((Math.round(rawPrice / this.priceStep) * this.priceStep).toFixed(2));
        const qty = Number(tick.qty || 0);
        let ts = Math.floor(tick.ts_ms / 1000);

        if (isNaN(ts) || ts <= 0) ts = Math.floor(Date.now() / 1000);

        // Tick Rule for Aggressor Side
        let side = this.lastSide;
        if (price > this.lastPrice) side = 1;
        else if (price < this.lastPrice) side = -1;

        const delta = side * qty;
        this.cvd += delta;
        this.lastPrice = price;
        this.lastSide = side;

        // Always cache ticks unless it's an internal re-aggregation of already cached ticks
        if (!isReaggregating) {
            this.ticks.push({ ts_ms: tick.ts_ms, price: rawPrice, qty: qty });
            if (this.ticks.length > 20000) this.ticks.shift();
        }

        if (!this.currentCandle || this.tickCount >= this.tpc) {
            // Finalize previous candle analytics
            if (this.currentCandle) this.calculateAnalytics(this.currentCandle);

            // New Candle
            if (this.currentCandle && ts <= this.currentCandle.time) {
                ts = this.currentCandle.time + 1;
            }

            this.currentCandle = {
                time: ts,
                open: price, high: price, low: price, close: price,
                volume: qty, delta: delta, cvd: this.cvd,
                footprint: {},
                imbalances: [],
                poc: price, vah: price, val: price
            };
            this.updateFootprint(this.currentCandle, price, side, qty);
            this.tickCount = 1;
            this.candles.push(this.currentCandle);
            if (this.candles.length > 1000) this.candles.shift();
            return { type: 'new', candle: this.currentCandle };
        } else {
            // Update Current Candle
            const c = this.currentCandle;
            c.high = Math.max(c.high, price);
            c.low = Math.min(c.low, price);
            c.close = price;
            c.volume += qty;
            c.delta += delta;
            c.cvd = this.cvd;
            this.updateFootprint(c, price, side, qty);
            this.tickCount++;
            return { type: 'update', candle: this.currentCandle };
        }
    }

    updateFootprint(candle, price, side, qty) {
        if (!candle.footprint[price]) {
            candle.footprint[price] = { buy: 0, sell: 0 };
        }
        if (side === 1) candle.footprint[price].buy += qty;
        else candle.footprint[price].sell += qty;

        const now = Date.now();
        if (!candle._lastCalc || now - candle._lastCalc > 250) {
            this.calculateAnalytics(candle);
            candle._lastCalc = now;
        }
    }

    calculateAnalytics(candle) {
        const fp = candle.footprint;
        const prices = Object.keys(fp).map(Number).sort((a, b) => a - b);
        if (prices.length === 0) return;

        let totalVol = 0;
        let maxVol = 0;
        let poc = prices[0];

        for (const p of prices) {
            const vol = fp[p].buy + fp[p].sell;
            totalVol += vol;
            if (vol > maxVol) {
                maxVol = vol;
                poc = p;
            }
        }

        candle.poc = poc;

        const targetVaVol = totalVol * 0.7;
        let currentVaVol = maxVol;
        let lIdx = prices.indexOf(poc);
        let uIdx = lIdx;

        while (currentVaVol < targetVaVol && (lIdx > 0 || uIdx < prices.length - 1)) {
            const lVol = lIdx > 0 ? (fp[prices[lIdx - 1]].buy + fp[prices[lIdx - 1]].sell) : 0;
            const uVol = uIdx < prices.length - 1 ? (fp[prices[uIdx + 1]].buy + fp[prices[uIdx + 1]].sell) : 0;

            if (lIdx > 0 && (lVol >= uVol || uIdx === prices.length - 1)) {
                currentVaVol += lVol;
                lIdx--;
            } else if (uIdx < prices.length - 1) {
                currentVaVol += uVol;
                uIdx++;
            } else break;
        }

        candle.vah = prices[uIdx];
        candle.val = prices[lIdx];

        candle.imbalances = [];
        for (let i = 0; i < prices.length; i++) {
            const p = prices[i];
            const buyV = fp[p].buy;
            const sellV = fp[p].sell;

            if (i > 0) {
                const sellBelow = fp[prices[i - 1]].sell;
                if (buyV >= sellBelow * 3 && buyV > 0 && sellBelow > 0) {
                    candle.imbalances.push({ price: p, side: 'buy' });
                }
            }
            if (i < prices.length - 1) {
                const buyAbove = fp[prices[i + 1]].buy;
                if (sellV >= buyAbove * 3 && sellV > 0 && buyAbove > 0) {
                    candle.imbalances.push({ price: p, side: 'sell' });
                }
            }
        }
    }
}

class CanvasRenderer {
    constructor(canvas, chart, series) {
        this.canvas = canvas;
        this.ctx = canvas.getContext('2d');
        this.chart = chart;
        this.series = series;
        this.colors = {
            bull: '#00ffc2',
            bear: '#ff3366',
            poc: '#fbbf24',
            va: 'rgba(255, 255, 255, 0.08)',
            muted: '#7d8590'
        };
    }

    render(candles) {
        if (!this.ctx || !this.chart || !candles || candles.length === 0) return;

        const timeScale = this.chart.timeScale();
        const spacing = timeScale.options().barSpacing;

        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        if (spacing < 45) return;

        const visibleCandles = candles.filter(c => {
            const x = timeScale.timeToCoordinate(c.time);
            return x !== null && x > -spacing && x < this.canvas.width + spacing;
        });

        for (const c of visibleCandles) {
            this.drawFootprint(c, timeScale, spacing);
        }
    }

    drawFootprint(candle, timeScale, spacing) {
        const x = timeScale.timeToCoordinate(candle.time);
        const fp = candle.footprint;
        const prices = Object.keys(fp).map(Number).sort((a, b) => b - a);
        const halfWidth = (spacing / 2) * 0.95;

        if (candle.vah && candle.val) {
            const vY1 = this.series.priceToCoordinate(candle.vah);
            const vY2 = this.series.priceToCoordinate(candle.val);
            if (vY1 !== null && vY2 !== null) {
                this.ctx.fillStyle = this.colors.va;
                this.ctx.fillRect(x - halfWidth - 2, vY1 - 6, halfWidth * 2 + 4, vY2 - vY1 + 12);
                this.ctx.strokeStyle = 'rgba(255,255,255,0.2)';
                this.ctx.setLineDash([2, 2]);
                this.ctx.strokeRect(x - halfWidth - 2, vY1 - 6, halfWidth * 2 + 4, vY2 - vY1 + 12);
                this.ctx.setLineDash([]);
            }
        }

        let maxDelta = 1;
        for (const p of prices) {
            const d = Math.abs(fp[p].buy - fp[p].sell);
            if (d > maxDelta) maxDelta = d;
        }

        for (const p of prices) {
            const y = this.series.priceToCoordinate(p);
            if (y === null || y < -10 || y > this.canvas.height + 10) continue;

            const data = fp[p];
            const buy = data.buy;
            const sell = data.sell;
            const delta = buy - sell;
            const intensity = Math.min(Math.abs(delta) / maxDelta, 1.0);

            const isBuyImb = candle.imbalances.some(imb => imb.price === p && imb.side === 'buy');
            const isSellImb = candle.imbalances.some(imb => imb.price === p && imb.side === 'sell');

            if (isBuyImb) {
                this.ctx.fillStyle = `rgba(0, 255, 194, ${0.1 + intensity * 0.5})`;
                this.ctx.fillRect(x, y - 6, halfWidth, 12);
            } else if (isSellImb) {
                this.ctx.fillStyle = `rgba(255, 51, 102, ${0.1 + intensity * 0.5})`;
                this.ctx.fillRect(x - halfWidth, y - 6, halfWidth, 12);
            }

            if (p === candle.poc) {
                this.ctx.strokeStyle = this.colors.poc;
                this.ctx.lineWidth = 1.5;
                this.ctx.strokeRect(x - halfWidth, y - 6, halfWidth * 2, 12);
                this.ctx.lineWidth = 1;
            }

            this.ctx.font = 'bold 8px "IBM Plex Mono"';
            this.ctx.textAlign = 'right';
            this.ctx.fillStyle = isSellImb ? this.colors.bear : (delta < 0 ? '#ff99aa' : this.colors.muted);
            this.ctx.fillText(sell, x - 3, y + 3);

            this.ctx.textAlign = 'left';
            this.ctx.fillStyle = isBuyImb ? this.colors.bull : (delta > 0 ? '#99ffdd' : this.colors.muted);
            this.ctx.fillText(buy, x + 3, y + 3);

            this.ctx.strokeStyle = 'rgba(255,255,255,0.1)';
            this.ctx.beginPath();
            this.ctx.moveTo(x, y-4);
            this.ctx.lineTo(x, y+4);
            this.ctx.stroke();
        }
    }
}

class ChartUI {
    constructor(engine) {
        this.engine = engine;
        this.charts = {};
        this.socket = io();
        this.currentSymbol = 'NSE:NIFTY';
        this.renderer = null;
        this.isReaggregating = false;
        this.markers = [];
    }

    init() {
        const urlParams = new URLSearchParams(window.location.search);
        this.currentSymbol = (urlParams.get('symbol') || 'NSE:NIFTY').toUpperCase();
        document.getElementById('display-symbol').textContent = this.currentSymbol;

        const tpc = parseInt(urlParams.get('ticks')) || 100;
        const step = parseFloat(urlParams.get('step')) || 0.05;
        this.engine.setParams(tpc, step);
        document.getElementById('ticks-input').value = tpc;
        document.getElementById('step-input').value = step.toFixed(2);

        this.initCharts();
        this.setupSocket();
        this.setupListeners();
        this.loadHistory();
        this.loadSentiment();
    }

    initCharts() {
        const chartOptions = {
            layout: { background: { type: 'solid', color: 'transparent' }, textColor: '#7d8590' },
            grid: { vertLines: { color: 'rgba(255,255,255,0.03)' }, horzLines: { color: 'rgba(255,255,255,0.03)' } },
            crosshair: { mode: 0 },
            timeScale: { borderColor: 'rgba(255,255,255,0.1)', timeVisible: true, secondsVisible: true },
            rightPriceScale: { borderColor: 'rgba(255,255,255,0.1)' }
        };

        this.charts.main = LightweightCharts.createChart(document.getElementById('main-chart'), chartOptions);
        this.charts.candles = this.charts.main.addCandlestickSeries({
            upColor: '#00ffc2', downColor: '#ff3366', borderVisible: false, wickUpColor: '#00ffc2', wickDownColor: '#ff3366'
        });

        this.charts.cvd = LightweightCharts.createChart(document.getElementById('cvd-chart'), {
            ...chartOptions,
            timeScale: { visible: false }
        });
        this.charts.cvdSeries = this.charts.cvd.addAreaSeries({
            lineColor: '#3b82f6', topColor: 'rgba(59, 130, 246, 0.3)', bottomColor: 'transparent', lineWidth: 2
        });

        this.charts.main.timeScale().subscribeVisibleLogicalRangeChange(range => {
            this.charts.cvd.timeScale().setVisibleLogicalRange(range);
        });

        const canvas = document.getElementById('footprint-canvas');
        this.renderer = new CanvasRenderer(canvas, this.charts.main, this.charts.candles);

        const updateRenderer = () => {
            this.renderer.render(this.engine.candles);
        };

        this.charts.main.timeScale().subscribeVisibleLogicalRangeChange(updateRenderer);

        window.addEventListener('resize', () => {
            const wrapper = document.getElementById('chart-wrapper');
            const cvdWrapper = document.getElementById('cvd-chart');
            if (!wrapper || !cvdWrapper) return;
            this.charts.main.applyOptions({ width: wrapper.clientWidth, height: wrapper.clientHeight });
            this.charts.cvd.applyOptions({ width: cvdWrapper.clientWidth, height: cvdWrapper.clientHeight });
            canvas.width = wrapper.clientWidth;
            canvas.height = wrapper.clientHeight;
            updateRenderer();
        });

        setTimeout(() => window.dispatchEvent(new Event('resize')), 100);
    }

    setupSocket() {
        this.socket.on('connect', () => {
            this.socket.emit('subscribe', { instrumentKeys: [this.currentSymbol] });
            this.updateStatus('Live', 'bg-[#00ffc2]');
        });

        this.socket.on('raw_tick', (data) => {
            try {
                if (data[this.currentSymbol]) {
                    const tick = data[this.currentSymbol];
                    if (!tick.last_price || tick.last_price <= 0) return;

                    const res = this.engine.processTick({
                        price: tick.last_price,
                        qty: tick.ltq || 1,
                        ts_ms: tick.ts_ms || Date.now()
                    });

                    if (res && res.candle) {
                        this.charts.candles.update(res.candle);
                        this.charts.cvdSeries.update({ time: res.candle.time, value: res.candle.cvd });

                        if (res.type === 'new') {
                            this.calculateMarkersForCandle(this.engine.candles.length - 2);
                            this.calculateMarkersForCandle(this.engine.candles.length - 1);
                        } else {
                            this.calculateMarkersForCandle(this.engine.candles.length - 1);
                        }

                        requestAnimationFrame(() => this.renderer.render(this.engine.candles));
                        this.updateUI(res.candle);
                    }
                }
            } catch (e) {
                console.error("Error processing raw_tick:", e);
            }
        });

        // Fallback: Listen to chart_update for price movements if raw_tick is missing
        this.socket.on('chart_update', (data) => {
            try {
                if (data.ohlcv && data.ohlcv.length > 0) {
                    const lastCandle = data.ohlcv[data.ohlcv.length - 1];
                    const [ts, o, h, l, c, v] = lastCandle;

                    // If the price is different from our engine's last price, treat it as a tick
                    if (Math.abs(c - this.engine.lastPrice) > 0.01) {
                        const res = this.engine.processTick({
                            price: c,
                            qty: 0, // No footprint data from OHLCV, but updates price
                            ts_ms: ts * 1000
                        });
                        if (res && res.candle) {
                            this.charts.candles.update(res.candle);
                            this.updateUI(res.candle);
                            requestAnimationFrame(() => this.renderer.render(this.engine.candles));
                        }
                    }
                }
            } catch (e) {
                console.warn("Error processing chart_update fallback:", e);
            }
        });
    }

    setupListeners() {
        document.getElementById('ticks-input').addEventListener('change', (e) => {
            this.engine.tpc = parseInt(e.target.value) || 100;
            this.reaggregate();
        });

        document.getElementById('step-input').addEventListener('change', (e) => {
            this.engine.priceStep = parseFloat(e.target.value) || 0.05;
            this.reaggregate();
        });

        document.getElementById('replay-btn').addEventListener('click', () => {
            window.location.href = `/tick?symbol=${this.currentSymbol}&ticks=${this.engine.tpc}`;
        });
    }

    updateStatus(text, colorClass) {
        document.getElementById('status-text').textContent = text;
        const dot = document.getElementById('status-dot');
        if (dot) dot.className = `w-1.5 h-1.5 rounded-full ${colorClass} shadow-[0_0_8px_rgba(0,255,194,0.5)]`;
    }

    updateUI(candle) {
        document.getElementById('last-price').textContent = candle.close.toFixed(2);
        const deltaEl = document.getElementById('delta-summary');
        deltaEl.textContent = `DELTA: ${Math.round(candle.delta)} | CVD: ${Math.round(candle.cvd)}`;
        deltaEl.className = `text-[11px] font-black mt-1 ${candle.delta >= 0 ? 'text-[#00ffc2]' : 'text-[#ff3366]'}`;
    }

    calculateMarkersForCandle(idx) {
        if (idx < 1 || idx >= this.engine.candles.length) return;
        const c = this.engine.candles[idx];
        const p = this.engine.candles[idx - 1];

        // Remove old markers for this timestamp
        this.markers = this.markers.filter(m => m.time !== c.time);

        const buyImbs = c.imbalances.filter(imb => imb.side === 'buy');
        const sellImbs = c.imbalances.filter(imb => imb.side === 'sell');

        let marker = null;
        if (buyImbs.length >= 3) {
            marker = { time: c.time, position: 'belowBar', color: '#00ffc2', shape: 'arrowUp', text: 'STACKED BUY' };
        } else if (sellImbs.length >= 3) {
            marker = { time: c.time, position: 'aboveBar', color: '#ff3366', shape: 'arrowDown', text: 'STACKED SELL' };
        } else if (c.low < p.low && c.cvd > p.cvd) {
            marker = { time: c.time, position: 'belowBar', color: '#3b82f6', shape: 'circle', text: 'BULL DIV' };
        } else if (c.high > p.high && c.cvd < p.cvd) {
            marker = { time: c.time, position: 'aboveBar', color: '#3b82f6', shape: 'circle', text: 'BEAR DIV' };
        }

        if (marker) {
            this.markers.push(marker);
            this.charts.candles.setMarkers(this.markers);
            if (!c._logged) {
                this.addSignalLog(marker.text, `Pattern detected at ${c.close.toFixed(2)}`, marker.color);
                c._logged = true;
            }
        }
    }

    async loadHistory() {
        this.updateStatus('Loading...', 'bg-yellow-500');
        try {
            const res = await fetch(`/api/ticks/history/${encodeURIComponent(this.currentSymbol)}?limit=15000`);
            const data = await res.json();
            let ticks = data.history || [];

            if (ticks.length < 50) {
                ticks = this.generateSimulatedHistory();
            }

            this.engine.reset();
            // IMPORTANT: isReaggregating=false ensures ticks are cached for future re-aggregation
            for (const t of ticks) {
                this.engine.processTick(t, false);
            }

            this.charts.candles.setData(this.engine.candles);
            this.charts.cvdSeries.setData(this.engine.candles.map(c => ({ time: c.time, value: c.cvd })));

            this.markers = [];
            for (let i = 1; i < this.engine.candles.length; i++) {
                this.calculateMarkersForCandle(i);
            }

            this.renderer.render(this.engine.candles);
            if (this.engine.candles.length > 0) {
                this.charts.main.timeScale().applyOptions({ barSpacing: 60 });
                this.updateUI(this.engine.candles[this.engine.candles.length - 1]);
            }
            this.updateStatus('Live', 'bg-[#00ffc2]');
        } catch (err) {
            console.error(err);
            this.updateStatus('Error', 'bg-red-500');
        }
    }

    reaggregate() {
        if (this.isReaggregating) return;
        this.isReaggregating = true;
        document.getElementById('reaggregate-overlay').classList.remove('hidden');

        setTimeout(() => {
            const cachedTicks = [...this.engine.ticks];
            this.engine.reset();
            for (const t of cachedTicks) {
                this.engine.processTick(t, true);
            }
            this.engine.ticks = cachedTicks;

            this.charts.candles.setData(this.engine.candles);
            this.charts.cvdSeries.setData(this.engine.candles.map(c => ({ time: c.time, value: c.cvd })));

            this.markers = [];
            for (let i = 1; i < this.engine.candles.length; i++) {
                this.calculateMarkersForCandle(i);
            }

            this.renderer.render(this.engine.candles);
            document.getElementById('reaggregate-overlay').classList.add('hidden');
            this.isReaggregating = false;
        }, 100);
    }

    async loadSentiment() {
        try {
            const res = await fetch(`/api/modern/data/${encodeURIComponent(this.currentSymbol)}`);
            const data = await res.json();
            if (data && !data.error) {
                this.updateSentimentUI(data);
            }
        } catch (e) { console.warn("Sentiment fail", e); }
    }

    updateSentimentUI(data) {
        const pcr = data.genie?.pcr || 1.0;
        const sentimentVal = document.getElementById('sentiment-value');
        const pcrVal = document.getElementById('pcr-value');
        if (!sentimentVal || !pcrVal) return;

        if (pcr > 1.1) {
            sentimentVal.textContent = 'BULLISH';
            sentimentVal.className = 'text-3xl font-black italic text-[#00ffc2] tracking-tighter';
        } else if (pcr < 0.9) {
            sentimentVal.textContent = 'BEARISH';
            sentimentVal.className = 'text-3xl font-black italic text-[#ff3366] tracking-tighter';
        } else {
            sentimentVal.textContent = 'NEUTRAL';
            sentimentVal.className = 'text-3xl font-black italic text-gray-500 tracking-tighter';
        }
        const oiChange = data.oi_buildup?.total_oi_change || 0;
        pcrVal.textContent = `PCR: ${pcr.toFixed(2)} | OI: ${(oiChange/1000000).toFixed(1)}M | PAIN: ${data.genie?.max_pain || '-'}`;
    }

    addSignalLog(type, message, color) {
        const list = document.getElementById('signals-list');
        if (!list) return;
        if (list.querySelector('.italic')) list.innerHTML = '';

        const div = document.createElement('div');
        div.className = 'bg-black/40 p-3 rounded-lg border-l-4 mb-2 border-opacity-50';
        div.style.borderLeftColor = color;
        div.innerHTML = `
            <div class="flex justify-between items-center mb-1">
                <span class="text-[9px] font-black uppercase px-2 py-0.5 rounded" style="background: ${color}22; color: ${color}">${type}</span>
                <span class="text-[8px] text-gray-600 mono">${new Date().toLocaleTimeString()}</span>
            </div>
            <p class="text-[10px] text-gray-400 font-medium">${message}</p>
        `;
        list.prepend(div);
        if (list.childNodes.length > 30) list.lastChild.remove();
    }

    generateSimulatedHistory() {
        const ticks = [];
        let price = 25500 + Math.random() * 200;
        let ts = Date.now() - 3600000;
        for (let i = 0; i < 2000; i++) {
            price += (Math.random() - 0.5) * 1.5;
            ts += Math.floor(Math.random() * 500) + 100;
            ticks.push({ ts_ms: ts, price: price, qty: Math.floor(Math.random() * 100) + 10 });
        }
        return ticks;
    }
}

// Bootstrap
window.addEventListener('DOMContentLoaded', () => {
    const engine = new OrderFlowEngine();
    const ui = new ChartUI(engine);
    window.uiInstance = ui; // Expose for debugging
    ui.init();
});
