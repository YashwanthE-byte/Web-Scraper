"""
utils/proxy_manager.py
----------------------
Manages rotating proxies (Webshare rotating backbone or custom proxy list)
for both requests-based and Playwright-based web scraping.
"""

import itertools
import random
from typing import Optional, Dict, Any, List
import requests

from config import (
    USE_PROXIES,
    WEBSHARE_USERNAME,
    WEBSHARE_PASSWORD,
    WEBSHARE_GATEWAY,
    WEBSHARE_PORT,
    WEBSHARE_MODE,
    CUSTOM_PROXIES,
    REQUEST_TIMEOUT_SECONDS,
)
from utils.logger import setup_logger

logger = setup_logger("proxy_manager")


class ProxyManager:
    """
    Handles proxy formatting, rotation, and diagnostic testing for scrapers.
    """

    def __init__(
        self,
        use_proxies: bool = USE_PROXIES,
        username: str = WEBSHARE_USERNAME,
        password: str = WEBSHARE_PASSWORD,
        gateway: str = WEBSHARE_GATEWAY,
        port: int = WEBSHARE_PORT,
        mode: str = WEBSHARE_MODE,
        custom_proxies: Optional[List[str]] = None,
    ):
        self.use_proxies = use_proxies
        self.username = username
        self.password = password
        self.gateway = gateway
        self.port = port
        self.mode = mode.lower()
        self.custom_proxies = custom_proxies or CUSTOM_PROXIES

        self._custom_cycle = (
            itertools.cycle(self.custom_proxies) if self.custom_proxies else None
        )

    def is_enabled(self) -> bool:
        """Returns True if proxy usage is enabled and credentials/proxies are set."""
        if not self.use_proxies:
            return False
        return bool(self.username and self.password) or bool(self.custom_proxies)

    def get_webshare_auth_user(self) -> str:
        """
        Formats Webshare username.
        For rotating mode, Webshare expects '<username>-rotate'.
        For direct mode, it uses '<username>'.
        """
        if self.mode == "rotating" and not self.username.endswith("-rotate"):
            return f"{self.username}-rotate"
        return self.username

    def get_requests_proxies(self) -> Optional[Dict[str, str]]:
        """
        Returns a dictionary suitable for requests.Session or requests.get(..., proxies=...).
        Example: {"http": "http://user:pass@p.webshare.io:80", "https": "http://user:pass@p.webshare.io:80"}
        """
        if not self.is_enabled():
            return None

        # 1. Webshare gateway
        if self.username and self.password:
            auth_user = self.get_webshare_auth_user()
            proxy_url = f"http://{auth_user}:{self.password}@{self.gateway}:{self.port}"
            return {"http": proxy_url, "https": proxy_url}

        # 2. Custom proxy pool fallback
        if self._custom_cycle:
            proxy = next(self._custom_cycle)
            if not proxy.startswith("http://") and not proxy.startswith("https://"):
                proxy = f"http://{proxy}"
            return {"http": proxy, "https": proxy}

        return None

    def get_playwright_proxy(self) -> Optional[Dict[str, str]]:
        """
        Returns a dictionary formatted for Playwright browser.new_context(proxy=...).
        Example: {"server": "http://p.webshare.io:80", "username": "...", "password": "..."}
        """
        if not self.is_enabled():
            return None

        if self.username and self.password:
            auth_user = self.get_webshare_auth_user()
            return {
                "server": f"http://{self.gateway}:{self.port}",
                "username": auth_user,
                "password": self.password,
            }

        if self._custom_cycle:
            proxy = next(self._custom_cycle)
            # format http://[user:pass@]host:port
            return {"server": proxy}

        return None

    def test_connection(self) -> Dict[str, Any]:
        """
        Tests current proxy connection and returns the outgoing IP address.
        """
        test_url = "https://httpbin.org/ip"
        proxies = self.get_requests_proxies()

        logger.info("Testing proxy connection...")
        try:
            response = requests.get(
                test_url,
                proxies=proxies,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            origin_ip = data.get("origin", "Unknown")
            logger.info(f"Proxy test SUCCESSFUL! Outgoing IP: {origin_ip}")
            return {
                "success": True,
                "ip": origin_ip,
                "proxies_used": bool(proxies),
                "gateway": f"{self.gateway}:{self.port}" if self.username else "custom",
            }
        except Exception as err:
            logger.error(f"Proxy test FAILED: {err}")
            return {
                "success": False,
                "error": str(err),
                "proxies_used": bool(proxies),
            }


# Singleton instance for general use
proxy_manager = ProxyManager()
