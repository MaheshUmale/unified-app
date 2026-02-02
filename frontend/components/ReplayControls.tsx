import React, { useState, useEffect } from 'react';
import { socket } from '../services/socketService';
import { getReplayDates, getReplaySessionInfo } from '../services/upstoxService';
import { Play, Pause, Square, FastForward, Calendar, Loader2 } from 'lucide-react';

interface ReplayStatus {
    active: boolean;
    date?: string;
    paused?: boolean;
    speed?: number;
}

interface Props {
    currentIndexKey: string;
    onReplaySessionInfo?: (info: any) => void;
}

export const ReplayControls: React.FC<Props> = ({ currentIndexKey, onReplaySessionInfo }) => {
    const [status, setStatus] = useState<ReplayStatus>({ active: false });
    const [availableDates, setAvailableDates] = useState<string[]>([]);
    const [selectedDate, setSelectedDate] = useState<string>('');
    const [speed, setSpeed] = useState<number>(1);
    const [loadingInfo, setLoadingInfo] = useState(false);
    const [sessionKeys, setSessionKeys] = useState<string[]>([]);

    useEffect(() => {
        // Fetch available dates for replay
        getReplayDates().then(data => {
            setAvailableDates(data);
            if (data.length > 0) {
                const firstDate = data[0];
                setSelectedDate(firstDate);
                // Trigger session info discovery for the default date
                handleDateChange(firstDate);
            }
        });

        // Listen for replay status updates
        const unsubscribe = socket.onMessage((msg) => {
            if (msg.type === 'replay_status') {
                setStatus(msg);
                if (msg.speed) setSpeed(msg.speed);
            } else if (msg.type === 'replay_finished') {
                setStatus({ active: false });
                // alert(`Replay for ${msg.date} finished.`);
            } else if (msg.type === 'replay_error') {
                setStatus({ active: false });
                alert(`Replay Error: ${msg.message}`);
            }
        });

        return () => unsubscribe();
    }, []);

    const handleDateChange = async (date: string) => {
        setSelectedDate(date);
        if (date && onReplaySessionInfo) {
            setLoadingInfo(true);
            try {
                const info = await getReplaySessionInfo(date, currentIndexKey);
                if (info && !info.error) {
                    setSessionKeys(info.available_keys || []);
                    onReplaySessionInfo(info);
                } else {
                    console.warn("Replay Session Info Error:", info?.error);
                }
            } finally {
                setLoadingInfo(false);
            }
        }
    };

    const handleStart = () => {
        if (!selectedDate) return;
        // Replay all discovered keys for high fidelity
        const keysToReplay = sessionKeys.length > 0 ? sessionKeys : [currentIndexKey];
        socket.startReplay(selectedDate, keysToReplay, speed);
    };

    const handleTogglePause = () => {
        if (status.paused) {
            socket.resumeReplay();
        } else {
            socket.pauseReplay();
        }
    };

    const handleStop = () => {
        socket.stopReplay();
    };

    const handleSpeedChange = (newSpeed: number) => {
        setSpeed(newSpeed);
        if (status.active) {
            socket.setReplaySpeed(newSpeed);
        }
    };

    return (
        <div className="flex items-center gap-3 px-3 py-1.5 glass-panel rounded-xl border border-white/5 shadow-2xl">
            <div className="flex items-center gap-2">
                <Calendar className={`w-3.5 h-3.5 ${status.active ? 'text-brand-blue' : 'text-gray-500'}`} />
                <select
                    value={selectedDate}
                    onChange={(e) => handleDateChange(e.target.value)}
                    disabled={status.active || loadingInfo}
                    className="bg-black/40 border-none rounded text-[10px] font-black uppercase tracking-wider text-gray-300 focus:ring-0 cursor-pointer disabled:opacity-50"
                >
                    <option value="">Live Mode</option>
                    {availableDates.map(date => (
                        <option key={date} value={date}>{date}</option>
                    ))}
                </select>
            </div>

            <div className="h-4 w-[1px] bg-gray-800"></div>

            <div className="flex items-center gap-1.5">
                {!status.active ? (
                    <button
                        onClick={handleStart}
                        disabled={!selectedDate}
                        className="p-1.5 hover:bg-green-500/20 text-green-500 rounded-lg transition-all disabled:opacity-20"
                        title="Start Replay"
                    >
                        <Play className="w-4 h-4 fill-current" />
                    </button>
                ) : (
                    <>
                        <button
                            onClick={handleTogglePause}
                            className="p-1.5 hover:bg-blue-500/20 text-blue-400 rounded-lg transition-all"
                            title={status.paused ? "Resume" : "Pause"}
                        >
                            {status.paused ? <Play className="w-4 h-4 fill-current" /> : <Pause className="w-4 h-4 fill-current" />}
                        </button>
                        <button
                            onClick={handleStop}
                            className="p-1.5 hover:bg-red-500/20 text-red-500 rounded-lg transition-all"
                            title="Stop Replay"
                        >
                            <Square className="w-4 h-4 fill-current" />
                        </button>
                    </>
                )}
            </div>

            {status.active && (
                <>
                    <div className="h-4 w-[1px] bg-gray-800"></div>
                    <div className="flex items-center gap-2">
                        <span className="text-[9px] font-bold text-gray-500 font-mono">{speed}x</span>
                        <input
                            type="range"
                            min="0.5"
                            max="50"
                            step="0.5"
                            value={speed}
                            onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
                            className="w-16 h-1 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-brand-blue"
                        />
                    </div>
                    <div className="ml-2 px-2 py-0.5 bg-brand-blue/10 border border-brand-blue/20 rounded text-[9px] font-black text-brand-blue animate-pulse tracking-widest uppercase">
                        Replay Active
                    </div>
                </>
            )}
        </div>
    );
};
