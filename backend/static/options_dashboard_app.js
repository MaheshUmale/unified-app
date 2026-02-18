/**
 * PRODESK Options Dashboard v3.0
 * Unified management of Option Chain, Analysis, Strategies, and Scalper.
 */

class OptionsDashboardManager {
    constructor() {
        this.currentUnderlying = 'NSE:NIFTY';
        this.socket = null;
        this.charts = {};
        this.theme = localStorage.getItem('theme') || 'light';

        // Chart.js defaults
        if (window.Chart) {
            Chart.defaults.font.family = "'Plus Jakarta Sans', sans-serif";
            Chart.defaults.color = '#94a3b8';
        }

        this.init();
    }

    async init() {
        this.applyTheme(this.theme);
        this.initSocket();
        this.setupEventListeners();
        await this.loadData();

        // Auto-refresh
        setInterval(() => this.loadData(), 120000);
    }

    initSocket() {
        this.socket = io();
        this.socket.on('connect', () => {
            console.log("[Options] Socket connected");
            this.socket.emit('subscribe_options', { underlying: this.currentUnderlying });
            this.socket.emit('subscribe', { instrumentKeys: [this.currentUnderlying], interval: '1' });
        });

        this.socket.on('raw_tick', (data) => {
            if (data[this.currentUnderlying]) {
                const price = parseFloat(data[this.currentUnderlying].last_price);
                if (price > 0) document.getElementById('spotPrice').textContent = price.toLocaleString(undefined, {minimumFractionDigits: 2});
            }
        });

        this.socket.on('chart_update', (data) => {
            if (data.instrumentKey === this.currentUnderlying && data.ohlcv?.length > 0) {
                const price = parseFloat(data.ohlcv[data.ohlcv.length - 1][4]);
                if (price > 0) document.getElementById('spotPrice').textContent = price.toLocaleString(undefined, {minimumFractionDigits: 2});
            }
        });

        this.socket.on('scalper_metrics', (data) => this.renderScalperMetrics(data));
        this.socket.on('scalper_log', (data) => this.renderScalperLog(data));
        this.socket.on('options_alert', (data) => alert(data.message));
    }

    setupEventListeners() {
        // Core controls
        document.getElementById('underlyingSelect').addEventListener('change', (e) => this.switchUnderlying(e.target.value));
        document.getElementById('refreshBtn').addEventListener('click', () => this.loadData());
        document.getElementById('backfillBtn').addEventListener('click', () => this.triggerBackfill());
        document.getElementById('optionsThemeToggle').addEventListener('click', () => this.toggleTheme());

        // Navigation
        document.querySelectorAll('.tab-btn').forEach(btn => {
            btn.addEventListener('click', () => this.switchTab(btn.dataset.tab));
        });

        // Sub-modules
        document.getElementById('strategyBtn').addEventListener('click', () => this.switchTab('strategies'));
        document.getElementById('alertsBtn').addEventListener('click', () => this.switchTab('alerts'));
        document.getElementById('buildStrategyBtn')?.addEventListener('click', () => this.buildStrategy());
        document.getElementById('addLegBtn')?.addEventListener('click', () => this.addLeg());
        document.getElementById('strategyType')?.addEventListener('change', (e) => {
            document.getElementById('customLegsContainer').classList.toggle('hidden', e.target.value !== 'custom');
        });
        document.getElementById('createAlertBtn')?.addEventListener('click', () => this.createAlert());
        document.getElementById('startScalperBtn')?.addEventListener('click', () => this.startScalper());
        document.getElementById('stopScalperBtn')?.addEventListener('click', () => this.stopScalper());
    }

    async switchUnderlying(newUnderlying) {
        this.socket.emit('unsubscribe_options', { underlying: this.currentUnderlying });
        this.socket.emit('unsubscribe', { instrumentKeys: [this.currentUnderlying], interval: '1' });

        this.currentUnderlying = newUnderlying;

        this.socket.emit('subscribe_options', { underlying: this.currentUnderlying });
        this.socket.emit('subscribe', { instrumentKeys: [this.currentUnderlying], interval: '1' });

        await this.loadData();
    }

