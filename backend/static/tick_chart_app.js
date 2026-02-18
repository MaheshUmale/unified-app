/**
 * PRODESK Tick Chart Engine v3.0
 * Pure tick-by-tick aggregation and rendering.
 */

class TickAggregator {
    constructor(tpc) {
        this.tpc = tpc;
        this.reset();
    }

    reset() {
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

    processTick(tick) {
        const price = Number(tick.price);
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
            if (ts <= this.lastTime) ts = this.lastTime + 1;
            this.lastTime = ts;

            this.currentCandle = {
                time: ts, open: price, high: price, low: price, close: price,
                volume: qty, delta: delta, cvd: this.cvd, footprint: {}
            };
            this.updateFootprint(this.currentCandle, price, side, qty);
            this.currentTickCount = 1;
            return { type: 'new', candle: this.currentCandle };
        } else {
            const c = this.currentCandle;
            c.high = Math.max(c.high, price);
            c.low = Math.min(c.low, price);
            c.close = price;
            c.volume += qty;
            c.delta += delta;
            c.cvd = this.cvd;
            this.updateFootprint(c, price, side, qty);
            this.currentTickCount++;
            return { type: 'update', candle: this.currentCandle };
        }
    }

    updateFootprint(candle, price, side, qty) {
        if (!candle.footprint[price]) candle.footprint[price] = { buy: 0, sell: 0 };
        if (side === 1) candle.footprint[price].buy += qty;
        else candle.footprint[price].sell += qty;

        const levels = Object.keys(candle.footprint).map(Number).sort((a,b) => a-b);
        let total = 0, maxV = 0, poc = levels[0];
        for (let p of levels) {
            const v = candle.footprint[p].buy + candle.footprint[p].sell;
            total += v;
            if (v > maxV) { maxV = v; poc = p; }
        }
        candle.poc = poc;

        let vaVol = total * 0.7, currentVa = maxV;
        let l = levels.indexOf(poc), u = l;
        while (currentVa < vaVol && (l > 0 || u < levels.length - 1)) {
            const lv = l > 0 ? (candle.footprint[levels[l-1]].buy + candle.footprint[levels[l-1]].sell) : 0;
            const uv = u < levels.length - 1 ? (candle.footprint[levels[u+1]].buy + candle.footprint[levels[u+1]].sell) : 0;
            if (lv >= uv) { currentVa += lv; l--; } else { currentVa += uv; u++; }
        }
        candle.vah = levels[u]; candle.val = levels[l];

        candle.imbalances = [];
        for (let i = 0; i < levels.length; i++) {
            const p = levels[i], { buy, sell } = candle.footprint[p];
            if (i > 0 && buy >= candle.footprint[levels[i-1]].sell * 3 && buy > 0) candle.imbalances.push({ price: p, side: 'buy' });
            if (i < levels.length - 1 && sell >= candle.footprint[levels[i+1]].buy * 3 && sell > 0) candle.imbalances.push({ price: p, side: 'sell' });
        }
    }
}

class TickChartManager {
    constructor() {
        this.socket = io();
        this.symbol = new URLSearchParams(window.location.search).get('symbol')?.toUpperCase() || 'NSE:NIFTY';
        this.aggregator = new TickAggregator(parseInt(new URLSearchParams(window.location.search).get('ticks')) || 100);
        this.candles = [];
        this.historicalTicks = [];
        this.isReplay = false;
        this.replayIdx = -1;
        this.isPlaying = false;
        this.init();
    }

    init() {
        this.setupChart();
        this.setupSocket();
        this.setupListeners();
        this.loadHistory();
    }

