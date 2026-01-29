import { Component, signal } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { OptionChainComponent } from './components/option-chain/option-chain.component';
import { SentimentCardComponent } from './components/sentiment-card/sentiment-card.component';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [RouterOutlet, CommonModule, OptionChainComponent, SentimentCardComponent],
  templateUrl: './app.html',
  styleUrl: './app.css'
})
export class App {
  protected readonly title = signal('ProTrade Desk');
}
