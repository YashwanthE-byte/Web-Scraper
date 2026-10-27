"""
config.py
---------
Centralized configuration management for the Beauty, Haircare, Skincare & Herbal Scraper project.
Defines product taxonomies, URLs, CSS selectors, delays, headers, export settings,
and lead enrichment configurations.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file if available
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

# ==========================================
# 1. PRODUCT TAXONOMY & KEYWORDS
# ==========================================
PRODUCT_TAXONOMY = {
    "Haircare": [
        "Rosemary Hair Oil",
        "Hair Growth Oil",
        "Hair Growth Serum",
        "Hair Serum",
        "Hair Mist",
        "Hair Spray",
        "Hair Tonic",
        "Scalp Serum",
        "Scalp Spray",
        "Hair Conditioner",
        "Hair Mask",
        "Shampoo",
        "Herbal Shampoo",
        "Anti Hair Fall Shampoo",
    ],
    "Skincare": [
        "Rose Water",
        "Face Toner",
        "Face Mist",
        "Facial Mist",
        "Hydrating Mist",
        "Skin Toner",
        "Face Spray",
        "Facial Spray",
        "Rose Toner",
        "Herbal Toner",
        "Face Cleanser",
        "Aloe Vera Toner",
    ],
    "Herbal": [
        "Ayurvedic Hair Oil",
        "Herbal Hair Oil",
        "Herbal Skin Care",
        "Organic Cosmetics",
        "Natural Cosmetics",
        "Herbal Cosmetics",
    ]
}

# Flattened list of all keywords
ALL_KEYWORDS = [kw for cat in PRODUCT_TAXONOMY.values() for kw in cat]

# Default values
DEFAULT_CATEGORY = "all"
DEFAULT_QUERY = "Rosemary Hair Oil"
DEFAULT_MAX_PAGES = 5
DEFAULT_OUTPUT_BASE = BASE_DIR / os.getenv("OUTPUT_DIR", "output") / "beauty_leads"
LOG_DIR = BASE_DIR / "logs"

# HTTP User-Agent identification
USER_AGENT = os.getenv(
    "USER_AGENT",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Responsible Scraping Delays (in seconds)
MIN_DELAY_SECONDS = 1.5
MAX_DELAY_SECONDS = 3.5

# Retry & Timeout Configuration
MAX_RETRIES = 3
BACKOFF_FACTOR = 2.0
REQUEST_TIMEOUT_SECONDS = 15.0

# Deep Contact Info & Lead Enrichment
ENRICH_CONTACT_DETAILS = os.getenv("ENRICH_CONTACT_DETAILS", "true").lower() in ("true", "1", "yes")
CACHE_FILE = BASE_DIR / "output" / "brand_enrichment_cache.json"

# Column Order (Strict enforcement)
FINAL_COLUMNS = [
    "Brand Name",
    "Company Name",
    "Product Category",
    "Keyword",
    "Product Name",
    "Product URL",
    "Seller/Brand Website",
    "Contact Email",
    "Phone Number",
    "LinkedIn",
    "City & State",
    "Marketplace",
    "Price",
    "MRP",
    "Discount"
]

# Standard Headers for Requests
DEFAULT_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

# Block detection strings/status codes
BLOCKED_STATUS_CODES = [403, 429]
BLOCKED_KEYWORDS = [
    "captcha",
    "access denied",
    "cf-browser-verification",
    "please verify you are a human",
    "security check"
]

# ==========================================
# PROXY CONFIGURATION (Webshare / Custom)
# ==========================================
USE_PROXIES = os.getenv("USE_PROXIES", "false").lower() in ("true", "1", "yes")
WEBSHARE_USERNAME = os.getenv("WEBSHARE_USERNAME", "")
WEBSHARE_PASSWORD = os.getenv("WEBSHARE_PASSWORD", "")
WEBSHARE_GATEWAY = os.getenv("WEBSHARE_GATEWAY", "p.webshare.io")
WEBSHARE_PORT = int(os.getenv("WEBSHARE_PORT", "80"))
WEBSHARE_MODE = os.getenv("WEBSHARE_MODE", "rotating")  # 'rotating' or 'direct'
CUSTOM_PROXIES = [p.strip() for p in os.getenv("CUSTOM_PROXIES", "").split(",") if p.strip()]

# ==========================================
# 2. EXPORTERSINDIA CONFIGURATION
# ==========================================
EXPORTERSINDIA_CONFIG = {
    "site_name": "ExportersIndia",
    "base_url": "https://www.exportersindia.com",
    "robots_url": "https://www.exportersindia.com/robots.txt",
    
    # Search URL format strings
    "search_url_template": "https://www.exportersindia.com/search.php?srch_catg_ty=prod&term={query}&cont=IN&ss_status=N",
    "search_url_paged_template": "https://www.exportersindia.com/search.php?srch_catg_ty=prod&term={query}&cont=IN&ss_status=N&page={page}",
    
    # CSS SELECTORS
    "selectors": {
        "card": "div.l3Inn, div.classified_details, div[id^='id_0_']",
        "product": "h2 a.prdclk, h2 a, .inDataH h2 a",
        "company": "h3._company a.com_nam, h3._company, a.com_nam, .com_nam",
        "location": "div._address span._fAdre, span._fAdre, div._address, ._address",
        "email": "span.email",
        "contact": "span.contact",
        "price": "span.price, .price, .approx_price, [class*='price']",
    }
}

# ==========================================
# 3. AJIO CONFIGURATION
# ==========================================
AJIO_CONFIG = {
    "site_name": "Ajio",
    "base_url": "https://www.ajio.com",
    "robots_url": "https://www.ajio.com/robots.txt",
    "page_size": 45,
    "selectors": {
        "card": "div.item.rilrtl-products-list__item, div.preview",
        "company": "div.brand, .brand",
        "product": "div.nameCls, div.name, .name",
        "price": "span.price, div.price",
        "mrp": "span.orginal-price, span.prod-cp",
        "discount": "span.discount",
        "url": "a.rilrtl-products-list__link",
    }
}
