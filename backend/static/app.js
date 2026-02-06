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
let bgSeries = null;
let indicatorSeries = {}; // Map of plot name -> series instance
let lastCandle = null;

// Replay State
let isReplayMode = false;
let replayIndex = -1;
let replayInterval = null;
let isPlaying = false;

// State
let fullHistory = { candles: [], volume: [], markers: new Map() };

// --- Initialization ---

function init() {
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
            localization: {
                locale: 'en-IN',
                timeFormatter: (timestamp) => {
                    return new Intl.DateTimeFormat('en-IN', {
                        timeZone: 'Asia/Kolkata',
                        hour: '2-digit',
                        minute: '2-digit',
                        hour12: false
                    }).format(new Date(timestamp * 1000));
                }
            },
            rightPriceScale: {
                borderColor: '#1f2937',
                autoScale: true,
                scaleMargins: {
                    top: 0.1,
                    bottom: 0.1,
                },
            },
            timeScale: {
                borderColor: '#1f2937',
                timeVisible: true,
                secondsVisible: false,
                tickMarkFormatter: (time, tickMarkType, locale) => {
                    const date = new Date(time * 1000);
                    const formatter = (options) => new Intl.DateTimeFormat('en-IN', { ...options, timeZone: 'Asia/Kolkata' }).format(date);

                    switch (tickMarkType) {
                        case LightweightCharts.TickMarkType.Year:
                            return formatter({ year: 'numeric' });
                        case LightweightCharts.TickMarkType.Month:
                            return formatter({ month: 'short' });
                        case LightweightCharts.TickMarkType.DayOfMonth:
                            return formatter({ day: 'numeric' });
                        case LightweightCharts.TickMarkType.Time:
                            return formatter({ hour: '2-digit', minute: '2-digit', hour12: false });
                        case LightweightCharts.TickMarkType.TimeWithSeconds:
                            return formatter({ hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
                    }
                }
            },
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

        bgSeries = mainChart.addHistogramSeries({
            priceScaleId: 'bg',
            lastValueVisible: false,
            priceLineVisible: false,
        });

        mainChart.priceScale('bg').applyOptions({
            scaleMargins: { top: 0, bottom: 0 },
            visible: false,
        });

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

    // Clear previous indicators and markers
    Object.values(indicatorSeries).forEach(obj => mainChart.removeSeries(obj.series));
    indicatorSeries = {};
    fullHistory.markers.clear();

    setLoading(true);
    try {
        const resData = await fetchIntraday(currentSymbol, currentInterval);
        let candles = resData.candles || [];

        // Filter for market hours (9:15 - 15:30 IST) for NSE symbols on intraday timeframes
        if (candles && candles.length > 0 && currentSymbol.startsWith('NSE:') && !['D', 'W'].includes(currentInterval)) {
            candles = candles.filter(c => {
                const ts = typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000);
                const date = new Date(ts * 1000);
                const istTime = new Intl.DateTimeFormat('en-GB', {
                    timeZone: 'Asia/Kolkata', hour: 'numeric', minute: 'numeric', hourCycle: 'h23'
                }).format(date);
                const [h, m] = istTime.split(':').map(Number);
                const mins = h * 60 + m;
                return mins >= 555 && mins <= 930;
            });
        }

        console.log(`Processed ${candles ? candles.length : 0} candles for ${currentSymbol}`);

        // Handle historical indicators if present
        if (resData.indicators) {
            handleChartUpdate({ indicators: resData.indicators });
        }

        if (candles && candles.length > 0) {
            const chartData = candles.map(c => ({
                time: typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000),
                open: c.open, high: c.high, low: c.low, close: c.close
            })).sort((a, b) => a.time - b.time);
            const volData = candles.map(c => ({
                time: typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000),
                value: c.volume,
                color: c.close >= c.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
            })).sort((a, b) => a.time - b.time);
            fullHistory.candles = chartData;
            fullHistory.volume = volData;
            if (!fullHistory.markers) fullHistory.markers = new Map();

            renderData();
            lastCandle = chartData[chartData.length - 1];
            lastCandle.volume = candles[candles.length - 1].volume;

            // Set visible range to last 100 bars instead of fitContent
            const lastIndex = chartData.length - 1;
            mainChart.timeScale().setVisibleLogicalRange({
                from: lastIndex - 100,
                to: lastIndex + 5,
            });
        }
        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    } catch (e) {
        console.error("Switch symbol failed:", e);
    } finally { setLoading(false); }
}

