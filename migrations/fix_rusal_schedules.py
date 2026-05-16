#!/usr/bin/env python3
"""
Migration: Populate RUSAL lease_schedule and equity_schedule from parsed data.

Lease data from notes_lease_ppe_notes.json (values in mUSD → ×1e6 for DB).
Equity data from all_years_combined.json (BS equity components).

Usage:
  python3 migrations/fix_rusal_schedules.py --dry-run
  python3 migrations/fix_rusal_schedules.py
"""
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
DB_PATH = ROOT / "data_mart_v2.db"
COMPANY = "rusal"


def ensure_period(conn, company, year):
    row = conn.execute(
        "SELECT period_id FROM periods WHERE company_id=? AND year=? AND is_annual=1",
        (company, year)
    ).fetchone()
    if row:
        return row[0]
    conn.execute(
        "INSERT INTO periods (company_id, year, is_annual, is_forecast) VALUES (?,?,1,0)",
        (company, year)
    )
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def populate_lease_schedule(conn, dry_run=False):
    """Populate lease_schedule from parsed lease notes."""
    lease_path = ROOT / "companies/rusal/data/parsed/notes_lease_ppe_notes.json"
    if not lease_path.exists():
        print("  Lease notes file not found, skipping.")
        return 0
    
    with open(lease_path) as f:
        data = json.load(f)
    
    added = 0
    
    for year_key in sorted(data.keys()):
        if not year_key.startswith("lease_"):
            continue
        year = int(year_key.split("_")[1])
        lease_data = data[year_key]
        
        period_id = ensure_period(conn, COMPANY, year)
        
        # Operating lease (IFRS 16 — single lease approach for all operating leases)
        rou_total = lease_data.get("rou_total")
        rou_land = lease_data.get("rou_land", 0) or 0
        rou_machinery = lease_data.get("rou_machinery", 0) or 0
        liab_cur = lease_data.get("lease_liab_current", 0) or 0
        liab_ncur = lease_data.get("lease_liab_noncurrent", 0) or 0
        dep_rou = lease_data.get("depreciation_rou", 0) or 0
        int_leases = lease_data.get("interest_leases", 0) or 0
        payments = lease_data.get("lease_payments", 0) or 0
        
        if rou_total is None and liab_cur is None:
            continue
        
        # Convert mUSD → full USD
        rou_total = (rou_total or 0) * 1_000_000
        liab_cur = liab_cur * 1_000_000
        liab_ncur = liab_ncur * 1_000_000
        dep_rou = dep_rou * 1_000_000
        int_leases = int_leases * 1_000_000
        payments = payments * 1_000_000
        rou_land = rou_land * 1_000_000
        rou_machinery = rou_machinery * 1_000_000
        
        total_liab = liab_cur + liab_ncur
        
        # Upsert operating lease aggregate row
        for lease_id, lease_name, rou_val, liab_val in [
            ("op_lease_land", "Operating Lease — Land", rou_land, 0),
            ("op_lease_machinery", "Operating Lease — Machinery", rou_machinery, 0),
            ("op_lease_total", "Operating Lease — Total", rou_total, total_liab),
        ]:
            if rou_val == 0 and liab_val == 0 and lease_id != "op_lease_total":
                continue
            
            existing = conn.execute(
                "SELECT 1 FROM lease_schedule WHERE company_id=? AND period_id=? AND lease_id=?",
                (COMPANY, period_id, lease_id)
            ).fetchone()
            
            if existing:
                continue
            
            if not dry_run:
                conn.execute(
                    """INSERT INTO lease_schedule 
                       (company_id, period_id, lease_id, lease_name, lease_type,
                        rou_open, rou_dep, rou_close, liab_open, interest_exp, payment, liab_close, discount_rate, source, updated_at)
                       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,'migration_fix_rusal_schedules',CURRENT_TIMESTAMP)""",
                    (COMPANY, period_id, lease_id, lease_name, "operating",
                     rou_val, dep_rou if lease_id == "op_lease_total" else 0, rou_val - dep_rou if lease_id == "op_lease_total" else rou_val,
                     liab_val, int_leases if lease_id == "op_lease_total" else 0,
                     payments if lease_id == "op_lease_total" else 0,
                     liab_val - payments + int_leases if lease_id == "op_lease_total" else liab_val,
                     0.08)  # estimated discount rate 8%
                )
            added += 1
    
    return added


def populate_equity_schedule(conn, dry_run=False):
    """Populate equity_schedule from parsed BS data."""
    equity_path = ROOT / "companies/rusal/data/parsed/all_years_combined.json"
    if not equity_path.exists():
        print("  All years file not found, skipping.")
        return 0
    
    with open(equity_path) as f:
        data = json.load(f)
    
    added = 0
    
    for year_str, year_data in sorted(data.items()):
        try:
            year = int(year_str)
        except ValueError:
            continue
        
        bs = year_data.get("bs", {})
        if not bs:
            continue
        
        period_id = ensure_period(conn, COMPANY, year)
        
        # Check if already populated
        existing = conn.execute(
            "SELECT 1 FROM equity_schedule WHERE company_id=? AND period_id=?",
            (COMPANY, period_id)
        ).fetchone()
        if existing:
            continue
        
        re_val = (bs.get("retained_earnings") or 0)
        # Values from BS are in mUSD → full USD
        # But some are already stored as full USD in history_bs...
        # The parsed JSON stores in mUSD, so multiply by 1e6
        if abs(re_val) < 1e6:  # < 1M means it's still in millions
            re_val *= 1_000_000
        
        share_cap = (bs.get("share_capital") or 0)
        if abs(share_cap) < 1e6:
            share_cap *= 1_000_000
        
        apic_val = (bs.get("apic") or 0)
        if abs(apic_val) < 1e6:
            apic_val *= 1_000_000
        
        if not dry_run:
            # Get net_income for this year
            is_data = year_data.get("is", {})
            ni = (is_data.get("net_income") or 0)
            if abs(ni) < 1e6:
                ni *= 1_000_000
            
            conn.execute(
                """INSERT INTO equity_schedule
                   (company_id, period_id, re_open, net_income, dividends, buybacks, 
                    issuance, other_equity_changes, re_close, source, updated_at)
                   VALUES (?,?,?,?,0,0,0,0,?,'migration_fix_rusal_schedules',CURRENT_TIMESTAMP)
                   ON CONFLICT(company_id, period_id) DO UPDATE SET
                   net_income=excluded.net_income, source=excluded.source, updated_at=CURRENT_TIMESTAMP""",
                (COMPANY, period_id, re_val, ni, re_val + ni)
            )
        added += 1
    
    return added


def main(dry_run=False):
    conn = sqlite3.connect(str(DB_PATH))
    
    print(f"Company: {COMPANY}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    print("── Lease Schedule ──")
    lease_added = populate_lease_schedule(conn, dry_run)
    print(f"  Rows to add: {lease_added}")
    
    print("── Equity Schedule ──")
    equity_added = populate_equity_schedule(conn, dry_run)
    print(f"  Rows to add: {equity_added}")
    
    print(f"\n{'='*60}")
    print(f"Total: {lease_added + equity_added} rows")
    
    if dry_run:
        print("DRY RUN — no changes made.")
    else:
        conn.commit()
        print("COMMITTED.")
    
    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
