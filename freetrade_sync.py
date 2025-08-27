import os, re, sys, csv, io, time, pytz, base64
from datetime import datetime
import pandas as pd
from dateutil import tz
from playwright.sync_api import sync_playwright
import pyotp

LONDON = pytz.timezone("Europe/London")
GH_PATH = os.environ.get("GH_PATH", "activity_log.csv")

FT_EMAIL = os.environ.get("FT_EMAIL")
FT_PASSWORD = os.environ.get("FT_PASSWORD")
FT_TOTP_SECRET = os.environ.get("FT_TOTP_SECRET")

def parse_money(x):
    if pd.isna(x): return None
    s = str(x).strip()
    neg = False
    if s.startswith('(') and s.endswith(')'):
        neg = True
        s = s[1:-1]
    s = re.sub(r'[^0-9.\-]', '', s)
    if s in ("", "-", ".", "-."): return None
    val = float(s)
    return -val if neg else val

def parse_qty(x):
    if pd.isna(x): return None
    s = str(x).strip()
    s = re.sub(r'[^0-9.\-]', '', s)
    if s in ("", "-", ".", "-."): return None
    return float(s)

def to_yyyymmdd(dt_str):
    if pd.isna(dt_str): return None
    # Be forgiving: try multiple formats, treat as London local date
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d %b %Y", "%Y-%m-%d %H:%M:%S", "%d/%m/%Y %H:%M"):
        try:
            dt = datetime.strptime(str(dt_str), fmt)
            return dt.date().isoformat()
        except ValueError:
            continue
    # Last resort: pandas parser
    try:
        dt = pd.to_datetime(str(dt_str), dayfirst=True, utc=False)
        if getattr(dt, 'tzinfo', None) is not None:
            dt = dt.tz_convert(LONDON).to_pydatetime()
        return dt.date().isoformat()
    except Exception:
        return None

def normalise(df):
    cols = {c.lower().strip(): c for c in df.columns}

    def pick(options):
        for o in options:
            if o.lower() in cols: return cols[o.lower()]
        # fuzzy contains
        for o in options:
            for k in cols:
                if o.lower() in k:
                    return cols[k]
        return None

    c_date = pick(["date","time","timestamp","created"])
    c_type = pick(["type","action","activity"])
    c_asset = pick(["instrument","ticker","name","asset","security"])
    c_qty  = pick(["quantity","shares","units","qty"])
    c_val  = pick(["amount","value","total","price","consideration"])

    if not c_date or not c_type or not c_asset:
        raise RuntimeError("Normalise: required columns not found in export")

    out = pd.DataFrame()
    out["Date"] = df[c_date].map(to_yyyymmdd)
    out["Type"] = df[c_type].astype(str).str.strip()
    out["Asset"] = df[c_asset].astype(str).str.strip()
    out["Quantity"] = parse_series(df[c_qty]) if c_qty else None
    out["Value"] = parse_series(df[c_val]) if c_val else None
    out["Notes"] = ""

    # ensure numeric
    if "Quantity" in out: out["Quantity"] = pd.to_numeric(out["Quantity"], errors="coerce")
    if "Value" in out:    out["Value"] = pd.to_numeric(out["Value"], errors="coerce")

    # order & drop NA dates
    out = out[["Date","Type","Asset","Quantity","Value","Notes"]]
    out = out.dropna(subset=["Date"])
    return out

def parse_series(s):
    return s.apply(lambda v: parse_money(v) if isinstance(v, str) and re.search(r'[£$€()]', v) else parse_qty(v))

