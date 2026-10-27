"""
deep_scrape_and_enrich.py
--------------------------
Phase 1: Scrape ALL possible data from Ajio + ExportersIndia (no page cap).
Phase 2: Run enrichment on every brand that has a website but no email/phone yet.
Phase 3: Merge with existing Excel sheets (dedup) and re-export.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime
import pandas as pd

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from config import PRODUCT_TAXONOMY, FINAL_COLUMNS, CACHE_FILE
from scrapers.exportersindia_scraper import ExportersIndiaScraper
from scrapers.ajio_scraper import AjioScraper
from utils.cleaner import clean_dataframe
from utils.exporter import format_excel_sheet
from utils.enricher import LeadEnricher
from utils.logger import setup_logger

logger = setup_logger("deep_scraper")
OUT_DIR = BASE_DIR / "output"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ──────────────────────────────────────────────────────────────────────────────
# CONFIGURATION — push limits as high as possible
# ──────────────────────────────────────────────────────────────────────────────
MAX_PAGES_AJIO          = 50    # 50 pages x 45 items = up to 2,250 per keyword
MAX_PAGES_EI            = 30    # ExportersIndia up to 30 pages per keyword

CATEGORY_FILES = {
    "Haircare": ("Haircare_Leads.xlsx", "Haircare_Leads.csv", "Haircare Leads"),
    "Skincare":  ("Skincare_Leads.xlsx",  "Skincare_Leads.csv",  "Skincare Leads"),
    "Herbal":    ("Herbal_Leads.xlsx",    "Herbal_Leads.csv",    "Herbal Leads"),
}


# ──────────────────────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────────────────────

def load_existing() -> pd.DataFrame:
    """Load all 3 existing CSVs and merge into one DataFrame."""
    frames = []
    for cat, (xlsx, csv_name, _) in CATEGORY_FILES.items():
        csv_path = OUT_DIR / csv_name
        if csv_path.exists():
            try:
                df = pd.read_csv(csv_path)
                frames.append(df)
                logger.info(f"Loaded {len(df)} existing rows from {csv_name}")
            except Exception as e:
                logger.warning(f"Could not read {csv_name}: {e}")
    if frames:
        combined = pd.concat(frames, ignore_index=True)
        logger.info(f"Total existing records loaded: {len(combined)}")
        return combined
    return pd.DataFrame(columns=FINAL_COLUMNS)


def save_all(df: pd.DataFrame):
    """Split by category, dedup, and save each as CSV + formatted XLSX."""
    for cat_name, (xlsx_name, csv_name, sheet_title) in CATEGORY_FILES.items():
        cat_df = df[df["Product Category"] == cat_name].copy().reset_index(drop=True)
        if cat_df.empty:
            continue

        cat_df = clean_dataframe(cat_df.to_dict(orient="records"))

        # CSV
        cat_df.to_csv(OUT_DIR / csv_name, index=False, encoding="utf-8-sig")

        # Excel
        xlsx_path = OUT_DIR / xlsx_name
        try:
            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                cat_df.to_excel(writer, index=False, sheet_name=sheet_title)
                format_excel_sheet(writer.sheets[sheet_title], cat_df)
            logger.info(f"Saved {len(cat_df)} rows -> {xlsx_name}")
        except PermissionError:
            fallback = OUT_DIR / f"{xlsx_path.stem}_Updated.xlsx"
            with pd.ExcelWriter(fallback, engine="openpyxl") as writer:
                cat_df.to_excel(writer, index=False, sheet_name=sheet_title)
                format_excel_sheet(writer.sheets[sheet_title], cat_df)
            logger.info(f"(File locked) Saved {len(cat_df)} rows -> {fallback.name}")


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 1 — Deep Scraping
# ──────────────────────────────────────────────────────────────────────────────

def phase1_deep_scrape(existing_df: pd.DataFrame) -> pd.DataFrame:
    logger.info("\n" + "="*70)
    logger.info("PHASE 1 — DEEP SCRAPING (max pages per keyword, both sites)")
    logger.info("="*70)

    ei_scraper   = ExportersIndiaScraper()
    ajio_scraper = AjioScraper()

    all_records = existing_df.to_dict(orient="records")
    total_tasks = sum(len(kws) for kws in PRODUCT_TAXONOMY.values())
    task_num = 0

    for category, keywords in PRODUCT_TAXONOMY.items():
        logger.info(f"\n{'='*70}\nCATEGORY: {category.upper()} ({len(keywords)} keywords)\n{'='*70}")
        for kw in keywords:
            task_num += 1
            logger.info(f"\n[{task_num}/{total_tasks}] Keyword: '{kw}' | Category: '{category}'")

            # ---- Ajio ----
            try:
                logger.info(f"  >> Ajio (up to {MAX_PAGES_AJIO} pages)...")
                items = ajio_scraper.run(
                    query=kw, category=category,
                    max_pages=MAX_PAGES_AJIO, enrich_details=False
                )
                logger.info(f"  >> Ajio returned {len(items)} items")
                all_records.extend(items)
            except Exception as e:
                logger.error(f"Ajio error for '{kw}': {e}", exc_info=True)

            # ---- ExportersIndia ----
            try:
                logger.info(f"  >> ExportersIndia (up to {MAX_PAGES_EI} pages)...")
                items = ei_scraper.run(
                    query=kw, category=category,
                    max_pages=MAX_PAGES_EI, enrich_details=False
                )
                logger.info(f"  >> ExportersIndia returned {len(items)} items")
                all_records.extend(items)
            except Exception as e:
                logger.error(f"ExportersIndia error for '{kw}': {e}", exc_info=True)

            # Checkpoint after each keyword
            merged_df = clean_dataframe(all_records)
            save_all(merged_df)
            logger.info(f"  Checkpoint: {len(merged_df)} unique clean records total")

    final_df = clean_dataframe(all_records)
    logger.info(f"\nPhase 1 complete. Total unique records: {len(final_df)}")
    return final_df


# ──────────────────────────────────────────────────────────────────────────────
# PHASE 2 — Enrich ALL remaining unenriched brands
# ──────────────────────────────────────────────────────────────────────────────

def _is_empty(val) -> bool:
    return pd.isna(val) or str(val).strip() in ("", "nan", "N/A", "n/a")


def phase2_enrich(df: pd.DataFrame) -> pd.DataFrame:
    logger.info("\n" + "="*70)
    logger.info("PHASE 2 — ENRICHMENT PASS (all brands missing email/phone)")
    logger.info("="*70)

    enricher = LeadEnricher()

    # Target: brands that are missing email OR phone
    mask = df["Contact Email"].apply(_is_empty) | df["Phone Number"].apply(_is_empty)
    needs_enrich = df[mask].copy()
    already_done = df[~mask].copy()

    logger.info(f"Brands needing enrichment : {len(needs_enrich)}")
    logger.info(f"Brands already enriched   : {len(already_done)}")

    enriched_rows = []
    total = len(needs_enrich)

    for i, (idx, row) in enumerate(needs_enrich.iterrows(), 1):
        brand_name   = str(row.get("Brand Name", "")).strip()
        company_name = str(row.get("Company Name", "")).strip()
        location     = str(row.get("City & State", "")).strip()

        if i % 50 == 0 or i == 1:
            logger.info(f"  Enriching {i}/{total}: '{brand_name}'")

        try:
            result = enricher.enrich(brand_name, company_name, location)
            row = row.copy()

            if _is_empty(row.get("Seller/Brand Website")) and result.get("website"):
                row["Seller/Brand Website"] = result["website"]
            if _is_empty(row.get("Contact Email")) and result.get("email"):
                row["Contact Email"] = result["email"]
            if _is_empty(row.get("Phone Number")) and result.get("phone"):
                row["Phone Number"] = result["phone"]
            if _is_empty(row.get("LinkedIn")) and result.get("linkedin"):
                row["LinkedIn"] = result["linkedin"]
            if _is_empty(row.get("City & State")) and result.get("city_state"):
                row["City & State"] = result["city_state"]

        except Exception as e:
            logger.debug(f"Enrichment error for '{brand_name}': {e}")

        enriched_rows.append(row)

        # Checkpoint every 100 enrichments
        if i % 100 == 0:
            partial = pd.concat(
                [already_done, pd.DataFrame(enriched_rows)], ignore_index=True
            )
            save_all(partial)
            logger.info(f"  Enrichment checkpoint saved at {i}/{total}")

    enriched_df = pd.DataFrame(enriched_rows)
    final = pd.concat([already_done, enriched_df], ignore_index=True)
    final = clean_dataframe(final.to_dict(orient="records"))

    email_filled = final["Contact Email"].apply(lambda x: not _is_empty(x)).sum()
    phone_filled = final["Phone Number"].apply(lambda x: not _is_empty(x)).sum()
    logger.info(f"\nPhase 2 complete.")
    logger.info(f"  Emails filled : {email_filled} / {len(final)} ({email_filled/len(final)*100:.1f}%)")
    logger.info(f"  Phones filled : {phone_filled} / {len(final)} ({phone_filled/len(final)*100:.1f}%)")
    return final


# ──────────────────────────────────────────────────────────────────────────────
# MAIN
# ──────────────────────────────────────────────────────────────────────────────

def main():
    start = datetime.now()
    logger.info(f"Deep scrape + enrich started at {start.strftime('%Y-%m-%d %H:%M:%S')}")

    existing_df = load_existing()
    merged_df   = phase1_deep_scrape(existing_df)
    final_df    = phase2_enrich(merged_df)

    save_all(final_df)

    elapsed = datetime.now() - start
    logger.info(f"\n{'='*70}")
    logger.info("ALL DONE!")
    logger.info(f"Total unique records : {len(final_df)}")
    logger.info(f"Time elapsed         : {elapsed}")
    logger.info("="*70)

    print("\n" + "="*60)
    print("FINAL SUMMARY")
    print("="*60)
    for cat in ["Haircare", "Skincare", "Herbal"]:
        sub = final_df[final_df["Product Category"] == cat]
        if len(sub) == 0:
            continue
        emails = sub["Contact Email"].apply(lambda x: not _is_empty(x)).sum()
        phones = sub["Phone Number"].apply(lambda x: not _is_empty(x)).sum()
        print(f"\n  {cat}: {len(sub)} brands")
        print(f"    Email  : {emails} ({emails/len(sub)*100:.1f}%)")
        print(f"    Phone  : {phones} ({phones/len(sub)*100:.1f}%)")
    print("="*60)


if __name__ == "__main__":
    main()
