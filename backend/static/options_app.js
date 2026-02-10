/**
 * PRODESK Options Analysis Dashboard - One Glance Optimized
 */

let currentUnderlying = 'NSE:NIFTY';
let charts = {};
let socket;
let symbolToCells = {};

async function init() {
    initSocket();

    const selector = document.getElementById('underlyingSelect');
    selector.addEventListener('change', (e) => {
        const oldUnderlying = currentUnderlying;
        currentUnderlying = e.target.value;

        if (socket && socket.connected) {
            socket.emit('unsubscribe_options', { underlying: oldUnderlying });
            socket.emit('unsubscribe', { instrumentKeys: [oldUnderlying], interval: '1' });
            socket.emit('subscribe_options', { underlying: currentUnderlying });
            socket.emit('subscribe', { instrumentKeys: [currentUnderlying], interval: '1' });
        }

        loadAllData();
    });

    document.getElementById('refreshBtn').onclick = loadAllData;
    document.getElementById('backfillBtn').onclick = triggerBackfill;

    loadAllData();
    setInterval(loadAllData, 300000); // 5 min refresh
}

function initSocket() {
    socket = io();
    socket.on('connect', () => {
        if (currentUnderlying) {
            socket.emit('subscribe_options', { underlying: currentUnderlying });
            socket.emit('subscribe', { instrumentKeys: [currentUnderlying], interval: '1' });
        }
    });

    socket.on('chart_update', (data) => {
        if (data.instrumentKey === currentUnderlying && data.ohlcv && data.ohlcv.length > 0) {
            const candles = data.ohlcv;
            // Technical TV feed newest may be at end or beginning depending on source
            // But data_engine usually sends single point for live updates
            const latestPrice = candles[0][4];
            document.getElementById('spotPrice').innerText = latestPrice.toFixed(2);
        }
    });

    socket.on('options_quote_update', (data) => {
        if (data.underlying !== currentUnderlying) return;
        const cells = symbolToCells[data.symbol];
        if (!cells) return;

        if (data.lp !== undefined && data.lp !== null) {
            const oldLtp = parseFloat(cells.ltp.innerText);
            cells.ltp.innerText = data.lp.toFixed(2);
            if (oldLtp && Math.abs(oldLtp - data.lp) > 0.01) {
                cells.tr.classList.remove('flash-up', 'flash-down');
                void cells.tr.offsetWidth;
                cells.tr.classList.add(data.lp >= oldLtp ? 'flash-up' : 'flash-down');
            }
        }
        if (data.volume !== undefined && data.volume !== null) {
            cells.volume.innerText = data.volume.toLocaleString();
        }
    });
}

async function triggerBackfill() {
    const btn = document.getElementById('backfillBtn');
    btn.disabled = true;
    btn.innerText = 'Processing...';
    try {
        await fetch('/api/options/backfill', { method: 'POST' });
        setTimeout(loadAllData, 2000);
    } catch (e) { console.error(e); }
    finally {
        btn.disabled = false;
        btn.innerText = 'Backfill';
    }
}

async function loadAllData() {
    try {
        const [chainRes, oiRes, trendRes] = await Promise.all([
            fetch(`/api/options/chain/${encodeURIComponent(currentUnderlying)}`),
            fetch(`/api/options/oi-analysis/${encodeURIComponent(currentUnderlying)}`),
            fetch(`/api/options/pcr-trend/${encodeURIComponent(currentUnderlying)}`)
        ]);

        const chainData = await chainRes.json();
        const oiData = await oiRes.json();
        const trendData = await trendRes.json();

        updateHeader(chainData);
        renderOptionChain(chainData);
        renderOICharts(oiData);
        renderPCRTrend(trendData);
        updateSummary(trendData, oiData);
        renderSnapshots(trendData);

    } catch (err) { console.error("Load failed:", err); }
}

function updateHeader(data) {
    if (data.timestamp) {
        document.getElementById('lastUpdated').innerText = formatIST(data.timestamp);
    }
}

