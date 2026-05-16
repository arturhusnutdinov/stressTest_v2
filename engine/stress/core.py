"""
Стресс-тестирование v2.

Архитектура:
  1. Загружаем base прогноз из forecast_is/bs/cf
  2. Применяем шоки (macro_shocks + driver_shocks)
  3. Пересчитываем модель с модифицированными входными данными
  4. Сохраняем результаты в stress_results

Типы шоков:
  macro_shocks  — шоки макро-факторов (HRC, brent, GDP)
                  → пересчитывает macro_forecasts → пересчитывает модель
  driver_shocks — шоки драйверов (cogs_pct, dso_days, capex_pct)
                  → напрямую модифицирует ModelConfig перед прогоном

Наследование: extends: base_scenario → берём base как отправную точку.
Sector packs: готовые наборы шоков для отраслей.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# ── Sector Packs — готовые наборы шоков ────────────────────────────────────────

SECTOR_PACKS: Dict[str, Dict] = {
    "metals_mining": {
        "description": "Steel/Metals downturn",
        "macro_shocks": {
            "steel_price_hrc":      {"type": "percentage", "value": -25.0},
            "steel_ppi_iron_steel": {"type": "percentage", "value": -15.0},
            "brent":                {"type": "percentage", "value": -20.0},
        },
        "driver_shocks": {
            "capex_pct": {"type": "percentage", "value": -30.0},
        },
    },
    "recession": {
        "description": "General economic recession",
        "macro_shocks": {
            "gdp_us":   {"type": "percentage", "value": -3.0},
            "cpi_us":   {"type": "percentage", "value": -1.0},
            "brent":    {"type": "percentage", "value": -30.0},
        },
        "driver_shocks": {
            "dso_days": {"type": "percentage", "value": +20.0},
            "dih_days": {"type": "percentage", "value": +15.0},
        },
    },
    "liquidity_crisis": {
        "description": "Liquidity crunch — WC stress + rate spike",
        "macro_shocks": {},
        "driver_shocks": {
            "dso_days":  {"type": "percentage", "value": +30.0},
            "dih_days":  {"type": "percentage", "value": +20.0},
            "dpo_days":  {"type": "percentage", "value": -15.0},
            "avg_rate":  {"type": "pp",         "value": +2.0},  # +2pp = +200bp
        },
    },
}


# ── Dataclasses ─────────────────────────────────────────────────────────────────

@dataclass
class ShockSpec:
    """Спецификация одного шока."""
    factor: str
    shock_type: str   # percentage | absolute
    value: float      # значение шока
    start_year: Optional[int] = None
    duration: Optional[int] = None  # None = все годы прогноза

    def apply(self, base_value: float, year: int, base_year: int) -> float:
        """Применить шок к базовому значению."""
        if self.start_year and year < self.start_year:
            return base_value
        if self.duration and (year - (self.start_year or base_year)) >= self.duration:
            return base_value
        if self.shock_type == "percentage":
            return base_value * (1.0 + self.value / 100.0)
        elif self.shock_type == "absolute":
            return base_value + self.value
        elif self.shock_type == "basis_points":
            # 100bp = 1% = 0.01 в decimal
            return base_value + self.value / 10000.0
        elif self.shock_type == "pp":
            # percentage points — прямое прибавление к decimal ставке
            return base_value + self.value / 100.0
        return base_value


@dataclass
class StressScenario:
    """Полный стресс-сценарий."""
    name: str
    description: str = ""
    extends: Optional[str] = None
    macro_shocks: List[ShockSpec] = field(default_factory=list)
    driver_shocks: List[ShockSpec] = field(default_factory=list)
    sector_packs: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, name: str, cfg: Dict) -> "StressScenario":
        """Создаёт StressScenario из YAML-словаря."""
        macro_shocks = []
        for factor, spec in cfg.get("macro_shocks", {}).items():
            macro_shocks.append(ShockSpec(
                factor=factor,
                shock_type=spec.get("type", "percentage"),
                value=float(spec.get("value", 0)),
                start_year=spec.get("start_year"),
                duration=spec.get("duration"),
            ))

        driver_shocks = []
        for driver, spec in cfg.get("driver_shocks", {}).items():
            driver_shocks.append(ShockSpec(
                factor=driver,
                shock_type=spec.get("type", "percentage"),
                value=float(spec.get("value", 0)),
                start_year=spec.get("start_year"),
                duration=spec.get("duration"),
            ))

        return cls(
            name=name,
            description=cfg.get("description", ""),
            extends=cfg.get("extends"),
            macro_shocks=macro_shocks,
            driver_shocks=driver_shocks,
            sector_packs=cfg.get("sector_packs", []),
        )

    def expand_sector_packs(self) -> "StressScenario":
        """Разворачивает sector_packs в конкретные шоки."""
        for pack_name in self.sector_packs:
            pack = SECTOR_PACKS.get(pack_name, {})
            for factor, spec in pack.get("macro_shocks", {}).items():
                # Не перезаписываем явно заданные шоки
                if not any(s.factor == factor for s in self.macro_shocks):
                    self.macro_shocks.append(ShockSpec(
                        factor=factor,
                        shock_type=spec.get("type", "percentage"),
                        value=float(spec.get("value", 0)),
                    ))
            for driver, spec in pack.get("driver_shocks", {}).items():
                if not any(s.factor == driver for s in self.driver_shocks):
                    self.driver_shocks.append(ShockSpec(
                        factor=driver,
                        shock_type=spec.get("type", "percentage"),
                        value=float(spec.get("value", 0)),
                    ))
        return self


@dataclass
class StressResult:
    """Результат стресс-теста."""
    scenario_name: str
    company_id: str
    base_scenario: str
    success: bool = False
    errors: List[str] = field(default_factory=list)
    # Сравнение base vs stress по годам
    comparison: Dict[int, Dict[str, float]] = field(default_factory=dict)
    # {year: {metric: stress_value}}
    stress_values: Dict[int, Dict[str, float]] = field(default_factory=dict)
    # BS/CF balance diffs from the stress model run
    bs_diffs: Dict[int, float] = field(default_factory=dict)
    cf_diffs: Dict[int, float] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Стресс: {self.scenario_name} / {self.company_id}",
            f"  Статус: {'OK' if self.success else 'FAIL'}",
            f"  Годов:  {len(self.stress_values)}",
        ]
        if self.comparison:
            first_year = min(self.comparison.keys())
            c = self.comparison[first_year]
            lines.append(
                f"  {first_year}: Rev={c.get('revenue_delta_pct', 0):+.1f}%  "
                f"NI={c.get('ni_delta_pct', 0):+.1f}%  "
                f"EBITDA={c.get('ebitda_delta_pct', 0):+.1f}%"
            )
        if self.errors:
            lines += [f"  x {e}" for e in self.errors[:3]]
        return "\n".join(lines)


# ── ScenarioLoader ───────────────────────────────────────────────────────────────

class ScenarioLoader:
    """Загружает стресс-сценарии из YAML."""

    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path
        self._scenarios: Dict[str, StressScenario] = {}
        self._loaded = False

    def load(self) -> Dict[str, StressScenario]:
        if self._loaded:
            return self._scenarios

        if self.config_path and self.config_path.exists():
            import yaml
            with open(self.config_path) as f:
                cfg = yaml.safe_load(f) or {}

            for name, scenario_cfg in cfg.get("scenarios", {}).items():
                scenario = StressScenario.from_dict(name, scenario_cfg)
                scenario.expand_sector_packs()
                self._scenarios[name] = scenario
                logger.debug(
                    f"Загружен сценарий: {name} "
                    f"({len(scenario.macro_shocks)} macro, "
                    f"{len(scenario.driver_shocks)} driver shocks)"
                )

        # Добавляем встроенные сценарии если нет в YAML
        self._add_builtin_scenarios()
        self._resolve_extends()
        self._loaded = True
        return self._scenarios

    def _add_builtin_scenarios(self):
        """Встроенные сценарии всегда доступны."""
        builtins = {
            "steel_downturn": {
                "description": "Steel price normalization (HRC -25%)",
                "macro_shocks": {
                    "steel_price_hrc": {"type": "percentage", "value": -25.0},
                    "steel_ppi_iron_steel": {"type": "percentage", "value": -15.0},
                },
                "sector_packs": ["metals_mining"],
            },
            "rate_spike": {
                "description": "Interest rate +200bp",
                "driver_shocks": {
                    "avg_rate": {"type": "pp", "value": +2.0},  # +2pp = +200bp
                },
            },
            "wc_stress": {
                "description": "Working capital stress (DSO+30%, DPO-15%)",
                "sector_packs": ["liquidity_crisis"],
            },
            "combined_stress": {
                "description": "Steel downturn + liquidity stress",
                "extends": "steel_downturn",
                "sector_packs": ["liquidity_crisis"],
            },
        }
        for name, cfg in builtins.items():
            if name not in self._scenarios:
                scenario = StressScenario.from_dict(name, cfg)
                scenario.expand_sector_packs()
                self._scenarios[name] = scenario

    def _resolve_extends(self):
        """Разворачивает наследование сценариев."""
        for scenario in self._scenarios.values():
            if scenario.extends and scenario.extends in self._scenarios:
                parent = self._scenarios[scenario.extends]
                # Добавляем шоки родителя если не перекрыты
                for shock in parent.macro_shocks:
                    if not any(s.factor == shock.factor for s in scenario.macro_shocks):
                        scenario.macro_shocks.append(shock)
                for shock in parent.driver_shocks:
                    if not any(s.factor == shock.factor for s in scenario.driver_shocks):
                        scenario.driver_shocks.append(shock)

    def get(self, name: str) -> Optional[StressScenario]:
        return self.load().get(name)

    def list_scenarios(self) -> List[str]:
        return list(self.load().keys())
