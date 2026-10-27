"""
utils/enricher.py
-----------------
Automated Brand & Lead Enrichment Engine (OSINT Web Bypasser).
Discovers official brand/company websites via Bing search with curl_cffi,
validates domain relevancy against brand name, extracts direct contact emails,
phone numbers, LinkedIn company pages, and HQ locations from official domains.
Includes persistent caching to avoid redundant web requests.
"""

import json
import re
import base64
from pathlib import Path
from typing import Dict, Any, Optional, List, Set
from urllib.parse import urlparse, urljoin, quote_plus
from bs4 import BeautifulSoup

from config import (
    DEFAULT_HEADERS,
    USER_AGENT,
    CACHE_FILE,
    REQUEST_TIMEOUT_SECONDS,
)
from utils.logger import setup_logger
from utils.cleaner import extract_phones, extract_emails

logger = setup_logger("enricher")

# Domains and suffixes to strictly ignore
IGNORED_DOMAINS = {
    "amazon.in", "amazon.com", "flipkart.com", "ajio.com", "nykaa.com",
    "purplle.com", "myntra.com", "tira.com", "tatacliq.com", "meesho.com",
    "exportersindia.com", "indiamart.com", "tradeindia.com", "justdial.com",
    "facebook.com", "instagram.com", "twitter.com", "x.com", "youtube.com",
    "pinterest.com", "wikipedia.org", "quora.com", "reddit.com",
    "play.google.com", "apps.apple.com", "glassdoor.co.in", "linkedin.com",
    "zaubacorp.com", "tofler.in", "instafinancials.com", "economicstimes.indiatimes.com",
    "mediafire.com", "starsunfolded.com", "lowyat.net", "fandom.com", "blogspot.com",
    "wordpress.com", "marutisuzuki.com", "tatamotors.com", "hyundai.com"
}

GENERIC_BRAND_STOPWORDS = {
    "pvt", "ltd", "private", "limited", "llp", "inc", "corp", "enterprises",
    "industries", "store", "official", "cosmetics", "products", "boutique", "international"
}

INDIAN_STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya", "Mizoram",
    "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim", "Tamil Nadu",
    "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand", "West Bengal",
    "Delhi", "New Delhi", "Chandigarh", "Puducherry"
]

LINKEDIN_COMPANY_REGEX = re.compile(
    r'https?://(?:[a-z]{2,3}\.)?linkedin\.com/company/([a-zA-Z0-9_\-]+)',
    re.IGNORECASE
)


