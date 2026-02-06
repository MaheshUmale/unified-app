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
let indicatorSeries = {}; // Registry for indicator series

// Replay State
let isReplayMode = false;
let replayIndex = -1;
let replayInterval = null;
let isPlaying = false;

// State
let fullHistory = { candles: [], volume: [] };

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
    fullHistory = { candles: [], volume: [] };

    // Clear all chart data
    candleSeries.setData([]);
    volumeSeries.setData([]);
    candleSeries.setMarkers([]);

    // Clear indicator series
    Object.values(indicatorSeries).forEach(s => mainChart.removeSeries(s));
    indicatorSeries = {};

    setLoading(true);
    try {
        const resData = await fetchIntraday(currentSymbol, currentInterval);
        let candles = resData.candles || [];

        // Filter for market hours (9:15 - 15:30 IST) for NSE symbols on intraday timeframes ONLY for today's data
        if (candles && candles.length > 0 && currentSymbol.startsWith('NSE:') && !['D', 'W'].includes(currentInterval)) {
            const todayIST = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: 'numeric', day: 'numeric' }).format(new Date());

            candles = candles.filter(c => {
                const ts = typeof c.timestamp === 'number' ? c.timestamp : Math.floor(new Date(c.timestamp).getTime() / 1000);
                const date = new Date(ts * 1000);
                const dateIST = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Kolkata', year: 'numeric', month: 'numeric', day: 'numeric' }).format(date);

                // If it's not today, don't filter by market hours (allow viewing historical backfills)
                if (dateIST !== todayIST) return true;

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
                open: Number(c.open), high: Number(c.high), low: Number(c.low), close: Number(c.close), volume: Number(c.volume)
            })).filter(c => !isNaN(c.open) && c.open > 0)
              .sort((a, b) => a.time - b.time);
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
        return { candles: [], indicators: [] }; // Return empty instead of throwing to avoid generic mock pollution
    } catch (err) {
        console.warn("Fetch intraday failed:", err);
        return { candles: [], indicators: [] };
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
    const currentUpper = currentSymbol.toUpperCase();
    const currentNorm = normalizeSymbol(currentSymbol);
    for (const [key, quote] of Object.entries(quotes)) {
        const keyUpper = key.toUpperCase();
        // Match either normalized symbol (e.g. BTCUSD) or full technical key (COINBASE:BTCUSD)
        if (keyUpper === currentUpper || normalizeSymbol(key) === currentNorm) {
            updateRealtimeCandle(quote);
            break;
        }
    }
}

let lastChartUpdateTime = 0;

function tvColorToRGBA(color) {
    if (color === null || color === undefined) return null;
    if (typeof color !== 'number') return color;
    let a = ((color >>> 24) & 0xFF) / 255;
    if (a === 0) a = 1; // Default to opaque if 0

    const r = (color >>> 16) & 0xFF;
    const g = (color >>> 8) & 0xFF;
    const b = (color & 0xFF);
    return `rgba(${r}, ${g}, ${b}, ${a})`;
}

function handleChartUpdate(data) {
    lastChartUpdateTime = Date.now();

    // Clear old indicators if symbol changed (handled by fullHistory reset usually)

    if (data.ohlcv && data.ohlcv.length > 0) {
        // Handle OHLCV update from chart session
        // Timestamps are usually > 1e9.
        const isTimestamp = data.ohlcv[0][0] > 1e9;

        if (isTimestamp) {
            const candles = data.ohlcv.map(v => ({
                time: Math.floor(v[0]),
                open: Number(v[1]), high: Number(v[2]), low: Number(v[3]), close: Number(v[4])
            })).filter(c => !isNaN(c.open) && c.open > 0);

            const vol = data.ohlcv.map(v => ({
                time: Math.floor(v[0]), value: Number(v[5]),
                color: Number(v[4]) >= Number(v[1]) ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
            }));

            if (candles.length > 1) {
                fullHistory.candles = candles;
                fullHistory.volume = vol;
                lastCandle = candles[candles.length - 1];
                lastCandle.volume = data.ohlcv[data.ohlcv.length-1][5];
                renderData();
            } else if (candles.length === 1) {
                const newCandle = candles[0];
                const newVol = vol[0];

                if (lastCandle && newCandle.time >= lastCandle.time) {
                    candleSeries.update(newCandle);
                    volumeSeries.update(newVol);

                    // Update fullHistory to keep it synced
                    const idx = fullHistory.candles.findIndex(c => c.time === newCandle.time);
                    if (idx !== -1) {
                        fullHistory.candles[idx] = newCandle;
                        fullHistory.volume[idx] = newVol;
                    } else {
                        fullHistory.candles.push(newCandle);
                        fullHistory.volume.push(newVol);
                    }

                    lastCandle = {...newCandle, volume: newVol.value};
                } else if (!lastCandle) {
                    fullHistory.candles = [newCandle];
                    fullHistory.volume = [newVol];
                    renderData();
                    lastCandle = {...newCandle, volume: newVol.value};
                }
            }
        }
    }

    if (data.indicators && data.indicators.length > 0) {
        processIndicators(data.indicators);
    }
}

