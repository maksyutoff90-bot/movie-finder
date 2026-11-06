"""Скриншот главного окна с заданными фильтрами (для проверки вида выдачи).

Запуск: python tools/shot_filters.py <файл.png> <год_от> <год_до> <рейтинг>
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tkinter as tk  # noqa: E402

from PIL import ImageGrab  # noqa: E402

from movie_search.ui import MovieApp  # noqa: E402

target = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "shots" / "08_фильтры.png"
year_from = int(sys.argv[2]) if len(sys.argv) > 2 else 1970
year_to = int(sys.argv[3]) if len(sys.argv) > 3 else 1984
rating = float(sys.argv[4]) if len(sys.argv) > 4 else 6.5


def pump(app: tk.Misc, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update_idletasks()
        app.update()
        time.sleep(0.03)


app = MovieApp()
app.geometry("1340x880+20+20")
pump(app, 3)
app.year_from_var.set(str(year_from))
app.year_to_var.set(str(year_to))
app.rating_var.set(rating)
app.search()
pump(app, 8)

app.update_idletasks()
x, y = app.winfo_rootx(), app.winfo_rooty()
image = ImageGrab.grab(bbox=(x, y, x + app.winfo_width(), y + app.winfo_height()))
target.parent.mkdir(parents=True, exist_ok=True)
image.save(target)
print(f"сохранено: {target} ({image.width}x{image.height})")
app.destroy()
