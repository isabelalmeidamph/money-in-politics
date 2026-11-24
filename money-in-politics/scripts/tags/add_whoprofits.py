"""Add the Who Profits 'Database of Complicit Companies' as tag whoprofits.

Usage: python3 -I add_whoprofits.py whoprofits.csv company_tags.csv investigate.xlsx
whoprofits.csv comes from parse_whoprofits.py. Who Profits gives exchanges but not tickers;
tickers come from the Investigate spreadsheet (matched by name) and the overrides below.
"""
import csv
import re
import sys

import openpyxl

WP, TAGS, XLSX = sys.argv[1:4]
URL = "https://www.whoprofits.org/companies"
US_EXCH = {"NYSE", "NASDAQ", "Nasdaq"}
EXCH = {"NASDAQ": "Nasdaq", "TKS": "Tokyo", "ETR": "Xetra", "MIL": "Milan", "PAR": "Paris", "STO": "Stockholm",
        "SWX": "SIX Swiss", "BRU": "Brussels", "LSE": "London", "SHENZHEN": "Shenzhen", "MEX": "Mexico",
        "XETRA German Electronic Exchange": "Xetra", "ASX": "ASX"}

# n -> dict of fields to set; "drop_match" discards a wrong name match
OVERRIDE = {
    11: dict(status="subsidiary", parent="Booking Holdings (Nasdaq: BKNG)"),
    21: dict(status="public", ticker="TUI1", exch="Xetra", note="Also listed in London"),
    22: dict(drop_match=True, status="subsidiary", note="Operated in Israel under the Carrefour brand; parent not identified"),
    23: dict(status="public", ticker="PHOE", exch="TASE"),
    26: dict(status="public", ticker="ORCL", exch="NYSE", us="ORCL"),
    30: dict(exch="Nasdaq"),
    31: dict(status="public", ticker="AMZN", exch="Nasdaq", us="AMZN"),
    32: dict(status="public", ticker="GOOGL", exch="Nasdaq", us="GOOGL;GOOG"),
    36: dict(status="public", ticker="LUMI", exch="TASE"),
    39: dict(status="public", ticker="MGDL", exch="TASE"),
    44: dict(status="public", ticker="HARL", exch="TASE"),
    52: dict(status="public", ticker="MAERSK B", exch="Copenhagen"),
    66: dict(status="public", ticker="SYENS", exch="Brussels"),
    73: dict(status="public", ticker="PAZ", exch="TASE", note="Paz Retail and Energy"),
    74: dict(note="No longer on the NYSE; US trades would be the OTC ADR"),
    79: dict(ticker="CNH", exch="NYSE", us="CNH", note="Now listed only on the NYSE"),
    81: dict(status="public", ticker="GE", exch="NYSE", us="GE", note="Now GE Aerospace; decide whether spin-offs (GEV, GEHC) count"),
    94: dict(status="public", ticker="CAF", exch="Madrid"),
    98: dict(status="public", note="Who Profits leaves Traded In blank; ZIM is NYSE-listed"),
    100: dict(exch="Nasdaq", us="ESLT", note="Also listed in Tel Aviv"),
    103: dict(status="subsidiary", parent="Traton (Frankfurt: 8TRA)"),
    106: dict(status="subsidiary", parent="CMA CGM (unlisted)"),
    116: dict(us="TEVA", note="Also listed in Tel Aviv"),
    120: dict(status="public", note="Who Profits leaves Traded In blank"),
    125: dict(status="public", ticker="YAAC", exch="TASE"),
    135: dict(status="public", ticker="ORON", exch="TASE"),
    143: dict(status="public", ticker="RMLI", exch="TASE"),
    172: dict(status="public", ticker="AMRK", exch="TASE"),
    181: dict(status="subsidiary", parent="Canon (Tokyo: 7751)"),
    184: dict(status="subsidiary", parent="Minerals Technologies (NYSE: MTX)", note="Who Profits lists Nasdaq; the parent trades on the NYSE"),
    208: dict(status="subsidiary", parent="Tata Motors (NSE)", note="Check the parent's ticker after Tata Motors' 2025 demerger"),
    242: dict(drop_match=True, status="subsidiary", parent="Sun Pharmaceutical (NSE: SUNPHARMA)", note="Taken private by Sun Pharma in 2024; TARO trades before then count"),
    216: dict(us="SONY", note="Also listed in Tokyo"),
    245: dict(us="PRGO"),
    248: dict(status="subsidiary", parent="Kardan N.V. (TASE: KRNV)"),
    256: dict(status="subsidiary", parent="Jain Irrigation Systems (NSE)"),
    284: dict(status="subsidiary", parent="Oshkosh (NYSE: OSK)"),
    318: dict(status="subsidiary", parent="Genie Energy (NYSE: GNE)"),
    319: dict(status="public", ticker="MTU", exch="Paris"),
    331: dict(status="merged", note="Merged into L3Harris (NYSE: LHX) in 2019; old LLL trades would match"),
    345: dict(status="subsidiary", parent="Ashtrom Group (TASE: ASHG)", note="Now Ashtrom Residential Development"),
    399: dict(status="subsidiary", parent="Orbia (Mexico: ORBIA)"),
    404: dict(status="public", ticker="AVIV", exch="TASE"),
    411: dict(status="subsidiary", parent="OSI Systems (Nasdaq: OSIS)"),
    426: dict(status="state-owned", note="Spanish state company"),
    447: dict(status="public", ticker="002459", exch="Shenzhen", note="Left Nasdaq in 2018; now JA Solar Technology in Shenzhen"),
    453: dict(status="defunct", note="Bankrupt and delisted in 2013"),
    461: dict(status="public", ticker="ANGL", exch="TASE"),
}
PAD = {"Shenzhen": 6, "KRX": 6}


