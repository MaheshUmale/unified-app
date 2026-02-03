import React, { useState, useEffect, useRef, useCallback } from 'react';
import * as API from './services/upstoxService';
import * as Trendlyne from './services/trendlyneService';
import { socket } from './services/socketService';
import { OhlcData } from './types';
import MarketChart from './components/MarketChart';
import PCRChart from './components/PCRChart';
import { ReplayControls } from './components/ReplayControls';

const App = () => {
  const [indexKey, setIndexKey] = useState('NIFTY');
  const [expiryDate, setExpiryDate] = useState('');
  const [indexData, setIndexData] = useState<OhlcData[]>([]);
  const [ceData, setCeData] = useState<OhlcData[]>([]);
  const [peData, setPeData] = useState<OhlcData[]>([]);
  const [pcrHistory, setPcrHistory] = useState<any[]>([]);
  const [atmStrike, setAtmStrike] = useState(0);

  const [loading, setLoading] = useState(false);
  const [isReplayMode, setIsReplayMode] = useState(false);
  const [replayDate, setReplayDate] = useState<string | null>(null);

  const atmOptionKeysRef = useRef({ ce: '', pe: '' });
  const indexKeyRef = useRef(indexKey);

  useEffect(() => { indexKeyRef.current = indexKey; }, [indexKey]);

  const updateCandle = useCallback((prev: OhlcData[], quote: any): OhlcData[] => {
    if (!quote) return prev;
    const tickTime = new Date(quote.timestamp);
    const tickMinute = new Date(tickTime);
    tickMinute.setSeconds(0, 0);
    tickMinute.setMilliseconds(0);

    if (!prev.length) {
        return [{
            timestamp: tickMinute.toISOString(),
            open: quote.last_price, high: quote.last_price,
            low: quote.last_price, close: quote.last_price, volume: 0
        }];
    }

    const last = { ...prev[prev.length - 1] };
    const lastMinute = new Date(new Date(last.timestamp).setSeconds(0, 0, 0));

    if (tickMinute.getTime() > lastMinute.getTime()) {
        return [...prev.slice(-499), {
            timestamp: tickMinute.toISOString(),
            open: quote.last_price, high: quote.last_price,
            low: quote.last_price, close: quote.last_price, volume: 0
        }];
    } else {
        last.close = quote.last_price;
        last.high = Math.max(last.high, quote.last_price);
        last.low = Math.min(last.low, quote.last_price);
        return [...prev.slice(0, -1), last];
    }
  }, []);

  useEffect(() => {
    const updateExpiry = async () => {
        setIndexData([]);
        setCeData([]);
        setPeData([]);
        setPcrHistory([]);
        setAtmStrike(0);
        atmOptionKeysRef.current = { ce: '', pe: '' };

        if (isReplayMode) return;

        setLoading(true);
        const expiries = await Trendlyne.fetchExpiryDates(indexKey);
        if (expiries && expiries.length > 0) {
            setExpiryDate(expiries[0].date);
        }
    };
    updateExpiry();
  }, [indexKey, isReplayMode]);

  useEffect(() => {
    socket.connect();
    const handleUpdate = (quotes: any) => {
        const { ce, pe } = atmOptionKeysRef.current;
        const idxKey = indexKeyRef.current;

        if (quotes[idxKey]) setIndexData(prev => updateCandle(prev, quotes[idxKey]));
        if (ce && quotes[ce]) setCeData(prev => updateCandle(prev, quotes[ce]));
        if (pe && quotes[pe]) setPeData(prev => updateCandle(prev, quotes[pe]));
    };

    const cleanupMessage = socket.onMessage((msg) => {
        if (msg.type === 'replay_status') {
            setIsReplayMode(!!msg.active);
            setReplayDate(msg.date || null);
        }
        if (msg.type === 'oi_update') {
            const currentSymbol = indexKeyRef.current;
            if (msg.symbol?.toUpperCase().includes(currentSymbol.toUpperCase())) {
                setPcrHistory(prev => {
                    const last = prev[prev.length - 1];
                    if (last && last.timestamp === msg.timestamp) return prev;
                    return [...prev.slice(-1000), { timestamp: msg.timestamp, pcr: msg.pcr }];
                });
            }
        }
        handleUpdate(msg);
    });

    const cleanupFootprint = socket.onFootprint(({ type, data }: any) => {
        const item = Array.isArray(data) ? data[0] : data;
        const token = item?.instrument_token;
        if (!token) return;

        const { ce, pe } = atmOptionKeysRef.current;
        const idxKey = indexKeyRef.current;

        const transform = (b: any): OhlcData => ({
            timestamp: new Date(b.ts).toISOString(),
            open: b.open, high: b.high, low: b.low, close: b.close, volume: b.volume
        });

        if (type === 'history') {
            const hist = data.map(transform);
            if (token === idxKey) setIndexData(hist);
            if (token === ce) setCeData(hist);
            if (token === pe) setPeData(hist);
        } else {
            const bar = transform(data);
            const update = (prev: OhlcData[]) => {
                if (!prev.length) return [bar];
                const last = prev[prev.length - 1];
                if (bar.timestamp === last.timestamp) return [...prev.slice(0, -1), bar];
                return [...prev.slice(-499), bar];
            };
            if (token === idxKey) setIndexData(update);
            if (token === ce) setCeData(update);
            if (token === pe) setPeData(update);
        }
    });

    return () => { cleanupMessage(); cleanupFootprint(); };
  }, [updateCandle]);

  const loadData = useCallback(async () => {
    if (isReplayMode && !replayDate) return;
    setLoading(true);
    try {
        socket.setSubscriptions([indexKey]);
        const [candles, pcr] = await Promise.all([
            API.getIntradayCandles(indexKey, isReplayMode ? replayDate! : undefined),
            API.getHistoricalPcr(indexKey, isReplayMode ? replayDate! : undefined)
        ]);

        if (candles.length) {
            setIndexData(candles);
            const currentPrice = candles[candles.length - 1].close;
            const step = indexKey === 'NIFTY' ? 50 : 100;
            const currentAtm = Math.round(currentPrice / step) * step;
            setAtmStrike(currentAtm);

            if (expiryDate && currentAtm > 0 && !isReplayMode) {
                const chain = await API.getOptionChain(indexKey, expiryDate);
                const atmItem = chain.find(i => i.strike_price === currentAtm);
                if (atmItem) {
                    const ceKey = atmItem.call_options.instrument_key;
                    const peKey = atmItem.put_options.instrument_key;
                    atmOptionKeysRef.current = { ce: ceKey, pe: peKey };
                    const [ceHist, peHist] = await Promise.all([
                        API.getIntradayCandles(ceKey),
                        API.getIntradayCandles(peKey)
                    ]);
                    setCeData(ceHist);
                    setPeData(peHist);
                    socket.setSubscriptions([indexKey, ceKey, peKey]);
                }
            }
        }
        setPcrHistory(pcr);
    } catch (e) {
        console.error(e);
    } finally {
        setLoading(false);
    }
  }, [indexKey, atmStrike, expiryDate, isReplayMode, replayDate]);

  useEffect(() => { loadData(); }, [loadData]);

  return (
    <div className="min-h-screen bg-black text-gray-300 flex flex-col font-sans">
      <header className="h-14 border-b border-gray-900 px-6 flex items-center justify-between bg-black/50 backdrop-blur-md sticky top-0 z-50">
        <div className="flex items-center gap-6">
          <span className="text-xl font-black text-white tracking-tighter">PRO<span className="text-blue-500">DESK</span></span>
          <select
            value={indexKey}
            onChange={e => setIndexKey(e.target.value)}
            disabled={isReplayMode}
            className="bg-gray-950 border border-gray-800 rounded px-2 py-1 text-xs font-bold text-blue-400 outline-none"
          >
            <option value="NIFTY">NIFTY 50</option>
            <option value="BANKNIFTY">BANK NIFTY</option>
            <option value="FINNIFTY">FIN NIFTY</option>
          </select>
        </div>
        <div className="flex items-center gap-4">
          <ReplayControls
            currentIndexKey={indexKey}
            onReplaySessionInfo={(info) => {
                setAtmStrike(info.atm);
                if (info.expiry) setExpiryDate(info.expiry);
                atmOptionKeysRef.current = { ce: info.suggested_ce || '', pe: info.suggested_pe || '' };
            }}
          />
          <div className="text-xs font-bold text-gray-500">SPOT: <span className="text-white font-mono">{indexData.length ? indexData[indexData.length-1].close.toFixed(2) : '---'}</span></div>
          <div className="text-xs font-bold text-gray-500">ATM: <span className="text-blue-500 font-mono">{atmStrike || '---'}</span></div>
        </div>
      </header>

      <main className="p-4 grid grid-cols-12 gap-4 flex-1 overflow-hidden">
        <div className="col-span-12 lg:col-span-8 h-full flex flex-col gap-4">
            <div className="flex-1 bg-gray-950/50 rounded-xl border border-gray-900 overflow-hidden">
                <MarketChart title={`${indexKey} INDEX`} data={indexData} />
            </div>
            <div className="h-[250px] bg-gray-950/50 rounded-xl border border-gray-900 overflow-hidden">
                <PCRChart title="PCR ANALYTICS" data={pcrHistory} />
            </div>
        </div>
        <div className="col-span-12 lg:col-span-4 h-full flex flex-col gap-4">
            <div className="flex-1 bg-gray-950/50 rounded-xl border border-gray-900 overflow-hidden">
                <MarketChart title="ATM CALL" data={ceData} />
            </div>
            <div className="flex-1 bg-gray-950/50 rounded-xl border border-gray-900 overflow-hidden">
                <MarketChart title="ATM PUT" data={peData} />
            </div>
        </div>
      </main>
    </div>
  );
};

export default App;
