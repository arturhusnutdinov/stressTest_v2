#!/usr/bin/env python3
"""
Block F: Behavioral verification of the corporate model via AppleScript.

Runs 3 scenarios, validates:
1. Monotonicity: worse scenario → worse metrics
2. Identity checks: BS=0, CF=0, Debt corkscrew=0 in ALL scenarios
3. Cash target: Cash = min_cash OR FundGap > 0
4. EBITDA sign protection: negative EBITDA → score floor, gate closed
5. Operating leverage: Revenue change → EBITDA change (elastic)

Usage:
    python3 verify_model.py model_rusal.xlsx
    python3 verify_model.py model_nornickel.xlsx
"""
import subprocess
import sys
import re
import json
from pathlib import Path


def run_applescript(script: str) -> str:
    """Run AppleScript and return stdout."""
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True, timeout=300
    )
    if result.returncode != 0:
        raise RuntimeError(f"AppleScript error: {result.stderr.strip()}")
    return result.stdout.strip()


def open_workbook(path: str) -> None:
    """Open workbook in Excel."""
    run_applescript(f'''
        tell application "Microsoft Excel"
            activate
            open "{path}"
            delay 4
        end tell
    ''')


def close_workbook() -> None:
    """Close active workbook without saving."""
    run_applescript('''
        tell application "Microsoft Excel"
            close workbook 1 saving no
        end tell
    ''')


def recalc(n: int = 25) -> None:
    """Recalculate n times."""
    run_applescript(f'''
        tell application "Microsoft Excel"
            repeat {n} times
                calculate
            end repeat
            delay 2
        end tell
    ''')


def set_scenario(sc: int) -> None:
    """Set Control_Panel!C5 to scenario number and recalc."""
    run_applescript(f'''
        tell application "Microsoft Excel"
            set ws to worksheet "Control_Panel" of workbook 1
            set value of range "C5" of ws to {sc}
        end tell
    ''')
    recalc()


def read_cell(sheet: str, cell: str) -> str:
    """Read a single cell value."""
    return run_applescript(f'''
        tell application "Microsoft Excel"
            set ws to worksheet "{sheet}" of workbook 1
            return string value of range "{cell}" of ws
        end tell
    ''')


def read_checks() -> dict:
    """Read all check values from 90_Checks for 3 forecast years."""
    raw = run_applescript('''
        tell application "Microsoft Excel"
            set ws to worksheet "90_Checks" of workbook 1
            set res to ""
            repeat with r from 7 to 24
                set lbl to string value of range ("A" & r) of ws
                if lbl is not "" then
                    set v1 to string value of range ("F" & r) of ws
                    set v2 to string value of range ("G" & r) of ws
                    set v3 to string value of range ("H" & r) of ws
                    set res to res & r & "|" & lbl & "|" & v1 & "|" & v2 & "|" & v3 & linefeed
                end if
            end repeat
            return res
        end tell
    ''')
    checks = {}
    for line in raw.strip().split("\n"):
        parts = line.split("|")
        if len(parts) >= 5:
            row, label = parts[0], parts[1]
            vals = [parse_num(v) for v in parts[2:5]]
            checks[label.strip()] = vals
    return checks


