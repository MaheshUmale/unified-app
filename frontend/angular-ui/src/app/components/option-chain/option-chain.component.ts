import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DataService } from '../../services/data.service';
import { Subscription } from 'rxjs';

interface OptionStrike {
  strike: number;
  ce_oi: number;
  ce_ltp: number;
  ce_oi_change: number;
  pe_oi: number;
  pe_ltp: number;
  pe_oi_change: number;
}

@Component({
  selector: 'app-option-chain',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="option-chain-container">
      <div class="header">
        <h2>Option Chain - {{ currentInstrument }}</h2>
        <div class="controls">
          <select (change)="onInstrumentChange($event)">
            <option *ngFor="let inst of availableInstruments" [value]="inst.key">{{ inst.name }}</option>
          </select>
          <button (click)="onBackfill()" [disabled]="isBackfilling">
            {{ isBackfilling ? 'Backfilling...' : 'Backfill Trendlyne' }}
          </button>
        </div>
      </div>

      <div class="table-wrapper">
        <table>
          <thead>
            <tr>
              <th colspan="3" class="call-header">CALLS</th>
              <th></th>
              <th colspan="3" class="put-header">PUTS</th>
            </tr>
            <tr>
              <th>OI Chg</th>
              <th>OI</th>
              <th>LTP</th>
              <th class="strike-col">Strike</th>
              <th>LTP</th>
              <th>OI</th>
              <th>OI Chg</th>
            </tr>
          </thead>
          <tbody>
            <tr *ngFor="let row of optionChainData">
              <td [ngClass]="row.ce_oi_change > 0 ? 'up' : 'down'">{{ row.ce_oi_change | number }}</td>
              <td>{{ row.ce_oi | number }}</td>
              <td>{{ row.ce_ltp | number:'1.2-2' }}</td>
              <td class="strike-val">{{ row.strike }}</td>
              <td>{{ row.pe_ltp | number:'1.2-2' }}</td>
              <td>{{ row.pe_oi | number }}</td>
              <td [ngClass]="row.pe_oi_change > 0 ? 'up' : 'down'">{{ row.pe_oi_change | number }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `,
  styles: [`
    .option-chain-container { padding: 20px; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; }
    .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; }
    .table-wrapper { overflow-x: auto; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-radius: 8px; }
    table { width: 100%; border-collapse: collapse; background: white; }
    th { background: #f4f7f6; color: #333; padding: 12px 8px; font-weight: 600; border-bottom: 2px solid #ddd; }
    td { padding: 10px 8px; border-bottom: 1px solid #eee; text-align: center; }
    .call-header { background: #e8f5e9; }
    .put-header { background: #ffebee; }
    .strike-col { background: #f9f9f9; font-weight: bold; width: 100px; }
    .strike-val { font-weight: bold; color: #1a73e8; }
    .up { color: #2e7d32; font-weight: 500; }
    .down { color: #c62828; font-weight: 500; }
    select { padding: 8px; border-radius: 4px; border: 1px solid #ccc; margin-right: 10px; }
    button {
      padding: 8px 16px; border-radius: 4px; border: none;
      background: #1a73e8; color: white; cursor: pointer; font-weight: 500;
    }
    button:disabled { background: #ccc; cursor: not-allowed; }
  `]
})
export class OptionChainComponent implements OnInit, OnDestroy {
  currentInstrument: string = 'NIFTY';
  availableInstruments: any[] = [];
  optionChainData: OptionStrike[] = [];
  isBackfilling: boolean = false;
  private sub: Subscription = new Subscription();

  constructor(private dataService: DataService) {}

  ngOnInit(): void {
    this.sub.add(
      this.dataService.getInstruments().subscribe(insts => {
        this.availableInstruments = insts;
      })
    );

    // Mock data for initial visualization
    this.generateMockData();
  }

  ngOnDestroy(): void {
    this.sub.unsubscribe();
  }

  onInstrumentChange(event: any): void {
    this.currentInstrument = event.target.value;
    this.dataService.subscribeToInstrument(this.currentInstrument);
  }

  onBackfill(): void {
    this.isBackfilling = true;
    const symbol = this.currentInstrument.split('|')[1]?.split(' ')[0] || 'NIFTY';
    this.dataService.triggerTrendlyneBackfill(symbol).subscribe({
      next: (res) => {
        alert(`Backfill successful: ${res.slots_processed} slots processed.`);
        this.isBackfilling = false;
      },
      error: (err) => {
        alert(`Backfill failed: ${err.error?.detail || err.message}`);
        this.isBackfilling = false;
      }
    });
  }

  private generateMockData() {
    const baseStrike = 24000;
    for (let i = -5; i <= 5; i++) {
      const strike = baseStrike + (i * 50);
      this.optionChainData.push({
        strike,
        ce_oi: Math.floor(Math.random() * 100000),
        ce_ltp: Math.random() * 200,
        ce_oi_change: (Math.random() - 0.5) * 5000,
        pe_oi: Math.floor(Math.random() * 100000),
        pe_ltp: Math.random() * 200,
        pe_oi_change: (Math.random() - 0.5) * 5000,
      });
    }
  }
}
