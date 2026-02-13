# TradingView Data Sync and Backup System Guide

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Quick Start](#quick-start)
3. [Data Synchronization](#data-synchronization)
4. [Data Backup](#data-backup)
5. [Configuration Management](#configuration-management)
6. [CLI Tool Usage](#cli-tool-usage)
7. [Monitoring and Maintenance](#monitoring-and-maintenance)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)

---

## 🎯 System Overview

The TradingView data synchronization and backup system provides a complete data lifecycle management solution, including:

### Core Features

- **📊 Multi-source Data Sync**: Supports flexible synchronization between primary data sources, cache, and backups.
- **💾 Multi-type Backups**: Full backup, incremental backup, snapshot backup, and differential backup.
- **⏰ Task Scheduling**: Flexible task scheduling based on Cron expressions.
- **🔍 Real-time Monitoring**: Complete performance metrics and health checks.
- **🛠️ CLI Management Tool**: Command-line interface for convenient operation and maintenance.
- **⚡ High-Performance Design**: Asynchronous processing, concurrency control, and intelligent caching.

### Architecture Design

```
┌─────────────────────────────────────────────────────────────────┐
│                 Data Sync & Backup System Architecture          │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  📊 Data Source Layer                                           │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐            │
│  │ TradingView │  │ Cache System│  │ Backup Store│            │
│  │  (Primary)  │  │  (Cache)    │  │  (Backup)   │            │
│  └─────────────┘  └─────────────┘  └─────────────┘            │
│         │                 │                 │                  │
│         └─────────────────┼─────────────────┘                  │
│                           │                                    │
│  🔄 Sync Engine Layer     │                                    │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │           DataSyncEngine (Async Task Scheduler)             │ │
│  │                                                             │ │
│  │ • Queue Mgmt  • Concurrency  • Retry Mech • Perf Monitor    │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                           │                                    │
│  💾 Backup Management Layer                                     │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │          DataBackupManager (Lifecycle Management)           │ │
│  │                                                             │ │
│  │ • Backup Types • Versioning • Verification • Cleanup        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🚀 Quick Start

### Environment Preparation

```bash
# 1. Install dependencies
pip install asyncio pyyaml schedule prometheus_client

# 2. Create necessary directories
mkdir -p data/backups
mkdir -p logs

# 3. Check configuration file
ls tradingview/sync_backup_config.yaml
```

### 30-Second Quick Experience

```bash
# 1. Run system test
python tradingview/sync_backup_cli.py test

# 2. Check system status
python tradingview/sync_backup_cli.py status

# 3. Create a snapshot backup
python tradingview/sync_backup_cli.py backup --type snapshot

# 4. List all backups
python tradingview/sync_backup_cli.py list backups
```

---

## 🔄 Data Synchronization

### Sync Types and Directions

| Source Type | Target Type | Description | Use Case |
|-------------|-------------|-------------|----------|
| primary     | cache       | Primary source to cache | Real-time data updates |
| cache       | backup      | Cache to backup | Regular data backup |
| backup      | cache       | Backup to cache | Disaster recovery |
| cache       | remote      | Cache to remote | Data distribution |

---

## 💾 Data Backup

### Backup Types Detailed

#### 1. Full Backup
A complete data backup, containing all historical data.
```bash
python tradingview/sync_backup_cli.py backup --type full
```

#### 2. Incremental Backup
Only backs up new data since the last backup.
```bash
python tradingview/sync_backup_cli.py backup --type incremental
```

#### 3. Snapshot Backup
Backs up the data state at the current moment.
```bash
python tradingview/sync_backup_cli.py backup --type snapshot
```

---

## 🛠️ CLI Tool Usage

### Basic Commands

```bash
# View help
python tradingview/sync_backup_cli.py --help

# Check system status
python tradingview/sync_backup_cli.py status
```

### Backup Management Commands

```bash
# Create full backup
python tradingview/sync_backup_cli.py backup --type full

# List all backups
python tradingview/sync_backup_cli.py list backups

# Restore backup
python tradingview/sync_backup_cli.py restore <backup_id>
```

---

## ✅ Best Practices

1. **Backup Strategy**: Use weekly full backups, daily incremental backups, and hourly snapshots.
2. **Resource Management**: Monitor disk space and memory usage during large sync tasks.
3. **Verification**: Regularly verify backups using the `test` command to ensure data integrity.

---

## 📞 Technical Support

For more details, check the source code or use the CLI help command.
