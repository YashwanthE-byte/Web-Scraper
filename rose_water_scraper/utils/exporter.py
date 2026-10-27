"""
utils/exporter.py
-----------------
Handles exporting cleaned pandas DataFrames to CSV (utf-8-sig) and multi-sheet Excel (.xlsx).
Creates a Master Leads tab plus dedicated tabs for each category (Haircare, Skincare, Herbal).
Automatically formats column widths in Excel for optimal readability.
"""

from pathlib import Path
from typing import Tuple
import pandas as pd
from utils.logger import setup_logger

logger = setup_logger("exporter")


def openpyxl_col_letter(col_idx: int) -> str:
    """Helper to convert 1-indexed column number to Excel column letters (e.g. 1 -> 'A', 2 -> 'B')."""
    result = ""
    while col_idx > 0:
        col_idx, remainder = divmod(col_idx - 1, 26)
        result = chr(65 + remainder) + result
    return result


def format_excel_sheet(worksheet, df: pd.DataFrame) -> None:
    """Auto-adjusts column widths and sets header formatting."""
    for col_idx, col_name in enumerate(df.columns, start=1):
        try:
            col_series = df[col_name].fillna("").astype(str)
            max_len = max(
                col_series.apply(lambda x: len(str(x))).max() if not df.empty else 0,
                len(str(col_name))
            )
        except Exception:
            max_len = len(str(col_name))
        col_letter = openpyxl_col_letter(col_idx)
        worksheet.column_dimensions[col_letter].width = min(max_len + 4, 60)


def export_to_csv(df: pd.DataFrame, file_path: Path) -> Path:
    """
    Exports a DataFrame to a CSV file with utf-8-sig encoding.
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(file_path, index=False, encoding="utf-8-sig")
    logger.info(f"Successfully exported {len(df)} rows to CSV: {file_path}")
    return file_path


def export_to_excel(df: pd.DataFrame, file_path: Path) -> Path:
    """
    Exports DataFrame to a multi-tab Excel (.xlsx) file:
    - Sheet 1: Master Leads (All)
    - Subsequent Sheets: Haircare, Skincare, Herbal (if present in Product Category)
    """
    file_path.parent.mkdir(parents=True, exist_ok=True)
    
    with pd.ExcelWriter(file_path, engine="openpyxl") as writer:
        # 1. Master Sheet
        df.to_excel(writer, index=False, sheet_name="Master Leads")
        format_excel_sheet(writer.sheets["Master Leads"], df)

        # 2. Individual Category Sheets
        if "Product Category" in df.columns:
            unique_categories = [c for c in df["Product Category"].unique() if c and str(c).strip()]
            for cat in unique_categories:
                sheet_name = str(cat)[:31]  # Excel max sheet name length is 31 chars
                cat_df = df[df["Product Category"] == cat]
                if not cat_df.empty:
                    cat_df.to_excel(writer, index=False, sheet_name=sheet_name)
                    format_excel_sheet(writer.sheets[sheet_name], cat_df)

    logger.info(f"Successfully exported {len(df)} rows to multi-tab Excel: {file_path}")
    return file_path


def export_data(df: pd.DataFrame, base_path: Path) -> Tuple[Path, Path]:
    """
    Exports DataFrame to both CSV and multi-sheet Excel format.
    """
    base_path.parent.mkdir(parents=True, exist_ok=True)
    
    csv_path = base_path.with_suffix(".csv") if not str(base_path).endswith(".csv") else base_path
    excel_path = base_path.with_suffix(".xlsx") if not str(base_path).endswith(".xlsx") else base_path.parent / f"{base_path.stem}.xlsx"
    
    csv_saved = export_to_csv(df, csv_path)
    excel_saved = export_to_excel(df, excel_path)
    
    return csv_saved, excel_saved
