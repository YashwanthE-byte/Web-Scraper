"""
run_full_scraper.py
-------------------
Comprehensive runner to scrape all possible data from both ExportersIndia and Ajio
across all 3 product categories (Haircare, Skincare, Herbal), validate against junk/random data,
remove duplicates, and generate 3 clean, organized Excel workbooks and CSV files.
"""

import os
import sys
import time
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

import pandas as pd

from config import (
    PRODUCT_TAXONOMY,
    BASE_DIR,
    FINAL_COLUMNS,
    CACHE_FILE
)
from scrapers.exportersindia_scraper import ExportersIndiaScraper
from scrapers.ajio_scraper import AjioScraper
from utils.cleaner import clean_dataframe
from utils.exporter import format_excel_sheet
from utils.logger import setup_logger

logger = setup_logger("full_scraper")


def save_categorized_workbooks(df_all: pd.DataFrame, out_dir: Path):
    """
    Saves clean, formatted categorized Excel workbooks and CSVs for Haircare, Skincare, and Herbal.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    
    categories = [
        ("Haircare", "Haircare_Leads.xlsx", "Haircare_Leads.csv", "Haircare Leads"),
        ("Skincare", "Skincare_Leads.xlsx", "Skincare_Leads.csv", "Skincare Leads"),
        ("Herbal", "Herbal_Leads.xlsx", "Herbal_Leads.csv", "Herbal Leads")
    ]
    
    for cat_name, xlsx_name, csv_name, sheet_title in categories:
        cat_df = df_all[df_all["Product Category"] == cat_name].copy().reset_index(drop=True)
        if cat_df.empty:
            continue
            
        # Clean and deduplicate category slice
        cat_df = clean_dataframe(cat_df.to_dict(orient="records"))
        
        # Save CSV
        csv_path = out_dir / csv_name
        cat_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        
        # Save Excel with formatting
        xlsx_path = out_dir / xlsx_name
        try:
            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                cat_df.to_excel(writer, index=False, sheet_name=sheet_title)
                format_excel_sheet(writer.sheets[sheet_title], cat_df)
        except PermissionError:
            fallback_xlsx = out_dir / f"{xlsx_path.stem}_Updated.xlsx"
            with pd.ExcelWriter(fallback_xlsx, engine="openpyxl") as writer:
                cat_df.to_excel(writer, index=False, sheet_name=sheet_title)
                format_excel_sheet(writer.sheets[sheet_title], cat_df)
            xlsx_name = fallback_xlsx.name
            
        ajio_n = (cat_df["Marketplace"] == "Ajio").sum()
        ei_n = (cat_df["Marketplace"] == "ExportersIndia").sum()
        logger.info(f"Updated {xlsx_name}: Total {len(cat_df)} leads (Ajio: {ajio_n}, ExportersIndia: {ei_n})")


def run_full_pipeline(max_pages_ei: int = 10, max_pages_ajio: int = 15, enrich: bool = True):
    """
    Runs the comprehensive scraping loop across all categories and keywords.
    """
    out_dir = BASE_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Load existing historical data if any to combine and deduplicate
    existing_records: List[Dict[str, Any]] = []
    for csv_file in ["Haircare_Leads.csv", "Skincare_Leads.csv", "Herbal_Leads.csv"]:
        p = out_dir / csv_file
        if p.exists():
            try:
                old_df = pd.read_csv(p)
                existing_records.extend(old_df.to_dict(orient="records"))
                logger.info(f"Loaded existing {len(old_df)} records from {csv_file}")
            except Exception as e:
                logger.warning(f"Could not load {csv_file}: {e}")
                
    logger.info(f"Total baseline existing records loaded: {len(existing_records)}")
    
    ei_scraper = ExportersIndiaScraper()
    ajio_scraper = AjioScraper()
    
    all_collected = existing_records.copy()
    
    total_tasks = sum(len(kws) for kws in PRODUCT_TAXONOMY.values())
    task_num = 0
    
    for category, keywords in PRODUCT_TAXONOMY.items():
        logger.info(f"\n{'='*75}\nSTARTING CATEGORY: [{category.upper()}] ({len(keywords)} keywords)\n{'='*75}")
        
        for kw in keywords:
            task_num += 1
            logger.info(f"\n[{task_num}/{total_tasks}] Processing Keyword: '{kw}' for Category: '{category}'")
            
            # --- Scrape Ajio ---
            try:
                logger.info(f">> Scraping Ajio for '{kw}' (up to {max_pages_ajio} pages)...")
                ajio_items = ajio_scraper.run(
                    query=kw,
                    category=category,
                    max_pages=max_pages_ajio,
                    enrich_details=enrich
                )
                logger.info(f">> Ajio returned {len(ajio_items)} items for '{kw}'.")
                all_collected.extend(ajio_items)
            except Exception as e:
                logger.error(f"Error scraping Ajio for '{kw}': {e}", exc_info=True)
                
            # --- Scrape ExportersIndia ---
            try:
                logger.info(f">> Scraping ExportersIndia for '{kw}' (up to {max_pages_ei} pages)...")
                ei_items = ei_scraper.run(
                    query=kw,
                    category=category,
                    max_pages=max_pages_ei,
                    enrich_details=enrich
                )
                logger.info(f">> ExportersIndia returned {len(ei_items)} items for '{kw}'.")
                all_collected.extend(ei_items)
            except Exception as e:
                logger.error(f"Error scraping ExportersIndia for '{kw}': {e}", exc_info=True)
                
            # Clean and checkpoint save after each keyword
            clean_df = clean_dataframe(all_collected)
            save_categorized_workbooks(clean_df, out_dir)
            logger.info(f"Checkpoint saved: Current total unique clean records = {len(clean_df)}")
            
    # Final cleanup and save
    final_df = clean_dataframe(all_collected)
    save_categorized_workbooks(final_df, out_dir)
    
    logger.info("\n" + "="*75)
    logger.info("FULL SCRAPING AND ENRICHMENT COMPLETE!")
    logger.info(f"Final Total Unique Records: {len(final_df)}")
    logger.info("="*75)


if __name__ == "__main__":
    run_full_pipeline(max_pages_ei=10, max_pages_ajio=15, enrich=True)