    async loadData() {
        try {
            const [chain, genie, buildup, iv, overview] = await Promise.all([
                fetch(`/api/options/chain/${this.currentUnderlying}/with-greeks`).then(r => r.json()),
                fetch(`/api/options/genie-insights/${this.currentUnderlying}`).then(r => r.json()),
                fetch(`/api/options/oi-buildup/${this.currentUnderlying}`).then(r => r.json()),
                fetch(`/api/options/iv-analysis/${this.currentUnderlying}`).then(r => r.json()),
                this.fetchOverviewData()
            ]);

            this.renderOptionChain(chain);
            this.renderGenieCard(genie);
            this.renderBuildupSummary(buildup);
            this.renderIVCard(iv);

            document.getElementById('lastUpdated').textContent = new Date().toLocaleTimeString('en-IN', { hour12: false });
        } catch (e) { console.error("[Options] Load failed:", e); }
    }

    async fetchOverviewData() {
        const [pcr, oi, sr] = await Promise.all([
            fetch(`/api/options/pcr-trend/${this.currentUnderlying}`).then(r => r.json()),
            fetch(`/api/options/oi-analysis/${this.currentUnderlying}`).then(r => r.json()),
            fetch(`/api/options/support-resistance/${this.currentUnderlying}`).then(r => r.json())
        ]);
        this.renderPCRChart(pcr);
        this.renderOIChart(oi);
        this.renderSupportResistance(sr);
        this.updateSummaryFromOverview(pcr);
    }

    renderOptionChain(data) {
        const tbody = document.getElementById('optionChainBody');
        if (!tbody) return;
        tbody.innerHTML = '';

        const spot = data.spot_price || 0;
        document.getElementById('spotPrice').textContent = spot.toLocaleString(undefined, {minimumFractionDigits: 2});

        const grouped = {};
        data.chain.forEach(item => {
            if (!grouped[item.strike]) grouped[item.strike] = { call: null, put: null };
            grouped[item.strike][item.option_type] = item;
        });

        Object.keys(grouped).sort((a,b) => a-b).forEach(strike => {
            const { call, put } = grouped[strike];
            const isATM = Math.abs(strike - spot) / spot < 0.005;
            const tr = document.createElement('tr');
            tr.className = `${isATM ? 'bg-blue-500/10' : ''} hover:bg-white/5 border-b border-white/5`;
            tr.innerHTML = `
                <td class="p-2 text-right text-gray-500">${call?.iv || '-'}</td>
                <td class="p-2 text-right ${call?.delta > 0 ? 'text-green-500' : 'text-red-500'}">${call?.delta?.toFixed(2) || '-'}</td>
                <td class="p-2 text-right text-gray-600">${call?.theta?.toFixed(2) || '-'}</td>
                <td class="p-2 text-right font-black text-green-400">${call?.ltp?.toFixed(2) || '-'}</td>
                <td class="p-2 text-right ${call?.oi_change > 0 ? 'text-green-500' : 'text-red-500'}">${call?.oi_change || '-'}</td>
                <td class="p-2 text-right border-r border-white/10 font-bold">${call?.oi?.toLocaleString() || '-'}</td>
                <td class="p-2 text-center strike-cell">${strike}</td>
                <td class="p-2 font-bold">${put?.oi?.toLocaleString() || '-'}</td>
                <td class="p-2 ${put?.oi_change > 0 ? 'text-green-500' : 'text-red-500'}">${put?.oi_change || '-'}</td>
                <td class="p-2 font-black text-red-400">${put?.ltp?.toFixed(2) || '-'}</td>
                <td class="p-2 text-gray-600">${put?.theta?.toFixed(2) || '-'}</td>
                <td class="p-2 ${put?.delta > 0 ? 'text-green-500' : 'text-red-500'}">${put?.delta?.toFixed(2) || '-'}</td>
                <td class="p-2 text-gray-500">${put?.iv || '-'}</td>
            `;
            tbody.appendChild(tr);
        });
    }

