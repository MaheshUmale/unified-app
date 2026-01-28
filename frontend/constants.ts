export const API_BASE_URL = 'https://api.upstox.com/v2';
export const PROVIDED_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI3NkFGMzUiLCJqdGkiOiI2OTc4MzEzZmM3YmIxYTdkYTQ4ZThjZDMiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc2OTQ4NDYwNywiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzY5NTUxMjAwfQ.bSH3wxNgCR48xzsvxcEWl6vK_ihJap2_g1YfC4q0tvQ";

export const INDICES = {
  NIFTY: {
    key: 'NSE_INDEX|Nifty 50',
    symbol: 'NIFTY',
    step: 50
  },
  BANKNIFTY: {
    key: 'NSE_INDEX|Nifty Bank',
    symbol: 'BANKNIFTY',
    step: 100
  }
};

export const LIVE_FEED_RATE = 2000; // Poll rate for pseudo-live data