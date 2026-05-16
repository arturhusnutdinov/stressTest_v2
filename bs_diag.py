import sys, logging, warnings
sys.path.insert(0, '.')
warnings.filterwarnings('ignore')
logging.disable(logging.CRITICAL)

from engine.orchestrator import build_model

result = build_model('us_steel',
    run_preprocessor=False, run_macro=False,
    run_model=True, run_stress=False,
    run_rating=False, run_covenants=False)

mr = result.model_result
s  = mr.years[2025]
from engine.database.repository import Repository
from engine.model.loader import ModelInputLoader
with Repository() as _repo:
    _loader = ModelInputLoader(company_id='us_steel', repo=_repo)
    _hist, _cfg = _loader.load()
h = _hist.base_year_state

print('=== BS DIFF ДИАГНОСТИКА 2025 ===')
print(f'total_assets = {s.total_assets/1e6:.0f}M')
print(f'total_liab   = {s.total_liabilities/1e6:.0f}M')
print(f'total_equity = {s.total_equity/1e6:.0f}M')
print(f'BS diff      = {(s.total_assets - s.total_liabilities - s.total_equity)/1e6:.0f}M')
print()

print('АКТИВЫ 2025 vs 2024:')
for name in ['cash','restricted_cash','accounts_receivable','inventory','other_ca',
             'ppe_net','rou_asset','intangibles','goodwill','dta','investments_lt','other_nca']:
    sv = getattr(s, name, 0) or 0
    hv = getattr(h, name, 0) or 0
    print(f'  {name:<22} {sv/1e6:>8.0f}  base={hv/1e6:>8.0f}  d={( sv-hv)/1e6:>+8.0f}')

print()
print('LIABILITIES 2025 vs 2024:')
for name in ['short_term_debt','accounts_payable','taxes_payable','interest_payable',
             'accrued_liabilities','lease_liab_current','other_cl',
             'long_term_debt','dtl','employee_benefits','lease_liab_noncurrent','other_ncl']:
    sv = abs(getattr(s, name, 0) or 0)
    hv = abs(getattr(h, name, 0) or 0)
    print(f'  {name:<22} {sv/1e6:>8.0f}  base={hv/1e6:>8.0f}  d={( sv-hv)/1e6:>+8.0f}')

print()
print('EQUITY:')
for name in ['share_capital','apic','retained_earnings','treasury_stock','aoci','nci']:
    sv = getattr(s, name, 0) or 0
    hv = getattr(h, name, 0) or 0
    print(f'  {name:<22} {sv/1e6:>8.0f}  base={hv/1e6:>8.0f}  d={( sv-hv)/1e6:>+8.0f}')

re_check = (h.retained_earnings or 0) + (s.net_income or 0) + (getattr(s,'cff_dividends',0) or 0)
print(f'\nRE bridge: base_RE={h.retained_earnings/1e6:.0f} + NI={s.net_income/1e6:.0f} = {re_check/1e6:.0f}  actual={s.retained_earnings/1e6:.0f}')
print(f'treasury_sign_check: state={s.treasury_stock/1e6:.0f}')

# Check total_equity formula manually
manual_eq = (
    (s.share_capital or 0) + (s.apic or 0) + (s.retained_earnings or 0)
    - abs(s.treasury_stock or 0) + (s.aoci or 0) + (s.nci or 0)
)
print(f'\nEquity formula check: manual={manual_eq/1e6:.0f}  state.total_equity={s.total_equity/1e6:.0f}')
print(f'  treasury_stock raw = {s.treasury_stock/1e6:.0f}  abs={abs(s.treasury_stock or 0)/1e6:.0f}')
print(f'  -abs(treasury) = {-abs(s.treasury_stock or 0)/1e6:.0f}')
