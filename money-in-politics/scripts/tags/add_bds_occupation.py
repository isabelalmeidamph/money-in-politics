"""Add AFSC Investigate 'Occupations' companies to company_tags.csv as tag bds_occupation."""
import csv
import sys

import openpyxl

XLSX, TAGS = sys.argv[1], sys.argv[2]

PAD = {"KRX": 6, "SHENZHEN": 6, "SHE": 6, "SHG": 6, "HKG": 4}
EXCH_NAMES = {
    "XETRA German Electronic Exchange": "ETR",
    "TSE": "TSX",  # WSP Global is Toronto-listed
}
US_EXCH = {"NYSE", "NASDAQ", "OTCQB", "AMEX", "NYSE American"}
NOTES = {
    "Primo Water": "Merged into Primo Brands (PRMB) in Nov 2024; decide whether PRMB trades count",
    "CNH Industrial": "Now listed only on the NYSE as CNH",
    "Kardan": "Source HQ is the Netherlands; listed in Tel Aviv",
}

wb = openpyxl.load_workbook(XLSX, read_only=True)
rows = list(wb.active.iter_rows(values_only=True))
head, body = rows[0], rows[1:]
src = [dict(zip(head, r)) for r in body if r[0]]

with open(TAGS, newline="") as f:
    reader = csv.DictReader(f)
    fields = list(reader.fieldnames)
    existing = list(reader)
for extra in ("isin", "source_url", "source_summary"):
    if extra not in fields:
        fields.append(extra)

# reuse US tickers already worked out for the BDS list (matched on primary ticker)
known_us = {r["primary_ticker"]: r["us_tickers"] for r in existing if r["primary_ticker"] and r["us_tickers"]}

existing = [r for r in existing if r["tag_id"] != "bds_occupation"]
new = []
for r in src:
    if not r["Occupations"]:
        continue
    exch = (r["Primary Exchange Short"] or "").strip()
    exch = EXCH_NAMES.get(exch, exch)
    sym = str(r["Primary Symbol"] or "").strip()
    if exch in PAD and sym.isdigit():
        sym = sym.zfill(PAD[exch])
    us = sym if exch in US_EXCH else known_us.get(sym, "")
    new.append({
        "tag_id": "bds_occupation",
        "company": r["Company Short Name"].strip(),
        "listing_status": "public",
        "primary_ticker": sym,
        "primary_exchange": exch,
        "us_tickers": us,
        "parent_company": "",
        "source_type": "",
        "source_location": (r["Country of HQ"] or "").strip(),
        "source_category": (r["Industry"] or "").strip(),
        "review_note": NOTES.get(r["Company Short Name"].strip(), ""),
        "isin": (r["Primary ISIN"] or "").strip(),
        "source_url": (r["Link"] or "").strip(),
        "source_summary": " ".join((r["Summary"] or "").split()),
    })

with open(TAGS, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, restval="")
    w.writeheader()
    w.writerows(existing + new)

print(f"bds_occupation rows: {len(new)}; with US tickers: {sum(1 for r in new if r['us_tickers'])}")