    renderGenieCard(data) {
        const el = document.getElementById('genieControl');
        if (!el) return;
        el.textContent = data.control.replace(/_/g, ' ');
        el.className = `text-lg font-black uppercase ${data.control.includes('BUYERS') ? 'text-green-500' : data.control.includes('SELLERS') ? 'text-red-500' : 'text-white'}`;
        document.getElementById('genieDistribution').textContent = data.distribution.status;
        document.getElementById('genieRange').textContent = `${data.boundaries.lower} - ${data.boundaries.upper}`;
    }

    renderBuildupSummary(data) {
        const container = document.getElementById('buildupAnalysis');
        if (!container) return;
        container.innerHTML = '';
        const patterns = data.summary?.pattern_distribution || {};
        const colors = { 'Long Buildup': 'text-green-500', 'Short Buildup': 'text-red-500', 'Long Unwinding': 'text-orange-500', 'Short Covering': 'text-blue-400' };

        Object.entries(patterns).forEach(([p, count]) => {
            const div = document.createElement('div');
            div.className = 'flex flex-col items-center bg-black/10 rounded py-1 px-2';
            div.innerHTML = `<div class="text-[7px] text-gray-500 uppercase font-black truncate">${p.replace(' Buildup', '')}</div><div class="text-xs font-black ${colors[p] || 'text-white'}">${count}</div>`;
            container.appendChild(div);
        });
    }

    renderIVCard(data) {
        const rankEl = document.getElementById('ivRank');
        if (!rankEl) return;
        rankEl.textContent = data.iv_rank !== undefined ? data.iv_rank + '%' : '-';
        document.getElementById('ivValue').textContent = data.current_iv !== undefined ? data.current_iv + '%' : '-';
        const sig = document.getElementById('ivSignal');
        if (data.iv_rank > 70) { sig.textContent = 'HIGH'; sig.className = 'text-[8px] font-black bg-red-500/20 text-red-500 px-1.5 py-0.5 rounded'; }
        else if (data.iv_rank < 30) { sig.textContent = 'LOW'; sig.className = 'text-[8px] font-black bg-green-500/20 text-green-500 px-1.5 py-0.5 rounded'; }
        else { sig.textContent = 'NORMAL'; sig.className = 'text-[8px] font-black bg-gray-500/20 text-gray-400 px-1.5 py-0.5 rounded'; }
    }

    renderPCRChart(data) {
        const ctx = document.getElementById('confluenceChart')?.getContext('2d');
        if (!ctx) return;
        if (this.charts.pcr) this.charts.pcr.destroy();

        const history = (data.history || []).filter(h => (h.spot_price || h.underlying_price) > 0);
        const labels = history.map(h => new Date(h.timestamp).toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit', hour12: false }));

        this.charts.pcr = new Chart(ctx, {
            type: 'line',
            data: {
                labels,
                datasets: [
                    { label: 'Spot', data: history.map(h => h.spot_price || h.underlying_price), borderColor: this.theme === 'light' ? '#000' : '#fff', borderDash: [3,3], pointRadius: 0, yAxisID: 'y1' },
                    { label: 'PCR', data: history.map(h => h.pcr_oi), borderColor: '#3b82f6', backgroundColor: 'rgba(59, 130, 246, 0.1)', fill: true, tension: 0.4, pointRadius: 0, yAxisID: 'y' }
                ]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    y: { type: 'linear', position: 'left', title: { display: true, text: 'PCR' } },
                    y1: { type: 'linear', position: 'right', grid: { drawOnChartArea: false }, title: { display: true, text: 'SPOT' } }
                }
            }
        });
    }

