"""
scrapers/exportersindia_scraper.py
----------------------------------
Implementation of the ExportersIndia web scraper.
Fetches static HTML search pages, extracts product and supplier details using BeautifulSoup,
and enriches company contacts (phone, email, website, LinkedIn) via regex and OSINT search.
"""

from typing import List, Dict, Any, Optional
from urllib.parse import quote_plus, urljoin
from bs4 import BeautifulSoup

from config import (
    EXPORTERSINDIA_CONFIG,
    DEFAULT_QUERY,
    DEFAULT_MAX_PAGES,
    ENRICH_CONTACT_DETAILS,
)
from utils.cleaner import extract_phones, extract_emails
from utils.enricher import lead_enricher
from scrapers.base_scraper import BaseScraper


class ExportersIndiaScraper(BaseScraper):
    """
    Scraper for ExportersIndia (https://www.exportersindia.com).
    Uses requests Session + BeautifulSoup for fast and reliable static page scraping.
    """

    def __init__(self):
        super().__init__(
            site_name=EXPORTERSINDIA_CONFIG["site_name"],
            base_url=EXPORTERSINDIA_CONFIG["base_url"],
            robots_url=EXPORTERSINDIA_CONFIG["robots_url"]
        )
        self.config = EXPORTERSINDIA_CONFIG
        self.selectors = self.config["selectors"]

    def build_page_url(self, query: str, page_num: int) -> str:
        """
        Constructs the search URL for a given keyword and page number.
        """
        encoded_query = quote_plus(query)
        if page_num <= 1:
            template = self.config.get(
                "search_url_template",
                "https://www.exportersindia.com/search.php?srch_catg_ty=prod&term={query}&cont=IN&ss_status=N"
            )
            return template.format(query=encoded_query)
        else:
            template = self.config.get(
                "search_url_paged_template",
                "https://www.exportersindia.com/search.php?srch_catg_ty=prod&term={query}&cont=IN&ss_status=N&page={page}"
            )
            return template.format(query=encoded_query, page=page_num)

    def fetch_page(self, page_num: int, query: str = DEFAULT_QUERY) -> Optional[str]:
        """
        Fetches the HTML content for a specific search page.
        """
        url = self.build_page_url(query, page_num)
        self.logger.info(f"Fetching ExportersIndia page {page_num} for query '{query}': {url}")
        
        response = self.fetch_with_retry(url)
        if response and response.status_code == 200:
            return response.text
        return None

    def parse_listings(
        self,
        page_content: str,
        category: str = "General",
        keyword: str = DEFAULT_QUERY
    ) -> List[Dict[str, Any]]:
        """
        Parses HTML page content and extracts listing items into standard dictionaries.
        """
        listings: List[Dict[str, Any]] = []
        if not page_content:
            return listings

        try:
            soup = BeautifulSoup(page_content, "lxml")
        except Exception:
            soup = BeautifulSoup(page_content, "html.parser")

        # Find all listing cards
        card_selector = self.selectors.get("card", "div.l3Inn")
        cards = soup.select(card_selector)

        if not cards:
            cards = soup.select("div[id^='id_0_'], div.l3Inn, div.classified_details")

        self.logger.info(f"Found {len(cards)} listing cards on ExportersIndia page.")

        for card in cards:
            try:
                # 1. Product Title & URL
                product_elem = card.select_one(self.selectors.get("product", "h2 a.prdclk"))
                if not product_elem:
                    product_elem = card.select_one("h2 a, .inDataH h2 a, a.prdclk")

                product_name = ""
                product_url = ""
                if product_elem:
                    product_name = product_elem.get("title") or product_elem.get_text(strip=True)
                    href = product_elem.get("href", "").strip()
                    if href:
                        product_url = urljoin(self.base_url, href)

                if not product_name:
                    continue

                # 2. Company Name
                company_elem = card.select_one(self.selectors.get("company", "h3._company a.com_nam"))
                if not company_elem:
                    company_elem = card.select_one("h3._company, a.com_nam, .com_nam, ._company")
                company_name = company_elem.get_text(strip=True) if company_elem else ""

                # 3. Location (City & State)
                loc_elem = card.select_one(self.selectors.get("location", "div._address span._fAdre"))
                if not loc_elem:
                    loc_elem = card.select_one("span._fAdre, div._address, ._address")
                location_text = ""
                if loc_elem:
                    tooltip_elem = loc_elem.select_one(".title_tooltip")
                    if tooltip_elem and tooltip_elem.get("data-tooltip"):
                        location_text = tooltip_elem.get("data-tooltip", "").strip()
                    else:
                        location_text = loc_elem.get_text(strip=True)
                if not location_text:
                    location_text = "India"

                # 4. Price
                price_elem = card.select_one(self.selectors.get("price", "span.price"))
                price_text = price_elem.get_text(strip=True) if price_elem else "N/A"

                # 5. Email & Contact from Card
                email_elem = card.select_one(self.selectors.get("email", "span.email"))
                email_text = email_elem.get_text(strip=True) if email_elem else ""

                contact_elem = card.select_one(self.selectors.get("contact", "span.contact"))
                contact_text = contact_elem.get_text(strip=True) if contact_elem else ""

                item = {
                    "Brand Name": company_name or product_name.split()[0],
                    "Company Name": company_name or "N/A",
                    "Product Category": category,
                    "Keyword": keyword,
                    "Product Name": product_name,
                    "Product URL": product_url,
                    "Seller/Brand Website": "",
                    "Contact Email": email_text,
                    "Phone Number": contact_text,
                    "LinkedIn": "",
                    "City & State": location_text,
                    "Marketplace": self.site_name,
                    "Price": price_text,
                    "MRP": "N/A",
                    "Discount": "N/A"
                }
                listings.append(item)

            except Exception as err:
                self.logger.debug(f"Error parsing ExportersIndia card: {err}")
                continue

        return listings

    def enrich_listing(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """
        Deep enrichment: Inspects product detail page AND invokes the LeadEnricher
        to extract website, email, phone, and LinkedIn.
        """
        url = item.get("Product URL", "")

        # 1. Inspect ExportersIndia detail page for embedded contacts
        if url:
            try:
                proxies = self.proxy_manager.get_requests_proxies()
                resp = self.session.get(url, proxies=proxies, timeout=8.0)
                if resp and resp.status_code == 200 and resp.text:
                    soup = BeautifulSoup(resp.text, "html.parser")
                    text_content = soup.get_text(separator=" ", strip=True)

                    # Extract phones
                    if not item.get("Phone Number"):
                        phones = extract_phones(text_content)
                        for tel in soup.select("a[href^='tel:']"):
                            phones.extend(extract_phones(tel.get("href", "")))
                        if phones:
                            item["Phone Number"] = ", ".join(sorted(list(set(phones))))

                    # Extract emails
                    if not item.get("Contact Email"):
                        emails = extract_emails(text_content)
                        for mailto in soup.select("a[href^='mailto:']"):
                            emails.extend(extract_emails(mailto.get("href", "")))
                        if emails:
                            item["Contact Email"] = ", ".join(sorted(list(set(emails))))
            except Exception as e:
                self.logger.debug(f"Error fetching detail page {url}: {e}")

        # 2. OSINT Web Bypass Enrichment (Find official website, LinkedIn, additional contacts)
        company = item.get("Company Name", "")
        brand = item.get("Brand Name", "")
        loc = item.get("City & State", "")

        enriched = lead_enricher.enrich(brand_name=brand, company_name=company, location=loc)

        if not item.get("Seller/Brand Website") and enriched.get("website"):
            item["Seller/Brand Website"] = enriched["website"]

        if not item.get("Contact Email") and enriched.get("email"):
            item["Contact Email"] = enriched["email"]

        if not item.get("Phone Number") and enriched.get("phone"):
            item["Phone Number"] = enriched["phone"]

        if not item.get("LinkedIn") and enriched.get("linkedin"):
            item["LinkedIn"] = enriched["linkedin"]

        if (not item.get("City & State") or item["City & State"] in ["India", "N/A"]) and enriched.get("city_state"):
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
        Orchestrates multi-page scraping workflow for ExportersIndia with optional lead enrichment.
        """
        all_results: List[Dict[str, Any]] = []
        self.logger.info(
            f"Starting {self.site_name} scraper | Category: '{category}' | Query: '{query}' | Max Pages: {max_pages}"
        )

        for page in range(1, max_pages + 1):
            self.logger.info(f"--- Scraping {self.site_name} Page {page}/{max_pages} for '{query}' ---")
            html = self.fetch_page(page, query=query)
            if not html:
                self.logger.warning(f"No content retrieved for page {page}. Stopping pagination.")
                break

            items = self.parse_listings(html, category=category, keyword=query)
            self.logger.info(f"Extracted {len(items)} items from page {page}.")
            if not items:
                self.logger.info(f"No items found on page {page}. Reached end of results.")
                break

            if enrich_details:
                self.logger.info(f"Enriching contact info & LinkedIn on {len(items)} items in parallel...")
                from concurrent.futures import ThreadPoolExecutor
                with ThreadPoolExecutor(max_workers=5) as executor:
                    items = list(executor.map(self.enrich_listing, items))

            all_results.extend(items)

        self.logger.info(f"Finished {self.site_name} scraping for '{query}'. Total items: {len(all_results)}")
        return all_results
