# Аудит rusal_v4.xlsx

Дата: 2026-11-17 · Стандарт: СТАНДАРТ_верификации_моделей.md

- **A1** [PASS]: архив читается, 40 xml, bad=None
- **A2** [PASS]: длинных/битых формул: 0
- **A3a** [PASS]: внешних ссылок: 0
- **A3b** [PASS]: ссылок на несуществующие листы: 0
- **A4** [INFO]: calcPr: iterate=None, count=None, delta=None, fullCalcOnLoad=True

## Группа B: кэш и сходимость

- Формул: 2269, покрыто мини-вычислителем: 1015 (44.7%)
- Расхождений кэша: 0
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
- **E1:разрыв_факт/прогноз** [PASS]: Выручка 2025→2026: +5.6%
- **E2:сетка_годов_ссылок** [PASS]: 0 смещений
- **F5:unlabeled:Control_Panel** [PASS]: 0 констант без метки
- **F7:[РАСЧЁТ]-литерал:Control_Panel** [PASS]: 0
- **G1:регрессии_в_книге** [PASS]: SLOPE/INTERCEPT/RSQ/STEYX: {'SLOPE': 1, 'INTERCEPT': 1, 'RSQ': 1, 'STEYX': 1, 'CORREL': 0, 'LINEST': 0}
- **H1:литералы_в_формулах** [WARN]: 103; 17_Debt!C49=0.08; 17_Debt!D49=0.08; 17_Debt!E49=0.08; 17_Debt!F49=0.08; 17_Debt!G49=0.08; 17_Debt!H49=0.08; 17_Debt!H52=0.5; 17_Debt!H53=0.5; 17_Debt!E82=4.0; 17_Debt!E82=2025.0
- **H2:константы_в_прогнозе** [PASS]: 0; 
- **H3:=прошлый_год** [PASS]: 0 ячеек
- **I3:переключатель** [PASS]: Control_Panel!C25 использует C5
- **J1:потребитель_сигнала** [PASS]: 00_Cover!C20
- **J2:статус_обложки** [PASS]: 1 статус(ов): 00_Cover!C20: ⚠ КОВЕНАНТЫ НАРУШЕНЫ