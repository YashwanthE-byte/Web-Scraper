"""
utils package
-------------
Contains helper utilities for logging, data cleaning, normalization, and exporting files.
"""

from .logger import setup_logger
from .cleaner import clean_text, clean_dataframe, extract_phones, extract_emails
from .exporter import export_data, export_to_csv, export_to_excel
from .proxy_manager import ProxyManager, proxy_manager

__all__ = [
    "setup_logger",
    "clean_text",
    "clean_dataframe",
    "extract_phones",
    "extract_emails",
    "export_data",
    "export_to_csv",
    "export_to_excel",
    "ProxyManager",
    "proxy_manager",
]


