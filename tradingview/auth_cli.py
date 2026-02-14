#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
TradingView Account Configuration Management CLI Tool
Provides a command line interface to manage TradingView authentication configurations.
"""

import argparse
import sys
import os
import json
from pathlib import Path
from typing import Optional
import getpass
from datetime import datetime

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tradingview.auth_config import (
    TradingViewAuthManager,
    TradingViewAccount,
    get_auth_manager,
    create_account_from_env
)
from tradingview.utils import get_logger

logger = get_logger(__name__)


class AuthCLI:
    """Authentication Configuration CLI Manager"""

    def __init__(self, config_file: Optional[str] = None):
        self.auth_manager = get_auth_manager(config_file)

    def cmd_list(self, args):
        """List all account configurations"""
        print("📋 TradingView Account Configurations")
        print("=" * 60)

        accounts = self.auth_manager.list_accounts()

        if not accounts:
            print("❌ No account configurations found")
            print("\n💡 Hint:")
            print("   1. Set environment variables: export TV_SESSION=xxx TV_SIGNATURE=xxx")
            print("   2. Or use command to add config: python auth_cli.py add")
            return

        # Display account info
        for i, account in enumerate(accounts, 1):
            status_icon = "🟢" if account['is_active'] else "🔴"
            default_icon = "⭐" if account['is_default'] else "  "
            source_icon = "🌍" if account['source'] == 'environment' else "📁"

            print(f"{i:2d}. {default_icon} {status_icon} {source_icon} {account['name']}")
            print(f"     Server: {account['server']}")
            print(f"     Source: {'Environment Variable' if account['source'] == 'environment' else 'Configuration File'}")

            if account['description']:
                print(f"     Description: {account['description']}")

            if account.get('created_at'):
                created_time = datetime.fromisoformat(account['created_at']).strftime('%Y-%m-%d %H:%M')
                print(f"     Created: {created_time}")

            if account.get('last_used'):
                used_time = datetime.fromisoformat(account['last_used']).strftime('%Y-%m-%d %H:%M')
                print(f"     Last Used: {used_time}")

            print()

        print("Legend: ⭐=Default 🟢=Active 🔴=Disabled 🌍=Environment 📁=Config File")

    def cmd_add(self, args):
        """Add account configuration"""
        print("✨ Add TradingView Account Configuration")
        print("=" * 40)

        # Check if creating from environment
        if args.from_env:
            account = create_account_from_env()
            if not account:
                print("❌ TV_SESSION and TV_SIGNATURE not found in environment variables")
                print("Please set them first:")
                print("   export TV_SESSION='your_session_token'")
                print("   export TV_SIGNATURE='your_signature'")
                return
        else:
            # Manual input
            print("Please enter account information:")

            name = input("Account Name: ").strip()
            if not name:
                print("❌ Account name cannot be empty")
                return

            session_token = getpass.getpass("Session Token (TV_SESSION): ").strip()
            if not session_token:
                print("❌ Session Token cannot be empty")
                return

            signature = getpass.getpass("Signature (TV_SIGNATURE): ").strip()
            if not signature:
                print("❌ Signature cannot be empty")
                return

            server = input("Server [data]: ").strip() or "data"
            description = input("Description (Optional): ").strip()

            account = TradingViewAccount(
                name=name,
                session_token=session_token,
                signature=signature,
                server=server,
                description=description
            )

        # Validate account config
        if not self.auth_manager.validate_account(account):
            print("❌ Account configuration validation failed")
            return

        # Add account
        set_as_default = args.set_default or input("Set as default account? [y/N]: ").lower() == 'y'

        if self.auth_manager.add_account(account, set_as_default):
            print(f"✅ Successfully added account: {account.name}")
            if set_as_default:
                print("⭐ Set as default account")
        else:
            print("❌ Failed to add account")

    def cmd_remove(self, args):
        """Remove account configuration"""
        account_name = args.name

        # Confirm deletion
        if not args.force:
            confirm = input(f"Confirm deletion of account '{account_name}'? [y/N]: ").lower()
            if confirm != 'y':
                print("Operation cancelled")
                return

        if self.auth_manager.remove_account(account_name):
            print(f"✅ Successfully deleted account: {account_name}")
        else:
            print(f"❌ Failed to delete account: {account_name}")

    def cmd_update(self, args):
        """Update account configuration"""
        account_name = args.name
        updates = {}

        # Collect update fields
        if args.server:
            updates['server'] = args.server

        if args.description is not None:
            updates['description'] = args.description

        if args.active is not None:
            updates['is_active'] = args.active

        if not updates:
            print("❌ No fields specified for update")
            return

        if self.auth_manager.update_account(account_name, **updates):
            print(f"✅ Successfully updated account: {account_name}")
            for key, value in updates.items():
                print(f"   {key}: {value}")
        else:
            print(f"❌ Failed to update account: {account_name}")

    def cmd_default(self, args):
        """Set default account"""
        account_name = args.name

        if self.auth_manager.set_default_account(account_name):
            print(f"✅ Default account set to: {account_name}")
        else:
            print(f"❌ Failed to set default account: {account_name}")

    def cmd_test(self, args):
        """Test account configuration"""
        account_name = args.name if hasattr(args, 'name') else None

        print(f"🧪 Testing account configuration: {account_name or 'default account'}")
        print("=" * 40)

        # Get account config
        account = self.auth_manager.get_account(account_name)

        if not account:
            print("❌ Specified account configuration not found")
            return

        print(f"📋 Account Information:")
        print(f"   Name: {account.name}")
        print(f"   Server: {account.server}")
        print(f"   Description: {account.description}")
        print(f"   Token Preview: {(account.session_token[:10])}... ")
        print(f"   Signature Preview: {(account.signature[:10])}... ")
        print(f"   Token Length: {len(account.session_token)} characters")
        print(f"   Signature Length: {len(account.signature)} characters")

        # Basic validation
        if self.auth_manager.validate_account(account):
            print("✅ Account configuration format validation passed")
        else:
            print("❌ Account configuration format validation failed")
            return

        # Connection test
        try:
            import asyncio
            from tradingview.client import Client

            async def test_connection():
                client = Client({
                    'token': account.session_token,
                    'signature': account.signature,
                    'server': account.server
                })

                try:
                    print("🔄 Testing connection...")
                    await client.connect()

                    if client.is_logged and client.is_open:
                        print("✅ Connection test successful")
                        return True
                    else:
                        print("❌ Connection test failed: Authentication failed")
                        return False

                except Exception as e:
                    print(f"❌ Connection test failed: {e}")
                    return False
                finally:
                    if client:
                        await client.end()

            # Run test
            success = asyncio.run(test_connection())

            if success:
                # Update last used
                account.update_last_used()
                print("📝 Last used time updated")

        except ImportError:
            print("⚠️  Unable to import TradingView client, skipping connection test")
        except Exception as e:
            print(f"❌ Connection test exception: {e}")

    def cmd_export(self, args):
        """Export account configurations"""
        accounts = self.auth_manager.list_accounts()

        # Filter out environment configs
        config_accounts = [acc for acc in accounts if account['source'] == 'config_file']

        if not config_accounts:
            print("❌ No config file accounts available for export")
            return

        export_data = {
            'accounts': config_accounts,
            'exported_at': datetime.now().isoformat(),
            'version': '1.0'
        }

        output_file = args.output or 'tradingview_accounts_export.json'

        try:
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, ensure_ascii=False, indent=2)

            print(f"✅ Configurations exported to: {output_file}")
            print(f"📊 Number of exported accounts: {len(config_accounts)}")

        except Exception as e:
            print(f"❌ Export failed: {e}")

    def cmd_import(self, args):
        """Import account configurations"""
        import_file = args.file

        if not os.path.exists(import_file):
            print(f"❌ Import file does not exist: {import_file}")
            return

        try:
            with open(import_file, 'r', encoding='utf-8') as f:
                import_data = json.load(f)

            accounts_data = import_data.get('accounts', [])
            if not accounts_data:
                print("❌ No account configurations found in import file")
                return

            print(f"📋 Preparing to import {len(accounts_data)} account configurations")

            imported_count = 0
            for acc_data in accounts_data:
                try:
                    # Remove runtime fields
                    clean_data = {
                        'name': acc_data['name'],
                        'server': acc_data['server'],
                        'description': acc_data['description'],
                        'is_active': acc_data['is_active']
                    }

                    # Need user input for sensitive info
                    print(f"\nImporting Account: {acc_data['name']}")
                    session_token = getpass.getpass("Session Token: ").strip()
                    signature = getpass.getpass("Signature: ").strip()

                    if not session_token or not signature:
                        print("Skipping account (missing authentication info)")
                        continue

                    account = TradingViewAccount(
                        session_token=session_token,
                        signature=signature,
                        **clean_data
                    )

                    if self.auth_manager.add_account(account):
                        imported_count += 1
                        print(f"✅ Successfully imported: {account.name}")
                    else:
                        print(f"❌ Failed to import: {account.name}")

                except Exception as e:
                    print(f"❌ Failed to import account: {e}")

            print(f"\n📊 Import complete, successfully imported {imported_count} accounts")

        except Exception as e:
            print(f"❌ Import failed: {e}")

    def cmd_encrypt(self, args):
        """Enable configuration encryption"""
        password = None

        if args.password:
            password = getpass.getpass("Enter encryption password: ")
            if not password:
                print("❌ Password cannot be empty")
                return

        if self.auth_manager.enable_encryption(password):
            print("✅ Configuration encryption enabled")
            if not password:
                print("💡 Using default encryption password (based on machine identifier)")
        else:
            print("❌ Failed to enable encryption")

    def cmd_decrypt(self, args):
        """Disable configuration encryption"""
        if not args.force:
            confirm = input("Confirm disabling configuration encryption? [y/N]: ").lower()
            if confirm != 'y':
                print("Operation cancelled")
                return

        if self.auth_manager.disable_encryption():
            print("✅ Configuration encryption disabled")
        else:
            print("❌ Failed to disable encryption")


def create_parser():
    """Create command line parser"""
    parser = argparse.ArgumentParser(
        description='TradingView Account Configuration Management CLI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example Usage:
  # List all account configurations
  python auth_cli.py list

  # Add account from environment variables
  python auth_cli.py add --from-env --set-default

  # Manually add an account
  python auth_cli.py add

  # Set default account
  python auth_cli.py default my_account

  # Test account connection
  python auth_cli.py test my_account

  # Update account information
  python auth_cli.py update my_account --server prodata --description "Production Account"

  # Remove an account
  python auth_cli.py remove my_account --force

  # Enable configuration encryption
  python auth_cli.py encrypt --password

  # Export configurations
  python auth_cli.py export --output my_accounts.json
        """
    )

    parser.add_argument(
        '-c', '--config',
        help='Configuration file path',
        default=None
    )

    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Available commands')

    # list command
    list_parser = subparsers.add_parser('list', help='List all account configurations')

    # add command
    add_parser = subparsers.add_parser('add', help='Add account configuration')
    add_parser.add_argument('--from-env', action='store_true', help='Create account from environment variables')
    add_parser.add_argument('--set-default', action='store_true', help='Set as default account')

    # remove command
    remove_parser = subparsers.add_parser('remove', help='Remove account configuration')
    remove_parser.add_argument('name', help='Account name')
    remove_parser.add_argument('--force', action='store_true', help='Force removal without confirmation')

    # update command
    update_parser = subparsers.add_parser('update', help='Update account configuration')
    update_parser.add_argument('name', help='Account name')
    update_parser.add_argument('--server', help='Server')
    update_parser.add_argument('--description', help='Description')
    update_parser.add_argument('--active', type=bool, help='Whether active')

    # default command
    default_parser = subparsers.add_parser('default', help='Set default account')
    default_parser.add_argument('name', help='Account name')

    # test command
    test_parser = subparsers.add_parser('test', help='Test account configuration')
    test_parser.add_argument('name', nargs='?', help='Account name (optional, defaults to default account)')

    # export command
    export_parser = subparsers.add_parser('export', help='Export account configurations')
    export_parser.add_argument('--output', help='Output file path')

    # import command
    import_parser = subparsers.add_parser('import', help='Import account configurations')
    import_parser.add_argument('file', help='Import file path')

    # encrypt command
    encrypt_parser = subparsers.add_parser('encrypt', help='Enable configuration encryption')
    encrypt_parser.add_argument('--password', action='store_true', help='Use custom password')

    # decrypt command
    decrypt_parser = subparsers.add_parser('decrypt', help='Disable configuration encryption')
    decrypt_parser.add_argument('--force', action='store_true', help='Force disablement without confirmation')

    return parser


def main():
    """Main function"""
    parser = create_parser()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        cli = AuthCLI(args.config)

        # Execute command
        command_method = getattr(cli, f'cmd_{args.command}', None)
        if command_method:
            command_method(args)
        else:
            print(f"Unknown command: {args.command}")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\nOperation interrupted by user")
        sys.exit(0)
    except Exception as e:
        logger.error(f"CLI execution failed: {e}")
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()