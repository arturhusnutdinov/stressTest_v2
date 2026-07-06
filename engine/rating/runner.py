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
            lines.append(
                f"  {yr}: {r['rating']:<5} скор={r['score']:.0f}  [{ig}]  "
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
                self._repo.upsert_rating(
                    company_id=self.company_id,
                    scenario_id=sid,
                    year=yr_int,
                    methodology='sp_scoring',
                    grade=r.get('rating', '?'),
                    score=r.get('score', 0),
                )
                total += 1

            # Также сохраняем в legacy rating_results для обратной совместимости
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
            logger.info(f"  Рейтинг сохранён: {result.rating_type} → {total} лет (ratings + rating_results)")
        except Exception as e:
            logger.error(f"  Ошибка сохранения рейтинга: {e}")
