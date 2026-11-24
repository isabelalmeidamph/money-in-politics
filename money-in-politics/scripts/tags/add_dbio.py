"""Add the companies in Annex 1 of the Don't Buy Into Occupation IV report (Nov 2024) as tag dbio.

Usage: python3 -I add_dbio.py dbio.pdf company_tags.csv investigate.xlsx
Company names are read from the PDF's 12 pt AntiqueOli-Med headings; market data is set below.
"""
import csv
import sys

import openpyxl
import pdfplumber

PDF, TAGS, XLSX = sys.argv[1:4]
URL = "https://dontbuyintooccupation.org/"

# name -> (status, ticker, exchange, us_tickers, parent, hq, note)
M = {
    "Airbnb": ("public", "ABNB", "Nasdaq", "ABNB", "", "United States", ""),
    "Alon Blue Square": ("unverified", "", "", "", "", "Israel", "Majority owner of Dor Alon (TASE: DRAL)"),
    "Alstom": ("public", "ALO", "Paris", "ALSMY", "", "France", "US trades would be the OTC ADR"),
    "Altice International": ("private", "", "", "", "", "Luxembourg", "Owns Hot Telecommunication Systems and Hot Mobile"),
    "Ashtrom Group": ("public", "ASHG", "TASE", "", "", "Israel", ""),
    "Axel Springer": ("private", "", "", "", "", "Germany", "Delisted after its 2020 KKR takeover; involvement is through Yad2 (AVIV Group)"),
    "Bank Hapoalim": ("public", "POLI", "TASE", "", "", "Israel", ""),
    "Bank Leumi": ("public", "LUMI", "TASE", "", "", "Israel", ""),
    "Bezeq Group": ("public", "BEZQ", "TASE", "", "", "Israel", ""),
    "Booking Holdings": ("public", "BKNG", "Nasdaq", "BKNG", "", "United States", ""),
    "Bright Dairy & Food": ("public", "600597", "Shanghai", "", "", "China", "Owner of Tnuva"),
    "Construcciones y Auxiliar de Ferrocarriles (CAF)": ("public", "CAF", "Madrid", "", "", "Spain", ""),
    "Carlsberg": ("public", "CARL B", "Copenhagen", "CABGY", "", "Denmark", "Involvement is through its Israeli licensee, Central Beverage Company; US trades would be the OTC ADR"),
    "Carrefour": ("public", "CA", "Paris", "", "", "France", "Involvement is through its Israeli franchise"),
    "Caterpillar": ("public", "CAT", "NYSE", "CAT", "", "United States", ""),
    "Cellcom Israel": ("public", "CEL", "TASE", "", "", "Israel", ""),
    "Cemex": ("public", "CEMEXCPO", "Mexico", "CX", "", "Mexico", "CX is its NYSE-listed ADS"),
    "Cisco Systems": ("public", "CSCO", "Nasdaq", "CSCO", "", "United States", ""),
    "CNH Industrial": ("public", "CNH", "NYSE", "CNH", "", "United Kingdom", ""),
    "Danya Cebus": ("public", "DNYA", "TASE", "", "", "Israel", ""),
    "Delek Group": ("public", "DLEKG", "TASE", "", "", "Israel", ""),
    "Delta Galil Industries": ("public", "DELG", "TASE", "", "", "Israel", ""),
    "eDreams ODIGEO": ("public", "EDR", "Madrid", "", "", "Spain", "Removed from the UN database in 2025"),
    "Elbit Systems": ("public", "ESLT", "Nasdaq", "ESLT", "", "Israel", "Also listed in Tel Aviv"),
    "Electra Group": ("public", "ELTR", "TASE", "", "", "Israel", ""),
    "Expedia Group": ("public", "EXPE", "Nasdaq", "EXPE", "", "United States", ""),
    "Hamat Group": ("public", "HAMAT", "TASE", "", "", "Israel", ""),
    "Heidelberg Materials": ("public", "HEI", "Xetra", "", "", "Germany", ""),
    "Hewlett Packard Enterprise (HPE)": ("public", "HPE", "NYSE", "HPE", "", "United States", ""),
    "HikVision": ("public", "002415", "Shenzhen", "", "", "China", ""),
    "Hilan": ("public", "HLAN", "TASE", "", "", "Israel", ""),
    "Hyundai Heavy Industries": ("public", "329180", "KRX", "", "", "South Korea", "Now HD Hyundai Heavy Industries"),
    "IBM": ("public", "IBM", "NYSE", "IBM", "", "United States", ""),
    "Israel Chemicals (ICL Group)": ("public", "ICL", "NYSE", "ICL", "", "Israel", "Also listed in Tel Aviv"),
    "Israel Discount Bank": ("public", "DSCT", "TASE", "", "", "Israel", ""),
    "MAN Group": ("subsidiary", "", "", "", "Traton (Frankfurt: 8TRA)", "Germany",
                  "The truck and bus maker; not Man Group plc, the London-listed fund manager"),
    "Matrix IT": ("public", "MTRX", "TASE", "", "", "Israel", ""),
    "Mivne Group": ("public", "MVNE", "TASE", "", "", "Israel", ""),
    "Mizrahi Tefahot Bank": ("public", "MZTF", "TASE", "", "", "Israel", ""),
    "Motorola Solutions": ("public", "MSI", "NYSE", "MSI", "", "United States", ""),
    "Orbia": ("public", "ORBIA", "Mexico", "", "", "Mexico", "Owner of Netafim"),
    "Partner Communications": ("public", "PTNR", "TASE", "PTNR", "", "Israel", "Also on Nasdaq"),
    "Paz Oil Company": ("public", "PAZ", "TASE", "", "", "Israel", "Now Paz Retail and Energy"),
    "Rami Levy Chain Stores Hashikma Marketing 2006": ("public", "RMLI", "TASE", "", "", "Israel", ""),
    "RE/MAX Holdings": ("public", "RMAX", "NYSE", "RMAX", "", "United States", ""),
    "Shapir Engineering and Industry": ("public", "SPEN", "TASE", "", "", "Israel", ""),
    "Shikun & Binui": ("public", "SKBN", "TASE", "", "", "Israel", ""),
    "Shufersal": ("public", "SAE", "TASE", "", "", "Israel", ""),
    "Siemens": ("public", "SIE", "Xetra", "", "", "Germany", ""),
    "Syensqo": ("public", "SYENS", "Brussels", "", "", "Belgium", ""),
    "The Coca-Cola Company": ("public", "KO", "NYSE", "KO", "", "United States", ""),
    "TKH Group": ("public", "TWEKA", "Amsterdam", "", "", "Netherlands", ""),
    "Tripadvisor": ("public", "TRIP", "Nasdaq", "TRIP", "", "United States", ""),
    "TUI Group": ("public", "TUI1", "Xetra", "", "", "Germany", "Also listed in London"),
    "Villar International": ("public", "VILR", "TASE", "", "", "Israel", ""),
    "Vinci / SEMI": ("public", "DG", "Paris", "", "", "France", "Vinci bought SEMI (Spain) in Dec 2021; involvement is through SEMI"),
    "Volvo Group": ("public", "VOLV B", "Stockholm", "", "", "Sweden", ""),
    "WSP Global": ("public", "WSP", "TSX", "", "", "Canada", ""),
}

