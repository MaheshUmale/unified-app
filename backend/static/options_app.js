/**
 * PRODESK Options Analysis Dashboard
 */

let currentUnderlying = 'NSE:NIFTY';
let currentTab = 'chain';
let charts = {};
let socket;
let symbolToCells = {}; // technical_symbol -> { ltp, bidAsk, volume, tr }

async function init() {
    initSocket();

    const selector = document.getElementById('underlyingSelect');
    selector.addEventListener('change', (e) => {
        const oldUnderlying = currentUnderlying;
        currentUnderlying = e.target.value;

        if (socket && socket.connected) {
            socket.emit('unsubscribe_options', { underlying: oldUnderlying });
            socket.emit('subscribe_options', { underlying: currentUnderlying });
        }

        loadData();
    });

    loadData();
    setInterval(loadData, 300000); // Background refresh every 5 mins for OI data
}

function initSocket() {
    socket = io();
    socket.on('connect', () => {
        console.log('Socket connected');
        if (currentUnderlying) {
            socket.emit('subscribe_options', { underlying: currentUnderlying });
        }
    });

    socket.on('options_quote_update', (data) => {
        // data: { underlying, symbol, lp, volume, bid, ask }
        if (data.underlying !== currentUnderlying) return;

        const cells = symbolToCells[data.symbol];
        if (!cells) return;

        if (data.lp !== undefined && data.lp !== null) {
            const oldLtp = parseFloat(cells.ltp.innerText);
            cells.ltp.innerText = data.lp.toFixed(2);

            // Flash effect
            if (oldLtp && oldLtp !== data.lp) {
                cells.tr.classList.remove('flash-up', 'flash-down');
                void cells.tr.offsetWidth; // trigger reflow
                cells.tr.classList.add(data.lp >= oldLtp ? 'flash-up' : 'flash-down');
            }
        }

        if (data.volume !== undefined && data.volume !== null) {
            cells.volume.innerText = data.volume.toLocaleString();
        }

        if (data.bid !== undefined || data.ask !== undefined) {
            const bid = data.bid !== undefined ? data.bid.toFixed(2) : (cells.bidAsk.innerText.split(' / ')[0] || '-');
            const ask = data.ask !== undefined ? data.ask.toFixed(2) : (cells.bidAsk.innerText.split(' / ')[1] || '-');
            cells.bidAsk.innerText = `${bid} / ${ask}`;
        }
    });
}

function switchTab(tabId) {
    currentTab = tabId;
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.getElementById(`tab-${tabId}`).classList.add('active');

    document.querySelectorAll('main > div').forEach(div => div.classList.add('hidden'));
    document.getElementById(`content-${tabId}`).classList.remove('hidden');

    loadData();
}

async function loadData() {
    if (currentTab === 'chain') await loadChain();
    else if (currentTab === 'oi') await loadOIAnalysis();
    else if (currentTab === 'pcr') await loadPCRTrend();
}

function formatIST(ts) {
    if (!ts) return '-';
    const date = new Date(ts);
    return new Intl.DateTimeFormat('en-IN', {
        timeZone: 'Asia/Kolkata',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hour12: false
    }).format(date);
}

async function loadChain() {
    try {
        const res = await fetch(`/api/options/chain/${encodeURIComponent(currentUnderlying)}`);
        const data = await res.json();

        const body = document.getElementById('chainBody');
        body.innerHTML = '';
        symbolToCells = {};

        if (data.timestamp) {
            document.getElementById('lastUpdateTime').innerText = formatIST(data.timestamp);
        }

        // Group by strike
        const grouped = {};
        data.chain.forEach(opt => {
            if (!grouped[opt.strike]) grouped[opt.strike] = { call: null, put: null };
            if (opt.option_type === 'call') grouped[opt.strike].call = opt;
            else grouped[opt.strike].put = opt;
        });

        const sortedStrikes = Object.keys(grouped).map(Number).sort((a, b) => a - b);

        sortedStrikes.forEach(strike => {
            const pair = grouped[strike];
            const tr = document.createElement('tr');
            tr.className = 'hover:bg-white/5 transition-colors border-b border-white/5';

            const c = pair.call || {};
            const p = pair.put || {};

            tr.innerHTML = `
                <td class="p-2 font-mono text-blue-400">${c.oi?.toLocaleString() || '-'}</td>
                <td class="p-2 font-mono ${c.oi_change >= 0 ? 'text-green-500' : 'text-red-500'}">${c.oi_change?.toLocaleString() || '-'}</td>
                <td id="vol-call-${strike}" class="p-2 font-mono text-gray-500">${c.volume?.toLocaleString() || '-'}</td>
                <td id="bidAsk-call-${strike}" class="p-2 font-mono text-gray-400 text-[9px]">- / -</td>
                <td id="ltp-call-${strike}" class="p-2 font-mono text-gray-300 font-bold">${c.ltp?.toFixed(2) || '-'}</td>

                <td class="p-2 text-center font-black bg-gray-900/50 border-x border-white/5 text-blue-100">${strike}</td>

                <td id="ltp-put-${strike}" class="p-2 font-mono text-gray-300 font-bold text-right">${p.ltp?.toFixed(2) || '-'}</td>
                <td id="bidAsk-put-${strike}" class="p-2 font-mono text-gray-400 text-right text-[9px]">- / -</td>
                <td id="vol-put-${strike}" class="p-2 font-mono text-gray-500 text-right">${p.volume?.toLocaleString() || '-'}</td>
                <td class="p-2 font-mono ${p.oi_change >= 0 ? 'text-green-500' : 'text-red-500'} text-right">${p.oi_change?.toLocaleString() || '-'}</td>
                <td class="p-2 font-mono text-red-400 text-right">${p.oi?.toLocaleString() || '-'}</td>
            `;
            body.appendChild(tr);

            if (c.symbol) {
                symbolToCells[c.symbol] = {
                    ltp: document.getElementById(`ltp-call-${strike}`),
                    bidAsk: document.getElementById(`bidAsk-call-${strike}`),
                    volume: document.getElementById(`vol-call-${strike}`),
                    tr: tr
                };
            }
            if (p.symbol) {
                symbolToCells[p.symbol] = {
                    ltp: document.getElementById(`ltp-put-${strike}`),
                    bidAsk: document.getElementById(`bidAsk-put-${strike}`),
                    volume: document.getElementById(`vol-put-${strike}`),
                    tr: tr
                };
            }
        });

    } catch (err) { console.error("Load chain failed:", err); }
}

