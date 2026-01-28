export interface OhlcData {
  timestamp: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

export interface OptionChainItem {
  strike_price: number;
  call_options: OptionContract;
  put_options: OptionContract;
}

export interface OptionContract {
  instrument_key: string;
  market_data: {
    ltp: number;
    volume: number;
    oi: number;
    bid_price: number;
    ask_price: number;
  };
  option_greeks: {
    delta: number;
    theta: number;
    gamma: number;
    vega: number;
  };
}

export interface MarketSentiment {
  pcr: number;
  trend: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  maxCallOI: number;
  maxPutOI: number;
  maxCallStrike: number;
  maxPutStrike: number;
}