function formatIST(ts) {
    if (!ts) return '-';
    const date = new Date(ts);
    return new Intl.DateTimeFormat('en-IN', {
        timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false
    }).format(date);
}

function renderOptionChain(data) {
    const body = document.getElementById('chainBody');
    body.innerHTML = '';
    symbolToCells = {};

    const grouped = {};
    data.chain.forEach(opt => {
        if (!grouped[opt.strike]) grouped[opt.strike] = { call: null, put: null };
        if (opt.option_type === 'call') grouped[opt.strike].call = opt;
        else grouped[opt.strike].put = opt;
    });

    const strikes = Object.keys(grouped).map(Number).sort((a, b) => a - b);
    strikes.forEach(strike => {
        const pair = grouped[strike];
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-white/5 border-b border-white/5';

        const c = pair.call || {};
        const p = pair.put || {};

        tr.innerHTML = `
            <td class="p-2 text-right font-mono text-green-400">${c.oi?.toLocaleString() || '0'}</td>
            <td class="p-2 text-right font-mono ${c.oi_change >= 0 ? 'text-green-500' : 'text-red-500'}">${c.oi_change?.toLocaleString() || '0'}</td>
            <td id="vol-call-${strike}" class="p-2 text-right font-mono text-gray-500">${c.volume?.toLocaleString() || '0'}</td>
            <td id="ltp-call-${strike}" class="p-2 text-right font-mono text-gray-300 font-bold">${c.ltp?.toFixed(2) || '0.00'}</td>

            <td class="p-2 text-center font-black bg-slate-800 border-x border-white/5 text-yellow-500">${strike}</td>

            <td id="ltp-put-${strike}" class="p-2 font-mono text-gray-300 font-bold">${p.ltp?.toFixed(2) || '0.00'}</td>
            <td id="vol-put-${strike}" class="p-2 font-mono text-gray-500">${p.volume?.toLocaleString() || '0'}</td>
            <td class="p-2 font-mono ${p.oi_change >= 0 ? 'text-green-500' : 'text-red-500'}">${p.oi_change?.toLocaleString() || '0'}</td>
            <td class="p-2 font-mono text-red-400">${p.oi?.toLocaleString() || '0'}</td>
        `;
        body.appendChild(tr);

        if (c.symbol) symbolToCells[c.symbol] = { ltp: document.getElementById(`ltp-call-${strike}`), volume: document.getElementById(`vol-call-${strike}`), tr };
        if (p.symbol) symbolToCells[p.symbol] = { ltp: document.getElementById(`ltp-put-${strike}`), volume: document.getElementById(`vol-put-${strike}`), tr };
    });
}

function renderOICharts(result) {
    const data = result.data;
    const labels = data.map(d => d.strike);
    const callOI = data.map(d => d.call_oi);
    const putOI = data.map(d => d.put_oi);

    if (charts.oiDistChart) charts.oiDistChart.destroy();
    const ctx = document.getElementById('oiDistChart').getContext('2d');
    charts.oiDistChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels,
            datasets: [
                { label: 'Call OI', data: callOI, backgroundColor: '#3b82f6' },
                { label: 'Put OI', data: putOI, backgroundColor: '#ef4444' }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { size: 9 } } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { size: 9 } } }
            },
            plugins: { legend: { position: 'top', align: 'end', labels: { color: '#94a3b8', font: { size: 9, weight: 'bold' }, usePointStyle: true, boxWidth: 6 } } }
        }
    });
}

