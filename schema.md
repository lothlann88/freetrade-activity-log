# Data Schema and Processing Notes

This repository stores the Freetrade activity export as the single source of truth and deterministically derives a current positions file for analysis and AI workflows.

## Files

1. `data/activity.csv`  
   Canonical activity feed. You may instead keep a single `data/activity-feed-export_*.csv`.  
   Only **one** activity file should exist at a time.

2. `data/holdings.csv`  
   Generated from the activity file by `scripts/build_holdings.py` via GitHub Actions.

3. `scripts/build_holdings.py`  
   Deterministic transformer from activity to holdings using pooled average cost.

4. `.github/workflows/build-holdings.yml`  
   Automation that regenerates `data/holdings.csv` on activity updates.

---

## Freetrade activity export schema

The script expects these headers **exactly** as produced by Freetrade:

- `Type`
- `Buy / Sell`
- `Ticker`
- `Title`
- `ISIN`
- `Quantity`
- `Instrument Currency`
- `Account Currency`
- `Total Shares Amount`
- `Total Amount`
- `FX Rate`
- `FX Fee Amount`
- `Stamp Duty`
- `Timestamp`

### Header meanings

- `Type`  
  Rows with value `ORDER` are processed. Others are ignored.

- `Buy / Sell`  
  Expected values: `BUY` or `SELL`.

- `Ticker`  
  Short code, for example `GAW`, `RR.`, `VOD`.

- `Title`  
  Instrument name, for example `Games Workshop`.

- `ISIN`  
  International identifier, useful for unambiguous joins.

- `Quantity`  
  Positive quantity of shares filled.

- `Instrument Currency`  
  The instrument’s trading currency, for example `GBP`, `USD`, `EUR`.

- `Account Currency`  
  The account’s cash currency, typically `GBP`.

- `Total Shares Amount`  
  **Instrument-currency** gross consideration for the shares only  
  (`price_per_share × quantity` in the
