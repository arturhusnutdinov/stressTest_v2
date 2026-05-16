import sys, logging, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from engine.orchestrator import build_model
result = build_model('us_steel', run_preprocessor=False, run_macro=False,
    run_model=True, run_stress=True, run_rating=False, run_covenants=False)

mr = result.model_result
print('=== BASE CASE ===')
print(f'  {"Year":<6} {"Cash":>8} {"LTD":>8} {"IntExp":>8} {"BS_diff":>8}')
for yr in sorted(mr.years.keys()):
    s = mr.years[yr]
    bd = mr.bs_diffs.get(yr, 0)
    print(f'  {yr:<6} {s.cash/1e6:>8.0f} {(s.long_term_debt or 0)/1e6:>8.0f} {(s.interest_expense or 0)/1e6:>8.0f} {bd/1e6:>+8.2f}')

if result.stress_results:
    for scen_name, sr in result.stress_results.items():
        print(f'\n=== STRESS: {scen_name} (success={sr.success}) ===')
        print(f'  {"Year":<6} {"Cash":>8} {"IntExp":>8} {"BS_diff":>8}')
        for yr in sorted(sr.stress_values.keys()):
            sv = sr.stress_values[yr]
            bd = sv.get('bs_diff', 0)
            cash = sv.get('cash', 0)
            ie = sv.get('interest_expense', 0)
            flag = ' NEG!' if cash < 0 else ''
            print(f'  {yr:<6} {cash/1e6:>8.0f} {ie/1e6:>8.0f} {bd/1e6:>+8.2f}{flag}')
        if sr.errors:
            print(f'  ERRORS: {sr.errors}')
else:
    print('No stress result')
