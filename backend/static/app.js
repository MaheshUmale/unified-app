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
let isReplay = false;
let replayDate = '';

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
            },
            timeScale: {
                borderColor: '#1f2937',
                timeVisible: true,
                secondsVisible: false,
            },
        });

        // Compatibility for different versions of Lightweight Charts
        candleSeries = mainChart.addCandlestickSeries ? mainChart.addCandlestickSeries({
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
        }) : mainChart.addSeries(LightweightCharts.CandlestickSeries, {
            upColor: '#22c55e',
            downColor: '#ef4444',
            borderVisible: false,
            wickUpColor: '#22c55e',
            wickDownColor: '#ef4444',
        });

        volumeSeries = mainChart.addHistogramSeries ? mainChart.addHistogramSeries({
            color: '#3b82f6',
            lineWidth: 2,
            priceFormat: {
                type: 'volume',
            },
            overlay: true,
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        }) : mainChart.addSeries(LightweightCharts.HistogramSeries, {
            color: '#3b82f6',
            lineWidth: 2,
            priceFormat: {
                type: 'volume',
            },
            overlay: true,
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });

        window.addEventListener('resize', () => {
            mainChart.resize(chartContainer.clientWidth, chartContainer.clientHeight);
        });
    }

    initSocket();
    initSearch();
    fetchReplayDates();

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
                color: c.close >= c.open ? 'rgba(34, 197, 94, 0.5)' : 'rgba(239, 68, 68, 0.5)'
            })).sort((a, b) => a.time - b.time);

            candleSeries.setData(chartData);
            volumeSeries.setData(volData);

            lastCandle = chartData[chartData.length - 1];
            lastCandle.volume = candles[candles.length - 1].volume;
        } else {
            candleSeries.setData([]);
            volumeSeries.setData([]);
        }

        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    } catch (e) {
        console.error("Switch symbol failed:", e);
    } finally {
        setLoading(false);
    }
}

async function fetchIntraday(key, interval = '1') {
    let url = `/api/tv/intraday/${encodeURIComponent(key)}?interval=${interval}`;
    if (isReplay && replayDate) url += `&date=${replayDate}`;
    const res = await fetch(url);
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
        const statusDom = document.getElementById('socketStatus');
        if (statusDom) {
            statusDom.innerHTML = '<div class="w-1.5 h-1.5 bg-green-500 rounded-full"></div> CONNECTED';
        }
        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    });

    socket.on('disconnect', () => {
        const statusDom = document.getElementById('socketStatus');
        if (statusDom) {
            statusDom.innerHTML = '<div class="w-1.5 h-1.5 bg-red-500 rounded-full"></div> DISCONNECTED';
        }
    });

    socket.on('raw_tick', (data) => {
        const rawData = typeof data === 'string' ? JSON.parse(data) : data;
        handleTickUpdate(rawData);
    });

    socket.on('replay_status', (status) => {
        isReplay = !!status.active;
        replayDate = status.date || '';
        if (status.is_new) {
             candleSeries.setData([]);
             volumeSeries.setData([]);
             lastCandle = null;
        }
    });
}

function handleTickUpdate(quotes) {
    const entries = Object.entries(quotes);
    for (const [key, quote] of entries) {
        if (normalizeSymbol(key) === normalizeSymbol(currentSymbol)) {
            updateRealtimeCandle(quote);
            break;
        }
    }
}

function updateRealtimeCandle(quote) {
    if (!candleSeries) return;

    const tickTime = Math.floor(quote.ts_ms / 1000);
    const candleTime = tickTime - (tickTime % 60); // 1-min alignment
    const price = quote.last_price;
    const ltq = quote.ltq || 0;

    if (!lastCandle || candleTime > lastCandle.time) {
        lastCandle = {
            time: candleTime,
            open: price,
            high: price,
            low: price,
            close: price,
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
        color: lastCandle.close >= lastCandle.open ? 'rgba(34, 197, 94, 0.5)' : 'rgba(239, 68, 68, 0.5)'
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

async function fetchReplayDates() {
    try {
        const res = await fetch('/api/replay/dates');
        const dates = await res.json();
        const select = document.getElementById('replayDateSelect');
        if (!select) return;

        dates.forEach(d => {
            const opt = document.createElement('option');
            opt.value = d;
            opt.innerText = d;
            select.appendChild(opt);
        });

        select.addEventListener('change', (e) => {
            if (e.target.value) {
                isReplay = true;
                replayDate = e.target.value;
                switchSymbol(currentSymbol);
            } else {
                isReplay = false;
                replayDate = '';
                socket.emit('stop_replay', {});
                switchSymbol(currentSymbol);
            }
        });
    } catch (e) {
        console.error("Fetch replay dates failed:", e);
    }
}

const replayBtn = document.getElementById('replayBtn');
if (replayBtn) {
    replayBtn.addEventListener('click', () => {
        if (isReplay && replayDate) {
            socket.emit('start_replay', { date: replayDate, instrument_keys: [currentSymbol], speed: 10.0 });
        }
    });
}

try {
    init();
} catch (e) {
    console.error("Initialization failed:", e);
}
