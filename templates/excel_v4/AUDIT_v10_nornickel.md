# Аудит nornickel_v4.xlsx

Дата: 2026-11-17 · Стандарт: СТАНДАРТ_верификации_моделей.md

- **A1** [PASS]: архив читается, 40 xml, bad=None
- **A2** [PASS]: длинных/битых формул: 0
- **A3a** [PASS]: внешних ссылок: 0
- **A3b** [PASS]: ссылок на несуществующие листы: 0
- **A4** [INFO]: calcPr: iterate=None, count=None, delta=None, fullCalcOnLoad=True

## Группа B: кэш и сходимость

- Формул: 2072, покрыто мини-вычислителем: 967 (46.7%)
- Расхождений кэша: 0
- Ошибочных ячеек: 0
- Ссылок на пустые ячейки: 123
  - 05_Drivers!C29 -> 05_Drivers!D89
  - 05_Drivers!C29 -> 05_Drivers!C89
  - 05_Drivers!C30 -> 05_Drivers!D89
  - 05_Drivers!C30 -> 05_Drivers!C89
  - 05_Drivers!C56 -> 17_Debt!C56
  - 05_Drivers!D56 -> 17_Debt!D56
  - 05_Drivers!E56 -> 17_Debt!E56
  - 10_Revenue!F20 -> 01_Macro!E39
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
- **E1:разрыв_факт/прогноз** [PASS]: Выручка 2025→2026: +0.8%
- **E2:сетка_годов_ссылок** [PASS]: 0 смещений
- **F5:unlabeled:Control_Panel** [PASS]: 0 констант без метки
- **F7:[РАСЧЁТ]-литерал:Control_Panel** [PASS]: 0
- **G1:регрессии_в_книге** [PASS]: SLOPE/INTERCEPT/RSQ/STEYX: {'SLOPE': 1, 'INTERCEPT': 1, 'RSQ': 1, 'STEYX': 1, 'CORREL': 0, 'LINEST': 0}
- **H1:литералы_в_формулах** [WARN]: 109; 17_Debt!C49=0.08; 17_Debt!D49=0.08; 17_Debt!E49=0.08; 17_Debt!F49=0.08; 17_Debt!G49=0.08; 17_Debt!H49=0.08; 17_Debt!H52=0.5; 17_Debt!H53=0.5; 17_Debt!E82=4.0; 17_Debt!E82=2025.0
- **H2:константы_в_прогнозе** [PASS]: 0; 
- **H3:=прошлый_год** [PASS]: 0 ячеек
- **I3:переключатель** [PASS]: Control_Panel!C25 использует C5
- **J1:потребитель_сигнала** [PASS]: 00_Cover!C20
- **J2:статус_обложки** [PASS]: 1 статус(ов): 00_Cover!C20: ✅ ОК