class LeadEnricher:
    """
    Orchestrates brand/company website discovery and deep contact extraction.
    """

    def __init__(self, cache_path: Path = CACHE_FILE):
        self.cache_path = cache_path
        self.cache: Dict[str, Dict[str, Any]] = self._load_cache()

    def _load_cache(self) -> Dict[str, Dict[str, Any]]:
        """Loads cached brand enrichments from disk."""
        if self.cache_path.exists():
            try:
                with open(self.cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load enrichment cache: {e}")
        return {}

    def _save_cache(self) -> None:
        """Persists cache to disk."""
        try:
            self.cache_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(self.cache, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Failed to save enrichment cache: {e}")

    def normalize_name(self, name: str) -> str:
        """Normalizes company/brand name for cache key."""
        if not name:
            return ""
        clean = re.sub(
            r'(?i)\b(pvt\.?|ltd\.?|private limited|limited|llp|inc\.?|corp\.?|enterprises|industries|store|official)\b',
            '',
            name
        )
        return " ".join(clean.strip().lower().split())

    def search_web_bing(self, query: str) -> List[str]:
        """
        Queries Bing search using curl_cffi and decodes redirect result URLs.
        """
        urls: List[str] = []
        try:
            from curl_cffi import requests as curl_requests
        except ImportError:
            import requests as curl_requests

        try:
            search_url = f"https://www.bing.com/search?q={quote_plus(query)}"
            resp = curl_requests.get(
                search_url,
                impersonate="chrome124",
                timeout=10
            )
            if resp.status_code == 200:
                soup = BeautifulSoup(resp.text, "html.parser")
                for li in soup.select("li.b_algo h2 a"):
                    h = li.get("href", "")
                    if "bing.com/ck/a" in h and "u=" in h:
                        try:
                            import urllib.parse
                            parsed = urllib.parse.parse_qs(urllib.parse.urlparse(h).query)
                            raw_u = parsed.get("u", [""])[0]
                            if raw_u.startswith("a1"):
                                b64 = raw_u[2:] + "=" * (-len(raw_u[2:]) % 4)
                                decoded = base64.b64decode(b64).decode("utf-8", errors="ignore")
                                if decoded.startswith("http"):
                                    urls.append(decoded)
                        except Exception:
                            pass
                    elif h.startswith("http"):
                        urls.append(h)
        except Exception as err:
            logger.debug(f"Bing search error for query '{query}': {err}")

        return urls

    def is_valid_brand_domain(self, domain: str, brand_name: str) -> bool:
        """
        Strict domain validator. Checks whether domain contains brand name tokens
        and excludes irrelevant or spam domains.
        """
        if not domain or len(domain) < 4:
            return False

        for ign in IGNORED_DOMAINS:
            if ign in domain:
                return False

        if any(bad in domain for bad in [".gov", ".nic.in", ".mil", ".edu", "forum", "wiki", "mediafire", "starsunfolded", "lowyat"]):
            return False

        # Extract tokens from brand_name
        tokens = [w.lower() for w in re.findall(r'[a-zA-Z]{3,}', brand_name) if w.lower() not in GENERIC_BRAND_STOPWORDS]
        if not tokens:
            tokens = [w.lower() for w in re.findall(r'[a-zA-Z]{3,}', brand_name)]

        clean_dom = domain.replace("-", "").replace("_", "").lower()
        return any(tok in clean_dom for tok in tokens)

    def find_official_website(self, brand_name: str) -> Optional[str]:
        """
        Searches the web for the brand's official D2C/corporate website.
        """
        if not brand_name or brand_name.lower() in ["n/a", "ajio seller", "unknown"]:
            return None

        query = f'"{brand_name}" official website India'
        search_links = self.search_web_bing(query)

        for link in search_links:
            try:
                domain = urlparse(link).netloc.lower().replace("www.", "")
                if self.is_valid_brand_domain(domain, brand_name):
                    parsed = urlparse(link)
                    base_website = f"{parsed.scheme}://{parsed.netloc}"
                    return base_website
            except Exception:
                continue

        return None

    def find_linkedin_page(self, brand_name: str) -> Optional[str]:
        """
        Finds the official LinkedIn company page for a brand with token verification.
        """
        if not brand_name or brand_name.lower() in ["n/a", "ajio seller"]:
            return None

        query = f'"{brand_name}" site:linkedin.com/company'
        search_links = self.search_web_bing(query)

        for link in search_links:
            match = LINKEDIN_COMPANY_REGEX.search(link)
            if match:
                company_slug = match.group(1).rstrip("/")
                if self.is_valid_brand_domain(company_slug, brand_name):
                    return f"https://www.linkedin.com/company/{company_slug}"

        return None

    def crawl_website_for_contacts(self, website_url: str) -> Dict[str, Any]:
        """
        Visits the brand website homepage + /contact and /about pages to extract contacts.
        """
        result = {
            "emails": set(),
            "phones": set(),
            "linkedin": None,
            "city_state": None
        }

        if not website_url:
            return result

        pages_to_check = [
            website_url,
            urljoin(website_url, "/contact"),
            urljoin(website_url, "/contact-us"),
            urljoin(website_url, "/pages/contact-us"),
            urljoin(website_url, "/about-us"),
            urljoin(website_url, "/pages/about-us"),
        ]

        try:
            from curl_cffi import requests as curl_requests
        except ImportError:
            import requests as curl_requests

        visited = set()
        for page_url in pages_to_check:
            if page_url in visited:
                continue
            visited.add(page_url)

            try:
                resp = curl_requests.get(
                    page_url,
                    impersonate="chrome124",
                    timeout=8.0
                )
                if resp.status_code != 200:
                    continue

                soup = BeautifulSoup(resp.text, "html.parser")
                text_content = soup.get_text(separator=" ", strip=True)

                # 1. Emails
                emails = extract_emails(text_content)
                for mailto in soup.select("a[href^='mailto:']"):
                    raw_mail = mailto.get("href", "").replace("mailto:", "").split("?")[0].strip()
                    emails.extend(extract_emails(raw_mail))
                result["emails"].update(emails)

                # 2. Phones
                phones = extract_phones(text_content)
                for tel in soup.select("a[href^='tel:']"):
                    raw_tel = tel.get("href", "").replace("tel:", "").strip()
                    phones.extend(extract_phones(raw_tel))
                result["phones"].update(phones)

                # 3. LinkedIn Link
                if not result["linkedin"]:
                    for a in soup.select("a[href*='linkedin.com/company']"):
                        href = a.get("href", "")
                        match = LINKEDIN_COMPANY_REGEX.search(href)
                        if match:
                            result["linkedin"] = f"https://www.linkedin.com/company/{match.group(1)}"
                            break

                # 4. Location extraction
                if not result["city_state"]:
                    for state in INDIAN_STATES:
                        if re.search(r'\b' + re.escape(state) + r'\b', text_content, re.IGNORECASE):
                            city_match = re.search(r'([A-Za-z\s]+),\s*' + re.escape(state), text_content)
                            if city_match:
                                matched_city = city_match.group(1).strip().split()[-1]
                                if len(matched_city) > 2 and matched_city.isalpha():
                                    result["city_state"] = f"{matched_city.capitalize()}, {state}"
                                    break
                            result["city_state"] = state
                            break

            except Exception as err:
                logger.debug(f"Error crawling {page_url}: {err}")
                continue

        return result

    def enrich(self, brand_name: str, company_name: str = "", location: str = "") -> Dict[str, str]:
        """
        Main enrichment entry point. Checks cache first, performs web discovery if missing.
        """
        lookup_name = brand_name if (brand_name and brand_name.lower() not in ["n/a", "ajio seller"]) else company_name
        cache_key = self.normalize_name(lookup_name)

        if not cache_key:
            return {
                "website": "",
                "email": "",
                "phone": "",
                "linkedin": "",
                "city_state": location or "India"
            }

        # Check Cache
        if cache_key in self.cache:
            cached = self.cache[cache_key]
            logger.debug(f"Cache hit for brand '{lookup_name}': {cached.get('website', '')}")
            return cached

        logger.info(f"Enriching brand/company: '{lookup_name}'...")

        # 1. Discover Official Website
        website = self.find_official_website(lookup_name)

        # 2. Crawl website if found
        contact_data = self.crawl_website_for_contacts(website) if website else {"emails": set(), "phones": set(), "linkedin": None, "city_state": None}

        # 3. Discover LinkedIn if not found on website
        linkedin_url = contact_data.get("linkedin") or self.find_linkedin_page(lookup_name)

        # 4. Resolve City & State
        resolved_location = location if (location and location.lower() != "n/a") else (contact_data.get("city_state") or "India")

        enriched_entry = {
            "website": website or "",
            "email": ", ".join(sorted(list(contact_data["emails"]))) if contact_data["emails"] else "",
            "phone": ", ".join(sorted(list(contact_data["phones"]))) if contact_data["phones"] else "",
            "linkedin": linkedin_url or "",
            "city_state": resolved_location
        }

        # Save to memory and disk cache
        self.cache[cache_key] = enriched_entry
        self._save_cache()

        logger.info(
            f"Enriched '{lookup_name}': Website={enriched_entry['website'] or 'N/A'} | "
            f"Email={enriched_entry['email'] or 'N/A'} | Phone={enriched_entry['phone'] or 'N/A'} | "
            f"LinkedIn={enriched_entry['linkedin'] or 'N/A'}"
        )

        return enriched_entry


# Singleton instance
lead_enricher = LeadEnricher()