names = []
with pdfplumber.open(PDF) as pdf:
    for page in pdf.pages:
        lines = {}
        for ch in page.chars:
            if "AntiqueOli-Med" in ch["fontname"] and round(ch["size"]) == 12:
                lines.setdefault(round(ch["top"]), []).append(ch)
        for top in sorted(lines):
            names.append("".join(c["text"] for c in sorted(lines[top], key=lambda c: c["x0"])).strip())
# The PDF sets this one heading in body type, so the font test misses it; it sits between Paz and RE/MAX.
RAMI = "Rami Levy Chain Stores Hashikma Marketing 2006"
if RAMI not in names:
    names.insert(names.index("RE/MAX Holdings"), RAMI)
assert len(names) == 58, len(names)
missing, extra = set(names) - set(M), set(M) - set(names)
assert not missing and not extra, (missing, extra)

wb = openpyxl.load_workbook(XLSX, read_only=True)
isin_by_ticker = {str(r[3]).strip(): (r[7] or "").strip()
                  for r in list(wb.active.iter_rows(values_only=True))[1:] if r[0] and r[3]}

with open(TAGS, newline="") as f:
    reader = csv.DictReader(f)
    fields = list(reader.fieldnames)
    existing = [r for r in reader if r["tag_id"] != "dbio"]
known_us = {r["primary_ticker"]: r["us_tickers"] for r in existing if r["primary_ticker"] and r["us_tickers"]}
known_isin = {r["primary_ticker"]: r["isin"] for r in existing if r["primary_ticker"] and r["isin"]}

new = []
for name in names:
    status, tic, exch, us, parent, hq, note = M[name]
    new.append({
        "tag_id": "dbio", "company": name, "listing_status": status, "primary_ticker": tic,
        "primary_exchange": exch, "us_tickers": us or known_us.get(tic, ""), "parent_company": parent,
        "source_type": "", "source_location": hq, "source_category": "", "review_note": note,
        "isin": known_isin.get(tic) or isin_by_ticker.get(tic, ""), "source_url": URL, "source_summary": "",
    })

with open(TAGS, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields, restval="")
    w.writeheader()
    w.writerows(existing + new)
print(len(new), "rows; US tickers:", sum(1 for r in new if r["us_tickers"]))
