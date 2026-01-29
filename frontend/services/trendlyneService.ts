export interface BuildupData {
  timestamp: string;
  price: number;
  price_change: number;
  oi: number;
  oi_change: number;
  buildup_type: string;
}

const API_BASE = '/api/trendlyne';

export const isSessionInitialized = true; // Handled by backend

export const fetchExpiryDates = async (symbol: string): Promise<{ date: string, label: string }[]> => {
  try {
    const url = `${API_BASE}/expiry/${symbol}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data;
  } catch (e) {
    console.warn(`Trendlyne: Expiry fetch failed for ${symbol}`, e);
    return [];
  }
};

export const fetchFuturesBuildup = async (symbol: string, expiry: string): Promise<BuildupData[]> => {
  try {
    const url = `${API_BASE}/buildup/futures/${symbol}/${expiry}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data;
  } catch (e) {
    console.warn(`Trendlyne: Futures flow failed for ${symbol}`, e);
    return [];
  }
};

export const fetchOptionBuildup = async (symbol: string, expiry: string, strike: number, type: 'call' | 'put'): Promise<BuildupData[]> => {
  try {
    const url = `${API_BASE}/buildup/options/${symbol}/${expiry}/${strike}/${type}`;
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data;
  } catch (e) {
    console.warn(`Trendlyne: ${type.toUpperCase()} flow failed for strike ${strike}`, e);
    return [];
  }
};
