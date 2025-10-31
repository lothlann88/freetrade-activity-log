# scripts/build_holdings.py
import csv, sys, pathlib, datetime
from collections import defaultdict, namedtuple

# Map your activity headers here if they differ
COL = {
    "date": "Date",
    "type": "Type",             # e.g. Buy, Sell, Dividend
    "ticker": "Ticker",         # e.g. GAW, RR., VOD
    "name": "Name",             # e.g. Games Workshop
    "currency": "Currency",     # e.g. GBP, USD
    "quantity": "Quantity",     # numeric
    "price": "Price",           # per-share price in trade currency
    "fee": "Fee",               # optional
    "stamp": "Stamp Duty",      # optional
}

BUY_TYPES = {"Buy"}
SELL_TYPES = {"Sell"}

def parse_decimal(x):
    if x is None or x == "":
        return 0.0
    return float(str(x).replace(",", ""))

def load_rows(path):
    with open(path, newline="", encoding="utf-8-sig") as f:
        r = csv.DictReader(f)
        for row in r:
            yield {
                "date": row.get(COL["date"], ""),
                "type": row.get(COL["type"], ""),
                "ticker": row.get(COL["ticker"], "").strip(),
                "name": row.get(COL["name"], "").strip(),
                "currency": row.get(COL["currency"], "").strip() or "GBP",
                "qty": parse_decimal(row.get(COL["quantity"], 0)),
                "price": parse_decimal(row.get(COL["price"], 0)),
                "fee": parse_decimal(row.get(COL.get("fee", ""), 0)),
                "stamp": parse_decimal(row.get(COL.get("stamp", ""), 0)),
            }

def build_holdings(activity_path, output_path):
    Pool = namedtuple("Pool", "qty cost name currency last_date")
    pools = {}  # key is (ticker, currency) to avoid FX mixing

    for row in load_rows(activity_path):
        k = (row["ticker"], row["currency"])
        pools.setdefault(k, Pool(0.0, 0.0, row["name"], row["currency"], ""))

        p = pools[k]
        date = row["date"] or p.last_date

        if row["type"] in BUY_TYPES:
            gross = row["qty"] * row["price"] + row["fee"] + row["stamp"]
            pools[k] = Pool(
                qty=p.qty + row["qty"],
                cost=p.cost + gross,
                name=row["name"] or p.name,
                currency=row["currency"],
                last_date=date,
            )

        elif row["type"] in SELL_TYPES:
            if p.qty <= 0:
                # ignore pathological sell with no pool
                continue
            avg = p.cost / p.qty if p.qty else 0.0
            qty_out = min(row["qty"], p.qty)
            cost_reduction = avg * qty_out
            pools[k] = Pool(
                qty=p.qty - qty_out,
                cost=p.cost - cost_reduction,
                name=row["name"] or p.name,
                currency=row["currency"],
                last_date=date,
            )
        else:
            # dividends and other lines do not change the pool
            pools[k] = Pool(p.qty, p.cost, p.name, p.currency, date)

    # Write holdings
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["ticker","name","currency","quantity","avg_entry_price","total_cost","last_txn_date","notes"])
        today = datetime.date.today().isoformat()
        for (ticker, currency), p in sorted(pools.items()):
            if p.qty <= 0:
                continue
            avg_price = p.cost / p.qty if p.qty else 0.0
            w.writerow([
                ticker, p.name, currency,
                f"{p.qty:.6f}",
                f"{avg_price:.6f}",
                f"{p.cost:.2f}",
                p.last_date or today,
                ""
            ])

if __name__ == "__main__":
    repo = pathlib.Path(__file__).resolve().parents[1]
    activity = repo / "data" / "activity.csv"
    output = repo / "data" / "holdings.csv"
    build_holdings(activity, output)
    print(f"Wrote {output}")

