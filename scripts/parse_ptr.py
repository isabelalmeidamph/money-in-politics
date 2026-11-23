#!/usr/bin/env python3
"""Parse e-filed House Periodic Transaction Report (PTR) PDFs into transaction rows.

E-filed PTRs (8-digit DocIDs starting with 2) have a text layer with a fixed column
layout: ID | Owner | Asset | Transaction Type | Date | Notification Date | Amount | Cap. Gains.
We read word positions with pdfplumber and assign words to columns using the
header row's x positions, which is more reliable than table detection on these files.

  python3 scripts/parse_ptr.py data/ptr_pdfs data/processed
  -> data/processed/ptr_transaction.parquet, ptr_filing_parse.parquet, ptr_parse_warnings.csv

Scanned PTRs (7-digit DocIDs) have no text layer and are skipped here (Phase 2: OCR).
"""
import csv
import glob
import os
import re
import sys
from datetime import datetime

import pdfplumber

COLS = ["id", "owner", "asset", "type", "date", "notified", "amount", "gains"]
HEADER_WORDS = {"id": "id", "owner": "owner", "asset": "asset", "transaction": "type",
                "date": "date", "notification": "notified", "amount": "amount", "cap.": "gains"}
DETAIL_KEYS = {"FILING STATUS": "filing_status", "SUBHOLDING OF": "subholding_of",
               "DESCRIPTION": "description", "COMMENTS": "comments", "LOCATION": "location"}
END_MARK = "for the complete list of asset type"
DATE_RE = re.compile(r"^\d{2}/\d{2}/\d{4}$")
OWNER_CODES = {"SP", "JT", "DC"}
TYPE_MAP = {"P": "purchase", "S": "sale", "S (PARTIAL)": "partial sale", "E": "exchange"}


def group_lines(words, tol=3.0):
    lines = []
    for w in sorted(words, key=lambda w: (w["top"], w["x0"])):
        if lines and abs(w["top"] - lines[-1][0]) <= tol:
            lines[-1][1].append(w)
        else:
            lines.append([w["top"], [w]])
    return [sorted(ws, key=lambda w: w["x0"]) for _, ws in lines]


def find_header(lines):
    """Return (index of header line, {col: x0}) or (None, None)."""
    for i, ws in enumerate(lines):
        low = [w["text"].lower() for w in ws]
        if "owner" in low and "asset" in low and "amount" in low:
            xs = {}
            for w in ws:
                k = HEADER_WORDS.get(w["text"].lower())
                if k and k not in xs:
                    xs[k] = w["x0"]
            return i, xs
    return None, None


def col_of(x0, xs):
    best = "id"
    for c in COLS:
        if c in xs and x0 >= xs[c] - 4:
            best = c
    return best


def line_text(ws):
    return " ".join(w["text"] for w in ws)


def _masked_eq(seg, key):
    """Compare text to a label where some letters may be NUL (a font quirk in newer
    PDFs: 'FILING' comes out as 'F' + 5 NULs). Lengths must match; visible letters must agree."""
    return len(seg) == len(key) and all(c == "\x00" or c.upper() == k for c, k in zip(seg, key))


def detail_key(text):
    for k, field in DETAIL_KEYS.items():
        n = len(k) + 1
        if len(text) >= n and _masked_eq(text[:n], k + ":"):
            return field, text[n:].strip()
    return None, None


def parse_amount(raw):
    s = raw.replace("–", "-").strip()
    spouse_dc_over = "spouse/dc" in s.lower()
    nums = [int(n.replace(",", "")) for n in re.findall(r"\$\s*([\d,]+)", s)]
    if re.search(r"\bover\b", s, re.I) and nums:
        return nums[0] + 1, None, spouse_dc_over
    if len(nums) == 2:
        return nums[0], nums[1], spouse_dc_over
    if len(nums) == 1:
        return nums[0], nums[0], spouse_dc_over
    return None, None, spouse_dc_over


def parse_date(s):
    try:
        return datetime.strptime(s, "%m/%d/%Y").date()
    except (TypeError, ValueError):
        return None


