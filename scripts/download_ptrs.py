#!/usr/bin/env python3
"""Download House Periodic Transaction Report (PTR) PDFs listed in the Clerk's yearly indexes.

Standard library only (works with the python3 that ships with Apple's command-line tools).
Run from the repo root.

  # 1. A small test sample (30 e-filed PDFs spread across years and members):
  python3 scripts/download_ptrs.py --sample 30

  # 2. Everything e-filed (about 3,300 PDFs, about an hour at the default pace):
  python3 scripts/download_ptrs.py

  # Other options: --format scanned | all, --years 2024 2026, --delay 1.5

Files are saved to data/ptr_pdfs/<year>/<DocID>.pdf. Files already downloaded are
skipped, so you can stop with Ctrl-C and run again to resume. Failures are logged to
data/ptr_pdfs/download_log.csv.
"""
import argparse
import csv
import glob
import os
import random
import sys
import time
import urllib.error
import urllib.request

UA = "Mozilla/5.0 (money-in-politics; public-interest research)"
URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc}.pdf"


def doc_format(doc_id):
    if len(doc_id) == 8 and doc_id.startswith("2"):
        return "e-filed"
    if len(doc_id) == 7:
        return "scanned"
    return "other"


def load_ptrs(index_dir):
    rows = []
    for path in sorted(glob.glob(os.path.join(index_dir, "*FD.txt"))):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f, delimiter="\t"):
                if (r.get("FilingType") or "").strip() == "P":
                    doc = r["DocID"].strip()
                    rows.append(dict(year=r["Year"].strip(), doc=doc, last=r["Last"],
                                     first=r["First"], state_dst=r["StateDst"],
                                     format=doc_format(doc)))
    return rows


def pick_sample(rows, n, seed=42):
    """Spread the sample across years, and avoid repeating a member where possible."""
    rng = random.Random(seed)
    by_year = {}
    for r in rows:
        by_year.setdefault(r["year"], []).append(r)
    for v in by_year.values():
        rng.shuffle(v)
    picked, seen = [], set()
    years = sorted(by_year)
    while len(picked) < n and any(by_year.values()):
        for y in years:
            pool = by_year[y]
            if not pool or len(picked) >= n:
                continue
            idx = next((i for i, r in enumerate(pool) if (r["last"], r["state_dst"]) not in seen), 0)
            r = pool.pop(idx)
            seen.add((r["last"], r["state_dst"]))
            picked.append(r)
    return picked


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--index-dir", default="data/house_index")
    ap.add_argument("--out", default="data/ptr_pdfs")
    ap.add_argument("--format", choices=["e-filed", "scanned", "all"], default="e-filed")
    ap.add_argument("--years", nargs=2, type=int, metavar=("FROM", "TO"))
    ap.add_argument("--sample", type=int, help="download only N PDFs, spread across years")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between requests (be polite)")
    a = ap.parse_args()

    rows = load_ptrs(a.index_dir)
    if not rows:
        sys.exit("No PTRs found. Run from the repo root, or set --index-dir.")
    if a.format != "all":
        rows = [r for r in rows if r["format"] == a.format]
    if a.years:
        rows = [r for r in rows if a.years[0] <= int(r["year"]) <= a.years[1]]
    if a.sample:
        rows = pick_sample(rows, a.sample)

    os.makedirs(a.out, exist_ok=True)
    log_path = os.path.join(a.out, "download_log.csv")
    new_log = not os.path.exists(log_path)
    log = open(log_path, "a", newline="")
    w = csv.writer(log)
    if new_log:
        w.writerow(["time", "year", "doc_id", "status", "bytes", "detail"])

    total, got, skipped, failed = len(rows), 0, 0, 0
    print(f"{total} PDFs to fetch ({a.format}) -> {a.out}")
    try:
        for i, r in enumerate(rows, 1):
            dest_dir = os.path.join(a.out, r["year"])
            dest = os.path.join(dest_dir, r["doc"] + ".pdf")
            if os.path.exists(dest) and os.path.getsize(dest) > 0:
                skipped += 1
                continue
            os.makedirs(dest_dir, exist_ok=True)
            url = URL.format(year=r["year"], doc=r["doc"])
            status, size, detail = "ok", 0, ""
            for attempt in range(3):
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": UA})
                    with urllib.request.urlopen(req, timeout=60) as resp:
                        data = resp.read()
                    if not data.startswith(b"%PDF"):
                        status, detail = "not_pdf", data[:60].decode("latin-1", "replace")
                        break
                    tmp = dest + ".part"
                    with open(tmp, "wb") as f:
                        f.write(data)
                    os.replace(tmp, dest)
                    size, status, detail = len(data), "ok", ""
                    break
                except urllib.error.HTTPError as e:
                    status, detail = "http_%d" % e.code, str(e.reason)
                    if e.code in (404, 410):
                        break
                except Exception as e:  # network hiccup: back off and retry
                    status, detail = "error", repr(e)[:120]
                time.sleep(5 * (attempt + 1))
            w.writerow([time.strftime("%Y-%m-%d %H:%M:%S"), r["year"], r["doc"], status, size, detail])
            log.flush()
            if status == "ok":
                got += 1
            else:
                failed += 1
            if i % 25 == 0 or i == total:
                print(f"  {i}/{total}  downloaded {got}, already had {skipped}, failed {failed}")
            time.sleep(a.delay)
    except KeyboardInterrupt:
        print("\nStopped. Run the same command again to resume.")
    finally:
        log.close()
    print(f"Done: downloaded {got}, already had {skipped}, failed {failed}. Log: {log_path}")


if __name__ == "__main__":
    main()
