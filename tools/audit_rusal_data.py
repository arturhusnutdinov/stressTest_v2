#!/usr/bin/env python3
"""
Audit RUSAL data in DB vs Engine expectations.
Read-only — no modifications. Generates a report of issues found.

Usage:
    python3 tools/audit_rusal_data.py
"""
import sqlite3
import sys
from pathlib import Path
from collections import defaultdict

DB_PATH = Path(__file__).parent.parent / "data_mart_v2.db"
COMPANY = "rusal"

# ── Engine expectations ──────────────────────────────────────────────────

# BS metrics the engine reads from history (from ModelInputLoader._build_base_year_state)
# Format: (primary_metric, fallback_metric_or_None)
BS_EXPECTED = [
    ("cash", None),
    ("restricted_cash", None),
    ("accounts_receivable", None),
    ("inventory", None),
    ("other_ca", "other_current_assets"),
    ("accounts_payable", None),
    ("ppe_gross", None),
    ("ppe_accum_dep", None),
    ("ppe_net", None),
    ("rou_asset", None),
    ("intangibles", None),
    ("goodwill", None),
    ("investments_lt", "investments_and_long_term_receivables"),
    ("dta", None),
    ("dtl", None),
    ("other_nca", "other_non_current_assets"),
    ("short_term_debt", None),
    ("long_term_debt", None),
    ("lease_liab_current", None),
    ("lease_liab_noncurrent", None),
    ("employee_benefits", None),
    ("other_ncl", "other_non_current_liabilities"),
    ("other_cl", "other_current_liabilities"),
    ("taxes_payable", "accrued_taxes"),
    ("interest_payable", "accrued_interest"),
    ("payroll_payable", "payroll_and_benefits_payable"),
    ("share_capital", None),
    ("apic", None),
    ("treasury_stock", None),
    ("retained_earnings", None),
    ("aoci", None),
    ("nci", None),
    ("total_assets", None),
    ("total_equity", None),
    ("total_liab_equity", None),
]

# IS metrics the engine reads
IS_EXPECTED = [
    ("revenue", None),
    ("cogs", None),
    ("gross_profit", None),
    ("sga", None),
    ("depreciation_owned", None),
    ("depreciation_rou", None),
    ("amortization", None),
    ("total_da", None),
    ("ebitda", None),
    ("ebit", None),
    ("interest_expense", None),
    ("ebt", None),
    ("tax_expense", None),
    ("net_income", None),
    ("earnings_from_investees", None),
    ("net_periodic_benefit_income", None),
    ("interest_income", None),
]

# CF metrics the engine reads
CF_EXPECTED = [
    ("capex", None),
    ("cfo_total", None),
    ("cfi_total", None),
    ("cff_total", None),
    ("cash_ending", None),
]

# Metrics that engine COMPUTES (should NOT be in raw history)
COMPUTED_BS = {
    "total_ca", "total_cl", "total_nca", "total_ncl",
    "total_liabilities",  # computed as total_cl + total_ncl
}

COMPUTED_IS = {
    "gross_profit", "ebitda", "ebit", "ebt", "net_income", "total_da",
}

COMPUTED_CF = {
    "net_change_cash", "net_change",
}


def get_metrics(conn, company, table, year=None):
    """Get {metric: value} for a company from a history table."""
    if year:
        sql = f"""
            SELECT h.metric, h.value, h.source
            FROM {table} h
            JOIN periods p ON h.period_id = p.period_id
            WHERE h.company_id=? AND p.year=?
        """
        rows = conn.execute(sql, (company, year)).fetchall()
    else:
        sql = f"""
            SELECT DISTINCT h.metric
            FROM {table} h
            WHERE h.company_id=?
        """
        rows = conn.execute(sql, (company,)).fetchall()
    return rows


