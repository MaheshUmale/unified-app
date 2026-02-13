# TradingView K-Line API Quick Start Guide

## 🚀 One-Minute Quick Start

### Step 1: Install Dependencies

```bash
pip install fastapi uvicorn
```

### Step 2: Start Service

```bash
python -m tradingview.kline_api_server
```

You will see:

```
==========================================
🚀 TradingView K-Line Data HTTP API Service
==========================================

📡 Service Address: http://0.0.0.0:8000
📚 API Docs: http://0.0.0.0:8000/docs
📊 ReDoc: http://0.0.0.0:8000/redoc

Example Requests:
  curl "http://0.0.0.0:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100"
  curl "http://0.0.0.0:8000/klines?symbol=BTCUSDT&timeframe=15m&count=50"
  curl "http://0.0.0.0:8000/health"
  curl "http://0.0.0.0:8000/stats"

==========================================
Press Ctrl+C to stop service
```

### Step 3: Test Request

Open a new terminal and execute tests:

```bash
# Test 1: Health Check
curl "http://localhost:8000/health"

# Test 2: Get Gold 15-minute K-lines
curl "http://localhost:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=10"

# Test 3: Get BTC K-lines (Simple format)
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=15m&count=5&format=simple"
```

Or use the test script:

```bash
chmod +x test_kline_api.sh
./test_kline_api.sh
```

### Step 4: Browser Access

Open in browser: http://localhost:8000/docs

You will see the interactive API documentation where you can test all interfaces directly in the browser.

## 📝 Common Commands

### Start Service

```bash
# Default port 8000
python -m tradingview.kline_api_server

# Specify port
python -m tradingview.kline_api_server --port 8080

# Development mode (auto-reload)
python -m tradingview.kline_api_server --reload

# Multi-process mode
python -m tradingview.kline_api_server --workers 4
```

### API Request Examples

```bash
# 1. Get Gold 15-minute K-lines
curl "http://localhost:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100"

# 2. Get Bitcoin 1-hour K-lines
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=1h&count=50&format=simple"

# 3. Batch get multiple symbols
curl "http://localhost:8000/batch_klines?symbols=BTCUSDT,ETHUSDT&timeframe=15&count=20"

# 4. Get high-quality data
curl "http://localhost:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100&quality=financial"

# 5. Health Check
curl "http://localhost:8000/health"

# 6. Service Statistics
curl "http://localhost:8000/stats"
```

## 🎯 Core Features

### 1. Single Symbol K-Line Retrieval

**Simplest request**:
```bash
curl "http://localhost:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100"
```

**Full parameters**:
```bash
curl "http://localhost:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100&quality=production&use_cache=true&format=simple"
```

### 2. Batch Retrieval

**Get multiple symbols**:
```bash
curl "http://localhost:8000/batch_klines?symbols=BINANCE:BTCUSDT,BINANCE:ETHUSDT,OANDA:XAUUSD&timeframe=15&count=50"
```

### 3. Different Timeframes

```bash
# 1 minute
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=1m&count=60"

# 15 minutes
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=15m&count=100"

# 1 hour
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=1h&count=24"

# 4 hours
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=4h&count=30"

# Daily
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=1d&count=365"
```

## 🔧 Configuration Description

### Symbol Formats

| Input Format | Automatically Converted To | Description |
|---------|-----------|------|
| `OANDA:XAUUSD` | `OANDA:XAUUSD` | Standard format, remains unchanged |
| `BTCUSDT` | `BINANCE:BTCUSDT` | Automatically adds BINANCE prefix |
| `ETHUSDT` | `BINANCE:ETHUSDT` | Automatically adds BINANCE prefix |

### Timeframe Formats

| Input Format | Standard Format | Description |
|---------|---------|------|
| `1`, `1m`, `1min` | `1` | 1 minute |
| `5`, `5m` | `5` | 5 minutes |
| `15`, `15m` | `15` | 15 minutes |
| `30`, `30m` | `30` | 30 minutes |
| `60`, `1h` | `60` | 1 hour |
| `240`, `4h` | `240` | 4 hours |
| `1D`, `1d` | `1D` | Daily |
| `1W`, `1w` | `1W` | Weekly |
| `1M` | `1M` | Monthly |

### Quality Levels

