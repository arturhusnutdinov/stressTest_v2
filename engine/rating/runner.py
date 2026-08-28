"""RatingRunner — рассчитывает рейтинги для Base/Forecast/Stress."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from .core import CreditMetrics, RatingEngine, RatingConfig, sp_to_numeric

logger = logging.getLogger(__name__)


@dataclass
class RatingResult:
    company_id: str
    rating_type: str  # base | forecast | stress
    success: bool = False
    errors: List[str] = field(default_factory=list)
    # {year: rating_dict}
    ratings: Dict[int, Dict] = field(default_factory=dict)
    # {year: CreditMetrics}
    metrics: Dict[int, CreditMetrics] = field(default_factory=dict)

    def summary(self) -> str:
        lines = [
            f"Рейтинг [{self.rating_type}]: {self.company_id}",
            f"  Статус: {'OK' if self.success else 'FAIL'}",
        ]
        for yr, r in sorted(self.ratings.items()):
            ig = "IG" if r.get("is_investment_grade") else "HY"
            nat = r.get('rating_national', '')
            nat_str = f" / {nat}" if nat else ""
            lines.append(
                f"  {yr}: {r['rating']:<5}{nat_str:<12} скор={r['score']:.0f}  [{ig}]  "
                f"lev={r['sub_scores'].get('leverage', 0):.0f} "
                f"cov={r['sub_scores'].get('coverage', 0):.0f} "
                f"prof={r['sub_scores'].get('profitability', 0):.0f} "
                f"liq={r['sub_scores'].get('liquidity', 0):.0f}"
            )
        if self.errors:
            lines += [f"  x {e}" for e in self.errors]
        return "\n".join(lines)

    def worst_rating(self) -> Optional[str]:
        if not self.ratings:
            return None
        return max(self.ratings.values(), key=lambda r: r.get("numeric", 99))["rating"]

    def best_rating(self) -> Optional[str]:
        if not self.ratings:
            return None
        return min(self.ratings.values(), key=lambda r: r.get("numeric", 99))["rating"]


class RatingRunner:
    """Рассчитывает кредитные рейтинги из результатов модели."""

    def __init__(
        self,
        company_id: str,
        repo,
        config: Optional[RatingConfig] = None,
    ):
        self.company_id = company_id
        self._repo = repo
        self._engine = RatingEngine(config or RatingConfig())

    @classmethod
    def from_project_yaml(cls, company_id: str, repo, company_dir) -> "RatingRunner":
        """Создаёт RatingRunner с настройками из project.yaml."""
        import yaml
        from pathlib import Path
        proj_path = Path(company_dir) / "configs" / "project.yaml"
        config = RatingConfig()
        if proj_path.exists():
            with open(proj_path) as f:
                cfg = yaml.safe_load(f) or {}
            rating_cfg = cfg.get("rating", {})
            config.methodology = rating_cfg.get("methodology", "sp")
            config.industry_adjustment = float(
                rating_cfg.get("industry_adjustment", -8.0)
            )
            config.size_adjustment = float(
                rating_cfg.get("size_adjustment", 3.0)
            )
            config.cycle_avg_ebitda_margin = float(
                rating_cfg.get("cycle_avg_ebitda_margin", 0.10)
            )
            config.sovereign_rating = rating_cfg.get(
                "sovereign_rating", "BBB+"
            )
            weights = rating_cfg.get("weights", {})
            if weights:
                config.weights = {
                    "leverage":      weights.get("leverage",      0.35),
                    "coverage":      weights.get("coverage",      0.30),
                    "profitability": weights.get("profitability", 0.20),
                    "liquidity":     weights.get("liquidity",     0.15),
                }
        return cls(company_id, repo, config)

    def rate_model_result(
        self,
        model_result,
        rating_type: str = "forecast",
        save: bool = True,
    ) -> RatingResult:
        """
        Рассчитывает рейтинг из ModelResult.

        Args:
            model_result: результат ThreeStatementModel.run()
            rating_type:  base | forecast | stress
            save:         сохранить в БД
        """
        result = RatingResult(
            company_id=self.company_id,
            rating_type=rating_type,
        )

        try:
            for yr, state in sorted(model_result.years.items()):
                metrics = CreditMetrics.from_year_state(state, yr)
                rating  = self._engine.calculate(metrics)
                rating['factor_analysis'] = self._factor_analysis(metrics, rating)
                result.metrics[yr] = metrics
                result.ratings[yr] = rating

            if save:
                self._save(result)

            result.success = True
            logger.info(f"Рейтинг [{rating_type}]: {result.best_rating()} → {result.worst_rating()}")

        except Exception as e:
            result.errors.append(str(e))
            logger.exception(f"Ошибка рейтинга: {e}")

        return result

    def rate_historical(
        self,
        historic_state,
        years: Optional[List[int]] = None,
        save: bool = True,
    ) -> RatingResult:
        """Рассчитывает исторический рейтинг из base_year_state."""
        result = RatingResult(company_id=self.company_id, rating_type="base")
        try:
            state  = historic_state.base_year_state
            year   = historic_state.base_year
            metrics = CreditMetrics.from_year_state(state, year)
            rating  = self._engine.calculate(metrics)
            result.metrics[year] = metrics
            result.ratings[year] = rating

            if save:
                self._save(result)
            result.success = True
        except Exception as e:
            result.errors.append(str(e))
        return result

    def rate_from_kpis(
        self,
        stress_values: Dict[int, Dict[str, float]],
        rating_type: str = "stress",
        save: bool = True,
    ) -> RatingResult:
        """Rate from stress KPI values {year: {metric: value}}.

        Builds CreditMetrics from raw KPI dict (revenue, ebitda, net_income,
        total_debt, cash, interest_expense, total_assets, total_equity, etc.)
        """
        result = RatingResult(company_id=self.company_id, rating_type=rating_type)
        try:
            for yr, kpis in sorted(stress_values.items()):
                metrics = CreditMetrics.from_kpi_dict(kpis, yr)
                rating = self._engine.calculate(metrics)
                # Factor analysis
                rating['factor_analysis'] = self._factor_analysis(metrics, rating)
                result.metrics[yr] = metrics
                result.ratings[yr] = rating
            if save:
                self._save(result)
            result.success = True
        except Exception as e:
            result.errors.append(str(e))
            logger.debug(f"rate_from_kpis error: {e}")
        return result

    @staticmethod
    def _factor_analysis(metrics: CreditMetrics, rating: Dict) -> Dict:
        """Factor contribution analysis for rating.

        Returns:
          - sub_score_contributions: how each factor group contributes to total score
          - proximity_to_threshold: how close each metric is to rating boundary
          - key_drivers: top 3 factors driving the rating
          - vulnerabilities: metrics closest to downgrade threshold
        """
        sub_scores = rating.get('sub_scores', {})
        weights = rating.get('weights', {})
        total_score = rating.get('score', 0)

        # Contribution = weight × sub_score / total_score
        contributions = {}
        for factor, score in sub_scores.items():
            w = weights.get(factor, 0.25)
            contributions[factor] = {
                'score': score,
                'weight': w,
                'weighted_score': score * w,
                'contribution_pct': (score * w / total_score * 100) if total_score > 0 else 0,
            }

        # Sort by contribution
        sorted_factors = sorted(contributions.items(), key=lambda x: x[1]['weighted_score'], reverse=True)
        key_drivers = [f[0] for f in sorted_factors[:3]]

        # Proximity to threshold (how close to downgrade)
        # S&P-style: BB+ boundary ~55, BBB- ~60, BBB ~65, A- ~70
        thresholds = {
            'BBB-': 60, 'BBB': 65, 'BBB+': 68, 'A-': 70, 'A': 75,
            'BB+': 55, 'BB': 50, 'BB-': 45, 'B+': 40,
        }
        current_grade = rating.get('rating', '')
        numeric = rating.get('numeric', 0)
        headroom = {}
        for grade, threshold in thresholds.items():
            headroom[grade] = total_score - threshold

        # Vulnerabilities: metrics with low sub_scores
        vulnerabilities = [f for f, s in sub_scores.items() if s < 50]

        return {
            'contributions': contributions,
            'key_drivers': key_drivers,
            'vulnerabilities': vulnerabilities,
            'headroom_to_ig': total_score - thresholds.get('BBB-', 60),
            'headroom_to_downgrade': total_score - thresholds.get('BB', 50),
        }

    def _save(self, result: RatingResult) -> None:
        """Сохраняет рейтинги в БД через Repository."""
        try:
            import json
            # Определяем scenario_id
            scenario_name = result.rating_type  # 'base', 'forecast', 'stress'
            sid = self._repo.ensure_scenario(
                self.company_id, scenario_name, type_=scenario_name,
            )
            total = 0
            for yr, r in result.ratings.items():
                yr_int = int(yr)
                # Build score_detail from sub_scores + factor_analysis
                score_detail = {}
                if r.get('sub_scores'):
                    score_detail['sub_scores'] = r['sub_scores']
                if r.get('weights'):
                    score_detail['weights'] = r['weights']
                if r.get('factor_analysis'):
                    fa = r['factor_analysis']
                    score_detail['key_drivers'] = fa.get('key_drivers', [])
                    score_detail['vulnerabilities'] = fa.get('vulnerabilities', [])
                    score_detail['headroom_to_ig'] = fa.get('headroom_to_ig')
                    score_detail['headroom_to_downgrade'] = fa.get('headroom_to_downgrade')

                # Extract key metrics from CreditMetrics
                metrics = result.metrics.get(yr)
                nd_ebitda = getattr(metrics, 'net_debt_ebitda', None) if metrics else None
                icr = getattr(metrics, 'interest_coverage', None) if metrics else None

                self._repo.upsert_rating(
                    company_id=self.company_id,
                    scenario_id=sid,
                    year=yr_int,
                    methodology='sp_scoring',
                    grade=r.get('rating', '?'),
                    score=r.get('score', 0),
                    score_detail=score_detail if score_detail else None,
                    nd_ebitda=nd_ebitda,
                    icr=icr,
                )
                total += 1

            # Также сохраняем в legacy rating_results (SQLite only)
            try:
                self._repo.execute("""
                    CREATE TABLE IF NOT EXISTS rating_results (
                        id           INTEGER PRIMARY KEY AUTOINCREMENT,
                        company_id   TEXT NOT NULL,
                        rating_type  TEXT NOT NULL,
                        ratings_json TEXT,
                        metrics_json TEXT,
                        created_at   TEXT DEFAULT (datetime('now')),
                        UNIQUE(company_id, rating_type)
                    )
                """)
                metrics_serializable = {}
                for yr, m in result.metrics.items():
                    metrics_serializable[yr] = {
                        k: v for k, v in m.__dict__.items() if v is not None
                    }
                self._repo.execute("""
                    INSERT OR REPLACE INTO rating_results
                    (company_id, rating_type, ratings_json, metrics_json, created_at)
                    VALUES (?, ?, ?, ?, datetime('now'))
                """, (
                    self.company_id, result.rating_type,
                    json.dumps(result.ratings), json.dumps(metrics_serializable),
            ))
                self._repo.conn.commit()
            except Exception as e_legacy:
                # rating_results is SQLite-only legacy table; skip on PG
                logger.debug(f"  Legacy rating_results skip (PG): {e_legacy}")
            logger.info(f"  Рейтинг сохранён: {result.rating_type} → {total} лет")
        except Exception as e:
            logger.error(f"  Ошибка сохранения рейтинга: {e}")
