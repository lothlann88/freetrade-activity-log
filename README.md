# Freetrade Activity Log to Holdings

This repository keeps a single source of truth for your Freetrade activity and deterministically derives a current holdings file for analysis and AI workflows.

See the companion specification in [`schema.md`](./schema.md).

## What lives here

1. `data/activity.csv` or a single `data/activity-feed-export_*.csv`  
   The canonical Freetrade export. Only one activity file should exist at any time.

2. `data/holdings.csv`  
   Generated positions table. Do not edit by hand.

3. `scripts/build_holdings.py`  
   The transformer from activity to holdings using pooled average cost.

4. `.github/workflows/build-holdings.yml`  
   GitHub Actions workflow that regenerates `data/holdings.csv` whenever the activity file changes.

## Quick start

1. Add your latest Freetrade export to `data/`  
   Option A: rename it to `data/activity.csv`  
   Option B: keep it as `data/activity-feed-export_YYYYMMDD.csv` and make sure there is only one such file in `data/`.

2. Push to `main`  
   The workflow runs and writes `data/holdings.csv`.

3. Point your analysis or AI tool at `data/holdings.csv`  
   The file contains quantities, pooled costs and average entry in native currency and in GBP.

## Local run

You can run the transformer locally to preview the result.

```bash
python3 scripts/build_holdings.py
