"""Parse Annex I of A/HRC/60/19 (pdftotext -layout output) into a CSV of n, name, subparagraphs, state."""
import csv
import re
import sys

TXT, OUT = sys.argv[1], sys.argv[2]
lines = open(TXT).read().splitlines()
start = next(i for i, l in enumerate(lines) if l.strip() == "Annex I")
end = next(i for i, l in enumerate(lines) if l.strip() == "Annex II")
body = lines[start:end]

row_re = re.compile(r"^\s*(\d{1,3})\s{2,}(.+?)\s*((?:\([a-j]\)(?:,\s*)?)+)\s{2,}(.+?)\s*$")
rows, cur = [], None
for l in body:
    if not l.strip() or "Listed activity" in l or "subparagraph of" in l or l.strip().startswith(("No.", "A/HRC", "a “Listed")):
        continue
    m = row_re.match(l)
    if m:
        cur = {"n": int(m[1]), "name": m[2].strip(), "subs": re.sub(r"\s+", " ", m[3].strip()), "state": m[4].strip()}
        rows.append(cur)
        continue
    if cur is None or re.fullmatch(r"\s*\d+\s*", l):
        continue
    if re.match(r"^\s+[a-m]\s{2,}(Formerly|Previously)", l) or l.strip().startswith(("international fact", "political, econ", "Palestinian Terr")):
        cur = None
        continue
    # continuation: name part sits in the name column, state part far right
    idx = len(l) - len(l.lstrip())
    text = l.strip()
    if idx > 60:
        cur["state"] += " " + text
    else:
        parts = re.split(r"\s{2,}", text)
        cur["name"] += " " + parts[0]
        if len(parts) > 1:
            cur["state"] += " " + parts[-1]

# strip footnote letters stuck to names, e.g. "Ltd. b" or "Ltd.c"
for r in rows:
    r["footnote"] = ""
    m = re.search(r"(Ltd\.|Ltd)\s?([a-m])$", r["name"])
    if m:
        r["footnote"] = m[2]
        r["name"] = r["name"][: m.start(2)].rstrip()
    r["state"] = r["state"].replace("Kingdom of the Netherlands", "Netherlands").replace(
        "United Kingdom of Great Britain and Northern Ireland", "United Kingdom").replace(
        "United States of America", "United States")

assert [r["n"] for r in rows] == list(range(1, 159)), [r["n"] for r in rows]
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["n", "name", "subs", "state", "footnote"])
    w.writeheader()
    w.writerows(rows)
print(len(rows))
