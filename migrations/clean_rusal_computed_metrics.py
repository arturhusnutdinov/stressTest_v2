#!/usr/bin/env python3
"""
Phase 1: Remove computed metrics from RUSAL raw history tables.

Engine computes these itself — having them in history_* causes confusion
and potential conflicts. This migration is safe: metrics that are ALWAYS
computed by the engine are removed from raw history.

BS computed: total_ca, total_cl, total_nca, total_ncl, total_liabilities
CF computed: net_change_cash

Usage:
  python3 migrations/clean_rusal_computed_metrics.py --dry-run
  python3 migrations/clean_rusal_computed_metrics.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data_mart_v2.db"
COMPANY = "rusal"

# Metrics engine ALWAYS computes from components
BS_COMPUTED = {"total_ca", "total_cl", "total_nca", "total_ncl", "total_liabilities"}
CF_COMPUTED = {"net_change_cash"}


def main(dry_run=False):
    conn = sqlite3.connect(str(DB_PATH))
    
    print(f"Company: {COMPANY}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    total_deleted = 0
    
    for table, metrics in [("history_bs", BS_COMPUTED), ("history_cf", CF_COMPUTED)]:
        print(f"── {table} ──")
        for metric in sorted(metrics):
            rows = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE company_id=? AND metric=?",
                (COMPANY, metric)
            ).fetchone()[0]
            
            if rows > 0:
                print(f"  DELETE {metric}: {rows} rows")
                if not dry_run:
                    conn.execute(
                        f"DELETE FROM {table} WHERE company_id=? AND metric=?",
                        (COMPANY, metric)
                    )
                total_deleted += rows
            else:
                print(f"  SKIP  {metric}: 0 rows (already clean)")
    
    print(f"\n{'='*60}")
    print(f"Total rows to delete: {total_deleted}")
    
    if dry_run:
        print("DRY RUN — no changes made.")
    else:
        conn.commit()
        print("COMMITTED.")
    
    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
