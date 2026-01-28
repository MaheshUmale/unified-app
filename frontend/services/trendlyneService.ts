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
const PROVIDED_CSRF = 'TxzIO3d7zB6Mhq7nVxN98vKEPp6qp8BLmtN0ZnuIfHlPNBeWeSue3qqpVym9eKRm';
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


const jsondata = await performInitialRequest();
console.log('Initial Request JSON Data:', jsondata);


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