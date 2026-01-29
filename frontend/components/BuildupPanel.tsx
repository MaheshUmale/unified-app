import React from 'react';
import { BuildupData } from '../services/trendlyneService';

interface Props {
  title: string;
  data: BuildupData[];
  compact?: boolean;
}

const BuildupPanel: React.FC<Props> = ({ title, data }) => {
  const getBuildupConfig = (type: string) => {
    switch (type?.toLowerCase()) {
      case 'long buildup':
        return { color: 'text-green-400', label: 'LONG BUILDUP', indicator: '▲', colorClass: 'bg-green-500' };
      case 'short buildup':
        return { color: 'text-red-400', label: 'SHORT BUILDUP', indicator: '▼', colorClass: 'bg-red-500' };
      case 'long unwinding':
        return { color: 'text-orange-400', label: 'LONG UNWIND', indicator: '▽', colorClass: 'bg-orange-500' };
      case 'short covering':
        return { color: 'text-blue-400', label: 'SHORT COVER', indicator: '△', colorClass: 'bg-blue-500' };
      default:
        return { color: 'text-gray-500', label: 'NEUTRAL', indicator: '•', colorClass: 'bg-gray-500' };
    }
  };

  return (
    <div className="glass-panel rounded-xl flex flex-col h-full overflow-hidden border border-white/5 shadow-2xl">
      <div className="px-4 py-3 bg-gradient-to-r from-gray-900 to-black border-b border-white/10 flex justify-between items-center">
        <h3 className="text-[11px] font-black text-white uppercase tracking-[0.2em] flex items-center gap-2">
          <div className="w-2 h-2 rounded-sm bg-brand-blue shadow-[0_0_8px_#3b82f6]"></div>
          {title}
        </h3>
        <span className="text-[9px] font-bold text-gray-500 bg-white/5 px-2 py-0.5 rounded border border-white/5">LIVE TAPE</span>
      </div>

      <div className="flex-1 overflow-y-auto custom-scrollbar">
        <table className="w-full text-left border-collapse">
          <thead className="sticky top-0 bg-gray-950/90 backdrop-blur-md z-10">
            <tr className="border-b border-white/5">
              <th className="px-4 py-2 text-[8px] font-black text-gray-600 uppercase tracking-widest">Time</th>
              <th className="px-4 py-2 text-[8px] font-black text-gray-600 uppercase tracking-widest">Action</th>
              <th className="px-4 py-2 text-[8px] font-black text-gray-600 uppercase tracking-widest text-right">Price</th>
              <th className="px-4 py-2 text-[8px] font-black text-gray-600 uppercase tracking-widest text-right">OI Δ</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {data.length === 0 ? (
              <tr>
                <td colSpan={4} className="py-20 text-center">
                   <div className="flex flex-col items-center gap-3 opacity-20">
                     <div className="w-6 h-6 border-2 border-t-brand-blue border-transparent rounded-full animate-spin"></div>
                     <span className="text-[9px] font-mono uppercase tracking-[0.3em]">Decoding Tape...</span>
                   </div>
                </td>
              </tr>
            ) : (
              data.map((item, idx) => {
                const config = getBuildupConfig(item.buildup_type);
                return (
                  <tr key={idx} className={`hover:bg-white/5 transition-colors ${idx === 0 ? 'bg-brand-blue/5' : ''}`}>
                    <td className="px-4 py-2.5 text-[10px] font-mono-data text-gray-500">
                      {new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </td>
                    <td className="px-4 py-2.5">
                       <div className="flex items-center gap-2">
                         <span className={`text-[10px] font-bold ${config.color}`}>{config.indicator}</span>
                         <span className={`text-[9px] font-black tracking-tight ${config.color}`}>{config.label}</span>
                       </div>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                       <div className="flex flex-col items-end">
                         <span className="text-[11px] font-black text-white font-mono-data">{item.price.toFixed(1)}</span>
                         <span className={`text-[8px] font-bold ${item.price_change >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                           {item.price_change > 0 ? '+' : ''}{item.price_change.toFixed(1)}
                         </span>
                       </div>
                    </td>
                    <td className="px-4 py-2.5 text-right">
                       <div className="flex flex-col items-end">
                         <span className={`text-[10px] font-black font-mono-data ${item.oi_change >= 0 ? 'text-brand-green' : 'text-brand-red'}`}>
                           {item.oi_change > 0 ? '+' : ''}{(item.oi_change / 1000).toFixed(1)}K
                         </span>
                         <div className="w-12 h-0.5 bg-gray-800 mt-1 rounded-full overflow-hidden">
                            <div className={`h-full ${config.colorClass}`} style={{ width: `${Math.min(Math.abs(item.oi_change/50000)*100, 100)}%` }}></div>
                         </div>
                       </div>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="px-4 py-2 border-t border-white/5 bg-black/40 flex justify-between items-center text-[8px] text-gray-600 font-mono">
         <span>TOTAL SAMPLES: {data.length}</span>
         <span className="flex items-center gap-1.5 uppercase font-bold">
           <span className="w-1 h-1 rounded-full bg-brand-green shadow-[0_0_5px_#22c55e]"></span>
           Tape Synced
         </span>
      </div>
    </div>
  );
};

export default BuildupPanel;