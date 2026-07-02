"""
Ковенанты v2.

Проверяет финансовые ковенанты по прогнозным данным.
Поддерживает: Leverage, Coverage, Liquidity, Profitability ковенанты.
Конфигурируется через YAML или программно.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from engine.rating.core import CreditMetrics

logger = logging.getLogger(__name__)


# ── Типы ковенантов ─────────────────────────────────────────────────────────────

@dataclass
class CovenantSpec:
    """Спецификация одного ковенанта."""
    name: str
    metric: str           # имя метрики из CreditMetrics
    bound: str            # max | min
    threshold: float      # пороговое значение
    warning_buffer: float = 0.10  # предупреждение за 10% до нарушения
    description: str = ""

    def check(self, value: Optional[float]) -> Tuple[str, float]:
        """
        Проверяет ковенант.
        Returns: (status, headroom)
            status: 'ok' | 'warning' | 'breach'
            headroom: запас до нарушения (отрицательный = нарушение)
        """
        if value is None:
            return "na", 0.0

        if self.bound == "max":
            headroom = (self.threshold - value) / abs(self.threshold) if self.threshold else 0
            if value > self.threshold:
                return "breach", headroom
            elif value > self.threshold * (1 - self.warning_buffer):
                return "warning", headroom
            return "ok", headroom

        elif self.bound == "min":
            headroom = (value - self.threshold) / abs(self.threshold) if self.threshold else 0
            if value < self.threshold:
                return "breach", headroom
            elif value < self.threshold * (1 + self.warning_buffer):
                return "warning", headroom
            return "ok", headroom

        return "na", 0.0


@dataclass
class CovenantResult:
    """Результат проверки одного ковенанта за один год."""
    year: int
    covenant_name: str
    metric: str
    value: Optional[float]
    threshold: float
    bound: str
    status: str      # ok | warning | breach | na
    headroom: float
    description: str = ""


@dataclass
class CovenantsCheckResult:
    """Результат проверки всех ковенантов."""
    company_id: str
    scenario_name: str
    success: bool = False
    errors: List[str] = field(default_factory=list)
    results: List[CovenantResult] = field(default_factory=list)

    def breaches(self) -> List[CovenantResult]:
        return [r for r in self.results if r.status == "breach"]

    def warnings(self) -> List[CovenantResult]:
        return [r for r in self.results if r.status == "warning"]

    def summary(self) -> str:
        breaches = self.breaches()
        warnings = self.warnings()
        lines = [
            f"Ковенанты: {self.company_id} / {self.scenario_name}",
            f"  Статус:    {'OK' if self.success else 'FAIL'}",
            f"  Нарушений: {len(breaches)}",
            f"  Предупрежд: {len(warnings)}",
        ]
        if breaches:
            lines.append("  Нарушения:")
            for r in breaches[:5]:
                lines.append(f"    {r.year} {r.covenant_name}: {r.value:.2f} {'>' if r.bound=='max' else '<'} {r.threshold:.2f}")
        if warnings:
            lines.append("  Предупреждения:")
            for r in warnings[:3]:
                lines.append(f"    {r.year} {r.covenant_name}: {r.value:.2f} (лимит {r.threshold:.2f})")
        return "\n".join(lines)

    def first_breach_year(self) -> Optional[int]:
        """Первый год нарушения ковенантов."""
        breach_years = [r.year for r in self.breaches()]
        return min(breach_years) if breach_years else None


# ── Стандартные ковенанты ────────────────────────────────────────────────────────

DEFAULT_COVENANTS = [
    CovenantSpec("Net Debt/EBITDA",  "net_debt_ebitda",   "max", 4.0,  0.10, "Leverage covenant"),
    CovenantSpec("Interest Coverage","interest_coverage",  "min", 2.0,  0.15, "ICR covenant (EBIT/Int)"),
    CovenantSpec("Debt/Equity",      "debt_to_equity",     "max", 3.0,  0.10, "Gearing covenant"),
    CovenantSpec("Current Ratio",    "current_ratio",      "min", 1.0,  0.10, "Liquidity covenant"),
]

# Ковенанты для стальной отрасли (более жёсткие)
# NOTE: used as default when project.yaml doesn't specify covenants and industry is metals/steel/mining
STEEL_COVENANTS = [
    CovenantSpec("Net Debt/EBITDA",  "net_debt_ebitda",   "max", 3.5,  0.10, "Steel industry leverage"),
    CovenantSpec("Interest Coverage","interest_coverage",  "min", 2.5,  0.15, "Steel ICR"),
    CovenantSpec("EBITDA Margin",    "ebitda_margin",      "min", 0.05, 0.20, "Min EBITDA margin 5%"),
    CovenantSpec("Current Ratio",    "current_ratio",      "min", 1.0,  0.10, "Liquidity"),
    CovenantSpec("FCF/Debt",         "fcf_to_debt",        "min", -0.10,0.0,  "FCF floor"),
]


class CovenantsChecker:
    """Проверяет ковенанты по прогнозным данным."""

    def __init__(
        self,
        company_id: str,
        repo,
        covenants: Optional[List[CovenantSpec]] = None,
        acceleration_triggers: Optional[List[str]] = None,
    ):
        self.company_id = company_id
        self._repo = repo
        self._covenants = covenants or DEFAULT_COVENANTS
        # acceleration_triggers: metrics whose breach triggers callable_flag acceleration
        self.acceleration_triggers = acceleration_triggers or []

    @classmethod
    def from_yaml(cls, company_id: str, repo, config_path) -> "CovenantsChecker":
        """Загружает ковенанты из YAML."""
        try:
            import yaml
            from pathlib import Path
            path = Path(config_path)
            if not path.exists():
                return cls(company_id, repo)
            with open(path) as f:
                cfg = yaml.safe_load(f) or {}
            covenants = []
            for name, spec in cfg.get("covenants", {}).items():
                covenants.append(CovenantSpec(
                    name=name,
                    metric=spec["metric"],
                    bound=spec.get("bound", "max"),
                    threshold=float(spec["threshold"]),
                    warning_buffer=float(spec.get("warning_buffer", 0.10)),
                    description=spec.get("description", ""),
                ))
            return cls(company_id, repo, covenants or None)
        except Exception as e:
            logger.debug(f"YAML ковенанты: {e}, используем дефолтные")
            return cls(company_id, repo)

    @classmethod
    def from_project_yaml(cls, company_id: str, repo, company_dir) -> "CovenantsChecker":
        """
        Загружает ковенанты из configs компании.
        Порядок приоритета:
        1. covenants.yaml (кастомные ковенанты)
        2. project.yaml секция covenants.thresholds
        3. Отраслевые дефолты (STEEL_COVENANTS для metals)
        4. DEFAULT_COVENANTS
        """
        import yaml
        from pathlib import Path
        company_dir = Path(company_dir)

        # 1. Пробуем covenants.yaml
        cov_path = company_dir / "configs" / "covenants.yaml"
        if cov_path.exists():
            checker = cls.from_yaml(company_id, repo, cov_path)
            if checker._covenants:
                return checker

        # 2. Читаем из project.yaml секция covenants
        proj_path = company_dir / "configs" / "project.yaml"
        if proj_path.exists():
            with open(proj_path) as f:
                cfg = yaml.safe_load(f) or {}

            cov_cfg = cfg.get("covenants", {})
            if not cov_cfg.get("enabled", True):
                return cls(company_id, repo, [])  # ковенанты отключены

            thresholds = cov_cfg.get("thresholds", {})
            warning_buffer = cov_cfg.get("warning_buffer", 0.10)

            # Методология
            methodology = cov_cfg.get("methodology", "default")
            if methodology == "steel":
                covenants = list(STEEL_COVENANTS)
            else:
                covenants = list(DEFAULT_COVENANTS)

            # Переопределяем пороги из project.yaml
            THRESHOLD_MAP = {
                "net_debt_ebitda_max":   ("Net Debt/EBITDA",   "net_debt_ebitda",   "max"),
                "interest_coverage_min": ("Interest Coverage",  "interest_coverage", "min"),
                "debt_to_equity_max":    ("Debt/Equity",        "debt_to_equity",    "max"),
                "current_ratio_min":     ("Current Ratio",      "current_ratio",     "min"),
                "ebitda_margin_min":     ("EBITDA Margin",      "ebitda_margin",     "min"),
                "fcf_to_debt_min":       ("FCF/Debt",           "fcf_to_debt",       "min"),
            }
            for threshold_key, val in thresholds.items():
                if val is None:
                    continue
                mapping = THRESHOLD_MAP.get(threshold_key)
                if mapping:
                    label, metric, bound = mapping
                    existing = next((c for c in covenants if c.metric == metric), None)
                    if existing:
                        existing.threshold = float(val)
                        existing.warning_buffer = warning_buffer
                    else:
                        covenants.append(CovenantSpec(
                            name=label, metric=metric, bound=bound,
                            threshold=float(val), warning_buffer=warning_buffer,
                        ))

            # acceleration_triggers from YAML (metrics whose breach accelerates callable debt)
            accel_triggers = cov_cfg.get("acceleration_triggers", [])

            # Отраслевые дефолты из company — если пороги не были заданы в YAML,
            # используем steel covenants как базу и накладываем YAML-переопределения
            industry = cfg.get("company", {}).get("industry", "")
            if industry in ("metals", "steel", "mining") and methodology == "default":
                if not thresholds:
                    # Нет пользовательских порогов — чистые steel defaults
                    return cls(company_id, repo, STEEL_COVENANTS,
                               acceleration_triggers=accel_triggers)
                # Есть пользовательские пороги — начинаем с steel и переопределяем
                steel = list(STEEL_COVENANTS)
                for threshold_key, val in thresholds.items():
                    if val is None:
                        continue
                    mapping = THRESHOLD_MAP.get(threshold_key)
                    if mapping:
                        label, metric, bound = mapping
                        existing = next((c for c in steel if c.metric == metric), None)
                        if existing:
                            existing.threshold = float(val)
                            existing.warning_buffer = warning_buffer
                        else:
                            steel.append(CovenantSpec(
                                name=label, metric=metric, bound=bound,
                                threshold=float(val), warning_buffer=warning_buffer,
                            ))
                return cls(company_id, repo, steel,
                           acceleration_triggers=accel_triggers)

            return cls(company_id, repo, covenants,
                       acceleration_triggers=accel_triggers)

        return cls(company_id, repo)  # дефолтные ковенанты

    def check(
        self,
        model_result,
        scenario_name: str = "base",
        save: bool = True,
    ) -> CovenantsCheckResult:
        """
        Проверяет ковенанты по всем прогнозным годам.

        Args:
            model_result: результат ThreeStatementModel.run()
            scenario_name: имя сценария
            save: сохранить в БД
        """
        result = CovenantsCheckResult(
            company_id=self.company_id,
            scenario_name=scenario_name,
        )

        try:
            for yr, state in sorted(model_result.years.items()):
                metrics = CreditMetrics.from_year_state(state, yr)
                for cov in self._covenants:
                    value = getattr(metrics, cov.metric, None)
                    status, headroom = cov.check(value)
                    result.results.append(CovenantResult(
                        year=yr,
                        covenant_name=cov.name,
                        metric=cov.metric,
                        value=value,
                        threshold=cov.threshold,
                        bound=cov.bound,
                        status=status,
                        headroom=headroom,
                        description=cov.description,
                    ))

            if save:
                self._save(result)

            result.success = True

        except Exception as e:
            result.errors.append(str(e))
            logger.exception(f"Ошибка ковенантов: {e}")

        return result

    def check_year(self, state, year: int) -> Dict[str, CovenantResult]:
        """
        Проверяет ковенанты для одного YearState (используется внутри итерационного
        цикла модели для определения covenant acceleration).

        Returns: dict keyed by CovenantSpec.metric (e.g. 'interest_coverage')
        """
        metrics = CreditMetrics.from_year_state(state, year)
        results: Dict[str, CovenantResult] = {}
        for cov in self._covenants:
            value = getattr(metrics, cov.metric, None)
            status, headroom = cov.check(value)
            results[cov.metric] = CovenantResult(
                year=year,
                covenant_name=cov.name,
                metric=cov.metric,
                value=value,
                threshold=cov.threshold,
                bound=cov.bound,
                status=status,
                headroom=headroom,
                description=cov.description,
            )
        return results

    # NOTE: reserved for future covenant acceleration implementation
    def get_acceleration_breach_instruments(
        self, state, year: int, debt_instruments: list
    ) -> set:
        """
        Returns set of instrument_ids with callable_flag that should be accelerated
        due to acceleration_triggers breach in the given year.
        """
        if not self.acceleration_triggers:
            return set()
        year_results = self.check_year(state, year)
        triggered = any(
            year_results.get(metric, None) and year_results[metric].status == "breach"
            for metric in self.acceleration_triggers
        )
        if not triggered:
            return set()
        # Accelerate only instruments with callable_flag
        return {
            inst.instrument_id
            for inst in debt_instruments
            if getattr(inst, "callable_flag", False)
        }

    def _save(self, result: CovenantsCheckResult) -> None:
        try:
            import json
            self._repo.execute("""
                CREATE TABLE IF NOT EXISTS covenant_results (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    company_id   TEXT NOT NULL,
                    scenario_name TEXT NOT NULL,
                    n_breaches   INTEGER DEFAULT 0,
                    n_warnings   INTEGER DEFAULT 0,
                    first_breach_year INTEGER,
                    results_json TEXT,
                    created_at   TEXT DEFAULT (datetime('now')),
                    UNIQUE(company_id, scenario_name)
                )
            """)
            rows = [
                {
                    "year": r.year, "covenant": r.covenant_name,
                    "metric": r.metric, "value": r.value,
                    "threshold": r.threshold, "status": r.status,
                    "headroom": round(r.headroom, 4),
                }
                for r in result.results
            ]
            self._repo.execute("""
                INSERT OR REPLACE INTO covenant_results
                (company_id, scenario_name, n_breaches, n_warnings,
                 first_breach_year, results_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                self.company_id, result.scenario_name,
                len(result.breaches()), len(result.warnings()),
                result.first_breach_year(),
                json.dumps(rows),
            ))
        except Exception as e:
            logger.debug(f"Сохранение ковенантов: {e}")
