"""
init_company.py — инициализация новой компании.

Создаёт структуру директорий, копирует шаблоны конфигов и ноутбуков,
подставляет company_id во всех шаблонах.

Использование:
    python3 tools/init_company.py test_corp --name "Test Corporation" --industry metals --standard IFRS
    python3 tools/init_company.py test_corp --force  # перезаписать
"""
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


# Корень проекта — один уровень выше tools/
ROOT = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = ROOT / "templates"


# ── Структура директорий ─────────────────────────────────────────────────────

DIRS = [
    "configs",
    "configs/forecast",
    "data",
    "data/excel",
    "data/macro",
    "data/debt",
    "data/operational",
    "data/statements",
    "data/annual_reports",
    "notebooks",
    "outputs/model",
    "outputs/stress",
    "outputs/reports",
]

# Ноутбуки: шаблон → целевое имя
NOTEBOOKS = {
    "00_Build_Model_Main.ipynb":              "00_Build_Model_Main.ipynb",
    "01_Data_Loading.ipynb":                  "01_Data_Loading.ipynb",
    "01_Test_Macro_Module.ipynb":             "01_Test_Macro_Module.ipynb",
    "02_Test_Model_Module.ipynb":             "02_Test_Model_Module.ipynb",
    "03_Stress_Testing.ipynb":                "03_Stress_Testing.ipynb",
    "04_Rating.ipynb":                        "04_Rating.ipynb",
    "05_Covenants.ipynb":                     "05_Covenants.ipynb",
    "98_Generate_Model_Documentation.ipynb":  "98_Generate_Model_Documentation.ipynb",
    "99_Configure_Excel_Loader.ipynb":        "99_Configure_Excel_Loader.ipynb",
    "99_Configure_YAML.ipynb":                "99_Configure_YAML.ipynb",
}

# Placeholder ноутбуки (создаются если шаблон не найден)
PLACEHOLDER_NOTEBOOKS = []


