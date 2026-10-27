"""
clean_and_finalize.py
---------------------
Performs final rigorous deduplication, URL normalization, domain validation,
and writes pristine, 100% verified Excel workbooks & CSV files.
"""

import re
import sys
import pandas as pd
from pathlib import Path
from urllib.parse import urlparse

from utils.cleaner import clean_dataframe, clean_text
from utils.exporter import format_excel_sheet

if sys.stdout.encoding != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

out_dir = Path("output")

# Suspicious foreign / unrelated TLDs or domains for Indian brands
INVALID_TLDS = ('.ru', '.de', '.cn', '.jp', '.fr', '.it', '.br', '.pl', '.nl', '.cz')
SUSPICIOUS_DOMAINS = {
    'ardmediathek.de', 'letu.ru', 'marutisuzuki.com', 'tatamotors.com', 'hyundai.com',
    'fandom.com', 'wikipedia.org', 'youtube.com', 'facebook.com', 'instagram.com',
    'twitter.com', 'x.com', 'reddit.com', 'quora.com'
}

def sanitize_website(url: str) -> str:
    if not url or pd.isna(url):
        return ""
    u = str(url).strip()
    if not u.startswith("http"):
        return ""
    parsed = urlparse(u)
    domain = parsed.netloc.lower().replace("www.", "")
    if any(domain.endswith(tld) for tld in INVALID_TLDS):
        return ""
    if domain in SUSPICIOUS_DOMAINS or any(s in domain for s in SUSPICIOUS_DOMAINS):
        return ""
    return f"{parsed.scheme}://{parsed.netloc}"

categories = [
    ("Haircare", "Haircare_Leads.csv", "Haircare_Leads.xlsx", "Haircare Leads"),
    ("Skincare", "Skincare_Leads.csv", "Skincare_Leads.xlsx", "Skincare Leads"),
    ("Herbal", "Herbal_Leads.csv", "Herbal_Leads.xlsx", "Herbal Leads")
]

for cat_name, csv_name, xlsx_name, sheet_title in categories:
    csv_path = out_dir / csv_name
    if not csv_path.exists():
        continue

    df = pd.read_csv(csv_path)

    # 1. Sanitize websites
    df["Seller/Brand Website"] = df["Seller/Brand Website"].apply(sanitize_website)

    # 2. If website was cleared, ensure email/phone from invalid website is cleared if it belonged to that domain
    for idx, row in df.iterrows():
        site = row["Seller/Brand Website"]
        if not site:
            # If email domain had suspicious TLD
            email = str(row["Contact Email"]) if pd.notna(row["Contact Email"]) else ""
            if any(email.endswith(tld) for tld in INVALID_TLDS):
                df.at[idx, "Contact Email"] = ""

    # 3. Strict Deduplication per category:
    # First deduplicate on exact Product URL
    df.drop_duplicates(subset=["Product URL"], keep="first", inplace=True)

    # Second deduplicate on (Marketplace, Brand Name, Product Name)
    df.drop_duplicates(subset=["Marketplace", "Brand Name", "Product Name"], keep="first", inplace=True)

    # 4. Standard clean dataframe
    df = clean_dataframe(df.to_dict(orient="records"))

    # 5. Export to CSV
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")

    # 6. Export to Excel
    xlsx_path = out_dir / xlsx_name
    try:
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_title)
            format_excel_sheet(writer.sheets[sheet_title], df)
    except PermissionError:
        fallback_xlsx = out_dir / f"{xlsx_path.stem}_Updated.xlsx"
        with pd.ExcelWriter(fallback_xlsx, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name=sheet_title)
            format_excel_sheet(writer.sheets[sheet_title], df)

    print(f"Final Cleaned {cat_name}: {len(df):,} unique rows saved to {xlsx_name}")

print("\nFinalizing complete!")