function processIndicators(indicators) {
    const markers = [];
    const seriesUpdates = {};

    indicators.forEach(row => {
        const time = Math.floor(row.timestamp);

        // Find Bar Color
        if (row.Bar_Color !== undefined) {
            const candle = fullHistory.candles.find(c => c.time === time);
            if (candle) {
                const color = tvColorToRGBA(row.Bar_Color);
                candle.color = color;
                candle.wickColor = color;
                candle.borderColor = color;
                candle.hasExplicitColor = true;
            }
        }

        // Process Plots
        Object.entries(row).forEach(([key, val]) => {
            if (key === 'timestamp' || key === 'Bar_Color' || key.endsWith('_meta') || key.endsWith('_color')) return;
            if (val === null || val === undefined) return;

            const meta = row[`${key}_meta`];
            const color = tvColorToRGBA(row[`${key}_color`] || (meta ? meta.color : null));

            if (meta && (meta.title.includes('Bubble') || meta.title.includes('S') || meta.title.includes('R'))) {
                // Marker indicators
                let shape = 'circle';
                let position = 'inBar';
                let text = '';
                let size = 1;

                if (meta.title.includes('Bubble')) {
                    position = 'aboveBar';
                    size = 2;
                } else if (meta.title.includes('S')) {
                    position = 'belowBar';
                    shape = meta.title.includes('3') ? 'square' : 'circle';
                    size = meta.title.includes('3') ? 1 : meta.title.includes('2') ? 0.5 : 0.2;
                } else if (meta.title.includes('R')) {
                    position = 'aboveBar';
                    shape = meta.title.includes('3') ? 'square' : 'circle';
                    size = meta.title.includes('3') ? 1 : meta.title.includes('2') ? 0.5 : 0.2;
                }

                markers.push({
                    time: time,
                    position: position,
                    color: color || '#3b82f6',
                    shape: shape,
                    size: size,
                    text: text
                });
            } else {
                // Line indicators
                if (!seriesUpdates[key]) seriesUpdates[key] = [];
                seriesUpdates[key].push({ time: time, value: val, color: color });
            }
        });
    });

    // Update markers
    if (markers.length > 0) {
        markers.sort((a,b) => a.time - b.time);
        candleSeries.setMarkers(markers);
    }

    // Update Line Series
    Object.entries(seriesUpdates).forEach(([key, points]) => {
        if (!indicatorSeries[key]) {
            indicatorSeries[key] = mainChart.addLineSeries({
                title: key,
                lineWidth: 2,
                priceScaleId: 'right',
                autoscaleInfoProvider: () => null, // Don't let indicators squash the price scale
            });
        }
        points.sort((a,b) => a.time - b.time);
        indicatorSeries[key].setData(points);
    });
}

