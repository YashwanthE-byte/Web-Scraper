"""
main.py
-------
Command-line interface (CLI) entry point for the Beauty & Wellness Lead Scraper.
Orchestrates multi-category (Haircare, Skincare, Herbal) and multi-source scraping
from ExportersIndia and Ajio, enriches brand contact details (Website, Email, Phone, LinkedIn),
and exports structured outputs to CSV and multi-tab Excel workbooks.
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime
from typing import List, Tuple
import pandas as pd

from config import (
    PRODUCT_TAXONOMY,
    ALL_KEYWORDS,
    DEFAULT_CATEGORY,
    DEFAULT_QUERY,
    DEFAULT_MAX_PAGES,
    DEFAULT_OUTPUT_BASE,
    BASE_DIR,
    ENRICH_CONTACT_DETAILS
)
from scrapers.exportersindia_scraper import ExportersIndiaScraper
from scrapers.ajio_scraper import AjioScraper
from utils.cleaner import clean_dataframe
from utils.exporter import export_data
from utils.logger import setup_logger

logger = setup_logger("main")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Beauty, Haircare & Skincare Lead Scraper - Collect seller and brand intelligence from ExportersIndia & Ajio."
    )
    parser.add_argument(
        "-c", "--category",
        choices=["haircare", "skincare", "herbal", "all"],
        default=None,
        help="Run scraping for an entire product category (haircare, skincare, herbal, or all)"
    )
    parser.add_argument(
        "-q", "--query", "--keyword",
        dest="query",
        type=str,
        default=None,
        help="Search term(s). Can be a single keyword or comma-separated terms (e.g. 'Rosemary Hair Oil, Face Toner')"
    )
    parser.add_argument(
        "-p", "--max-pages",
        type=int,
        default=DEFAULT_MAX_PAGES,
        help=f"Maximum pages to scrape per website per keyword (default: {DEFAULT_MAX_PAGES})"
    )
    parser.add_argument(
        "-s", "--source",
        choices=["exportersindia", "ajio", "all"],
        default="all",
        help="Target scraping source: 'exportersindia', 'ajio', or 'all' (default: 'all')"
    )
    parser.add_argument(
        "-o", "--output-name",
        type=str,
        default=None,
        help="Custom base name for output files (default: auto-generated with timestamp)"
    )
    parser.add_argument(
        "--enrich",
        action="store_true",
        default=True,
        help="Enrich leads with website discovery, direct email, phone, and LinkedIn lookup (default: True)"
    )
    parser.add_argument(
        "--no-enrich",
        action="store_false",
        dest="enrich",
        help="Disable lead enrichment for faster raw catalog scraping"
    )
    parser.add_argument(
        "--test-proxy",
        action="store_true",
        help="Test proxy connectivity and display exit IP"
    )
    return parser.parse_args()


def build_task_list(args) -> List[Tuple[str, str]]:
    """
    Returns a list of (category, keyword) tuples based on CLI arguments.
    """
    tasks: List[Tuple[str, str]] = []

    # 1. If explicit query/keyword passed
    if args.query:
        raw_keywords = [k.strip() for k in args.query.split(",") if k.strip()]
        for kw in raw_keywords:
            # Detect category if known
            cat = "General"
            for c_name, kw_list in PRODUCT_TAXONOMY.items():
                if any(kw.lower() == k.lower() for k in kw_list):
                    cat = c_name
                    break
            tasks.append((cat, kw))
        return tasks

    # 2. If category specified
    if args.category:
        if args.category.lower() == "all":
            for cat_name, kw_list in PRODUCT_TAXONOMY.items():
                for kw in kw_list:
                    tasks.append((cat_name, kw))
        else:
            cat_key = next((c for c in PRODUCT_TAXONOMY if c.lower() == args.category.lower()), None)
            if cat_key:
                for kw in PRODUCT_TAXONOMY[cat_key]:
                    tasks.append((cat_key, kw))
        return tasks

    # 3. Default fallback: single default keyword
    tasks.append(("Haircare", DEFAULT_QUERY))
    return tasks


def main():
    args = parse_args()

    if args.test_proxy:
        from utils.proxy_manager import proxy_manager
        logger.info("Testing proxy connectivity...")
        res = proxy_manager.test_connection()
        if res.get("success"):
            print(f"\n[SUCCESS] Proxy is ACTIVE and working! Outgoing IP: {res.get('ip')}\n")
        else:
            print(f"\n[ERROR] Proxy test failed: {res.get('error')}\n")
        return

    tasks = build_task_list(args)

    logger.info("=" * 70)
    logger.info("STARTING BEAUTY & WELLNESS LEAD SCRAPER")
    logger.info(f"Target Tasks     : {len(tasks)} keyword(s)")
    logger.info(f"Target Source(s) : {args.source}")
    logger.info(f"Max Pages/Query  : {args.max_pages}")
    logger.info(f"Enrichment Mode  : {'ENABLED (Website, Email, Phone, LinkedIn)' if args.enrich else 'DISABLED'}")
    logger.info("=" * 70)

    all_raw_data = []

    ei_scraper = ExportersIndiaScraper() if args.source in ["exportersindia", "all"] else None
    ajio_scraper = AjioScraper() if args.source in ["ajio", "all"] else None

    for idx, (category, keyword) in enumerate(tasks, start=1):
        logger.info(f"\n{'#' * 70}")
        logger.info(f"TASK {idx}/{len(tasks)}: [{category.upper()}] -> '{keyword}'")
        logger.info(f"{'#' * 70}\n")

        # 1. ExportersIndia
        if ei_scraper:
            try:
                logger.info(f">>> Running ExportersIndia for '{keyword}'...")
                ei_results = ei_scraper.run(
                    query=keyword,
                    category=category,
                    max_pages=args.max_pages,
                    enrich_details=args.enrich
                )
                all_raw_data.extend(ei_results)
                logger.info(f"ExportersIndia: collected {len(ei_results)} items.")
            except Exception as err:
                logger.error(f"Error on ExportersIndia for '{keyword}': {err}", exc_info=True)

        # 2. Ajio
        if ajio_scraper:
            try:
                logger.info(f">>> Running Ajio for '{keyword}'...")
                ajio_results = ajio_scraper.run(
                    query=keyword,
                    category=category,
                    max_pages=args.max_pages,
                    enrich_details=args.enrich
                )
                all_raw_data.extend(ajio_results)
                logger.info(f"Ajio: collected {len(ajio_results)} items.")
            except Exception as err:
                logger.error(f"Error on Ajio for '{keyword}': {err}", exc_info=True)

    logger.info(f"\nTotal raw records collected across all tasks: {len(all_raw_data)}")

    # 3. Clean and Structure DataFrame
    logger.info("Cleaning, standardizing, and deduplicating records...")
    df_cleaned = clean_dataframe(all_raw_data)
    logger.info(f"Cleaned dataset contains {len(df_cleaned)} unique listings/leads.")

    # 4. Generate Output Paths
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = BASE_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.output_name:
        base_filename = args.output_name
    else:
        if args.category:
            slug = f"category_{args.category.lower()}"
        elif len(tasks) == 1:
            slug = "_".join(tasks[0][1].lower().split())
        else:
            slug = f"multi_{len(tasks)}_keywords"
        base_filename = f"{slug}_{args.source}_{timestamp}"

    base_path = out_dir / base_filename

    # 5. Export to CSV & Multi-Sheet Excel
    csv_file, excel_file = export_data(df_cleaned, base_path)

    # 6. Also update the 3 dedicated Category Workbooks
    from utils.exporter import format_excel_sheet
    categories_to_export = [
        ('Haircare', 'Haircare_Leads.xlsx', 'Haircare_Leads.csv', 'Haircare Leads'),
        ('Skincare', 'Skincare_Leads.xlsx', 'Skincare_Leads.csv', 'Skincare Leads'),
        ('Herbal', 'Herbal_Leads.xlsx', 'Herbal_Leads.csv', 'Herbal Leads')
    ]
    for cat_name, x_name, c_name, sheet_title in categories_to_export:
        cat_df = df_cleaned[df_cleaned['Product Category'] == cat_name].copy().reset_index(drop=True)
        if not cat_df.empty:
            cat_csv = out_dir / c_name
            cat_df.to_csv(cat_csv, index=False, encoding='utf-8-sig')
            cat_xlsx = out_dir / x_name
            try:
                with pd.ExcelWriter(cat_xlsx, engine='openpyxl') as writer:
                    cat_df.to_excel(writer, index=False, sheet_name=sheet_title)
                    format_excel_sheet(writer.sheets[sheet_title], cat_df)
            except PermissionError:
                fallback_xlsx = out_dir / f"{cat_xlsx.stem}_Updated.xlsx"
                with pd.ExcelWriter(fallback_xlsx, engine='openpyxl') as writer:
                    cat_df.to_excel(writer, index=False, sheet_name=sheet_title)
                    format_excel_sheet(writer.sheets[sheet_title], cat_df)

    logger.info("=" * 70)
    logger.info("[SUCCESS] Scraping & Lead Enrichment Pipeline Finished!")
    logger.info(f"Master CSV Output : {csv_file}")
    logger.info(f"Master Excel Output: {excel_file}")
    logger.info(f"Category Workbooks: Haircare_Leads.xlsx | Skincare_Leads.xlsx | Herbal_Leads.xlsx")
    logger.info(f"Total Unique Rows : {len(df_cleaned)}")
    logger.info("=" * 70)

    if not df_cleaned.empty:
        print("\n--- Preview (First 5 Rows) ---")
        preview_cols = ["Brand Name", "Product Category", "Keyword", "Seller/Brand Website", "Contact Email", "Phone Number", "LinkedIn", "Marketplace"]
        print(df_cleaned[[c for c in preview_cols if c in df_cleaned.columns]].head().to_string(index=False))


if __name__ == "__main__":
    main()
