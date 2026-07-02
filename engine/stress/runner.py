"""
StressRunner — применяет шоки и пересчитывает модель.

Алгоритм:
1. Загружаем базовый прогноз (macro_forecasts + ModelConfig из base сценария)
2. Применяем macro_shocks → модифицируем macro_forecasts в БД (временно)
3. Применяем driver_shocks → модифицируем ModelConfig
4. Пересчитываем ThreeStatementModel с модифицированными входными данными
5. Сравниваем со базовым прогнозом, сохраняем результаты
"""
from __future__ import annotations

import logging
import copy
from pathlib import Path
from typing import Dict, List, Optional

from .core import StressScenario, StressResult, ScenarioLoader, ShockSpec

logger = logging.getLogger(__name__)


class StressRunner:
    """
    Запускает стресс-тестирование для одной компании.

    Пример использования:
        runner = StressRunner('us_steel', repo, config_path)
        result = runner.run('steel_downturn', base_scenario='base')
        print(result.summary())
    """

    def __init__(
        self,
        company_id: str,
        repo,
        config_path: Optional[Path] = None,
        stress_config_path: Optional[Path] = None,
    ):
        self.company_id = company_id
        self._repo = repo
        self._config_path = config_path
        self._loader = ScenarioLoader(stress_config_path)

    def list_scenarios(self) -> List[str]:
        return self._loader.list_scenarios()

    def run(
        self,
        scenario_name: str,
        base_scenario: str = "base",
        save_results: bool = True,
    ) -> StressResult:
        """
        Запустить один стресс-сценарий.

        Args:
            scenario_name: имя стресс-сценария
            base_scenario:  имя базового сценария (откуда берём прогноз)
            save_results:   сохранить результаты в БД
        """
        result = StressResult(
            scenario_name=scenario_name,
            company_id=self.company_id,
            base_scenario=base_scenario,
        )

        # Загружаем сценарий
        scenario = self._loader.get(scenario_name)
        if scenario is None:
            result.errors.append(f"Сценарий не найден: {scenario_name}")
            return result

        logger.info(f"Стресс: {scenario_name} (base={base_scenario})")
        logger.info(f"  Macro шоков: {len(scenario.macro_shocks)}")
        logger.info(f"  Driver шоков: {len(scenario.driver_shocks)}")

        try:
            # Загружаем базовый сценарий
            from engine.model.loader import ModelInputLoader
            from engine.model.core import ThreeStatementModel

            loader = ModelInputLoader(
                company_id=self.company_id,
                repo=self._repo,
                config_path=self._config_path,
                scenario_name=base_scenario,
            )
            historic, config = loader.load()

            # Базовые прогнозы для сравнения
            base_model = ThreeStatementModel(historic, config)
            base_result = base_model.run()

            if not base_result.success:
                result.errors.append(f"Базовая модель не запустилась: {base_result.errors}")
                return result

            # Применяем macro_shocks — модифицируем macro_forecasts в historic
            stressed_historic = self._apply_macro_shocks(
                historic, scenario.macro_shocks, config.forecast_years, config
            )

            # Применяем driver_shocks — модифицируем config
            stressed_config = self._apply_driver_shocks(config, scenario.driver_shocks)

            # Применяем rate шоки к debt_instruments в stressed_historic напрямую.
            # Только floating-rate инструменты: fixed-rate купоны зафиксированы
            # на дату выпуска и не реагируют на движение ставок.
            rate_shocks = [s for s in scenario.driver_shocks
                           if s.factor in ("avg_rate", "rate_spread")]
            if rate_shocks and getattr(stressed_historic, "debt_instruments", None):
                for shock in rate_shocks:
                    n = 0
                    for inst in stressed_historic.debt_instruments:
                        # Применяем шок только к floating-rate инструментам
                        if getattr(inst, "rate_type", "fixed") != "floating":
                            continue
                        cur_rate = inst.interest_rate
                        if cur_rate is None or cur_rate <= 0:
                            continue
                        if shock.shock_type in ("pp", "absolute"):
                            inst.interest_rate = max(0.001, cur_rate + shock.value / 100.0)
                        elif shock.shock_type == "basis_points":
                            inst.interest_rate = max(0.001, cur_rate + shock.value / 10000.0)
                        else:
                            inst.interest_rate = max(0.001, cur_rate * (1 + shock.value / 100.0))
                        n += 1
                    logger.info(f"  Rate shock (floating) на {n} debt instruments: +{shock.value:.1f}pp")

            # Пересчитываем модель с шоками
            stress_model = ThreeStatementModel(stressed_historic, stressed_config)
            stress_result_model = stress_model.run()

            if not stress_result_model.success:
                result.errors.append(f"Стресс-модель не запустилась: {stress_result_model.errors}")
                return result

            # Сравниваем результаты
            result.comparison = self._compare(base_result, stress_result_model)
            result.stress_values = self._extract_kpis(stress_result_model)
            result.bs_diffs = getattr(stress_result_model, 'bs_diffs', {})
            result.cf_diffs = getattr(stress_result_model, 'cf_diffs', {})

            # Сохраняем в БД
            if save_results:
                self._save_results(scenario_name, base_scenario, result, stress_result_model)

            result.success = True
            logger.info(f"  OK: {len(result.stress_values)} лет")

        except Exception as e:
            result.errors.append(str(e))
            logger.exception(f"Ошибка стресс-теста: {e}")

        return result

    def run_all(
        self,
        base_scenario: str = "base",
        scenario_names: Optional[List[str]] = None,
    ) -> Dict[str, StressResult]:
        """Запустить все (или выбранные) стресс-сценарии."""
        if scenario_names is None:
            scenario_names = self.list_scenarios()

        results = {}
        for name in scenario_names:
            logger.info(f"\n{'='*50}")
            results[name] = self.run(name, base_scenario=base_scenario)

        return results

    # ── Применение шоков ───────────────────────────────────────────────────────

    def _apply_macro_shocks(self, historic, shocks: List[ShockSpec], forecast_years, config=None) -> object:
        """
        Применяет macro_shocks к копии historic.macro_forecasts.
        Возвращает модифицированный historic (deepcopy).
        """
        stressed = copy.deepcopy(historic)

        base_year = historic.base_year
        # forecast_years может быть списком годов или целым числом горизонта
        if isinstance(forecast_years, list):
            fc_years = forecast_years
        else:
            fc_years = list(range(base_year + 1, base_year + int(forecast_years) + 1))

        for shock in shocks:
            factor = shock.factor
            if factor not in stressed.macro_forecasts:
                logger.debug(f"  Macro shock {factor}: фактор не найден в macro_forecasts")
                continue

            original = stressed.macro_forecasts[factor]
            # Сохраняем исторические значения (включая base_year) — нужны для chain-link
            modified = {yr: v for yr, v in original.items() if yr <= base_year}
            for yr in fc_years:
                base_val = original.get(yr)
                if base_val is None:
                    continue
                modified[yr] = shock.apply(base_val, yr, base_year)

            stressed.macro_forecasts[factor] = modified
            orig_first = original.get(fc_years[0], 0)
            mod_first  = modified.get(fc_years[0], 0)
            if orig_first:
                logger.info(
                    f"  Macro shock {factor}: "
                    f"{orig_first:.1f} → {mod_first:.1f} "
                    f"({(mod_first / orig_first - 1) * 100:+.1f}%)"
                )
            else:
                logger.info(f"  Macro shock {factor}: applied")

        # Если есть шок revenue-драйвера (HRC) — сбрасываем revenue в base_year_state
        # чтобы _solve_revenue пересчитал chain-link от истории, а не от base прогноза
        # Get revenue factors from project config, fallback to common set
        revenue_factors = set(getattr(config, 'revenue_macro_factors', None) or
                              getattr(config, 'macro_policy_factors', None) or
                              ["steel_price_hrc", "gdp_us", "gdp_world"])
        has_revenue_shock = any(s.factor in revenue_factors for s in shocks)
        if has_revenue_shock:
            # base_year_state.revenue остаётся историческим (2024 факт) — это правильно
            # Модель пересчитает revenue через chain-link от historic, используя шокированный HRC
            logger.info("  Revenue будет пересчитан от шокированного HRC (chain-link от истории)")

        # Прямой расчёт revenue шока от HRC если модель использует OLS beta
        hrc_shock = next((s for s in shocks if s.factor == "steel_price_hrc"), None)
        if hrc_shock:
            import math
            # Revenue beta из препроцессора (R²=0.858, beta=1.13)
            try:
                rev_betas = self._repo.get_preprocess(self.company_id, "revenue_betas") if hasattr(self, "_repo") else {}
                # Ищем beta специфично для фактора; fallback — rev_best_beta из препроцессора
                beta = rev_betas.get(f"rev_beta_{hrc_shock.factor}", {})
                if isinstance(beta, dict):
                    beta = beta.get(-1)
                if not beta:
                    best = rev_betas.get("rev_best_beta", {})
                    if isinstance(best, dict):
                        best = best.get(-1)
                    beta = float(best) if best else 1.0
                else:
                    beta = float(beta)
            except Exception:
                beta = 1.0

            hrc_shock_factor = 1.0 + hrc_shock.value / 100.0
            ln_hrc_delta = math.log(hrc_shock_factor)
            revenue_mult = math.exp(beta * ln_hrc_delta)

            logger.info(
                f"  Revenue шок: HRC {hrc_shock.value:+.1f}% × beta={beta:.2f} "
                f"→ revenue {(revenue_mult - 1) * 100:+.1f}%"
            )

            # Создаём прогноз revenue в macro_forecasts чтобы _solve_revenue его подхватил
            # Базовый revenue из прогноза
            base_rev_fc = {}
            for yr in range(2025, 2030):
                # Если есть base прогноз в БД — читаем оттуда
                pass  # оставляем пустым — _solve_revenue сам пересчитает через OLS

        return stressed

    def _apply_driver_shocks(self, config, shocks: List[ShockSpec]) -> object:
        """
        Применяет driver_shocks к копии ModelConfig.
        Поддерживаемые драйверы: cogs_pct, sga_pct, dso_days, dih_days, dpo_days,
                                  capex_pct, dep_rate, avg_rate, dividend_payout,
                                  tax_rate
        """
        stressed_cfg = copy.deepcopy(config)

        # Маппинг driver_name → атрибут ModelConfig
        DRIVER_MAP = {
            "cogs_pct":        ("cogs_pct",         1.0),
            "sga_pct":         ("sga_pct",           1.0),
            "dso_days":        ("dso_days",          1.0),
            "dih_days":        ("dih_days",          1.0),
            "dio_days":        ("dih_days",          1.0),
            "dpo_days":        ("dpo_days",          1.0),
            "capex_pct":       ("capex_pct",         1.0),
            "dep_rate":        ("dep_rate",          1.0),
            "avg_rate":        ("debt.avg_rate_pct", 1.0),
            "rate_spread":     ("debt.avg_rate_pct", 1.0),  # алиас
            "dividend_payout": ("dividend_payout",   1.0),
            "tax_rate":        ("tax_rate",          1.0),
        }

        base_year = getattr(config, "base_year", 2024)

        for shock in shocks:
            mapping = DRIVER_MAP.get(shock.factor)
            if mapping is None:
                logger.debug(f"  Driver shock {shock.factor}: нет маппинга")
                continue

            attr_path, _ = mapping

            try:
                if "." in attr_path:
                    obj_name, attr_name = attr_path.split(".", 1)
                    obj = getattr(stressed_cfg, obj_name)
                    base_val = getattr(obj, attr_name, None)
                else:
                    base_val = getattr(stressed_cfg, attr_path, None)

                if base_val is None:
                    logger.debug(f"  Driver shock {shock.factor}: значение None")
                    continue

                new_val = shock.apply(base_val, base_year + 1, base_year)

                if "." in attr_path:
                    obj_name, attr_name = attr_path.split(".", 1)
                    obj = getattr(stressed_cfg, obj_name)
                    setattr(obj, attr_name, new_val)
                else:
                    setattr(stressed_cfg, attr_path, new_val)

                logger.info(f"  Driver shock {shock.factor}: {base_val:.4f} → {new_val:.4f}")

            except Exception as e:
                logger.debug(f"  Driver shock {shock.factor}: ошибка — {e}")

        return stressed_cfg

    # ── Анализ результатов ─────────────────────────────────────────────────────

    def _compare(self, base_result, stress_result) -> Dict[int, Dict[str, float]]:
        """Сравнивает base vs stress по ключевым метрикам."""
        comparison = {}
        for yr in sorted(stress_result.years.keys()):
            base_s   = base_result.years.get(yr)
            stress_s = stress_result.years.get(yr)
            if not base_s or not stress_s:
                continue

            def pct_delta(a, b):
                return (b / a - 1) * 100 if a and abs(a) > 1e-6 else 0.0

            comparison[yr] = {
                "revenue_base":      base_s.revenue,
                "revenue_stress":    stress_s.revenue,
                "revenue_delta_pct": pct_delta(base_s.revenue, stress_s.revenue),
                "ebitda_base":       base_s.ebitda,
                "ebitda_stress":     stress_s.ebitda,
                "ebitda_delta_pct":  pct_delta(base_s.ebitda, stress_s.ebitda),
                "ni_base":           base_s.net_income,
                "ni_stress":         stress_s.net_income,
                "ni_delta_pct":      pct_delta(base_s.net_income, stress_s.net_income),
                "cash_base":         base_s.cash,
                "cash_stress":       stress_s.cash,
                "cash_delta":        stress_s.cash - base_s.cash,
                "net_debt_base":     (base_s.short_term_debt  + base_s.long_term_debt  - base_s.cash),
                "net_debt_stress":   (stress_s.short_term_debt + stress_s.long_term_debt - stress_s.cash),
                "bs_diff":           stress_result.bs_diffs.get(yr, 0),
            }
        return comparison

    def _extract_kpis(self, model_result) -> Dict[int, Dict[str, float]]:
        """Извлекает ключевые KPI из результата модели."""
        kpis = {}
        for yr, s in model_result.years.items():
            net_debt = s.short_term_debt + s.long_term_debt - s.cash
            kpis[yr] = {
                "revenue":            s.revenue,
                "ebitda":             s.ebitda,
                "ebitda_margin":      s.ebitda / s.revenue if s.revenue else 0,
                "ebit":               s.ebit,
                "net_income":         s.net_income,
                "total_da":           s.total_da,
                "cfo_total":          s.cfo_total,
                "capex":              s.cfi_capex,
                "fcf":                s.cfo_total + s.cfi_capex,
                "cash":               s.cash,
                "short_term_debt":    s.short_term_debt,
                "long_term_debt":     s.long_term_debt,
                "interest_expense":   s.interest_expense,
                "net_debt":           net_debt,
                "net_debt_ebitda":    net_debt / s.ebitda if s.ebitda > 0 else None,
                "interest_coverage":  s.ebit / s.interest_expense if s.interest_expense > 0 else None,
                "bs_diff":            model_result.bs_diffs.get(yr, 0),
            }
        return kpis

    def _save_results(
        self,
        scenario_name: str,
        base_scenario: str,
        result: StressResult,
        model_result,
    ) -> None:
        """Сохраняет результаты стресс-теста в БД."""
        try:
            import json
            self._repo.execute("""
                INSERT OR REPLACE INTO stress_results
                (company_id, scenario_name, base_scenario, status,
                 comparison_json, kpis_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, datetime('now'))
            """, (
                self.company_id,
                scenario_name,
                base_scenario,
                "success" if result.success else "fail",
                json.dumps(result.comparison),
                json.dumps(result.stress_values),
            ))
            logger.debug(f"  Результаты сохранены: {scenario_name}")
        except Exception as e:
            logger.debug(f"  Сохранение результатов: {e} (таблица может отсутствовать)")
