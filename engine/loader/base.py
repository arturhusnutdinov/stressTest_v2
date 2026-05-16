"""
Базовый загрузчик и движок маппинга.
Принцип: алиасы и формулы — только здесь. После записи в БД везде единые имена.
"""

from __future__ import annotations

import ast
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

import yaml

logger = logging.getLogger(__name__)

# ─── единицы измерения ────────────────────────────────────────────────────────

UNIT_SCALE: Dict[str, float] = {
    "usd":    1.0,
    "tusd":   1_000.0,
    "musd":   1_000_000.0,
    "busd":   1_000_000_000.0,
    "rub":    1.0,
    "trub":   1_000.0,
    "mrub":   1_000_000.0,
    "eur":    1.0,
    "teur":   1_000.0,
    "meur":   1_000_000.0,
    "cny":    1.0,
    "tcny":   1_000.0,
    "mcny":   1_000_000.0,
    "kt":     1_000.0,       # килотонны → тонны
    "mt":     1_000_000.0,   # мегатонны → тонны
    "pct":    0.01,           # проценты → доли
    "percent":0.01,
    "%":      0.01,
    "days":   1.0,
    "index":  1.0,
    "ratio":  1.0,
    "units":  1.0,
    "":       1.0,
}

def unit_scale_factor(source_unit: str, db_unit: str) -> float:
    """
    Возвращает коэффициент конвертации source → db.
    Пример: source=mUSD, db=tUSD → scale=1000 (1M / 1K = ×1000).
    """
    src = UNIT_SCALE.get(source_unit.lower().strip(), 1.0)
    dst = UNIT_SCALE.get(db_unit.lower().strip(), 1.0)
    if dst == 0:
        raise ValueError(f"db_unit '{db_unit}' имеет нулевой scale")
    return src / dst


# ─── dataclasses ──────────────────────────────────────────────────────────────

@dataclass
class RowMapping:
    """Маппинг одной строки Excel → канон."""
    label: str                          # отображаемое название из Excel
    db_metric: Optional[str] = None     # каноническое имя в БД
    formula: Optional[str] = None       # "product_revenue + service_revenue"
    sign: float = 1.0                   # +1 или -1
    unit: Optional[str] = None          # переопределение единицы для строки
    note: str = ""

    @property
    def is_canonical(self) -> bool:
        return bool(self.db_metric and not self.formula)

    @property
    def is_formula(self) -> bool:
        return bool(self.db_metric and self.formula)

    @property
    def is_unmapped(self) -> bool:
        return not self.db_metric


@dataclass
class SheetMapping:
    """Маппинг одного листа Excel."""
    sheet_name: str
    statement: str              # IS | BS | CF | canonical | schedule
    mappings: List[RowMapping] = field(default_factory=list)
    unmapped: List[str] = field(default_factory=list)  # labels без db_metric

    def mapped_metrics(self) -> Set[str]:
        return {m.db_metric for m in self.mappings if m.db_metric}


@dataclass
class MappingConfig:
    """Полный конфиг маппинга компании (из excel_loader.yaml)."""
    company_id: str
    version: str = "1.0"
    sheets: Dict[str, SheetMapping] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: Path) -> "MappingConfig":
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        cfg = cls(
            company_id=raw.get("company", ""),
            version=raw.get("version", "1.0"),
        )
        for sheet_name, sheet_data in (raw.get("sheets") or {}).items():
            statement = sheet_data.get("statement", _infer_statement(sheet_name))
            sm = SheetMapping(sheet_name=sheet_name, statement=statement)
            for m in sheet_data.get("mappings", []):
                sm.mappings.append(RowMapping(
                    label=m["label"],
                    db_metric=m.get("db_metric") or None,
                    formula=m.get("formula") or None,
                    sign=float(m.get("sign", 1)),
                    unit=m.get("unit") or None,
                    note=m.get("note", ""),
                ))
            sm.unmapped = sheet_data.get("unmapped", [])
            cfg.sheets[sheet_name] = sm
        return cfg

    def to_yaml(self, path: Path) -> None:
        data: Dict[str, Any] = {
            "version": self.version,
            "company": self.company_id,
            "sheets": {},
        }
        for sheet_name, sm in self.sheets.items():
            data["sheets"][sheet_name] = {
                "statement": sm.statement,
                "mappings": [
                    {k: v for k, v in {
                        "label": m.label,
                        "db_metric": m.db_metric,
                        "formula": m.formula,
                        "sign": m.sign if m.sign != 1.0 else None,
                        "unit": m.unit,
                        "note": m.note or None,
                    }.items() if v is not None}
                    for m in sm.mappings
                ],
                "unmapped": sm.unmapped,
            }
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