async function fetchIntraday(key, interval = '1') {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    let url = `/api/tv/intraday/${encodeURIComponent(key)}?interval=${interval}`;
    const res = await fetch(url, { signal: controller.signal });
    clearTimeout(timeoutId);
    const data = await res.json();
    if (data && data.candles) {
        data.candles = data.candles.map(c => ({
            timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
        })).reverse();
    }
    return data || { candles: [] };
}

function initSocket() {
    socket.on('connect', () => {
        console.log("Socket connected:", socket.id);
        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    });
    socket.on('disconnect', (reason) => {
        console.warn("Socket disconnected:", reason);
        if (reason === "io server disconnect") {
            // the disconnection was initiated by the server, you need to reconnect manually
            socket.connect();
        }
    });
    socket.on('connect_error', (error) => {
        console.error("Socket connection error:", error);
    });
    socket.on('raw_tick', (data) => handleTickUpdate(typeof data === 'string' ? JSON.parse(data) : data));
    socket.on('chart_update', (data) => handleChartUpdate(data));
}

function handleTickUpdate(quotes) {
    // If we're getting fresh chart updates, prefer them over raw ticks to avoid conflicts
    if (Date.now() - lastChartUpdateTime < 2000) return;

    const currentNorm = normalizeSymbol(currentSymbol);
    for (const [key, quote] of Object.entries(quotes)) {
        if (normalizeSymbol(key) === currentNorm) { updateRealtimeCandle(quote); break; }
    }
}

let lastChartUpdateTime = 0;

