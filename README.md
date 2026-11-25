# money-in-politics

A free, public resource showing what members of Congress own and trade in stocks. Every number links back to the official filing it came from.

Version 1 covers the stock holdings and trades of members of Congress. FEC campaign contributions and Senate lobbying data come later, linked by each member's bioguide ID.

## Status: Phase 0 (foundation)

| Phase | What | Status |
| --- | --- | --- |
| 0 | Member roster and House filing indexes in DuckDB/Parquet, filings linked to members | Done |
| 1 | Parse e-filed House trade reports (PTRs) | Parser built and checked on a 30-filing sample; full run next |
| 2 | Senate eFD and OCR for scanned filings | |
| 3 | Annual holdings, sectors, committee overlap | |
| 4 | Public launch | |
| 5 | FEC contributions and lobbying | |

## Quick start

```bash
pip install -r requirements.txt
bash scripts/fetch_sources.sh                                       # House indexes + member roster
python3 scripts/build_phase0.py data/house_index refs data/processed
```

Querying the results with DuckDB:

```sql
select m.official_full, m.party, count(*) as trade_reports
from 'data/processed/filing.parquet' f
join 'data/processed/member.parquet' m using (bioguide_id)
where f.filing_type = 'P'
group by all order by trade_reports desc limit 10;
```

## Phase 1: trade report parser

```bash
python3 scripts/download_ptrs.py --sample 30     # or no flag for all e-filed PTRs (~1 hour)
python3 scripts/parse_ptr.py data/ptr_pdfs data/processed
```

Outputs: `ptr_transaction.parquet` (one row per trade), `ptr_filing_parse.parquet` (one row per PDF), and `ptr_parse_warnings.csv`.

The parser assigns words to columns by their x position under the table header. Table detection merged rows on these PDFs, so it isn't used. Two font quirks are handled:
- Older PDFs garble letter case (`(AAPl)`), so tickers and codes are upper-cased. Asset names are kept as filed.
- Newer PDFs replace most letters of labels with NUL characters (`F\0\0\0\0\0 S\0\0\0\0\0:` for `FILING STATUS:`). Labels are matched on their length plus the visible letters.

Identical rows within a filing are flagged in `possible_duplicate_of`, never dropped. Some are page-break repeats; others are two real lots traded the same day.

**Sample check (30 filings, 2020–2026):** 192 trades parsed. The row count matched an independent count of transaction-date lines in every file. All stock and option rows have a ticker.

## Late-filing check

```bash
python3 scripts/compliance.py data/processed
```

Each trade must be reported by the earlier of 30 days after the filer was notified or 45 days after the trade ([House Ethics PTR calculator](https://ethics.house.gov/periodic-transaction-report-calculator)). "Filed" is the date the Clerk received the report, taken from the Clerk's index rather than anything the member wrote. When the self-reported notification date is missing or impossible, only the 45-day rule is used, and the row is flagged. Amendments aren't assessed, because their receipt date says nothing about the original filing.

Outputs: `ptr_timeliness.parquet` (deadline, days late and a timeliness band for each trade) and `late_filers_by_member.csv`. Bands: on time / late within the 30-day grace period / 31–365 days late / over a year late. The $200 late fee applies after the 30-day grace period.

### Missing or unusable data

The same script flags information each filer was required to give but didn't, or gave in a form that can't be right. The flags are in `data_issues` in `ptr_timeliness.parquet`, and are counted per member in `missing_data_by_member.csv`:

| Flag | Meaning |
| --- | --- |
| `missing_trade_date` | No transaction date |
| `missing_notification_date` | No date-notified, including schedules that leave out that column |
| `missing_amount` | No amount range marked |
| `invalid_amount` | An amount that isn't one of the form's ranges (e.g. `$.01`) |
| `missing_tx_type` | No purchase, sale or exchange marked |
| `notification_after_receipt_or_before_trade` | Notified before the trade, or after the Clerk received the report |
| `impossible_trade_date` | Trade dated after the report was received, or outside 2012–today |

A blank owner column is **not** flagged, because on the House form a blank owner means the member's own asset. Column K (a spouse or dependent-child transaction over $1,000,000) is a permitted way to report an amount, so it isn't flagged either. On e-filed reports, a transaction type counts as missing only when the field itself is empty, so a parser miss isn't blamed on the filer.

## Data sources

| Source | Used for |
| --- | --- |
| [House Clerk financial disclosures](https://disclosures-clerk.house.gov/FinancialDisclosure/ViewReport) | Yearly index of every House filing (`{YEAR}FD.ZIP`) |
| [unitedstates/congress-legislators](https://github.com/unitedstates/congress-legislators) | Member IDs, party, districts, terms, committees |

## Tables (`data/processed/`)

| Table | One row per | Notes |
| --- | --- | --- |
| `member` | Member who served in 2019 or later (House and Senate) | `bioguide_id` is the join key; includes FEC and OpenSecrets IDs |
| `member_term` | Term served in 2019 or later | Type, state, district, party, start and end dates |
| `committee_membership` | Member × committee or subcommittee (current Congress) | |
| `filing` | House disclosure filing, 2020–2026 | `format` = e-filed / scanned; `source_url` points to the PDF; `bioguide_id` and `match_method` (`district` or `state`) link the filer to a member |
| `filing_type` | Filing type code | `confirmed = false` means the label is a best guess; it hasn't been checked against Clerk documentation |

## Phase 0 findings (House index as published Nov 20, 2026)

- 17,928 House filings were indexed from 2020 to 2026. Of these, 3,940 are trade reports (PTRs) filed by 270 different members.
- 3,938 of the 3,940 PTRs (99.9%) are linked to a member. The other 2 come from non-members.
- 623 PTRs (15.8%) are paper scans that will need OCR. Scans are concentrated among a few heavy filers: every PTR from Ro Khanna (83), Harold Rogers (81) and Michael McCaul (80) is a scan. Skipping scanned filings would leave out some of the most active traders.

| Year | PTRs | E-filed | Scanned | Members filing |
| --- | --- | --- | --- | --- |
| 2020 | 733 | 597 | 136 | 119 |
| 2021 | 680 | 565 | 115 | 124 |
| 2022 | 624 | 505 | 119 | 116 |
| 2023 | 460 | 388 | 72 | 101 |
| 2024 | 451 | 394 | 57 | 98 |
| 2025 | 515 | 449 | 66 | 108 |
| 2026 (to Nov 20) | 477 | 419 | 58 | 111 |

## Use of this data

## Permitted use

The financial disclosure data on this site comes from reports filed under the
Ethics in Government Act of 1978, as amended. By law, these reports may not be
used:

- for any unlawful purpose;
- for any commercial purpose, other than by news and communications media for
  dissemination to the general public;
- for determining or establishing the credit rating of any individual; or
- for use, directly or indirectly, in the solicitation of money for any
  political, charitable, or other purpose.

These restrictions apply to anyone who downloads or reuses this data.
Sources: Clerk of the U.S. House of Representatives, Secretary of the U.S.
Senate, and the U.S. Office of Government Ethics (OGE).

These reports are public under the Ethics in Government Act. Under [5 U.S.C. § 13107(c)](https://uscode.house.gov/us/usc/119-120/t5/s13107/), it is unlawful to use them for any unlawful purpose, for a commercial purpose (except by news media sharing them with the public), to determine anyone's credit rating, or to solicit money for any political, charitable or other purpose. This project is free, non-commercial and does no fundraising with the data.
