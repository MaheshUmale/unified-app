# TradingView K-line Data HTTP API Service

Professional TradingView historical K-line data HTTP API service, providing RESTful interfaces for real-time and historical K-line data.

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install fastapi uvicorn
```

### 2. Start Service

```bash
# Default port 8000
python -m tradingview.kline_api_server

# Specify port
python -m tradingview.kline_api_server --port 8080

# Development mode (Hot Reload)
python -m tradingview.kline_api_server --reload
```

### 3. Access API Documentation

Once the service starts, visit the following addresses for interactive API documentation:

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

## 📡 API Endpoints

### 1. Get K-line Data

**Endpoint**: `GET /klines`

**Parameters**:
- `symbol` (Required): Trading symbol (e.g., `BINANCE:BTCUSDT`)
- `timeframe` (Optional): Timeframe, default `15`. Supports `1`, `5`, `15`, `30`, `60`, `1D`, etc.
- `count` (Optional): Number of K-lines, default `100`, range `1-5000`.
- `quality` (Optional): Quality level: `development`, `production`, `financial`.
- `use_cache` (Optional): Whether to use cache, default `true`.
- `format` (Optional): Return format: `json` (default) or `simple`.

### 2. Batch Get K-line Data

**Endpoint**: `GET /batch_klines`

**Parameters**:
- `symbols` (Required): Comma-separated list of symbols (up to 50).
- Other parameters same as `/klines`.

### 3. Health Check

**Endpoint**: `GET /health`

### 4. Service Statistics

**Endpoint**: `GET /stats`

## 🐳 Docker Deployment

Create `Dockerfile`:

```dockerfile
FROM python:3.10-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8000
CMD ["python", "-m", "tradingview.kline_api_server", "--host", "0.0.0.0", "--port", "8000"]
```