    renderOIChart(data) {
        const ctx = document.getElementById('oiChart')?.getContext('2d');
        if (!ctx) return;
        if (this.charts.oi) this.charts.oi.destroy();
        const oiData = data.data || [];
        this.charts.oi = new Chart(ctx, {
            type: 'bar',
            data: {
                labels: oiData.map(d => d.strike),
                datasets: [
                    { label: 'Call OI', data: oiData.map(d => d.call_oi), backgroundColor: 'rgba(34, 197, 94, 0.6)' },
                    { label: 'Put OI', data: oiData.map(d => d.put_oi), backgroundColor: 'rgba(239, 68, 68, 0.6)' }
                ]
            },
            options: { responsive: true, maintainAspectRatio: false }
        });
    }

    renderSupportResistance(data) {
        const container = document.getElementById('supportResistance');
        if (!container) return;
        container.innerHTML = '';
        const all = [...(data.resistance_levels || []).map(l => ({...l, type: 'RES'})), ...(data.support_levels || []).map(l => ({...l, type: 'SUP'}))].sort((a,b) => b.strike - a.strike);

        all.forEach(l => {
            const isSup = l.type === 'SUP';
            const color = isSup ? 'text-green-500' : 'text-red-500';
            const div = document.createElement('div');
            div.className = `flex justify-between items-center p-2 ${isSup ? 'bg-green-500/5 border-green-500/20' : 'bg-red-500/5 border-red-500/20'} border-l-4 rounded mb-1`;
            div.innerHTML = `<div><span class="text-xs font-black ${color}">${l.strike}</span> <span class="text-[8px] text-gray-500 uppercase">${l.type}</span></div><div class="text-[10px] font-bold">${(l.oi/1000000).toFixed(2)}M</div>`;
            container.appendChild(div);
        });
    }

    updateSummaryFromOverview(data) {
        const history = data.history || [];
        if (history.length === 0) return;
        const last = history[history.length - 1];
        document.getElementById('pcrValue').textContent = last.pcr_oi?.toFixed(2) || '0.00';
        document.getElementById('maxPain').textContent = (last.max_pain || 0).toLocaleString();
    }

