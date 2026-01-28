import React, { useState, useEffect, useRef, useCallback } from 'react';
import { INDICES } from './constants';
import * as API from './services/upstoxService';
import * as Trendlyne from './services/trendlyneService';
import { socket } from './services/socketService';
import { OhlcData, MarketSentiment } from './types';
import MarketChart from './components/MarketChart';
import BuildupPanel from './components/BuildupPanel';
import SentimentAnalysis from './components/SentimentAnalysis';

type TabType = 'TERMINAL' | 'ANALYTICS' | 'FLOW';

const App = () => {
  const [activeTab, setActiveTab] = useState<TabType>('TERMINAL');
  const [indexKey, setIndexKey] = useState(INDICES.NIFTY.key);
  const [expiryLabel, setExpiryLabel] = useState('27-jan-2026-near');

  const [indexData, setIndexData] = useState<OhlcData[]>([]);
  const [ceData, setCeData] = useState<OhlcData[]>([]);
  const [peData, setPeData] = useState<OhlcData[]>([]);
  const [sentiment, setSentiment] = useState<MarketSentiment | null>(null);
  const [atmStrike, setAtmStrike] = useState(0);

  const [futuresBuildup, setFuturesBuildup] = useState<Trendlyne.BuildupData[]>([]);
  const [ceBuildup, setCeBuildup] = useState<Trendlyne.BuildupData[]>([]);
  const [peBuildup, setPeBuildup] = useState<Trendlyne.BuildupData[]>([]);

  const [loading, setLoading] = useState(false);
  const [lastSync, setLastSync] = useState<Date>(new Date());
  const [trendlyneReady, setTrendlyneReady] = useState(false);

  const atmOptionKeysRef = useRef({ ce: '', pe: '' });
  const indexKeyRef = useRef(indexKey);

  useEffect(() => { indexKeyRef.current = indexKey; }, [indexKey]);

  const updateCandle = useCallback((prev: OhlcData[], quote: any): OhlcData[] => {
    if (!quote || !prev.length) return prev;
    const tickTime = new Date(quote.timestamp);
    const tickMinute = new Date(tickTime);
    tickMinute.setSeconds(0, 0);
    tickMinute.setMilliseconds(0);

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

  useEffect(() => {
    socket.connect();
    const handleUpdate = (quotes: any) => {
        if (quotes[indexKeyRef.current]) setIndexData(prev => updateCandle(prev, quotes[indexKeyRef.current]));
        const { ce, pe } = atmOptionKeysRef.current;
        if (ce && quotes[ce]) setCeData(prev => updateCandle(prev, quotes[ce]));
        if (pe && quotes[pe]) setPeData(prev => updateCandle(prev, quotes[pe]));
    };
    return socket.onMessage(handleUpdate);
  }, [updateCandle]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
        const currentSymbol = indexKey.includes('Nifty 50') ? 'NIFTY' : 'BANKNIFTY';

        const [candles, chainData] = await Promise.all([
            API.getIntradayCandles(indexKey).catch(() => []),
            API.getOptionChain(indexKey, '2026-01-27').catch(() => [])
        ]);

        if (candles && candles.length > 0) {
            setIndexData(candles);
            const currentPrice = candles[candles.length - 1].close;
            const step = currentSymbol === 'NIFTY' ? 50 : 100;
            const atm = Math.round(currentPrice / step) * step;
            setAtmStrike(atm);

            if (chainData && chainData.length > 0) {
                setSentiment(API.calculateSentiment(chainData));
                const atmItem = chainData.find(i => i.strike_price === atm);

                if (atmItem) {
                    const ceKey = atmItem.call_options.instrument_key;
                    const peKey = atmItem.put_options.instrument_key;
                    atmOptionKeysRef.current = { ce: ceKey, pe: peKey };

                    const [ceHist, peHist, fBuildup, cBuildup, pBuildup] = await Promise.all([
                        API.getIntradayCandles(ceKey).catch(() => []),
                        API.getIntradayCandles(peKey).catch(() => []),
                        Trendlyne.fetchFuturesBuildup(currentSymbol, expiryLabel).catch(() => []),
                        Trendlyne.fetchOptionBuildup(currentSymbol, expiryLabel, atm, 'call').catch(() => []),
                        Trendlyne.fetchOptionBuildup(currentSymbol, expiryLabel, atm, 'put').catch(() => [])
                    ]);

                    setCeData(ceHist);
                    setPeData(peHist);
                    setFuturesBuildup(fBuildup);
                    setCeBuildup(cBuildup);
                    setPeBuildup(pBuildup);
                    socket.setSubscriptions([indexKey, ceKey, peKey]);
                    setTrendlyneReady(Trendlyne.isSessionInitialized);
                }
            }
        }
        setLastSync(new Date());
    } catch (e) {
        console.error("Dashboard Load Error:", e);
    } finally {
        setLoading(false);
    }
  }, [indexKey, expiryLabel]);

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
            {(['TERMINAL', 'ANALYTICS', 'FLOW'] as TabType[]).map(tab => (
                <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-1.5 rounded-md text-[10px] font-black uppercase tracking-widest transition-all ${
                        activeTab === tab ? 'bg-brand-blue text-white shadow-lg shadow-brand-blue/20' : 'text-gray-500 hover:text-gray-300'
                    }`}
                >
                    {tab}
                </button>
            ))}
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="flex gap-3">
            <select value={indexKey} onChange={e => setIndexKey(e.target.value)} className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-[11px] font-black text-brand-blue outline-none focus:ring-1 focus:ring-brand-blue transition-all">
              <option value={INDICES.NIFTY.key}>NIFTY 50</option>
              <option value={INDICES.BANKNIFTY.key}>BANK NIFTY</option>
            </select>
            <div className="bg-gray-900 border border-gray-800 rounded-lg px-3 py-1.5 text-[10px] flex items-center gap-2">
              <span className="text-gray-600 font-bold uppercase text-[8px]">Expiry</span>
              <span className="text-gray-100 font-black font-mono-data tracking-tight">{expiryLabel.replace('-near', '').toUpperCase()}</span>
            </div>
            <button
              onClick={() => loadData()}
              disabled={loading}
              className={`bg-gray-800 hover:bg-gray-700 p-2 rounded-lg border border-white/5 transition-colors group ${loading ? 'opacity-50' : ''}`}
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
            <div className="grid grid-cols-12 gap-4 h-full animate-fadeIn">
                <div className="col-span-12 xl:col-span-3">
                    {sentiment ? (
                        <SentimentAnalysis sentiment={sentiment} />
                    ) : (
                        <div className="glass-panel rounded-xl p-8 flex items-center justify-center text-[9px] text-gray-600 font-mono uppercase tracking-widest">Crunching Sentiment...</div>
                    )}
                    <div className="mt-4 glass-panel rounded-xl p-4">
                      <h3 className="text-[10px] font-black text-gray-500 uppercase mb-3">System Health</h3>
                      <div className="space-y-2 font-mono-data text-[9px]">
                        <div className="flex justify-between">
                          <span className="text-gray-600">Sync Status:</span>
                          <span className="text-brand-green">ACTIVE</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">Last Pulse:</span>
                          <span className="text-gray-400">{lastSync.toLocaleTimeString()}</span>
                        </div>
                        <div className="flex justify-between">
                          <span className="text-gray-600">Data Feed:</span>
                          <span className="text-brand-blue">UPSTOX V3</span>
                        </div>
                      </div>
                    </div>
                </div>
                <div className="col-span-12 xl:col-span-9 grid grid-rows-2 gap-4">
                    <div className="glass-panel rounded-xl p-4 flex flex-col">
                        <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-4">ATM Strike Dynamics</h3>
                        <div className="grid grid-cols-2 gap-4 flex-1">
                            <MarketChart title="CE ATM Volatility" data={ceData} />
                            <MarketChart title="PE ATM Volatility" data={peData} />
                        </div>
                    </div>
                    <div className="glass-panel rounded-xl p-4 flex flex-col">
                        <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-4">Index Performance</h3>
                        <MarketChart title="Spot Base" data={indexData} />
                    </div>
                </div>
            </div>
        )}

        {activeTab === 'FLOW' && (
            <div className="flex flex-col h-full animate-fadeIn overflow-hidden">
                <div className="flex items-center justify-between mb-4 bg-white/5 border border-white/10 p-3 rounded-xl">
                  <div className="flex items-center gap-4">
                    <div className="flex flex-col">
                      <span className="text-[8px] text-gray-500 font-black uppercase tracking-[0.2em]">Live Flow Monitor</span>
                      <span className="text-sm font-black text-white italic">INSTITUTIONAL TAPE FLOW <span className="text-brand-blue text-[10px] ml-2 font-mono">256-BIT SYNC</span></span>
                    </div>
                    <div className="h-8 w-[1px] bg-white/10"></div>
                    <div className="flex items-center gap-3">
                      <div className="flex flex-col">
                        <span className="text-[7px] text-gray-500 font-bold uppercase">Symbol</span>
                        <span className="text-[10px] text-gray-300 font-black font-mono">{symbolLabel}</span>
                      </div>
                      <div className="flex flex-col">
                        <span className="text-[7px] text-gray-500 font-bold uppercase">Base Strike</span>
                        <span className="text-[10px] text-brand-blue font-black font-mono">{atmStrike}</span>
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <div className="px-3 py-1 bg-green-500/10 border border-green-500/20 rounded-md flex items-center gap-2">
                      <div className={`w-1.5 h-1.5 rounded-full ${trendlyneReady ? 'bg-green-500 animate-pulse' : 'bg-yellow-500'}`}></div>
                      <span className={`text-[8px] font-black uppercase ${trendlyneReady ? 'text-green-500' : 'text-yellow-500'}`}>
                        Trendlyne: {trendlyneReady ? 'Authenticated' : 'Warming Up'}
                      </span>
                    </div>
                  </div>
                </div>

                <div className="grid grid-cols-12 gap-4 flex-1 min-h-0">
                    <div className="col-span-12 xl:col-span-4 h-full min-h-0">
                        <BuildupPanel title={`${symbolLabel} FUTURES TAPE`} data={futuresBuildup} />
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