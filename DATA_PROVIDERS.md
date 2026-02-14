# ProTrade Data Provider Architecture

The application uses an interface-based architecture for data ingestion. This allows for redundancy and easy integration of new data providers without modifying core business logic.

## Core Interfaces

All providers must implement one of the following interfaces defined in `backend/core/interfaces.py`:

### 1. `ILiveStreamProvider`
Handles real-time tick and OHLCV streaming.
- `subscribe(symbols, interval)`: Subscribes to specific instruments.
- `unsubscribe(symbol, interval)`: Unsubscribes from instruments.
- `set_callback(callback)`: Sets the function to handle incoming `live_feed` or `chart_update` messages.

### 2. `IOptionsDataProvider`
Fetches option chain and Open Interest (OI) data.
- `get_option_chain(underlying)`: Returns full option chain data.
- `get_oi_data(underlying, expiry, time_str)`: Returns OI snapshots.
- `get_expiry_dates(underlying)`: Returns a list of available expiry dates.

### 3. `IHistoricalDataProvider`
Fetches historical OHLCV data.
- `get_hist_candles(symbol, interval, count)`: Returns a list of `[ts, o, h, l, c, v]` candles.

## Provider Registry

The `ProviderRegistry` (`backend/core/provider_registry.py`) manages these implementations. It supports:
- **Registration**: Add new providers at runtime or during startup.
- **Priority**: Providers are ordered by priority. The system always tries the highest priority provider first.
- **Failover**: If a provider fails (e.g., in `OptionsManager._fetch_oi_data`), the system automatically attempts to fetch data from the next available provider in the registry.

## Adding a New Provider

1. **Create Implementation**: Create a new class in `backend/external/` that inherits from the relevant interface.
   ```python
   class MyNewLiveStream(ILiveStreamProvider):
       # Implement all abstract methods
   ```
2. **Register Provider**: Update `initialize_default_providers` in `backend/core/provider_registry.py` to register your new provider.
   ```python
   live_stream_registry.register("my_provider", MyNewLiveStream(), priority=15)
   ```

## Existing Implementations

| Interface | Provider Name | Source |
|-----------|---------------|--------|
| `ILiveStreamProvider` | `tradingview` | Standard TradingView WebSocket |
| `ILiveStreamProvider` | `enhanced_tv` | Integrated Enterprise-grade Module |
| `IOptionsDataProvider` | `trendlyne` | Trendlyne API |
| `IOptionsDataProvider` | `nse` | Direct NSE India API |
| `IHistoricalDataProvider` | `tradingview` | Standard TradingView API |
| `IHistoricalDataProvider` | `enhanced_tv` | Integrated Module with Caching |