function renderPCRTrend(result) {
    const history = result.history;
    const labels = history.map(h => formatIST(h.timestamp).split(':')[0] + ':' + formatIST(h.timestamp).split(':')[1]);
    const pcrOI = history.map(h => h.pcr_oi);
    const pcrChg = history.map(h => h.pcr_oi_change);

    if (charts.pcrTrendChart) charts.pcrTrendChart.destroy();
    const ctx = document.getElementById('pcrTrendChart').getContext('2d');
    charts.pcrTrendChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'PCR (Total)', data: pcrOI, borderColor: '#818cf8', backgroundColor: 'rgba(129, 140, 248, 0.1)', fill: true, tension: 0.4, pointRadius: 2 },
                { label: 'PCR (Change)', data: pcrChg, borderColor: '#c084fc', backgroundColor: 'transparent', fill: false, tension: 0.4, pointRadius: 2 }
            ]
        },
        options: {
            responsive: true, maintainAspectRatio: false,
            scales: {
                x: { grid: { display: false }, ticks: { color: '#64748b', font: { size: 8 } } },
                y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#64748b', font: { size: 8 } } }
            },
            plugins: { legend: { display: true, position: 'top', align: 'end', labels: { color: '#94a3b8', font: { size: 9 }, usePointStyle: true, boxWidth: 6 } } }
        }
    });
}

function updateSummary(trendData, oiData) {
    const history = trendData.history;
    if (history.length === 0) return;
    const last = history[history.length - 1];

    if (parseFloat(last.spot_price) > 0) {
        document.getElementById('spotPrice').innerText = last.spot_price?.toFixed(2);
    }
    document.getElementById('pcrOi').innerText = last.pcr_oi?.toFixed(2) || '0.0';
    document.getElementById('pcrVol').innerText = last.pcr_vol?.toFixed(2) || '0.0';
    document.getElementById('maxPain').innerText = last.max_pain?.toFixed(0) || '0';

    // Sentiment
    const spotSent = document.getElementById('spotSentiment');
    const prevSpot = history.length > 1 ? history[history.length - 2].spot_price : last.spot_price;
    if (last.spot_price >= prevSpot) {
        spotSent.innerText = 'BULLISH';
        spotSent.className = 'text-[10px] font-black bg-green-500/20 text-green-500 px-2 py-0.5 rounded uppercase';
    } else {
        spotSent.innerText = 'BEARISH';
        spotSent.className = 'text-[10px] font-black bg-red-500/20 text-red-500 px-2 py-0.5 rounded uppercase';
    }

    const pcrSent = document.getElementById('pcrSentiment');
    if (last.pcr_oi > 1.0) {
        pcrSent.innerText = 'BULLISH';
        pcrSent.className = 'text-[10px] font-black bg-green-500/20 text-green-500 px-2 py-0.5 rounded uppercase';
    } else {
        pcrSent.innerText = 'BEARISH';
        pcrSent.className = 'text-[10px] font-black bg-red-500/20 text-red-500 px-2 py-0.5 rounded uppercase';
    }

    // Support/Resistance
    const sortedOI = [...oiData.data].sort((a, b) => (b.call_oi + b.put_oi) - (a.call_oi + a.put_oi));
    if (sortedOI.length > 0) {
        const maxCall = [...oiData.data].sort((a, b) => b.call_oi - a.call_oi)[0];
        const maxPut = [...oiData.data].sort((a, b) => b.put_oi - a.put_oi)[0];
        document.getElementById('supportResistance').innerText = `${maxPut.strike} / ${maxCall.strike}`;
    }
}

function renderSnapshots(result) {
    const body = document.getElementById('snapshotBody');
    body.innerHTML = '';
    const history = [...result.history].reverse().slice(0, 20);

    history.forEach((h, i) => {
        const tr = document.createElement('tr');
        const pcrChg = h.pcr_oi_change ? h.pcr_oi_change.toFixed(2) : '0.00';

        tr.innerHTML = `
            <td class="p-2 text-gray-400">${formatIST(h.timestamp)}</td>
            <td class="p-2 font-bold">${h.spot_price?.toFixed(2) || '0.00'}</td>
            <td class="p-2 text-green-500 font-bold">${h.pcr_oi?.toFixed(2) || '0.00'}</td>
            <td class="p-2 text-blue-400">${pcrChg}</td>
            <td class="p-2 text-gray-300">${h.max_pain || '0'}</td>
        `;
        body.appendChild(tr);
    });
}

document.addEventListener('DOMContentLoaded', init);
