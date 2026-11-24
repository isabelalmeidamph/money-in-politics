"""Replace unhrc_watch_list rows with the 158 companies in Annex I of A/HRC/60/19 (Sept 2025).

Usage: python3 -I add_unhrc_watch_list_2025.py annex1.csv company_tags.csv investigate.xlsx
annex1.csv comes from parse_hrc60.py.
"""
import csv
import sys

import openpyxl

ANNEX, TAGS, XLSX = sys.argv[1:4]
URL = "https://www.ohchr.org/en/business/bhr-database"

FOOTNOTES = {
    "b": "Formerly Ashdar Building Company", "c": "Formerly Mayer Davidov Garages Ltd.",
    "d": "Formerly Chish Nofei Israel Ltd.", "e": "Formerly Naaman Group Ltd.",
    "f": "Previously listed as Lipski Installation and Sanitation Ltd.", "g": "Previously listed as Re/Max Israel",
    "h": "Formerly Shikun Dayarim Ltd.", "i": "Formerly Paz Oil Company Ltd.", "j": "Formerly Solegreen Ltd.",
    "k": "Previously listed as Angel Bakery", "l": "Previously listed as D.B.S Satellite Services Ltd.",
    "m": "Previously listed as Z.F. Development and Construction",
}

# n -> (status, ticker, exchange, us_tickers, parent, note); anything not listed is "unverified"
MARKET = {
    3: ("public", "ACS", "Madrid", "", "", "New in 2025"),
    5: ("public", "ABNB", "Nasdaq", "ABNB", "", ""),
    7: ("private", "", "", "", "", ""),
    8: ("public", "AMRK", "TASE", "", "", ""),
    10: ("public", "AMOT", "TASE", "", "", "New in 2025"),
    13: ("public", "ASHG", "TASE", "", "", ""),
    14: ("subsidiary", "", "", "", "Ashtrom Group (TASE: ASHG)", ""),
    15: ("subsidiary", "", "", "", "Ashtrom Group (TASE: ASHG)", "New in 2025"),
    16: ("public", "GAON-M", "TASE", "", "", "New in 2025"),
    17: ("public", "POLI", "TASE", "", "", ""),
    18: ("public", "LUMI", "TASE", "", "", ""),
    19: ("public", "JBNK", "TASE", "", "", ""),
    22: ("public", "BRAN", "TASE", "", "", "New in 2025"),
    25: ("public", "BEZQ", "TASE", "", "", ""),
    27: ("public", "BKNG", "Nasdaq", "BKNG", "", ""),
    28: ("subsidiary", "", "", "", "Booking Holdings (Nasdaq: BKNG)", ""),
    30: ("public", "CMER", "TASE", "", "", ""),
    33: ("public", "CEL", "TASE", "", "", ""),
    38: ("public", "CAF", "Madrid", "", "", "New in 2025"),
    42: ("public", "DNYA", "TASE", "", "", "New in 2025"),
    43: ("subsidiary", "", "", "", "Mayer's Cars and Trucks (unlisted)", ""),
    45: ("public", "DLEKG", "TASE", "", "", ""),
    46: ("public", "DELG", "TASE", "", "", ""),
    47: ("public", "DLTI", "TASE", "", "", ""),
    48: ("public", "DRAL", "TASE", "", "", ""),
    52: ("private", "", "", "", "", ""),
    53: ("subsidiary", "", "", "", "Egis (unlisted)", ""),
    55: ("public", "ELCO", "TASE", "", "", "New in 2025"),
    56: ("subsidiary", "", "", "", "Electra Group (TASE: ELTR)", ""),
    57: ("public", "ELTR", "TASE", "", "", ""),
    60: ("public", "EXPE", "Nasdaq", "EXPE", "", ""),
    61: ("public", "EXPO", "TASE", "", "", ""),
    66: ("public", "FIBI", "TASE", "", "", ""),
    67: ("public", "0656", "HKEX", "", "", "New in 2025; owns Ahava"),
    4: ("subsidiary", "", "", "", "Fosun International (HKEX: 0656)", "New in 2025"),
    75: ("public", "HAMAT", "TASE", "", "", ""),
    76: ("subsidiary", "", "", "", "Heidelberg Materials (Xetra: HEI)", "New in 2025"),
    78: ("public", "HEI", "Xetra", "", "", "New in 2025"),
    79: ("subsidiary", "", "", "", "Altice International (unlisted)", ""),
    80: ("subsidiary", "", "", "", "Altice International (unlisted)", ""),
    82: ("state-owned", "", "", "", "", "New in 2025; Spanish state company"),
    83: ("public", "DSCT", "TASE", "", "", ""),
    84: ("state-owned", "", "", "", "", ""),
    86: ("private", "", "", "", "", "Also on the BDS list"),
    92: ("public", "LAPD", "TASE", "", "", "New in 2025"),
    96: ("public", "MTRX", "TASE", "", "", ""),
    99: ("public", "MGOR", "TASE", "", "", "New in 2025"),
    100: ("state-owned", "", "", "", "", ""),
    101: ("subsidiary", "", "", "", "Israel Discount Bank (TASE: DSCT)", ""),
    108: ("public", "MVNE", "TASE", "", "", ""),
    110: ("public", "MZTF", "TASE", "", "", ""),
    112: ("public", "AVIV", "TASE", "", "", ""),
    113: ("subsidiary", "", "", "", "Motorola Solutions (NYSE: MSI)", ""),
    114: ("public", "MSI", "NYSE", "MSI", "", ""),
    120: ("public", "ORON", "TASE", "", "", "New in 2025"),
    121: ("public", "PTNR", "TASE", "PTNR", "", "Also on Nasdaq"),
    122: ("public", "PAZ", "TASE", "", "", "Also on the BDS list"),
    123: ("subsidiary", "", "", "", "Bezeq (TASE: BEZQ)", ""),
    126: ("public", "RMLI", "TASE", "", "", ""),
    127: ("subsidiary", "", "", "", "Rami Levy Chain Stores (TASE: RMLI)", ""),
    128: ("public", "RMAX", "NYSE", "RMAX", "", "New in 2025; the parent is now listed, not just RE/MAX Israel"),
    129: ("public", "ROTS", "TASE", "", "", "New in 2025"),
    131: ("public", "ANGL", "TASE", "", "", ""),
    135: ("public", "SPEN", "TASE", "", "", ""),
    136: ("public", "SKBN", "TASE", "", "", "New in 2025"),
    137: ("subsidiary", "", "", "", "Shikun & Binui (TASE: SKBN)", "New in 2025"),
    140: ("public", "SAE", "TASE", "", "", ""),
    141: ("subsidiary", "", "", "", "Vinci (Paris: DG)", "New in 2025; owned by Vinci since Dec 2021"),
    147: ("public", "TRIP", "Nasdaq", "TRIP", "", ""),
    150: ("public", "VILR", "TASE", "", "", ""),
    153: ("public", "YAAC", "TASE", "", "", "New in 2025"),
    154: ("subsidiary", "", "", "", "Bezeq (TASE: BEZQ)", ""),
    157: ("public", "ZMH", "TASE", "", "", ""),
}

