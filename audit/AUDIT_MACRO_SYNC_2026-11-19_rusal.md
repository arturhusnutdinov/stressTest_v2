# Аудит rusal_v4.xlsx

Дата: 2026-11-19 · Стандарт: СТАНДАРТ_верификации_моделей.md

- **A1** [PASS]: архив читается, 41 xml, bad=None
- **A2** [PASS]: длинных/битых формул: 0
- **A3a** [PASS]: внешних ссылок: 0
- **A3b** [PASS]: ссылок на несуществующие листы: 0
- **A4** [INFO]: calcPr: iterate=True, count=None, delta=None, fullCalcOnLoad=True

## Группа B: кэш и сходимость

- Формул: 2299, покрыто мини-вычислителем: 1006 (43.8%)
- Расхождений кэша: 141
  - MISMATCH 03_Assump!C9: кэш=0.064, пересчёт=0.06435765168263326 :: =IFERROR('21_PL'!C$12/'21_PL'!C$7,0)
  - MISMATCH 03_Assump!D9: кэш=0.124, пересчёт=0.12365502400264856 :: =IFERROR('21_PL'!D$12/'21_PL'!D$7,0)
  - MISMATCH 03_Assump!E9: кэш=0.071, пересчёт=0.07109100729138536 :: =IFERROR('21_PL'!E$12/'21_PL'!E$7,0)
  - MISMATCH 03_Assump!C10: кэш=0.023, пересчёт=0.02309014984033407 :: =IFERROR('21_PL'!C$22/'21_PL'!C$7,0)
  - MISMATCH 03_Assump!D10: кэш=0.066, пересчёт=0.06646250620758153 :: =IFERROR('21_PL'!D$22/'21_PL'!D$7,0)
  - MISMATCH 03_Assump!E10: кэш=-0.031, пересчёт=-0.030718336483931945 :: =IFERROR('21_PL'!E$22/'21_PL'!E$7,0)
  - MISMATCH 03_Assump!C24: кэш=7.4, пересчёт=7.352417302798982 :: =IFERROR(('20_BS'!C$23+'20_BS'!C$29-'20_BS'!C$7)/'21_PL'!C$1
  - MISMATCH 03_Assump!D24: кэш=4.3, пересчёт=4.295180722891566 :: =IFERROR(('20_BS'!D$23+'20_BS'!D$29-'20_BS'!D$7)/'21_PL'!D$1
  - MISMATCH 03_Assump!E24: кэш=7.7, пересчёт=7.653371320037987 :: =IFERROR(('20_BS'!E$23+'20_BS'!E$29-'20_BS'!E$7)/'21_PL'!E$1
  - MISMATCH 03_Assump!C52: кэш=2.22, пересчёт=2.218 :: =Control_Panel!$C$46
  - MISMATCH 05_Drivers!D7: кэш=0.037, пересчёт=0.03742203742203731 :: =IFERROR('11_Segments'!D$7/'11_Segments'!C$7-1,0)
  - MISMATCH 05_Drivers!E7: кэш=-0.019, пересчёт=-0.01853707414829664 :: =IFERROR('11_Segments'!E$7/'11_Segments'!D$7-1,0)
  - MISMATCH 05_Drivers!D8: кэш=0.17, пересчёт=0.1699604743083003 :: =IFERROR('11_Segments'!D$12/'11_Segments'!C$12-1,0)
  - MISMATCH 05_Drivers!E8: кэш=0.356, пересчёт=0.3558558558558558 :: =IFERROR('11_Segments'!E$12/'11_Segments'!D$12-1,0)
  - MISMATCH 05_Drivers!G16: кэш=0.118, пересчёт=0.11764705882352944 :: =IFERROR('01_Macro'!G$41/'01_Macro'!F$41-1,0)
  - MISMATCH 05_Drivers!H16: кэш=0.042, пересчёт=0.042105263157894646 :: =IFERROR('01_Macro'!H$41/'01_Macro'!G$41-1,0)
  - MISMATCH 05_Drivers!G18: кэш=-0.014, пересчёт=-0.014285714285714235 :: =IFERROR('01_Macro'!G$42/'01_Macro'!F$42-1,0)
  - MISMATCH 05_Drivers!H18: кэш=-0.014, пересчёт=-0.01449275362318847 :: =IFERROR('01_Macro'!H$42/'01_Macro'!G$42-1,0)
  - MISMATCH 05_Drivers!F21: кэш=0.225, пересчёт=0.22549019607843146 :: =IFERROR('11_Segments'!F$8/'11_Segments'!E$8-1,0)
  - MISMATCH 05_Drivers!G21: кэш=-0.062, пересчёт=-0.06153846153846154 :: =IFERROR('11_Segments'!G$8/'11_Segments'!F$8-1,0)
- Ошибочных ячеек: 0
- Ссылок на пустые ячейки: 82
  - 05_Drivers!C29 -> 05_Drivers!D89
  - 05_Drivers!C29 -> 05_Drivers!C89
  - 05_Drivers!C30 -> 05_Drivers!D89
  - 05_Drivers!C30 -> 05_Drivers!C89
  - 05_Drivers!C56 -> 17_Debt!C56
  - 05_Drivers!D56 -> 17_Debt!D56
  - 05_Drivers!E56 -> 17_Debt!E56
  - 15_PPE!C21 -> 15_PPE!C18
  - 15_PPE!D21 -> 15_PPE!D18
  - 18_Lease!F7 -> 18_Lease!E9
  - 18_Lease!F11 -> 18_Lease!E14
  - 19_Tax!F8 -> 19_Tax!E12
  - 19_Tax!F35 -> 19_Tax!E31
  - 20_BS!F15 -> 20_BS!E15
  - 20_BS!E19 -> 20_BS!E14
  - 20_BS!E19 -> 20_BS!E15
  - 20_BS!C27 -> 20_BS!C24
  - 20_BS!E27 -> 20_BS!E24
  - 20_BS!F31 -> 20_BS!E31
  - 20_BS!C34 -> 20_BS!C31

### C C3:BS: Активы − Обяз. − Капитал [PASS]
0 по всем годам

### C C3:CF: ΔCash(BS) − (CFO+CFI+CFF) [PASS]
0 по всем годам

### C C3:PPE: Net(close) − Gross + AccDep [PASS]
0 по всем годам

### C C3:Debt: Open + Draw − Repay − Close [PASS]
0 по всем годам

### C C3:Equity: Open + NI − Div − Close [PASS]
0 по всем годам

### C C3:ST + LT = DT.close [PASS]
0 по всем годам

### C C3:DT.close = Term + RC + FX [PASS]
0 по всем годам

### C C3:Int = Term + RC + Fee + Penalty [PASS]
0 по всем годам

### C C3:Невязка кольца (Cash vs est_cash) [PASS]
0 по всем годам

### C C3:PPE: 15_PPE = 02_Hist (col E only) [PASS]
0 по всем годам
- **D2:NI<=PBT** [PASS]: OK по всем годам
- **D4:tax_rate** [PASS]: |налог|/PBT в [0;50%] (прибыльные годы), убыточные без положительного налога
- **D8:ABS_в_суммах** [WARN]: формул с ABS в суммах: 57
- **E1:разрыв_факт/прогноз** [PASS]: Выручка 2025→2026: +20.1%
- **E2:сетка_годов_ссылок** [PASS]: 0 смещений
- **E7:sanity_bounds** [PASS]: interest/rev, debt/rev, Δdebt, денормалы — в порогах
- **F5:unlabeled:Control_Panel** [WARN]: 4: WC λ нормализации (год 1) (C58); Fallback средней ставки долга (C72); Fallback доли ST (справочно) (C73); Допуск drift ST/история ± (C74)
- **F7:[РАСЧЁТ]-литерал:Control_Panel** [PASS]: 0
- **G1:регрессии_в_книге** [PASS]: SLOPE/INTERCEPT/RSQ/STEYX: {'SLOPE': 1, 'INTERCEPT': 1, 'RSQ': 1, 'STEYX': 1, 'CORREL': 0, 'LINEST': 0}
- **H1:литералы_в_формулах** [WARN]: 92; 17_Debt!E82=4.0; 17_Debt!E82=2025.0; 18_Lease!F12=0.5; 18_Lease!G12=0.5; 18_Lease!H12=0.5; 31_Score!F7=5.0; 31_Score!F7=5.0; 31_Score!G7=5.0; 31_Score!G7=5.0; 31_Score!H7=5.0
- **H2:константы_в_прогнозе** [PASS]: 0; 
- **H3:=прошлый_год** [PASS]: 0 ячеек
- **H4:цвета_кросс-ссылок** [PASS]: все кросс-ссылки аналитики зелёные
- **I3:переключатель** [PASS]: Control_Panel!C25 использует C5
- **J1:потребитель_сигнала** [PASS]: 00_Cover!C20
- **J2:статус_обложки** [PASS]: 1 статус(ов): 00_Cover!C20: ✅ ОК