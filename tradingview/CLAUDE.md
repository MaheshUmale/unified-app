# CLAUDE.md - TradingView Professional Data Source Engine

This file provides guidance for Claude Code when working in the TradingView professional data source engine module.

## 🎯 Module Positioning & Design Philosophy

### Core Positioning
The `tradingview` module is the **data cornerstone** of the entire trading system, carrying the critical responsibility of the "data lifeline." It is not just a simple data acquisition tool but a professional data source engine with enterprise-grade reliability.

### Design Philosophy
```
🏗️ Core Design Concepts
├── Single Responsibility Principle - Focus on data acquisition, no analysis logic
├── High Availability First - 99.9%+ availability, automatic fault recovery
├── Data Quality First - 95%+ quality guarantee, better to have nothing than bad data
├── Standardized Interfaces - Unified data format for easy system integration
└── Progressive Enhancement - Smooth upgrade from basic client to enhanced features
```

### Module Value Proposition
- **For Trading Analysis**: Provides high-quality, formatted K-line data.
- **For Core System**: Provides real-time market data and historical data support.
- **For Overall System**: Provides a unified data source abstraction layer.
- **For Developers**: Simple and easy-to-use data acquisition interfaces.

## 🏗️ Architectural Design Principles

### Layered Architecture
```
📐 Five-Layer Architecture Design

┌─────────────────────────────────────────────────────────────────┐
│                    📱 Application Interface Layer               │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ TradingViewEngine  │  Data Manager  │  Integration Adapters  │  │
│  └─────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    🔧 Enhancement Layer                         │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │ Conn Monitoring │ Quality Assurance │ Perf Opt │ Recovery  │  │
│  └─────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    📊 Data Session Layer                        │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  ChartSession     │     QuoteSession    │   StudySession   │  │
│  │  (K-line Mgmt)    │   (Real-time Quote) │   (Indicators)   │  │
│  └─────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    🔌 Connection Management Layer               │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  WebSocket Mgmt   │ Message Processing │ Auth │ Conn Pool  │  │
│  └─────────────────────────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────┤
│                    🌐 Protocol Processing Layer                │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │  Encoding/Decoding │ Parsing │ Error Handling │ Conversion │  │
│  └─────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 🔌 Standard Integration Process

### Quick Start (5 Minutes)
1. **Choose Client Type**: Basic (`Client`), Enterprise (`EnhancedTradingViewClient`), or Integrated (`EnhancedTradingViewEngine`).
2. **Establish Connection**: `await client.connect()`, check state, handle errors.
3. **Fetch Data**: `chart = client.Session.Chart()`, `data = await chart.get_historical_data()`.

## 🛡️ Quality Assurance Mechanism

### Four-Level Quality System
- **L1: Protocol Layer**: Format checks, type validation, field integrity.
- **L2: Logical Layer**: Price relationship validation (high >= max(open, close)), timestamp consistency.
- **L3: Statistical Layer**: Continuity checks, outlier detection, trend consistency.
- **L4: System Layer**: Metrics statistics, trend analysis, anomaly alerting.

## 🔧 Fault Handling Strategy

### Fault Classification
- **Network**: Timeout, disconnection, auth failure -> Exponential backoff, reconnection.
- **Data**: Missing data, anomalies, format errors -> Use backup sources, manual review.
- **System**: OOM, CPU overload, disk space -> Cache cleanup, rate limiting.

## 📊 Collaboration with Other Modules

### Relationship Map
The module acts as a data provider for `trading_core` and analysis engines, consumes configuration from the `config` module, and provides the foundation for trade execution.

---

**💡 Core Design Concept**: The `tradingview` module follows the "Data Supremacy, Quality First, Stable and Reliable" design principles, providing a solid data foundation for the entire trading system.
