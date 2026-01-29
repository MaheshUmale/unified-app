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
            if (data.length > 0) setSelectedDate(data[0]);
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
        <div className="flex flex-wrap items-center gap-4 p-3 bg-slate-800 rounded-lg border border-slate-700 shadow-lg text-white">
            <div className="flex items-center gap-2">
                {loadingInfo ? (
                    <Loader2 className="w-4 h-4 text-blue-400 animate-spin" />
                ) : (
                    <Calendar className="w-4 h-4 text-blue-400" />
                )}
                <select
                    value={selectedDate}
                    onChange={(e) => handleDateChange(e.target.value)}
                    disabled={status.active || loadingInfo}
                    className="bg-slate-900 border border-slate-600 rounded px-2 py-1 text-sm focus:outline-none focus:border-blue-500 disabled:opacity-50"
                >
                    <option value="">Select Date</option>
                    {availableDates.map(date => (
                        <option key={date} value={date}>{date}</option>
                    ))}
                </select>
            </div>

            <div className="flex items-center gap-2 border-l border-slate-700 pl-4">
                {!status.active ? (
                    <button
                        onClick={handleStart}
                        disabled={!selectedDate}
                        className="p-2 bg-green-600 hover:bg-green-700 rounded-full transition-colors disabled:opacity-50"
                        title="Start Replay"
                    >
                        <Play className="w-5 h-5 fill-current" />
                    </button>
                ) : (
                    <>
                        <button
                            onClick={handleTogglePause}
                            className="p-2 bg-blue-600 hover:bg-blue-700 rounded-full transition-colors"
                            title={status.paused ? "Resume" : "Pause"}
                        >
                            {status.paused ? <Play className="w-5 h-5 fill-current" /> : <Pause className="w-5 h-5 fill-current" />}
                        </button>
                        <button
                            onClick={handleStop}
                            className="p-2 bg-red-600 hover:bg-red-700 rounded-full transition-colors"
                            title="Stop Replay"
                        >
                            <Square className="w-5 h-5 fill-current" />
                        </button>
                    </>
                )}
            </div>

            <div className="flex items-center gap-3 border-l border-slate-700 pl-4">
                <div className="flex items-center gap-2">
                    <FastForward className="w-4 h-4 text-amber-400" />
                    <span className="text-xs font-mono w-8">{speed}x</span>
                </div>
                <input
                    type="range"
                    min="0.5"
                    max="50"
                    step="0.5"
                    value={speed}
                    onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
                    className="w-24 h-1 bg-slate-600 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
            </div>

            {status.active && (
                <div className="ml-auto px-3 py-1 bg-blue-900/40 border border-blue-800 rounded text-xs animate-pulse">
                    REPLAYING: {status.date}
                </div>
            )}
        </div>
    );
};
