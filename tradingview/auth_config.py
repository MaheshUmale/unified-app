#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Account Configuration Manager
Supports environment variable priority and persistent configuration file storage.
"""
import rookiepy
from typing import Optional
from dataclasses import dataclass
from datetime import datetime

import os
import json
import yaml
from pathlib import Path
from typing import Dict, List, Optional, Any, Union
from dataclasses import dataclass, asdict
from datetime import datetime
import base64
import hashlib
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

from tradingview.utils import get_logger

logger = get_logger(__name__)


@dataclass
class TradingViewAccount:
    """TradingView Account Configuration"""
    name: str                           # Account name/identifier
    session_token: str                  # TV_SESSION
    signature: str                      # TV_SIGNATURE
    server: str = "data"               # Selected server
    description: str = ""              # Account description
    is_active: bool = True             # Whether account is active
    created_at: Optional[str] = None   # Creation time
    last_used: Optional[str] = None    # Last used time

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now().isoformat()

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TradingViewAccount':
        """Create instance from dictionary"""
        return cls(**data)

    def update_last_used(self):
        """Update last used timestamp"""
        self.last_used = datetime.now().isoformat()


@dataclass
class AuthConfig:
    """Authentication Configuration"""
    accounts: List[TradingViewAccount]
    default_account: Optional[str] = None   # Name of the default account
    encryption_enabled: bool = False        # Whether encryption is enabled
    config_version: str = "1.0"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        return {
            'accounts': [acc.to_dict() for acc in self.accounts],
            'default_account': self.default_account,
            'encryption_enabled': self.encryption_enabled,
            'config_version': self.config_version
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'AuthConfig':
        """Create instance from dictionary"""
        accounts = [TradingViewAccount.from_dict(acc_data) for acc_data in data.get('accounts', [])]
        return cls(
            accounts=accounts,
            default_account=data.get('default_account'),
            encryption_enabled=data.get('encryption_enabled', False),
            config_version=data.get('config_version', '1.0')
        )


class ConfigEncryption:
    """Configuration File Encryption Management"""

    def __init__(self, password: Optional[str] = None):
        self.password = password or self._get_default_password()
        self.key = self._derive_key(self.password)
        self.cipher_suite = Fernet(self.key)

    def _get_default_password(self) -> str:
        """Get default password"""
        # Get from env or generate from machine identifier
        env_password = os.getenv('TV_CONFIG_PASSWORD')
        if env_password:
            return env_password

        # Use machine info for unique password
        import platform
        machine_info = f"{platform.node()}-{platform.machine()}-{platform.system()}"
        return hashlib.sha256(machine_info.encode()).hexdigest()[:32]

    def _derive_key(self, password: str) -> bytes:
        """Derive encryption key from password"""
        password_bytes = password.encode()
        salt = b'tradingview_auth_salt_2024'  # Static salt for now

        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=32,
            salt=salt,
            iterations=100000,
        )
        key = base64.urlsafe_b64encode(kdf.derive(password_bytes))
        return key

    def encrypt(self, data: str) -> str:
        """Encrypt data"""
        try:
            encrypted_data = self.cipher_suite.encrypt(data.encode())
            return base64.urlsafe_b64encode(encrypted_data).decode()
        except Exception as e:
            logger.error(f"Data encryption failed: {e}")
            raise

    def decrypt(self, encrypted_data: str) -> str:
        """Decrypt data"""
        try:
            encrypted_data_bytes = base64.urlsafe_b64decode(encrypted_data.encode())
            decrypted_data = self.cipher_suite.decrypt(encrypted_data_bytes)
            return decrypted_data.decode()
        except Exception as e:
            logger.error(f"Data decryption failed: {e}")
            raise


class TradingViewAuthManager:
    """TradingView Authentication Manager"""

    def __init__(self, config_file: Optional[str] = None, encryption_password: Optional[str] = None):
        """
        Initialize auth manager.

        Args:
            config_file: Config file path
            encryption_password: Password for encryption
        """
        self.config_file = config_file or self._get_default_config_path()
        self.config_dir = Path(self.config_file).parent
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # Encryption manager
        self.encryption = ConfigEncryption(encryption_password)

        # Auth config
        self.auth_config: Optional[AuthConfig] = None

        # Env config cache
        self._env_config_cache: Optional[TradingViewAccount] = None

        # Load config
        self._load_config()

    def _get_default_config_path(self) -> str:
        """Get default config file path"""
        # Env variable has priority
        env_config_path = os.getenv('TV_AUTH_CONFIG_PATH')
        if env_config_path:
            return env_config_path

        # Default project path
        project_root = Path(__file__).parent.parent
        config_path = project_root / "config" / "tradingview_auth.yaml"
        return str(config_path)

    def _load_config(self):
        """Load configuration file"""
        try:
            config_path = Path(self.config_file)

            if not config_path.exists():
                logger.info(f"Config file not found, creating default: {self.config_file}")
                self.auth_config = AuthConfig(accounts=[])
                self._save_config()
                return

            # Read file
            with open(config_path, 'r', encoding='utf-8') as f:
                if config_path.suffix.lower() == '.json':
                    data = json.load(f)
                else:
                    data = yaml.safe_load(f) or {}

            # Check for encryption
            if data.get('encrypted', False):
                encrypted_content = data.get('content', '')
                if encrypted_content:
                    decrypted_content = self.encryption.decrypt(encrypted_content)
                    data = json.loads(decrypted_content)
                else:
                    logger.warning("Config marked as encrypted but content is empty")
                    data = {}

            # Parse config
            self.auth_config = AuthConfig.from_dict(data)
            logger.info(f"Loaded config: {self.config_file}, Account count: {len(self.auth_config.accounts)}")

        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            self.auth_config = AuthConfig(accounts=[])

    def _save_config(self):
        """Save configuration to file"""
        try:
            config_path = Path(self.config_file)
            config_data = self.auth_config.to_dict()

            # Handle encryption
            if self.auth_config.encryption_enabled:
                content_json = json.dumps(config_data, ensure_ascii=False, indent=2)
                encrypted_content = self.encryption.encrypt(content_json)

                final_data = {
                    'encrypted': True,
                    'content': encrypted_content,
                    'version': self.auth_config.config_version,
                    'created_at': datetime.now().isoformat()
                }
            else:
                final_data = config_data

            # Write file
            with open(config_path, 'w', encoding='utf-8') as f:
                if config_path.suffix.lower() == '.json':
                    json.dump(final_data, f, ensure_ascii=False, indent=2)
                else:
                    yaml.dump(final_data, f, default_flow_style=False, allow_unicode=True)

            # Set restrictive permissions (owner read/write only)
            config_path.chmod(0o600)
            logger.info(f"Config saved: {self.config_file}")

        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            raise

    def _get_env_config(self) -> Optional[TradingViewAccount]:
        """Retrieve configuration from environment variables"""
        if self._env_config_cache:
            return self._env_config_cache

        session_token = os.getenv('TV_SESSION')
        signature = os.getenv('TV_SIGNATURE')

        if session_token and signature:
            server = os.getenv('TV_SERVER', 'data')

            self._env_config_cache = TradingViewAccount(
                name="environment",
                session_token=session_token,
                signature=signature,
                server=server,
                description="Configuration from environment variables",
                is_active=True
            )

            logger.info("Retrieved TradingView auth configuration from environment")
            return self._env_config_cache

        return None





    def get_account(self, account_name: Optional[str] = None) -> Optional[TradingViewAccount]:
        """
        Get account configuration.

        Args:
            account_name: Account name (None for default)

        Returns:
            TradingViewAccount: Found configuration. Priority: Env > Explicit Name > Default
        """
        

        cookies = rookiepy.brave(['.tradingview.com'])
        if cookies:
            # Map cookies to your class fields
            session_token = next((c['value'] for c in cookies if c['name'] == 'sessionid'), "")
            # TradingView signatures usually start with 'v3:'
            signature = next((c['value'] for c in cookies if c['name'] == 'sessionid_sign'), "")
            
            tv_acct= TradingViewAccount(
                name=account_name,
                session_token=session_token,
                signature=signature,
                created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
            
            self._env_config_cache =tv_acct



        # 1. Environment variable priority
        env_config = self._get_env_config()
        if env_config:
            env_config.update_last_used()
            return env_config

        # 2. Check config file
        if not self.auth_config or not self.auth_config.accounts:
            logger.warning("No TradingView account configurations available")
            return None

        # 3. Find specific account
        if account_name:
            for account in self.auth_config.accounts:
                if account.name == account_name and account.is_active:
                    account.update_last_used()
                    return account

            logger.warning(f"Specified account not found: {account_name}")
            return None

        # 4. Use default account
        if self.auth_config.default_account:
            for account in self.auth_config.accounts:
                if account.name == self.auth_config.default_account and account.is_active:
                    account.update_last_used()
                    return account

        # 5. Fallback to first active account
        for account in self.auth_config.accounts:
            if account.is_active:
                account.update_last_used()
                return account

        logger.warning("No active accounts found")
        return None

    def add_account(self, account: TradingViewAccount, set_as_default: bool = False) -> bool:
        """
        Add a new account configuration.

        Args:
            account: Account config
            set_as_default: Whether to make this the default

        Returns:
            bool: Success or failure
        """
        try:
            # Check for uniqueness
            for existing_account in self.auth_config.accounts:
                if existing_account.name == account.name:
                    logger.warning(f"Account name already exists: {account.name}")
                    return False

            # Add account
            self.auth_config.accounts.append(account)

            # Set default
            if set_as_default or not self.auth_config.default_account:
                self.auth_config.default_account = account.name

            # Save
            self._save_config()

            logger.info(f"Added TradingView account: {account.name}")
            return True

        except Exception as e:
            logger.error(f"Failed to add account: {e}")
            return False

    def update_account(self, account_name: str, **updates) -> bool:
        """
        Update an existing account configuration.

        Args:
            account_name: Name of the account
            **updates: Fields to update

        Returns:
            bool: Success or failure
        """
        try:
            for account in self.auth_config.accounts:
                if account.name == account_name:
                    for key, value in updates.items():
                        if hasattr(account, key):
                            setattr(account, key, value)
                        else:
                            logger.warning(f"Unknown account field: {key}")

                    self._save_config()
                    logger.info(f"Updated account: {account_name}")
                    return True

            logger.warning(f"Account not found: {account_name}")
            return False

        except Exception as e:
            logger.error(f"Failed to update account: {e}")
            return False

    def remove_account(self, account_name: str) -> bool:
        """
        Remove an account configuration.

        Args:
            account_name: Name of the account

        Returns:
            bool: Success or failure
        """
        try:
            for i, account in enumerate(self.auth_config.accounts):
                if account.name == account_name:
                    del self.auth_config.accounts[i]

                    # Handle default account removal
                    if self.auth_config.default_account == account_name:
                        if self.auth_config.accounts:
                            self.auth_config.default_account = self.auth_config.accounts[0].name
                        else:
                            self.auth_config.default_account = None

                    self._save_config()
                    logger.info(f"Removed account: {account_name}")
                    return True

            logger.warning(f"Account not found: {account_name}")
            return False

        except Exception as e:
            logger.error(f"Failed to remove account: {e}")
            return False

    def list_accounts(self) -> List[Dict[str, Any]]:
        """
        List all account configurations.

        Returns:
            List[Dict]: List of account summaries
        """
        accounts_info = []

        # Env config first
        env_config = self._get_env_config()
        if env_config:
            accounts_info.append({
                'name': env_config.name,
                'server': env_config.server,
                'description': env_config.description,
                'is_active': env_config.is_active,
                'source': 'environment',
                'is_default': True
            })

        # Config file accounts
        if self.auth_config:
            for account in self.auth_config.accounts:
                accounts_info.append({
                    'name': account.name,
                    'server': account.server,
                    'description': account.description,
                    'is_active': account.is_active,
                    'source': 'config_file',
                    'is_default': account.name == self.auth_config.default_account,
                    'created_at': account.created_at,
                    'last_used': account.last_used
                })

        return accounts_info

    def set_default_account(self, account_name: str) -> bool:
        """
        Set the default account.

        Args:
            account_name: Name of the account

        Returns:
            bool: Success or failure
        """
        try:
            for account in self.auth_config.accounts:
                if account.name == account_name:
                    self.auth_config.default_account = account_name
                    self._save_config()
                    logger.info(f"Set default account: {account_name}")
                    return True

            logger.warning(f"Account not found: {account_name}")
            return False

        except Exception as e:
            logger.error(f"Failed to set default account: {e}")
            return False

    def enable_encryption(self, password: Optional[str] = None) -> bool:
        """
        Enable configuration file encryption.

        Args:
            password: Password for encryption (None for default)

        Returns:
            bool: Success or failure
        """
        try:
            if password:
                self.encryption = ConfigEncryption(password)

            self.auth_config.encryption_enabled = True
            self._save_config()

            logger.info("Encryption enabled for config file")
            return True

        except Exception as e:
            logger.error(f"Failed to enable encryption: {e}")
            return False

    def disable_encryption(self) -> bool:
        """
        Disable configuration file encryption.

        Returns:
            bool: Success or failure
        """
        try:
            self.auth_config.encryption_enabled = False
            self._save_config()

            logger.info("Encryption disabled for config file")
            return True

        except Exception as e:
            logger.error(f"Failed to disable encryption: {e}")
            return False

    def validate_account(self, account: TradingViewAccount) -> bool:
        """
        Validate account configuration structure.

        Args:
            account: Account config

        Returns:
            bool: Validity
        """
        try:
            # Basic validation
            if not account.session_token or not account.signature:
                logger.error("Missing required authentication info")
                return False

            # Simple format check
            if len(account.session_token) < 10 or len(account.signature) < 10:
                logger.error("Invalid authentication info format")
                return False

            # Server check
            valid_servers = ['data', 'prodata', 'tradingview']
            if account.server not in valid_servers:
                logger.warning(f"Uncommon server selection: {account.server}")

            return True

        except Exception as e:
            logger.error(f"Account validation failed: {e}")
            return False


# Global singleton instance
_auth_manager: Optional[TradingViewAuthManager] = None


def get_auth_manager(config_file: Optional[str] = None,
                    encryption_password: Optional[str] = None) -> TradingViewAuthManager:
    """
    Retrieve the global singleton authentication manager.

    Args:
        config_file: Config file path
        encryption_password: Password for encryption

    Returns:
        TradingViewAuthManager instance
    """
    global _auth_manager

    if _auth_manager is None:
        _auth_manager = TradingViewAuthManager(config_file, encryption_password)

    return _auth_manager


def get_tradingview_auth(account_name: Optional[str] = None) -> Optional[Dict[str, str]]:
    """
    Helper function to get TradingView auth info.

    Args:
        account_name: Optional account name

    Returns:
        Dict: Auth info (token, signature, server)
    """
    auth_manager = get_auth_manager()
    account = auth_manager.get_account(account_name)

    if account:
        return {
            'token': account.session_token,
            'signature': account.signature,
            'server': account.server
        }

    return None


def get_tradingview_cookies(account_name: Optional[str] = None) -> Dict[str, str]:
    """
    Get session cookies as a dictionary.
    """
    auth = get_tradingview_auth(account_name)
    if auth:
        return {
            'sessionid': auth['token'],
            'sessionid_sign': auth['signature']
        }
    return {}


def get_tradingview_cookie_jar(account_name: Optional[str] = None):
    """
    Get session cookies as a CookieJar.
    """
    try:
        import rookiepy
        # Try to get full cookie jar from Brave if available
        raw_cookies = rookiepy.brave(['.tradingview.com'])
        if raw_cookies:
            # Check if our current account session matches what's in Brave
            # If so, return the full jar for better compatibility
            auth = get_tradingview_auth(account_name)
            session_id = next((c['value'] for c in raw_cookies if c['name'] == 'sessionid'), "")
            if auth and auth['token'] == session_id:
                return rookiepy.to_cookiejar(raw_cookies)

        # Fallback: Construct jar from auth info
        import http.cookiejar
        jar = http.cookiejar.CookieJar()
        auth = get_tradingview_auth(account_name)
        if auth:
            for name, value in [('sessionid', auth['token']), ('sessionid_sign', auth['signature'])]:
                cookie = http.cookiejar.Cookie(
                    version=0, name=name, value=value,
                    port=None, port_specified=False,
                    domain='.tradingview.com', domain_specified=True, domain_initial_dot=True,
                    path='/', path_specified=True,
                    secure=True, expires=None, discard=True,
                    comment=None, comment_url=None, rest={'HttpOnly': None}, rfc2109=False
                )
                jar.set_cookie(cookie)
            return jar
    except Exception as e:
        logger.warning(f"Failed to get cookie jar: {e}")

    return None


def create_account_from_env() -> Optional[TradingViewAccount]:
    """Helper to create account configuration from current environment variables."""
    session_token = os.getenv('TV_SESSION')
    signature = os.getenv('TV_SIGNATURE')

    if session_token and signature:
        return TradingViewAccount(
            name=input("Enter account name: ").strip() or "default",
            session_token=session_token,
            signature=signature,
            server=os.getenv('TV_SERVER', 'data'),
            description=input("Enter account description (optional): ").strip() or "Created from environment variables"
        )

    return None
