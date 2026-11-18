# Backtest rusal: прогноз 2024–2026 от истории ≤ 2023

Дата: 2026-11-18 · Сценарий: `backtest` (temp БД) · sanity: fail

## Статус: FAIL (прогон прерван)
- ✗ 2024: 2024: sanity FAIL — total_assets=1.94e+14 (|x|>1e+12 или non-finite); interest/revenue=66818.21 > 0.50 (int=774234687418571, rev=11587181302); debt/revenue=895664.8 > 10.0 (debt=10378230936428538)

Sanity bounds отработали как fail-fast гейты adequacy — см. AUDIT_ADEQUACY §3.3 (на усечённых данных без bounds раньше получали STD=5.6e15 при BS diff=0).