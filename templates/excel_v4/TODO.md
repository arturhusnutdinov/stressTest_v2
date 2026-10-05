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

### Фаза 3: Полные формулы — TODO
- [ ] Control_Panel — 130+ параметров
- [ ] 03_Assump — expanded (← Control_Panel)
- [ ] 17_Debt — instrument-level с circular solver
- [ ] 18_Lease — IFRS 16 ROU corkscrew
- [ ] Cross-sheet links: BS ← corkscrews
- [ ] Circular solver (Excel Iterative Calc)
- [ ] 33_RevStress — reverse stress + tornado
- [ ] 40_Scen — scenario comparison
- [ ] Model_Output — 12-section dashboard
- [ ] 00_Guide — navigation with hyperlinks

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
| 1 | Nornickel: Revenue segments (Ni/Cu/Pd) volumes/prices не заполняются из unified.xlsx — формат отличается | OPEN | 2026-10-05 |
| 2 | Nornickel: Debt instruments = 0 — нет в unified.xlsx, нужно из project.yaml или DB | OPEN | 2026-10-05 |
| 3 | 02_Hist year columns hardcoded (C=first year) — нужна гибкость для разной глубины истории | OPEN | 2026-10-05 |
| 4 | IFRS cross-check: сверить Revenue/NI/TA с опубликованной отчётностью (Databook) | OPEN | 2026-10-05 |
| 5 | CF metric mapping: cfo_total/cfi_total may have different names in sources | OPEN | 2026-10-05 |
| 6 | Заполнить IFRS Raw_IFRS лист (167+ ключей) из statements/ | OPEN | 2026-10-05 |
| 7 | Macro factors: только 4 из 22 для Норникель (остальные в отдельных CSV) | OPEN | 2026-10-05 |
