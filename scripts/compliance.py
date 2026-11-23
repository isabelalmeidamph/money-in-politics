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
scan_path = os.path.join(proc, "ptr_transaction_scanned.parquet")
if os.path.exists(scan_path):  # scanned filings, transcribed (Phase 2)
    s = pd.read_parquet(scan_path)
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

keep = ["filing_id", "line_no", "source", "bioguide_id", "owner", "asset_name", "ticker", "tx_type",
        "tx_date", "notification_date", "filed_date", "deadline", "deadline_basis", "days_late",
        "timeliness", "date_issue", "amount_low", "amount_high"]
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

print(df.timeliness.value_counts().to_string())
print("date issues:", df.date_issue.value_counts().to_dict())
