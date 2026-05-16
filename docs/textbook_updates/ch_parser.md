# PDF Parser Module

## Архитектура

| Метод | Режим | Применение |
|-------|-------|-----------|
| parse_section() | standard | IS, BS, CF, Inventory |
| parse_pivot_note() | text pivot | PPE, Intangibles, Provisions |
| parse_pivot_note() | wide pivot | Associates |
| parse_pivot_note() | sequential | DTA/DTL, Tax |
| parse_instrument_list() | instrument | Debt schedule |

## Исправленные баги

1. Fallback anti-trigger — skip TOC in fallback
2. anchor_mode: any — multi-page face sheets
3. Year range 2010+ — support pre-2015 PDFs
4. IS columns removal — fix wrong years
5. Non-consolidated BS anti-trigger

## Тестирование

22 unit tests, 12 smoke tests. Prod BS=0.000004.
