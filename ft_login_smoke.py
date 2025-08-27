name: Freetrade Login Smoke Test

on:
  workflow_dispatch:

permissions:
  contents: read

jobs:
  login:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install playwright pyotp
          python -m playwright install --with-deps chromium

      - name: Run login test
        env:
          FT_EMAIL: ${{ secrets.FT_EMAIL }}
          FT_PASSWORD: ${{ secrets.FT_PASSWORD }}
          FT_TOTP_SECRET: ${{ secrets.FT_TOTP_SECRET }}
        run: |
          python .github/scripts/ft_login_smoke.py

      - name: Upload screenshot
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: freetrade-login-screenshot
          path: .github/scripts/ft_login_smoke.png
          if-no-files-found: warn

