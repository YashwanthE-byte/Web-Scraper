"""
fetch_rosewater_contacts.py
============================
Fetches phone numbers and emails for all 638 entries in the first rose water
scraped dataset: multi_3_keywords_all_20261003_184545.csv

STRATEGY (after diagnosing ExportersIndia):
  ExportersIndia hides ALL supplier contacts behind login wall.
  So for BOTH ExportersIndia AND Ajio rows we use:
    1. Extract supplier slug from EI product page -> use as Bing search hint
    2. OSINT LeadEnricher: Bing search company name -> find official website -> crawl for contacts
    3. Also directly try common contact page patterns on official website

Output:
  output/RoseWater_Leads_With_Contacts.xlsx  (4-tab premium Excel)
  output/RoseWater_Leads_With_Contacts.csv
"""

import sys
import time
import re
import json
from pathlib import Path
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urljoin, urlparse

import requests
import pandas as pd
from bs4 import BeautifulSoup
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

from utils.cleaner import extract_phones, extract_emails
from utils.enricher import LeadEnricher
from utils.logger import setup_logger

# ------------------------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------------------------
INPUT_FILE  = BASE_DIR / "output" / "multi_3_keywords_all_20261003_184545.csv"
OUTPUT_BASE = BASE_DIR / "output" / "RoseWater_Leads_With_Contacts"
CACHE_FILE  = BASE_DIR / "output" / "rosewater_contact_cache.json"
EI_CACHE    = BASE_DIR / "output" / "brand_enrichment_cache.json"

MAX_WORKERS     = 4     # keep lower to be polite to Bing
REQUEST_TIMEOUT = 10
SAVE_EVERY      = 50

logger = setup_logger("rw_contacts")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}


# ------------------------------------------------------------------------------
# CONTACT CACHE
# ------------------------------------------------------------------------------

class ContactCache:
    def __init__(self, path: Path):
        self.path = path
        self.data: dict = {}
        self._load()

    def _load(self):
        if self.path.exists():
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
                logger.info(f"Loaded {len(self.data)} cached entries from {self.path.name}")
            except Exception as e:
                logger.warning(f"Cache load failed: {e}")

    def save(self):
        try:
            snapshot = dict(self.data)  # thread-safe copy before serialising
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.warning(f"Cache save failed: {e}")

    def get(self, key: str):
        return self.data.get(key)

    def set(self, key: str, value: dict):
        self.data[key] = value
        self.save()


contact_cache = ContactCache(CACHE_FILE)
enricher = LeadEnricher(cache_path=EI_CACHE)


# ------------------------------------------------------------------------------
# HTTP HELPERS
# ------------------------------------------------------------------------------

def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(HEADERS)
    return s


def safe_get(session: requests.Session, url: str, retries: int = 2) -> str:
    """Fetch URL with retries, returns HTML text or empty string."""
    for attempt in range(retries + 1):
        try:
            resp = session.get(url, timeout=REQUEST_TIMEOUT)
            if resp.status_code == 200:
                return resp.text
            elif resp.status_code in (403, 404):
                return ""
        except Exception as e:
            if attempt < retries:
                time.sleep(1.5)
            else:
                logger.debug(f"Failed to fetch {url}: {e}")
    return ""


# ------------------------------------------------------------------------------
# EXTRACT SUPPLIER SLUG FROM EI PRODUCT PAGE
# (e.g. "shreejiperfumerscontractors" from product page links)
# ------------------------------------------------------------------------------

