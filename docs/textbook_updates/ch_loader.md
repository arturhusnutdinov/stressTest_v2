# Загрузка данных через ноутбуки

## Workflow

PDF Parser → Excel (21 лист) → 01_Data_Loading.ipynb → data_mart_v2.db

## 01_Data_Loading.ipynb (9 ячеек)

Шаг 1: ExcelLoader — IS/BS/CF + PPE + canonical (2,280 строк)
Шаг 2: Schedule Loader — Notes корки (177 строк)
Итого: 2,457 строк → DB

## Тест-стенд

```bash
python3 tests/integration/setup_test_stand.py --company rusal
python3 tests/integration/verify_consistency.py --company rusal
```

11 таблиц сравниваются: prod vs test. BS Identity: 13/13 OK.
