
import React, { useState, useEffect } from 'react';
import * as StrategyService from '../services/strategyService';

interface StrategyDashboardProps {
    indexKey: string;
    atmStrike: number;
    expiryDate: string;
    symbol: string;
}

const StrategyDashboard: React.FC<StrategyDashboardProps> = ({ indexKey, atmStrike, expiryDate, symbol }) => {
    const [analysis, setAnalysis] = useState<any>(null);
    const [loading, setLoading] = useState(false);
    const [cues, setCues] = useState({ global_cues: '', major_events: '' });
    const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

    const fetchAnalysis = async () => {
        if (!atmStrike || !expiryDate) return;
        setLoading(true);
        const data = await StrategyService.getAtmStrategyAnalysis(indexKey, atmStrike, expiryDate);
        if (data) {
            setAnalysis(data);
            setLastUpdated(new Date());
            if (data.context) {
                setCues({
                    global_cues: data.context.global_cues || '',
                    major_events: data.context.major_events || ''
                });
            }
        }
        setLoading(false);
    };

    const handleContextUpdate = async () => {
        await StrategyService.updateStrategyContext(symbol, cues.global_cues, cues.major_events);
        fetchAnalysis();
    };

    const handleFetchCues = async () => {
        const data = await StrategyService.searchMarketCues();
        if (data) {
            setCues(data);
        }
    };

    useEffect(() => {
        fetchAnalysis();
        const interval = setInterval(fetchAnalysis, 60000); // Auto refresh every 1 min
        return () => clearInterval(interval);
    }, [indexKey, atmStrike, expiryDate]);

    if (!analysis) return (
        <div className="flex-1 flex items-center justify-center text-gray-500 font-mono text-xs uppercase tracking-widest">
            Awaiting Strategy Analysis Engine...
        </div>
    );

    const filters = analysis.filters || {};
    const scores = analysis.edge_scores || {};
    const metrics = analysis.metrics || {};
    const expectancy = metrics.expectancy || [];
    const regimes = metrics.regimes || {};

    return (
        <div className="flex flex-col gap-6 h-full overflow-y-auto pr-2 animate-fadeIn pb-8">
            {/* Header / Decision */}
            <div className={`p-6 rounded-2xl border-2 flex items-center justify-between ${
                analysis.decision === 'NO TRADE' ? 'bg-gray-900/50 border-gray-800' :
                analysis.decision.includes('CALL') ? 'bg-green-500/10 border-green-500/30' :
                analysis.decision.includes('PUT') ? 'bg-red-500/10 border-red-500/30' : 'bg-blue-500/10 border-blue-500/30'
            }`}>
                <div className="flex flex-col gap-1">
                    <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Recommended Action</span>
                    <h2 className={`text-3xl font-black italic tracking-tighter ${
                        analysis.decision === 'NO TRADE' ? 'text-gray-400' :
                        analysis.decision.includes('CALL') ? 'text-green-500' :
                        analysis.decision.includes('PUT') ? 'text-red-500' : 'text-blue-500'
                    }`}>
                        {analysis.decision}
                    </h2>
                </div>
                <div className="flex flex-col items-end">
                    <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">System Confidence</span>
                    <span className="text-white font-black font-mono-data text-2xl">
                        {Math.max(scores.call || 0, scores.put || 0, scores.straddle || 0)}%
                    </span>
                </div>
            </div>

            <div className="grid grid-cols-12 gap-6">
                {/* Edge & Probability Table */}
                <div className="col-span-12 lg:col-span-8 flex flex-col gap-6">
                    <div className="glass-panel rounded-2xl p-6">
                        <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-4">Probability × Expectancy (15m Window)</h3>
                        <div className="overflow-hidden rounded-xl border border-white/5 bg-black/20">
                            <table className="w-full text-[11px] text-left">
                                <thead className="bg-white/5 text-[9px] font-black uppercase text-gray-500 tracking-wider">
                                    <tr>
                                        <th className="px-4 py-3">Strategy</th>
                                        <th className="px-4 py-3 text-center">Win Prob (%)</th>
                                        <th className="px-4 py-3 text-center">Req. Move (pts)</th>
                                        <th className="px-4 py-3 text-center">Exp. Move (pts)</th>
                                        <th className="px-4 py-3 text-right">Net Expectancy</th>
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-white/5 font-mono-data">
                                    {expectancy.map((row: any, i: number) => (
                                        <tr key={i} className="hover:bg-white/5 transition-colors">
                                            <td className="px-4 py-4 font-black text-white italic tracking-tighter">ATM {row.type} BUY</td>
                                            <td className="px-4 py-4 text-center">
                                                <span className={`px-2 py-0.5 rounded ${row.win_prob > 60 ? 'bg-green-500/20 text-green-500' : 'bg-gray-800 text-gray-400'}`}>
                                                    {row.win_prob}%
                                                </span>
                                            </td>
                                            <td className="px-4 py-4 text-center text-gray-300">{row.req_move}</td>
                                            <td className="px-4 py-4 text-center text-blue-400">{row.exp_move}</td>
                                            <td className={`px-4 py-4 text-right font-black ${row.net > 0 ? 'text-green-500' : 'text-red-500'}`}>
                                                {row.net > 0 ? '+' : ''}{row.net}
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    </div>

                    <div className="grid grid-cols-2 gap-6">
                        <div className="glass-panel rounded-2xl p-6">
                            <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-6">Regime Probabilities (Next 30m)</h3>
                            <div className="space-y-4">
                                {Object.entries(regimes).map(([name, prob]: [string, any]) => (
                                    <div key={name} className="flex flex-col gap-1.5">
                                        <div className="flex justify-between text-[9px] font-black uppercase tracking-tight">
                                            <span className="text-gray-400">{name.replace('_', ' → ')}</span>
                                            <span className="text-white">{prob}%</span>
                                        </div>
                                        <div className="h-1 bg-white/5 rounded-full overflow-hidden">
                                            <div className="h-full bg-blue-500 transition-all duration-1000" style={{ width: `${prob}%` }} />
                                        </div>
                                    </div>
                                ))}
                            </div>
                        </div>

                        <div className="glass-panel rounded-2xl p-6">
                            <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest mb-6">Condition Filters</h3>
                            <div className="grid grid-cols-1 gap-2">
                                {Object.entries(filters).map(([key, passed]: [string, any]) => (
                                    <div key={key} className={`px-3 py-2 rounded-lg border flex items-center gap-3 ${
                                        passed ? 'bg-green-500/5 border-green-500/20' : 'bg-gray-900/40 border-white/5'
                                    }`}>
                                        <div className={`w-1.5 h-1.5 rounded-full ${passed ? 'bg-green-500 shadow-[0_0_8px_rgba(34,197,94,0.6)]' : 'bg-gray-700'}`}></div>
                                        <span className={`text-[9px] font-black uppercase ${passed ? 'text-gray-100' : 'text-gray-500'}`}>
                                            {key.replace('_', ' ')}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        </div>
                    </div>
                </div>

                {/* Side Panels */}
                <div className="col-span-12 lg:col-span-4 flex flex-col gap-6">
                    <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4">
                        <div className="flex justify-between items-center">
                            <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Context & Global Cues</h3>
                            <button
                                onClick={handleFetchCues}
                                className="text-[9px] font-black text-blue-500 hover:text-white transition-colors uppercase"
                            >
                                AUTO-FETCH
                            </button>
                        </div>
                        <div className="space-y-4">
                            <textarea
                                value={cues.global_cues}
                                onChange={e => setCues({...cues, global_cues: e.target.value})}
                                placeholder="Global Cues..."
                                className="w-full bg-black/40 border border-white/10 rounded-xl p-3 text-[11px] text-gray-300 h-24 outline-none focus:border-blue-500 transition-all font-mono"
                            />
                            <textarea
                                value={cues.major_events}
                                onChange={e => setCues({...cues, major_events: e.target.value})}
                                placeholder="Scheduled Events..."
                                className="w-full bg-black/40 border border-white/10 rounded-xl p-3 text-[11px] text-gray-300 h-24 outline-none focus:border-blue-500 transition-all font-mono"
                            />
                            <button
                                onClick={handleContextUpdate}
                                className="w-full bg-blue-600 hover:bg-blue-500 text-white font-black uppercase text-[10px] py-3 rounded-xl transition-all shadow-lg shadow-blue-500/20"
                            >
                                Re-sync Engine
                            </button>
                        </div>
                    </div>

                    <div className="glass-panel rounded-2xl p-6 flex flex-col gap-4">
                        <h3 className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Alpha One-Liner</h3>
                        <p className="text-xs text-gray-400 font-mono leading-relaxed italic border-l-2 border-blue-500 pl-4">
                            "Should ATM options be BOUGHT today?
                            <span className={`ml-1 font-black not-italic ${analysis.decision === 'NO TRADE' ? 'text-red-500' : 'text-green-500'}`}>
                                {analysis.decision === 'NO TRADE' ? 'NO' : 'YES'}
                            </span>
                            — ({Math.max(scores.call, scores.put)}% probability, Expectancy {metrics.expected_move?.toFixed(1)} pts)."
                        </p>
                    </div>
                </div>
            </div>
        </div>
    );
};

export default StrategyDashboard;
