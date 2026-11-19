# Аудит nornickel_v4.xlsx

Дата: 2026-11-19 · Стандарт: СТАНДАРТ_верификации_моделей.md

- **A1** [PASS]: архив читается, 41 xml, bad=None
- **A2** [PASS]: длинных/битых формул: 0
- **A3a** [PASS]: внешних ссылок: 0
- **A3b** [PASS]: ссылок на несуществующие листы: 0
- **A4** [INFO]: calcPr: iterate=True, count=None, delta=None, fullCalcOnLoad=True

## Группа B: кэш и сходимость

- Формул: 2102, покрыто мини-вычислителем: 958 (45.6%)
- Расхождений кэша: 125
  - MISMATCH 03_Assump!C9: кэш=0.478, пересчёт=0.47775695745714486 :: =IFERROR('21_PL'!C$12/'21_PL'!C$7,0)
  - MISMATCH 03_Assump!D9: кэш=0.415, пересчёт=0.4145193458316713 :: =IFERROR('21_PL'!D$12/'21_PL'!D$7,0)
  - MISMATCH 03_Assump!E9: кэш=0.412, пересчёт=0.41182881639177504 :: =IFERROR('21_PL'!E$12/'21_PL'!E$7,0)
  - MISMATCH 03_Assump!C10: кэш=0.199, пересчёт=0.19918106738843777 :: =IFERROR('21_PL'!C$22/'21_PL'!C$7,0)
  - MISMATCH 03_Assump!D10: кэш=0.145, пересчёт=0.14479457518946948 :: =IFERROR('21_PL'!D$22/'21_PL'!D$7,0)
  - MISMATCH 03_Assump!E10: кэш=0.179, пересчёт=0.1794666860422873 :: =IFERROR('21_PL'!E$22/'21_PL'!E$7,0)
  - MISMATCH 03_Assump!C24: кэш=1.1, пересчёт=1.1000871586287042 :: =IFERROR(('20_BS'!C$23+'20_BS'!C$29-'20_BS'!C$7)/'21_PL'!C$1
  - MISMATCH 03_Assump!D24: кэш=1.6, пересчёт=1.5635103926096998 :: =IFERROR(('20_BS'!D$23+'20_BS'!D$29-'20_BS'!D$7)/'21_PL'!D$1
  - MISMATCH 03_Assump!E24: кэш=1.5, пересчёт=1.5155257586450246 :: =IFERROR(('20_BS'!E$23+'20_BS'!E$29-'20_BS'!E$7)/'21_PL'!E$1
  - MISMATCH 03_Assump!C46: кэш=2.14, пересчёт=2.135 :: =Control_Panel!$C$40
  - MISMATCH 05_Drivers!D7: кэш=-0.019, пересчёт=-0.019138755980861233 :: =IFERROR('11_Segments'!D$7/'11_Segments'!C$7-1,0)
  - MISMATCH 05_Drivers!E7: кэш=-0.034, пересчёт=-0.034146341463414664 :: =IFERROR('11_Segments'!E$7/'11_Segments'!D$7-1,0)
  - MISMATCH 05_Drivers!D8: кэш=0.016, пересчёт=0.016470588235294015 :: =IFERROR('11_Segments'!D$12/'11_Segments'!C$12-1,0)
  - MISMATCH 05_Drivers!E8: кэш=-0.016, пересчёт=-0.01620370370370372 :: =IFERROR('11_Segments'!E$12/'11_Segments'!D$12-1,0)
  - MISMATCH 05_Drivers!D9: кэш=0.026, пересчёт=0.026002971768201988 :: =IFERROR('11_Segments'!D$17/'11_Segments'!C$17-1,0)
  - MISMATCH 05_Drivers!E9: кэш=-0.013, пересчёт=-0.013396089790007282 :: =IFERROR('11_Segments'!E$17/'11_Segments'!D$17-1,0)
  - MISMATCH 05_Drivers!G16: кэш=0.118, пересчёт=0.11764705882352944 :: =IFERROR('01_Macro'!G$43/'01_Macro'!F$43-1,0)
  - MISMATCH 05_Drivers!H16: кэш=0.042, пересчёт=0.042105263157894646 :: =IFERROR('01_Macro'!H$43/'01_Macro'!G$43-1,0)
  - MISMATCH 05_Drivers!F21: кэш=0.013, пересчёт=0.012658227848101333 :: =IFERROR('11_Segments'!F$8/'11_Segments'!E$8-1,0)
  - MISMATCH 05_Drivers!G21: кэш=0.063, пересчёт=0.0625 :: =IFERROR('11_Segments'!G$8/'11_Segments'!F$8-1,0)
- Ошибочных ячеек: 0
- Ссылок на пустые ячейки: 122
  - 05_Drivers!C29 -> 05_Drivers!D89
  - 05_Drivers!C29 -> 05_Drivers!C89
  - 05_Drivers!C30 -> 05_Drivers!D89
  - 05_Drivers!C30 -> 05_Drivers!C89
  - 05_Drivers!C56 -> 17_Debt!C56
  - 05_Drivers!D56 -> 17_Debt!D56
  - 05_Drivers!E56 -> 17_Debt!E56
  - 15_PPE!C21 -> 15_PPE!C18
  - 15_PPE!D21 -> 15_PPE!D18
  - 17_Debt!F30 -> 05_Drivers!F18
  - 17_Debt!G30 -> 05_Drivers!G18
  - 17_Debt!H30 -> 05_Drivers!H18
  - 17_Debt!F90 -> Raw_IFRS!F70
  - 17_Debt!F91 -> Raw_IFRS!F71
  - 17_Debt!F93 -> Raw_IFRS!F73
  - 17_Debt!F95 -> Raw_IFRS!F75
  - 17_Debt!F96 -> Raw_IFRS!F76
  - 17_Debt!F98 -> Raw_IFRS!F78
  - 17_Debt!A99 -> Raw_IFRS!A79
  - 17_Debt!C99 -> Raw_IFRS!D79

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
- **D8:ABS_в_суммах** [WARN]: формул с ABS в суммах: 42
- **E1:разрыв_факт/прогноз** [PASS]: Выручка 2025→2026: +14.9%
- **E2:сетка_годов_ссылок** [FAIL]: 3; 10_Revenue!F17 (2026) -> 11_Segments!C (2023); 10_Revenue!G17 (2027) -> 11_Segments!C (2023); 10_Revenue!H17 (2028) -> 11_Segments!C (2023)
- **E7:sanity_bounds** [PASS]: interest/rev, debt/rev, Δdebt, денормалы — в порогах
- **F5:unlabeled:Control_Panel** [WARN]: 4: WC λ нормализации (год 1) (C52); Fallback средней ставки долга (C66); Fallback доли ST (справочно) (C67); Допуск drift ST/история ± (C68)
- **F7:[РАСЧЁТ]-литерал:Control_Panel** [PASS]: 0
- **G1:регрессии_в_книге** [PASS]: SLOPE/INTERCEPT/RSQ/STEYX: {'SLOPE': 1, 'INTERCEPT': 1, 'RSQ': 1, 'STEYX': 1, 'CORREL': 0, 'LINEST': 0}
- **H1:литералы_в_формулах** [WARN]: 98; 17_Debt!E82=4.0; 17_Debt!E82=2025.0; 18_Lease!F12=0.5; 18_Lease!G12=0.5; 18_Lease!H12=0.5; 20_BS!F40=0.158; 20_BS!G40=0.158; 20_BS!H40=0.158; 24_Equity!F8=0.158; 24_Equity!G8=0.158
- **H2:константы_в_прогнозе** [PASS]: 0; 
- **H3:=прошлый_год** [PASS]: 0 ячеек
- **H4:цвета_кросс-ссылок** [PASS]: все кросс-ссылки аналитики зелёные
- **I3:переключатель** [PASS]: Control_Panel!C25 использует C5
- **J1:потребитель_сигнала** [PASS]: 00_Cover!C20
- **J2:статус_обложки** [PASS]: 1 статус(ов): 00_Cover!C20: ✅ ОК