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
let graphicsSeries = {}; // Map of graphic ID -> series instance
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
            borderVisible: true,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
            priceScaleId: 'right',
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

    // Clear previous indicators, markers and graphics
    Object.values(indicatorSeries).forEach(obj => mainChart.removeSeries(obj.series));
    indicatorSeries = {};
    Object.values(graphicsSeries).forEach(s => mainChart.removeSeries(s));
    graphicsSeries = {};
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

        if (candles && candles.length > 0) {
            const chartData = candles.map(c => ({
                time: typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000),
                open: c.open, high: c.high, low: c.low, close: c.close
            })).sort((a, b) => a.time - b.time);
            fullHistory.candles = chartData;
            lastCandle = chartData[chartData.length - 1];
        }

        // Handle historical indicators if present
        if (resData.indicators) {
            handleChartUpdate({ indicators: resData.indicators });
        }

        if (candles && candles.length > 0) {
            const volData = candles.map(c => ({
                time: typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000),
                value: c.volume,
                color: c.close >= c.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
            })).sort((a, b) => a.time - b.time);

            fullHistory.volume = volData;
            if (!fullHistory.markers) fullHistory.markers = new Map();

            renderData();
            lastCandle.volume = candles[candles.length - 1].volume;

            // Set visible range to last 100 bars instead of fitContent
            const lastIndex = fullHistory.candles.length - 1;
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
    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 30000);
        let url = `/api/tv/intraday/${encodeURIComponent(key)}?interval=${interval}`;
        const res = await fetch(url, { signal: controller.signal });
        clearTimeout(timeoutId);
        const data = await res.json();
        if (data && data.candles && data.candles.length > 0) {
            data.candles = data.candles.map(c => ({
                timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
            })).reverse();
            return data;
        }
        throw new Error("No candles returned from API");
    } catch (err) {
        console.warn("Fetch intraday failed, using mock data:", err);
        return generateMockData();
    }
}

