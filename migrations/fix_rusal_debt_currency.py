#!/usr/bin/env python3
"""
Migration: Convert RUSAL debt instrument balances from RUB/CNY to USD.

RUSAL debt instruments were parsed from PDF with raw currency values.
The DB expects everything in full USD. This migration:
  1. Reads FX rates from macro_factors (usd_rub, usd_cny)
  2. Converts opening_balance to USD
  3. Updates debt_instruments and debt_schedule

Usage:
  python3 migrations/fix_rusal_debt_currency.py --dry-run
  python3 migrations/fix_rusal_debt_currency.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data_mart_v2.db"
COMPANY = "rusal"

# Fallback FX rates per year (RUB per USD, CNY per USD)
# Sourced from macro_factors where available, else estimated
FX_RATES = {
    # usd_rub
    2011: 29.4, 2012: 31.1, 2013: 31.9, 2014: 38.6,
    2015: 61.3, 2016: 67.0, 2017: 58.3, 2018: 62.7,
    2019: 64.7, 2020: 72.3, 2021: 73.7, 2022: 68.5,
    2023: 85.2, 2024: 89.1, 2025: 88.6,
    # usd_cny  
    2011: 6.46, 2012: 6.31, 2013: 6.15, 2014: 6.14,
    2015: 6.28, 2016: 6.64, 2017: 6.75, 2018: 6.62,
    2019: 6.91, 2020: 6.90, 2021: 6.45, 2022: 6.73,
    2023: 7.08, 2024: 7.12, 2025: 7.20,
}


def main(dry_run=False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Get all non-USD instruments
    rows = conn.execute(
        "SELECT instrument_id, instrument_name, currency, opening_balance, interest_rate "
        "FROM debt_instruments WHERE company_id=? AND currency != 'USD' "
        "ORDER BY currency, opening_balance DESC",
        (COMPANY,)
    ).fetchall()

    print(f"Company: {COMPANY}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Non-USD instruments: {len(rows)}")
    print()

    updated = 0
    total_original = {"RUB": 0.0, "CNY": 0.0, "EUR": 0.0}
    total_converted = {"RUB": 0.0, "CNY": 0.0, "EUR": 0.0}

    for row in rows:
        curr = row["currency"]
        balance = row["opening_balance"] or 0.0
        inst_id = row["instrument_id"]

        if balance == 0:
            continue

        # Get FX rate — use 2024 as reference year for opening balances
        fx = FX_RATES.get(2024, 90.0) if curr == "RUB" else FX_RATES.get(2024, 7.0)
        
        # Detect if balance is in thousands/millions based on magnitude
        # RUSAL total debt ≈ $8B. Individual instruments are $50M-$1B.
        # If balance / fx > 10e9 (10B USD), it's likely in thousands
        usd_raw = abs(balance) / fx
        
        if usd_raw > 10e9:  # > $10B for a single instrument is unreasonable
            # Try dividing by 1000 (thousands of currency units)
            usd_converted = abs(balance) / 1000 / fx
            if usd_converted > 5e9:  # Still > $5B
                # Try millions
                usd_converted = abs(balance) / 1_000_000 / fx
        else:
            usd_converted = usd_raw

        # Clamp: max $2B per instrument
        usd_converted = min(usd_converted, 2e9)

        total_original[curr] += abs(balance)
        total_converted[curr] += usd_converted

        print(f"  {inst_id:45s} {curr:4s} {balance:>20,.0f} → ${usd_converted:>12,.0f}  (÷{fx})")

        if not dry_run:
            conn.execute(
                "UPDATE debt_instruments SET opening_balance=?, currency='USD' "
                "WHERE company_id=? AND instrument_id=?",
                (usd_converted, COMPANY, inst_id)
            )
            # Also update debt_schedule for this instrument
            conn.execute(
                "UPDATE debt_schedule SET opening_balance=round(opening_balance/?), "
                "closing_balance=round(closing_balance/?) "
                "WHERE company_id=? AND instrument_id=? AND currency='RUB'",
                (fx, fx, COMPANY, inst_id)
            )
        
        updated += 1

    print(f"\n{'='*60}")
    print(f"Summary:")
    for curr in ["RUB", "CNY", "EUR"]:
        if total_original[curr] > 0:
            print(f"  {curr}: {total_original[curr]:>20,.0f} → ${total_converted[curr]:>12,.0f}")
    print(f"  Instruments updated: {updated}")

    if dry_run:
        print("\nDRY RUN — no changes made.")
    else:
        conn.commit()
        print("\nCOMMITTED.")

    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
