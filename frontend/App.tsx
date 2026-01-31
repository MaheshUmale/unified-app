import React, { useState, useEffect, useRef, useCallback } from 'react';
import { INDICES } from './constants';
import * as API from './services/upstoxService';
import * as Trendlyne from './services/trendlyneService';
import { socket } from './services/socketService';
import { OhlcData, MarketSentiment } from './types';
import MarketChart from './components/MarketChart';
import BuildupPanel from './components/BuildupPanel';
import SentimentAnalysis from './components/SentimentAnalysis';
import PCRVsSpotChart from './components/AnalyticsCharts';
import { ReplayControls } from './components/ReplayControls';
import StrategyDashboard from './components/StrategyDashboard';

type TabType = 'TERMINAL' | 'STRATEGY' | 'ANALYTICS';

const App = () => {
  const [activeTab, setActiveTab] = useState<TabType>('STRATEGY');
  const [indexKey, setIndexKey] = useState(INDICES.NIFTY.key);
  const [expiryLabel, setExpiryLabel] = useState('');
  const [expiryDate, setExpiryDate] = useState('');

  const [indexData, setIndexData] = useState<OhlcData[]>([]);
  const [ceData, setCeData] = useState<OhlcData[]>([]);
  const [peData, setPeData] = useState<OhlcData[]>([]);
  const [sentiment, setSentiment] = useState<MarketSentiment | null>(null);
  const [atmStrike, setAtmStrike] = useState(0);

  const [futuresBuildup, setFuturesBuildup] = useState<Trendlyne.BuildupData[]>([]);
  const [ceBuildup, setCeBuildup] = useState<Trendlyne.BuildupData[]>([]);
  const [peBuildup, setPeBuildup] = useState<Trendlyne.BuildupData[]>([]);
  const [historicalPcr, setHistoricalPcr] = useState<any[]>([]);

  const [loading, setLoading] = useState(false);
  const [lastSync, setLastSync] = useState<Date>(new Date());
  const [trendlyneReady, setTrendlyneReady] = useState(false);
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
    const lastTime = new Date(last.timestamp);
    const lastMinute = new Date(lastTime.setSeconds(0, 0));

    if (tickMinute.getTime() > lastMinute.getTime()) {
        const newCandle: OhlcData = {
            timestamp: tickMinute.toISOString(),
            open: quote.last_price, high: quote.last_price,
            low: quote.last_price, close: quote.last_price, volume: 0
        };
        return [...prev.slice(-499), newCandle];
    } else {
        last.close = quote.last_price;
        last.high = Math.max(last.high, quote.last_price);
        last.low = Math.min(last.low, quote.last_price);
        return [...prev.slice(0, -1), last];
    }
  }, []);

  const lastExpiryIndexRef = useRef('');

  useEffect(() => {
    const updateExpiry = async () => {
        if (isReplayMode) return; // Skip external expiry fetch in replay mode
        const symbol = indexKey.includes('Nifty 50') ? 'NIFTY' : 'BANKNIFTY';
        if (lastExpiryIndexRef.current === symbol) return;

        setLoading(true);
        const expiries = await Trendlyne.fetchExpiryDates(symbol);
        if (expiries && expiries.length > 0) {
            lastExpiryIndexRef.current = symbol;
            setExpiryDate(expiries[0].date);
            setExpiryLabel(expiries[0].label);
        }
    };
    updateExpiry();
  }, [indexKey, isReplayMode]);

  useEffect(() => {
    socket.connect();
    const handleUpdate = (quotes: any) => {
        const { ce, pe } = atmOptionKeysRef.current;
        const idxKey = indexKeyRef.current;

        if (quotes[idxKey]) {
            setIndexData(prev => updateCandle(prev, quotes[idxKey]));
            setLastSync(new Date());
        }

        if (ce && quotes[ce]) {
            setCeData(prev => updateCandle(prev, quotes[ce]));
        }

        if (pe && quotes[pe]) {
            setPeData(prev => updateCandle(prev, quotes[pe]));
        }
    };

    const handleFootprint = ({ type, data }: { type: 'history' | 'update', data: any }) => {
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
            const updateBar = (prev: OhlcData[]) => {
                if (!prev.length) return [bar];
                const last = prev[prev.length - 1];
                if (bar.timestamp === last.timestamp) return [...prev.slice(0, -1), bar];
                if (new Date(bar.timestamp).getTime() > new Date(last.timestamp).getTime()) return [...prev.slice(-499), bar];
                return prev;
            };
            if (token === idxKey) setIndexData(updateBar);
            if (token === ce) setCeData(updateBar);
            if (token === pe) setPeData(updateBar);
        }
    };

    const cleanupMessage = socket.onMessage((msg) => {
        if (msg.type === 'replay_status') {
            setIsReplayMode(msg.active);
            setReplayDate(msg.date || null);
            // If it's a fresh replay start
            if (msg.active && msg.is_new) {
                setIndexData([]);
                setCeData([]);
                setPeData([]);
                setHistoricalPcr([]);
                setFuturesBuildup([]);
                setCeBuildup([]);
                setPeBuildup([]);
            }
        }
        if (msg.type === 'oi_update') {
            const currentSymbol = indexKeyRef.current.includes('Nifty 50') ? 'NIFTY' : 'BANKNIFTY';
            if (msg.symbol !== currentSymbol) return;

            setLastSync(new Date());

            setSentiment(prev => {
                if (!prev) return null;
                return {
                    ...prev,
                    pcr: msg.pcr,
                    trend: msg.pcr > 1.2 ? 'BULLISH' : msg.pcr < 0.8 ? 'BEARISH' : 'NEUTRAL',
                    maxCallOI: msg.call_oi || prev.maxCallOI,
                    maxPutOI: msg.put_oi || prev.put_oi
                };
            });

            setHistoricalPcr(prev => {
                const newPoint = { timestamp: msg.timestamp, pcr: msg.pcr, price: 0 };
                // Avoid duplicate timestamps
                if (prev.length > 0 && prev[prev.length - 1].timestamp === msg.timestamp) {
                    const updated = [...prev];
                    updated[updated.length - 1] = newPoint;
                    return updated;
                }
                return [...prev, newPoint].slice(-100);
            });
        }
        handleUpdate(msg);
    });
    const cleanupFootprint = socket.onFootprint(handleFootprint);
    return () => {
        cleanupMessage();
        cleanupFootprint();
    };
  }, [updateCandle]);

  const loadData = useCallback(async () => {
    // In replay mode, we only load data if we have a replay date
    if (isReplayMode && !replayDate) return;

    const currentSymbol = indexKey.includes('Nifty 50') ? 'NIFTY' : 'BANKNIFTY';

    setLoading(true);
    try {
        // Start index subscription immediately
        socket.setSubscriptions([indexKey]);

        // 1. Fetch Index Candles first (unconditionally)
        const candles = await API.getIntradayCandles(indexKey, isReplayMode ? replayDate! : undefined).catch(() => []);
        let currentAtm = atmStrike;

        if (candles && candles.length > 0) {
            setIndexData(candles);
            const currentPrice = candles[candles.length - 1].close;
            const step = currentSymbol === 'NIFTY' ? 50 : 100;
            currentAtm = Math.round(currentPrice / step) * step;
            setAtmStrike(currentAtm);
        }

        // 2. Fetch Option Chain and Buildup if expiry is available
        if (expiryDate) {
            let ceKey = atmOptionKeysRef.current.ce;
            let peKey = atmOptionKeysRef.current.pe;

            if (!isReplayMode) {
                const chainData = await API.getOptionChain(indexKey, expiryDate).catch(() => []);
                if (chainData && chainData.length > 0) {
                    setSentiment(API.calculateSentiment(chainData));
                    const atmItem = chainData.find(i => i.strike_price === currentAtm);
                    if (atmItem) {
                        ceKey = atmItem.call_options.instrument_key;
                        peKey = atmItem.put_options.instrument_key;
                        atmOptionKeysRef.current = { ce: ceKey, pe: peKey };
                    }
                }
            }

            if (ceKey && peKey) {
                const [ceHist, peHist, fBuildup, cBuildup, pBuildup] = await Promise.all([
                    API.getIntradayCandles(ceKey, isReplayMode ? replayDate! : undefined).catch(() => []),
                    API.getIntradayCandles(peKey, isReplayMode ? replayDate! : undefined).catch(() => []),
                    Trendlyne.fetchFuturesBuildup(currentSymbol, expiryDate).catch(() => []),
                    Trendlyne.fetchOptionBuildup(currentSymbol, expiryDate, currentAtm, 'call').catch(() => []),
                    Trendlyne.fetchOptionBuildup(currentSymbol, expiryDate, currentAtm, 'put').catch(() => [])
                ]);

                setCeData(ceHist);
                setPeData(peHist);
                setFuturesBuildup(fBuildup);
                setCeBuildup(cBuildup);
                setPeBuildup(pBuildup);
                socket.setSubscriptions([indexKey, ceKey, peKey]);
                setTrendlyneReady(Trendlyne.isSessionInitialized);
            }

            const pcrHist = await fetch(`/api/analytics/pcr/${currentSymbol}${isReplayMode ? `?date=${replayDate}` : ''}`).then(r => r.json()).catch(() => []);
            if (pcrHist && pcrHist.length > 0) {
                setHistoricalPcr(prev => {
                    // Only use historical if we don't have many live points yet
                    // or merge them properly. For simplicity, if we have live points,
                    // we just keep them if they are newer.
                    if (prev.length > 5) return prev;
                    return pcrHist;
                });
            }
        }
        setLastSync(new Date());
    } catch (e) {
        console.error("Dashboard Load Error:", e);
    } finally {
        setLoading(false);
    }
  }, [indexKey, atmStrike, expiryLabel, isReplayMode, replayDate]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const symbolLabel = indexKey.includes('Nifty 50') ? 'NIFTY' : 'BANKNIFTY';

  return (
    <div className="min-h-screen bg-gray-950 text-gray-300 flex flex-col antialiased w-full h-full">
      {loading && <div className="absolute top-0 left-0 w-full z-[100] loading-bar"></div>}

      <header className="h-16 glass-panel border-b border-white/5 sticky top-0 z-50 px-6 flex items-center justify-between">
        <div className="flex items-center gap-8">
          <div className="flex flex-col cursor-pointer" onClick={() => setActiveTab('TERMINAL')}>
            <span className="text-2xl font-black text-white tracking-tighter italic leading-none">PRO<span className="text-brand-blue">DESK</span></span>
            <span className="text-[8px] text-gray-600 font-bold tracking-[0.4em] uppercase">Integrated Terminal</span>
          </div>
          <div className="h-8 w-[1px] bg-gray-800 mx-1"></div>
          <div className="flex gap-1 p-1 bg-black/40 rounded-lg border border-white/5">
            {(['STRATEGY', 'TERMINAL', 'ANALYTICS'] as TabType[]).map(tab => (
                <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase tracking-widest transition-all ${
                        activeTab === tab ? 'bg-brand-blue text-white shadow-lg shadow-brand-blue/20' : 'text-gray-500 hover:text-gray-300'
                    }`}
                >
                    {tab === 'ANALYTICS' ? 'FLOW & DATA' : tab}
                </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex gap-3">
            <select
              value={indexKey}
              onChange={e => setIndexKey(e.target.value)}
              disabled={isReplayMode}
              className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-[11px] font-black text-brand-blue outline-none focus:ring-1 focus:ring-brand-blue transition-all disabled:opacity-50"
            >
              <option value={INDICES.NIFTY.key}>NIFTY 50</option>
              <option value={INDICES.BANKNIFTY.key}>BANK NIFTY</option>
            </select>
            <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-[10px] flex items-center gap-2">
              <span className="text-gray-600 font-bold uppercase text-[8px]">Expiry</span>
              <span className="text-gray-100 font-black font-mono-data tracking-tight">{expiryLabel.replace('-near', '').toUpperCase()}</span>
            </div>
            <button
              onClick={() => loadData()}
              disabled={loading || isReplayMode}
              className={`bg-gray-800 hover:bg-gray-700 p-2 rounded-lg border border-white/5 transition-colors group ${(loading || isReplayMode) ? 'opacity-50' : ''}`}
              title={isReplayMode ? "Disabled in Replay" : "Refresh"}
            >
              <svg className={`w-4 h-4 text-gray-400 group-hover:text-brand-blue ${loading ? 'animate-spin' : ''}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
            </button>
          </div>
          <div className="h-8 w-[1px] bg-gray-800 mx-1"></div>
          <div className="flex items-center gap-6">
            <div className="flex flex-col items-end min-w-[80px]">
                <span className="text-[8px] text-gray-600 font-bold uppercase tracking-widest">SPOT</span>
                <span className="text-white font-black font-mono-data text-sm">
                    {indexData.length ? indexData[indexData.length-1].close.toFixed(2) : '---'}
                </span>
            </div>
            <div className="flex flex-col items-end min-w-[80px]">
                <span className="text-[8px] text-gray-600 font-bold uppercase tracking-widest">ATM</span>
                <span className="text-brand-blue font-black font-mono-data text-sm">{atmStrike || '---'}</span>
            </div>
          </div>
        </div>
      </header>

      <div className="px-4 pt-4">
          <ReplayControls
            currentIndexKey={indexKey}
            onReplaySessionInfo={(info) => {
                setAtmStrike(info.atm);
                if (info.expiry) {
                    setExpiryDate(info.expiry);
                    setExpiryLabel(info.expiry);
                }
                atmOptionKeysRef.current = {
                    ce: info.suggested_ce || '',
                    pe: info.suggested_pe || ''
                };
            }}
          />
      </div>

      <main className="p-4 flex-1 overflow-hidden flex flex-col">
        {activeTab === 'TERMINAL' && (
            <div className="grid grid-cols-12 gap-4 h-full animate-fadeIn">
                <div className="col-span-12 xl:col-span-8 flex flex-col gap-4">
                    <div className="flex-1 glass-panel rounded-xl p-2 glow-border-blue relative">
                        <div className="absolute top-4 left-4 z-10 bg-brand-blue/20 px-2 py-0.5 rounded text-[8px] font-black text-brand-blue uppercase">Spot Execution</div>
                        {indexData.length > 0 ? (
                            <MarketChart title={`${symbolLabel} INDEX`} data={indexData} />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-600 uppercase font-mono tracking-widest">Awaiting Index Feed...</div>
                        )}
                    </div>
                </div>
                <div className="col-span-12 xl:col-span-4 flex flex-col gap-4">
                    <div className="flex-1 glass-panel rounded-xl p-2 relative">
                        <div className="absolute top-4 right-4 z-10 bg-brand-green/20 px-2 py-0.5 rounded text-[8px] font-black text-brand-green uppercase">CE Premium</div>
                        {ceData.length > 0 ? (
                            <MarketChart title={`ATM ${atmStrike} CE`} data={ceData} />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-600 uppercase font-mono tracking-widest">Awaiting Call Data...</div>
                        )}
                    </div>
                    <div className="flex-1 glass-panel rounded-xl p-2 relative">
                        <div className="absolute top-4 right-4 z-10 bg-brand-red/20 px-2 py-0.5 rounded text-[8px] font-black text-brand-red uppercase">PE Premium</div>
                        {peData.length > 0 ? (
                            <MarketChart title={`ATM ${atmStrike} PE`} data={peData} />
                        ) : (
                            <div className="w-full h-full flex items-center justify-center text-[10px] text-gray-600 uppercase font-mono tracking-widest">Awaiting Put Data...</div>
                        )}
                    </div>
                </div>
            </div>
        )}

        {activeTab === 'ANALYTICS' && (
            <div className="flex flex-col gap-4 h-full animate-fadeIn overflow-hidden">
                <div className="grid grid-cols-12 gap-4 h-1/2 min-h-0">
                    <div className="col-span-12 xl:col-span-3 flex flex-col gap-4">
                        {sentiment ? (
                            <SentimentAnalysis sentiment={sentiment} />
                        ) : (
                            <div className="glass-panel rounded-xl p-8 flex items-center justify-center text-[9px] text-gray-600 font-mono uppercase tracking-widest">Crunching Sentiment...</div>
                        )}
                        <div className="glass-panel rounded-xl p-4">
                          <div className="flex justify-between items-center mb-2">
                            <h3 className="text-[8px] font-black text-gray-600 uppercase">System Status</h3>
                            <div className="flex items-center gap-1.5">
                                <div className="w-1.5 h-1.5 rounded-full bg-brand-green animate-pulse"></div>
                                <span className="text-[8px] font-black text-brand-green">LIVE</span>
                            </div>
                          </div>
                          <div className="space-y-1 font-mono-data text-[9px]">
                            <div className="flex justify-between">
                              <span className="text-gray-600">Last Pulse:</span>
                              <span className="text-gray-400">{lastSync.toLocaleTimeString()}</span>
                            </div>
                          </div>
                        </div>
                    </div>
                    <div className="col-span-12 xl:col-span-9 flex flex-col gap-4 overflow-hidden">
                        <div className="flex-1 glass-panel rounded-xl p-4 flex flex-col min-h-0">
                            <div className="flex justify-between items-center mb-4">
                               <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Sentiment Convergence (PCR)</h3>
                            </div>
                            <div className="flex-1">
                              <PCRVsSpotChart pcrData={historicalPcr} spotData={indexData} title="Market Sentiment Convergence" />
                            </div>
                        </div>
                    </div>
                </div>
                <div className="grid grid-cols-12 gap-4 h-1/2 min-h-0">
                    <div className="col-span-12 xl:col-span-4 h-full min-h-0">
                        <BuildupPanel title={`${symbolLabel} FUTURES FLOW`} data={futuresBuildup} />
                    </div>
                    <div className="col-span-12 xl:col-span-4 h-full min-h-0">
                        <BuildupPanel title={`ATM CE ${atmStrike} FLOW`} data={ceBuildup} />
                    </div>
                    <div className="col-span-12 xl:col-span-4 h-full min-h-0">
                        <BuildupPanel title={`ATM PE ${atmStrike} FLOW`} data={peBuildup} />
                    </div>
                </div>
            </div>
        )}

        {activeTab === 'STRATEGY' && (
            <StrategyDashboard
                indexKey={indexKey}
                atmStrike={atmStrike}
                expiryDate={expiryDate}
                symbol={symbolLabel}
            />
        )}
      </main>

      <footer className="h-8 glass-panel border-t border-white/5 flex items-center justify-between px-6 text-[8px] font-mono text-gray-600 uppercase tracking-[0.2em]">
        <div className="flex gap-6 items-center">
          <span className="flex items-center gap-1"><div className="w-1.5 h-1.5 bg-brand-blue rounded-full animate-pulse"></div> V3 SOCKET CONNECTING</span>
          {sentiment && (
              <span className="border-l border-gray-800 pl-6">
                PCR: <span className={sentiment.pcr > 1 ? 'text-brand-green' : 'text-brand-red'}>{sentiment.pcr}</span> |
                RES: <span className="text-brand-red">{sentiment.maxCallStrike}</span> |
                SUP: <span className="text-brand-green">{sentiment.maxPutStrike}</span>
              </span>
          )}
        </div>
        <div className="flex gap-4">
            <span className={trendlyneReady ? 'text-brand-green' : 'text-gray-600'}>
                Auth Status: {trendlyneReady ? 'SECURE' : 'PENDING'}
            </span>
            <span className="italic uppercase">ProDesk v4.4 Secure Tap</span>
        </div>
      </footer>
    </div>
  );
};

export default App;