def norm(s):
    s = s.lower().replace("’", "'").replace("-", " ")
    s = re.sub(r"\(.*?\)", "", s)
    s = re.sub(r"\b(ltd|inc|plc|sa|s\.a|s\.p\.a|spa|ag|nv|n\.v|corp|corporation|company|co|the|group|holdings?|hldgs|"
               r"international|intl|industries|indus|systems|solns|technologies|tech|israel|israeli|bank|limited|"
               r"enterprises|ab|llc)\b\.?", "", s)
    return re.sub(r"[^a-z0-9]", "", s)


wb = openpyxl.load_workbook(XLSX, read_only=True)
inv = {}
for r in list(wb.active.iter_rows(values_only=True))[1:]:
    if r[0]:
        for nm in (r[0], r[1]):
            if nm and norm(nm):
                inv.setdefault(norm(nm), (str(r[3]).strip(), (r[4] or "").strip(), (r[7] or "").strip()))
isin_by_ticker = {v[0]: v[2] for v in inv.values()}

with open(TAGS, newline="") as f:
    reader = csv.DictReader(f)
    fields = list(reader.fieldnames)
    existing = [r for r in reader if r["tag_id"] != "whoprofits"]
known_us = {r["primary_ticker"]: r["us_tickers"] for r in existing if r["primary_ticker"] and r["us_tickers"]}


def base_status(traded):
    t = traded.lower()
    if "subsidiary of public" in t:
        return "subsidiary"
    if t == "private":
        return "private"
    if t == "cooperative":
        return "cooperative"
    if not t:
        return "unverified"  # Who Profits left "Traded In" blank
    return "public"


new = []
for w in csv.DictReader(open(WP)):
    n = int(w["n"])
    o = OVERRIDE.get(n, {})
    status, tic, exch, us, isin, notes = base_status(w["traded_in"]), "", "", "", "", []
    m = None if o.get("drop_match") or status in ("private", "cooperative") else inv.get(norm(w["name"]))
    if m:
        tic, exch, isin = m[0], EXCH.get(m[1], m[1]), m[2]
        if exch in PAD and tic.isdigit():
            tic = tic.zfill(PAD[exch])
    status = o.get("status", status)
    tic, exch = o.get("ticker", tic), o.get("exch", exch)
    us = o.get("us", tic if exch in US_EXCH else known_us.get(tic, ""))
    parent = o.get("parent", "")
    if o.get("note"):
        notes.append(o["note"])
    if status == "public" and not tic:
        notes.append("Ticker not filled in")
    if status == "subsidiary" and not parent:
        notes.append("Who Profits says its parent is public; parent not identified")
    new.append({
        "tag_id": "whoprofits", "company": w["name"], "listing_status": status, "primary_ticker": tic,
        "primary_exchange": exch, "us_tickers": us, "parent_company": parent, "source_type": w["traded_in"],
        "source_location": w["hq"], "source_category": w["involvement"], "review_note": "; ".join(notes),
        "isin": isin or isin_by_ticker.get(tic, ""), "source_url": URL,
        "source_summary": f"Sector: {w['sector']}. Region: {w['region']}. Revenue: {w['revenue'] or 'n/a'}.",
    })

with open(TAGS, "w", newline="") as f:
    wr = csv.DictWriter(f, fieldnames=fields, restval="")
    wr.writeheader()
    wr.writerows(existing + new)

from collections import Counter
print(len(new), Counter(r["listing_status"] for r in new), "US tickers:", sum(1 for r in new if r["us_tickers"]))
print("US-listed parents:", sum(1 for r in new if any(x in r["parent_company"] for x in ("NYSE", "Nasdaq"))))
print("public without ticker:", [r["company"] for r in new if r["listing_status"] == "public" and not r["primary_ticker"]])
