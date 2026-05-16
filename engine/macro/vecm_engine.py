from pathlib import Path
from typing import Optional
from .vecm import run_vecm_all
import yaml

class VECMEngine:
    def __init__(self, root: Path, company: str = "") -> None:
        self.root = Path(root)
        self.company = company

    def train(self, config_path: Path, steps: Optional[int] = None) -> None:
        """
        Запуск обучения/прогноза VECM согласно конфигу (совместимо с новой схемой run/frequency/factors/vecm/io).
        steps: если задано, переопределяет horizon в конфиге (в годах при target=Y, в месяцах при target=M).
        """
        # В текущей архитектуре run_vecm_all читает horizon из YAML.
        # Чтобы не дублировать логику, здесь опционально можно сгенерировать временный конфиг с модифицированным horizon.
        cfg_path = Path(config_path)
        # Поддержка новой схемы (run/frequency/factors/vecm/io): конвертируем в legacy-конфиг для run_vecm_all
        data = yaml.safe_load(Path(cfg_path).read_text(encoding="utf-8"))
        legacy = {}
        # параметры окна и истории
        window_start = int(data.get('run', {}).get('start_year_required', 2006))
        min_hist = int(data.get('run', {}).get('require_min_history_years', 15))
        legacy['window'] = {'start_year': window_start}
        legacy['min_history_years'] = min_hist
        # lag/rank
        p_max = int(data.get('run', {}).get('max_lag', 2))
        legacy['lag_search'] = {'p_min': 1, 'p_max': p_max, 'criterion': 'AIC'}
        legacy['rank_test'] = {'method': 'johansen_trace', 'alpha': float(data.get('run', {}).get('johansen_alpha', 0.05))}
        legacy['deterministic'] = 'ci'
        # diagnostics
        legacy['diagnostics'] = {'ljung_box_alpha': 0.05}
        # horizon
        freq_target = (data.get('frequency', {}) or {}).get('target', 'Y')
        if 'vecm' in data and isinstance(data['vecm'], dict) and 'horizon_periods' in data['vecm']:
            hp = int(data['vecm']['horizon_periods'])
            legacy['horizon_years'] = int(round(hp/12)) if str(freq_target).upper().startswith('M') else hp
        else:
            legacy['horizon_years'] = int(data.get('run', {}).get('horizon_years', 5))
        # blocks из vecm.groups
        blocks = {}
        for grp in (data.get('vecm', {}).get('groups', []) or []):
            name = grp.get('name', 'block')
            facs = grp.get('factors', []) or []
            if facs:
                blocks[name] = {'factors': facs}
        legacy['blocks'] = blocks
        # записываем временный legacy-конфиг
        import tempfile
        with tempfile.NamedTemporaryFile('w', suffix='.yaml', delete=False) as tmp:
            yaml.safe_dump(legacy, tmp, sort_keys=False, allow_unicode=True)
            tmp_path = Path(tmp.name)
        try:
            # steps переопределяет горизонт
            if steps is not None:
                if str(freq_target).upper().startswith('M'):
                    legacy['horizon_years'] = int(round(int(steps)/12))
                else:
                    legacy['horizon_years'] = int(steps)
                Path(tmp_path).write_text(yaml.safe_dump(legacy, sort_keys=False, allow_unicode=True), encoding='utf-8')
            run_vecm_all(self.root, self.company, tmp_path)
        finally:
            try:
                Path(tmp_path).unlink(missing_ok=True)  # type: ignore
            except Exception:
                pass


