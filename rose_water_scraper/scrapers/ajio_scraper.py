"""
scrapers/ajio_scraper.py
-------------------------
Implementation of the Ajio web scraper.
Fetches catalog items via Ajio's search JSON API using curl_cffi/requests,
and enriches brand contacts (Website, Email, Phone, LinkedIn, HQ Location) via OSINT web lookup.
"""

from typing import List, Dict, Any, Optional
from urllib.parse import quote, urljoin
from bs4 import BeautifulSoup

from config import (
    AJIO_CONFIG,
    DEFAULT_QUERY,
    DEFAULT_MAX_PAGES,
    ENRICH_CONTACT_DETAILS,
    USER_AGENT,
    MAX_RETRIES,
    BACKOFF_FACTOR,
)
from utils.enricher import lead_enricher
from scrapers.base_scraper import BaseScraper


class AjioScraper(BaseScraper):
    """
    Scraper for Ajio (https://www.ajio.com).
    Fetches catalog items via Ajio's search JSON API using curl_cffi with proxy support.
    """

    def __init__(self):
        super().__init__(
            site_name=AJIO_CONFIG["site_name"],
            base_url=AJIO_CONFIG["base_url"],
            robots_url=AJIO_CONFIG["robots_url"]
        )
        self.config = AJIO_CONFIG
        self.selectors = self.config.get("selectors", {})

    def build_api_url(self, query: str, page_num: int, page_size: int = 45) -> str:
        """
        Constructs the search JSON API URL for Ajio.
        Page indexing is 0-based for Ajio API.
        """
        encoded_query = quote(query.lower().strip())
        current_page = max(0, page_num - 1)
        return (
            f"{self.base_url}/api/search?fields=DEFAULT"
            f"&currentPage={current_page}&pageSize={page_size}&format=json&query={encoded_query}"
        )

    def fetch_api_page(self, page_num: int, query: str = DEFAULT_QUERY) -> Optional[Dict[str, Any]]:
        """
        Fetches search results from Ajio's JSON API using curl_cffi to bypass Akamai Bot Manager.
        """
        url = self.build_api_url(query, page_num)
        self.logger.info(f"Fetching Ajio API page {page_num} for '{query}': {url}")

        self.apply_politeness_delay()

        try:
            # pyrefly: ignore [missing-import]
            from curl_cffi import requests as curl_requests
        except ImportError:
            self.logger.warning("curl_cffi not available, falling back to standard requests session.")
            curl_requests = None

        proxies = self.proxy_manager.get_requests_proxies()
        api_headers = {
            "User-Agent": USER_AGENT,
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://www.ajio.com/",
            "Accept-Language": "en-US,en;q=0.9",
        }

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                if curl_requests:
                    resp = curl_requests.get(
                        url,
                        impersonate="chrome124",
                        headers=api_headers,
                        proxies=proxies,
                        timeout=25
                    )
                else:
                    resp = self.session.get(url, headers=api_headers, proxies=proxies, timeout=25)

                if resp.status_code == 200:
                    data = resp.json()
                    return data
                elif resp.status_code in (403, 429):
                    self.logger.warning(
                        f"Ajio API returned status {resp.status_code} on attempt {attempt}/{MAX_RETRIES}."
                    )
                else:
                    self.logger.warning(
                        f"Ajio API returned status {resp.status_code} for URL: {url}"
                    )

            except Exception as err:
                self.logger.error(f"Error fetching Ajio API on attempt {attempt}/{MAX_RETRIES}: {err}")

            if attempt < MAX_RETRIES:
                import time
                sleep_time = BACKOFF_FACTOR ** attempt
                time.sleep(sleep_time)

        return None

    def fetch_page(self, page_num: int, query: str = DEFAULT_QUERY) -> Optional[Any]:
        """
        Implements BaseScraper abstract method. Fetches page data as parsed JSON or HTML.
        """
        return self.fetch_api_page(page_num, query=query)

    def parse_listings(
        self,
        page_content: Any,
        category: str = "General",
        keyword: str = DEFAULT_QUERY
    ) -> List[Dict[str, Any]]:
        """
        Parses JSON response or HTML content from Ajio and extracts standard listing items.
        """
        listings: List[Dict[str, Any]] = []
        if not page_content:
            return listings

        # 1. If page_content is parsed JSON dict
        if isinstance(page_content, dict):
            products = page_content.get("products", [])
            self.logger.info(f"Parsed {len(products)} products from Ajio API.")

            for p in products:
                try:
                    product_name = p.get("name", "").strip()
                    if not product_name:
                        continue

                    # Brand extraction
                    brand_data = p.get("fnlColorVariantData", {})
                    brand_name = (
                        brand_data.get("brandName")
                        or p.get("brandName")
                        or p.get("brandTypeName")
                        or "Ajio Seller"
                    ).strip()

                    # Price extraction
                    price_obj = p.get("price", {})
                    price_val = price_obj.get("displayformattedValue") or price_obj.get("formattedValue") or ""

                    # MRP (Was Price)
                    was_price_obj = p.get("wasPriceData", {})
                    mrp_val = was_price_obj.get("displayformattedValue") or was_price_obj.get("formattedValue") or "N/A"

                    # Discount
                    discount_val = p.get("discountPercent") or "N/A"

                    # URL
                    rel_url = p.get("url", "")
                    full_url = urljoin(self.base_url, rel_url) if rel_url else ""

                    item = {
                        "Brand Name": brand_name,
                        "Company Name": brand_name,
                        "Product Category": category,
                        "Keyword": keyword,
                        "Product Name": product_name,
                        "Product URL": full_url,
                        "Seller/Brand Website": "",
                        "Contact Email": "",
                        "Phone Number": "",
                        "LinkedIn": "",
                        "City & State": "India",
                        "Marketplace": self.site_name,
                        "Price": price_val if price_val else "N/A",
                        "MRP": mrp_val if mrp_val else "N/A",
                        "Discount": discount_val if discount_val else "N/A",
                    }
                    listings.append(item)

                except Exception as err:
                    self.logger.debug(f"Error parsing Ajio product item: {err}")
                    continue

            return listings

        # 2. If page_content is raw HTML (fallback)
        try:
            soup = BeautifulSoup(page_content, "html.parser")
            cards = soup.select("div.item.rilrtl-products-list__item, div.preview, .rilrtl-products-list__item")
            for card in cards:
                brand_elem = card.select_one(".brand, div.brand")
                name_elem = card.select_one(".name, .name-cls, div.name")
                link_elem = card.select_one("a.rilrtl-products-list__link, a")
                price_elem = card.select_one(".price, span.price")
                mrp_elem = card.select_one(".orginal-price, .prod-cp")
                disc_elem = card.select_one(".discount, span.discount")

                p_name = name_elem.get_text(strip=True) if name_elem else ""
                if not p_name:
                    continue

                b_name = brand_elem.get_text(strip=True) if brand_elem else "Ajio Seller"

                item = {
                    "Brand Name": b_name,
                    "Company Name": b_name,
                    "Product Category": category,
                    "Keyword": keyword,
                    "Product Name": p_name,
                    "Product URL": urljoin(self.base_url, link_elem.get("href", "")) if link_elem else "",
                    "Seller/Brand Website": "",
                    "Contact Email": "",
                    "Phone Number": "",
                    "LinkedIn": "",
                    "City & State": "India",
                    "Marketplace": self.site_name,
                    "Price": price_elem.get_text(strip=True) if price_elem else "N/A",
                    "MRP": mrp_elem.get_text(strip=True) if mrp_elem else "N/A",
                    "Discount": disc_elem.get_text(strip=True) if disc_elem else "N/A",
                }
                listings.append(item)
        except Exception as err:
            self.logger.error(f"Error parsing HTML fallback for Ajio: {err}")

        return listings

    def enrich_listing(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enriches brand contact details (Official Website, Email, Phone, LinkedIn, HQ Location)
        using the LeadEnricher module.
        """
        brand = item.get("Brand Name", "")
        company = item.get("Company Name", "")

        enriched = lead_enricher.enrich(brand_name=brand, company_name=company)

        if enriched.get("website"):
            item["Seller/Brand Website"] = enriched["website"]

        if enriched.get("email"):
            item["Contact Email"] = enriched["email"]

        if enriched.get("phone"):
            item["Phone Number"] = enriched["phone"]

        if enriched.get("linkedin"):
            item["LinkedIn"] = enriched["linkedin"]

        if enriched.get("city_state"):
            item["City & State"] = enriched["city_state"]

        return item

    def run(
        self,
        query: str = DEFAULT_QUERY,
        category: str = "General",
        max_pages: int = DEFAULT_MAX_PAGES,
        enrich_details: bool = ENRICH_CONTACT_DETAILS
    ) -> List[Dict[str, Any]]:
        """
        Executes scraping pipeline across multiple Ajio pages with optional brand enrichment.
        """
        all_results: List[Dict[str, Any]] = []
        self.logger.info(
            f"Starting {self.site_name} scraper | Category: '{category}' | Query: '{query}' | Max Pages: {max_pages}"
        )

        for page in range(1, max_pages + 1):
            self.logger.info(f"--- Scraping {self.site_name} Page {page}/{max_pages} for '{query}' ---")
            data = self.fetch_page(page, query=query)
            if not data:
                self.logger.warning(f"No content returned for Ajio page {page}. Stopping pagination.")
                break

            items = self.parse_listings(data, category=category, keyword=query)
            self.logger.info(f"Extracted {len(items)} items from Ajio page {page}.")
            if not items:
                self.logger.info("No more items found on Ajio. Stopping pagination.")
                break

            if enrich_details:
                self.logger.info(f"Enriching brand contact info & LinkedIn on {len(items)} items in parallel...")
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=5) as executor:
                    items = list(executor.map(self.enrich_listing, items))

            all_results.extend(items)

            if isinstance(data, dict):
                pagination = data.get("pagination", {})
                total_pages = pagination.get("totalPages", 1)
                current_p = pagination.get("currentPage", 0)
                if current_p + 1 >= total_pages:
                    self.logger.info(f"Reached final page ({total_pages}) reported by Ajio API.")
                    break

        self.logger.info(f"Finished {self.site_name} scraping for '{query}'. Total items: {len(all_results)}")
        return all_results