    setupChart() {
        const isLight = document.body.classList.contains('light-theme');
        const options = {
            layout: { background: { type: 'solid', color: 'transparent' }, textColor: isLight ? '#1e293b' : '#f8fafc' },
            grid: { vertLines: { color: 'rgba(255,255,255,0.05)' }, horzLines: { color: 'rgba(255,255,255,0.05)' } },
            timeScale: {
                timeVisible: true,
                secondsVisible: true,
                borderColor: 'rgba(255,255,255,0.1)',
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

        this.chart = LightweightCharts.createChart(document.getElementById('chart'), options);
        this.series = this.chart.addCandlestickSeries({ upColor: '#22c55e', downColor: '#ef4444' });
        this.cvdSeries = this.chart.addAreaSeries({ lineColor: '#3b82f6', topColor: 'rgba(59, 130, 246, 0.4)', bottomColor: 'transparent', priceScaleId: 'cvd' });
        this.chart.priceScale('cvd').applyOptions({ scaleMargins: { top: 0.85, bottom: 0 } });

        this.canvas = document.getElementById('footprint-canvas');
        this.ctx = this.canvas.getContext('2d');
        this.syncCanvas();

        this.chart.timeScale().subscribeVisibleLogicalRangeChange(() => this.renderFootprints());
        window.addEventListener('resize', () => {
            this.chart.resize(this.canvas.parentElement.clientWidth, this.canvas.parentElement.clientHeight);
            this.syncCanvas();
            this.renderFootprints();
        });
    }

    syncCanvas() {
        this.canvas.width = this.canvas.parentElement.clientWidth;
        this.canvas.height = this.canvas.parentElement.clientHeight;
    }

    renderFootprints() {
        if (!this.ctx) return;
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        const spacing = this.chart.timeScale().options().barSpacing;
        if (spacing < 45) return;

        this.candles.forEach(c => {
            const x = this.chart.timeScale().timeToCoordinate(c.time);
            if (x === null || x < 0 || x > this.canvas.width) return;
            this.drawFootprint(c, x, spacing);
        });
    }

    drawFootprint(c, x, spacing) {
        const levels = Object.keys(c.footprint).map(Number).sort((a,b) => b-a);
        const hw = spacing / 2;
        this.ctx.font = '8px "Plus Jakarta Sans"';

        levels.forEach(p => {
            const y = this.series.priceToCoordinate(p);
            if (y === null || y < 0 || y > this.canvas.height) return;
            const { buy, sell } = c.footprint[p];
            const isBuyI = c.imbalances.some(i => i.price === p && i.side === 'buy');
            const isSellI = c.imbalances.some(i => i.price === p && i.side === 'sell');

            if (isBuyI) { this.ctx.fillStyle = 'rgba(34, 197, 94, 0.2)'; this.ctx.fillRect(x, y-6, hw, 12); }
            else if (isSellI) { this.ctx.fillStyle = 'rgba(239, 68, 68, 0.2)'; this.ctx.fillRect(x-hw, y-6, hw, 12); }

            if (p === c.poc) { this.ctx.strokeStyle = '#fbbf24'; this.ctx.lineWidth = 1.5; this.ctx.strokeRect(x-hw, y-6, spacing, 12); }

            const formatV = (v) => {
                if (v >= 1000000) return (v / 1000000).toFixed(1) + 'M';
                if (v >= 1000) return (v / 1000).toFixed(1) + 'K';
                return v;
            };

            this.ctx.textAlign = 'right'; this.ctx.fillStyle = isSellI ? '#ef4444' : '#cbd5e1'; this.ctx.fillText(formatV(sell), x-4, y+3);
            this.ctx.textAlign = 'left'; this.ctx.fillStyle = isBuyI ? '#22c55e' : '#cbd5e1'; this.ctx.fillText(formatV(buy), x+4, y+3);
        });
    }

    async loadHistory() {
        this.updateStatus('Loading...', 'bg-yellow-500');
        const res = await fetch(`/api/ticks/history/${encodeURIComponent(this.symbol)}?limit=10000`).then(r => r.json());
        this.historicalTicks = res.history || [];
        if (!this.isReplay) this.renderTicks(this.historicalTicks);
        this.updateStatus(this.isReplay ? 'Replay' : 'Live', this.isReplay ? 'bg-blue-500' : 'bg-green-500');
    }

    renderTicks(ticks) {
        this.aggregator.reset();
        this.candles = [];
        ticks.forEach(t => {
            const r = this.aggregator.processTick(t);
            if (r.type === 'new') this.candles.push({ ...r.candle });
            else if (this.candles.length) this.candles[this.candles.length-1] = { ...r.candle };
        });

        this.series.setData(this.candles);
        this.cvdSeries.setData(this.candles.map(c => ({ time: c.time, value: c.cvd })));
        this.renderFootprints();
        if (this.candles.length) this.updateUI(this.candles[this.candles.length-1]);
    }

    updateUI(c) {
        document.getElementById('last-price').textContent = c.close.toFixed(2);
        const d = Math.round(c.delta), cvd = Math.round(c.cvd);
        document.getElementById('delta-info').textContent = `DELTA: ${d > 0 ? '+' : ''}${d} | CVD: ${cvd > 0 ? '+' : ''}${cvd}`;
        document.getElementById('delta-info').className = `text-xs font-black mt-1 ${d >= 0 ? 'text-green-500' : 'text-red-500'}`;
    }

    setupSocket() {
        this.socket.on('connect', () => this.socket.emit('subscribe', { instrumentKeys: [this.symbol] }));
        this.socket.on('raw_tick', (data) => {
            if (this.isReplay || !data[this.symbol]) return;
            const r = this.aggregator.processTick(data[this.symbol]);
            this.series.update(r.candle);
            this.cvdSeries.update({ time: r.candle.time, value: r.candle.cvd });
            if (r.type === 'new') this.candles.push({ ...r.candle });
            else this.candles[this.candles.length-1] = { ...r.candle };
            this.renderFootprints();
            this.updateUI(r.candle);
        });
    }

    setupListeners() {
        document.getElementById('ticks-input').addEventListener('change', (e) => {
            this.aggregator.setTicksPerCandle(parseInt(e.target.value) || 100);
            this.loadHistory();
        });
        document.getElementById('theme-toggle').addEventListener('click', () => {
            const isL = document.body.classList.toggle('light-theme');
            localStorage.setItem('theme', isL ? 'light' : 'dark');
            this.chart.applyOptions({ layout: { textColor: isL ? '#1e293b' : '#f8fafc' } });
        });
        document.getElementById('replay-mode-btn').addEventListener('click', () => this.toggleReplay(true));
        document.getElementById('exit-replay-btn').addEventListener('click', () => this.toggleReplay(false));
    }

    toggleReplay(on) {
        this.isReplay = on;
        document.getElementById('normal-controls').classList.toggle('hidden', on);
        document.getElementById('replay-controls').classList.toggle('hidden', !on);
        if (!on) { this.isPlaying = false; if (this.replayInterval) clearInterval(this.replayInterval); this.renderTicks(this.historicalTicks); }
        this.updateStatus(on ? 'Replay' : 'Live', on ? 'bg-blue-500' : 'bg-green-500');
    }

    updateStatus(text, color) {
        document.getElementById('status-text').textContent = text;
        document.getElementById('status-dot').className = `w-2 h-2 rounded-full ${color}`;
    }
}

// Bootstrap
document.addEventListener('DOMContentLoaded', () => {
    window.tickChart = new TickChartManager();
});
