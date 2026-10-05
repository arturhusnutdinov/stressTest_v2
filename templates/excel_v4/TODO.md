# Corporate Model v4 — TODO & Issues

## Требования (от Artur)
- Все исторические данные МСФО заполнены аккуратно (IS/BS/CF)
- Операционные показатели заполнены (production, sales, prices, costs)
- Данные НЕ разбросаны — каждый лист самодостаточен
- Дизайн идентичен банковской модели (цвета, шрифты, нумерация)
- Модель полностью Excel-driven (формулы, не Python engine)
- Макроанализ + эконометрика уравнений видна в модели
- Два шаблона: Русал + Норникель

## Прогресс

### Фаза 1: Каркас — DONE
- [x] 30 листов с правильным дизайном
- [x] styles.py — цветовая схема из bank model
- [x] reg.json — реестр 200+ строк
- [x] 19 builders, 223 формулы

### Фаза 2: Заполнение данными — IN PROGRESS
- [x] fill_data.py — скрипт загрузки из existing templates
- [ ] Русал: IS 2011-2025 (15 лет)
- [ ] Русал: BS 2011-2025
- [ ] Русал: CF 2011-2025
- [ ] Русал: Segments (primary_al, alumina, other)
- [ ] Русал: Operational (production_kt, sales_kt, prices)
- [ ] Русал: Debt instruments (31 шт)
- [ ] Русал: Macro factors (22 шт)
- [ ] Норникель: IS 2010-2025 (16 лет)
- [ ] Норникель: BS 2010-2025
- [ ] Норникель: CF 2010-2025
- [ ] Норникель: Segments (Ni, Cu, Pd, Pt, other)
- [ ] Норникель: Operational (38 drivers)
- [ ] Норникель: Debt instruments
- [ ] Норникель: Macro factors

### Фаза 3: Полные формулы — DONE
- [x] Control_Panel — 130+ params, 12 sections (A-L)
- [x] 17_Debt — aggregate corkscrew + interest + ND/EBITDA
- [x] 18_Lease — IFRS 16 ROU + liability corkscrew
- [x] Cross-sheet links: BS ← corkscrews (cash, AR, INV, AP, PPE, debt, DTA/DTL, RE)
- [x] PL ← engine sheets (Revenue, COGS, SGA, DA, Interest, Tax)
- [x] CF ← sources (NI, DA, WC, CapEx, Div, Interest)
- [x] 33_RevStress — reverse stress + tornado (8 vars)
- [x] 40_Scen — scenario comparison (7 scenarios × 6 KPIs)
- [x] Model_Output — 12-section dashboard (144 refs)
- [x] 00_Guide — 18-step navigation with hyperlinks
- [x] 35_Valuation — DCF (FCFF+Terminal+PV) + SOTP + 5×5 Sensitivity
- [x] 31_Score — S&P 4-factor with scoring formulas + rating lookup
- [x] 32_Covenants — actual vs threshold + headroom + breach count

### Фаза 3.5: Circular solver — TODO
- [ ] Excel Iterative Calc setup (Debt ↔ Interest ↔ Cash ↔ NI)
- [ ] Seed/relax/converge pattern (from bank model 15_Funding)
- [ ] 03_Assump — expanded assumptions (← Control_Panel refs)

### Фаза 4: Валидация — TODO
- [ ] BS Identity: A - L - E = 0 для всех лет
- [ ] CF Bridge: ΔCash = CFO + CFI + CFF
- [ ] PPE rollforward check
- [ ] Debt rollforward check
- [ ] Equity rollforward check
- [ ] Cross-check с Python engine results

## Неточности и доработки
| # | Проблема | Статус | Дата |
|---|----------|--------|------|
| 1 | Nornickel: Revenue segments (Ni/Cu/Pd) volumes/prices не заполняются — формат unified отличается | OPEN | 2026-10-05 |
| 2 | Nornickel: Debt instruments = 0 — нет в unified.xlsx, нужно из project.yaml или DB | OPEN | 2026-10-05 |
| 3 | 02_Hist year columns hardcoded (C=first year) — нужна гибкость для разной глубины истории | LOW | 2026-10-05 |
| 4 | IFRS cross-check: сверить Revenue/NI/TA с Databook | LOW | 2026-10-05 |
| 5 | CF metric mapping: cfo_total may have different names | LOW | 2026-10-05 |
| 6 | Raw_IFRS: template создан, нужно заполнить из statements/ | OPEN | 2026-10-05 |
| 7 | Macro factors: только 4 из 22 для Норникель (остальные в CSV файлах) | OPEN | 2026-10-05 |
| 8 | EBITDA 2011-2014 Rusal: вычислен как GP+SGA+DA (не из source) — проверить | FIXED | 2026-10-05 |
| 9 | 14_OtherIS: пустой лист — нужен builder | LOW | 2026-10-05 |
| 10 | Nornickel PPE_gross=0: unified не имеет gross/accum_dep, только net | INFO | 2026-10-05 |
| 11 | Circular solver (Debt↔Cash) не реализован — нужен seed/relax pattern | FIXING | 2026-10-05 |
| 15 | **CRITICAL**: Эконометрика макро-факторов: Revenue = β×Δln(Factor), COGS = β×Δln(PPI) | OPEN | 2026-10-05 |
| 16 | Revenue forecast: НЕ carry-forward а macro-driven (β from OLS на Δln series) | OPEN | 2026-10-05 |
| 17 | COGS forecast: component model с macro factors (alumina, energy, FX, CPI) | OPEN | 2026-10-05 |
| 18 | 01_Macro: regression display (β, R², α, factor forecasts) | OPEN | 2026-10-05 |
| 19 | Preprocessing: EWA with AR(1) (if R²>0.3 use AR1, else EWA) | OPEN | 2026-10-05 |
| 12 | Forecast columns в COGS/SGA — формулы ratio, но нужны input или forecast-method | FIXED | 2026-10-05 |
| 13 | **CRITICAL**: Column misalignment — Revenue/WC use C-E=hist+F-H=fc, but BS/PL/CF use C=hist+D-F=fc | FIXING | 2026-10-05 |
| 14 | BS history col C not filled for Other_CA, Lease, Reserves → carry-forward = 0 | FIXED | 2026-10-05 |