def export_csv_with_playwright() -> bytes:
    if not FT_EMAIL or not FT_PASSWORD:
        raise RuntimeError("Login: FT_EMAIL/FT_PASSWORD not provided")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(accept_downloads=True, locale="en-GB")
        page = context.new_page()
        page.goto("https://web.freetrade.io/activity", wait_until="domcontentloaded")

        # If login form appears
        if page.get_by_label("Email").is_visible(timeout=5000) or page.locator("input[type='email']").count():
            page.fill("input[type='email']", FT_EMAIL)
            # Some UIs split steps; be defensive:
            if page.get_by_role("button", name=re.compile("Continue|Next|Sign in", re.I)).count():
                page.get_by_role("button", name=re.compile("Continue|Next|Sign in", re.I)).first.click()
                page.wait_for_timeout(1000)

            if page.locator("input[type='password']").count():
                page.fill("input[type='password']", FT_PASSWORD)
                page.get_by_role("button", name=re.compile("Sign.*in|Log.*in|Continue", re.I)).first.click()

        # 2FA
        try:
            code_field = page.get_by_label(re.compile("code|2fa|verification", re.I))
            if code_field.is_visible(timeout=5000):
                if not FT_TOTP_SECRET:
                    raise RuntimeError("Login: 2FA required but FT_TOTP_SECRET not set")
                totp = pyotp.TOTP(FT_TOTP_SECRET).now()
                code_field.fill(totp)
                page.get_by_role("button", name=re.compile("Verify|Continue|Submit", re.I)).first.click()
        except Exception:
            pass

        # Ensure Activity page
        page.wait_for_load_state("networkidle", timeout=30000)
        # Try to switch to "View all"
        try:
            page.get_by_role("tab", name=re.compile("View all", re.I)).click(timeout=3000)
        except Exception:
            pass

        # Try to set date range
        try:
            page.get_by_role("button", name=re.compile("Last.*months|Date range|Filter", re.I)).first.click()
            if page.get_by_role("option", name=re.compile("Last 3 months", re.I)).count():
                page.get_by_role("option", name=re.compile("Last 3 months", re.I)).click()
            elif page.get_by_role("option", name=re.compile("Last 6 months", re.I)).count():
                page.get_by_role("option", name=re.compile("Last 6 months", re.I)).click()
        except Exception:
            pass

        # Export CSV
        download = None
        try:
            with page.expect_download(timeout=20000) as dl_info:
                # “Export CSV” then “Export all activity”
                if page.get_by_role("button", name=re.compile("Export CSV", re.I)).count():
                    page.get_by_role("button", name=re.compile("Export CSV", re.I)).click()
                    time.sleep(0.5)
                if page.get_by_role("menuitem", name=re.compile("Export all activity|CSV", re.I)).count():
                    page.get_by_role("menuitem", name=re.compile("Export all activity|CSV", re.I)).click()
                else:
                    # fallback: single button export
                    page.get_by_role("button", name=re.compile("Export", re.I)).first.click()
            download = dl_info.value
        except Exception:
            # fallback: Statements tab
            try:
                page.get_by_role("tab", name=re.compile("Statements", re.I)).click()
                with page.expect_download(timeout=20000) as dl_info:
                    page.get_by_role("button", name=re.compile("Export.*CSV|Download", re.I)).first.click()
                download = dl_info.value
            except Exception as e:
                raise RuntimeError(f"Export: CSV export UI not found ({e})")

        bytes_csv = download.content()
        context.close(); browser.close()
        return bytes_csv

def main():
    try:
        raw = export_csv_with_playwright()
    except Exception as e:
        print(f"FAILURE: {e}")
        sys.exit(2)

    # Load CSV (auto-detect delimiter)
    df = pd.read_csv(io.BytesIO(raw))
    try:
        canon = normalise(df)
    except Exception as e:
        print(f"FAILURE: Normalise step: {e}")
        sys.exit(3)

    # Merge with existing
    if os.path.exists(GH_PATH):
        existing = pd.read_csv(GH_PATH)
    else:
        existing = pd.DataFrame(columns=["Date","Type","Asset","Quantity","Value","Notes"])

    before = len(existing)
    merged = pd.concat([existing, canon], ignore_index=True)

    # De-dup by compound key
    merged["__key"] = merged["Date"].astype(str) + "||" + merged["Type"].astype(str) + "||" + merged["Asset"].astype(str) + "||" + merged["Quantity"].astype(str) + "||" + merged["Value"].astype(str)
    merged = merged.drop_duplicates(subset="__key").drop(columns="__key")

    # Sort ascending by Date
    merged["Date"] = pd.to_datetime(merged["Date"], errors="coerce")
    merged = merged.dropna(sub
