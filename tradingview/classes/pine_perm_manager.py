"""
Pine Permission Manager Module
"""
import aiohttp
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from ..utils import gen_auth_cookies

class PinePermManager:
    """
    Class for managing Pine Script indicator permissions.
    """
    def __init__(self, session_id: str, signature: str, pine_id: str):
        """
        Initialize Pine permission manager.

        Args:
            session_id: SessionID
            signature: Signature
            pine_id: Pine indicator ID
        """
        if not session_id:
            raise ValueError("Please provide session ID")
        if not signature:
            raise ValueError("Please provide signature")
        if not pine_id:
            raise ValueError("Please provide Pine ID")

        self.session_id = session_id
        self.signature = signature
        self.pine_id = pine_id

    async def get_users(self, limit: int = 10, order: str = '-created') -> List[Dict[str, Any]]:
        """
        Get list of authorized users.

        Args:
            limit: Limit of records to fetch
            order: Sorting order

        Returns:
            List[Dict]: User list
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                f"https://www.tradingview.com/pine_perm/list_users/?limit={limit}&order_by={order}",
                data=f"pine_id={self.pine_id.replace(';', '%3B')}",
                headers={
                    "origin": "https://www.tradingview.com",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "cookie": gen_auth_cookies(self.session_id, self.signature)
                }
            ) as resp:
                if resp.status >= 400:
                    error_data = await resp.json()
                    raise ValueError(error_data.get('detail', 'Invalid credentials or Pine ID'))

                data = await resp.json()
                return data.get('results', [])

    async def add_user(self, username: str, expiration: Optional[datetime] = None) -> str:
        """
        Add an authorized user.

        Args:
            username: Username to add
            expiration: Expiration date

        Returns:
            str: Status
        """
        data = f"pine_id={self.pine_id.replace(';', '%3B')}&username_recip={username}"
        if expiration:
            data += f"&expiration={expiration.isoformat()}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://www.tradingview.com/pine_perm/add/",
                data=data,
                headers={
                    "origin": "https://www.tradingview.com",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "cookie": gen_auth_cookies(self.session_id, self.signature)
                }
            ) as resp:
                if resp.status >= 400:
                    error_data = await resp.json()
                    raise ValueError(error_data.get('detail', 'Invalid credentials or Pine ID'))

                data = await resp.json()
                return data.get('status', None)

    async def modify_expiration(self, username: str, expiration: Optional[datetime] = None) -> str:
        """
        Modify authorization expiration.

        Args:
            username: Username
            expiration: New expiration date

        Returns:
            str: Status
        """
        data = f"pine_id={self.pine_id.replace(';', '%3B')}&username_recip={username}"
        if expiration:
            data += f"&expiration={expiration.isoformat()}"

        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://www.tradingview.com/pine_perm/modify_user_expiration/",
                data=data,
                headers={
                    "origin": "https://www.tradingview.com",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "cookie": gen_auth_cookies(self.session_id, self.signature)
                }
            ) as resp:
                if resp.status >= 400:
                    error_data = await resp.json()
                    raise ValueError(error_data.get('detail', 'Invalid credentials or Pine ID'))

                data = await resp.json()
                return data.get('status', None)

    async def remove_user(self, username: str) -> str:
        """
        Remove an authorized user.

        Args:
            username: Username to remove

        Returns:
            str: Status
        """
        async with aiohttp.ClientSession() as session:
            async with session.post(
                "https://www.tradingview.com/pine_perm/remove/",
                data=f"pine_id={self.pine_id.replace(';', '%3B')}&username_recip={username}",
                headers={
                    "origin": "https://www.tradingview.com",
                    "Content-Type": "application/x-www-form-urlencoded",
                    "cookie": gen_auth_cookies(self.session_id, self.signature)
                }
            ) as resp:
                if resp.status >= 400:
                    error_data = await resp.json()
                    raise ValueError(error_data.get('detail', 'Invalid credentials or Pine ID'))

                data = await resp.json()
                return data.get('status', None)
