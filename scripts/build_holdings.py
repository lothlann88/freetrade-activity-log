#!/usr/bin/env python3
"""
Build holdings.csv from a Freetrade activity export.

Input location priority:
1) data/activity.csv
2) the single file matching data/activity-feed-export_*.csv
If neither exists, the script exits with a clear message.

This script matches the following headers exactly, as found in the Freetrade export:
Type, Buy / Sell, Ticker, Title, ISIN, Quantity, Instrument Currency, Account Currency,
Total Shares Amount, Total Amount, FX Rate, FX Fee Amount, Stamp Duty, Timestamp

Outputs: data/holdings.csv with columns
ticker,title,isin,instrument_currency,account_currency,quantity,
avg_entry_price_native,avg_entry_price_gbp,total_cost_native,total_cost_gbp,last_txn_timestamp
"""

from __future__ import annotations
import csv
import sys
import pathlib
from datetime import datetime, timezone

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA_DIR = REPO_ROOT / "data"
INPUT_PRIMARY = DATA_DIR / "activity.csv"

def find_input_csv() -> pathlib.Path:
    if INPUT_PRIMARY.exists():
        return INPUT_PRIMARY
    matches = sorted(DATA_DIR.glob("activity-feed-export_*.csv"))
    if len(matches) == 1:
        return matches[0]
    if len(matches) == 0:
        sys.exit("No input found. Place data/activity.csv or a single data/activity-feed-export_*.csv.")
    else:
        sys.exit("Multiple Freetrade exports found. Keep only one, or rename your chosen file to data/activity.csv.")

def fnum(x) -> float:
    try:
        if x is None:
            return 0.0
        s = str(x).strip()
        if s == "" or s.lower() == "nan":
            return 0.0
        return float(s)
    except Exception:
        return 0.0

def parse_ts(s: str) -> datetime | None:
    if not s:
        return None
    try:
        # CSV shows ISO with Z
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None

def build_holdings(input_path: pathlib.Path, output_path: pathlib.Path) -> None:
    # Pools keyed by (ticker, instrument_currency)
    pools = {}

    required = {
        "Type","Buy / Sell","Ticker","Title","ISIN","Quantity","Instrument Currency",
        "Account Currency","Total Shares Amount","Total Amount","FX Rate",
        "FX Fee Amount","Stamp Duty","Timestamp"
    }

    with input_path.open("r", newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        missing = [c for c in required if c not in r.fieldnames]
        if missing:
            sys.exit(f"Missing expected columns: {', '.join(sorted(missing))}")

        # sort rows by Timestamp ascending for correct pooled logic
        rows = list(r)
        rows.sort(key=lambda row: parse_ts(row.get("Timestamp","")) or datetime(1970,1,1, tzinfo=timezone.utc))

        for row in rows:
            if row["Type"] != "ORDER":
                continue
            side = row.get("Buy / Sell", "")
            if side not in {"BUY","SELL"}:
                continue

            ticker = row.get("Ticker","").strip()
            instr = row.get("Instrument Currency","").strip()
            acct  = row.get("Account Currency","").strip()
            if not ticker or not instr:
                continue

            qty = fnum(row.get("Quantity", 0))
            if qty <= 0:
                continue

            key = (ticker, instr)
            pool = pools.setdefault(key, {
                "qty": 0.0,
                "cost_native": 0.0,
                "cost_gbp": 0.0,
                "title": row.get("Title","").strip(),
                "isin": row.get("ISIN","").strip(),
                "instr_curr": instr,
                "acct_curr": acct,
                "last_ts": None,
            })

            total_shares_amt = fnum(row.get("Total Shares Amount", 0.0))   # instrument currency
            total_amount_gbp = fnum(row.get("Total Amount", 0.0))          # account currency
            stamp = fnum(row.get("Stamp Duty", 0.0))                       # account currency, GBP for UK
            fx_fee_amt = fnum(row.get("FX Fee Amount", 0.0))               # account currency
            fx_rate = fnum(row.get("FX Rate", 0.0))                        # instrument per GBP
            ts = parse_ts(row.get("Timestamp",""))

            # Convert FX fee into instrument currency when needed
            if instr == acct:
                fee_native = fx_fee_amt
            else:
                # FX Rate is instrument per GBP, so GBP -> instrument is multiply
                fee_native = fx_fee_amt * fx_rate if (fx_fee_amt and fx_rate) else 0.0

            # Stamp duty applies in GBP for UK equities, which equals instrument when instr == acct == GBP
            stamp_native = stamp if instr == acct else 0.0

            if side == "BUY":
                pool["qty"] += qty
                pool["cost_native"] += total_shares_amt + fee_native + stamp_native
                pool["cost_gbp"] += total_amount_gbp
            else:  # SELL
                if pool["qty"] > 0:
                    qty_out = min(qty, pool["qty"])
                    avg_n = pool["cost_native"] / pool["qty"] if pool["qty"] else 0.0
                    avg_g = pool["cost_gbp"] / pool["qty"] if pool["qty"] else 0.0
                    pool["cost_native"] -= avg_n * qty_out
                    pool["cost_gbp"] -= avg_g * qty_out
                    pool["qty"] -= qty_out

            pool["last_ts"] = ts or pool["last_ts"]

    # Write holdings
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow([
            "ticker","title","isin","instrument_currency","account_currency",
            "quantity","avg_entry_price_native","avg_entry_price_gbp",
            "total_cost_native","total_cost_gbp","last_txn_timestamp"
        ])
        for (ticker, instr), p in sorted(pools.items()):
            if p["qty"] <= 0:
                continue
            avg_n = p["cost_native"] / p["qty"] if p["qty"] else 0.0
            avg_g = p["cost_gbp"] / p["qty"] if p["qty"] else 0.0
            w.writerow([
                ticker,
                p["title"],
                p["isin"],
                p["instr_curr"],
                p["acct_curr"],
                f"{p['qty']:.6f}",
                f"{avg_n:.6f}",
                f"{avg_g:.6f}",
                f"{p['cost_native']:.6f}",
                f"{p['cost_gbp']:.6f}",
                p["last_ts"].isoformat() if p["last_ts"] else ""
            ])

if __name__ == "__main__":
    src = find_input_csv()
    dst = DATA_DIR / "holdings.csv"
    print(f"Reading {src}")
    build_holdings(src, dst)
    print(f"Wrote {dst}")
