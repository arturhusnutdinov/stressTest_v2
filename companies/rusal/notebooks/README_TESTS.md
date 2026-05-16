# 📓 Инструкции по запуску тестовых ноутбуков

## 🧪 01_Test_Macro_Module.ipynb

Тестирование модуля макропрогнозирования и VECM.

### Быстрый запуск

```bash
# Вариант 1: Через команду (откроется в браузере)
jupyter notebook 01_Test_Macro_Module.ipynb

# Вариант 2: Через JupyterLab
jupyter lab 01_Test_Macro_Module.ipynb

# Вариант 3: Из корня проекта
cd /Users/arturhusnutdinov/Documents/IT\ Development/Docker/stressTest
jupyter notebook companies/us_steel/notebooks/01_Test_Macro_Module.ipynb
```

### Что тестируется

- ✅ Загрузка конфигурации (project.yaml, macro_ecm.yaml)
- ✅ Поиск и загрузка макро-файлов
- ✅ Чтение временных рядов
- ✅ VECM конфигурация и группы
- ✅ ln-трансформация данных
- ✅ Запуск полного VECM pipeline
- ✅ Создание прогнозов
- ✅ Валидация выходных данных

### Ожидаемые результаты

После выполнения в `outputs/macro_forecast/` должны появиться:
- `*_forecast.csv` - прогнозы для каждого фактора
- `*_ecm_fit.csv` - информация о методах моделирования
- `*_actual_vs_fitted.csv` - метрики валидации

---

## 🏗️ 02_Test_Model_Module.ipynb

**Ключевой тестовый ноутбук для детального тестирования 3-Statement Model.**

### Запуск

```bash
jupyter notebook 02_Test_Model_Module.ipynb
```

### 📖 Пошаговая инструкция

**Полная инструкция:** см. `STEP_BY_STEP_02_Test_Model.md` в корне проекта

### Функционал

1. **Проверка конфигурации**: Загрузка и валидация project.yaml
2. **Загрузка входных данных**: История IS/BS/CF, макро-прогнозы
3. **Построение модели**: Запуск build_model() с валидацией
4. **Сводная таблица 3-Statement**: 
   - Последние 5 лет истории + прогноз
   - Income Statement (с расчетом EBITDA, EBIT, Interest, Tax, Finance Income/Expense, Net Income)
   - Balance Sheet (с 21 канонической строкой)
   - Cash Flow Statement (CFO, CFI, CFF, NetChange)
5. **Детальный анализ** по статьям:
   - Revenue (регрессия с макрофакторами, fitted values, прогнозы)
   - COGS (Variable COGS + D&A, PPI индексация, Clamp ограничения)
   - SG&A (CPI индексация, адаптация к падению, Clamp роста и ratio)
   - CapEx (ratio к revenue, адаптация к падению спроса, Clamp ограничения)
   - Depreciation & Amortization
   - Working Capital (DSO, DPO, DIO, AR, AP, Inventory)
   - PP&E Corkscrew (opening, Capex, Disposals, Dep, ending)
   - Intangibles Corkscrew (opening, Additions, Amort, ending)
   - Debt & RC (погашения, рефинансирование, debt corkscrew по инструментам)
   - Finance Income & Expense
   - Taxes с NOL utilization
   - EBITDA, EBIT, EBT, Net Income
   - Rate Deltas для стресс-тестирования
6. **Валидация**:
   - BS Identity
   - Cash Bridge
   - Retained Earnings Check
   - WC Delta Check

### Особенности

- **Универсальный**: Работает с любой компанией (us_steel, rusal, и т.д.)
- **Динамические периоды**: Использует HISTORY_START_YEAR, HISTORY_END_YEAR, FORECAST_* из project.yaml
- **Train/Test Split**: Автоматическое разделение на обучающую и тестовую выборки
- **Детальная валидация**: Проверка всех финансовых связей
- **Визуализация**: Графики Actual vs Fitted для всех ключевых метрик

