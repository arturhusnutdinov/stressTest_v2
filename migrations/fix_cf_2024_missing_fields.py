"""
Fix CF 2024 data issues:
1. capex = 0 (stored as -0) → compute from cfi_total residual
2. Add canonical aliases for renamed WC metrics (wc_* → changes_in_*)
3. Add net_income to CF 2024 from IS history
4. Add deferred_income_taxes alias for tax_deferred_adjustment
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.database.repository import Repository

COMPANY = "us_steel"
YEAR = 2024
SOURCE = "fix_cf_2024_missing_fields"


def main():
    with Repository() as repo:
        cf = repo.get_history_year(COMPANY, "CF", YEAR)
        is_ = repo.get_history_year(COMPANY, "IS", YEAR)

        fixes: dict = {}

        # ── 1. capex ─────────────────────────────────────────────────────────
        # capex is stored as 0 (bug). Compute from cfi_total residual.
        cfi_total = cf.get("cfi_total") or 0.0
        disposal  = cf.get("disposal_of_assets") or 0.0
        inv_net   = cf.get("investments_net") or 0.0
        emp_inv   = cf.get("active_employee_benefit_investments") or 0.0
        # cfi_total = capex + disposal + inv_net + emp_inv + other
        # capex is the largest component — assume other = 0
        capex_computed = cfi_total - disposal - inv_net - emp_inv
        print(f"capex computed: {cfi_total:.0f} - {disposal:.0f} - {inv_net:.0f} - {emp_inv:.0f} = {capex_computed:.0f}M raw")
        # Store in millions (DB uses absolute values)
        fixes["capex"] = capex_computed
        print(f"  → capex = {capex_computed/1e6:.0f}M")

        # ── 2. WC canonical aliases ───────────────────────────────────────────
        aliases = {
            "wc_accounts_receivable_change":        "changes_in_current_receivables",
            "wc_inventory_change":                  "changes_in_inventories",
            "wc_accounts_payable_change":           "changes_in_current_accounts_payable_and_accrued_expenses",
            "wc_income_taxes_receivable_payable_change": "changes_in_income_taxes_receivable_payable",
            "wc_all_other_net":                     "changes_in_all_other_net",
            "tax_deferred_adjustment":              "deferred_income_taxes",
        }
        for src_key, dst_key in aliases.items():
            val = cf.get(src_key)
            if val is not None and dst_key not in cf:
                fixes[dst_key] = val
                print(f"  alias {src_key} → {dst_key} = {val/1e6:.0f}M")

        # ── 3. net_income from IS ─────────────────────────────────────────────
        if not cf.get("net_income"):
            ni = is_.get("net_income")
            if ni is not None:
                fixes["net_income"] = ni
                print(f"  net_income from IS = {ni/1e6:.0f}M")

        # ── 4. Write to DB ────────────────────────────────────────────────────
        if fixes:
            n = repo.upsert_history(COMPANY, "CF", YEAR, fixes, source=SOURCE)
            print(f"\nUpserted {n} CF metrics for {COMPANY} {YEAR}")
        else:
            print("Nothing to fix.")

        # Verify
        cf2 = repo.get_history_year(COMPANY, "CF", YEAR)
        print(f"\nVerify capex 2024 = {(cf2.get('capex') or 0)/1e6:.0f}M")
        print(f"Verify cfi_total 2024 = {(cf2.get('cfi_total') or 0)/1e6:.0f}M")
        print(f"Verify changes_in_current_receivables = {(cf2.get('changes_in_current_receivables') or 0)/1e6:.0f}M")
        print(f"Verify deferred_income_taxes = {(cf2.get('deferred_income_taxes') or 0)/1e6:.0f}M")


if __name__ == "__main__":
    main()
