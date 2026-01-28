import React from 'react';
import { MarketSentiment } from '../types';

interface Props {
  sentiment: MarketSentiment;
}

const SentimentAnalysis: React.FC<Props> = ({ sentiment }) => {
  const getTrendColor = (trend: string) => {
    if (trend === 'BULLISH') return 'text-green-400';
    if (trend === 'BEARISH') return 'text-red-400';
    return 'text-yellow-400';
  };

  const getPcrColor = (pcr: number) => {
    if (pcr > 1.2) return 'text-green-400';
    if (pcr < 0.7) return 'text-red-400';
    return 'text-blue-400';
  };

  return (
    <div className="glass-panel rounded-xl p-4 flex flex-col h-full shadow-2xl border-l-2 border-l-blue-500/30">
      <div className="flex justify-between items-center mb-4">
        <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-[0.2em]">Market DNA</h3>
        <span className="bg-blue-500/10 text-blue-500 text-[8px] px-2 py-0.5 rounded-full font-bold uppercase">Real-time</span>
      </div>

      <div className="space-y-4">
        {/* PCR Metric */}
        <div className="p-3 bg-gray-950/40 rounded-lg border border-gray-800/50 flex flex-col items-center">
           <span className="text-[9px] text-gray-500 font-bold uppercase mb-1">Put-Call Ratio</span>
           <div className={`text-3xl font-black font-mono-data ${getPcrColor(sentiment.pcr)}`}>
             {sentiment.pcr.toFixed(2)}
           </div>
           <div className={`text-[10px] font-bold mt-1 uppercase tracking-wider ${getTrendColor(sentiment.trend)}`}>
             {sentiment.trend} Bias
           </div>
        </div>

        {/* Zones */}
        <div className="space-y-3">
          <div className="group">
            <div className="flex justify-between text-[10px] mb-1">
              <span className="text-gray-400 font-bold uppercase">Strong Resistance</span>
              <span className="text-red-400 font-black font-mono-data">{sentiment.maxCallStrike}</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1.5 p-[1px]">
              <div
                className="bg-red-500 h-full rounded-full shadow-[0_0_8px_rgba(239,68,68,0.5)]"
                style={{ width: '85%' }}
              ></div>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[8px] text-gray-600 uppercase">Max Call OI</span>
              <span className="text-[9px] text-gray-400 font-mono-data">{(sentiment.maxCallOI/100000).toFixed(1)}L</span>
            </div>
          </div>

          <div className="group">
            <div className="flex justify-between text-[10px] mb-1">
              <span className="text-gray-400 font-bold uppercase">Major Support</span>
              <span className="text-green-400 font-black font-mono-data">{sentiment.maxPutStrike}</span>
            </div>
            <div className="w-full bg-gray-800 rounded-full h-1.5 p-[1px]">
              <div
                className="bg-green-500 h-full rounded-full shadow-[0_0_8px_rgba(34,197,94,0.5)]"
                style={{ width: '70%' }}
              ></div>
            </div>
            <div className="flex justify-between mt-1">
              <span className="text-[8px] text-gray-600 uppercase">Max Put OI</span>
              <span className="text-[9px] text-gray-400 font-mono-data">{(sentiment.maxPutOI/100000).toFixed(1)}L</span>
            </div>
          </div>
        </div>
      </div>

      <div className="mt-auto pt-4">
        <div className="text-[9px] text-gray-600 leading-relaxed italic border-t border-gray-800 pt-3">
          OI distribution suggests {sentiment.trend === 'BULLISH' ? 'unwinding of calls' : 'accumulation of puts'} is likely if spot breaches {sentiment.maxCallStrike}.
        </div>
      </div>
    </div>
  );
};

export default SentimentAnalysis;