function tvColorToRGBA(color) {
    if (typeof color !== 'number') return color;
    const a = ((color >>> 24) & 0xFF) / 255;
    const r = (color >>> 16) & 0xFF;
    const g = (color >>> 8) & 0xFF;
    const b = (color & 0xFF);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function handleChartUpdate(data) {
    lastChartUpdateTime = Date.now();
    if (data.ohlcv && data.ohlcv.length > 0) {
        // Handle OHLCV update from chart session
        const candles = data.ohlcv.map(v => ({
            time: Math.floor(v[0]), open: v[1], high: v[2], low: v[3], close: v[4]
        }));
        const vol = data.ohlcv.map(v => ({
            time: Math.floor(v[0]), value: v[5],
            color: v[4] >= v[1] ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
        }));

        if (candles.length > 1) {
            fullHistory.candles = candles;
            fullHistory.volume = vol;
            if (!fullHistory.markers) fullHistory.markers = new Map();
            renderData();
            lastCandle = candles[candles.length - 1];
            lastCandle.volume = data.ohlcv[data.ohlcv.length-1][5];
        } else if (candles.length === 1) {
            if (lastCandle && candles[0].time >= lastCandle.time) {
                candleSeries.update(candles[0]);
                volumeSeries.update(vol[0]);
                lastCandle = {...candles[0], volume: vol[0].value};
            }
        }
    }

    if (data.indicators && data.indicators.length > 0) {
        const barColors = {}; // time -> color
        const bgColors = {}; // time -> color

        data.indicators.forEach(row => {
            const time = Math.floor(row.timestamp);

            if (row.Bar_Color) {
                barColors[time] = tvColorToRGBA(row.Bar_Color);
            }
            if (row.Background_Color) {
                bgColors[time] = tvColorToRGBA(row.Background_Color);
            }

            Object.keys(row).forEach(key => {
                if (key === 'timestamp' || key === 'Bar_Color' || key === 'Background_Color' || key.endsWith('_meta')) return;

                const meta = row[`${key}_meta`];
                const val = row[key];
                if (val === null || typeof val !== 'number' || val >= 1e10) return;

                let color = meta ? tvColorToRGBA(meta.color) : '#3b82f6';
                if (row[`${key}_color`]) {
                    color = tvColorToRGBA(row[`${key}_color`]);
                }

                const plottype = meta ? meta.type : 0;
                const title = meta ? meta.title : key;

                // Handle Shapes/Dots/Bubbles as Markers
                if (plottype >= 3 || title.includes('Bubble') || title.includes('Dot') || title.includes('TF')) {
                    let shape = 'circle';
                    let position = 'inBar';
                    if (title.includes('Bubble')) {
                        shape = 'circle';
                        const candle = fullHistory.candles.find(c => c.time === time);
                        position = (candle && val > candle.close) ? 'aboveBar' : 'belowBar';
                    } else if (title.includes('R') || title.includes('High') || title.includes('Resistance')) {
                        shape = 'circle'; // Use circles for S/R as in the image
                        position = 'aboveBar';
                    } else if (title.includes('S') || title.includes('Low') || title.includes('Support')) {
                        shape = 'circle';
                        position = 'belowBar';
                    } else if (title.includes('TF')) {
                        shape = 'circle';
                        position = 'inBar';
                    }

                    const markerKey = `${time}_${key}`;
                    fullHistory.markers.set(markerKey, {
                        time: time,
                        position: position,
                        color: color,
                        shape: shape,
                        size: title.includes('Bubble') ? 2 : 1
                    });
                    return;
                }

                let series = indicatorSeries[key];
                if (!series) {
                    if (plottype === 1 || plottype === 2) {
                        series = mainChart.addHistogramSeries({
                            color: color,
                            title: title,
                            priceScaleId: 'right',
                            autoscaleInfoProvider: () => null,
                        });
                    } else if (plottype === 5 || plottype === 4) {
                        series = mainChart.addAreaSeries({
                            topColor: color,
                            bottomColor: 'transparent',
                            lineColor: color,
                            lineWidth: meta ? meta.linewidth : 1,
                            title: title,
                            priceScaleId: 'right',
                            autoscaleInfoProvider: () => null,
                        });
                    } else {
                        series = mainChart.addLineSeries({
                            color: color,
                            lineWidth: meta ? meta.linewidth : 1,
                            lineStyle: (meta && meta.linestyle === 2) ? 2 : 0,
                            title: title,
                            priceScaleId: 'right',
                            autoscaleInfoProvider: () => null,
                        });
                    }
                    indicatorSeries[key] = { series, lastTime: 0 };
                }

                if (time >= indicatorSeries[key].lastTime) {
                    indicatorSeries[key].series.update({ time: time, value: val });
                    indicatorSeries[key].lastTime = time;
                }
            });
        });

        // Apply Markers (persistent from fullHistory)
        if (fullHistory.markers.size > 0) {
            const allMarkers = Array.from(fullHistory.markers.values());
            candleSeries.setMarkers(allMarkers.sort((a,b) => a.time - b.time));
        }

        // Apply Bar Colors
        if (Object.keys(barColors).length > 0) {
            const updatedCandles = fullHistory.candles.map(c => {
                if (barColors[c.time]) {
                    return { ...c, color: barColors[c.time], wickColor: barColors[c.time], borderColor: barColors[c.time] };
                }
                return c;
            });
            candleSeries.setData(updatedCandles);
            fullHistory.candles = updatedCandles;
        }

        // Apply Background Colors
        if (Object.keys(bgColors).length > 0) {
            const bgData = Object.keys(bgColors).map(t => ({
                time: parseInt(t),
                value: 1000000, // Large enough to cover range
                color: bgColors[t]
            })).sort((a,b) => a.time - b.time);
            bgSeries.setData(bgData);
        }
    }
}

function updateRealtimeCandle(quote) {
    if (!candleSeries) return;

    // Map interval to duration in seconds
    const intervalMap = { '1': 60, '5': 300, '15': 900, '30': 1800, '60': 3600, 'D': 86400, 'W': 604800 };
    const duration = intervalMap[currentInterval] || 60;

    // Adjust for IST offset (5.5 hours) for day boundary calculations
    const IST_OFFSET = 5.5 * 3600;
    const tickTime = Math.floor(quote.ts_ms / 1000);

    // Drop ticks outside market hours (9:15 - 15:30 IST) for NSE symbols
    if (currentSymbol.startsWith('NSE:') && !['D', 'W'].includes(currentInterval)) {
        const date = new Date(tickTime * 1000);
        const istTime = new Intl.DateTimeFormat('en-GB', {
            timeZone: 'Asia/Kolkata', hour: 'numeric', minute: 'numeric', hourCycle: 'h23'
        }).format(date);
        const [h, m] = istTime.split(':').map(Number);
        const mins = h * 60 + m;
        if (mins < 555 || mins > 930) return;
    }

    // For intervals >= 1 Day, we need to snap to IST midnight, not UTC midnight
    let candleTime;
    if (duration >= 86400) {
        candleTime = (Math.floor((tickTime + IST_OFFSET) / duration) * duration) - IST_OFFSET;
    } else {
        candleTime = tickTime - (tickTime % duration);
    }

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
        renderData();
    } else if (candleTime === lastCandle.time) {
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


function renderData() {
    if (fullHistory.candles.length === 0) return;
    candleSeries.setData(fullHistory.candles);
    volumeSeries.setData(fullHistory.volume);
    // Markers are set by handleChartUpdate
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
        renderData();
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
        candleSeries.setData(vC);
        volumeSeries.setData(vV);
        // Note: Markers could also be subsetted here if they were stored in fullHistory
        lastCandle = {...vC[vC.length - 1]};
        document.getElementById('replayStatus').innerText = `BAR ${replayIndex + 1} / ${fullHistory.candles.length}`;
    }
}

try { init(); } catch (e) { console.error("Initialization failed:", e); }
