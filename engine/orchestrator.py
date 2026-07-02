"""
Оркестратор — единая точка входа для построения модели.
Вызывает препроцессор → модель → сохранение → downstream модули.
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .database.repository import Repository
from .preprocessor.core import ModelPreprocessor, PreprocessResult
from .model.loader import ModelInputLoader
from .model.core import ThreeStatementModel, ModelResult
from .model.saver import ModelSaver
from .macro.runner import run_macro as _run_macro, MacroResult
from .stress.runner import StressRunner
from .stress.core import StressResult
from .rating.runner import RatingRunner, RatingResult
from .covenants.core import CovenantsChecker, STEEL_COVENANTS

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    """Итог полного прогона build_model()."""
    company_id:    str
    scenario_name: str
    success:       bool = False
    errors:        List[str] = field(default_factory=list)
    warnings:      List[str] = field(default_factory=list)
    timings:       Dict[str, float] = field(default_factory=dict)
    rows_written:  int = 0
    # Промежуточные результаты
    preprocess_result: Optional[PreprocessResult] = None
    macro_result:      Optional[MacroResult] = None
    model_result:      Optional[ModelResult] = None
    stress_results:    Dict[str, Any] = field(default_factory=dict)
    rating_result:     Optional[Any] = None
    covenants_result:  Optional[Any] = None

    def summary(self) -> str:
        lines = [
            f"build_model: {self.company_id} / {self.scenario_name}",
            f"  Статус:  {'OK' if self.success else 'FAIL'}",
            f"  Строк:   {self.rows_written}",
        ]
        for step, t in self.timings.items():
            lines.append(f"  {step:<20} {t:.1f}s")
        if self.warnings:
            lines += [f"  ⚠ {w}" for w in self.warnings[:3]]
        if self.errors:
            lines += [f"  ✗ {e}" for e in self.errors[:3]]
        if self.model_result:
            r = self.model_result
            lines.append(f"  BS max diff: {max(r.bs_diffs.values(), default=0):.2f}")
            lines.append(f"  CF max diff: {max(r.cf_diffs.values(), default=0):.2f}")
        return "\n".join(lines)


def build_model(
    company_id:       str,
    config_path:      Optional[Path] = None,
    db_path:          Optional[Path] = None,
    scenario_name:    str = "base",
    run_preprocessor: bool = True,
    run_macro:        bool = True,
    run_model:        bool = True,
    run_stress:       bool = False,
    run_rating:       bool = False,
    run_covenants:    bool = False,
    stress_scenarios: Optional[List[str]] = None,  # None = все встроенные
    log_level:        int  = logging.INFO,
) -> BuildResult:
    """
    Full pipeline: preprocessor → macro → model → stress → rating → covenants.

    Args:
        company_id: Company identifier in the database (e.g. 'us_steel', 'rusal').
        config_path: Path to project.yaml. Defaults to companies/{company_id}/configs/project.yaml.
        db_path: Path to SQLite database. Defaults to data_mart_v2.db in project root.
        scenario_name: Scenario name (default: 'base').
        run_preprocessor: Recompute driver metrics from historical data.
        run_macro: Run VECM/ARIMA macro-economic forecasts.
        run_model: Run the three-statement model solver.
        run_stress: Apply stress scenarios.
        run_rating: Compute credit ratings (S&P / Moody's / Fitch).
        run_covenants: Check covenant compliance.
        stress_scenarios: List of scenario names to run (None = all from YAML).
        log_level: Python logging level.

    Returns:
        BuildResult with per-step results, timings, and BS/CF diffs.
    """
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s %(levelname)s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    result = BuildResult(company_id=company_id, scenario_name=scenario_name)
    t0_total = time.time()

    # Разрешаем пути
    from engine import ROOT as root

    if db_path is None:
        db_path = root / "data_mart_v2.db"

    if config_path is None:
        config_path = root / "companies" / company_id / "configs" / "project.yaml"

    if not db_path.exists():
        result.errors.append(f"БД не найдена: {db_path}")
        return result

    logger.info(f"{'='*60}")
    logger.info(f"build_model: {company_id} / {scenario_name}")
    logger.info(f"  БД:     {db_path}")
    logger.info(f"  Config: {config_path}")
    logger.info(f"{'='*60}")

    try:
        with Repository(db_path=db_path) as repo:

            # ── 1. Препроцессор ───────────────────────────────────────────
            if run_preprocessor:
                t0 = time.time()
                logger.info("▶ Препроцессор...")
                pp = ModelPreprocessor(company_id, repo)
                pp_result = pp.run()
                result.preprocess_result = pp_result
                result.timings["preprocessor"] = time.time() - t0

                if not pp_result.success:
                    result.errors += pp_result.errors
                    logger.error(f"  Препроцессор завершился с ошибками: {pp_result.errors}")
                else:
                    logger.info(
                        f"  OK: {len(pp_result.groups_computed)} групп, "
                        f"{pp_result.metrics_written} метрик"
                    )

            # ── 1b. Макро-прогноз ──────────────────────────────────────────
            if run_macro:
                t0 = time.time()
                logger.info("▶ Макро-прогноз...")
                # macro_ecm.yaml: check forecast/ subdirectory first, then configs/ directly
                _macro_forecast = config_path.parent / "forecast" / "macro_ecm.yaml"
                _macro_direct = config_path.parent / "macro_ecm.yaml"
                macro_cfg = (
                    _macro_forecast if _macro_forecast.exists()
                    else _macro_direct if _macro_direct.exists()
                    else None
                )
                macro_result = _run_macro(
                    company_id=company_id,
                    repo=repo,
                    config_path=macro_cfg,
                    scenario_name=scenario_name,
                    forecast_years=(
                        5  # будет обновлено из config после загрузки
                    ),
                )
                result.macro_result = macro_result
                result.timings["macro"] = time.time() - t0
                if macro_result.success:
                    logger.info(
                        f"  OK: {len(macro_result.factors_forecast)} факторов, "
                        f"методы: {set(macro_result.methods_used.values())}"
                    )
                else:
                    result.errors += macro_result.errors
                    logger.error(f"  ✗ Макро: {macro_result.errors}")

            # ── 2. Модель ─────────────────────────────────────────────────
            if run_model:
                t0 = time.time()
                logger.info("▶ Загрузка входных данных...")

                loader = ModelInputLoader(
                    company_id=company_id,
                    repo=repo,
                    config_path=config_path if config_path.exists() else None,
                    scenario_name=scenario_name,
                )
                historic, config = loader.load()

                logger.info(f"  История: {historic.years[0]}–{historic.base_year}")
                logger.info(f"  Прогноз: {config.forecast_start_year}–{config.forecast_end_year}")
                logger.info(f"  Debt mode: {config.debt.mode}")
                logger.info(f"  Инструментов: {len(historic.debt_instruments)}")

                logger.info("▶ Построение модели...")
                model = ThreeStatementModel(historic, config)
                model_result = model.run()
                result.model_result = model_result
                result.timings["model"] = time.time() - t0

                if not model_result.success:
                    result.errors += model_result.errors
                    logger.error(f"  Модель завершилась с ошибками: {model_result.errors}")
                else:
                    bs_max = max(model_result.bs_diffs.values(), default=0)
                    cf_max = max(model_result.cf_diffs.values(), default=0)
                    logger.info(
                        f"  OK: {len(model_result.years)} лет, "
                        f"BS_max={bs_max:.2f}, CF_max={cf_max:.2f}"
                    )
                    if model_result.warnings:
                        result.warnings += model_result.warnings

                # ── Сохранение ────────────────────────────────────────────
                if model_result.success:
                    t0 = time.time()
                    logger.info("▶ Сохранение результатов...")
                    saver = ModelSaver(company_id, repo, config)
                    rows = saver.save(model_result)
                    result.rows_written = rows
                    result.timings["save"] = time.time() - t0
                    logger.info(f"  OK: {rows} строк записано в БД")

                    # Краткая таблица результатов
                    logger.info("")
                    logger.info(
                        f"  {'Год':<6} {'Rev$B':>7} {'EBITDA%':>8} "
                        f"{'NI$M':>7} {'BS_diff':>8} {'CF_diff':>8}"
                    )
                    for yr, state in sorted(model_result.years.items()):
                        _, _, bs_d = state.bs_check()
                        _, _, cf_d = state.cf_bridge_check()
                        logger.info(
                            f"  {yr:<6} {state.revenue/1e9:>7.2f} "
                            f"{state.ebitda/state.revenue*100:>7.1f}% "
                            f"{state.net_income/1e6:>7.0f} "
                            f"{bs_d:>8.2f} {cf_d:>8.2f}"
                        )

            # ── 3. Downstream ─────────────────────────────────────────────
            # ── 4. Стресс-тестирование ────────────────────────────────────
            if run_stress and result.model_result and result.model_result.success:
                t0 = time.time()
                logger.info("▶ Стресс-тестирование...")
                try:
                    stress_cfg_path = (
                        config_path.parent / "stress_scenarios.yaml"
                        if config_path and config_path.exists() else None
                    )
                    stress_runner = StressRunner(
                        company_id=company_id,
                        repo=repo,
                        config_path=config_path if config_path and config_path.exists() else None,
                        stress_config_path=stress_cfg_path if stress_cfg_path and stress_cfg_path.exists() else None,
                    )
                    # Use explicit list, or read from company stress_scenarios.yaml, or defaults
                    if stress_scenarios:
                        scenarios_to_run = stress_scenarios
                    elif stress_cfg_path and stress_cfg_path.exists():
                        import yaml as _yaml
                        with open(stress_cfg_path) as _sf:
                            _sc = _yaml.safe_load(_sf) or {}
                        scenarios_to_run = list((_sc.get("scenarios") or {}).keys())
                    else:
                        scenarios_to_run = ["steel_downturn", "rate_spike", "wc_stress"]
                    stress_results = {}
                    for sc_name in scenarios_to_run:
                        sc_result = stress_runner.run(sc_name, base_scenario=scenario_name)
                        stress_results[sc_name] = sc_result
                        if sc_result.success and sc_result.comparison:
                            c = sc_result.comparison.get(min(sc_result.comparison.keys()), {})
                            logger.info(
                                f"  {sc_name}: Rev={c.get('revenue_delta_pct', 0):+.1f}% "
                                f"NI={c.get('ni_delta_pct', 0):+.1f}%"
                            )
                        else:
                            logger.warning(f"  {sc_name}: {sc_result.errors}")
                    result.stress_results = stress_results
                    result.timings["stress"] = time.time() - t0
                    n_ok = sum(1 for r in stress_results.values() if r.success)
                    logger.info(f"  OK: {n_ok}/{len(stress_results)} сценариев")
                except Exception as e:
                    result.warnings.append(f"Стресс: {e}")
                    logger.warning(f"  ⚠ Стресс: {e}")

            if run_rating and result.model_result and result.model_result.success:
                t0 = time.time()
                logger.info("▶ Рейтинг...")
                try:
                    company_dir = (db_path.parent / "companies" / company_id
                                   if db_path else Path("companies") / company_id)
                    rating_runner = RatingRunner.from_project_yaml(company_id, repo, company_dir)
                    rating_result = rating_runner.rate_model_result(
                        result.model_result,
                        rating_type=scenario_name,
                        save=True,
                    )
                    result.rating_result = rating_result
                    result.timings["rating"] = time.time() - t0
                    if rating_result.success:
                        logger.info(
                            f"  OK: {rating_result.best_rating()} → {rating_result.worst_rating()}"
                        )
                        logger.info(result.rating_result.summary())
                    else:
                        result.warnings += rating_result.errors
                        logger.warning(f"  ⚠ Рейтинг: {rating_result.errors}")
                except Exception as e:
                    result.warnings.append(f"Рейтинг: {e}")
                    logger.warning(f"  ⚠ Рейтинг: {e}")

            if run_covenants and result.model_result and result.model_result.success:
                t0 = time.time()
                logger.info("▶ Проверка ковенантов...")
                try:
                    company_dir = (db_path.parent / "companies" / company_id
                                   if db_path else Path("companies") / company_id)
                    checker = CovenantsChecker.from_project_yaml(company_id, repo, company_dir)
                    cov_result = checker.check(result.model_result, scenario_name, save=True)
                    result.covenants_result = cov_result
                    breaches = cov_result.breaches()
                    warnings_cov = cov_result.warnings()
                    result.timings["covenants"] = time.time() - t0
                    logger.info(f"  OK: нарушений={len(breaches)} предупреждений={len(warnings_cov)}")
                    if breaches:
                        for b in breaches[:3]:
                            logger.warning(f"  ✗ {b.year} {b.covenant_name}: {b.value:.2f} (лимит {b.threshold:.2f})")
                    if cov_result.first_breach_year():
                        result.warnings.append(f"Первое нарушение ковенанта: {cov_result.first_breach_year()}")

                    # ── Auto-trigger covenant_breach stress scenario ──────────
                    # auto-trigger: when breach_years detected, re-run model with covenant stress
                    breach_years = [b.year for b in breaches]
                    if breach_years and run_stress and "covenant_breach" not in result.stress_results:
                        logger.warning(
                            f"  → Covenant breach detected in {breach_years} — auto-running covenant_breach stress"
                        )
                        try:
                            stress_cfg_path = (
                                config_path.parent / "stress_scenarios.yaml"
                                if config_path and config_path.exists() else None
                            )
                            _breach_runner = StressRunner(
                                company_id=company_id,
                                repo=repo,
                                config_path=config_path if config_path and config_path.exists() else None,
                                stress_config_path=stress_cfg_path if stress_cfg_path and stress_cfg_path.exists() else None,
                            )
                            breach_sc = _breach_runner.run("covenant_breach", base_scenario=scenario_name)
                            result.stress_results["covenant_breach"] = breach_sc
                            if breach_sc.success and breach_sc.comparison:
                                c = breach_sc.comparison.get(min(breach_sc.comparison.keys()), {})
                                logger.warning(
                                    f"  covenant_breach: Rev={c.get('revenue_delta_pct', 0):+.1f}% "
                                    f"NI={c.get('ni_delta_pct', 0):+.1f}%"
                                )
                        except Exception as _be:
                            logger.warning(f"  ⚠ covenant_breach stress failed: {_be}")

                except Exception as e:
                    result.warnings.append(f"Ковенанты: {e}")
                    logger.warning(f"  ⚠ Ковенанты: {e}")

    except Exception as e:
        result.errors.append(str(e))
        logger.exception(f"Критическая ошибка: {e}")

    result.timings["total"] = time.time() - t0_total
    result.success = len(result.errors) == 0

    logger.info("")
    logger.info(result.summary())
    return result


# ── CLI ────────────────────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Построить финансовую модель")
    parser.add_argument("company", help="ID компании (например: us_steel)")
    parser.add_argument("--scenario", default="base", help="Имя сценария")
    parser.add_argument("--no-preprocess", action="store_true")
    parser.add_argument("--no-macro", action="store_true")
    parser.add_argument("--no-model", action="store_true")
    parser.add_argument("--stress", action="store_true")
    parser.add_argument("--rating", action="store_true")
    parser.add_argument("--covenants", action="store_true")
    parser.add_argument("--db", help="Путь к БД")
    parser.add_argument("--config", help="Путь к project.yaml")
    args = parser.parse_args()

    res = build_model(
        company_id=args.company,
        scenario_name=args.scenario,
        db_path=Path(args.db) if args.db else None,
        config_path=Path(args.config) if args.config else None,
        run_preprocessor=not args.no_preprocess,
        run_macro=not args.no_macro,
        run_model=not args.no_model,
        run_stress=args.stress,
        run_rating=args.rating,
        run_covenants=args.covenants,
    )
    exit(0 if res.success else 1)


if __name__ == "__main__":
    main()
