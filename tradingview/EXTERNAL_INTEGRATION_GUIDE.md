# TradingView Module External Integration Guide

This document details how to integrate and use the TradingView data source module in different scenarios.

## 📋 Table of Contents

- [Quick Start](#quick-start)
- [Architecture Overview](#architecture-overview)
- [Integration Methods](#integration-methods)
- [API Interfaces](#api-interfaces)
- [Data Caching](#data-caching)
- [Quality Monitoring](#quality-monitoring)
- [Best Practices](#best-practices)
- [Troubleshooting](#troubleshooting)

## 🚀 Quick Start

### Environmental Requirements

```bash
# Python Version Requirement
Python >= 3.9

# Core Dependencies
pip install asyncio websockets fastapi uvicorn aiohttp
pip install sqlite3 pandas numpy

# Optional Dependencies (for advanced features)
pip install prometheus_client grafana-api redis
```

### 30-Second Quick Experience

```python
import asyncio
from tradingview.api_server import TradingViewAPIServer

async def quick_start():
    # Start API server
    server = TradingViewAPIServer({
        'cache_db_path': 'quick_demo.db',
        'max_memory_cache': 1000
    })

    await server.start_server(host="127.0.0.1", port=8000)

# Run server
asyncio.run(quick_start())
```

Visit http://127.0.0.1:8000/api/v1/health to check service status.

## 🏗️ Architecture Overview

The TradingView module adopts a **three-layer architecture** design:

```
┌─────────────────────────────────────────────────────────────────┐
│                      External Integration Layer                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ RESTful API │  │ WebSocket   │  │ Python SDK  │            │
│  │   (HTTP)    │  │ (Real-time) │  │ (Direct)    │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Data Processing Layer                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Cache Mgr   │  │ Quality Mon │  │ Recovery    │            │
│  │(Dual-layer) │  │(Multi-dim)  │  │(Fault Tol)  │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                     TradingView Core Layer                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ Enhanced Cl │  │ Session Mgr │  │ Protocol Pr │            │
│  │(Auto-recon) │  │(Multi-sess) │  │(Msg Parsing)│            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
└─────────────────────────────────────────────────────────────────┘
```

### Core Component Description

| Component | Responsibility | Features |
|------|------|------|
| **API Server** | Provides RESTful and WebSocket interfaces | Async processing, CORS support, auto-docs |
| **Cache Manager** | Dual-layer cache management | LRU Memory cache + SQLite persistence |
| **Quality Monitor** | Data quality monitoring | Six-dimensional assessment, smart alerts |
| **Enhanced Client** | TradingView connection management | Auto-reconnect, health monitoring, performance optimization |

## 🔌 Integration Methods

### Method 1: RESTful API Integration (Recommended)

Applicable to **cross-language**, **microservices**, **Web applications**, and other scenarios.

```python
import aiohttp
import asyncio

class TradingViewClient:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url

    async def get_data(self, symbol, timeframe, count=500):
        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}/api/v1/data/historical"
            payload = {
                'symbol': symbol,
                'timeframe': timeframe,
                'count': count,
                'quality_check': True,
                'use_cache': True
            }

            async with session.post(url, json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    raise Exception(f"API Request Failed: {response.status}")

# Example usage
async def example():
    client = TradingViewClient()

    # Get BTC 15-minute K-line data
    data = await client.get_data('BINANCE:BTCUSDT', '15', 1000)

    if data['status'] == 'success':
        klines = data['data']['klines']
        print(f"Obtained {len(klines)} K-line data points")
        print(f"Data quality score: {data['metadata']['quality_score']:.3f}")

asyncio.run(example())
```

#### API Endpoint Description

| Endpoint | Method | Description | Example |
|------|------|------|------|
| `/api/v1/health` | GET | Get health status | `curl http://localhost:8000/api/v1/health` |
| `/api/v1/data/historical` | POST | Get historical data | See example above |
| `/api/v1/symbols` | GET | Get supported symbols | `curl http://localhost:8000/api/v1/symbols` |
| `/api/v1/cache/stats` | GET | Get cache statistics | `curl http://localhost:8000/api/v1/cache/stats` |
| `/api/v1/cache/clear` | DELETE | Clear cache | `curl -X DELETE http://localhost:8000/api/v1/cache/clear` |

### Method 2: WebSocket Real-time Data Integration

Applicable to scenarios requiring **real-time push**.

```python
import asyncio
import websockets
import json

async def websocket_example():
    uri = "ws://localhost:8000/ws/realtime"

    async with websockets.connect(uri) as websocket:
        # Subscribe to real-time data
        subscribe_msg = {
            'type': 'subscribe',
            'symbols': ['BINANCE:BTCUSDT', 'BINANCE:ETHUSDT'],
            'timeframes': ['1', '5', '15']
        }

        await websocket.send(json.dumps(subscribe_msg))

        # Receive data
        async for message in websocket:
            data = json.loads(message)

            if data['type'] == 'realtime_data':
                symbol = data['symbol']
                price = data['data']['price']
                print(f"Real-time Price: {symbol} = ${price}")

            elif data['type'] == 'subscribed':
                print(f"Subscription Successful: {data['symbols']}")

asyncio.run(websocket_example())
```

### Method 3: Python SDK Direct Integration

Applicable for internal integration within **Python projects**.

```python
from tradingview.integration_examples import TradingViewDataSource

async def sdk_example():
    # Initialize data source
    data_source = TradingViewDataSource({
        'cache_db_path': 'my_trading_app.db',
        'max_cache_size': 2000
    })

    if await data_source.initialize():
        # Get historical data
        market_data = await data_source.get_historical_data(
            'BINANCE:BTCUSDT', '15', count=1000
        )

        if market_data:
            print(f"Obtained {len(market_data.klines)} K-lines")

            # Subscribe to real-time data
            async def on_realtime_data(data):
                print(f"Real-time Data: {data}")

            await data_source.subscribe_realtime_data(
                ['BINANCE:BTCUSDT'], on_realtime_data
            )

        # Get health status
        health = await data_source.get_health_status()
        print(f"Data Source Status: {health['status']}")

        await data_source.shutdown()

asyncio.run(sdk_example())
```

## 🗄️ Data Caching

### Dual-layer Cache Architecture

 the TradingView module implements a **Memory + SQLite** dual-layer cache architecture:

```
┌─────────────────────────────────────────────────────────────────┐
│                      Dual-layer Cache Architecture               │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  🚀 L1: Memory Cache (LRU)                                      │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ • Capacity: 1000-5000 records                               │ │
│  │ • Latency: < 1ms                                            │ │
│  │ • Hit Rate: 80-90%                                          │ │
│  │ • Strategy: LRU Eviction                                    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼ (Miss)                           │
│  💾 L2: SQLite Cache (Persistent)                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │ • Capacity: Unlimited                                       │ │
│  │ • Latency: 5-10ms                                           │ │
│  │ • Hit Rate: 15-20%                                          │ │
│  │ • Features: Cross-session Persistence                       │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

### Cache Usage Example

```python
from tradingview.data_cache_manager import DataCacheManager

async def cache_example():
    # Initialize cache manager
    cache_manager = DataCacheManager(
        db_path="my_cache.db",
        max_memory_size=2000
    )

    # Store data
    sample_data = {
        'symbol': 'BINANCE:BTCUSDT',
        'timeframe': '15',
        'klines': [
            {
                'timestamp': 1699123456,
                'open': 35000.0,
                'high': 35500.0,
                'low': 34800.0,
                'close': 35200.0,
                'volume': 123.45
            }
        ],
        'quality_score': 0.95
    }

    # Store to cache
    await cache_manager.store_historical_data(
        'BINANCE:BTCUSDT', '15', sample_data, expire_seconds=3600
    )

    # Get from cache
    cached_data = await cache_manager.get_historical_data(
        'BINANCE:BTCUSDT', '15', count=500
    )

    if cached_data:
        print("Cache Hit!")
        print(f"Quality Score: {cached_data['quality_score']}")

    # Get cache statistics
    stats = await cache_manager.get_statistics()
    print(f"Cache Hit Rate: {cache_manager.get_hit_rate():.2%}")
    print(f"Cache Entries: {stats.total_entries}")

asyncio.run(cache_example())
```

### Cache Optimization Configuration

```python
# Recommended cache configuration
cache_config = {
    # Memory cache size (number of entries)
    'max_memory_size': 2000,

    # SQLite database path
    'db_path': 'data/tradingview_cache.db',

    # Default expiration time (seconds)
    'default_expire_seconds': 3600,  # 1 hour

    # Cleanup interval (seconds)
    'cleanup_interval': 300,  # 5 minutes

    # Quality threshold (don't cache if below this)
    'min_quality_for_cache': 0.8
}
```

## 🛡️ Quality Monitoring

### Six-dimensional Quality Assessment System

The system implements data quality assessment across **Completeness, Accuracy, Consistency, Timeliness, Validity, and Uniqueness**:

```python
from tradingview.enhanced_data_quality_monitor import DataQualityMonitor

async def quality_monitor_example():
    # Initialize quality monitor
    monitor = DataQualityMonitor({
        'critical_quality_score': 0.6,
        'warning_quality_score': 0.8,
        'max_consecutive_failures': 3
    })

    # Register alert handler
    async def alert_handler(alert):
        print(f"Quality Alert: {alert.level.value} - {alert.message}")

        if alert.level.value == 'critical':
            # Critical alert handling logic
            print("Triggering emergency response mechanism")

    monitor.register_alert_handler(alert_handler)

    # Assess data quality
    sample_data = {
        'symbol': 'BINANCE:BTCUSDT',
        'timeframe': '15',
        'klines': [
            # ... K-line data
        ]
    }

    result = await monitor.evaluate_data_quality(
        'BINANCE:BTCUSDT', '15', sample_data
    )

    print(f"Quality Assessment Result:")
    print(f"  Overall Score: {result.quality_score:.3f}")
    print(f"  Quality Level: {result.metrics.quality_level.value}")
    print(f"  Completeness: {result.metrics.completeness_score:.3f}")
    print(f"  Accuracy: {result.metrics.accuracy_score:.3f}")
    print(f"  Consistency: {result.metrics.consistency_score:.3f}")

    # Get improvement suggestions
    if result.suggestions:
        print("Improvement Suggestions:")
        for suggestion in result.suggestions:
            print(f"  - {suggestion}")

asyncio.run(quality_monitor_example())
```

### Quality Monitoring Configuration

```python
quality_config = {
    # Quality thresholds
    'thresholds': {
        'min_completeness': 0.95,       # Min completeness requirement
        'min_accuracy': 0.90,           # Min accuracy requirement
        'max_price_deviation': 0.20,    # Max price deviation (20%)
        'max_volume_deviation': 5.0,    # Max volume deviation (5x)
        'max_timestamp_gap': 300,       # Max timestamp gap (5 minutes)
    },

    # Quality weights
    'weights': {
        'completeness': 0.25,
        'accuracy': 0.25,
        'consistency': 0.20,
        'timeliness': 0.15,
        'validity': 0.10,
        'uniqueness': 0.05
    },

    # Alert configuration
    'alerts': {
        'critical_quality_score': 0.6,
        'warning_quality_score': 0.8,
        'max_consecutive_failures': 3
    }
}
```

## 📊 Integration Scenario Examples

### Scenario 1: Integrating into trading_core

```python
# Use TradingView as a data source in trading_core
from tradingview.integration_examples import TradingViewDataSource

class TradingSystem:
    def __init__(self):
        self.data_source = TradingViewDataSource({
            'cache_db_path': 'trading_system.db',
            'max_cache_size': 5000
        })

    async def initialize(self):
        await self.data_source.initialize()

    async def get_market_data(self, symbol, timeframe, count):
        return await self.data_source.get_historical_data(
            symbol, timeframe, count
        )

    async def start_realtime_monitoring(self, symbols):
        async def on_price_update(data):
            # Process real-time price updates
            await self.process_price_update(data)

        await self.data_source.subscribe_realtime_data(
            symbols, on_price_update
        )

    async def process_price_update(self, data):
        # Implement your trading logic
        symbol = data.get('symbol')
        price = data.get('price')
        print(f"Processing price update: {symbol} = ${price}")
```

### Scenario 2: Integrating into Chanpy Analysis

```python
from tradingview.integration_examples import ChanpyDataFeeder

async def chanpy_integration():
    # Initialize data feeder
    feeder = ChanpyDataFeeder()
    await feeder.initialize()

    # Create Chan analysis for multiple symbols
    symbols = ['BINANCE:BTCUSDT', 'BINANCE:ETHUSDT', 'BINANCE:ADAUSDT']
    timeframes = ['15', '60', '240']

    instances = {}

    for symbol in symbols:
        for tf in timeframes:
            instance_id = await feeder.create_chan_analysis(
                symbol, tf,
                {'bi_strict': True, 'trigger_step': True}
            )

            if instance_id:
                instances[f"{symbol}_{tf}"] = instance_id
                print(f"Created Chan analysis: {symbol} {tf} min")

    # Periodically update analysis results
    while True:
        for key, instance_id in instances.items():
            await feeder.update_chan_analysis(instance_id)

            result = feeder.get_chan_analysis_result(instance_id)
            if result:
                bsp_count = len(result.get('buy_sell_points', []))
                zs_count = len(result.get('zs_list', []))
                print(f"{key}: B/S Points={bsp_count}, Center (ZS)={zs_count}")

        await asyncio.sleep(60)  # Update every minute

asyncio.run(chanpy_integration())
```

### Scenario 3: Web Application Integration

```javascript
// Frontend JavaScript integration example
class TradingViewAPIClient {
    constructor(baseUrl = 'http://localhost:8000') {
        this.baseUrl = baseUrl;
        this.websocket = null;
    }

    // Get historical data
    async getHistoricalData(symbol, timeframe, count = 500) {
        const response = await fetch(`${this.baseUrl}/api/v1/data/historical`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                symbol: symbol,
                timeframe: timeframe,
                count: count,
                quality_check: true,
                use_cache: true
            })
        });

        return await response.json();
    }

    // Connect to WebSocket
    connectWebSocket(onMessage) {
        this.websocket = new WebSocket(`ws://localhost:8000/ws/realtime`);

        this.websocket.onopen = () => {
            console.log('WebSocket connection successful');
        };

        this.websocket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            onMessage(data);
        };

        this.websocket.onerror = (error) => {
            console.error('WebSocket error:', error);
        };
    }

    // Subscribe to real-time data
    subscribe(symbols, timeframes = ['1']) {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            this.websocket.send(JSON.stringify({
                type: 'subscribe',
                symbols: symbols,
                timeframes: timeframes
            }));
        }
    }
}

// Example usage
const client = new TradingViewAPIClient();

// Get historical data
client.getHistoricalData('BINANCE:BTCUSDT', '15', 1000)
    .then(data => {
        if (data.status === 'success') {
            console.log(`Obtained ${data.data.klines.length} K-lines`);
            // Process K-line data here, e.g., drawing charts
        }
    });

// Connect to real-time data
client.connectWebSocket((data) => {
    if (data.type === 'realtime_data') {
        console.log(`Real-time Data: ${data.symbol} = $${data.data.price}`);
        // Update UI display
    }
});

// Subscribe to real-time data
client.subscribe(['BINANCE:BTCUSDT', 'BINANCE:ETHUSDT']);
```

## ⚙️ Configuration Parameters

### API Server Configuration

```python
api_server_config = {
    # Server configuration
    'host': '0.0.0.0',
    'port': 8000,

    # Cache configuration
    'cache_db_path': 'data/tradingview_cache.db',
    'max_memory_cache': 5000,

    # TradingView client configuration
    'tradingview_config': {
        'auto_reconnect': True,
        'health_monitoring': True,
        'performance_optimization': True,
        'max_reconnect_attempts': 10,
        'heartbeat_interval': 30,
        'connection_timeout': 10
    },

    # Quality monitoring configuration
    'quality_config': {
        'critical_quality_score': 0.6,
        'warning_quality_score': 0.8,
        'enable_auto_correction': True
    },

    # Security configuration
    'cors_origins': ['*'],
    'rate_limit': {
        'requests_per_minute': 1000,
        'burst_size': 100
    }
}
```

### Data Source Adapter Configuration

```python
data_source_config = {
    # Cache configuration
    'cache_db_path': 'trading_data.db',
    'max_cache_size': 2000,
    'cache_ttl': 3600,  # 1 hour

    # Quality configuration
    'min_quality_score': 0.8,
    'enable_quality_alerts': True,

    # Retry configuration
    'max_retries': 3,
    'retry_delay': 1.0,
    'backoff_factor': 2.0,

    # Performance configuration
    'request_timeout': 10.0,
    'concurrent_requests': 10,
    'batch_size': 100
}
```

## 🛠️ Best Practices

### 1. Connection Management

```python
# ✅ Recommended practice
class ReliableDataSource:
    def __init__(self):
        self.client = None
        self.connection_pool = []

    async def initialize(self):
        # Use connection pool
        for i in range(3):
            client = EnhancedTradingViewClient({
                'auto_reconnect': True,
                'health_monitoring': True
            })
            await client.connect()
            self.connection_pool.append(client)

    async def get_data_with_fallback(self, symbol, timeframe):
        for client in self.connection_pool:
            try:
                return await client.get_data(symbol, timeframe)
            except Exception as e:
                print(f"Client failed, trying next: {e}")
                continue

        raise Exception("All connections failed")
```

### 2. Cache Strategy

```python
# ✅ Smart cache strategy
async def smart_cache_strategy(cache_manager, symbol, timeframe, count):
    # 1. Check cache
    cached_data = await cache_manager.get_historical_data(symbol, timeframe, count)

    if cached_data:
        # 2. Check data freshness
        last_timestamp = max(k['timestamp'] for k in cached_data['klines'])
        age_minutes = (time.time() - last_timestamp) / 60

        # 3. Decide if update is needed based on timeframe
        update_intervals = {'1': 2, '5': 10, '15': 30, '60': 120}
        max_age = update_intervals.get(timeframe, 60)

        if age_minutes < max_age:
            return cached_data  # Use cache

    # 4. Get new data
    fresh_data = await get_fresh_data(symbol, timeframe, count)

    # 5. Update cache
    if fresh_data and fresh_data.get('quality_score', 0) >= 0.8:
        await cache_manager.store_historical_data(symbol, timeframe, fresh_data)

    return fresh_data
```

### 3. Error Handling

```python
# ✅ Robust error handling
async def robust_data_fetching(data_source, symbol, timeframe, max_retries=3):
    for attempt in range(max_retries):
        try:
            data = await data_source.get_historical_data(symbol, timeframe)

            if data and len(data.klines) > 0:
                return data
            else:
                raise ValueError("Data is empty")

        except asyncio.TimeoutError:
            print(f"Request timed out, retrying {attempt + 1}/{max_retries}")
            await asyncio.sleep(2 ** attempt)  # Exponential backoff

        except Exception as e:
            if attempt == max_retries - 1:
                print(f"Final failure: {e}")
                return None
            else:
                print(f"Attempt {attempt + 1} failed: {e}, retrying...")
                await asyncio.sleep(1)

    return None
```

### 4. Monitoring and Alerting

```python
# ✅ Complete monitoring and alerting
class AlertManager:
    def __init__(self):
        self.alert_channels = []

    def add_channel(self, channel):
        self.alert_channels.append(channel)

    async def send_alert(self, level, message, details=None):
        alert_data = {
            'level': level,
            'message': message,
            'details': details or {},
            'timestamp': time.time()
        }

        for channel in self.alert_channels:
            try:
                await channel.send(alert_data)
            except Exception as e:
                print(f"Alert sending failed: {e}")

# Email alert channel
class EmailAlertChannel:
    async def send(self, alert_data):
        # Implement email sending logic
        pass

# Webhook alert channel
class WebhookAlertChannel:
    def __init__(self, webhook_url):
        self.webhook_url = webhook_url

    async def send(self, alert_data):
        async with aiohttp.ClientSession() as session:
            await session.post(self.webhook_url, json=alert_data)
```

## 🔧 Troubleshooting

### Common Problems and Solutions

#### 1. Connection Issues

**Problem**: Unable to connect to TradingView
```
Error: Connection failed: Cannot connect to host
```

**Solution**:
```python
# Check network connection
import aiohttp

async def test_connection():
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('https://www.tradingview.com') as response:
                print(f"Network connection normal: {response.status}")
    except Exception as e:
        print(f"Network connection issue: {e}")

# Check proxy settings
client_config = {
    'proxy': 'http://proxy.example.com:8080',  # If proxy is needed
    'timeout': 30,  # Increase timeout
    'retry_attempts': 5
}
```

#### 2. Data Quality Issues

**Problem**: Data quality score is too low
```
Quality Score: 0.45 (Below threshold 0.8)
```

**Solution**:
```python
# Adjust quality thresholds
quality_config = {
    'critical_quality_score': 0.4,  # Lower threshold
    'warning_quality_score': 0.6,
    'enable_auto_correction': True   # Enable auto-repair
}

# Or use data cleaning
async def clean_data(raw_data):
    cleaned_klines = []

    for kline in raw_data['klines']:
        # Fix price logic errors
        if kline['high'] < max(kline['open'], kline['close']):
            kline['high'] = max(kline['open'], kline['close'])

        if kline['low'] > min(kline['open'], kline['close']):
            kline['low'] = min(kline['open'], kline['close'])

        cleaned_klines.append(kline)

    raw_data['klines'] = cleaned_klines
    return raw_data
```

#### 3. Cache Issues

**Problem**: Cache hit rate is too low
```
Cache Hit Rate: 15% (Expected > 70%)
```

**Solution**:
```python
# Optimize cache configuration
cache_config = {
    'max_memory_size': 5000,  # Increase memory cache size
    'default_expire_seconds': 7200,  # Extend expiration time
    'enable_predictive_caching': True  # Enable predictive caching
}

# Warm up cache
async def warm_cache(cache_manager, popular_symbols):
    for symbol in popular_symbols:
        for timeframe in ['1', '5', '15', '60']:
            await cache_manager.get_historical_data(symbol, timeframe, 500)

    print("Cache warming complete")
```

#### 4. Performance Issues

**Problem**: Response time is too long
```
Average Response Time: 2.5s (Expected < 500ms)
```

**Solution**:
```python
# Enable concurrent processing
async def parallel_data_fetching(symbols, timeframe):
    tasks = []

    for symbol in symbols:
        task = asyncio.create_task(
            get_data_with_timeout(symbol, timeframe, timeout=1.0)
        )
        tasks.append(task)

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Filter successful results
    valid_results = [r for r in results if not isinstance(r, Exception)]
    return valid_results

# Enable connection reuse
client_config = {
    'connection_pool_size': 20,
    'keep_alive_timeout': 60,
    'enable_compression': True
}
```

### Debugging Tools

#### 1. Health Check Tool

```python
async def health_check():
    """Comprehensive health check"""

    # Check API server
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get('http://localhost:8000/api/v1/health') as response:
                if response.status == 200:
                    data = await response.json()
                    print(f"✅ API Server: {data.get('status')}")
                else:
                    print(f"❌ API Server: HTTP {response.status}")
    except Exception as e:
        print(f"❌ API Server: {e}")

    # Check cache
    try:
        cache_manager = DataCacheManager('test_cache.db')
        await cache_manager.store_historical_data('TEST', '1', {'klines': []})
        cached = await cache_manager.get_historical_data('TEST', '1')
        if cached is not None:
            print("✅ Cache System: Normal")
        else:
            print("❌ Cache System: Abnormal")
    except Exception as e:
        print(f"❌ Cache System: {e}")

    # Check TradingView connection
    try:
        client = EnhancedTradingViewClient()
        if await client.connect():
            print("✅ TradingView Connection: Normal")
            await client.disconnect()
        else:
            print("❌ TradingView Connection: Failed")
    except Exception as e:
        print(f"❌ TradingView Connection: {e}")

# Run health check
asyncio.run(health_check())
```

#### 2. Performance Analysis Tool

```python
import time
from functools import wraps

def timing_decorator(func):
    """Performance timing decorator"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        start_time = time.time()
        result = await func(*args, **kwargs)
        end_time = time.time()

        print(f"{func.__name__} execution time: {end_time - start_time:.3f}s")
        return result

    return wrapper

# Usage example
@timing_decorator
async def timed_data_fetch(symbol, timeframe):
    return await data_source.get_historical_data(symbol, timeframe)
```

#### 3. Log Analysis Tool

```python
import logging
from collections import defaultdict

class PerformanceLogger:
    def __init__(self):
        self.metrics = defaultdict(list)
        self.logger = logging.getLogger(__name__)

    def log_request(self, symbol, timeframe, response_time, cache_hit):
        self.metrics['response_times'].append(response_time)
        self.metrics['cache_hits'].append(cache_hit)

        self.logger.info(f"Request: {symbol}:{timeframe}, "
                        f"Response Time: {response_time:.3f}s, "
                        f"Cache Hit: {cache_hit}")

    def get_statistics(self):
        if not self.metrics['response_times']:
            return {}

        response_times = self.metrics['response_times']
        cache_hits = self.metrics['cache_hits']

        return {
            'avg_response_time': sum(response_times) / len(response_times),
            'max_response_time': max(response_times),
            'min_response_time': min(response_times),
            'cache_hit_rate': sum(cache_hits) / len(cache_hits),
            'total_requests': len(response_times)
        }

# Usage example
perf_logger = PerformanceLogger()

# Log performance during data acquisition
async def monitored_data_fetch(symbol, timeframe):
    start_time = time.time()

    # Check cache
    cached_data = await cache_manager.get_historical_data(symbol, timeframe)
    cache_hit = cached_data is not None

    if not cache_hit:
        # Get from API
        data = await api_client.get_data(symbol, timeframe)
    else:
        data = cached_data

    response_time = time.time() - start_time
    perf_logger.log_request(symbol, timeframe, response_time, cache_hit)

    return data

# Periodically output statistical information
async def print_statistics():
    while True:
        await asyncio.sleep(60)  # Output every minute
        stats = perf_logger.get_statistics()
        if stats:
            print(f"Performance Statistics: {stats}")
```

## 📈 Monitoring and Alerting

### Prometheus Integration

```python
from prometheus_client import Counter, Histogram, Gauge, start_http_server

# Define metrics
request_count = Counter('tradingview_requests_total', 'Total requests', ['symbol', 'timeframe'])
request_duration = Histogram('tradingview_request_duration_seconds', 'Request duration')
cache_hit_rate = Gauge('tradingview_cache_hit_rate', 'Cache hit rate')
data_quality_score = Gauge('tradingview_data_quality', 'Data quality score', ['symbol'])

class PrometheusMonitor:
    def __init__(self, port=9090):
        self.port = port
        start_http_server(port)
        print(f"Prometheus monitoring port: {port}")

    def record_request(self, symbol, timeframe, duration, cache_hit):
        request_count.labels(symbol=symbol, timeframe=timeframe).inc()
        request_duration.observe(duration)

        # Update cache hit rate (simplified calculation)
        current_rate = cache_hit_rate._value.get() or 0
        new_rate = (current_rate * 0.9) + (1.0 if cache_hit else 0.0) * 0.1
        cache_hit_rate.set(new_rate)

    def record_quality_score(self, symbol, score):
        data_quality_score.labels(symbol=symbol).set(score)

# Usage example
monitor = PrometheusMonitor()

async def monitored_request(symbol, timeframe):
    start_time = time.time()

    # Execute request
    cache_hit, data = await get_data_with_cache(symbol, timeframe)

    # Record metrics
    duration = time.time() - start_time
    monitor.record_request(symbol, timeframe, duration, cache_hit)

    # Record quality score
    if data and 'quality_score' in data:
        monitor.record_quality_score(symbol, data['quality_score'])

    return data
```

---

## 🎯 Summary

The TradingView Module External Integration Guide provides a complete integration solution, including:

- **🔌 Multiple Integration Methods**: RESTful API, WebSocket, Python SDK
- **🗄️ Dual-layer Cache Architecture**: Memory + SQLite, providing high-performance data access
- **🛡️ Six-dimensional Quality Monitoring**: Comprehensive data quality assessment and alerting mechanism
- **📊 Complete Example Code**: Examples covering various usage scenarios
- **🛠️ Best Practice Guide**: Connection management, cache strategy, error handling
- **🔧 Troubleshooting Tools**: Health check, performance analysis, log monitoring

By following this guide, you can quickly and reliably integrate the TradingView data source into your trading system and obtain professional-level data service support.