def split_asset(raw):
    """'Apple Inc. (AAPl) [OP]' -> name, ticker 'AAPL', asset_type 'OP'.
    The PDFs' fonts garble letter case, so codes are upper-cased; names are kept as filed."""
    asset_type = None
    m = re.search(r"\[([A-Za-z]{2})\]\s*$", raw)
    if m:
        asset_type = m.group(1).upper()
        raw = raw[:m.start()].strip()
    ticker = None
    m = re.search(r"\(([A-Za-z][A-Za-z0-9.\-/ ]{0,9})\)\s*$", raw)
    if m:
        ticker = m.group(1).replace(" ", "").upper()
        raw = raw[:m.start()].strip()
    return raw, ticker, asset_type


def parse_pdf(path):
    filing_id = os.path.splitext(os.path.basename(path))[0]
    meta = dict(filing_id=filing_id, filer_name=None, filer_status=None, state_dst=None,
                signed_date=None, pages=0, ipo=None)
    rows, warnings = [], []
    cur, xs, ended, in_details = None, None, False, False

    def close():
        nonlocal cur
        if cur:
            rows.append(cur)
        cur = None

    with pdfplumber.open(path) as pdf:
        meta["pages"] = len(pdf.pages)
        full_text = "\n".join((p.extract_text() or "") for p in pdf.pages)
        for page in pdf.pages:
            lines = group_lines(page.extract_words())
            hi, page_xs = find_header(lines)
            if page_xs:
                xs = page_xs
                start = hi + 1
                # skip the 2nd/3rd header lines ("Type Date Gains >", "$200?")
                while start < len(lines) and line_text(lines[start]).lower().replace(" ", "") in (
                        "typedategains>", "$200?", "typedate", "gains>"):
                    start += 1
            elif xs and not ended:
                start = 0
            else:
                continue
            for ws in lines[start:]:
                text = line_text(ws)
                if END_MARK in text.lower():
                    ended = True
                    break
                if ended:
                    break
                cells = {c: [] for c in COLS}
                for w in ws:
                    cells[col_of(w["x0"], xs)].append(w["text"])
                cells = {c: " ".join(v) for c, v in cells.items()}
                field, value = detail_key(text)
                if DATE_RE.match(cells["date"].split(" ")[0] if cells["date"] else ""):
                    close()
                    in_details = False
                    owner, asset = cells["owner"].strip(), cells["asset"]
                    if owner.upper() not in OWNER_CODES | {""}:
                        asset, owner = (owner + " " + asset).strip(), ""
                    cur = dict(filing_id=filing_id, tx_id=cells["id"] or None,
                               owner=owner.upper() or "SELF", asset_raw=asset,
                               tx_type_raw=cells["type"].upper(), tx_date_raw=cells["date"],
                               notified_raw=cells["notified"], amount_raw=cells["amount"],
                               gains_box=cells["gains"], filing_status=None,
                               subholding_of=None, description=None, comments=None,
                               location=None, page=page.page_number)
                elif cur is None:
                    continue
                elif field:
                    in_details = True
                    cur[field] = value
                    cur["_last"] = field
                elif in_details:
                    f = cur.get("_last")
                    if f:
                        cur[f] = (cur[f] + " " + text).strip()
                else:
                    if cells["asset"] or cells["owner"]:
                        cur["asset_raw"] = (cur["asset_raw"] + " " + (cells["owner"] + " " + cells["asset"]).strip()).strip()
                    if cells["amount"]:
                        cur["amount_raw"] = (cur["amount_raw"] + " " + cells["amount"]).strip()
                    if cells["type"]:
                        cur["tx_type_raw"] = (cur["tx_type_raw"] + " " + cells["type"].upper()).strip()
                    if cells["gains"] and not cur["gains_box"]:
                        cur["gains_box"] = cells["gains"]
            if ended:
                break
        close()

    m = re.search(r"Name:\s*(.+)", full_text, re.I)
    meta["filer_name"] = m.group(1).strip() if m else None
    m = re.search(r"Status:\s*(.+)", full_text, re.I)
    meta["filer_status"] = m.group(1).strip() if m else None
    m = re.search(r"State/District:\s*(\S+)", full_text, re.I)
    meta["state_dst"] = m.group(1).upper() if m else None
    m = re.search(r"Digitally Signed:.*?,\s*(\d{2}/\d{2}/\d{4})", full_text, re.I)
    meta["signed_date"] = parse_date(m.group(1)) if m else None
    m = re.search(r"initial public offerings\s*\n\s*(\S+)\s*Yes\s*(\S+)\s*No", full_text, re.I)
    if m:
        meta["ipo"] = m.group(1).endswith("i")

    out, seen = [], {}
    for n, r in enumerate(rows, 1):
        r.pop("_last", None)
        name, ticker, asset_type = split_asset(r["asset_raw"])
        low, high, spouse_dc_over = parse_amount(r["amount_raw"])
        txt = re.sub(r"\s+", " ", r["tx_type_raw"]).strip()
        tx_date, notified = parse_date(r["tx_date_raw"]), parse_date(r["notified_raw"].split(" ")[0])
        r.update(line_no=n, asset_name=name, ticker=ticker, asset_type=asset_type,
                 tx_type=TYPE_MAP.get(txt), tx_date=tx_date, notification_date=notified,
                 amount_low=low, amount_high=high, spouse_dc_over=spouse_dc_over,
                 cap_gains_over_200=(r["gains_box"].endswith("b") if r["gains_box"] else None))
        r.pop("tx_date_raw"); r.pop("notified_raw"); r.pop("gains_box")
        if r["filing_status"]:
            r["filing_status"] = r["filing_status"].capitalize()
        # quality checks
        if r["tx_type"] is None:
            warnings.append((filing_id, n, "unknown_tx_type", txt))
        if tx_date is None:
            warnings.append((filing_id, n, "bad_tx_date", ""))
        if low is None:
            warnings.append((filing_id, n, "bad_amount", r["amount_raw"]))
        if asset_type in ("ST", "OP") and not ticker:
            warnings.append((filing_id, n, "stock_without_ticker", r["asset_raw"][:80]))
        if tx_date and notified and notified < tx_date:
            warnings.append((filing_id, n, "notified_before_trade", ""))
        # Identical rows in one filing. Seen at page breaks (a row repeated at the top of the
        # next page), but could also be two genuine identical trades: flag, never drop.
        key = (r["owner"], r["asset_raw"], r["tx_type"], tx_date, r["amount_raw"], r["description"],
               r["subholding_of"], r["tx_id"])
        r["possible_duplicate_of"] = seen.get(key)
        if r["possible_duplicate_of"]:
            warnings.append((filing_id, n, "possible_duplicate",
                             "same as line %d%s" % (seen[key], ", across page break" if r["page"] != out[seen[key] - 1]["page"] else "")))
        seen.setdefault(key, n)
        out.append(r)
    if not out:
        warnings.append((filing_id, 0, "no_transactions", ""))
    meta["n_transactions"] = len(out)
    return meta, out, warnings