function updateRealtimeCandle(quote) {
    if (!candleSeries || isReplayMode) return;

    // Map interval to duration in seconds
    const intervalMap = { '1': 60, '5': 300, '15': 900, '30': 1800, '60': 3600, 'D': 86400, 'W': 604800 };
    const duration = intervalMap[currentInterval] || 60;

    const tickTime = Math.floor(quote.ts_ms / 1000);
    const candleTime = tickTime - (tickTime % duration);

    const price = Number(quote.last_price);
    if (isNaN(price) || price <= 0) return;
    const ltq = Number(quote.ltq || 0);

    if (!lastCandle || candleTime > lastCandle.time) {
        if (lastCandle) {
            // Check if lastCandle is already in fullHistory
            if (!fullHistory.candles.some(c => c.time === lastCandle.time)) {
                fullHistory.candles.push({...lastCandle});
                fullHistory.volume.push({
                    time: lastCandle.time, value: lastCandle.volume,
                    color: lastCandle.close >= lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
                });
            }
        }
        lastCandle = { time: candleTime, open: price, high: price, low: price, close: price, volume: ltq };
        candleSeries.update(lastCandle);
        volumeSeries.update({
            time: candleTime, value: ltq,
            color: 'rgba(59, 130, 246, 0.5)'
        });
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


function calculateSMA(data, period) {
    const result = [];
    for (let i = 0; i < data.length; i++) {
        if (i < period - 1) {
            result.push(null);
            continue;
        }
        let sum = 0;
        for (let j = 0; j < period; j++) {
            sum += data[i - j];
        }
        result.push(sum / period);
    }
    return result;
}

function applyRvolColoring(candles) {
    if (candles.length < 2) return candles;

    const volumes = candles.map(c => c.volume || 0);
    // Use smaller period if not enough data
    const period = Math.min(20, candles.length);
    const sma = calculateSMA(volumes, period);

    return candles.map((c, i) => {
        const s = sma[i];
        if (!s || s === 0) return c;

        const volumePercent = c.volume / s;
        const isUp = c.close >= c.open;

        let cCol;
        if (volumePercent >= 3) {
            cCol = isUp ? '#007504' : 'rgb(137, 1, 1)';
        } else if (volumePercent >= 2) {
            cCol = isUp ? 'rgb(3, 179, 9)' : '#d30101';
        } else {
            let opacity;
            if (volumePercent >= 1.6) opacity = 0.9;
            else if (volumePercent >= 1.2) opacity = 0.7;
            else if (volumePercent >= 0.8) opacity = 0.4;
            else if (volumePercent >= 0.5) opacity = 0.2;
            else opacity = 0.1;

            const r = isUp ? 3 : 211;
            const g = isUp ? 179 : 1;
            const b = isUp ? 9 : 1;
            cCol = `rgba(${r}, ${g}, ${b}, ${opacity})`;
        }

        return { ...c, color: cCol, wickColor: cCol, borderColor: cCol };
    });
}

function renderData() {
    if (fullHistory.candles.length === 0) return;

    // Apply RVOL coloring if candles don't already have explicit colors
    let displayCandles = [...fullHistory.candles].sort((a,b) => a.time - b.time);
    const hasExplicitColors = displayCandles.some(c => c.hasExplicitColor);

    if (!hasExplicitColors) {
        displayCandles = applyRvolColoring(displayCandles);
    }

    candleSeries.setData(displayCandles);
    volumeSeries.setData([...fullHistory.volume].sort((a,b) => a.time - b.time));
}

// --- Utils & Controls ---

function normalizeSymbol(sym) {
    if (!sym) return "";
    let s = String(sym).toUpperCase().trim();
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
        const timeScale = mainChart.timeScale();
        const currentSpacing = timeScale.options().barSpacing;
        timeScale.applyOptions({ barSpacing: Math.min(50, currentSpacing * 1.2) });
    });
    document.getElementById(btns.out).addEventListener('click', () => {
        const timeScale = mainChart.timeScale();
        const currentSpacing = timeScale.options().barSpacing;
        timeScale.applyOptions({ barSpacing: Math.max(0.1, currentSpacing / 1.2) });
    });
    document.getElementById(btns.res).addEventListener('click', () => {
        mainChart.timeScale().reset();
        const lastIndex = fullHistory.candles.length - 1;
        if (lastIndex >= 0) {
            mainChart.timeScale().setVisibleLogicalRange({
                from: lastIndex - 100,
                to: lastIndex + 5,
            });
        }
    });
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