# rows not in the 2023 update (matched by name, allowing for the renames in the footnotes)
NEW_2025 = {1, 2, 3, 4, 10, 11, 15, 16, 20, 21, 22, 23, 26, 29, 35, 36, 38, 39, 40, 41, 42, 50, 54, 55, 58, 59, 67, 68, 69, 71, 73, 74, 76, 78, 82, 87, 89, 90, 91, 92, 93, 94, 95, 98, 99, 103, 104, 105, 106, 107, 109, 115, 117, 119, 120, 124, 128, 129, 130, 132, 133, 136, 137, 138, 139, 141, 143, 151, 152, 153}

wb = openpyxl.load_workbook(XLSX, read_only=True)
isin_by_ticker = {str(r[3]).strip(): r[7].strip()
                  for r in list(wb.active.iter_rows(values_only=True))[1:] if r[0] and r[3] and r[7]}

with open(TAGS, newline="") as f:
    reader = csv.DictReader(f)
    fields = list(reader.fieldnames)
    existing = [r for r in reader if r["tag_id"] != "unhrc_watch_list"]

new = []
for a in csv.DictReader(open(ANNEX)):
    n = int(a["n"])
    status, tic, exch, us, parent, note = MARKET.get(n, ("unverified", "", "", "", "", ""))
    notes = [x for x in (FOOTNOTES.get(a["footnote"], ""), note) if x]
    if n in NEW_2025 and not any("New in 2025" in x for x in notes):
        notes.insert(0, "New in 2025")
    new.append({
        "tag_id": "unhrc_watch_list", "company": a["name"], "listing_status": status,
        "primary_ticker": tic, "primary_exchange": exch, "us_tickers": us, "parent_company": parent,
        "source_type": "involved in listed activities", "source_location": a["state"],
        "source_category": a["subs"], "review_note": "; ".join(notes),
        "isin": isin_by_ticker.get(tic, ""), "source_url": URL, "source_summary": "",
    })

with open(TAGS, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, restval="")
    w.writeheader()
    w.writerows(existing + new)

c = lambda k, v: sum(1 for r in new if r[k] == v)
print(f"rows {len(new)}; new in 2025 {sum('New in 2025' in r['review_note'] for r in new)}; public {c('listing_status','public')}; "
      f"subsidiary {c('listing_status','subsidiary')}; unverified {c('listing_status','unverified')}; "
      f"US tickers {sum(1 for r in new if r['us_tickers'])}")