def main():
    pdf_dir, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    paths = sorted(p for p in glob.glob(os.path.join(pdf_dir, "**", "*.pdf"), recursive=True)
                   if re.match(r"^2\d{7}$", os.path.splitext(os.path.basename(p))[0]))
    metas, txs, warns = [], [], []
    for i, p in enumerate(paths, 1):
        try:
            m, t, w = parse_pdf(p)
            m["parse_status"] = "ok" if t else "empty"
        except Exception as e:  # keep going; log the failure
            m = dict(filing_id=os.path.splitext(os.path.basename(p))[0], parse_status="error",
                     n_transactions=0)
            t, w = [], [(m["filing_id"], 0, "parse_error", repr(e)[:200])]
        metas.append(m); txs.extend(t); warns.extend(w)
        if i % 100 == 0:
            print(f"  {i}/{len(paths)}")
    import pandas as pd
    pd.DataFrame(metas).to_parquet(os.path.join(out_dir, "ptr_filing_parse.parquet"), index=False)
    pd.DataFrame(txs).to_parquet(os.path.join(out_dir, "ptr_transaction.parquet"), index=False)
    with open(os.path.join(out_dir, "ptr_parse_warnings.csv"), "w", newline="") as f:
        cw = csv.writer(f)
        cw.writerow(["filing_id", "line_no", "warning", "detail"])
        cw.writerows(warns)
    print(f"{len(paths)} PDFs -> {len(txs)} transactions, {len(warns)} warnings")


if __name__ == "__main__":
    main()
