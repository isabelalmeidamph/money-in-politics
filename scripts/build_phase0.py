"""Phase 0: load House Clerk FD indexes + congress-legislators roster into DuckDB/Parquet,
and link each House filing to a member's bioguide ID.

Usage: python3 scripts/build_phase0.py data/house_index refs data/processed
"""
import sys, re, unicodedata, datetime as dt
from pathlib import Path
import duckdb, yaml
from rapidfuzz import fuzz

raw_dir, refs_dir, out_dir = map(Path, sys.argv[1:4])
out_dir.mkdir(parents=True, exist_ok=True)

# Filing type codes seen in the index. P/O/A/C/X/T are documented by the Clerk;
# the rest are best guesses and are flagged as such.
FILING_TYPES = {
    "P": ("Periodic Transaction Report", True),
    "O": ("Annual report (original)", True),
    "A": ("Amendment", True),
    "C": ("Candidate report", True),
    "X": ("Extension request", True),
    "T": ("Termination report", True),
    "D": ("Unconfirmed (D)", False),
    "H": ("Unconfirmed (H) - likely new filer", False),
    "W": ("Unconfirmed (W) - likely withdrawal/waiver", False),
    "B": ("Unconfirmed (B)", False),
    "G": ("Unconfirmed (G)", False),
    "E": ("Unconfirmed (E)", False),
}

def norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z ]", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()

# ---------- members ----------
members, terms = [], []
for fname in ["legislators-current.yaml", "legislators-historical.yaml"]:
    for p in yaml.safe_load(open(refs_dir / fname)):
        last_term_end = p["terms"][-1]["end"]
        if str(last_term_end) < "2019-01-01":
            continue  # irrelevant to 2020+ filings
        n, b = p["name"], p["id"]["bioguide"]
        cur = p["terms"][-1]
        members.append(dict(
            bioguide_id=b, first=n.get("first"), last=n.get("last"),
            nickname=n.get("nickname"), official_full=n.get("official_full"),
            party=cur.get("party"), state=cur.get("state"),
            district=cur.get("district"), chamber="House" if cur["type"] == "rep" else "Senate",
            is_current=fname.endswith("current.yaml"),
            fec_ids=",".join(p["id"].get("fec", []) or []),
            opensecrets_id=p["id"].get("opensecrets"),
        ))
        for t in p["terms"]:
            if str(t["end"]) < "2019-01-01":
                continue
            terms.append(dict(bioguide_id=b, type=t["type"], state=t["state"],
                              district=t.get("district"), party=t.get("party"),
                              start=str(t["start"]), end=str(t["end"])))

con = duckdb.connect()
con.register("members_df", __import__("pandas").DataFrame(members))
con.register("terms_df", __import__("pandas").DataFrame(terms))
con.sql("create table member as select * from members_df")
con.sql("create table member_term as select * from terms_df")

# committees (current only)
cm = yaml.safe_load(open(refs_dir / "committee-membership-current.yaml"))
cms = yaml.safe_load(open(refs_dir / "committees-current.yaml"))
cname = {}
for c in cms:
    cname[c["thomas_id"]] = c["name"]
    for sc in c.get("subcommittees", []) or []:
        cname[c["thomas_id"] + sc["thomas_id"]] = c["name"] + " - " + sc["name"]
rows = [dict(committee_id=k, committee_name=cname.get(k), bioguide_id=m["bioguide"],
             role=m.get("title"), rank=m.get("rank"), party=m.get("party"))
        for k, ms in cm.items() for m in ms]
con.register("cm_df", __import__("pandas").DataFrame(rows))
con.sql("create table committee_membership as select * from cm_df")

# ---------- filings ----------
con.sql(f"""
create table filing as
select DocID as filing_id, FilingType as filing_type, trim(coalesce(Prefix,'')) prefix,
       Last as last, First as first, Suffix as suffix, StateDst as state_dst,
       cast(Year as int) as report_year, strptime(FilingDate, '%m/%d/%Y')::date as filed_date,
       case when length(DocID)=8 and DocID like '2%' then 'e-filed'
            when length(DocID)=7 then 'scanned' else 'other' end as format,
       case when FilingType='P' then 'https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/' || Year || '/' || DocID || '.pdf'
            else 'https://disclosures-clerk.house.gov/public_disc/financial-pdfs/' || Year || '/' || DocID || '.pdf' end as source_url,
       'House' as chamber
from read_csv('{raw_dir}/**/*FD.txt', delim='\t', header=true, all_varchar=true)
""")
con.register("ft_df", __import__("pandas").DataFrame(
    [dict(filing_type=k, label=v[0], confirmed=v[1]) for k, v in FILING_TYPES.items()]))
con.sql("create table filing_type as select * from ft_df")

# ---------- link filings to members ----------
reps = con.sql("""select t.bioguide_id, t.state, t.district, t.start, t.end, m.first, m.last, m.nickname, m.official_full
                  from member_term t join member m using (bioguide_id) where t.type='rep'""").fetchall()
fil = con.sql("select filing_id, filing_type, first, last, state_dst, report_year, filed_date from filing").fetchall()

def name_score(f_first, f_last, m):
    _, _, _, _, _, mfirst, mlast, mnick, mfull = m
    fl, ml = norm(f_last), norm(mlast)
    last = max(fuzz.ratio(fl, ml), 100 if ml and (ml in fl or fl in ml) else 0,
               fuzz.token_set_ratio(fl, norm(mfull)) if mfull else 0)
    ff = norm(f_first).split(" ")[0] if f_first else ""
    firsts = {norm(mfirst).split(" ")[0] if mfirst else "", norm(mnick) if mnick else ""}
    first = max((fuzz.ratio(ff, x) for x in firsts if x), default=0)
    return last, first

links = []
for fid, ftype, first, last, sd, ry, fd in fil:
    st, dist = (sd[:2], int(sd[2:])) if sd and re.match(r"^[A-Z]{2}\d{2}$", sd) else (None, None)
    fy = fd.year if fd else ry
    lo = dt.date(min(ry, fy) - 1, 1, 1).isoformat()
    hi = dt.date(max(ry, fy) + 1, 12, 31).isoformat()
    best = None
    # pass 1: same state + district, term overlapping the report window
    # pass 2: same state, any district (redistricting / renumbering)
    for passno, cands in ((1, [r for r in reps if r[1] == st and r[2] == dist]),
                          (2, [r for r in reps if r[1] == st])):
        for r in cands:
            if r[4] < lo or r[3] > hi:
                continue
            ls, fs = name_score(first, last, r)
            score = ls * 0.7 + fs * 0.3
            if ls >= 85 and (passno == 1 or fs >= 80) and (best is None or score > best[1]):
                best = (r[0], score, "district" if passno == 1 else "state")
        if best:
            break
    links.append(dict(filing_id=fid, bioguide_id=best[0] if best else None,
                      match_method=best[2] if best else None,
                      match_score=round(best[1], 1) if best else None))

con.register("links_df", __import__("pandas").DataFrame(links))
con.sql("""create table filing2 as select f.*, l.bioguide_id, l.match_method, l.match_score
           from filing f left join (select distinct * from links_df) l using (filing_id)""")
con.sql("drop table filing"); con.sql("alter table filing2 rename to filing")

for t in ["member", "member_term", "committee_membership", "filing", "filing_type"]:
    con.sql(f"copy {t} to '{out_dir}/{t}.parquet' (format parquet)")
print("done")
