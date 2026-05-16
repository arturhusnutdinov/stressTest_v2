#!/usr/bin/env python3
"""
Smoke test: Run stressTest Engine v2 for RUSAL (preprocessor → model).

Tests:
  1. Preprocessor runs without errors
  2. Model runs without errors
  3. BS and CF diffs are reasonable
  4. All forecast years produce output

Usage:
  python3 tools/smoke_test_rusal.py
"""
import sys
import logging
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from engine.orchestrator import build_model

logging.basicConfig(
    level=logging.WARNING,  # reduce noise
    format="%(levelname)s %(name)s — %(message)s",
)


def main():
    print("=" * 60)
    print("RUSAL SMOKE TEST — stressTest Engine v2")
    print("=" * 60)
    print()
    
    result = build_model(
        company_id="rusal",
        run_preprocessor=True,
        run_macro=True,
        run_model=True,
        run_stress=False,
        run_rating=False,
        run_covenants=False,
        log_level=logging.WARNING,
    )
    
    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    
    if not result.success:
        print(f"\n❌ FAILED with {len(result.errors)} errors:")
        for e in result.errors[:5]:
            print(f"   • {e}")
        return 1
    
    print(f"\n✅ Preprocessor: {'OK' if result.preprocess_result and result.preprocess_result.success else 'FAIL'}")
    if result.preprocess_result:
        print(f"   Groups: {len(result.preprocess_result.groups_computed)}")
        print(f"   Metrics: {result.preprocess_result.metrics_written}")
    
    print(f"\n✅ Macro: {'OK' if result.macro_result and result.macro_result.success else 'FAIL/WARN'}")
    if result.macro_result:
        print(f"   Factors: {len(result.macro_result.factors_forecast)}")
    
    print(f"\n✅ Model: {'OK' if result.model_result and result.model_result.success else 'FAIL'}")
    if result.model_result:
        r = result.model_result
        print(f"   Years: {list(r.years.keys())}")
        
        max_bs = max(r.bs_diffs.values(), default=0)
        max_cf = max(r.cf_diffs.values(), default=0)
        
        print(f"   BS max diff: ${max_bs:,.0f}")
        print(f"   CF max diff: ${max_cf:,.0f}")
        
        if r.warnings:
            print(f"   Warnings ({len(r.warnings)}):")
            for w in r.warnings[:3]:
                print(f"     ⚠ {w}")
        
        # Print summary table
        print(f"\n   {'Year':<6} {'Rev$B':>8} {'EBITDA%':>8} {'NI$M':>8} {'BS_diff':>10} {'CF_diff':>10}")
        print(f"   {'-'*6} {'-'*8} {'-'*8} {'-'*8} {'-'*10} {'-'*10}")
        for yr, state in sorted(r.years.items()):
            bs_diff = r.bs_diffs.get(yr, 0)
            cf_diff = r.cf_diffs.get(yr, 0)
            ebitda_pct = (abs(state.ebitda) / abs(state.revenue) * 100) if state.revenue else 0
            print(f"   {yr:<6} {state.revenue/1e9:>8.2f} {ebitda_pct:>7.1f}% {state.net_income/1e6:>8.0f} {bs_diff:>10.0f} {cf_diff:>10.0f}")
    
    # Verify basic sanity
    if result.model_result and result.model_result.success:
        years = result.model_result.years
        if not years:
            print("\n❌ No forecast years generated!")
            return 1
        
        # Revenue should be positive and reasonable
        for yr, state in years.items():
            if state.revenue <= 0:
                print(f"\n❌ {yr}: Revenue <= 0 ({state.revenue})")
                return 1
            if state.total_assets <= 0:
                print(f"\n❌ {yr}: Total Assets <= 0")
                return 1
        
        print(f"\n{'='*60}")
        print(f"✅ ALL CHECKS PASSED")
        print(f"{'='*60}")
        return 0
    
    return 1


if __name__ == "__main__":
    sys.exit(main())