def init_company(
    company_id: str,
    name: str,
    industry: str = "metals",
    currency: str = "USD",
    standard: str = "US_GAAP",
    force: bool = False,
) -> Path:
    """Инициализирует структуру новой компании."""
    company_dir = ROOT / "companies" / company_id

    if company_dir.exists() and not force:
        print(f"  ⚠ Директория уже существует: {company_dir}")
        print(f"    Используйте --force для перезаписи")
        return company_dir

    print(f"Инициализация компании: {name} ({company_id})")
    print(f"  Отрасль:   {industry}")
    print(f"  Валюта:    {currency}")
    print(f"  Стандарт:  {standard}")
    print(f"  Директория: {company_dir}")
    print()

    # Общие подстановки для всех файлов
    replacements = {
        "{company}": company_id,
        "{COMPANY_NAME}": name,
        "{INDUSTRY}": industry,
        "{CURRENCY}": currency,
        "{STANDARD}": standard,
        "us_steel": company_id,
        "US Steel": name,
        "_COMPANY_": company_id,
    }

    def _apply_replacements(content: str) -> str:
        for old, new in replacements.items():
            content = content.replace(old, new)
        return content

    # ── 1. Создаём директории ────────────────────────────────────────────────
    for d in DIRS:
        (company_dir / d).mkdir(parents=True, exist_ok=True)
    print(f"  ✓ Директории ({len(DIRS)})")

    # ── 2. project.yaml ──────────────────────────────────────────────────────
    src = TEMPLATES_DIR / "project_template.yaml"
    dst = company_dir / "configs" / "project.yaml"
    if src.exists():
        content = _apply_replacements(src.read_text())
        # Подстановка is_income_sign по стандарту
        if standard == "IFRS":
            content = content.replace("is_income_sign: credit_negative", "is_income_sign: natural")
            content = content.replace("da_in_cogs: true", "da_in_cogs: false")
        dst.write_text(content)
    else:
        dst.write_text(f"# project.yaml — {name}\nmodel:\n  mode: standard\n")
    print(f"  ✓ configs/project.yaml")

    # ── 3. accounting_conventions.yaml ──────────────────────────────────────
    src = TEMPLATES_DIR / "accounting_conventions_template.yaml"
    dst = company_dir / "configs" / "accounting_conventions.yaml"
    if src.exists():
        dst.write_text(_apply_replacements(src.read_text()))
    else:
        dst.write_text(f"company: {company_id}\ncash_in_cf:\n  type: cash_only\n")
    print(f"  ✓ configs/accounting_conventions.yaml")

    # ── 4. excel_loader.yaml ─────────────────────────────────────────────────
    src = TEMPLATES_DIR / "excel_loader_template.yaml"
    if not src.exists():
        src = TEMPLATES_DIR / "mapping_template.yaml"
    dst = company_dir / "configs" / "excel_loader.yaml"
    if src.exists():
        dst.write_text(_apply_replacements(src.read_text()))
    else:
        dst.write_text(f"# Excel loader config for {name}\nloader_settings:\n  company_id: {company_id}\n")
    print(f"  ✓ configs/excel_loader.yaml")

    # ── 5. macro_ecm.yaml ────────────────────────────────────────────────────
    src = TEMPLATES_DIR / "macro_ecm_full_template.yaml"
    dst = company_dir / "configs" / "forecast" / "macro_ecm.yaml"
    if src.exists():
        dst.write_text(_apply_replacements(src.read_text()))
    else:
        dst.write_text(f"# Macro ECM config for {name}\n")
    print(f"  ✓ configs/forecast/macro_ecm.yaml")

    # ── 6. stress_scenarios.yaml ─────────────────────────────────────────────
    src = TEMPLATES_DIR / "scenario_template.yaml"
    dst = company_dir / "configs" / "stress_scenarios.yaml"
    if src.exists():
        dst.write_text(_apply_replacements(src.read_text()))
    else:
        _write_stress_scenarios(dst, industry)
    print(f"  ✓ configs/stress_scenarios.yaml")

    # ── 7. Ноутбуки ──────────────────────────────────────────────────────────
    notebooks_src = TEMPLATES_DIR / "notebooks"
    notebooks_dst = company_dir / "notebooks"

    copied = 0
    for src_name, dst_name in NOTEBOOKS.items():
        src = notebooks_src / src_name
        dst = notebooks_dst / dst_name
        if src.exists():
            _copy_notebook(src, dst, company_id, name)
            copied += 1
        else:
            _create_placeholder_notebook(dst, dst_name, company_id)

    for nb_name in PLACEHOLDER_NOTEBOOKS:
        _create_placeholder_notebook(notebooks_dst / nb_name, nb_name, company_id)

    print(f"  ✓ notebooks ({copied} скопировано + {len(PLACEHOLDER_NOTEBOOKS)} placeholder)")

    # ── 8. Excel шаблон ───────────────────────────────────────────────────────
    excel_path = company_dir / "data" / "excel" / f"{company_id}_unified.xlsx"
    if not excel_path.exists():
        _create_excel_template(excel_path, company_id)
        print(f"  ✓ data/excel/{company_id}_unified.xlsx")

    # ── 9. README.md ─────────────────────────────────────────────────────────
    (company_dir / "README.md").write_text(f"""\
# {name}

**company_id**: `{company_id}`
**Отрасль**: {industry}
**Валюта**: {currency}
**Стандарт учёта**: {standard}

## Структура
```
companies/{company_id}/
  configs/
    project.yaml              # Главный конфиг модели
    excel_loader.yaml         # Маппинг Excel → DB
    accounting_conventions.yaml
    forecast/macro_ecm.yaml   # Настройки макро-прогноза
    stress_scenarios.yaml     # Стресс-сценарии
  data/
    excel/                    # UNIFIED Excel с данными (IS/BS/CF/debt/macro)
    statements/               # МСФО / US GAAP отчётность (PDF)
    annual_reports/           # Годовые отчёты для акционеров (PDF)
    macro/                    # Макро-факторы (CSV)
    debt/                     # Долговые расписания
    operational/              # Операционные KPI
  notebooks/
    00_Build_Model_Main.ipynb # Главный pipeline
    01_Data_Loading.ipynb     # Загрузка данных
    02_Test_Model_Module.ipynb # Тестирование модели
    03_Stress_Testing.ipynb   # Стресс-тесты
    04_Rating.ipynb           # Кредитный рейтинг
    05_Covenants.ipynb        # Ковенанты
  outputs/                    # Результаты модели
```

## Быстрый старт

1. Заполните Excel: `data/excel/{company_id}_unified.xlsx`
2. Настройте: `configs/project.yaml`
3. Загрузите данные: `notebooks/01_Data_Loading.ipynb`
4. Запустите модель: `notebooks/00_Build_Model_Main.ipynb`

## CLI
```bash
# Полный прогон
python3 -m engine.orchestrator {company_id} --stress --rating

# Только модель
python3 -m engine.orchestrator {company_id} --no-preprocess
```
""")
    print(f"  ✓ README.md")

    print()
    print(f"✅ Компания '{company_id}' инициализирована: {company_dir}")
    print()
    print("Следующие шаги:")
    print(f"  1. Подготовьте Excel: companies/{company_id}/data/excel/{company_id}_unified.xlsx")
    print(f"  2. Отредактируйте:   companies/{company_id}/configs/project.yaml")
    print(f"  3. Запустите:        companies/{company_id}/notebooks/01_Data_Loading.ipynb")

    return company_dir


