# TradingView Account Configuration Management System

## 📋 Feature Overview

The TradingView account configuration management system provides a complete solution for managing authentication information, supporting:

- **Environment Variable Priority** - Authentication info is retrieved from environment variables first.
- **Multi-Account Management** - Support for configuring multiple TradingView accounts.
- **Secure Encrypted Storage** - Support for encrypting configuration files to protect sensitive info.
- **CLI Management Tool** - Provides a full CLI tool for managing account configurations.
- **Automatic Integration** - Automatically integrates into existing TradingView clients.

## 🚀 Quick Start

### 1. Environment Variable Method (Recommended)

```bash
# Set environment variables
export TV_SESSION="your_session_token_here"
export TV_SIGNATURE="your_signature_here"
export TV_SERVER="data"  # Optional, defaults to "data"

# Use directly without extra configuration
python your_script.py
```

### 2. Configuration File Method

```bash
# Use CLI tool to add an account
python auth_cli.py add --from-env --set-default

# Or manually add an account
python auth_cli.py add
```

### 3. Usage in Code

```python
# Automatically retrieve auth info from configuration
from tradingview import Client
client = Client()  # Automatically uses configured auth info
await client.connect()

# Specify a specific account
client = Client({'account_name': 'my_account'})
await client.connect()

# Enhanced client also supports this
from tradingview.enhanced_client import EnhancedTradingViewClient
client = EnhancedTradingViewClient()
await client.connect()
```

## 📁 File Structure

```
tradingview/
├── auth_config.py          # Core module for auth config management
├── auth_cli.py             # CLI management tool
├── README_AUTH.md          # This documentation
└── client.py               # Authentication manager integrated

config/
└── tradingview_auth.yaml   # Default configuration file template
```

## 🔧 CLI Tool Usage

### Basic Commands

```bash
# View all account configurations
python auth_cli.py list

# Add account from environment variables and set as default
python auth_cli.py add --from-env --set-default

# Manually add account
python auth_cli.py add

# Test account connection
python auth_cli.py test [account_name]

# Set default account
python auth_cli.py default my_account

# Remove account
python auth_cli.py remove my_account --force
```

### Advanced Features

```bash
# Enable configuration file encryption
python auth_cli.py encrypt --password

# Disable configuration file encryption
python auth_cli.py decrypt --force

# Export configuration
python auth_cli.py export --output my_accounts.json

# Import configuration
python auth_cli.py import my_accounts.json

# Update account information
python auth_cli.py update my_account --server prodata --description "Professional Account"
```

## ⚙️ Configuration File Format

### YAML Format (Recommended)

```yaml
# config/tradingview_auth.yaml
config_version: "1.0"
encryption_enabled: false
default_account: "main_account"

accounts:
  - name: "main_account"
    session_token: "your_session_token"
    signature: "your_signature"
    server: "data"
    description: "Primary trading account"
    is_active: true
    created_at: "2024-01-01T00:00:00"
    last_used: null
```

### Encrypted Storage

Format when encryption is enabled:

```yaml
encrypted: true
content: "gAAAAABh5x..."  # Encrypted configuration content
version: "1.0"
created_at: "2024-01-01T00:00:00"
```

## 🔐 Obtaining Authentication Info

### 1. Log in to TradingView

Visit [TradingView Official Site](https://tradingview.com) and log in to your account.

### 2. Get Session and Signature

1. Open Browser Developer Tools (F12).
2. Switch to the **Network** tab.
3. Filter for **WS** (WebSocket) requests.
4. Refresh the page or open a chart.
5. Find the WebSocket connection request.
6. Look for these in request details:
   - `session`: Copy as `TV_SESSION`.
   - `signature`: Copy as `TV_SIGNATURE`.

### 3. Verify Configuration

```bash
# Test if configuration is correct
python auth_cli.py test
```

## 🎯 Use Priority

Authentication info retrieval priority (highest to lowest):

1. **Environment Variables** - `TV_SESSION`, `TV_SIGNATURE`, `TV_SERVER`.
2. **Specified Account** - Specified via the `account_name` parameter.
3. **Default Account** - `default_account` in the config file.
4. **First Active Account** - The first account with `is_active: true` in the config file.

## 🛡️ Security Recommendations

### Production Environment

```bash
# 1. Enable configuration file encryption
python auth_cli.py encrypt --password

# 2. Set file permissions
chmod 600 config/tradingview_auth.yaml

# 3. Use environment variables (more secure)
export TV_SESSION="..."
export TV_SIGNATURE="..."
```

### Development Environment

```bash
# Use configuration file for easy management of multiple accounts
python auth_cli.py add --from-env --set-default
```

## 📊 Configuration Examples

### Multi-Account Example

```yaml
accounts:
  # Primary account
  - name: "main_trading"
    session_token: "main_session_token"
    signature: "main_signature"
    server: "data"
    description: "Main trading account"
    is_active: true

  # Backup account
  - name: "backup_account"
    session_token: "backup_session_token"
    signature: "backup_signature"
    server: "data"
    description: "Backup account"
    is_active: true

  # Pro data account
  - name: "pro_data"
    session_token: "pro_session_token"
    signature: "pro_signature"
    server: "prodata"
    description: "Pro data account"
    is_active: false  # Activate when needed
```

### Switching Accounts in Code

```python
# Use default account
client = Client()

# Use specified account
client = Client({'account_name': 'backup_account'})

# Use pro data account
client = Client({'account_name': 'pro_data'})
```

## 🔍 Troubleshooting

### Common Problems

1. **Authentication Failure**
   ```bash
   python auth_cli.py test  # Test connection
   ```

2. **Configuration File Permission Issues**
   ```bash
   chmod 600 config/tradingview_auth.yaml
   ```

3. **Cannot Read Encrypted Config**
   ```bash
   python auth_cli.py decrypt --force  # Disable encryption
   ```

4. **Environment Variables Not Taking Effect**
   ```bash
   echo $TV_SESSION  # Check environment variable
   source ~/.bashrc  # Reload environment variables
   ```

### Debug Mode

```python
# Enable debug logs
import logging
logging.basicConfig(level=logging.DEBUG)

from tradingview.auth_config import get_auth_manager
auth_manager = get_auth_manager()
account = auth_manager.get_account()
print(f"Using account: {account.name if account else 'None'}")
```

## 🔄 Migration Guide

### Migrating from Environment Variables to Config File

```bash
# 1. Create config from current environment variables
python auth_cli.py add --from-env --set-default

# 2. Verify config
python auth_cli.py list

# 3. Test connection
python auth_cli.py test
```

### Configuration Format Upgrade

The configuration manager automatically handles version compatibility; no manual upgrade is required.

## 📚 API Reference

### Main Classes and Functions

```python
from tradingview.auth_config import (
    TradingViewAuthManager,     # Auth manager
    TradingViewAccount,         # Account config class
    get_auth_manager,          # Get global manager instance
    get_tradingview_auth       # Helper function for auth info
)

# Get authentication info
auth_info = get_tradingview_auth('my_account')
# Returns: {'token': '...', 'signature': '...', 'server': 'data'}

# Using the manager
auth_manager = get_auth_manager()
account = auth_manager.get_account('my_account')
```

---

**Note**: Please keep your TradingView authentication information secure; do not share it with others or commit it to public code repositories.
