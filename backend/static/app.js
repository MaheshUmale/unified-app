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
    }

    initSocket();
    initSearch();

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

            candleSeries.setData(chartData);
            volumeSeries.setData(volData);

            lastCandle = chartData[chartData.length - 1];
            lastCandle.volume = candles[candles.length - 1].volume;

            // Auto fit content
            mainChart.timeScale().fitContent();
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
        socket.emit('subscribe', { instrumentKeys: [currentSymbol] });
    });

    socket.on('raw_tick', (data) => {
        const rawData = typeof data === 'string' ? JSON.parse(data) : data;
        handleTickUpdate(rawData);
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

try {
    init();
} catch (e) {
    console.error("Initialization failed:", e);
}