@dataclass
class LoadResult:
    """Результат операции загрузки."""
    company_id: str
    source_file: str
    rows_written: int = 0
    rows_skipped: int = 0
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    missing_required: List[str] = field(default_factory=list)
    unmapped_labels: List[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    def summary(self) -> str:
        lines = [
            f"Загрузка: {self.source_file} → {self.company_id}",
            f"  Записано: {self.rows_written}  Пропущено: {self.rows_skipped}",
        ]
        if self.missing_required:
            lines.append(f"  ⚠ Отсутствуют обязательные метрики: {self.missing_required}")
        if self.unmapped_labels:
            lines.append(f"  ⚠ Не замаплено строк: {len(self.unmapped_labels)}")
        if self.warnings:
            for w in self.warnings[:5]:
                lines.append(f"  ⚠ {w}")
        if self.errors:
            for e in self.errors[:5]:
                lines.append(f"  ✗ {e}")
        return "\n".join(lines)


# ─── formula engine ───────────────────────────────────────────────────────────

class FormulaEngine:
    """
    Вычисляет составные метрики по формулам.
    Формулы: строки вида "a + b - c * 0.5"
    Поддерживает: +, -, *, /, унарный минус, скобки, константы.
    Все имена в формуле — db_metric из текущего контекста.
    """

    def __init__(self) -> None:
        self._cache: Dict[str, Any] = {}

    def evaluate(
        self,
        formula: str,
        context: Dict[str, float],
        year: int,
    ) -> Optional[float]:
        """
        Вычислить формулу для одного года.
        context: {db_metric: value} — все загруженные значения за этот год.
        Возвращает None если любой компонент отсутствует в context.
        """
        try:
            expr = self._parse(formula)
            return self._eval_node(expr, context, year)
        except MissingMetricError as e:
            logger.debug(f"Формула '{formula}' год {year}: отсутствует {e}")
            return None
        except Exception as e:
            logger.warning(f"Ошибка формулы '{formula}' год {year}: {e}")
            return None

    def build_dag(
        self, mappings: List[RowMapping]
    ) -> List[RowMapping]:
        """
        Топологическая сортировка: сначала строки без формул,
        потом формульные в порядке зависимостей.
        Поднимает ValueError при обнаружении цикла.
        """
        no_formula = [m for m in mappings if not m.formula]
        with_formula = [m for m in mappings if m.formula]

        if not with_formula:
            return no_formula

        # Строим граф зависимостей
        metric_to_mapping = {m.db_metric: m for m in mappings if m.db_metric}
        in_degree: Dict[str, int] = {}
        deps: Dict[str, List[str]] = {}

        for m in with_formula:
            names = self._extract_names(m.formula or "")
            formula_deps = [n for n in names if n in metric_to_mapping]
            if m.db_metric:
                deps[m.db_metric] = formula_deps
            if m.db_metric:
                in_degree[m.db_metric] = len([d for d in formula_deps if d in metric_to_mapping and metric_to_mapping[d].formula])

        # Kahn's algorithm
        sorted_formula: List[RowMapping] = []
        queue = [m for m in with_formula if in_degree.get(m.db_metric, 0) == 0]
        visited: Set[str] = set()

        while queue:
            node = queue.pop(0)
            sorted_formula.append(node)
            visited.add(node.db_metric)
            # обновить зависимости тех кто зависит от node
            for m in with_formula:
                if m.db_metric in visited:
                    continue
                if node.db_metric in deps.get(m.db_metric, []):
                    in_degree[m.db_metric] = in_degree.get(m.db_metric, 1) - 1
                    if in_degree[m.db_metric] <= 0:
                        queue.append(m)

        if len(sorted_formula) != len(with_formula):
            remaining = [m.db_metric for m in with_formula if m.db_metric not in visited]
            raise ValueError(f"Цикл в формулах: {remaining}")

        return no_formula + sorted_formula

    def _extract_names(self, formula: str) -> List[str]:
        """Извлечь все идентификаторы из формулы."""
        return re.findall(r'\b([a-z_][a-z0-9_]*)\b', formula.lower())

    def _parse(self, formula: str) -> ast.AST:
        key = formula
        if key not in self._cache:
            self._cache[key] = ast.parse(formula, mode="eval").body
        return self._cache[key]

    def _eval_node(self, node: ast.AST, ctx: Dict[str, float], year: int) -> float:
        if isinstance(node, ast.Constant):
            return float(node.value)
        if isinstance(node, ast.Name):
            name = node.id
            if name not in ctx:
                raise MissingMetricError(name)
            return float(ctx[name])
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
            return -self._eval_node(node.operand, ctx, year)
        if isinstance(node, ast.BinOp):
            left  = self._eval_node(node.left,  ctx, year)
            right = self._eval_node(node.right, ctx, year)
            op = node.op
            if isinstance(op, ast.Add):  return left + right
            if isinstance(op, ast.Sub):  return left - right
            if isinstance(op, ast.Mult): return left * right
            if isinstance(op, ast.Div):
                if right == 0:
                    raise ZeroDivisionError(f"Деление на ноль в формуле")
                return left / right
        raise ValueError(f"Неподдерживаемый AST-узел: {type(node).__name__}")


class MissingMetricError(Exception):
    pass


# ─── базовый загрузчик ────────────────────────────────────────────────────────

class BaseLoader:
    """
    Базовый класс для всех загрузчиков.
    Предоставляет: конвертацию единиц, formula engine, запись в Repository.
    """

    # Обязательные метрики для каждого statement
    REQUIRED_METRICS: Dict[str, List[str]] = {
        "IS": ["revenue", "cogs", "sga", "ebit", "ebt", "tax_expense", "net_income"],
        "BS": ["cash", "accounts_receivable", "inventory", "accounts_payable",
               "long_term_debt", "retained_earnings", "total_assets", "total_equity"],
        "CF": ["cfo_total", "cfi_total", "cff_total", "net_change", "cash_ending"],
    }

    def __init__(
        self,
        company_id: str,
        db_unit: str = "tUSD",
        input_default_unit: str = "tUSD",
    ) -> None:
        self.company_id = company_id
        self.db_unit = db_unit
        self.input_default_unit = input_default_unit
        self._formula_engine = FormulaEngine()

    def convert_value(
        self,
        value: Any,
        source_unit: Optional[str] = None,
    ) -> Optional[float]:
        """Конвертировать значение в единицы БД."""
        if value is None or value == "":
            return None
        try:
            v = float(value)
        except (TypeError, ValueError):
            return None
        unit = source_unit or self.input_default_unit
        scale = unit_scale_factor(unit, self.db_unit)
        return v * scale

    def check_coverage(
        self,
        loaded_metrics: Set[str],
        statement: str,
    ) -> List[str]:
        """Проверить покрытие обязательных метрик."""
        required = self.REQUIRED_METRICS.get(statement.upper(), [])
        return [m for m in required if m not in loaded_metrics]

    def sort_mappings(self, mappings: List[RowMapping]) -> List[RowMapping]:
        """Топологически отсортировать маппинги с учётом формул."""
        return self._formula_engine.build_dag(mappings)


# ─── helpers ──────────────────────────────────────────────────────────────────

def _infer_statement(sheet_name: str) -> str:
    """Определить тип отчёта по имени листа."""
    name = sheet_name.lower()
    if "history_is" in name or name == "is":
        return "IS"
    if "history_bs" in name or name == "bs":
        return "BS"
    if "history_cf" in name or name == "cf":
        return "CF"
    return "canonical"