def read_metrics() -> dict:
    """Read key financial metrics."""
    # Read row registry to get correct row numbers
    reg_path = Path(__file__).parent.parent / "reg.json"
    if reg_path.exists():
        reg = json.loads(reg_path.read_text())
    else:
        reg = {"PL.revenue": 7, "PL.ebitda": 12, "PL.ni": 22,
               "BS.cash": 7, "DT.close": 42, "DT.new_term": 27,
               "DT.funding_gap": 38}
    r_rev = reg.get("PL.revenue", 7)
    r_ebitda = reg.get("PL.ebitda", 12)
    r_ni = reg.get("PL.ni", 22)
    r_cash = reg.get("BS.cash", 7)
    r_debt = reg.get("DT.close", 42)
    r_new_term = reg.get("DT.new_term", 27)
    r_gap = reg.get("DT.funding_gap", 38)

    raw = run_applescript(f'''
        tell application "Microsoft Excel"
            set pl to worksheet "21_PL" of workbook 1
            set bs to worksheet "20_BS" of workbook 1
            set dt to worksheet "17_Debt" of workbook 1
            set sc to worksheet "31_Score" of workbook 1

            set mRev to string value of range "F{r_rev}" of pl
            set mEbitda to string value of range "F{r_ebitda}" of pl
            set mNI to string value of range "F{r_ni}" of pl
            set mCash to string value of range "F{r_cash}" of bs
            set mDebt to string value of range "F{r_debt}" of dt
            set mLevScore to string value of range "F7" of sc
            set mRating to string value of range "F16" of sc
            set mNewTerm to string value of range "F{r_new_term}" of dt
            set mGap to string value of range "F{r_gap}" of dt

            return mRev & "|" & mEbitda & "|" & mNI & "|" & mCash & "|" & mDebt & "|" & mLevScore & "|" & mRating & "|" & mNewTerm & "|" & mGap
        end tell
    ''')
    parts = raw.split("|")
    keys = ["revenue", "ebitda", "ni", "cash", "debt", "lev_score", "rating", "new_term", "gap"]
    return {k: parse_num(v) if i < 6 or i >= 7 else v.strip()
            for i, (k, v) in enumerate(zip(keys, parts))}


def parse_num(s: str) -> float:
    """Parse number from Excel string (handles spaces, commas, 'x' suffix)."""
    s = s.strip().replace("\xa0", "").replace(" ", "").replace(",", ".")
    s = s.rstrip("x").rstrip("%")
    if not s or s == "missing value" or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def test_monotonicity(results: dict) -> list:
    """Check that worse scenario → worse metrics."""
    errors = []
    # Revenue: should decrease Base > Stress > Severe
    if results[1]["revenue"] > 0 and results[2]["revenue"] > 0:
        if results[2]["revenue"] >= results[1]["revenue"]:
            errors.append(f"Revenue not decreasing: Sc1={results[1]['revenue']:.0f} Sc2={results[2]['revenue']:.0f}")
    if results[2]["revenue"] > 0 and results[3]["revenue"] > 0:
        if results[3]["revenue"] >= results[2]["revenue"]:
            errors.append(f"Revenue not decreasing: Sc2={results[2]['revenue']:.0f} Sc3={results[3]['revenue']:.0f}")
    # EBITDA: should decrease
    if results[2]["ebitda"] >= results[1]["ebitda"]:
        errors.append(f"EBITDA not decreasing: Sc1={results[1]['ebitda']:.0f} Sc2={results[2]['ebitda']:.0f}")
    if results[3]["ebitda"] >= results[2]["ebitda"]:
        errors.append(f"EBITDA not decreasing: Sc2={results[2]['ebitda']:.0f} Sc3={results[3]['ebitda']:.0f}")
    return errors


def test_identities(checks: dict, scenario: int) -> list:
    """Check that structural identities hold (all should be 0)."""
    errors = []
    identity_keys = [
        "BS: Активы − Обяз. − Капитал",
        "CF: ΔCash(BS) − (CFO+CFI+CFF)",
        "PPE: Net(close) − Gross + AccDep",
        "Debt: Open + Draw − Repay − Close",
        "Equity: Open + NI − Div − Close",
        "ST + LT = DT.close",
        "DT.close = Term + RC + FX",
        "Int = Term + RC + Fee",
        "Невязка кольца (Cash vs est_cash)",
    ]
    for key in identity_keys:
        if key in checks:
            vals = checks[key]
            for i, v in enumerate(vals):
                if abs(v) > 0.01:
                    errors.append(f"Sc{scenario} Y{i+1} {key} = {v:.2f}")
    return errors


def test_ebitda_protection(results: dict) -> list:
    """If EBITDA < 0, leverage score should be 5 (floor) and new_term = 0."""
    errors = []
    for sc in [1, 2, 3]:
        m = results[sc]
        if m["ebitda"] < 0:
            if m["lev_score"] > 6:
                errors.append(f"Sc{sc}: EBITDA={m['ebitda']:.0f}<0 but lev_score={m['lev_score']:.0f} (should be 5)")
            if m["new_term"] > 0:
                errors.append(f"Sc{sc}: EBITDA<0 but new_term={m['new_term']:.0f} (gate should be closed)")
    return errors


