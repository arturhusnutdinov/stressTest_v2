#!/usr/bin/env python3
"""
Phase 2: Fix RUSAL debt instrument balances using debt_schedule as source of truth.

Problem: debt_instruments.opening_balance stores raw currency values
(RUB/CNY in quadrillions — parser multiplied by 1e6 without FX conversion).
But debt_schedule for 2025 already has correct USD-converted values.

Solution:
  1. For each instrument, get 2024 closing_balance from debt_schedule
     (this is the opening balance for 2025 forecast)
  2. Update debt_instruments.opening_balance and set currency='USD'
  3. For instruments without schedule data, use BS debt allocation

Usage:
  python3 migrations/fix_rusal_debt_currency_v2.py --dry-run
  python3 migrations/fix_rusal_debt_currency_v2.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data_mart_v2.db"
COMPANY = "rusal"


def main(dry_run=False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    print(f"Company: {COMPANY}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    # Get period_id for 2024 (last historical year with debt schedule)
    p2024 = conn.execute(
        "SELECT period_id FROM periods WHERE company_id=? AND year=2024 AND is_annual=1",
        (COMPANY,)
    ).fetchone()
    
    if not p2024:
        print("ERROR: No 2024 period found")
        conn.close()
        return
    
    period_2024 = p2024["period_id"]
    
    # Get debt_schedule closing balances for 2024 (opening for 2025)
    schedule_2024 = {}
    rows = conn.execute(
        "SELECT instrument_id, closing_balance FROM debt_schedule "
        "WHERE company_id=? AND period_id=? AND closing_balance IS NOT NULL AND closing_balance != 0",
        (COMPANY, period_2024)
    ).fetchall()
    
    if not rows:
        # Try 2025 as fallback (use its opening_balance)
        p2025 = conn.execute(
            "SELECT period_id FROM periods WHERE company_id=? AND year=2025 AND is_annual=1",
            (COMPANY,)
        ).fetchone()
        if p2025:
            rows = conn.execute(
                "SELECT instrument_id, opening_balance as closing_balance FROM debt_schedule "
                "WHERE company_id=? AND period_id=? AND opening_balance IS NOT NULL AND opening_balance != 0",
                (COMPANY, p2025["period_id"])
            ).fetchall()
            print(f"Using 2025 opening_balance as fallback ({len(rows)} instruments)")
    
    for r in rows:
        schedule_2024[r["instrument_id"]] = abs(r["closing_balance"])
    
    print(f"Instruments with schedule data: {len(schedule_2024)}")
    
    # Get all non-USD instruments
    instruments = conn.execute(
        "SELECT instrument_id, instrument_name, currency, opening_balance, db_type "
        "FROM debt_instruments WHERE company_id=? AND currency != 'USD' "
        "ORDER BY currency, opening_balance DESC",
        (COMPANY,)
    ).fetchall()
    
    print(f"Non-USD instruments: {len(instruments)}")
    print()
    
    updated = 0
    skipped = 0
    total_old = 0.0
    total_new = 0.0
    
    for inst in instruments:
        inst_id = inst["instrument_id"]
        curr = inst["currency"]
        old_bal = abs(inst["opening_balance"] or 0)
        
        if old_bal == 0:
            skipped += 1
            continue
        
        # Get correct USD value from schedule
        new_bal = schedule_2024.get(inst_id)
        
        if new_bal is None:
            # No schedule data — estimate from BS allocation
            # BS total debt 2024 = $7.918B
            # Skip instruments with no schedule data
            print(f"  SKIP {inst_id:45s} {curr}: no schedule data, balance={old_bal:>.0f}")
            skipped += 1
            continue
        
        total_old += old_bal
        total_new += new_bal
        
        print(f"  {inst_id:45s} {curr} → \${new_bal:>15,.0f} (was {old_bal:>.0f})")
        
        if not dry_run:
            conn.execute(
                "UPDATE debt_instruments SET opening_balance=?, currency='USD' "
                "WHERE company_id=? AND instrument_id=?",
                (new_bal, COMPANY, inst_id)
            )
        updated += 1
    
    print(f"\n{'='*60}")
    print(f"Updated: {updated}  Skipped: {skipped}")
    print(f"Total old (raw): {total_old:,.0f}")
    print(f"Total new (USD): ${total_new:,.0f}")
    
    if dry_run:
        print("DRY RUN — no changes made.")
    else:
        conn.commit()
        print("COMMITTED.")
    
    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
