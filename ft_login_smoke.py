import os, re, sys, time
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
import pyotp

EMAIL = os.environ.get("FT_EMAIL")
PASSWORD = os.environ.get("FT_PASSWORD")
TOTP = os.environ.get("FT_TOTP_SECRET")

SCREENSHOT = ".github/scripts/ft_login_smoke.png"

def log(msg): print(msg, flush=True)

def try_click_any(page, selectors):
    for s in selectors:
        try:
            el = page.locator(s)
            if el.count() and el.first.is_visible():
                el.first.click(timeout=2000)
                return True
        except Exception:
            pass
    return False

def visible_any(page, selectors, timeout=5000):
    end = time.time() + timeout/1000
    while time.time() < end:
        for s in selectors:
            try:
                el = page.locator(s)
                if el.count() and el.first.is_visible():
                    return True
            except Exception:
                pass
        time.sleep(0.25)
    return False

def do_login(page):
    # Land on Activity page (redirects to sign-in if needed)
    page.goto("https://web.freetrade.io/activity", wait_until="domcontentloaded", timeout=60000)

    # Email step
    email_field = page.locator('input[type="email"], input[name="email"]')
    if email_field.count():
        if not EMAIL or not PASSWORD:
            raise RuntimeError("Credentials missing: set FT_EMAIL and FT_PASSWORD repo secrets.")
        email_field.first.fill(EMAIL)
        try_click_any(page, [
            'button:has-text("Continue")', 'button:has-text("Next")',
            'button:has-text("Sign in")', 'button:has-text("Log in")'
        ])
        page.wait_for_timeout(800)

    # Password step
    if page.locator('input[type="password"], input[name="password"]').count():
        page.locator('input[type="password"], input[name="password"]').first.fill(PASSWORD)
        try_click_any(page, [
            'button:has-text("Sign in")', 'button:has-text("Log in")',
            'button:has-text("Continue")', 'button[type="submit"]'
        ])

    # Possible 2FA
    # Look for any input likely to be the code field
    code_selectors = [
        'input[autocomplete="one-time-code"]',
        'input[name*="code" i]', 'input[name*="otp" i]',
        'input[aria-label*="code" i]',
        'input[placeholder*="code" i]'
    ]
    if visible_any(page, code_selectors, timeout=4000):
        if not TOTP:
            raise RuntimeError("2FA required but FT_TOTP_SECRET is not set. Re-run after adding it.")
        code = pyotp.TOTP(TOTP).now()
        page.locator(code_selectors[0]).first.fill(code)
        try_click_any(page, [
            'button:has-text("Verify")', 'button:has-text("Continue")', 'button:has-text("Submit")'
        ])

    # Wait for something that only appears when logged in
    logged_in_hints = [
        'role=tab[name="View all"]',
        'role=tab[name="Statements"]',
        'button:has-text("Export CSV")',
        'text=/Activity/i'
    ]
    if not visible_any(page, logged_in_hints, timeout=15000):
        raise RuntimeError("Login likely failed (activity UI not detected).")

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--disable-blink-features=AutomationControlled"]
        )
        context = browser.new_context(locale="en-GB", timezone_id="Europe/London")
        page = context.new_page()
        try:
            do_login(page)
            page.screenshot(path=SCREENSHOT, full_page=True)
            log(f"LOGIN_OK url={page.url}")
            context.close(); browser.close()
            sys.exit(0)
        except Exception as e:
            try:
                page.screenshot(path=SCREENSHOT, full_page=True)
            except Exception:
                pass
            log(f"FAILURE: {e}")
            try:
                context.close(); browser.close()
            except Exception:
                pass
            sys.exit(2)

if __name__ == "__main__":
    main()
