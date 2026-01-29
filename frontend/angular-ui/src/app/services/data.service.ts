import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { BehaviorSubject, Observable } from 'rxjs';
import { io, Socket } from 'socket.io-client';

@Injectable({
  providedIn: 'root'
})
export class DataService {
  private socket: Socket;
  private pcrDataSubject = new BehaviorSubject<any>(null);
  public pcrData$ = this.pcrDataSubject.asObservable();

  constructor(private http: HttpClient) {
    this.socket = io();
    this.setupSocketListeners();
  }

  private setupSocketListeners() {
    this.socket.on('footprint_update', (data) => {
      console.log('Received footprint update:', data);
      // For demonstration, map footprint updates to PCR if they contain such info
      // In reality, we'd have a specific 'pcr_update' event
      if (data && data.pcr) {
        this.pcrDataSubject.next(data);
      }
    });

    this.socket.on('pcr_update', (data) => {
      console.log('Received PCR update:', data);
      this.pcrDataSubject.next(data);
    });

    this.socket.on('connect', () => {
      console.log('Connected to WebSocket');
    });
  }

  getInstruments(): Observable<any> {
    return this.http.get('/api/instruments');
  }

  getLivePnl(): Observable<any> {
    return this.http.get('/api/live_pnl');
  }

  subscribeToInstrument(instrumentKey: string) {
    this.socket.emit('subscribe_to_instrument', { instrument_key: instrumentKey });
  }
}
