"""Точка входа: запуск графического приложения Movie Finder.

Работает и из исходников (`python main.py`), и из собранного exe. Дополнительно
поддерживает диагностические режимы:

    python main.py --selftest                      # проверить базу и окно
    python main.py --shot data/shot.png 8000       # снимок главного окна
    python main.py --shot data/shot.png 8000 --movie "Начало"

В сборке нет консоли, поэтому ошибки пишутся в data/crash.log и показываются
в окне сообщения.
"""

from __future__ import annotations

import sys
import traceback


def _report_error(exc: BaseException, dialog: bool = True) -> None:
    from datetime import datetime
    from pathlib import Path

    text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
    try:
        base = (
            Path(sys.executable).resolve().parent
            if getattr(sys, "frozen", False)
            else Path(__file__).resolve().parent
        )
        log = base / "data" / "crash.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        with log.open("a", encoding="utf-8") as handle:
            handle.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{text}\n")
    except OSError:
        pass

    if not dialog:
        print(text, file=sys.stderr)
        return

    try:
        import tkinter as tk
        from tkinter import messagebox

        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Movie Finder — ошибка запуска",
            f"{exc}\n\nПодробности записаны в data/crash.log",
        )
        root.destroy()
    except Exception:  # noqa: BLE001 - окно с ошибкой не обязано открыться
        print(text, file=sys.stderr)


def _run_diagnostics() -> int | None:
    """Диагностические режимы; None — значит, нужен обычный запуск."""
    args = sys.argv[1:]
    if "--selftest" in args:
        from movie_search.diagnostics import run_selftest

        return run_selftest()
    if "--repair" in args:
        from movie_search.diagnostics import run_repair

        return run_repair()
    if "--shot" in args:
        from movie_search.diagnostics import screenshot_from_argv

        action = screenshot_from_argv(sys.argv)
        if action:
            return action()
    return None


def main() -> int:
    try:
        result = _run_diagnostics()
    except Exception as exc:  # noqa: BLE001 - диагностика не должна вешать окно
        _report_error(exc, dialog=False)
        return 1
    if result is not None:
        return result

    try:
        from movie_search.ui import MovieApp
    except ImportError as exc:
        _report_error(
            ImportError(f"{exc}\nУстановите зависимости: pip install -r requirements.txt")
        )
        return 1

    try:
        app = MovieApp()
        app.mainloop()
    except Exception as exc:  # noqa: BLE001 - показываем любую ошибку запуска
        _report_error(exc)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