def _create_excel_template(path: Path, company_id: str) -> None:
    """Создаёт пустой Excel шаблон с листами IS/BS/CF/segments/debt/ppe/macro."""
    try:
        import openpyxl
    except ImportError:
        path.write_bytes(b"")  # fallback: пустой файл
        return

    wb = openpyxl.Workbook()
    years = list(range(2011, 2026))

    # history_is
    ws = wb.active
    ws.title = "history_is"
    ws.append(["metric"] + years)
    for m in ["revenue", "cost_of_goods_sold", "gross_profit",
              "selling_general_admin", "other_operating_income", "other_operating_expense",
              "asset_impairment", "depreciation_amortization", "total_depreciation_amortization",
              "ebitda", "ebit", "interest_expense", "interest_income",
              "earnings_from_investees", "other_financial_costs",
              "earnings_before_tax", "tax_expense", "net_income"]:
        ws.append([m] + [None] * len(years))

    # history_bs
    ws2 = wb.create_sheet("history_bs")
    ws2.append(["metric"] + years)
    for m in ["cash_and_equivalents", "accounts_receivable", "inventory",
              "other_current_assets", "total_current_assets",
              "ppe_net", "ppe_gross", "ppe_accumulated_depreciation",
              "intangibles", "goodwill", "investments_long_term",
              "deferred_tax_asset", "other_non_current_assets",
              "total_non_current_assets", "total_assets",
              "accounts_payable", "short_term_debt", "taxes_payable",
              "other_current_liabilities", "total_current_liabilities",
              "long_term_debt", "deferred_tax_liability",
              "other_non_current_liabilities", "total_non_current_liabilities",
              "total_liabilities",
              "share_capital", "additional_paid_in_capital", "retained_earnings",
              "accumulated_other_comprehensive_income",
              "total_equity", "non_controlling_interests",
              "total_liabilities_and_equity"]:
        ws2.append([m] + [None] * len(years))

    # history_cf
    ws3 = wb.create_sheet("history_cf")
    ws3.append(["metric"] + years)
    for m in ["net_income", "depreciation_amortization", "deferred_tax",
              "change_accounts_receivable", "change_inventory",
              "change_accounts_payable", "change_other_working_capital",
              "other_operating_activities", "cfo_total",
              "capital_expenditure", "acquisitions", "disposal_proceeds",
              "other_investing_activities", "cfi_total",
              "debt_issuance", "debt_repayment",
              "dividends_paid", "share_buyback",
              "other_financing_activities", "cff_total",
              "net_change_in_cash", "cash_beginning", "cash_ending"]:
        ws3.append([m] + [None] * len(years))

    # segments, debt_instruments, ppe_components, macro_factors, operational_drivers
    ws4 = wb.create_sheet("segments")
    ws4.append(["segment", "metric"] + years)

    ws5 = wb.create_sheet("debt_instruments")
    ws5.append(["instrument_id", "instrument_name", "currency", "opening_balance",
                "interest_rate", "rate_type", "base_rate_factor",
                "maturity_date", "amortization_profile", "callable_flag",
                "yr1", "yr2", "yr3", "yr4", "yr5", "yr6_plus"])

    ws6 = wb.create_sheet("ppe_components")
    ws6.append(["category", "movement", "year", "value"])

    ws7 = wb.create_sheet("macro_factors")
    ws7.append(["factor"] + years)

    ws8 = wb.create_sheet("operational_drivers")
    ws8.append(["driver", "unit"] + years)

    wb.save(path)


