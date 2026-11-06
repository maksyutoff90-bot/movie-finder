"""Снимает набор скриншотов всех экранов приложения.

Запуск: python tools/screens.py [папка]
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from movie_search.ui import (  # noqa: E402
    DetailWindow,
    HistoryWindow,
    MovieApp,
    SettingsWindow,
    SyncWindow,
)

OUT = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "shots"


def pump(app: tk.Misc, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.03)


def grab(window: tk.Misc, name: str) -> None:
    window.update_idletasks()
    window.update()
    time.sleep(0.4)
    x, y = window.winfo_rootx(), window.winfo_rooty()
    width, height = window.winfo_width(), window.winfo_height()
    image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    image.save(path)
    print(f"  {name}: {image.width}x{image.height}")


def main() -> int:
    app = MovieApp()
    app.geometry("1340x880+20+20")
    pump(app, 6)

    grab(app, "01_главное_окно.png")

    labels = {code: label for label, code in app._country_by_label.items()}  # noqa: SLF001
    app.country_var.set(labels.get("HK", "Гонконг"))
    app.search()
    pump(app, 4)
    grab(app, "02_гонконг.png")

    app.country_var.set(labels.get("JP", "Япония"))
    app.rating_var.set(7.5)
    app.search()
    pump(app, 4)
    grab(app, "03_япония_рейтинг.png")

    rows, _ = app.db.search(title="Infernal Affairs", limit=1)
    if rows:
        detail = DetailWindow(app, rows[0])
        pump(app, 4)
        grab(detail, "04_карточка_фильма.png")
        detail.destroy()

    settings = SettingsWindow(app)
    pump(app, 1.2)
    grab(settings, "05_настройки.png")
    settings.destroy()

    history = HistoryWindow(app)
    pump(app, 1.2)
    grab(history, "06_история.png")
    history.destroy()

    sync = SyncWindow(app, recent_only=True)
    pump(app, 1.2)
    grab(sync, "07_новинки.png")
    sync.destroy()

    app.destroy()
    print(f"\nСкриншоты в {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