function generateMockData() {
    const candles = [];
    const indicators = [];
    let now = Math.floor(Date.now() / 1000);
    let price = 25000;
    for (let i = 0; i < 100; i++) {
        const t = now - (100 - i) * 60;
        const o = price + Math.random() * 20 - 10;
        const h = o + Math.random() * 15;
        const l = o - Math.random() * 15;
        const c = l + Math.random() * (h - l);
        price = c;
        candles.push({ timestamp: t, open: o, high: h, low: l, close: c, volume: Math.random() * 1000 });
        const row = { timestamp: t, "MA": price + Math.sin(i / 10) * 50 };
        row["MA_meta"] = { title: "MA", type: 0, color: -16744193, linewidth: 2 };
        if (i % 20 === 0) {
            row["Bubble"] = price + 20;
            row["Bubble_meta"] = { title: "Bubble", type: 3, color: -16744193 };
        }
        indicators.push(row);
    }
    return { candles: candles.reverse(), indicators };
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
    // TradingView alpha is sometimes inverted or different.
    // We try to ensure it's at least partially visible if it's very transparent.
    let a = ((color >>> 24) & 0xFF) / 255;
    if (a < 0.2) a = 0.6; // Boost visibility if too transparent

    const r = (color >>> 16) & 0xFF;
    const g = (color >>> 8) & 0xFF;
    const b = (color & 0xFF);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function getMarkerConfig(title, val, candle) {
    let shape = 'circle';
    let position = 'inBar';

    if (title.includes('Bubble')) {
        shape = 'circle';
        position = (candle && val > candle.close) ? 'aboveBar' : 'belowBar';
    } else if (title.includes('R') || title.includes('High') || title.includes('Resistance')) {
        shape = 'circle';
        position = 'aboveBar';
    } else if (title.includes('S') || title.includes('Low') || title.includes('Support')) {
        shape = 'circle';
        position = 'belowBar';
    } else if (title.includes('TF')) {
        shape = 'circle';
        position = 'inBar';
    }

    return { shape, position };
}

function handleChartUpdate(data) {
    lastChartUpdateTime = Date.now();
    if (data.ohlcv && data.ohlcv.length > 0) {
        // Handle OHLCV update from chart session
        // Check if v[0] is index or timestamp.
        // Timestamps are usually > 1e9.
        const isTimestamp = data.ohlcv[0][0] > 1e9;

        if (isTimestamp) {
            const candles = data.ohlcv.map(v => ({
                time: Math.floor(v[0]),
                open: Number(v[1]), high: Number(v[2]), low: Number(v[3]), close: Number(v[4])
            }));
            const vol = data.ohlcv.map(v => ({
                time: Math.floor(v[0]), value: Number(v[5]),
                color: Number(v[4]) >= Number(v[1]) ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
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

                // Update fullHistory to keep it synced
                const idx = fullHistory.candles.findIndex(c => c.time === candles[0].time);
                if (idx !== -1) {
                    fullHistory.candles[idx] = candles[0];
                    fullHistory.volume[idx] = vol[0];
                } else {
                    fullHistory.candles.push(candles[0]);
                    fullHistory.volume.push(vol[0]);
                }

                lastCandle = {...candles[0], volume: vol[0].value};
            }
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

                // Filter out plots that look like part of a plotcandle (O, H, L, C)
                // These often have titles containing "Open", "High", "Low", "Close" or "plot_N".
                const lowerTitle = title.toLowerCase();
                if ((lowerTitle.includes('candle') || lowerTitle.includes('plot_')) &&
                    (lowerTitle.includes('open') || lowerTitle.includes('high') ||
                     lowerTitle.includes('low') || lowerTitle.includes('close') ||
                     /\d+/.test(lowerTitle))) {

                    // Specific check for plot_7, plot_8, plot_9, plot_10 which are common O/H/L/C plots
                    if (['plot_7', 'plot_8', 'plot_9', 'plot_10'].includes(title)) {
                        return;
                    }

                    // If it's very close to OHLC and has generic title, skip it
                    if (lastCandle && Math.abs(val - lastCandle.close) / lastCandle.close < 0.01) {
                         // Likely redundant plot
                         return;
                    }
                }

                // Handle Shapes/Dots/Bubbles as Markers
                if (plottype >= 3 || title.includes('Bubble') || title.includes('Dot') || title.includes('TF')) {
                    const candle = fullHistory.candles.find(c => c.time === time);
                    const config = getMarkerConfig(title, val, candle);

                    const markerKey = `${time}_${key}`;
                    fullHistory.markers.set(markerKey, {
                        time: time,
                        position: config.position,
                        color: color,
                        shape: config.shape,
                        size: title.includes('Bubble') ? 2 : 1
                    });
                    return;
                }

                let series = indicatorSeries[key];
                if (!series) {
                    // Determine if this is a price-based indicator or an oscillator (like z-score)
                    let targetScale = 'right';

                    // Use last candle or historical candles to estimate current price level
                    const referencePrice = lastCandle ? lastCandle.close :
                                         (fullHistory.candles.length > 0 ? fullHistory.candles[fullHistory.candles.length-1].close : null);

                    // Heuristic: If value is small (< 1000) and far from current price, it's likely an oscillator.
                    // Also check for specific keywords in title.
                    const isOscillator = (val < 1000 && (!referencePrice || Math.abs(val - referencePrice) > referencePrice * 0.5));

                    if (isOscillator && !title.toLowerCase().includes('pivot') && !title.toLowerCase().includes('vwap') && !title.toLowerCase().includes('ma')) {
                        targetScale = 'oscillator';
                        mainChart.priceScale(targetScale).applyOptions({
                            visible: false, // Keep oscillators hidden from Y-axis
                        });
                    }

                    const commonOptions = {
                        title: title,
                        priceScaleId: targetScale,
                        // By default, return null for priceRange to exclude from auto-scaling.
                        // This prevents oscillators on the main scale from squashing candles.
                        autoscaleInfoProvider: () => ({ priceRange: null }),
                    };

                    // For indicators on the main price scale, we only want them to scale
                    // if they are actually within a reasonable range of the price.
                    if (targetScale === 'right') {
                        commonOptions.autoscaleInfoProvider = () => {
                            if (!lastCandle) return null;
                            return {
                                priceRange: {
                                    minValue: lastCandle.low * 0.8,
                                    maxValue: lastCandle.high * 1.2,
                                }
                            };
                        };
                    }

                    if (plottype === 1 || plottype === 2) {
                        series = mainChart.addHistogramSeries({
                            ...commonOptions,
                            color: color,
                        });
                    } else if (plottype === 5) {
                        series = mainChart.addAreaSeries({
                            ...commonOptions,
                            topColor: color,
                            bottomColor: 'transparent',
                            lineColor: color,
                            lineWidth: meta ? meta.linewidth : 1,
                        });
                    } else {
                        // plottype 0 (Line) or 4 (Line with breaks) or others
                        series = mainChart.addLineSeries({
                            ...commonOptions,
                            color: color,
                            lineWidth: meta ? meta.linewidth : 1,
                            lineStyle: (meta && meta.linestyle === 2) ? 2 : 0,
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
                value: 1e12, // Extremely large to cover any price range
                color: bgColors[t]
            })).sort((a,b) => a.time - b.time);
            bgSeries.setData(bgData);
        }
    }

    if (data.graphics && data.graphics.length > 0) {
        data.graphics.forEach(g => {
            // Basic line object support
            if (g.v && g.v.length >= 4) {
                const [t1, p1, t2, p2] = g.v;
                const id = g.id || `line_${t1}_${p1}`;
                let series = graphicsSeries[id];
                if (!series) {
                    series = mainChart.addLineSeries({
                        color: g.c ? tvColorToRGBA(g.c) : '#ffffff',
                        lineWidth: g.w || 1,
                        priceScaleId: 'right',
                        autoscaleInfoProvider: () => ({ priceRange: null }),
                    });
                    graphicsSeries[id] = series;
                }
                series.setData([
                    { time: Math.floor(t1), value: p1 },
                    { time: Math.floor(t2), value: p2 }
                ]);
            }
        });
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

    // Use a fresh copy to avoid mutation issues
    candleSeries.setData([...fullHistory.candles].sort((a,b) => a.time - b.time));
    volumeSeries.setData([...fullHistory.volume].sort((a,b) => a.time - b.time));

    // If we have markers, re-apply them
    if (fullHistory.markers && fullHistory.markers.size > 0) {
        const allMarkers = Array.from(fullHistory.markers.values());
        candleSeries.setMarkers(allMarkers.sort((a,b) => a.time - b.time));
    }
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