def _write_stress_scenarios(path: Path, industry: str) -> None:
    pack = "metals_mining" if industry == "metals" else "recession"
    path.write_text(f"""\
scenarios:
  base_stress:
    description: "Base stress scenario"
    macro_shocks: {{}}
    driver_shocks:
      cogs_pct:
        type: pp
        value: 3.0
  rate_spike:
    description: "Interest rate +200bp"
    driver_shocks:
      avg_rate:
        type: pp
        value: 2.0
""")


def _copy_notebook(src: Path, dst: Path, company_id: str, company_name: str) -> None:
    """Копирует ноутбук и подставляет company_id."""
    with open(src) as f:
        nb = json.load(f)

    for cell in nb.get("cells", []):
        new_src = []
        for line in cell.get("source", []):
            line = line.replace("us_steel", company_id)
            line = line.replace("US Steel", company_name)
            new_src.append(line)
        cell["source"] = new_src
        # Clear outputs
        if cell.get("cell_type") == "code":
            cell["outputs"] = []
            cell["execution_count"] = None

    with open(dst, "w") as f:
        json.dump(nb, f, ensure_ascii=False, indent=1)


def _create_placeholder_notebook(dst: Path, name: str, company_id: str) -> None:
    """Создаёт минимальный placeholder ноутбук."""
    nb = {
        "nbformat": 4, "nbformat_minor": 4,
        "metadata": {
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.11.0"},
        },
        "cells": [
            {
                "cell_type": "markdown", "metadata": {},
                "source": [f"# {name.replace('.ipynb', '')}\n\nКомпания: `{company_id}`"],
            },
            {
                "cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                "source": [
                    "import sys\n",
                    "from pathlib import Path\n",
                    "\n",
                    "# Auto-detect project root\n",
                    "_nb = Path('.').resolve()\n",
                    "for _p in [_nb] + list(_nb.parents):\n",
                    "    if (_p / 'engine').is_dir():\n",
                    "        ROOT = _p\n",
                    "        break\n",
                    "sys.path.insert(0, str(ROOT))\n",
                    f"COMPANY_ID = '{company_id}'\n",
                    "print(f'ROOT: {ROOT}')\n",
                    "print(f'Company: {COMPANY_ID}')\n",
                ],
            },
        ],
    }
    dst.write_text(json.dumps(nb, ensure_ascii=False, indent=1))


def main():
    parser = argparse.ArgumentParser(description="Инициализация новой компании")
    parser.add_argument("company",    help="ID компании (например: test_corp)")
    parser.add_argument("--name",     default=None, help="Полное название")
    parser.add_argument("--industry", default="metals",
                        choices=["metals", "steel", "energy", "consumer", "tech", "financial", "other"])
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--standard", default="US_GAAP", choices=["US_GAAP", "IFRS"])
    parser.add_argument("--force",    action="store_true", help="Перезаписать если существует")
    args = parser.parse_args()

    name = args.name or args.company.replace("_", " ").title()
    init_company(
        company_id=args.company,
        name=name,
        industry=args.industry,
        currency=args.currency,
        standard=args.standard,
        force=args.force,
    )


if __name__ == "__main__":
    main()
