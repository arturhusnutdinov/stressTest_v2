"""
stressTest Engine v2

ROOT определяется автоматически как папка содержащая data_mart_v2.db.
Не зависит от глубины вложенности файлов.
"""
from pathlib import Path as _Path
import os as _os

def _find_root() -> _Path:
    """
    Находит корень проекта поднимаясь вверх от engine/__init__.py
    пока не найдёт data_mart_v2.db или README.md с маркером проекта.
    """
    # Переменная окружения имеет приоритет
    env_root = _os.environ.get('STRESSTEST_ROOT')
    if env_root:
        return _Path(env_root)
    
    # Поднимаемся вверх от engine/
    current = _Path(__file__).parent  # engine/
    for _ in range(5):
        current = current.parent
        if (current / 'data_mart_v2.db').exists():
            return current
        if (current / 'README.md').exists() and (current / 'engine').exists():
            return current
    
    # Fallback: parent of engine/
    return _Path(__file__).parent.parent

ROOT = _find_root()
DB_PATH = ROOT / 'data_mart_v2.db'
