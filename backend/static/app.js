/**
 * PRODESK Simplified Application
 * Handles Socket.IO connection and TradingView Lightweight Charts rendering.
 */

const socket = io();

// UI State
let currentSymbol = 'NSE:NIFTY';
let mainChart = null;
let candleSeries = null;
let volumeSeries = null;
let lastCandle = null;

// Replay State
let isReplayMode = false;
let fullHistory = { candles: [], volume: [] };
let replayIndex = -1;
let replayInterval = null;
let isPlaying = false;

// --- Initialization ---

function init() {
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
            crosshair: {
                mode: LightweightCharts.CrosshairMode.Normal,
            },
            rightPriceScale: {
                borderColor: '#1f2937',
                autoScale: true,
            },
            timeScale: {
                borderColor: '#1f2937',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        candleSeries = mainChart.addCandlestickSeries({
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
        });

        // Use a separate price scale for volume to prevent squashing candles
        volumeSeries = mainChart.addHistogramSeries({
            color: '#3b82f6',
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // Separate overlay scale
        });

        volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });

        window.addEventListener('resize', () => {
            mainChart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
        });

        // Click to select replay start
        mainChart.subscribeClick((param) => {
            if (isReplayMode && param.time && replayIndex === -1) {
                const clickedTime = param.time;
                const index = fullHistory.candles.findIndex(c => c.time === clickedTime);
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

    // Initial load
    switchSymbol(currentSymbol);
}

function initSearch() {
    const searchInput = document.getElementById('symbolSearch');
    const resultsDiv = document.getElementById('searchResults');
    let debounceTimer;

    searchInput.addEventListener('input', (e) => {
        clearTimeout(debounceTimer);
        const text = e.target.value.trim();
        if (text.length < 2) {
            resultsDiv.classList.add('hidden');
            return;
        }

        debounceTimer = setTimeout(async () => {
            try {
                const res = await fetch(`/api/tv/search?text=${encodeURIComponent(text)}`);
                const data = await res.json();
                if (data && data.symbols) {
                    displaySearchResults(data.symbols);
                }
            } catch (err) {
                console.error("Search failed:", err);
            }
        }, 300);
    });

    document.addEventListener('click', (e) => {
        if (!searchInput.contains(e.target) && !resultsDiv.contains(e.target)) {
            resultsDiv.classList.add('hidden');
        }
    });
}

function displaySearchResults(symbols) {
    const resultsDiv = document.getElementById('searchResults');
    resultsDiv.innerHTML = '';

    if (symbols.length === 0) {
        resultsDiv.classList.add('hidden');
        return;
    }

    symbols.forEach(s => {
        const item = document.createElement('div');
        item.className = 'px-3 py-2 hover:bg-gray-800 cursor-pointer border-b border-gray-800 last:border-0';
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
        const candles = await fetchIntraday(currentSymbol);
        if (candles && candles.length > 0) {
            const chartData = candles.map(c => ({
                time: Math.floor(new Date(c.timestamp).getTime() / 1000),
                open: c.open,
                high: c.high,
                low: c.low,
                close: c.close
            })).sort((a, b) => a.time - b.time);

            const volData = candles.map(c => ({
                time: Math.floor(new Date(c.timestamp).getTime() / 1000),
                value: c.volume,
                color: c.close >= c.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
            })).sort((a, b) => a.time - b.time);

            fullHistory = { candles: chartData, volume: volData };

            if (!isReplayMode) {
                candleSeries.setData(chartData);
                volumeSeries.setData(volData);
                lastCandle = chartData[chartData.length - 1];
                lastCandle.volume = candles[candles.length - 1].volume;
            } else {
                // If switching symbol while in replay mode, reset replay
                document.getElementById('exitReplayBtn').click();
            }

            // Auto fit content
            mainChart.timeScale().fitContent();
        } else {
            candleSeries.setData([]);
            volumeSeries.setData([]);
            fullHistory = { candles: [], volume: [] };
        }

        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    } catch (e) {
        console.error("Switch symbol failed:", e);
        // Fallback for demonstration if API fails
        if (currentSymbol === 'NSE:NIFTY' || currentSymbol.includes('BTCUSD')) {
            generateMockData();
        }
    } finally {
        setLoading(false);
    }
}

function generateMockData() {
    const now = Math.floor(Date.now() / 1000);
    const mockCandles = [];
    const mockVolume = [];
    let price = 25000;
    for (let i = 0; i < 100; i++) {
        const t = now - (100 - i) * 60;
        const o = price + Math.random() * 20 - 10;
        const c = o + Math.random() * 20 - 10;
        const h = Math.max(o, c) + Math.random() * 5;
        const l = Math.min(o, c) - Math.random() * 5;
        mockCandles.push({ time: t, open: o, high: h, low: l, close: c });
        mockVolume.push({ time: t, value: Math.random() * 1000, color: c >= o ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)' });
        price = c;
    }
    fullHistory = { candles: mockCandles, volume: mockVolume };
    candleSeries.setData(mockCandles);
    volumeSeries.setData(mockVolume);
    lastCandle = {...mockCandles[mockCandles.length - 1]};
    mainChart.timeScale().fitContent();
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
    socket.on('connect', () => {
        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    });

    socket.on('raw_tick', (data) => {
        const rawData = typeof data === 'string' ? JSON.parse(data) : data;
        handleTickUpdate(rawData);
    });
}

function handleTickUpdate(quotes) {
    const entries = Object.entries(quotes);
    const currentNorm = normalizeSymbol(currentSymbol);
    for (const [key, quote] of entries) {
        const tickNorm = normalizeSymbol(key);
        if (tickNorm === currentNorm) {
            updateRealtimeCandle(quote);
            break;
        }
    }
}

function updateRealtimeCandle(quote) {
    if (!candleSeries || isReplayMode) return;

    const tickTime = Math.floor(quote.ts_ms / 1000);
    const candleTime = tickTime - (tickTime % 60); // 1-min alignment
    const price = quote.last_price;
    const ltq = quote.ltq || 0;

    if (!lastCandle || candleTime > lastCandle.time) {
        lastCandle = {
            time: candleTime,
            open: price, high: price, low: price, close: price,
            volume: ltq
        };
    } else {
        lastCandle.close = price;
        lastCandle.high = Math.max(lastCandle.high, price);
        lastCandle.low = Math.min(lastCandle.low, price);
        lastCandle.volume += ltq;
    }

    candleSeries.update(lastCandle);
    volumeSeries.update({
        time: lastCandle.time,
        value: lastCandle.volume,
        color: lastCandle.close >= lastCandle.open ? 'rgba(34, 197, 94, 0.2)' : 'rgba(239, 68, 68, 0.2)'
    });
}

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
    if (loadingDom) {
        loadingDom.classList.toggle('hidden', !show);
    }
}

function initZoomControls() {
    const zoomInBtn = document.getElementById('zoomInBtn');
    const zoomOutBtn = document.getElementById('zoomOutBtn');
    const resetZoomBtn = document.getElementById('resetZoomBtn');

    if (zoomInBtn) zoomInBtn.addEventListener('click', () => mainChart && mainChart.timeScale().zoomIn(0.2));
    if (zoomOutBtn) zoomOutBtn.addEventListener('click', () => mainChart && mainChart.timeScale().zoomOut(0.2));
    if (resetZoomBtn) resetZoomBtn.addEventListener('click', () => mainChart && mainChart.timeScale().fitContent());
}

function initReplayControls() {
    const replayModeBtn = document.getElementById('replayModeBtn');
    const exitReplayBtn = document.getElementById('exitReplayBtn');
    const replayPlayBtn = document.getElementById('replayPlayBtn');
    const replayNextBtn = document.getElementById('replayNextBtn');
    const replayPrevBtn = document.getElementById('replayPrevBtn');
    const normalControls = document.getElementById('normalControls');
    const replayControls = document.getElementById('replayControls');

    replayModeBtn.addEventListener('click', () => {
        isReplayMode = true;
        normalControls.classList.add('hidden');
        replayControls.classList.remove('hidden');
        document.getElementById('replayStatus').innerText = 'SELECT START POINT';

        replayPlayBtn.disabled = true;
        replayNextBtn.disabled = true;
        replayPrevBtn.disabled = true;
    });

    exitReplayBtn.addEventListener('click', () => {
        stopReplay();
        isReplayMode = false;
        replayControls.classList.add('hidden');
        normalControls.classList.remove('hidden');

        candleSeries.setData(fullHistory.candles);
        volumeSeries.setData(fullHistory.volume);
        if (fullHistory.candles.length > 0) {
            lastCandle = {...fullHistory.candles[fullHistory.candles.length - 1]};
        }
    });

    replayNextBtn.addEventListener('click', () => stepReplay(1));
    replayPrevBtn.addEventListener('click', () => stepReplay(-1));

    replayPlayBtn.addEventListener('click', () => {
        if (isPlaying) pauseReplay();
        else startReplay();
    });
}

function startReplay() {
    isPlaying = true;
    document.getElementById('playIcon').classList.add('hidden');
    document.getElementById('pauseIcon').classList.remove('hidden');
    replayInterval = setInterval(() => {
        if (replayIndex < fullHistory.candles.length - 1) {
            stepReplay(1);
        } else {
            pauseReplay();
        }
    }, 1000);
}

function pauseReplay() {
    isPlaying = false;
    document.getElementById('playIcon').classList.remove('hidden');
    document.getElementById('pauseIcon').classList.add('hidden');
    if (replayInterval) clearInterval(replayInterval);
}

function stopReplay() {
    pauseReplay();
    replayIndex = -1;
}

function stepReplay(delta) {
    const newIndex = replayIndex + delta;
    if (newIndex >= 0 && newIndex < fullHistory.candles.length) {
        replayIndex = newIndex;
        const visibleCandles = fullHistory.candles.slice(0, replayIndex + 1);
        const visibleVolume = fullHistory.volume.slice(0, replayIndex + 1);

        candleSeries.setData(visibleCandles);
        volumeSeries.setData(visibleVolume);

        lastCandle = {...visibleCandles[visibleCandles.length - 1]};
        document.getElementById('replayStatus').innerText = `BAR ${replayIndex + 1} / ${fullHistory.candles.length}`;
    }
}

try {
    init();
} catch (e) {
    console.error("Initialization failed:", e);
}