---

## 🏢 00_Build_Model_Main.ipynb

Главный ноутбук построения полной финансовой модели.

### Запуск

```bash
jupyter notebook 00_Build_Model_Main.ipynb
```

### Функционал

- Просмотр канонических форм отчетности
- Создание новой модели компании
- Настройка конфигурации
- Валидация данных
- Запуск полного pipeline:
  - Макро-прогноз → Модель → Валидация → Стресс → Рейтинг
- Просмотр результатов и чек-листов

---

## ⚙️ 99_Configure_YAML.ipynb

Интерактивная настройка YAML конфигурации через виджеты.

### Запуск

```bash
jupyter notebook 99_Configure_YAML.ipynb
```

### Функционал

- Визуальный редактор параметров
- Настройка макро-факторов, Revenue, Debt, RC
- Настройка налогов (Tax Rate, NOL parameters)
- Настройка Finance Income/Expense с rate deltas
- Настройка Debt/RC/Refinancing с rate deltas
- Настройка Working Capital
- Валидация конфигурации
- Предпросмотр изменений
- Загрузка/сохранение конфигов

---

## 📝 98_Generate_Model_Documentation.ipynb

Генератор полной документации модели.

### Запуск

```bash
jupyter notebook 98_Generate_Model_Documentation.ipynb
```

### Функционал

- Генерация README.md с описанием данных и конфигурации
- Генерация MODEL_SPECIFICATION.md:
  - Методы моделирования всех статей
  - Расчетные параметры из истории (margins, days)
  - Допущения моделирования
  - Трансформации данных
- Генерация YAML_PARAMETERS.md (все параметры из project.yaml)
- Автоматическое извлечение информации из:
  - Конфигурации YAML
  - Результатов валидации
  - Расчетных параметров

---

## ⚠️ Общие требования

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Установка Jupyter

```bash
pip install jupyter jupyterlab
```

### 3. Проверка конфигурации

Убедитесь что существует:
- `companies/us_steel/configs/project.yaml`
- `companies/us_steel/configs/macro_ecm.yaml` (или общий в `configs/forecast/`)

### 4. Проверка данных

Убедитесь что существуют:
- Макро-файлы в `macro/global/drivers/` или `macro/industry/metallurgy/drivers/`
- Исторические данные (если тестируете модель): `companies/us_steel/history/*.csv`

---

## 🔧 Решение проблем

### Jupyter не запускается

```bash
# Проверьте установку
pip install --upgrade jupyter

# Или используйте полный путь к python
python3 -m jupyter notebook
```

### Модуль не найден

Убедитесь что вы запускаете ноутбук из корня проекта или используете правильный `ROOT` путь в ноутбуке.

### Конфигурация не найдена

Проверьте путь в `project.yaml`:
```yaml
macro_forecast:
  config: companies/us_steel/configs/macro_ecm.yaml
```

### Данные не загружаются

Проверьте:
1. Существуют ли файлы макро-факторов в указанных `search_paths`
2. Правильность `file_map` в `project.yaml`
3. Формат CSV файлов (должны быть годы в заголовках или year/value колонки)

---

## 📊 Интерпретация результатов

### Зеленые галочки (✅)
Все проверки пройдены, данные корректны.

### Желтые предупреждения (⚠️)
Есть проблемы, но не критичные. Рекомендуется проверить.

### Красные ошибки (❌)
Критичные проблемы, требуется исправление.

---

## 💡 Советы

1. **Запускайте ячейки последовательно** - не пропускайте шаги
2. **Проверяйте вывод каждой ячейки** - ошибки в начале могут повлиять на следующие шаги
3. **Используйте Run All Cells** только после первого успешного запуска
4. **Сохраняйте результаты** - они могут понадобиться для анализа
5. **Читайте комментарии** - в ноутбуке есть полезные подсказки

