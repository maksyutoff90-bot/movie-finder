"""Интеграционная проверка интерфейса без снимков экрана.

Проверяет: поиск и сетку карточек, «показать ещё», окно фильма, вёрстку диалогов
и аккуратное закрытие приложения.

Запуск:  python tools/selftest.py
"""

from __future__ import annotations

import sys
import time
import tkinter as tk
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.ui import DetailWindow, MovieApp, SettingsWindow, SyncWindow  # noqa: E402

problems: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        problems.append(message)


def pump(app: tk.Tk, seconds: float) -> None:
    """Крутит цикл событий, пока не выполнятся фоновые задачи."""
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def walk(widget: tk.Misc):
    for child in widget.winfo_children():
        yield child
        yield from walk(child)


def check_buttons(window: tk.Toplevel, name: str) -> None:
    window.update_idletasks()
    window.update()
    width, height = window.winfo_width(), window.winfo_height()
    top, left = window.winfo_rooty(), window.winfo_rootx()
    buttons = [w for w in walk(window) if isinstance(w, (ttk.Button, tk.Button))]
    check(bool(buttons), f"{name}: есть кнопки")
    for button in buttons:
        right = button.winfo_rootx() - left + button.winfo_width()
        bottom = button.winfo_rooty() - top + button.winfo_height()
        inside = button.winfo_ismapped() and right <= width and bottom <= height
        check(inside, f"{name}: кнопка «{button.cget('text')}» видна в окне ({width}×{height})")


def main() -> int:
    app = MovieApp()
    app.update()
    pump(app, 2.5)

    total_all = app.db.count()
    default_total = app.db.search(year_from=1990, year_to=2026, min_rating=6.0, limit=1)[1]
    print(f"\nФильмов в базе: {total_all} (под фильтром по умолчанию: {default_total})")
    check(total_all > 0, "база не пуста")
    check(len(app.cards) > 0, f"карточки отрисованы ({len(app.cards)})")
    check(app._total == default_total, "счётчик совпадает с фильтром по умолчанию")  # noqa: SLF001

    # Фильтры: жанр + рейтинг
    app.genre_var.set("Драма")
    app.rating_var.set(8.0)
    app.search()
    pump(app, 2.0)
    print(f"Драма ★8+: карточек {len(app.cards)}, счётчик {app._total}")  # noqa: SLF001
    check(all("драма" in (card.movie["genres"] or "") for card in app.cards), "все карточки — драмы")
    check(all((card.movie["rating"] or 0) >= 8.0 for card in app.cards), "у всех рейтинг ≥ 8.0")

    # «Показать ещё» — если результатов больше страницы
    if app._total > len(app.cards):  # noqa: SLF001
        before = len(app.cards)
        app.load_more()
        pump(app, 2.0)
        check(len(app.cards) > before, f"«Показать ещё» добавил карточки ({before} → {len(app.cards)})")
    else:
        print("  (пропуск «показать ещё»: результатов меньше страницы)")

    # Окно фильма
    first = app.cards[0].movie
    detail = DetailWindow(app, first)
    detail.geometry("1040x690+40+30")
    pump(app, 0.6)
    check(detail.winfo_exists() == 1, "окно фильма открылось")
    check(detail.text.get("1.0", "end").strip() != "", "в окне фильма есть описание")
    check_buttons(detail, "Окно фильма")
    detail.destroy()

    # Сброс фильтров
    app.reset()
    pump(app, 2.0)
    check(app._total == default_total, "сброс фильтров возвращает исходную выдачу")  # noqa: SLF001

    # Диалоги: размеры берём «как есть» — тест ловит вёрстку, которая вылезает за окно
    settings = SettingsWindow(app)
    pump(app, 0.3)
    check_buttons(settings, "Настройки")
    settings.destroy()

    sync = SyncWindow(app)
    pump(app, 0.3)
    check_buttons(sync, "Обновление базы")
    check(sync.log.get("1.0", "end").strip() != "", "в окне загрузки есть пояснение")
    sync.destroy()

    # Закрытие при активном поиске не должно ронять фоновый поток
    app.search()
    pump(app, 0.1)
    app._on_close()  # noqa: SLF001 - проверяем штатное закрытие

    print("\n" + ("ВСЁ ХОРОШО" if not problems else f"ПРОБЛЕМЫ: {len(problems)}"))
    for problem in problems:
        print("  -", problem)
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main())
