"""
utils/cleaner.py
----------------
Provides functions for cleaning, trimming, normalizing, deduplicating,
and structuring scraped product and lead data into a clean pandas DataFrame.
"""

import re
from typing import Optional, List, Dict, Any, Set
import pandas as pd
from config import FINAL_COLUMNS

# Regex patterns for Indian Phone numbers and standard emails
PHONE_PATTERN = re.compile(
    r'(?:(?:\+|0{0,2})91[\s\-]?)?(?:[6-9]\d{9}|[6-9]\d{4}[\s\-]?\d{5}|[6-9]\d{2}[\s\-]?\d{3}[\s\-]?\d{4})|(?:\b1800[\s\-]?\d{3}[\s\-]?\d{3,4}\b)'
)
EMAIL_PATTERN = re.compile(
    r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'
)

INVALID_EMAIL_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".js", ".woff", ".woff2", ".ttf"
)
INVALID_EMAIL_DOMAINS = (
    "example.com", "domain.com", "email.com", "yourdomain.com", "wixpress.com",
    "shopify.com", "myshopify.com", "sentry.io", "w3.org", "schema.org"
)


def extract_phones(text: Optional[str]) -> List[str]:
    """
    Extracts all unique valid phone numbers from a text string.
    Normalizes digits and formats Indian numbers.
    """
    if not text:
        return []
    
    matches = PHONE_PATTERN.findall(text)
    cleaned_phones: Set[str] = set()
    for match in matches:
        digits_only = re.sub(r'[^\d]', '', match)
        if len(digits_only) == 10 and digits_only[0] in '6789':
            cleaned_phones.add(f"+91-{digits_only}")
        elif len(digits_only) == 12 and digits_only.startswith("91") and digits_only[2] in '6789':
            cleaned_phones.add(f"+91-{digits_only[2:]}")
        elif len(digits_only) == 11 and digits_only.startswith("0") and digits_only[1] in '6789':
            cleaned_phones.add(f"+91-{digits_only[1:]}")
        elif digits_only.startswith("1800") and len(digits_only) in (10, 11):
            cleaned_phones.add(match.strip())
            
    return sorted(list(cleaned_phones))


def extract_emails(text: Optional[str]) -> List[str]:
    """
    Extracts all unique valid email addresses from a text string.
    Filters out image filenames, fake domains, and asset artifacts.
    """
    if not text:
        return []
    
    matches = EMAIL_PATTERN.findall(text)
    valid_emails: Set[str] = set()
    for match in matches:
        email = match.lower().strip(".,;:()[]{}<>\"'")
        if any(email.endswith(ext) for ext in INVALID_EMAIL_EXTENSIONS):
            continue
        domain = email.split("@")[-1] if "@" in email else ""
        if domain in INVALID_EMAIL_DOMAINS or not domain:
            continue
        if len(email) > 5 and "." in domain and not domain.startswith("image"):
            valid_emails.add(email)
            
    return sorted(list(valid_emails))


def clean_text(value: Optional[str]) -> str:
    """
    Cleans a single string value:
    - Strips leading/trailing whitespace
    - Normalizes internal extra spaces and newlines
    - Converts None/NaN values to empty string ""
    """
    if value is None or pd.isna(value):
        return ""
    
    cleaned = " ".join(str(value).split())
    return cleaned


def clean_dataframe(raw_data: List[Dict[str, Any]]) -> pd.DataFrame:
    """
    Converts a list of raw listing dictionaries into a clean, deduplicated pandas DataFrame.
    """
    if not raw_data:
        return pd.DataFrame(columns=FINAL_COLUMNS)

    df = pd.DataFrame(raw_data)

    # 1. Column mapping for backwards compatibility if old keys are present
    key_mapping = {
        "Source": "Marketplace",
        "Company": "Company Name",
        "Product": "Product Name",
        "URL": "Product URL",
        "Location": "City & State",
        "Email": "Contact Email",
        "Contact": "Phone Number",
    }
    for old_k, new_k in key_mapping.items():
        if old_k in df.columns and new_k not in df.columns:
            df[new_k] = df[old_k]

    # If Brand Name is empty, populate from Company Name
    if "Brand Name" not in df.columns or df["Brand Name"].isna().all():
        df["Brand Name"] = df.get("Company Name", "")

    # 2. Ensure all required columns exist
    for col in FINAL_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    # 3. Clean text across all string columns
    for col in FINAL_COLUMNS:
        df[col] = df[col].apply(clean_text)

    # 4. Remove empty product names
    if "Product Name" in df.columns:
        df = df[df["Product Name"] != ""].copy()

    # 5. Remove duplicates based on combination of Marketplace, Brand Name, Product Name, Product URL
    dedup_cols = [c for c in ["Marketplace", "Brand Name", "Product Name", "Product URL"] if c in df.columns]
    if dedup_cols:
        df.drop_duplicates(subset=dedup_cols, keep="first", inplace=True)

    # 6. Reorder columns strictly according to target schema
    df = df[FINAL_COLUMNS]

    # 7. Reset index starting from 0
    df.reset_index(drop=True, inplace=True)

    return df
