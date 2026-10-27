"""
Diagnose the supplier profile page on ExportersIndia.
"""
import sys
from pathlib import Path
BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR))

import requests
from bs4 import BeautifulSoup
from utils.cleaner import extract_phones, extract_emails

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# Supplier profile page
url = "https://www.exportersindia.com/shreejiperfumerscontractors/"
print(f"URL: {url}")
resp = requests.get(url, headers=HEADERS, timeout=15)
print(f"Status: {resp.status_code}")

soup = BeautifulSoup(resp.text, "html.parser")
text = soup.get_text(separator=" ", strip=True)

print("\n--- PHONES in page text ---")
phones = extract_phones(text)
print(phones if phones else "NONE FOUND")

print("\n--- EMAILS in page text ---")
emails = extract_emails(text)
print(emails if emails else "NONE FOUND")

print("\n--- tel: links ---")
for a in soup.select("a[href^='tel:']"):
    print(" ", a.get("href"))

print("\n--- mailto: links ---")
for a in soup.select("a[href^='mailto:']"):
    print(" ", a.get("href"))

print("\n--- Full page text (first 4000 chars) ---")
print(text[:4000])

# Now let's also try the /contact-us subpage
print("\n\n" + "="*60)
url2 = "https://www.exportersindia.com/shreejiperfumerscontractors/contact-us.htm"
print(f"URL: {url2}")
resp2 = requests.get(url2, headers=HEADERS, timeout=15)
print(f"Status: {resp2.status_code}")
if resp2.status_code == 200:
    soup2 = BeautifulSoup(resp2.text, "html.parser")
    text2 = soup2.get_text(separator=" ", strip=True)
    print("\n--- PHONES ---")
    print(extract_phones(text2) or "NONE")
    print("\n--- EMAILS ---")
    print(extract_emails(text2) or "NONE")
    print("\n--- tel: links ---")
    for a in soup2.select("a[href^='tel:']"):
        print(" ", a.get("href"))
    print("\n--- Full text (first 3000 chars) ---")
    print(text2[:3000])
