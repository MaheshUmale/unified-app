import { io, Socket } from 'socket.io-client';

class SocketService {
    private socket: Socket | null = null;
    private listeners: ((data: any) => void)[] = [];
    private footprintListeners: ((data: any) => void)[] = [];
    private subscriptions: Set<string> = new Set();
    private isConnecting: boolean = false;

    constructor() {}

    async connect() {
        if (this.socket?.connected || this.isConnecting) return;
        this.isConnecting = true;

        console.log("Connecting to Socket.IO data feed");

        // Use relative URL for single-server deployment
        this.socket = io('/', {
            transports: ['polling', 'websocket'],
            reconnection: true,
            reconnectionAttempts: Infinity,
            reconnectionDelay: 1000,
        });

        this.socket.on('connect', () => {
            console.log("Socket.IO Connected (ID:", this.socket?.id, ")");
            this.isConnecting = false;
            if (this.subscriptions.size > 0) {
                this.subscribe(Array.from(this.subscriptions));
            }
        });

        this.socket.on('raw_tick', (dataString: string) => {
            try {
                const rawData = JSON.parse(dataString);
                const flattenedQuotes: Record<string, { last_price: number, timestamp: number }> = {};

                Object.keys(rawData).forEach(key => {
                    const instrument = rawData[key];
                    const fullFeed = instrument?.fullFeed;

                    // Handle both Index (indexFF) and Regular Market (marketFF) structures
                    const ltpc = fullFeed?.indexFF?.ltpc || fullFeed?.marketFF?.ltpc;

                    if (ltpc && typeof ltpc.ltp === 'number') {
                        flattenedQuotes[key] = {
                            last_price: ltpc.ltp,
                            timestamp: ltpc.ltt ? parseInt(ltpc.ltt) : Date.now()
                        };
                    }
                });

                if (Object.keys(flattenedQuotes).length > 0) {
                    this.listeners.forEach(fn => fn(flattenedQuotes));
                }
            } catch (error) {
                console.error("Error parsing raw_tick data:", error);
            }
        });

        this.socket.on('connect_error', (error) => {
            console.error("Socket.IO Connection Error:", error);
            this.isConnecting = false;
        });

        this.socket.on('disconnect', (reason) => {
            console.log("Socket.IO Disconnected:", reason);
            this.isConnecting = false;
        });

        this.socket.on('footprint_update', (data: any) => {
            this.footprintListeners.forEach(fn => fn({ type: 'update', data }));
        });

        this.socket.on('footprint_history', (data: any) => {
            this.footprintListeners.forEach(fn => fn({ type: 'history', data }));
        });
    }

    setSubscriptions(keys: string[]) {
        if (!this.socket) this.connect();

        this.subscriptions = new Set(keys);
        this.subscribe(keys);
    }

    private subscribe(keys: string[]) {
        if (this.socket?.connected) {
            this.socket.emit('subscribe', {
                instrumentKeys: keys
            });
            console.log("Requested subscription for keys:", keys);
        }
    }

    onMessage(fn: (data: any) => void) {
        if (!this.listeners.includes(fn)) {
            this.listeners.push(fn);
        }
        return () => {
            this.listeners = this.listeners.filter(l => l !== fn);
        };
    }

    onFootprint(fn: (data: any) => void) {
        if (!this.footprintListeners.includes(fn)) {
            this.footprintListeners.push(fn);
        }
        return () => {
            this.footprintListeners = this.footprintListeners.filter(l => l !== fn);
        };
    }
}

export const socket = new SocketService();