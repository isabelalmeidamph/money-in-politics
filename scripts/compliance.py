#!/usr/bin/env python3
"""Flag late Periodic Transaction Reports (STOCK Act timeliness).

Rule (House Ethics Committee, ethics.house.gov/periodic-transaction-report-calculator):
a transaction must be reported by the EARLIER of
  (1) 30 days after the filer was notified of it, or
  (2) 45 days after the transaction.
Late fee: $200, after a 30-day grace period.

"Filed" = the date the Clerk received the report (FilingDate in the Clerk's index), which
does not depend on anything the member wrote. The notification date IS self-reported, so
when it is missing or impossible we fall back to the 45-day rule alone and say so.

  python3 scripts/compliance.py data/processed
  -> data/processed/ptr_timeliness.parquet  (one row per trade)
     data/processed/late_filers_by_member.csv
"""
import os
import sys
from datetime import date, timedelta

import pandas as pd

proc = sys.argv[1]
tx = pd.read_parquet(os.path.join(proc, "ptr_transaction.parquet"))
tx["source"] = "e-filed"
# Scanned filings, transcribed from page images (Phase 2). One row per trade; a row with
# line_no 0 records a filing with no trades ("nothing to report").
scan_path = os.path.join(proc, "..", "transcribed", "scanned_ptr_rows.csv")
if os.path.exists(scan_path):
    RANGES = {"A": (1001, 15000), "B": (15001, 50000), "C": (50001, 100000), "D": (100001, 250000),
              "E": (250001, 500000), "F": (500001, 1000000), "G": (1000001, 5000000),
              "H": (5000001, 25000000), "I": (25000001, 50000000), "J": (50000001, None),
              "K": (1000001, None)}
    s = pd.read_csv(scan_path, dtype=str)
    s = s[s.line_no != "0"].copy()
    s["line_no"] = s.line_no.astype(int)
    s["amount_low"] = s.amount_col.map(lambda c: RANGES.get(c, (None, None))[0])
    s["amount_high"] = s.amount_col.map(lambda c: RANGES.get(c, (None, None))[1])
    s["filing_status"] = None
    s["source"] = "scanned"
    tx = pd.concat([tx, s], ignore_index=True)

filing = pd.read_parquet(os.path.join(proc, "filing.parquet"))[
    ["filing_id", "filed_date", "bioguide_id", "report_year"]]
member = pd.read_parquet(os.path.join(proc, "member.parquet"))[
    ["bioguide_id", "official_full", "party", "state", "chamber"]]
df = tx.merge(filing, on="filing_id", how="left")

for c in ["tx_date", "notification_date", "filed_date"]:
    df[c] = pd.to_datetime(df[c], errors="coerce").dt.date

today = date.today()


def assess(r):
    t, n, f = r["tx_date"], r["notification_date"], r["filed_date"]
    out = dict(deadline=None, deadline_basis=None, days_late=None, timeliness="unknown", date_issue=None)
    if pd.isna(f) or f is None:
        out["date_issue"] = "no_clerk_receipt_date"
        return out
    if t is None or pd.isna(t) or not (2012 <= t.year <= today.year) or t > f:
        out["date_issue"] = "trade_date_missing_or_impossible"
        return out
    d45 = t + timedelta(days=45)
    valid_n = n is not None and not pd.isna(n) and t <= n <= f
    if valid_n:
        d30 = n + timedelta(days=30)
        deadline, basis = (d30, "30 days after notification") if d30 < d45 else (d45, "45 days after trade")
    else:
        deadline, basis = d45, "45 days after trade"
        if n is not None and not pd.isna(n):
            out["date_issue"] = "notification_date_impossible"
    late = (f - deadline).days
    out.update(deadline=deadline, deadline_basis=basis, days_late=max(late, 0))
    if late <= 0:
        out["timeliness"] = "on time"
    elif late <= 30:
        out["timeliness"] = "late (within 30-day grace)"
    elif late <= 365:
        out["timeliness"] = "late (31-365 days)"
    else:
        out["timeliness"] = "late (over 1 year)"
    return out


res = pd.DataFrame([assess(r) for _, r in df.iterrows()], index=df.index)
df = pd.concat([df, res], axis=1)
# An amendment re-files an earlier report; its receipt date says nothing about the original's timeliness.
amended = df["filing_status"].fillna("").str.lower().eq("amended")
df.loc[amended, "timeliness"] = "amendment (not assessed)"
df.loc[amended, "days_late"] = None