| Level | Quality Requirement | Use Case |
|-----|---------|---------|
| `development` | ≥90% | Dev/Test |
| `production` | ≥95% | Production Environment (Default) |
| `financial` | ≥98% | Financial-grade Trading |

## 📊 Response Format

### Simple Format (Recommended)

```json
{
  "success": true,
  "symbol": "OANDA:XAUUSD",
  "timeframe": "15",
  "count": 2,
  "data": [
    {
      "timestamp": 1699123456,
      "datetime": "2023-11-04T10:30:00",
      "open": 2645.50,
      "high": 2648.30,
      "low": 2644.20,
      "close": 2647.80,
      "volume": 1234.56
    },
    {
      "timestamp": 1699124356,
      "datetime": "2023-11-04T10:45:00",
      "open": 2647.80,
      "high": 2650.10,
      "low": 2646.50,
      "close": 2649.20,
      "volume": 2345.67
    }
  ]
}
```

### JSON Format (Full)

Contains more metadata such as quality metrics, request ID, response time, etc.

## 🐛 Common Questions

### Q1: Service Failed to Start

**Problem**: `ModuleNotFoundError: No module named 'fastapi'`

**Solution**:
```bash
pip install fastapi uvicorn
```

### Q2: Port Already Occupied

**Problem**: `Address already in use`

**Solution**:
```bash
# Option 1: Use another port
python -m tradingview.kline_api_server --port 8080

# Option 2: Stop the process occupying port 8000
lsof -i :8000
kill -9 <PID>
```

### Q3: Failed to Retrieve Data

**Problem**: Returns 500 error

**Solution**:
```bash
# 1. Check service health
curl "http://localhost:8000/health"

# 2. View service logs
# Service logs will show detailed error messages

# 3. Check TradingView connection
# Ensure network is normal and TradingView is accessible
```

### Q4: Low Data Quality

**Problem**: quality_score < 0.95

**Solution**:
```bash
# 1. Don't use cache, get latest data
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=15&count=100&use_cache=false"

# 2. Lower quality requirements
curl "http://localhost:8000/klines?symbol=BTCUSDT&timeframe=15&count=100&quality=development"
```

## 🎓 Advanced Usage

### Python Client Example

```python
import requests

# Get K-line data
response = requests.get(
    "http://localhost:8000/klines",
    params={
        "symbol": "OANDA:XAUUSD",
        "timeframe": "15",
        "count": 100,
        "format": "simple"
    }
)

data = response.json()

if data["success"]:
    print(f"Obtained {data['count']} K-line data points")
    for kline in data["data"][:5]:  # Print first 5
        print(f"{kline['datetime']}: O={kline['open']}, "
              f"H={kline['high']}, L={kline['low']}, C={kline['close']}")
else:
    print(f"Retrieval Failed: {data.get('error')}")
```

### JavaScript Client Example

```javascript
// Using fetch API
fetch('http://localhost:8000/klines?symbol=BTCUSDT&timeframe=15&count=100&format=simple')
  .then(response => response.json())
  .then(data => {
    if (data.success) {
      console.log(`Obtained ${data.count} K-lines`);
      data.data.forEach(kline => {
        console.log(`${kline.datetime}: ${kline.close}`);
      });
    }
  })
  .catch(error => console.error('Error:', error));
```

### Integration with Analysis Systems

```python
from tradingview.historical_kline_service import HistoricalKlineService
import requests

# Get data via API
response = requests.get(
    "http://localhost:8000/klines",
    params={
        "symbol": "BINANCE:BTCUSDT",
        "timeframe": "15",
        "count": 500,
        "quality": "financial"
    }
)

klines = response.json()["data"]

# Convert to system format for analysis
# ... Subsequent analysis logic
```

## 📚 Resources

- **Detailed Documentation**: [README_KLINE_API.md](./README_KLINE_API.md)
- **Interactive API Docs**: http://localhost:8000/docs
- **Source Code**: [kline_api_server.py](./kline_api_server.py)
- **Service Layer**: [historical_kline_service.py](./historical_kline_service.py)

## 🎉 Start Using

Now that you know how to use the K-line API service, start getting the data you need!

```bash
# Start Service
python -m tradingview.kline_api_server

# Test in new terminal
curl "http://localhost:8000/klines?symbol=OANDA:XAUUSD&timeframe=15&count=100"
```

Enjoy using it! 🚀
