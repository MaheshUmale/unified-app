
const safeFetch = async (url: string, options?: RequestInit) => {
    try {
        const res = await fetch(url, options);
        if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
        return await res.json();
    } catch (e) {
        console.warn(`API Fail: ${url}`, e);
        return null;
    }
};

export const getAtmStrategyAnalysis = async (indexKey: string, atmStrike: number, expiry: string) => {
    return await safeFetch(`/api/strategy/atm-buying?index_key=${encodeURIComponent(indexKey)}&atm_strike=${atmStrike}&expiry=${expiry}`);
};

export const updateStrategyContext = async (symbol: string, globalCues: string, majorEvents: string) => {
    return await safeFetch(`/api/strategy/context`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ symbol, global_cues: globalCues, major_events: majorEvents })
    });
};

export const searchMarketCues = async () => {
    return await safeFetch(`/api/strategy/search-cues`);
};

export const syncSessionData = async () => {
    return await safeFetch(`/api/backfill/session`, { method: 'POST' });
};