def get_ei_supplier_slug(session: requests.Session, product_url: str) -> str:
    """
    Fetches an EI product page and extracts the supplier profile slug.
    e.g. https://www.exportersindia.com/shreejiperfumerscontractors/
    Returns the slug string (without slashes) or empty string.
    """
    html = safe_get(session, product_url)
    if not html:
        return ""

    soup = BeautifulSoup(html, "html.parser")
    slug_pattern = re.compile(
        r"https?://(?:www\.)?exportersindia\.com/([a-z0-9\-]+)/?$",
        re.IGNORECASE
    )
    for a in soup.select("a[href]"):
        href = a.get("href", "")
        m = slug_pattern.match(href)
        if m:
            slug = m.group(1)
            # Skip generic EI pages
            skip = {
                "search", "register-business-online", "post-buy-requirement",
                "indian-manufacturers", "b2b-marketplace", "contact-us",
                "about-us", "sitemap", "advertise", "feedback", "disclaimer",
                "terms-conditions", "privacy-policy", "live-coverage",
                "web-stories", "testimonials"
            }
            if slug.lower() not in skip and len(slug) > 5:
                return slug

    return ""


# ------------------------------------------------------------------------------
# ENRICH A SINGLE ROW (both EI and Ajio via OSINT)
# ------------------------------------------------------------------------------

def enrich_row(session: requests.Session, row: pd.Series) -> dict:
    """
    Main enrichment function for a single row.
    Returns dict: {"Phone": str, "Email": str}
    """
    source  = str(row.get("Source", "")).strip()
    company = str(row.get("Company", "")).strip()
    url     = str(row.get("URL", "")).strip()

    # Cache key: company name (normalized)
    cache_key = re.sub(r"\s+", "_", company.lower().strip())[:80]

    cached = contact_cache.get(cache_key)
    if cached:
        return cached

    result = {"Phone": "", "Email": ""}

    # Skip junk / generic company names that will never yield real contacts
    JUNK_NAMES = {
        "nan", "n/a", "", "industry", "industries", "trader", "traders",
        "seller", "supplier", "manufacturer", "exporter", "company",
        "brand", "store", "shop", "enterprise", "enterprises"
    }
    if not company or company.lower().strip() in JUNK_NAMES or len(company.strip()) < 4:
        contact_cache.set(cache_key, result)
        return result

    # ── For ExportersIndia: try to get a better company name hint from slug ──
    slug_hint = ""
    if source == "ExportersIndia" and url.startswith("http"):
        slug_hint = get_ei_supplier_slug(session, url)
        # Convert slug like "shreejiperfumerscontractors" to "shreeji perfumers contractors"
        # (split CamelCase / run them together — use company name as primary)

    # ── OSINT enrichment via LeadEnricher ──
    try:
        # Primary: use company name
        enriched = enricher.enrich(brand_name=company, company_name=company)
        result["Phone"] = enriched.get("phone", "")
        result["Email"] = enriched.get("email", "")

        # If no contacts found and we have a slug, try slug-derived search
        if not result["Phone"] and not result["Email"] and slug_hint:
            # Try humanizing the slug: insert spaces before capital-ish transitions
            slug_readable = re.sub(r"([a-z])([A-Z])", r"\1 \2", slug_hint)
            slug_readable = slug_readable.replace("-", " ").strip()
            enriched2 = enricher.enrich(brand_name=slug_readable, company_name=company)
            result["Phone"] = enriched2.get("phone", "")
            result["Email"] = enriched2.get("email", "")

    except Exception as e:
        logger.debug(f"Enrichment failed for '{company}': {e}")

    contact_cache.set(cache_key, result)
    return result


# ------------------------------------------------------------------------------
# WORKER
# ------------------------------------------------------------------------------

def process_row(args):
    """Worker: returns (index, phone, email)."""
    idx, row, session = args
    try:
        contacts = enrich_row(session, row)
    except Exception as e:
        logger.debug(f"Row {idx} error: {e}")
        contacts = {"Phone": "", "Email": ""}
    return idx, contacts.get("Phone", ""), contacts.get("Email", "")


# ------------------------------------------------------------------------------
# PREMIUM EXCEL EXPORT
# ------------------------------------------------------------------------------

