"""Снимок окна в PNG — для проверки вёрстки и документации.

Запуск:
    python tools/screenshot.py                        # главное окно -> data/screenshot.png
    python tools/screenshot.py out.png 8000           # свой путь и задержка
    python tools/screenshot.py out.png 8000 "Начало"  # окно фильма по названию
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.diagnostics import take_screenshot  # noqa: E402


def main() -> int:
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "screenshot.png"
    delay = int(sys.argv[2]) if len(sys.argv) > 2 else 6000
    title = sys.argv[3] if len(sys.argv) > 3 else ""
    return take_screenshot(target, delay, title)


if __name__ == "__main__":
    raise SystemExit(main())
