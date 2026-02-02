export const API_BASE_URL = 'https://api.upstox.com/v2';
export const PROVIDED_TOKEN = import.meta.env.VITE_UPSTOX_TOKEN || "YOUR_TOKEN_HERE";

export const INDICES = {
  NIFTY: {
    key: 'NIFTY',
    symbol: 'NIFTY',
    step: 50
  },
  BANKNIFTY: {
    key: 'BANKNIFTY',
    symbol: 'BANKNIFTY',
    step: 100
  },
  FINNIFTY: {
    key: 'FINNIFTY',
    symbol: 'FINNIFTY',
    step: 40
  }
};

export const LIVE_FEED_RATE = 2000; // Poll rate for pseudo-live data
