"""Общая настройка pytest для исходников Movie Finder.

Тесты лежат в `tests/`, но импортируют пакет `movie_search` из корня исходников
и вспомогательные скрипты из `tools/`.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers", "gui: открывает окна Tk — нужен рабочий стол Windows"
    )