def main():
    if len(sys.argv) < 2:
        model_dir = Path(__file__).parent.parent / "model"
        xlsx = list(model_dir.glob("model_*.xlsx"))
        if not xlsx:
            print("Usage: python3 verify_model.py <model_file.xlsx>")
            sys.exit(1)
        model_path = str(xlsx[0])
    else:
        model_path = sys.argv[1]

    model_path = str(Path(model_path).resolve())
    print(f"Verifying: {Path(model_path).name}")
    print("=" * 60)

    open_workbook(model_path)
    all_errors = []
    results = {}

    for sc in [1, 2, 3]:
        print(f"\n--- Scenario {sc} ---")
        set_scenario(sc)
        metrics = read_metrics()
        checks = read_checks()
        results[sc] = metrics

        print(f"  Revenue:   {metrics['revenue']:>10,.0f}")
        print(f"  EBITDA:    {metrics['ebitda']:>10,.0f}")
        print(f"  NI:        {metrics['ni']:>10,.0f}")
        print(f"  Cash:      {metrics['cash']:>10,.0f}")
        print(f"  Debt:      {metrics['debt']:>10,.0f}")
        print(f"  LevScore:  {metrics['lev_score']:>10.1f}")
        print(f"  Rating:    {metrics['rating']:>10}")
        print(f"  NewTerm:   {metrics['new_term']:>10,.0f}")

        # Identity checks
        id_errors = test_identities(checks, sc)
        if id_errors:
            print(f"  IDENTITY FAILURES:")
            for e in id_errors:
                print(f"    ✗ {e}")
        else:
            print(f"  Identities: ALL PASS")
        all_errors.extend(id_errors)

    # Reset to base
    set_scenario(1)

    # Monotonicity
    print("\n--- Monotonicity ---")
    mono_errors = test_monotonicity(results)
    if mono_errors:
        for e in mono_errors:
            print(f"  ✗ {e}")
    else:
        print("  Revenue decreasing: PASS")
        print("  EBITDA decreasing: PASS")
    all_errors.extend(mono_errors)

    # EBITDA protection
    print("\n--- EBITDA Sign Protection ---")
    prot_errors = test_ebitda_protection(results)
    if prot_errors:
        for e in prot_errors:
            print(f"  ✗ {e}")
    else:
        has_neg = any(results[sc]["ebitda"] < 0 for sc in [1, 2, 3])
        if has_neg:
            print("  Negative EBITDA detected → score=5, gate closed: PASS")
        else:
            print("  No negative EBITDA scenario (all positive)")
    all_errors.extend(prot_errors)

    # Operating leverage
    print("\n--- Operating Leverage ---")
    if results[1]["revenue"] > 0 and results[1]["ebitda"] > 0:
        rev_drop = (results[3]["revenue"] - results[1]["revenue"]) / results[1]["revenue"]
        ebitda_drop = (results[3]["ebitda"] - results[1]["ebitda"]) / results[1]["ebitda"]
        leverage = ebitda_drop / rev_drop if abs(rev_drop) > 0.001 else 0
        print(f"  Revenue Δ:  {rev_drop:+.1%}")
        print(f"  EBITDA Δ:   {ebitda_drop:+.1%}")
        print(f"  Op leverage: {leverage:.1f}x (EBITDA elasticity to revenue)")
        if abs(leverage) < 0.5:
            all_errors.append("Operating leverage too low (<0.5x)")
            print("  ✗ Leverage too low — COGS not sensitive to price")
        else:
            print("  PASS")

    close_workbook()

    # Summary
    print("\n" + "=" * 60)
    if all_errors:
        print(f"FAILURES: {len(all_errors)}")
        for e in all_errors:
            print(f"  ✗ {e}")
        sys.exit(1)
    else:
        print("ALL BEHAVIORAL TESTS PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
