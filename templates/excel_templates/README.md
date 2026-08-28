# 📊 Excel шаблоны для загрузки данных

Эта директория содержит Excel шаблоны для загрузки данных в модель.

## template_UNIFIED_v3.xlsx (2026-08-28)

Текущий стандарт. 18 листов с каноническими именами метрик.

Формат IS/BS: `label | db_metric | sign | unit | year_1 | year_2 | ...`
Формат CF: `label | excel_metric | db_metric | sign | unit | year_1 | ...`

ExcelLoader (`engine/loader/excel.py`) автоматически определяет формат (legacy или v3) по наличию колонки `db_metric`.

Заполненные шаблоны:
- Nornickel: `companies/nornickel_v2/data/excel/nornickel_v2_template_v3.xlsx` (38 drivers, 5 segments, 14 cost items)
- Rusal: `companies/rusal/data/excel/rusal_template_v3.xlsx` (10 drivers, 69 instruments, SGA/D&A/tax splits)

```bash
# Загрузить template_v3 файл
python3 tools/load_unified_excel.py --company nornickel_v2 \
    --excel companies/nornickel_v2/data/excel/nornickel_v2_template_v3.xlsx
```

---

## Отдельные шаблоны (legacy)

### Финансовые отчеты

- **template_IS_Income_Statement.xlsx** - Отчет о прибылях и убытках
- **template_BS_Balance_Sheet.xlsx** - Баланс
- **template_CF_Cash_Flow.xlsx** - Отчет о движении денежных средств

### Макро-данные

- **template_MACRO_Factor.xlsx** - Шаблон для макроэкономических факторов
  - Используйте этот шаблон для каждого фактора отдельно
  - Переименуйте файл в `{factor_name}.xlsx` (например, `gdp_us.xlsx`)

### Данные по долгу

- **template_DEBT_Schedule.xlsx** - Расписание долга
  - Содержит все инструменты долга (RC, Loans, Bonds)

### Операционные данные

- **template_OPERATIONAL_Metric.xlsx** - Шаблон для операционных метрик
  - Используйте для каждого показателя отдельно
  - Переименуйте в `{metric_name}.xlsx` (например, `volumes_kt.xlsx`)

## 🚀 Использование

### Шаг 1: Откройте шаблон

1. Откройте нужный шаблон в Excel или LibreOffice Calc
2. Ознакомьтесь с инструкциями в первой строке (если есть)

### Шаг 2: Заполните данные

1. Заполните все обязательные поля
2. Опциональные поля можно оставить пустыми
3. Убедитесь, что:
   - Годы в формате YYYY (например, 2020)
   - Все значения числовые
   - Названия статей соответствуют каноническим именам

### Шаг 3: Сохраните и загрузите

```bash
# Загрузить все файлы из директории
python tools/excel_loader.py \
    --input path/to/your/excel/files/ \
    --output /path/to/project/root/ \
    --company your_company_name

# Или загрузить отдельный файл
python tools/excel_loader.py \
    --file Income_Statement.xlsx \
    --output /path/to/project/root/ \
    --company your_company_name \
    --statement IS
```

## 📚 Документация

Полная документация доступна в:
- **docs/EXCEL_TEMPLATES_GUIDE.md** - Руководство по использованию шаблонов
- **docs/CANONICAL_FORMS.md** - Описание канонических форм отчетности
- **docs/MAPPING_GUIDE.md** - Руководство по мэппингу данных

## 🔄 Регенерация шаблонов

Если нужно пересоздать шаблоны:

```bash
python tools/excel_template_generator.py --output_dir templates/excel_templates/
```

## ⚠️ Важные замечания

1. **Не изменяйте названия колонок** - они должны соответствовать каноническим именам
2. **Год в формате YYYY** - используйте полный формат (2020, не 20)
3. **Валюта** - все значения должны быть в одной валюте
4. **Пустые значения** - если статья отсутствует, оставьте ячейку пустой

## 📞 Поддержка

Если у вас возникли вопросы:
1. Ознакомьтесь с документацией в `docs/EXCEL_TEMPLATES_GUIDE.md`
2. Проверьте примеры в `companies/us_steel/`
3. Запустите валидацию данных через `00_Build_Model_Main.ipynb`

