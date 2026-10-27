"""
scrapers package
----------------
Contains base scraper class and target site implementations (ExportersIndia, Ajio).
"""

from .base_scraper import BaseScraper
from .exportersindia_scraper import ExportersIndiaScraper
from .ajio_scraper import AjioScraper

__all__ = ["BaseScraper", "ExportersIndiaScraper", "AjioScraper"]
