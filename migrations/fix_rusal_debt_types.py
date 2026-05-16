#!/usr/bin/env python3
"""
Migration: Classify RUSAL debt instruments with correct db_type.

Rules:
  - bond_fixed:   bonds with fixed rate (RUB %, CNY %, bond_bo-*)
  - bond_float:   bonds with floating rate (KeyRate + spread, Euribor)
  - term_bullet:  bank loans (secured/unsecured, fixed or floating)
  - revolving:    RC facilities (none identified for RUSAL)
  - other:        related party loans, accrued interest (non-standard)

Also identifies non-debt entries that should be removed from debt_instruments.

Usage:
  python3 migrations/fix_rusal_debt_types.py --dry-run
  python3 migrations/fix_rusal_debt_types.py
"""
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / "data_mart_v2.db"
COMPANY = "rusal"


def classify(instrument_id: str, instrument_name: str, rate_type: str, currency: str) -> str:
    """Determine db_type from instrument characteristics.
    
    Engine DebtOptimizer maps:
      bond_fixed / bond_float → InstrumentKind.BOND_BULLET
      term_bullet              → InstrumentKind.BULLET
      term_amort               → InstrumentKind.TERM_AMORT
      revolving                → InstrumentKind.RC
    """
    iid = instrument_id.lower()
    iname = (instrument_name or "").lower()
    rt = (rate_type or "").lower()
    
    # Accrued interest is a BS accrual, NOT a debt instrument
    if "accrued" in iid or "accrued" in iname:
        return "REMOVE"
    
    # Related party / inter-company loans → other
    if "related_parties" in iid or "related party" in iname:
        return "other"
    
    # Bank loans (secured/unsecured) from PDF parser
    if "bank_loan" in iid:
        return "term_bullet"
    
    # Bonds: identified by 'bond_' prefix or by CNY/RUB % naming  
    is_bond = (
        iid.startswith("bond_") or 
        iid.startswith("cny_") or 
        iid.startswith("rub_")
    )
    
    if is_bond:
        if rt == "fixed":
            return "bond_fixed"
        if rt in ("floating", "variable"):
            return "bond_float"
    
    # EUR floating-rate instruments
    if "euribor" in iid or "euribor" in iname:
        return "bond_float"
    
    # KeyRate-based floating → bond_float  
    if "keyrate" in iid or "keyrate" in iname:
        return "bond_float"
    
    # Default by rate type
    if rt == "fixed":
        return "bond_fixed"
    if rt in ("floating", "variable"):
        return "bond_float"
    
    return "other"


def main(dry_run=False):
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    
    rows = conn.execute(
        "SELECT instrument_id, instrument_name, db_type, currency, rate_type, interest_rate "
        "FROM debt_instruments WHERE company_id=? ORDER BY currency, rate_type, instrument_id",
        (COMPANY,)
    ).fetchall()
    
    print(f"Company: {COMPANY}")
    print(f"Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print(f"Instruments: {len(rows)}")
    print()
    
    changes = []
    to_remove = []
    stats = {"bond_fixed": 0, "bond_float": 0, "term_bullet": 0, "revolving": 0, "other": 0, "REMOVE": 0}
    
    for row in rows:
        new_type = classify(
            row["instrument_id"], row["instrument_name"],
            row["rate_type"], row["currency"]
        )
        old_type = row["db_type"]
        
        stats[new_type] = stats.get(new_type, 0) + 1
        
        if new_type == "REMOVE":
            to_remove.append(row["instrument_id"])
            print(f"  🔴 REMOVE: {row['instrument_id']} — {row['instrument_name']} (not a debt instrument)")
        elif new_type != old_type:
            changes.append((row["instrument_id"], old_type, new_type))
            print(f"  🟡 {row['instrument_id']:45s} {old_type:10s} → {new_type:15s} ({row['currency']} {row['rate_type']})")
        else:
            print(f"     {row['instrument_id']:45s} {old_type:10s} ✓ (already correct)")
    
    print(f"\n{'='*60}")
    print(f"Summary:")
    for k, v in sorted(stats.items()):
        if v > 0:
            print(f"  {k:20s}: {v}")
    print(f"  Changes: {len(changes)}")
    print(f"  To remove: {len(to_remove)}")
    
    if dry_run:
        print("\nDRY RUN — no changes made.")
        conn.close()
        return
    
    if changes:
        for inst_id, old, new in changes:
            conn.execute(
                "UPDATE debt_instruments SET db_type=? WHERE company_id=? AND instrument_id=?",
                (new, COMPANY, inst_id)
            )
        print(f"\nUpdated {len(changes)} instruments.")
    
    if to_remove:
        for inst_id in to_remove:
            conn.execute(
                "DELETE FROM debt_instruments WHERE company_id=? AND instrument_id=?",
                (COMPANY, inst_id)
            )
        print(f"Removed {len(to_remove)} non-debt entries.")
    
    conn.commit()
    print("COMMITTED.")
    conn.close()


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    main(dry_run=dry)
