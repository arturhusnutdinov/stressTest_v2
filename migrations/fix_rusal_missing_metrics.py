#!/usr/bin/env python3
"""
Migration: Add missing canonical metric names for RUSAL.
Copies values from existing equivalent metrics — additive only, no deletes.

Engine expects these metric names (from ModelInputLoader._build_base_year_state):
  IS: depreciation_owned, depreciation_rou, amortization, net_periodic_benefit_income
  BS: restricted_cash, interest_payable, payroll_payable, treasury_stock, total_liab_equity
  CF: cash_ending

RUSAL DB has these equivalents:
  IS: dep_ppe → depreciation_owned, amort_intangibles → amortization
  BS: (some missing entirely, some computable)
  CF: cash_closing → cash_ending

Usage:
  python3 migrations/fix_rusal_missing_metrics.py --dry-run
  python3 migrations/fix_rusal_missing_metrics.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data_mart_v2.db"
COMPANY = "rusal"

# ── Mappings: canonical_name → (source_metric, default_value_if_missing) ──
IS_ALIASES = {
    "depreciation_owned": ("dep_ppe", None),
    "depreciation_rou": (None, 0.0),           # RUSAL IFRS 16: rou dep in lease schedule
    "amortization": ("amort_intangibles", None),
    "net_periodic_benefit_income": ("net_periodic_benefit", 0.0),
}

BS_ALIASES = {
    "restricted_cash": (None, 0.0),
    "interest_payable": (None, 0.0),            # Will be computed by InterestPayableBlock
    "payroll_payable": (None, 0.0),             # Computed as 10% of SGA
    "treasury_stock": (None, 0.0),
    "total_liab_equity": (None, None),          # Computed below from total_liabilities + total_equity
}

CF_ALIASES = {
    "cash_ending": ("cash_closing", None),
}


def ensure_period(conn, company, year):
    """Get or create period_id."""
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


def copy_metric(conn, company, year, canonical, source_metric, default_val):
    """Copy a metric value from source to canonical name."""
    period_id = ensure_period(conn, company, year)

    # Get source value
    if source_metric:
        row = conn.execute(
            "SELECT value FROM history_is WHERE company_id=? AND period_id=? AND metric=?",
            (company, period_id, source_metric)
        ).fetchone()
        if row:
            val = row[0]
        elif default_val is not None:
            val = default_val
        else:
            return False
    else:
        if default_val is not None:
            val = default_val
        else:
            return False

    # Upsert
    conn.execute(
        """INSERT INTO history_is (company_id, period_id, metric, value, source, updated_at)
           VALUES (?,?,?,?,'migration_fix_rusal_missing',CURRENT_TIMESTAMP)
           ON CONFLICT(company_id, period_id, metric) DO NOTHING""",
        (company, period_id, canonical, val)
    )
    return True


def copy_bs_metric(conn, company, year, canonical, source_metric, default_val):
    """Copy a metric value to history_bs."""
    period_id = ensure_period(conn, company, year)

    if source_metric:
        row = conn.execute(
            "SELECT value FROM history_bs WHERE company_id=? AND period_id=? AND metric=?",
            (company, period_id, source_metric)
        ).fetchone()
        if row:
            val = row[0]
        elif default_val is not None:
            val = default_val
        else:
            return False
    else:
        if default_val is not None:
            val = default_val
        else:
            return False

    conn.execute(
        """INSERT INTO history_bs (company_id, period_id, metric, value, source, updated_at)
           VALUES (?,?,?,?,'migration_fix_rusal_missing',CURRENT_TIMESTAMP)
           ON CONFLICT(company_id, period_id, metric) DO NOTHING""",
        (company, period_id, canonical, val)
    )
    return True


def copy_cf_metric(conn, company, year, canonical, source_metric, default_val):
    """Copy a metric value to history_cf."""
    period_id = ensure_period(conn, company, year)

    if source_metric:
        row = conn.execute(
            "SELECT value FROM history_cf WHERE company_id=? AND period_id=? AND metric=?",
            (company, period_id, source_metric)
        ).fetchone()
        if row:
            val = row[0]
        elif default_val is not None:
            val = default_val
        else:
            return False
    else:
        if default_val is not None:
            val = default_val
        else:
            return False

    conn.execute(
        """INSERT INTO history_cf (company_id, period_id, metric, value, source, updated_at)
           VALUES (?,?,?,?,'migration_fix_rusal_missing',CURRENT_TIMESTAMP)
           ON CONFLICT(company_id, period_id, metric) DO NOTHING""",
        (company, period_id, canonical, val)
    )
    return True


def main(dry_run=False):
    conn = sqlite3.connect(str(DB_PATH))
    
    years = [
        row[0] for row in conn.execute(
            "SELECT DISTINCT p.year FROM history_is h JOIN periods p ON h.period_id=p.period_id "
            "WHERE h.company_id=? ORDER BY p.year", (COMPANY,)
        ).fetchall()
    ]
    
    print(f"Company: {COMPANY}")
    print(f"Years: {years[0]}–{years[-1]} ({len(years)} years)")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print()
    
    total_added = 0
    
    # ── IS ──────────────────────────────────────────────────────────
    print("── IS canonical aliases ──")
    for canonical, (source, default) in IS_ALIASES.items():
        added = 0
        for year in years:
            if dry_run:
                # Just check if it already exists
                period_id = conn.execute(
                    "SELECT period_id FROM periods WHERE company_id=? AND year=?", 
                    (COMPANY, year)
                ).fetchone()
                if period_id:
                    exists = conn.execute(
                        "SELECT 1 FROM history_is WHERE company_id=? AND period_id=? AND metric=?",
                        (COMPANY, period_id[0], canonical)
                    ).fetchone()
                else:
                    exists = None
                    
                if not exists:
                    src_exists = False
                    if source:
                        src_exists = conn.execute(
                            "SELECT 1 FROM history_is WHERE company_id=? AND period_id=? AND metric=?",
                            (COMPANY, period_id[0], source) if period_id else (COMPANY, -1, source)
                        ).fetchone() is not None
                    added += 1
            else:
                if copy_metric(conn, COMPANY, year, canonical, source, default):
                    added += 1

        src_info = f"← {source}" if source else f"= {default}"
        print(f"  {canonical:35s} {src_info:30s} → {added} years")
        total_added += added

    # ── BS ──────────────────────────────────────────────────────────
    print("── BS canonical aliases ──")
    for canonical, (source, default) in BS_ALIASES.items():
        added = 0
        for year in years:
            if dry_run:
                period_id = conn.execute(
                    "SELECT period_id FROM periods WHERE company_id=? AND year=?", 
                    (COMPANY, year)
                ).fetchone()
                if period_id:
                    exists = conn.execute(
                        "SELECT 1 FROM history_bs WHERE company_id=? AND period_id=? AND metric=?",
                        (COMPANY, period_id[0], canonical)
                    ).fetchone()
                else:
                    exists = None
                if not exists:
                    # For total_liab_equity, check if we can compute it
                    if canonical == "total_liab_equity" and period_id:
                        tl = conn.execute(
                            "SELECT value FROM history_bs WHERE company_id=? AND period_id=? AND metric='total_liabilities'",
                            (COMPANY, period_id[0])
                        ).fetchone()
                        te = conn.execute(
                            "SELECT value FROM history_bs WHERE company_id=? AND period_id=? AND metric='total_equity'",
                            (COMPANY, period_id[0])
                        ).fetchone()
                        if tl and te:
                            added += 1
                    else:
                        added += 1
            else:
                if canonical == "total_liab_equity":
                    # Compute from total_liabilities + total_equity
                    period_id = ensure_period(conn, COMPANY, year)
                    tl_row = conn.execute(
                        "SELECT value FROM history_bs WHERE company_id=? AND period_id=? AND metric='total_liabilities'",
                        (COMPANY, period_id)
                    ).fetchone()
                    te_row = conn.execute(
                        "SELECT value FROM history_bs WHERE company_id=? AND period_id=? AND metric='total_equity'",
                        (COMPANY, period_id)
                    ).fetchone()
                    if tl_row and te_row:
                        val = abs(tl_row[0]) + abs(te_row[0])
                        conn.execute(
                            """INSERT INTO history_bs (company_id, period_id, metric, value, source, updated_at)
                               VALUES (?,?,?,?,'migration_fix_rusal_missing',CURRENT_TIMESTAMP)
                               ON CONFLICT(company_id, period_id, metric) DO UPDATE SET
                               value=excluded.value, source=excluded.source, updated_at=CURRENT_TIMESTAMP""",
                            (COMPANY, period_id, canonical, val)
                        )
                        added += 1
                else:
                    if copy_bs_metric(conn, COMPANY, year, canonical, source, default):
                        added += 1

        src_info = f"← {source}" if source else f"= {default}"
        print(f"  {canonical:35s} {src_info:30s} → {added} years")
        total_added += added

    # ── CF ──────────────────────────────────────────────────────────
    print("── CF canonical aliases ──")
    for canonical, (source, default) in CF_ALIASES.items():
        added = 0
        for year in years:
            if dry_run:
                period_id = conn.execute(
                    "SELECT period_id FROM periods WHERE company_id=? AND year=?", 
                    (COMPANY, year)
                ).fetchone()
                if period_id:
                    exists = conn.execute(
                        "SELECT 1 FROM history_cf WHERE company_id=? AND period_id=? AND metric=?",
                        (COMPANY, period_id[0], canonical)
                    ).fetchone()
                else:
                    exists = None
                if not exists and source:
                    src_exists = conn.execute(
                        "SELECT 1 FROM history_cf WHERE company_id=? AND period_id=? AND metric=?",
                        (COMPANY, period_id[0], source) if period_id else (COMPANY, -1, source)
                    ).fetchone() is not None
                    if src_exists:
                        added += 1
            else:
                if copy_cf_metric(conn, COMPANY, year, canonical, source, default):
                    added += 1

        src_info = f"← {source}" if source else f"= {default}"
        print(f"  {canonical:35s} {src_info:30s} → {added} years")
        total_added += added

    print(f"\n{'='*60}")
    print(f"Total metric-year pairs to add: {total_added}")
    
    if not dry_run:
        conn.commit()
        print("COMMITTED.")
    else:
        print("DRY RUN — no changes made.")

    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