    switchTab(tabId) {
        document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.toggle('tab-active', btn.dataset.tab === tabId));
        document.querySelectorAll('.tab-pane').forEach(pane => pane.classList.toggle('hidden', pane.id !== `${tabId}Tab`));
        if (tabId === 'scalper') this.updateScalperStatusUI();
        if (tabId === 'alerts') this.loadAlerts();
    }

    async triggerBackfill() {
        const res = await fetch('/api/options/backfill', { method: 'POST' }).then(r => r.json());
        alert(res.message);
    }

    toggleTheme() {
        this.theme = this.theme === 'light' ? 'dark' : 'light';
        localStorage.setItem('theme', this.theme);
        this.applyTheme(this.theme);
    }

    applyTheme(theme) {
        if (theme === 'light') {
            document.body.classList.add('light-theme');
            document.getElementById('optionsSunIcon')?.classList.add('hidden');
            document.getElementById('optionsMoonIcon')?.classList.remove('hidden');
        } else {
            document.body.classList.remove('light-theme');
            document.getElementById('optionsSunIcon')?.classList.remove('hidden');
            document.getElementById('optionsMoonIcon')?.classList.add('hidden');
        }
    }

    // Scalper UI
    renderScalperMetrics(data) {
        document.getElementById('scalperOIPower').textContent = data.oi_power;
        const sentEl = document.getElementById('scalperOISentiment');
        sentEl.textContent = data.oi_sentiment.replace(/_/g, ' ');
        sentEl.className = `text-lg font-black mt-1 ${data.oi_sentiment.includes('BULLISH') ? 'text-green-500' : 'text-red-500'}`;

        if (data.confluence) {
            const update = (id, val) => document.getElementById(id)?.classList.toggle('opacity-40', !val);
            update('conf-lvl', data.confluence.lvl);
            update('conf-pcr', data.confluence.pcr);
            update('conf-oi', data.confluence.oi);
            update('conf-brk', data.confluence.opt_brk);
            update('conf-inv', data.confluence.inv_dwn);
        }
    }

    renderScalperLog(data) {
        const logEl = document.getElementById('scalperLog');
        if (!logEl) return;
        const p = document.createElement('p');
        p.textContent = data.message || `[${data.time}] ${data.signal} @ ${data.underlying_level}`;
        p.className = p.textContent.includes('BUY') ? 'text-green-400 font-bold' : 'text-gray-300';
        logEl.prepend(p);
        if (logEl.children.length > 50) logEl.lastChild.remove();
    }

    async updateScalperStatusUI() {
        const data = await fetch('/api/scalper/status').then(r => r.json());
        const active = data.is_running;
        document.getElementById('statusDot').className = `w-2 h-2 rounded-full ${active ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-red-500'}`;
        document.getElementById('statusText').textContent = active ? 'Active: ' + data.underlying : 'Inactive';
        document.getElementById('startScalperBtn').classList.toggle('hidden', active);
        document.getElementById('stopScalperBtn').classList.toggle('hidden', !active);
    }

    async startScalper() {
        await fetch(`/api/scalper/start?underlying=${document.getElementById('scalperUnderlying').value}`, { method: 'POST' });
        this.updateScalperStatusUI();
    }

    async stopScalper() {
        await fetch('/api/scalper/stop', { method: 'POST' });
        this.updateScalperStatusUI();
    }

    // Strategy Builder
    addLeg() {
        const list = document.getElementById('legsList');
        const div = document.createElement('div');
        div.className = 'flex gap-2 items-center bg-black/20 p-2 rounded leg-item';
        div.innerHTML = `
            <input type="number" placeholder="Strike" class="leg-strike bg-slate-800 border-none text-[10px] w-20 rounded p-1">
            <select class="leg-type bg-slate-800 border-none text-[10px] rounded p-1">
                <option value="call">CE</option><option value="put">PE</option>
            </select>
            <select class="leg-pos bg-slate-800 border-none text-[10px] rounded p-1">
                <option value="long">Buy</option><option value="short">Sell</option>
            </select>
            <input type="number" placeholder="Prem" class="leg-prem bg-slate-800 border-none text-[10px] w-16 rounded p-1">
            <button class="text-red-500 hover:text-red-400 p-1" onclick="this.parentElement.remove()">×</button>
        `;
        list.appendChild(div);
    }

    async buildStrategy() {
        const type = document.getElementById('strategyType').value;
        const payload = {
            underlying: this.currentUnderlying,
            strategy_type: type,
            legs: []
        };

        if (type === 'custom') {
            document.querySelectorAll('.leg-item').forEach(leg => {
                payload.legs.push({
                    strike: parseFloat(leg.querySelector('.leg-strike').value),
                    option_type: leg.querySelector('.leg-type').value,
                    position: leg.querySelector('.leg-pos').value,
                    premium: parseFloat(leg.querySelector('.leg-prem').value),
                    expiry: '2026-12-31' // Simplified for refactor
                });
            });
        }

        try {
            const res = await fetch('/api/options/strategy/build', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(r => r.json());

            this.renderStrategyAnalysis(res);
        } catch (e) { alert("Failed to build strategy"); }
    }

    renderStrategyAnalysis(data) {
        const container = document.getElementById('strategyAnalysis');
        if (!container) return;

        container.innerHTML = `
            <div class="grid grid-cols-2 gap-4 mb-4">
                <div class="p-3 bg-black/10 rounded">
                    <div class="text-[8px] text-gray-500 uppercase">Max Profit</div>
                    <div class="text-sm font-black text-green-500">${data.max_profit}</div>
                </div>
                <div class="p-3 bg-black/10 rounded">
                    <div class="text-[8px] text-gray-500 uppercase">Max Loss</div>
                    <div class="text-sm font-black text-red-500">${data.max_loss}</div>
                </div>
            </div>
            <div class="text-[10px] text-gray-400 mb-2 uppercase font-bold">Breakeven Points: ${data.breakeven_points.join(', ') || 'N/A'}</div>
            <div class="grid grid-cols-4 gap-2 text-center">
                <div class="p-1 bg-blue-500/5 rounded"><div class="text-[7px] text-gray-500">Delta</div><div class="text-xs font-bold">${data.net_delta}</div></div>
                <div class="p-1 bg-orange-500/5 rounded"><div class="text-[7px] text-gray-500">Theta</div><div class="text-xs font-bold">${data.net_theta}</div></div>
                <div class="p-1 bg-purple-500/5 rounded"><div class="text-[7px] text-gray-500">Vega</div><div class="text-xs font-bold">${data.net_vega}</div></div>
                <div class="p-1 bg-green-500/5 rounded"><div class="text-[7px] text-gray-500">Gamma</div><div class="text-xs font-bold">${data.net_gamma}</div></div>
            </div>
        `;

        if (data.payoff_chart_data) this.renderPayoffChart(data.payoff_chart_data);
    }

    renderPayoffChart(data) {
        const ctx = document.getElementById('payoffChart')?.getContext('2d');
        if (!ctx) return;
        document.getElementById('payoffChartContainer').classList.remove('hidden');
        if (this.charts.payoff) this.charts.payoff.destroy();

        this.charts.payoff = new Chart(ctx, {
            type: 'line',
            data: {
                labels: data.prices,
                datasets: [{
                    label: 'P&L at Expiry',
                    data: data.pnl,
                    borderColor: '#3b82f6',
                    backgroundColor: 'rgba(59, 130, 246, 0.1)',
                    fill: true,
                    tension: 0.2,
                    pointRadius: 0
                }]
            },
            options: {
                responsive: true, maintainAspectRatio: false,
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.05)' } },
                    y: { grid: { color: 'rgba(255,255,255,0.1)' } }
                }
            }
        });
    }

    // Alerts Management
    async createAlert() {
        const payload = {
            name: document.getElementById('alertName').value,
            underlying: this.currentUnderlying,
            alert_type: document.getElementById('alertType').value,
            threshold: parseFloat(document.getElementById('alertThreshold').value)
        };

        await fetch('/api/alerts/create', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        this.loadAlerts();
    }

    async loadAlerts() {
        const alerts = await fetch(`/api/alerts/list/${this.currentUnderlying}`).then(r => r.json());
        this.renderAlerts(alerts);
    }

    renderAlerts(alerts) {
        const container = document.getElementById('alertsList');
        if (!container) return;
        container.innerHTML = '';

        if (alerts.length === 0) {
            container.innerHTML = '<p class="text-gray-500 text-xs italic">No active alerts for this underlying.</p>';
            return;
        }

        alerts.forEach(alert => {
            const div = document.createElement('div');
            div.className = 'flex justify-between items-center p-3 glass-panel rounded border-l-4 border-purple-500 mb-2';
            div.innerHTML = `
                <div>
                    <div class="text-xs font-bold">${alert.name}</div>
                    <div class="text-[9px] text-gray-500 uppercase">${alert.alert_type.replace('_', ' ')} @ ${alert.threshold}</div>
                </div>
                <div class="flex gap-2">
                    <button class="p-1 hover:text-blue-500" onclick="window.optionsDashboard.toggleAlert('${alert.id}')">
                        ${alert.is_active ? '⏸' : '▶'}
                    </button>
                    <button class="p-1 hover:text-red-500" onclick="window.optionsDashboard.deleteAlert('${alert.id}')">🗑</button>
                </div>
            `;
            container.appendChild(div);
        });
    }

    async toggleAlert(id) {
        await fetch(`/api/alerts/toggle/${id}`, { method: 'POST' });
        this.loadAlerts();
    }

    async deleteAlert(id) {
        if (confirm("Delete this alert?")) {
            await fetch(`/api/alerts/delete/${id}`, { method: 'DELETE' });
            this.loadAlerts();
        }
    }
}

// Bootstrap
document.addEventListener('DOMContentLoaded', () => {
    window.optionsDashboard = new OptionsDashboardManager();
});
