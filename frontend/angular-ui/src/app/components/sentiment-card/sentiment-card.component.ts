import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DataService } from '../../services/data.service';
import { Subscription } from 'rxjs';

@Component({
  selector: 'app-sentiment-card',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="sentiment-card" [ngClass]="trendClass">
      <div class="card-header">
        <h3>Market Sentiment</h3>
        <span class="pulse-icon" *ngIf="isLive"></span>
      </div>

      <div class="metrics-grid">
        <div class="metric">
          <label>PCR (OI)</label>
          <div class="value">{{ pcrValue | number:'1.2-2' }}</div>
        </div>
        <div class="metric">
          <label>Signal</label>
          <div class="value signal">{{ sentiment }}</div>
        </div>
      </div>

      <div class="trend-indicator">
        <div class="bar-container">
          <div class="bar-fill" [style.width.%]="pcrPercentage"></div>
        </div>
        <div class="bar-labels">
          <span>Bearish</span>
          <span>Bullish</span>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .sentiment-card {
      background: white; border-radius: 12px; padding: 20px;
      box-shadow: 0 4px 12px rgba(0,0,0,0.08); width: 300px;
      transition: all 0.3s ease; border-left: 6px solid #ccc;
    }
    .card-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    h3 { margin: 0; color: #555; font-size: 1.1em; }
    .metrics-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 15px; margin-bottom: 20px; }
    .metric label { display: block; font-size: 0.85em; color: #888; margin-bottom: 5px; }
    .metric .value { font-size: 1.5em; font-weight: bold; color: #333; }

    .bullish { border-left-color: #2e7d32; }
    .bearish { border-left-color: #c62828; }
    .bullish .signal { color: #2e7d32; }
    .bearish .signal { color: #c62828; }

    .trend-indicator { margin-top: 10px; }
    .bar-container { height: 8px; background: #eee; border-radius: 4px; overflow: hidden; margin-bottom: 5px; }
    .bar-fill { height: 100%; background: linear-gradient(90deg, #c62828 0%, #2e7d32 100%); transition: width 0.5s ease; }
    .bar-labels { display: flex; justify-content: space-between; font-size: 0.75em; color: #999; }

    .pulse-icon {
      width: 8px; height: 8px; background: #4caf50; border-radius: 50%;
      box-shadow: 0 0 0 rgba(76, 175, 80, 0.4); animation: pulse 2s infinite;
    }
    @keyframes pulse {
      0% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0.4); }
      70% { box-shadow: 0 0 0 10px rgba(76, 175, 80, 0); }
      100% { box-shadow: 0 0 0 0 rgba(76, 175, 80, 0); }
    }
  `]
})
export class SentimentCardComponent implements OnInit, OnDestroy {
  pcrValue: number = 0.85;
  sentiment: string = 'Neutral';
  trendClass: string = '';
  pcrPercentage: number = 50;
  isLive: boolean = true;
  private sub: Subscription = new Subscription();

  constructor(private dataService: DataService) {}

  ngOnInit(): void {
    this.sub.add(
      this.dataService.pcrData$.subscribe(data => {
        if (data) {
          this.pcrValue = data.pcr;
          this.updateUI();
        }
      })
    );
    this.updateUI();
  }

  ngOnDestroy(): void {
    this.sub.unsubscribe();
  }

  private updateUI() {
    if (this.pcrValue > 1.2) {
      this.sentiment = 'Strong Bullish';
      this.trendClass = 'bullish';
    } else if (this.pcrValue > 1.0) {
      this.sentiment = 'Bullish';
      this.trendClass = 'bullish';
    } else if (this.pcrValue < 0.7) {
      this.sentiment = 'Strong Bearish';
      this.trendClass = 'bearish';
    } else if (this.pcrValue < 0.9) {
      this.sentiment = 'Bearish';
      this.trendClass = 'bearish';
    } else {
      this.sentiment = 'Neutral';
      this.trendClass = '';
    }

    // Map PCR 0.5 - 1.5 range to 0 - 100%
    this.pcrPercentage = Math.min(Math.max((this.pcrValue - 0.5) * 100, 0), 100);
  }
}