def export_excel(df: pd.DataFrame, path: Path):
    """4-tab Excel with deep navy headers, alternating rows, blue contact cells."""
    HEADER_FILL  = PatternFill("solid", fgColor="1A1A2E")
    HEADER_FONT  = Font(bold=True, color="E0E0E0", size=11)
    ALT_FILL     = PatternFill("solid", fgColor="F0F4FF")
    BORDER_SIDE  = Side(style="thin", color="CCCCCC")
    CELL_BORDER  = Border(
        left=BORDER_SIDE, right=BORDER_SIDE,
        top=BORDER_SIDE,  bottom=BORDER_SIDE
    )
    CONTACT_FONT = Font(color="0D6EFD", size=10, bold=True)
    CONTACT_COLS = {"Phone Number", "Contact Email"}

    def style_sheet(ws, data_df: pd.DataFrame):
        # Header row
        for col_idx, col_name in enumerate(data_df.columns, 1):
            c = ws.cell(row=1, column=col_idx)
            c.fill      = HEADER_FILL
            c.font      = HEADER_FONT
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            c.border    = CELL_BORDER

        # Auto-width + data rows
        for col_idx, col_name in enumerate(data_df.columns, 1):
            col_letter = get_column_letter(col_idx)
            col_data   = data_df[col_name].fillna("").astype(str)
            max_len    = max(col_data.str.len().max() if not data_df.empty else 0, len(str(col_name)))
            ws.column_dimensions[col_letter].width = min(max_len + 4, 55)

            for row_idx in range(2, len(data_df) + 2):
                c = ws.cell(row=row_idx, column=col_idx)
                c.border    = CELL_BORDER
                c.alignment = Alignment(vertical="top", wrap_text=True)
                if row_idx % 2 == 0:
                    c.fill = ALT_FILL
                if col_name in CONTACT_COLS and c.value:
                    c.font = CONTACT_FONT

        ws.freeze_panes          = "A2"
        ws.row_dimensions[1].height = 32

    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        # Sheet 1: All
        df.to_excel(writer, index=False, sheet_name="Rose Water Leads")
        style_sheet(writer.sheets["Rose Water Leads"], df)

        # Sheet 2: Only rows with contacts
        has_c = df[
            df["Phone Number"].fillna("").str.strip().ne("") |
            df["Contact Email"].fillna("").str.strip().ne("")
        ].copy()
        if not has_c.empty:
            has_c.to_excel(writer, index=False, sheet_name="Has Contacts")
            style_sheet(writer.sheets["Has Contacts"], has_c)

        # Sheet 3: ExportersIndia
        ei = df[df["Marketplace"] == "ExportersIndia"].copy()
        if not ei.empty:
            ei.to_excel(writer, index=False, sheet_name="ExportersIndia")
            style_sheet(writer.sheets["ExportersIndia"], ei)

        # Sheet 4: Ajio
        ajio = df[df["Marketplace"] == "Ajio"].copy()
        if not ajio.empty:
            ajio.to_excel(writer, index=False, sheet_name="Ajio")
            style_sheet(writer.sheets["Ajio"], ajio)

    logger.info(f"Saved Excel -> {path.name}")


# ------------------------------------------------------------------------------
# CHECKPOINT
# ------------------------------------------------------------------------------

def checkpoint_save(df: pd.DataFrame):
    try:
        cp = OUTPUT_BASE.parent / (OUTPUT_BASE.stem + "_checkpoint.csv")
        df.to_csv(cp, index=False, encoding="utf-8-sig")
        logger.info(f"  [Checkpoint] {cp.name}")
    except Exception as e:
        logger.warning(f"Checkpoint failed: {e}")


# ------------------------------------------------------------------------------
# MAIN
# ------------------------------------------------------------------------------

