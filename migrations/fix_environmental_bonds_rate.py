"""
Migration: fix_environmental_bonds_rate

Environmental Revenue Bonds ($1,104M) and Environmental Revenue Bonds - Big River Steel ($752M)
had interest_rate = NULL → fallback to avg_rate_pct = 5%.
Actual rate: tax-exempt fixed-coupon ~3.5% (US Steel 10-K footnotes; industrial revenue bonds).

Sets interest_rate = 3.5 (%) and rate_type = 'floating' so rate_spike stress scenario
applies a rate delta to them (they reference short-term tax-exempt rates which float with
benchmark rates, unlike fixed senior notes).

base_rate_factor = 'sofr' documents the reference index.

Run: python -m migrations.fix_environmental_bonds_rate
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).resolve().parents[1] / "data_mart_v2.db"

# Environmental revenue bonds — tax-exempt, ~3.5% (conservative estimate)
BOND_RATE_PCT = 3.5
RATE_TYPE = "floating"
BASE_RATE_FACTOR = "sofr"

TARGETS = [
    "environmental_revenue_bonds",
    "environmental_revenue_bonds___big_river_steel",
]


def run(db_path: Path = DB_PATH) -> None:
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        updated = 0
        for iid in TARGETS:
            cur.execute(
                """
                UPDATE debt_instruments
                   SET interest_rate    = ?,
                       rate_type        = ?,
                       base_rate_factor = ?
                 WHERE instrument_id = ?
                """,
                (BOND_RATE_PCT, RATE_TYPE, BASE_RATE_FACTOR, iid),
            )
            if cur.rowcount:
                print(f"  Updated: {iid} → rate={BOND_RATE_PCT}%, type={RATE_TYPE}")
                updated += cur.rowcount
            else:
                print(f"  NOT FOUND: {iid}")
        conn.commit()
        print(f"\nDone. {updated} rows updated.")
    finally:
        conn.close()


if __name__ == "__main__":
    db = Path(sys.argv[1]) if len(sys.argv) > 1 else DB_PATH
    run(db)
