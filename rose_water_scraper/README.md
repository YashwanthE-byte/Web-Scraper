# Beauty, Haircare, Skincare & Herbal Lead Scraper 🌸🧴

A modular, enterprise-grade Python web scraper and OSINT lead generation pipeline designed to collect seller, brand, and product intelligence across **Haircare**, **Skincare**, and **Herbal** categories from **ExportersIndia** and **Ajio**.

Includes an **Automated Lead Enrichment Engine** that bypasses marketplace barriers to discover official brand websites, business emails, phone numbers, LinkedIn company pages, and HQ locations.

---

## 📋 Table of Contents
- [✨ Key Features](#-key-features)
- [📂 Product Taxonomy (32 Keywords)](#-product-taxonomy-32-keywords)
- [📊 Output Data Schema](#-output-data-schema)
- [📁 Directory Structure](#-directory-structure)
- [⚙️ Installation & Setup](#️-installation--setup)
- [🚀 Usage Guide & CLI Commands](#-usage-guide--cli-commands)
- [🔍 Automated Lead Enrichment & Caching](#-automated-lead-enrichment--caching)
- [⚖️ Responsible Scraping & Compliance](#️-responsible-scraping--compliance)

---

## ✨ Key Features
- **Multi-Source Scraping**: Scrapes B2B supplier listings on **ExportersIndia** and D2C/retail catalogs on **Ajio**.
- **Automated Lead Enrichment**: Discovers brand domains, contact emails, phone numbers, and official LinkedIn company pages.
- **Persistent Brand Caching (`output/brand_enrichment_cache.json`)**: Eliminates redundant queries when multiple products belong to the same brand.
- **Multi-Tab Excel Workbooks**: Automatically exports a **Master Leads** sheet plus dedicated category sheets (**Haircare**, **Skincare**, **Herbal**), along with a UTF-8-BOM CSV file.
- **Anti-Bot & Proxy Rotation**: Uses `curl_cffi` (Chrome TLS fingerprinting) and Webshare rotating proxy support.

---

## 📂 Product Taxonomy (32 Keywords)

| Category | Keywords Included |
| :--- | :--- |
| **Haircare** (14) | Rosemary Hair Oil, Hair Growth Oil, Hair Growth Serum, Hair Serum, Hair Mist, Hair Spray, Hair Tonic, Scalp Serum, Scalp Spray, Hair Conditioner, Hair Mask, Shampoo, Herbal Shampoo, Anti Hair Fall Shampoo |
| **Skincare** (12) | Rose Water, Face Toner, Face Mist, Facial Mist, Hydrating Mist, Skin Toner, Face Spray, Facial Spray, Rose Toner, Herbal Toner, Face Cleanser, Aloe Vera Toner |
| **Herbal** (6) | Ayurvedic Hair Oil, Herbal Hair Oil, Herbal Skin Care, Organic Cosmetics, Natural Cosmetics, Herbal Cosmetics |

---

## 📊 Output Data Schema

Every lead and product listing is standardized into the following columns:

1. **Brand Name**
2. **Company Name**
3. **Product Category** (`Haircare` / `Skincare` / `Herbal`)
4. **Keyword** (The exact subcategory term queried)
5. **Product Name**
6. **Product URL**
7. **Seller/Brand Website** (Enriched)
8. **Contact Email** (Enriched)
9. **Phone Number** (Enriched)
10. **LinkedIn** (Enriched official company profile)
11. **City & State** (Supplier location / Brand HQ)
12. **Marketplace** (`ExportersIndia` or `Ajio`)
13. **Price**
14. **MRP**
15. **Discount**

---

## 📁 Directory Structure

```
rose_water_scraper/
├── main.py                             # CLI entry point
├── config.py                           # Centralized configuration, taxonomy & schema
├── .env                                # Environment variables (User-Agent, Proxies)
├── requirements.txt                    # Dependencies
├── README.md                           # Documentation
├── scrapers/
│   ├── base_scraper.py                 # Abstract base class with retry, delay & robots.txt
│   ├── exportersindia_scraper.py       # ExportersIndia scraper with detail-page parser
│   └── ajio_scraper.py                 # Ajio scraper using curl_cffi Chrome TLS
├── utils/
│   ├── cleaner.py                      # Data trimming, normalization & deduplication
│   ├── enricher.py                     # OSINT brand enricher (Website, Email, Phone, LinkedIn)
│   ├── exporter.py                     # CSV & multi-tab Excel exporter
│   ├── logger.py                       # Console & file logging
│   └── proxy_manager.py                # Webshare / custom proxy rotation
├── output/                             # Generated CSV, Excel (.xlsx) & brand cache
└── logs/                               # Runtime log files
```

---

## 🚀 Usage Guide & CLI Commands

### 1. Scrape an Entire Category (e.g. Haircare)
```powershell
python main.py --category haircare --source all --max-pages 3
```

### 2. Scrape Skincare or Herbal Keywords
```powershell
python main.py --category skincare --source exportersindia -p 2
python main.py --category herbal --source ajio -p 2
```

### 3. Scrape a Single Specific Keyword
```powershell
python main.py --query "Rosemary Hair Oil" --source all -p 1
```

### 4. Scrape Multiple Comma-Separated Keywords
```powershell
python main.py --query "Rose Water, Ayurvedic Hair Oil, Face Toner" --source all -p 2
```

### 5. Run All 32 Keywords Across Both Marketplaces
```powershell
python main.py --category all --source all --max-pages 3
```

### 6. Fast Raw Catalog Scrape (Without Web Enrichment)
```powershell
python main.py --category haircare --no-enrich
```

---

## 🔍 Automated Lead Enrichment & Caching

When scraping brands from Ajio or supplier listings on ExportersIndia, the **LeadEnricher** automatically:
1. Searches Bing for the official brand/company website using `curl_cffi`.
2. Validates domain tokens to prevent false positives.
3. Crawls the homepage and `/contact` / `/about` pages to extract:
   - Direct business emails (`info@`, `care@`, `contact@`, `sales@`)
   - Customer support and WhatsApp phone numbers
   - Official LinkedIn Company Page URLs (`linkedin.com/company/...`)
4. Stores verified profiles in `output/brand_enrichment_cache.json` for rapid instant reuse.

---

## ⚖️ Responsible Scraping & Compliance

> [!IMPORTANT]
> - Always respect target sites' `robots.txt` rules and polite delay intervals.
> - Handled data must comply with India's **Digital Personal Data Protection Act (DPDP 2023)** and TRAI regulations for commercial communications.
