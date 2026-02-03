import { OhlcData, OptionChainItem, MarketSentiment } from '../types';

// Internal Backend API Base
const API_BASE = '/api/upstox';

// --- API HELPERS ---
const safeFetch = async (url: string) => {
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
        const data = await res.json();
        return data;
    } catch (e) {
        console.warn(`API Fail: ${url}`, e);
        return null;
    }
};

// --- EXPORTS ---

export const getReplayDates = async (): Promise<string[]> => {
    const data = await safeFetch('/api/replay/dates');
    return data || [];
};

export const getReplaySessionInfo = async (date: string, indexKey: string) => {
    return await safeFetch(`/api/replay/session_info/${date}/${encodeURIComponent(indexKey)}`);
};

export const getIntradayCandles = async (key: string, date?: string): Promise<OhlcData[]> => {
    let url = `${API_BASE}/intraday/${encodeURIComponent(key)}`;
    if (date) url += `?date=${date}`;

    const data = await safeFetch(url);

    if (data && data.candles) {
        return data.candles.map((c: any[]) => ({
            timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
        })).reverse();
    }
    return [];
};

export const getHistoricalPcr = async (symbol: string, date?: string) => {
    let url = `/api/analytics/pcr/${symbol}`;
    if (date) url += `?date=${date}`;
    const data = await safeFetch(url);
    return data || [];
};

export const getOptionChain = async (key: string, expiry: string): Promise<OptionChainItem[]> => {
    const url = `${API_BASE}/option_chain/${encodeURIComponent(key)}/${expiry}`;
    const data = await safeFetch(url);
    if (data) {
        return data.map((item: any) => ({
            strike_price: item.strike_price,
            call_options: item.call_options,
            put_options: item.put_options
        })).sort((a: any, b: any) => a.strike_price - b.strike_price);
    }
    return [];
};

export const calculateSentiment = (chain: OptionChainItem[]): MarketSentiment => {
    let totalCe = 0, totalPe = 0;
    let maxCe = 0, maxPe = 0;
    let maxCeStrike = 0, maxPeStrike = 0;

    chain.forEach(i => {
        const ce = i.call_options?.market_data?.oi || 0;
        const pe = i.put_options?.market_data?.oi || 0;
        totalCe += ce;
        totalPe += pe;
        if(ce > maxCe) { maxCe = ce; maxCeStrike = i.strike_price; }
        if(pe > maxPe) { maxPe = pe; maxPeStrike = i.strike_price; }
    });

    const pcr = totalCe ? parseFloat((totalPe / totalCe).toFixed(2)) : 0;
    return {
        pcr,
        trend: pcr > 1.2 ? 'BULLISH' : pcr < 0.8 ? 'BEARISH' : 'NEUTRAL',
        maxCallOI: maxCe, maxPutOI: maxPe,
        maxCallStrike: maxCeStrike, maxPutStrike: maxPeStrike
    };
};
