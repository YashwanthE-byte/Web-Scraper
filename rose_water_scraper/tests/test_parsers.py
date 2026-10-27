"""
tests/test_parsers.py
---------------------
Unit tests for HTML parsers and data cleaning logic.
"""

import pytest
from pathlib import Path
from scrapers.exportersindia_scraper import ExportersIndiaScraper
from utils.cleaner import clean_dataframe, clean_text

TESTS_DIR = Path(__file__).resolve().parent
SAMPLE_HTML_DIR = TESTS_DIR / "sample_html"

def test_exportersindia_parser_with_sample_html():
    """
    Tests that ExportersIndiaScraper accurately extracts product, company,
    and location details from the actual HTML snippet.
    """
    sample_file = SAMPLE_HTML_DIR / "exportersindia_sample.html"
    assert sample_file.exists(), f"Sample HTML file not found at {sample_file}"

    html_content = sample_file.read_text(encoding="utf-8")
    scraper = ExportersIndiaScraper()
    items = scraper.parse_listings(html_content)

    assert len(items) == 1, f"Expected 1 item parsed, found {len(items)}"
    item = items[0]

    assert item["Source"] == "ExportersIndia"
    assert "Panneer Rose Water" in item["Product"]
    assert "Sri Varahi Bairavar Pooja Centre" in item["Company"]
    assert "Chennai" in item["Location"] or "Tamil Nadu" in item["Location"]
    assert "exportersindia.com/product-detail/panneer-rose-water-4424133469.htm" in item["URL"]

def test_cleaner_deduplication_and_schema():
    """
    Tests that clean_dataframe properly normalizes text, fills missing columns,
    and removes duplicate records.
    """
    raw_data = [
        {
            "Source": "ExportersIndia",
            "Company": "  Sri Varahi Bairavar Pooja Centre..  ",
            "Product": "Panneer Rose Water\nForm : Liquid",
            "Location": "Chennai, Tamil Nadu",
            "Email": "N/A",
            "Contact": "N/A",
            "URL": "https://www.exportersindia.com/product-detail/123.htm"
        },
        # Duplicate record
        {
            "Source": "ExportersIndia",
            "Company": "Sri Varahi Bairavar Pooja Centre..",
            "Product": "Panneer Rose Water Form : Liquid",
            "Location": "Chennai, Tamil Nadu",
            "Email": "N/A",
            "Contact": "N/A",
            "URL": "https://www.exportersindia.com/product-detail/123.htm"
        }
    ]

    df = clean_dataframe(raw_data)
    assert len(df) == 1
    assert list(df.columns) == ["Source", "Company", "Product", "Price", "MRP", "Discount", "Location", "Email", "Contact", "URL"]
    assert df.iloc[0]["Product"] == "Panneer Rose Water Form : Liquid"


def test_extract_phones_and_emails():
    """
    Tests extraction of Indian phone numbers and emails from unstructured descriptions.
    """
    from utils.cleaner import extract_phones, extract_emails

    sample_text = """
    We are leading manufacturers of Pure Steam Distilled Rose Water.
    For wholesale bulk orders, please call us at +91-9876543210 or 09123456789.
    You can also email us at sales@shreejiperfumers.com or info@rosewaterindia.org.
    Ignore image files like banner@2x.png or placeholders like test@example.com.
    """
    phones = extract_phones(sample_text)
    emails = extract_emails(sample_text)

    assert "+91-9876543210" in phones
    assert "+91-9123456789" in phones
    assert "sales@shreejiperfumers.com" in emails
    assert "info@rosewaterindia.org" in emails
    assert "banner@2x.png" not in emails
    assert "test@example.com" not in emails


def test_is_valid_rose_water_filter():
    """
    Tests strict filtering logic to ensure authentic Rose Water products pass
    while irrelevant categories (jewelry, apparel, sanitaryware, sweets) are rejected.
    """
    from utils.cleaner import is_valid_rose_water

    # Authentic Rose Water products (MUST PASS)
    assert is_valid_rose_water("Steam Distilled Pure Rose Water")
    assert is_valid_rose_water("Dabur Gulabari Rose Water")
    assert is_valid_rose_water("Flowers Rose Otto Hydrosol, Supply Type : OEM/ODM")
    assert is_valid_rose_water("Natural Rose Water 100ml Liquid Facial Cleanser")
    assert is_valid_rose_water("Rose Water Panneer for Pooja Purpose in Spray Bottle")
    assert is_valid_rose_water("100ml Gulab Ark")
    assert is_valid_rose_water("Pure Natural Rose Water Facial Toner")

    # Spurious / Irrelevant products (MUST BE REJECTED)
    assert not is_valid_rose_water("14K Rose Gold Floral Cluster Diamond Ring")
    assert not is_valid_rose_water("Rose Gold (1120) Water Closet")
    assert not is_valid_rose_water("Water Lily Bandeau Bikini Top")
    assert not is_valid_rose_water("Ladies Rose Pink Printed Cotton Ethnic Suit")
    assert not is_valid_rose_water("Titan Force 111 semi-commercial Alkaline Hydrogen Water Ionizer")
    assert not is_valid_rose_water("Gulab Jamun, For Dessert, Feature : Delicious")
    assert not is_valid_rose_water("Rose Incense Sticks - Bamboo Fragrance for Home")
    assert not is_valid_rose_water("Stainless Steel Rose Gold Water Ripple Sheet")
    assert not is_valid_rose_water("Rose Quartz Table Lamp - Hand Made Semi Precious Stone")


