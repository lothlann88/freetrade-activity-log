# Data Schema and Processing Notes

This repository keeps the Freetrade activity export as the single source of truth and derives a holdings snapshot using pooled average cost. The workflow also archives each processed activity file into `data/archive/`.

## Files

1. `data/activity.csv`  
   Canonical activity feed. Alternatively keep a single `data/activity-feed-export_*.csv`. Exactly one input file should be present at a time.

2. `data/holdings.csv`  
   Generated from the activity file by `scripts/build_holdings.py`.

3. `data/archive/`  
   Timestamped copies of processed activity files. Created by the workflow after a successful build.

4. `scripts/build_holdings.py`  
   Transformer from activity to holdings.

5. `.github/workflows/build-holdings.yml`  
   Workflow that builds holdings then archives the input.

---

## Expected Freetrade activity headers

These headers are used verbatim.

* `Type`
* `Buy / Sell`
* `Ticker`
* `Title`
* `ISIN`
* `Quantity`
* `Instrument Currency`
* `Account Currency`
* `Total Shares Amount`
* `Total Amount`
* `FX Rate`
* `FX Fee Amount`
* `Stamp Duty`
* `Timestamp`

### Header meanings

* `Type`  
  Rows with value `ORDER` are processed. All others are ignored.

* `Buy / Sell`  
  Expected values are `BUY` or `SELL`.

* `Ticker`  
  Short code such as `GAW`, `RR.`, `VOD`.

* `Title`  
  Instrument name.

* `ISIN`  
  Global security identifier.

* `Quantity`  
  Filled shares for the lot. Positive values.

* `Instrument Currency`  
  Trading currency for the instrument such as `GBP`, `USD`.

* `Account Currency`  
  Account cash currency such as `GBP`.

* `Total Shares Amount`  
  Consideration for shares only in instrument currency. This equals `price_per_share × quantity` in instrument currency and excludes fees.

* `Total Amount`  
  Cash movement in account currency. This includes FX fees and stamp duty where applicable.

* `FX Rate`  
  Instrument currency units per 1 GBP.

* `FX Fee Amount`  
  FX fee in account currency.

* `Stamp Duty`  
  UK stamp duty in account currency.

* `Timestamp`  
  ISO 8601 timestamp used to sort events.

---

## Derived holdings output schema

`data/holdings.csv` columns:

1. `ticker`
2. `title`
3. `isin`
4. `instrument_currency`
5. `account_currency`
6. `quantity`
7. `avg_entry_price_native`  
   Average entry per share in instrument currency, fee-inclusive.

8. `avg_entry_price_gbp`  
   Average entry per share in GBP, fee-inclusive.

9. `total_cost_native`  
   Pooled cost in instrument currency, fee-inclusive.

10. `total_cost_gbp`  
    Pooled cost in GBP, fee-inclusive.

11. `last_txn_timestamp`

Numeric fields are written with sensible precision. Consumers may round for display.

---

## Cost methodology

1. Rows are sorted by `Timestamp` ascending before processing.  
2. Buys increase `quantity` and pooled costs.  
   * Native cost increases by  
     `Total Shares Amount` plus FX fee converted to instrument currency plus stamp duty when the instrument is GBP.  
     FX fee in native currency equals `FX Fee Amount × FX Rate` when instrument and account currencies differ.  
   * GBP cost increases by `Total Amount` which already includes fees and stamp duty.

3. Sells reduce `quantity` and reduce both pooled costs using the current average cost method.  
   * Quantity reduced equals the lesser of the sell quantity and the pool quantity.  
   * Cost reduced equals `current_avg × quantity_reduced` for each of native and GBP pools.  
   * Realised profit is not calculated in this step. The goal is a clean holdings snapshot.

4. Non-order rows such as dividends do not affect holdings.

5. Pools are keyed by `(Ticker, Instrument Currency)` so positions and costs are never mixed across currencies.

---

## Archiving behaviour

1. After a successful build, the workflow moves any input file that matched the trigger into `data/archive/` using a UTC timestamped filename for traceability.  
   Example  
   `data/activity.csv → data/archive/2025_11_01_14_52_10__activity.csv`

2. The commit includes  
   * the updated `data/holdings.csv`  
   * the removal of the input file from `data/`  
   * the addition of the archived copy in `data/archive/`

3. Archiving is handled in the workflow, not in the Python script. This ensures the archive happens even when holdings do not change.

---

## Validation and failure modes

1. If more than one `data/activity-feed-export_*.csv` exists, the script exits and instructs you to keep a single input.  
2. If an expected header is missing, the script exits and lists missing columns.  
3. If the runner cannot push, check repository Actions workflow permissions and the `permissions: contents: write` block in the workflow YAML.

---

## Conventions and rationale

1. Averages shown in `holdings.csv` are fee-inclusive. This is correct for cost basis and will differ slightly from broker UI averages that often exclude fees.  
2. Both native and GBP costs are tracked so downstream analysis can report in either currency without re-deriving costs.  
3. Keeping GitHub as the source of truth makes the pipeline auditable and tool-agnostic.
