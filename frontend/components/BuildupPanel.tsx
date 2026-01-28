import React from 'react';
import { BuildupData } from '../services/trendlyneService';

interface Props {
  title: string;
  data: BuildupData[];
  compact?: boolean;
}

const BuildupPanel: React.FC<Props> = ({ title, data, compact = false }) => {
  const getBuildupConfig = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'long buildup':
        return {
          color: 'text-green-400',
          bg: 'bg-green-500/10',
          border: 'border-green-500/20',
          label: 'L-BULL',
          indicator: '▲'
        };
      case 'short buildup':
        return {
          color: 'text-red-400',
          bg: 'bg-red-500/10',
          border: 'border-red-500/20',
          label: 'S-BEAR',
          indicator: '▼'
        };
      case 'long unwinding':
        return {
          color: 'text-orange-400',
          bg: 'bg-orange-500/10',
          border: 'border-orange-500/20',
          label: 'L-EXIT',
          indicator: '▽'
        };
      case 'short covering':
        return {
          color: 'text-blue-400',
          bg: 'bg-blue-500/10',
          border: 'border-blue-500/20',
          label: 'S-EXIT',
          indicator: '△'
        };
      default:
        return {
          color: 'text-gray-500',
          bg: 'bg-gray-800/10',
          border: 'border-gray-800',
          label: 'NEUTRAL',
          indicator: '•'
        };
    }
  };

  return (
    <div className="glass-panel rounded-xl flex flex-col h-full overflow-hidden border-t-2 border-t-brand-blue/20">
      <div className="px-4 py-3 border-b border-white/5 bg-white/5 flex justify-between items-center">
        <div className="flex items-center gap-2">
          <div className="w-1.5 h-1.5 rounded-full bg-brand-blue animate-pulse"></div>
          <h3 className="text-[10px] font-black text-white uppercase tracking-[0.2em]">{title}</h3>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-[8px] font-mono text-gray-500 bg-black/40 px-1.5 py-0.5 rounded border border-white/5">15M INTERVAL</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar p-2 space-y-1">
        {data.length === 0 ? (
          <div className="h-full flex flex-col items-center justify-center space-y-3 opacity-20">
            <div className="w-8 h-8 border-2 border-dashed border-gray-600 rounded-full animate-spin"></div>
            <span className="text-[9px] font-mono uppercase tracking-[0.3em]">Syncing Stream</span>
          </div>
        ) : (
          data.map((item, idx) => {
            const config = getBuildupConfig(item.buildup_type);
            const isLatest = idx === 0;

            return (
              <div
                key={idx}
                className={`group relative overflow-hidden flex items-center gap-3 px-3 py-2 rounded-lg border transition-all hover:bg-white/5 ${isLatest ? 'bg-white/5 border-white/10 ring-1 ring-white/5 shadow-xl' : 'bg-transparent border-transparent'}`}
              >
                {/* Time & Indicator */}
                <div className="flex flex-col items-center justify-center min-w-[40px] border-r border-white/5 pr-2">
                  <span className={`text-[10px] font-bold ${config.color}`}>{config.indicator}</span>
                  <span className="text-[8px] text-gray-500 font-mono-data">{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </div>

                {/* Main Info */}
                <div className="flex-1 grid grid-cols-2 gap-2">
                  <div className="flex flex-col">
                    <span className={`text-[9px] font-black tracking-widest uppercase mb-0.5 px-1.5 py-0.5 rounded-sm w-fit ${config.bg} ${config.color}`}>
                      {config.label}
                    </span>
                    <span className="text-[11px] font-black text-white font-mono-data tracking-tight">
                      {item.price.toLocaleString(undefined, { minimumFractionDigits: 1 })}
                    </span>
                  </div>

                  <div className="flex flex-col items-end justify-center">
                    <div className="flex items-center gap-1.5">
                       <span className="text-[8px] text-gray-600 uppercase font-bold">OI Δ</span>
                       <span className={`text-[10px] font-black font-mono-data ${item.oi_change >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                         {item.oi_change > 0 ? '+' : ''}{(item.oi_change / 1000).toFixed(1)}K
                       </span>
                    </div>
                    <div className="w-16 h-1 bg-gray-800 rounded-full mt-1 overflow-hidden relative">
                      <div
                        className={`absolute right-0 h-full rounded-full transition-all duration-500 ${item.oi_change >= 0 ? 'bg-brand-green' : 'bg-brand-red'}`}
                        style={{ width: `${Math.min(Math.abs(item.oi_change / 50000) * 100, 100)}%` }}
                      ></div>
                    </div>
                  </div>
                </div>

                {/* Price Change Tooltip-like Area */}
                <div className="flex flex-col items-end min-w-[50px]">
                  <span className={`text-[10px] font-black font-mono-data ${item.price_change >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                    {item.price_change > 0 ? '+' : ''}{item.price_change.toFixed(1)}
                  </span>
                  <span className="text-[7px] text-gray-600 uppercase font-bold">P-DELTA</span>
                </div>

                {isLatest && (
                  <div className="absolute top-0 right-0 h-full w-1 bg-brand-blue shadow-[0_0_10px_#3b82f6]"></div>
                )}
              </div>
            );
          })
        )}
      </div>

      {/* Summary Footer */}
      <div className="px-4 py-2 border-t border-white/5 bg-black/20 flex justify-between items-center text-[8px] text-gray-500 font-mono uppercase tracking-widest">
         <span>Samples: {data.length}</span>
         <span className="text-gray-700">|</span>
         <span className="flex items-center gap-1">
           <div className="w-1 h-1 rounded-full bg-brand-green"></div>
           Pulse OK
         </span>
      </div>
    </div>
  );
};

export default BuildupPanel;