def main():
    start = datetime.now()
    logger.info("=" * 70)
    logger.info("ROSE WATER CONTACT FETCHER  (OSINT Strategy)")
    logger.info(f"Input  : {INPUT_FILE.name}")
    logger.info(f"Started: {start.strftime('%Y-%m-%d %H:%M:%S')}")
    logger.info("=" * 70)

    if not INPUT_FILE.exists():
        logger.error(f"Input file not found: {INPUT_FILE}")
        sys.exit(1)

    df_raw = pd.read_csv(INPUT_FILE)
    logger.info(f"Loaded {len(df_raw)} rows")

    # Rename columns to output schema
    df = df_raw.rename(columns={
        "Source":   "Marketplace",
        "Company":  "Company Name",
        "Product":  "Product Name",
        "Location": "City & State",
        "Email":    "Contact Email",
        "Contact":  "Phone Number",
        "URL":      "Product URL",
    })

    df["Phone Number"]  = df["Phone Number"].fillna("").astype(str).str.strip()
    df["Contact Email"] = df["Contact Email"].fillna("").astype(str).str.strip()

    total = len(df)
    logger.info(f"Sources: {df['Marketplace'].value_counts().to_dict()}")

    # Rows needing enrichment
    needs_work = df[
        df["Phone Number"].eq("") | df["Contact Email"].eq("")
    ].index.tolist()
    logger.info(f"Rows to enrich: {len(needs_work)} / {total}")

    if needs_work:
        session      = make_session()
        tasks        = [(idx, df_raw.loc[idx], session) for idx in needs_work]
        done_count   = 0
        phone_count  = 0
        email_count  = 0

        logger.info(f"Starting enrichment with {MAX_WORKERS} workers...")

        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_row, t): t[0] for t in tasks}

            for future in as_completed(futures):
                idx, phone, email = future.result()
                df.at[idx, "Phone Number"]  = phone
                df.at[idx, "Contact Email"] = email

                if phone:  phone_count += 1
                if email:  email_count += 1
                done_count += 1

                if done_count % 10 == 0 or done_count == len(needs_work):
                    pct = done_count / len(needs_work) * 100
                    logger.info(
                        f"  {done_count}/{len(needs_work)} ({pct:.1f}%) | "
                        f"Phones: {phone_count} | Emails: {email_count}"
                    )

                if done_count % SAVE_EVERY == 0:
                    checkpoint_save(df)

    # Final export
    logger.info("\nExporting results...")
    csv_path  = OUTPUT_BASE.with_suffix(".csv")
    xlsx_path = OUTPUT_BASE.with_suffix(".xlsx")
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    logger.info(f"CSV saved: {csv_path.name}")
    export_excel(df, xlsx_path)

    # Summary
    elapsed     = datetime.now() - start
    tot_phone   = df["Phone Number"].str.strip().ne("").sum()
    tot_email   = df["Contact Email"].str.strip().ne("").sum()

    print("\n" + "=" * 60)
    print("ROSE WATER CONTACT FETCH -- DONE")
    print("=" * 60)
    print(f"  Total Rows      : {total}")
    print(f"  Phones Found    : {tot_phone}  ({tot_phone/total*100:.1f}%)")
    print(f"  Emails Found    : {tot_email}  ({tot_email/total*100:.1f}%)")
    print(f"  Time Elapsed    : {elapsed}")
    print(f"\n  Output:")
    print(f"    Excel  -> output/{xlsx_path.name}")
    print(f"    CSV    -> output/{csv_path.name}")
    print("=" * 60)
    for src in df["Marketplace"].unique():
        sub = df[df["Marketplace"] == src]
        ph  = sub["Phone Number"].str.strip().ne("").sum()
        em  = sub["Contact Email"].str.strip().ne("").sum()
        print(f"\n  [{src}] {len(sub)} rows")
        print(f"    Phones : {ph} ({ph/len(sub)*100:.1f}%)")
        print(f"    Emails : {em} ({em/len(sub)*100:.1f}%)")
    print("=" * 60)


if __name__ == "__main__":
    main()
