#!/usr/bin/env bash
# Download the source data for Phase 0. Run from the repo root.
#   bash scripts/fetch_sources.sh            # years 2020 through the current year
#   bash scripts/fetch_sources.sh 2024 2026  # a custom range
set -euo pipefail

START=${1:-2020}
END=${2:-$(date +%Y)}
UA="Mozilla/5.0 (money-in-politics; public-interest research)"

mkdir -p data/house_index refs tmp

# 1. House Clerk yearly financial-disclosure indexes (republished daily by the Clerk)
for y in $(seq "$START" "$END"); do
  echo "House index $y"
  curl -fsSL -A "$UA" -o "tmp/${y}FD.zip" \
    "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/${y}FD.ZIP"
  unzip -o -q "tmp/${y}FD.zip" "${y}FD.txt" -d data/house_index
  sleep 2  # be polite to the Clerk's server
done

# 2. Member roster and committees (unitedstates/congress-legislators)
BASE=https://raw.githubusercontent.com/unitedstates/congress-legislators/main
for f in legislators-current.yaml legislators-historical.yaml \
         committee-membership-current.yaml committees-current.yaml; do
  echo "roster $f"
  curl -fsSL -o "refs/$f" "$BASE/$f"
done

rm -rf tmp
echo "Done. Next: python3 scripts/build_phase0.py data/house_index refs data/processed"
