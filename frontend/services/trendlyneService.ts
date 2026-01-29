export interface BuildupData {
  timestamp: string;
  price: number;
  price_change: number;
  oi: number;
  oi_change: number;
  buildup_type: string;
}

export let isSessionInitialized = false;
// Using the specific CSRF token provided by the user
const PROVIDED_CSRF = import.meta.env.VITE_TRENDLYNE_CSRF || 'YOUR_CSRF_TOKEN_HERE';
const TRENDLYNE_ROOT = 'https://smartoptions.trendlyne.com/';


async function performInitialRequest() {
    const url = TRENDLYNE_ROOT;

    const headers = {
        'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36',
        'accept-language': 'en,gu;q=0.9,hi;q=0.8',
        // 'referer' can be added here, but 'referrer' in options is often more reliable
        'referer': 'https://www.google.com'
    };

    const response = await fetch(url, {
        method: 'GET',
        headers: headers,
        // The Fetch API uses the 'referrer' key to set the HTTP Referer header
        referrer: TRENDLYNE_ROOT,
        referrerPolicy: 'no-referrer-when-downgrade'
    });

    // 1. Accessing Response Headers
    console.log('Content-Type:', response.headers.get('content-type'));

    // 2. Extracting Cookies (Set-Cookie)
    // In Node.js/modern environments, use getSetCookie() for multiple cookies
    const cookies = response.headers.getSetCookie?.() || [response.headers.get('set-cookie')];
    console.log('Received Cookies:', cookies);

    return await response.json();
}


// const jsondata = await performInitialRequest();
// console.log('Initial Request JSON Data:', jsondata);


/**
 * Initializes the Trendlyne session.
 * In a browser environment, 'credentials: include' with a pre-flight fetch
 * to the root domain helps establish the required session cookies.
 */
const initTrendlyneSession = async () => {
  if (isSessionInitialized) return;

  try {
    console.log("Trendlyne: Initializing Session Warm-up...");
    // Fetching root to capture cookies in the browser's native cookie jar
    await fetch(TRENDLYNE_ROOT, {
      method: 'GET',
      credentials: 'include',
      mode: 'no-cors' // Use no-cors to at least trigger cookie placement if root has strict CORS
    });

    isSessionInitialized = true;
    console.log("Trendlyne: Session Primed.");
  } catch (e) {
    console.warn("Trendlyne: Session warm-up failed, proceeding with provided CSRF token", e);
    isSessionInitialized = true;
  }
};

const getHeaders = () => ({
  'Accept': 'application/json, text/plain, */*',
  'X-Requested-With': 'XMLHttpRequest',
  'X-CSRFToken': PROVIDED_CSRF,
  'Referer': TRENDLYNE_ROOT,
});

export const fetchExpiryDates = async (symbol: string): Promise<{ date: string, label: string }[]> => {
  await initTrendlyneSession();

  // Stock IDs for major indices on Trendlyne
  const stockIds: Record<string, number> = {
    'NIFTY': 1887,
    'BANKNIFTY': 1888, // Assumed ID for BankNifty, 1887 is Nifty 50
    'FINNIFTY': 2244,
  };

  const stockId = stockIds[symbol] || 1887;

  try {
    const url = `${TRENDLYNE_ROOT}phoenix/api/fno/get-expiry-dates/?mtype=options&stock_id=${stockId}`;
    const response = await fetch(url, {
      headers: getHeaders(),
      credentials: 'include'
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();

    // Transform Trendlyne dates into labels used by the app
    // Trendlyne returns objects like { id: 1, expiryDate: "2026-01-27", ... }
    return (data || []).map((item: any, index: number) => {
        const date = item.expiryDate; // "2026-01-27"
        const d = new Date(date);
        const day = d.getDate();
        const month = d.toLocaleString('en-US', { month: 'short' }).toLowerCase();
        const year = d.getFullYear();

        // Label format: "27-jan-2026-near", "03-feb-2026-next", etc.
        const suffix = index === 0 ? 'near' : index === 1 ? 'next' : 'far';

        return {
            date: date,
            label: `${day}-${month}-${year}-${suffix}`
        };
    });
  } catch (e) {
    console.warn(`Trendlyne: Expiry fetch failed for ${symbol}`, e);
    return [{ date: '2026-01-27', label: '27-jan-2026-near' }]; // Fallback
  }
};

export const fetchFuturesBuildup = async (symbol: string, expiry: string): Promise<BuildupData[]> => {
  await initTrendlyneSession();

  try {
    const url = `${TRENDLYNE_ROOT}phoenix/api/fno/buildup-15/${expiry}/${symbol}/?fno_mtype=futures&format=json`;
    const response = await fetch(url, {
      headers: getHeaders(),
      credentials: 'include'
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data.results || [];
  } catch (e) {
    console.warn(`Trendlyne: Futures flow failed for ${symbol}`, e);
    return generateMockBuildup();
  }
};

export const fetchOptionBuildup = async (symbol: string, expiry: string, strike: number, type: 'call' | 'put'): Promise<BuildupData[]> => {
  await initTrendlyneSession();

  try {
    // Exact URL pattern as requested: buildup-15, specific param order
    const url = `${TRENDLYNE_ROOT}phoenix/api/fno/buildup-15/${expiry}/${symbol}/?fno_mtype=options&format=json&option_type=${type}&strikePrice=${strike}`;
    const response = await fetch(url, {
      headers: getHeaders(),
      credentials: 'include'
    });

    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    return data.results || [];
  } catch (e) {
    console.warn(`Trendlyne: ${type.toUpperCase()} flow failed for strike ${strike}`, e);
    return generateMockBuildup();
  }
};

const generateMockBuildup = (): BuildupData[] => {
  const data: BuildupData[] = [];
  const now = new Date();
  const types = ["Long Buildup", "Short Buildup", "Short Covering", "Long Unwinding"];
  for (let i = 0; i < 20; i++) {
    const time = new Date(now.getTime() - i * 15 * 60000);
    data.push({
      timestamp: time.toISOString(),
      price: 25000 + (Math.random() * 100),
      price_change: (Math.random() - 0.5) * 50,
      oi: 1000000 + Math.random() * 500000,
      oi_change: (Math.random() - 0.5) * 20000,
      buildup_type: types[Math.floor(Math.random() * types.length)]
    });
  }
  return data;
};