# ---- Missing or unusable data the filer was required to give ----------------------------
# Each flag is about what the FILER left out or got wrong, not about our parser. A blank
# owner column is not missing: on the House form it means the member's own asset.
def blank(s):
    return s.isna() | s.astype(str).str.strip().isin(["", "nan", "None"])


is_scan = df.source.eq("scanned")
raw_type = df["tx_type_raw"] if "tx_type_raw" in df else pd.Series(None, index=df.index)
raw_amt = df["amount_raw"] if "amount_raw" in df else pd.Series(None, index=df.index)
flags = pd.DataFrame(index=df.index)
flags["missing_trade_date"] = df.tx_date.isna()
flags["missing_notification_date"] = df.notification_date.isna()
# Amount: scanned rows have no box marked; e-filed rows have a value that is not one of the
# form's ranges (e.g. "$.01"). Column K is a legal way to report and is not flagged.
flags["missing_amount"] = (is_scan & blank(df.get("amount_col"))) | (~is_scan & df.amount_low.isna() & blank(raw_amt))
flags["invalid_amount"] = ~is_scan & df.amount_low.isna() & ~blank(raw_amt) & ~df.get("spouse_dc_over", False).fillna(False).astype(bool)
# Transaction type: for e-filed rows only count it when the raw field itself is empty, so a
# parser miss is not blamed on the filer.
flags["missing_tx_type"] = (is_scan & blank(df.tx_type)) | (~is_scan & blank(raw_type))
flags["notification_after_receipt_or_before_trade"] = df.date_issue.eq("notification_date_impossible")
flags["impossible_trade_date"] = df.date_issue.eq("trade_date_missing_or_impossible") & df.tx_date.notna()
FLAG_COLS = list(flags.columns)
df = pd.concat([df, flags], axis=1)
df["data_issues"] = flags.apply(lambda r: ";".join(c for c in FLAG_COLS if r[c]), axis=1)

keep = ["filing_id", "line_no", "source", "bioguide_id", "owner", "asset_name", "ticker", "tx_type",
        "tx_date", "notification_date", "filed_date", "deadline", "deadline_basis", "days_late",
        "timeliness", "date_issue", "data_issues", "amount_low", "amount_high"]
out = df[keep].copy()
for c in ["tx_date", "notification_date", "filed_date", "deadline"]:
    out[c] = pd.to_datetime(out[c])
out.to_parquet(os.path.join(proc, "ptr_timeliness.parquet"), index=False)

assessed = df[df.timeliness.str.startswith(("on time", "late"))]
g = assessed.groupby("bioguide_id")
summary = pd.DataFrame({
    "trades_assessed": g.size(),
    "late_trades": g.apply(lambda x: x.timeliness.str.startswith("late").sum()),
    "late_over_30_days": g.apply(lambda x: (x.days_late > 30).sum()),
    "late_filings": g.apply(lambda x: x[x.timeliness.str.startswith("late")].filing_id.nunique()),
    "max_days_late": g.days_late.max(),
}).reset_index()
summary["share_late"] = (summary.late_trades / summary.trades_assessed).round(3)
summary = summary.merge(member, on="bioguide_id", how="left").sort_values(
    ["late_over_30_days", "late_trades"], ascending=False)
summary.to_csv(os.path.join(proc, "late_filers_by_member.csv"), index=False)

gm = df[df.bioguide_id.notna()].groupby("bioguide_id")
miss = pd.DataFrame({"trades_reported": gm.size()})
for c in FLAG_COLS:
    miss[c] = gm[c].sum()
miss["trades_with_any_issue"] = gm.apply(lambda x: x[FLAG_COLS].any(axis=1).sum())
miss["filings_with_any_issue"] = gm.apply(lambda x: x[x[FLAG_COLS].any(axis=1)].filing_id.nunique())
miss["share_with_issue"] = (miss.trades_with_any_issue / miss.trades_reported).round(3)
miss = miss.reset_index().merge(member, on="bioguide_id", how="left")
miss = miss[miss.trades_with_any_issue > 0].sort_values(
    ["trades_with_any_issue", "filings_with_any_issue"], ascending=False)
miss.to_csv(os.path.join(proc, "missing_data_by_member.csv"), index=False)

print(df.timeliness.value_counts().to_string())
print("data issues (trades):", {c: int(df[c].sum()) for c in FLAG_COLS})
print("members with any data issue:", len(miss))
print("date issues:", df.date_issue.value_counts().to_dict())