def audit():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    issues = defaultdict(list)
    warnings = []

    # ── 1. Check all expected metrics exist ──────────────────────────
    for statement, table, expected in [
        ("IS", "history_is", IS_EXPECTED),
        ("BS", "history_bs", BS_EXPECTED),
        ("CF", "history_cf", CF_EXPECTED),
    ]:
        db_metrics = {r["metric"] for r in get_metrics(conn, COMPANY, table, year=None)}
        
        for primary, fallback in expected:
            found = primary in db_metrics
            if not found and fallback:
                found = fallback in db_metrics
            if not found:
                issues[f"missing_{statement.lower()}"].append(
                    f"{primary}" + (f" (fallback: {fallback})" if fallback else "")
                )

    # ── 2. Check for computed metrics in raw history ──────────────────
    db_bs = {r["metric"] for r in get_metrics(conn, COMPANY, "history_bs", year=None)}
    db_is = {r["metric"] for r in get_metrics(conn, COMPANY, "history_is", year=None)}
    db_cf = {r["metric"] for r in get_metrics(conn, COMPANY, "history_cf", year=None)}

    for m in COMPUTED_BS & db_bs:
        warnings.append(f"BS: '{m}' is computed by engine, should not be in history_bs")
    for m in COMPUTED_IS & db_is:
        pass  # IS computed metrics can be in history for validation
    for m in COMPUTED_CF & db_cf:
        warnings.append(f"CF: '{m}' is computed by engine, should not be in history_cf")

    # ── 3. BS Identity check per year ────────────────────────────────
    years = conn.execute(
        "SELECT DISTINCT p.year FROM history_bs h JOIN periods p ON h.period_id=p.period_id "
        "WHERE h.company_id=? ORDER BY p.year", (COMPANY,)
    ).fetchall()
    
    bs_balance_issues = []
    for (year,) in years:
        metrics = {r["metric"]: r["value"] for r in get_metrics(conn, COMPANY, "history_bs", year=year)}
        ta = abs(metrics.get("total_assets", 0) or 0)
        te = abs(metrics.get("total_equity", 0) or 0)
        # Compute L from key components (engine computes total_liabilities)
        tl_comp = (
            abs(metrics.get("short_term_debt", 0) or 0) +
            abs(metrics.get("accounts_payable", 0) or 0) +
            abs(metrics.get("taxes_payable", 0) or 0) +
            abs(metrics.get("interest_payable", 0) or 0) +
            abs(metrics.get("lease_liab_current", 0) or 0) +
            abs(metrics.get("other_cl", 0) or 0) +
            abs(metrics.get("long_term_debt", 0) or 0) +
            abs(metrics.get("dtl", 0) or 0) +
            abs(metrics.get("employee_benefits", 0) or 0) +
            abs(metrics.get("lease_liab_noncurrent", 0) or 0) +
            abs(metrics.get("other_ncl", 0) or 0)
        )
        le_comp = tl_comp + te
        diff = abs(ta - le_comp)
        # Allow up to 20% gap (unmodeled items: dividends_payable, provisions, etc.)
        threshold = max(1e6, ta * 0.20)
        if diff > threshold:
            bs_balance_issues.append(
                f"{year}: A={ta/1e9:.3f}B  L_comp={tl_comp/1e9:.3f}B  E={te/1e9:.3f}B  "
                f"gap=${diff/1e6:.1f}M ({(diff/ta*100):.1f}% of A)"
            )
    
    if bs_balance_issues:
        issues["bs_balance"] = bs_balance_issues

    # ── 4. Debt instruments classification ───────────────────────────
    debt_types = conn.execute(
        "SELECT db_type, COUNT(*) as cnt FROM debt_instruments WHERE company_id=? GROUP BY db_type",
        (COMPANY,)
    ).fetchall()
    
    for row in debt_types:
        if row["db_type"] == "other":
            issues["debt_classification"].append(
                f"{row['cnt']} instruments have db_type='other' (need bond_fixed/bond_float/term_bullet/revolving)"
            )

    # ── 5. Debt instrument currency vs balance magnitude ─────────────
    large_rub = conn.execute(
        "SELECT instrument_id, currency, opening_balance FROM debt_instruments "
        "WHERE company_id=? AND currency='RUB' AND opening_balance > 1e12 "
        "ORDER BY opening_balance DESC LIMIT 5",
        (COMPANY,)
    ).fetchall()
    
    if large_rub:
        issues["debt_currency"].append(
            f"RUB instruments with balance > 1e12 (appear unconverted):"
        )
        for r in large_rub:
            issues["debt_currency"].append(
                f"  {r['instrument_id']}: {r['opening_balance']/1e12:.1f}T RUB"
            )

    # ── 6. Duplicate metrics ─────────────────────────────────────────
    for table, label in [("history_bs", "BS"), ("history_is", "IS"), ("history_cf", "CF")]:
        dupes = conn.execute(f"""
            SELECT p.year, h.metric, COUNT(*) as cnt
            FROM {table} h JOIN periods p ON h.period_id=p.period_id
            WHERE h.company_id=?
            GROUP BY p.year, h.metric HAVING cnt > 1
        """, (COMPANY,)).fetchall()
        for d in dupes:
            warnings.append(f"{label} duplicate: {d['metric']} in {d['year']} ({d['cnt']} rows)")

    # ── 7. Missing schedule data ─────────────────────────────────────
    for table in ["lease_schedule", "equity_schedule", "tax_schedule"]:
        cnt = conn.execute(
            f"SELECT COUNT(*) FROM {table} WHERE company_id=?", (COMPANY,)
        ).fetchone()[0]
        if cnt == 0:
            issues["missing_schedules"].append(f"{table}: 0 rows (required for corkscrews)")

    # ── 8. Macro factors check ───────────────────────────────────────
    mf_cnt = conn.execute(
        "SELECT COUNT(*) FROM macro_factors WHERE company_id=? OR company_id=''", (COMPANY,)
    ).fetchone()[0]
    if mf_cnt == 0:
        issues["macro"].append("macro_factors: 0 rows (needed for COGS/SGA beta indexing)")

    conn.close()

    # ── Print report ─────────────────────────────────────────────────
    print("=" * 60)
    print("RUSAL DATA AUDIT REPORT")
    print("=" * 60)
    
    total_issues = sum(len(v) for v in issues.values())
    
    for section, items in sorted(issues.items()):
        print(f"\n🔴 {section.upper()} ({len(items)} issues):")
        for item in items[:10]:
            print(f"   • {item}")
        if len(items) > 10:
            print(f"   ... +{len(items)-10} more")

    if warnings:
        print(f"\n🟡 WARNINGS ({len(warnings)}):")
        for w in warnings[:15]:
            print(f"   • {w}")
        if len(warnings) > 15:
            print(f"   ... +{len(warnings)-15} more")

    print(f"\n{'='*60}")
    print(f"Total issues: {total_issues}  |  Warnings: {len(warnings)}")
    
    return total_issues


if __name__ == "__main__":
    sys.exit(audit())
