"""
utils/logger.py
---------------
Configures logging for the scraping application.
Outputs formatted logs both to stdout (console) and to a file in the logs/ directory.
"""

import sys
import logging
from pathlib import Path
from config import LOG_DIR, BASE_DIR

def setup_logger(name: str = "rose_water_scraper", log_level: str = "INFO") -> logging.Logger:
    """
    Sets up and returns a configured logger instance.
    
    Args:
        name (str): Name of the logger module.
        log_level (str): Logging level string (e.g. 'INFO', 'DEBUG', 'WARNING').
        
    Returns:
        logging.Logger: Configured logger.
    """
    # Create logs directory if it does not exist
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    log_file_path = LOG_DIR / "scraper.log"

    # Get or create logger
    logger = logging.getLogger(name)
    
    # Avoid adding duplicate handlers if setup_logger is called multiple times
    if logger.hasHandlers():
        return logger

    # Set logging level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)
    logger.setLevel(numeric_level)

    # Common log message format: timestamp | level | logger_name | message
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console handler (prints to standard output)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)
    logger.addHandler(console_handler)

    # 2. File handler (appends logs to logs/scraper.log)
    file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)
    logger.addHandler(file_handler)

    return logger
