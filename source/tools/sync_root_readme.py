"""Синхронизирует README из source/ в корень репозитория.

Корневой README показывает GitHub и он же лежит рядом с exe. В нём пути к
скриншотам должны быть без `../`, потому что папка `screenshots/` находится
на том же уровне.

Запуск:  python tools/sync_root_readme.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT.parent / "README.md"


def main() -> int:
    if not (ROOT.parent / ".git").is_dir():
        print("Корень репозитория не найден — синхронизация не нужна.")
        return 0
    if not (ROOT / "README.md").is_file():
        print("README.md в source/ не найден.")
        return 1
    text = (ROOT / "README.md").read_text(encoding="utf-8")
    text = text.replace("](../screenshots/", "](screenshots/")
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"Обновлён {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
