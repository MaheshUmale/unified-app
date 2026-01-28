import { PROVIDED_TOKEN } from '../constants';
import { OhlcData, OptionChainItem, MarketSentiment } from '../types';

// V3 Base URL
const API_BASE_V3 = 'https://api.upstox.com/v3';
const API_BASE_V2 = 'https://api.upstox.com/v2'; // Keeping V2 for chain/contracts if V3 doesn't support them same way

// --- MOCK GENERATORS ---
const generateMockCandles = (startPrice: number, count: number): OhlcData[] => {
  const candles: OhlcData[] = [];
  let currentPrice = startPrice;
  const now = new Date();
  for (let i = count; i > 0; i--) {
    const time = new Date(now.getTime() - i * 60000);
    const volatility = currentPrice * 0.0005;
    const change = (Math.random() - 0.5) * volatility * 2;
    const open = currentPrice;
    const close = currentPrice + change;
    candles.push({
      timestamp: time.toISOString(),
      open,
      high: Math.max(open, close) + Math.random(),
      low: Math.min(open, close) - Math.random(),
      close,
      volume: Math.floor(Math.random() * 100000)
    });
    currentPrice = close;
  }
  return candles;
};

const generateMockChain = (spot: number, step: number): OptionChainItem[] => {
    const center = Math.round(spot / step) * step;
    const chain: OptionChainItem[] = [];
    for (let i = -10; i <= 10; i++) {
        const strike = center + (i * step);
        chain.push({
            strike_price: strike,
            call_options: {
                instrument_key: `mock_ce_${strike}`,
                market_data: { ltp: Math.max(1, (spot - strike) + 50), oi: 100000 + Math.random() * 50000, volume: 1000, bid_price: 0, ask_price: 0 },
                option_greeks: { delta: 0.5, theta: -0.1, gamma: 0.01, vega: 0.2 }
            },
            put_options: {
                instrument_key: `mock_pe_${strike}`,
                market_data: { ltp: Math.max(1, (strike - spot) + 50), oi: 100000 + Math.random() * 50000, volume: 1000, bid_price: 0, ask_price: 0 },
                option_greeks: { delta: -0.5, theta: -0.1, gamma: 0.01, vega: 0.2 }
            }
        });
    }
    return chain;
};

// --- API HELPERS ---
const headers = {
    'Authorization': `Bearer ${PROVIDED_TOKEN}`,
    'Accept': 'application/json',
    'Content-Type': 'application/json'
};

const safeFetch = async (url: string) => {
    try {
        const res = await fetch(url, { headers });
        if (!res.ok) throw new Error(`${res.status}: ${res.statusText}`);
        const json = await res.json();
        if (json.status === 'error') throw new Error(json.errors?.[0]?.message || 'API Error');
        return json.data;
    } catch (e) {
        console.warn(`API Fail: ${url}`, e);
        return null;
    }
};

// --- EXPORTS ---

export const getIntradayCandles = async (key: string): Promise<OhlcData[]> => {
    // V3 Pattern: historical-candle/intraday/:instrument_key/minutes/:interval
    const url = `${API_BASE_V3}/historical-candle/intraday/${encodeURIComponent(key)}/minutes/1`;
    const data = await safeFetch(url);

    if (data && data.candles) {
        return data.candles.map((c: any[]) => ({
            timestamp: c[0], open: c[1], high: c[2], low: c[3], close: c[4], volume: c[5]
        })).reverse();
    }
    // Fallback
    const start = key.includes('Nifty 50') ? 25000 : key.includes('Bank') ? 58000 : 100;
    return generateMockCandles(start, 100);
};

export const getOptionChain = async (key: string, expiry: string): Promise<OptionChainItem[]> => {
    // Using V2 for option chain as V3 structure differs or might be in preview
    const data = await safeFetch(`${API_BASE_V2}/option/chain?instrument_key=${encodeURIComponent(key)}&expiry_date=${expiry}`);
    if (data) {
        return data.map((item: any) => ({
            strike_price: item.strike_price,
            call_options: item.call_options,
            put_options: item.put_options
        })).sort((a: any, b: any) => a.strike_price - b.strike_price);
    }
    const spot = key.includes('Nifty 50') ? 25000 : 58000;
    return generateMockChain(spot, key.includes('Nifty 50') ? 50 : 100);
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