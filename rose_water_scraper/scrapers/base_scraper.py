"""
scrapers/base_scraper.py
------------------------
Defines the abstract BaseScraper class.
Implements common infrastructure shared across all scrapers:
- urllib.robotparser checking for robots.txt compliance
- Politeness random delays (3 to 6 seconds)
- Retry mechanism with exponential backoff
- CAPTCHA / Block detection (403, 429, block keywords)
- Common interface: fetch_page(), parse_listings(), run()
"""

import time
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from urllib.robotparser import RobotFileParser
from urllib.parse import urlparse

import requests
from config import (
    USER_AGENT,
    DEFAULT_HEADERS,
    MIN_DELAY_SECONDS,
    MAX_DELAY_SECONDS,
    MAX_RETRIES,
    BACKOFF_FACTOR,
    REQUEST_TIMEOUT_SECONDS,
    BLOCKED_STATUS_CODES,
    BLOCKED_KEYWORDS,
)
from utils.logger import setup_logger
from utils.proxy_manager import proxy_manager, ProxyManager

class BaseScraper(ABC):
    """
    Abstract Base Class for website scrapers.
    All site-specific scrapers inherit from BaseScraper and implement abstract methods.
    """

    def __init__(self, site_name: str, base_url: str, robots_url: str, user_agent: str = USER_AGENT):
        """
        Initializes the base scraper with target site configurations and sets up logger & HTTP session.
        
        Args:
            site_name (str): Friendly name of the target site (e.g., 'ExportersIndia').
            base_url (str): Base domain URL.
            robots_url (str): URL to the site's robots.txt file.
            user_agent (str): User-Agent header string.
        """
        self.site_name = site_name
        self.base_url = base_url
        self.robots_url = robots_url
        self.user_agent = user_agent
        self.logger = setup_logger(self.site_name.lower())
        self.proxy_manager = proxy_manager
        
        # Configure requests Session
        self.session = requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        if self.proxy_manager.is_enabled():
            self.logger.info(
                f"Proxy rotation ENABLED for {self.site_name} (Mode: {self.proxy_manager.mode}, Gateway: {self.proxy_manager.gateway})"
            )
        
        # Robot File Parser setup
        self.robot_parser = RobotFileParser()
        self._init_robots_txt()


    def _init_robots_txt(self) -> None:
        """
        Fetches and parses robots.txt to respect site scraping policies.
        If robots.txt cannot be fetched or parsed, logs a warning and proceeds with caution.
        """
        try:
            self.logger.info(f"Checking robots.txt for {self.site_name} at {self.robots_url}...")
            self.robot_parser.set_url(self.robots_url)
            self.robot_parser.read()
        except Exception as err:
            self.logger.warning(
                f"Could not fetch or parse robots.txt for {self.site_name} ({err}). "
                "Will continue scraping while adhering to delay guidelines."
            )

    def is_allowed_by_robots(self, target_url: str) -> bool:
        """
        Checks whether scraping target_url is allowed for our User-Agent by robots.txt.
        
        Args:
            target_url (str): Full URL to check.
            
        Returns:
            bool: True if allowed or if robots parsing is inconclusive, False if explicitly disallowed.
        """
        try:
            allowed = self.robot_parser.can_fetch(self.user_agent, target_url)
            if not allowed:
                self.logger.warning(f"ROBOTS.TXT DISALLOWED: Access to {target_url} is blocked by robots.txt rules.")
            return allowed
        except Exception as err:
            self.logger.debug(f"Error checking robots.txt rules for {target_url}: {err}")
            return True

    def apply_politeness_delay(self) -> None:
        """
        Executes a randomized politeness delay between requests (3.0 to 6.0 seconds)
        to prevent overwhelming target servers.
        """
        delay = random.uniform(MIN_DELAY_SECONDS, MAX_DELAY_SECONDS)
        self.logger.debug(f"Politeness delay: sleeping for {delay:.2f} seconds...")
        time.sleep(delay)

    def is_blocked_response(self, status_code: int, response_text: str) -> bool:
        """
        Checks if the response indicates IP blocking, rate limiting, or CAPTCHA challenge.
        
        Args:
            status_code (int): HTTP status code.
            response_text (str): HTML body content of the response.
            
        Returns:
            bool: True if blocked or CAPTCHA detected, False otherwise.
        """
        # 1. Check HTTP Status Code
        if status_code in BLOCKED_STATUS_CODES:
            self.logger.error(
                f"BLOCK DETECTED! Received HTTP Status {status_code} (Rate Limited or Blocked) from {self.site_name}."
            )
            return True

        # 2. Check HTML body for block signatures
        text_lower = response_text.lower()
        for keyword in BLOCKED_KEYWORDS:
            if keyword in text_lower:
                self.logger.error(
                    f"BLOCK/CAPTCHA DETECTED! Found block keyword '{keyword}' in page response from {self.site_name}."
                )
                return True

        return False

    def fetch_with_retry(self, url: str) -> Optional[Any]:
        """
        Fetches a URL over HTTP using curl_cffi (Chrome TLS fingerprint) with retry mechanism
        (up to 3 retries with exponential backoff).
        Includes robots.txt verification and CAPTCHA detection.
        """
        if not self.is_allowed_by_robots(url):
            self.logger.warning(f"Skipping disallowed path: {url}")
            return None

        self.apply_politeness_delay()

        try:
            from curl_cffi import requests as curl_requests
        except ImportError:
            curl_requests = None

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                self.logger.info(f"Fetching URL (Attempt {attempt}/{MAX_RETRIES}): {url}")
                proxies = self.proxy_manager.get_requests_proxies()

                if curl_requests:
                    response = curl_requests.get(
                        url,
                        impersonate="chrome124",
                        headers=DEFAULT_HEADERS,
                        proxies=proxies,
                        timeout=REQUEST_TIMEOUT_SECONDS
                    )
                else:
                    response = self.session.get(url, proxies=proxies, timeout=REQUEST_TIMEOUT_SECONDS)

                # Check for rate limiting / block page
                if self.is_blocked_response(response.status_code, response.text):
                    self.logger.warning(
                        f"Received status {response.status_code} on attempt {attempt}/{MAX_RETRIES}. Will retry with rotating proxy if attempts remain."
                    )
                    if attempt < MAX_RETRIES:
                        sleep_time = BACKOFF_FACTOR ** attempt
                        time.sleep(sleep_time)
                        continue
                    else:
                        return None

                response.raise_for_status()
                return response

            except Exception as err:
                self.logger.error(f"HTTP request error on attempt {attempt}/{MAX_RETRIES} for {url}: {err}")
                if attempt < MAX_RETRIES:
                    sleep_time = BACKOFF_FACTOR ** attempt
                    self.logger.info(f"Waiting {sleep_time} seconds before retrying...")
                    time.sleep(sleep_time)

        self.logger.error(f"Failed to fetch {url} after {MAX_RETRIES} attempts.")
        return None

    @abstractmethod
    def fetch_page(self, page_num: int) -> Optional[Any]:
        """
        Abstract method: Fetches raw content (HTML or JSON) for a specific search page.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def parse_listings(self, page_content: Any) -> List[Dict[str, Any]]:
        """
        Abstract method: Extracts individual product item dictionaries from page content.
        Must be implemented by subclasses.
        """
        pass

    @abstractmethod
    def run(self, query: str = "rose water", max_pages: int = 3) -> List[Dict[str, Any]]:
        """
        Abstract method: Executes full multi-page scraping workflow.
        Must be implemented by subclasses.
        """
        pass