async function loadOIAnalysis() {
    try {
        const res = await fetch(`/api/options/oi-analysis/${encodeURIComponent(currentUnderlying)}`);
        const result = await res.json();
        const data = result.data;

        const labels = data.map(d => d.strike);
        const callOI = data.map(d => d.call_oi);
        const putOI = data.map(d => d.put_oi);
        const callChg = data.map(d => d.call_oi_change);
        const putChg = data.map(d => d.put_oi_change);

        renderBarChart('oiDistChart', labels, [
            { label: 'Call OI', data: callOI, backgroundColor: 'rgba(59, 130, 246, 0.6)' },
            { label: 'Put OI', data: putOI, backgroundColor: 'rgba(239, 68, 68, 0.6)' }
        ]);

        renderBarChart('oiChgChart', labels, [
            { label: 'Call OI Chg', data: callChg, backgroundColor: 'rgba(59, 130, 246, 0.8)' },
            { label: 'Put OI Chg', data: putChg, backgroundColor: 'rgba(239, 68, 68, 0.8)' }
        ]);

    } catch (err) { console.error("Load OI analysis failed:", err); }
}

async function loadPCRTrend() {
    try {
        const res = await fetch(`/api/options/pcr-trend/${encodeURIComponent(currentUnderlying)}`);
        const data = await res.json();
        const history = data.history;

        if (history.length > 0) {
            const last = history[history.length - 1];
            document.getElementById('maxPainVal').innerText = last.max_pain?.toFixed(0) || '-';
            document.getElementById('spotPriceVal').innerText = last.spot_price?.toFixed(2) || '-';
        }

        const labels = history.map(h => formatIST(h.timestamp));
        const pcrOI = history.map(h => h.pcr_oi);
        const pcrVol = history.map(h => h.pcr_vol);
        const price = history.map(h => h.underlying_price);
        const maxPain = history.map(h => h.max_pain);

        renderLineChart('pcrTrendChart', labels, [
            { label: 'PCR (OI)', data: pcrOI, borderColor: '#3b82f6', yAxisID: 'y' },
            { label: 'PCR (Vol)', data: pcrVol, borderColor: '#10b981', yAxisID: 'y' },
            { label: 'Max Pain', data: maxPain, borderColor: '#ef4444', yAxisID: 'y1', borderDash: [5, 5] },
            { label: 'Underlying Price', data: price, borderColor: '#f59e0b', yAxisID: 'y1' }
        ]);

    } catch (err) { console.error("Load PCR trend failed:", err); }
}

function renderBarChart(canvasId, labels, datasets) {
    if (charts[canvasId]) charts[canvasId].destroy();

    const ctx = document.getElementById(canvasId).getContext('2d');
    charts[canvasId] = new Chart(ctx, {
        type: 'bar',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { size: 10 } } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { size: 10 } } }
            },
            plugins: {
                legend: { labels: { color: '#d1d5db', font: { size: 10, weight: 'bold' } } }
            }
        }
    });
}

function renderLineChart(canvasId, labels, datasets) {
    if (charts[canvasId]) charts[canvasId].destroy();

    const ctx = document.getElementById(canvasId).getContext('2d');
    charts[canvasId] = new Chart(ctx, {
        type: 'line',
        data: { labels, datasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            elements: { point: { radius: 0 }, line: { borderWidth: 2, tension: 0.3 } },
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af', font: { size: 10 } } },
                y: {
                    grid: { color: 'rgba(255,255,255,0.05)' },
                    ticks: { color: '#3b82f6', font: { size: 10 } },
                    position: 'left',
                    title: { display: true, text: 'PCR', color: '#3b82f6' }
                },
                y1: {
                    grid: { drawOnChartArea: false },
                    ticks: { color: '#f59e0b', font: { size: 10 } },
                    position: 'right',
                    title: { display: true, text: 'Price', color: '#f59e0b' }
                }
            },
            plugins: {
                legend: { labels: { color: '#d1d5db', font: { size: 10, weight: 'bold' } } }
            }
        }
    });
}

document.addEventListener('DOMContentLoaded', init);
