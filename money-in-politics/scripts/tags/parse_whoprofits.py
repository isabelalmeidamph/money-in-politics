"""Parse the Who Profits 'Database of Complicit Companies' PDF export into a CSV.

Works from word positions rather than table detection, because rows that cross a page
break are dropped or mis-joined by table extraction. Column edges are fixed in the export.
"""
import csv
import re
import sys

import pdfplumber

PDF, OUT = sys.argv[1], sys.argv[2]
FIELDS = ["n", "name", "traded_in", "hq", "involvement", "sector", "revenue", "region"]
EDGES = [31.2, 78.0, 210.5, 296.2, 382.0, 537.9, 639.2, 732.8, 10_000]
HEADER = {"Company", "Name", "Traded", "In", "Main", "Headquaters", "Involvement", "Sector", "Revenue", "Region"}


def col(x):
    for i in range(len(EDGES) - 1):
        if EDGES[i] - 1 <= x < EDGES[i + 1] - 1:
            return i
    return None


rows = []
with pdfplumber.open(PDF) as pdf:
    for i, page in enumerate(pdf.pages):
        top = 60 if i == 0 else 0  # only the first page has a title
        words = [w for w in page.extract_words() if top < w["top"] < page.height - 40]  # drop title and footer
        words = [w for w in words if not (w["top"] < 85 and w["text"] in HEADER)]
        words.sort(key=lambda w: (round(w["top"]), w["x0"]))
        for w in words:
            c = col(w["x0"])
            if c is None:
                continue
            if c == 0 and re.fullmatch(r"\d{1,3}", w["text"]):
                rows.append({k: [] for k in FIELDS})
                rows[-1]["n"] = [w["text"]]
            elif rows:  # words before the first number on a page continue the previous page's last row
                rows[-1][FIELDS[c]].append(w["text"])

out = []
for r in rows:
    d = {k: " ".join(v) for k, v in r.items()}
    d["n"] = int(d["n"])
    out.append(d)

ns = [r["n"] for r in out]
assert ns == list(range(1, len(ns) + 1)), sorted(set(range(1, max(ns) + 1)) - set(ns))
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=FIELDS)
    w.writeheader()
    w.writerows(out)
print(len(out))
