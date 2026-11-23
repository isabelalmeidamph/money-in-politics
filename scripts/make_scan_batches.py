#!/usr/bin/env python3
"""Group downloaded scanned PTR PDFs into upload batches for transcription.

Standard library only. Run from the repo root after:
  python3 scripts/download_ptrs.py --format scanned

  python3 scripts/make_scan_batches.py
  -> data/scan_batches/batch_01/, batch_02/, ...  (copies of the PDFs, ready to drag into the chat)
     data/scan_batches/manifest.csv               (which filing is in which batch)

Batches hold up to --max-files PDFs or --max-pages pages, whichever comes first. A filing
longer than --max-pages gets a batch of its own. Filings listed in data/scan_done.txt
(one DocID per line) are skipped, so batches can be rebuilt as work progresses.
"""
import argparse
import csv
import glob
import os
import re
import shutil


def page_count(path):
    """Page count without a PDF library: the largest /Count in a /Pages node, looking
    inside compressed object streams too (these scans keep their page tree compressed)."""
    import zlib
    with open(path, "rb") as f:
        data = f.read()
    chunks = [data]
    for m in re.finditer(rb"stream\r?\n", data):
        try:
            chunks.append(zlib.decompressobj().decompress(data[m.end():m.end() + 5_000_000]))
        except zlib.error:
            pass
    counts = [int(c) for ch in chunks
              for c in re.findall(rb"/Type\s*/Pages\b[^>]*?/Count\s+(\d+)", ch)
              + re.findall(rb"/Count\s+(\d+)[^>]*?/Type\s*/Pages\b", ch)]
    return max(counts) if counts else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf-dir", default="data/ptr_pdfs")
    ap.add_argument("--out", default="data/scan_batches")
    ap.add_argument("--max-files", type=int, default=20)
    ap.add_argument("--max-pages", type=int, default=30)
    a = ap.parse_args()

    done = set()
    if os.path.exists("data/scan_done.txt"):
        done = {l.strip() for l in open("data/scan_done.txt") if l.strip()}

    pdfs = sorted(p for p in glob.glob(os.path.join(a.pdf_dir, "**", "*.pdf"), recursive=True)
                  if re.fullmatch(r"\d{7}", os.path.splitext(os.path.basename(p))[0])
                  and os.path.splitext(os.path.basename(p))[0] not in done)
    if not pdfs:
        print("No scanned PDFs found. Run: python3 scripts/download_ptrs.py --format scanned")
        return

    if os.path.exists(a.out):
        shutil.rmtree(a.out)
    batches, cur, cur_pages = [], [], 0
    for p in pdfs:
        n = page_count(p)
        if cur and (len(cur) >= a.max_files or cur_pages + n > a.max_pages):
            batches.append(cur)
            cur, cur_pages = [], 0
        cur.append((p, n))
        cur_pages += n
    if cur:
        batches.append(cur)

    rows = []
    for i, b in enumerate(batches, 1):
        d = os.path.join(a.out, "batch_%02d" % i)
        os.makedirs(d)
        for p, n in b:
            shutil.copy2(p, d)
            rows.append(dict(batch=i, filing_id=os.path.splitext(os.path.basename(p))[0], pages=n,
                             year=os.path.basename(os.path.dirname(p))))
    with open(os.path.join(a.out, "manifest.csv"), "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["batch", "filing_id", "year", "pages"])
        w.writeheader()
        w.writerows(rows)
    total_pages = sum(r["pages"] for r in rows)
    print("%d filings, ~%d pages -> %d batches in %s" % (len(rows), total_pages, len(batches), a.out))
    big = [r for r in rows if r["pages"] > a.max_pages]
    if big:
        print("Long filings (own batch): " + ", ".join("%s (%d pp)" % (r["filing_id"], r["pages"]) for r in big))


if __name__ == "__main__":
    main()
