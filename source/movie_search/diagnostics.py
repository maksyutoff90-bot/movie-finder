"""Диагностические режимы: самопроверка и снимок окна.

Используются и при запуске из исходников (`tools/selftest.py`,
`tools/screenshot.py`), и из собранного exe:

    "Movie Finder.exe" --selftest
    "Movie Finder.exe" --shot data/shot.png 8000
    "Movie Finder.exe" --shot data/shot.png 8000 --movie "Начало"
"""

from __future__ import annotations

import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from typing import Callable


def _log_dir() -> Path:
    """Каталог для отчётов: рядом с программой, иначе — в профиле пользователя."""
    from .config import BUNDLED_DATA_DIR, fallback_data_dir, is_writable

    for folder in (BUNDLED_DATA_DIR, fallback_data_dir()):
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError:
            continue
        if is_writable(folder):
            return folder
    import tempfile

    return Path(tempfile.gettempdir())


def _log_path(base: Path | None = None) -> Path:
    return _log_dir() / "selftest.log"


def _say(message: str) -> None:
    """Печать, которая не падает на консоли с кодировкой cp866."""
    try:
        print(message)
    except UnicodeEncodeError:
        print(message.encode("ascii", "replace").decode("ascii"))


def _write(path: Path, lines: list[str]) -> None:
    text = "\n".join(lines) + "\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} ===\n{text}")


def _pump(app, seconds: float) -> None:
    end = time.time() + seconds
    while time.time() < end:
        app.update()
        time.sleep(0.02)


def _grab_best(window, attempts: int = 4):
    """Несколько снимков: первый может быть чёрным, пока окно не отрисовано."""
    from PIL import ImageGrab, ImageStat

    best, best_score = None, -1.0
    for _ in range(attempts):
        x, y = window.winfo_rootx(), window.winfo_rooty()
        width, height = window.winfo_width(), window.winfo_height()
        image = ImageGrab.grab(bbox=(x, y, x + width, y + height))
        score = ImageStat.Stat(image.convert("L")).stddev[0]
        if score > best_score:
            best, best_score = image, score
        if best_score > 8:
            break
        time.sleep(0.8)
    return best


def take_screenshot(target: Path, delay_ms: int = 6000, title: str = "") -> int:
    """Открывает программу, ждёт отрисовки и сохраняет снимок окна."""
    from .ui import DetailWindow, MovieApp

    app = MovieApp()
    app.geometry("1340x880+30+20")
    holder: dict[str, object] = {}

    def open_detail() -> None:
        rows, _ = app.db.search(title=title, limit=1)
        if not rows:
            _say(f"Фильм «{title}» не найден — снимаю главное окно")
            return
        window = DetailWindow(app, rows[0])
        window.geometry("1040x690+40+30")
        holder["window"] = window

    def capture() -> None:
        window = holder.get("window") or app
        try:
            window.deiconify()
            window.lift()
            window.attributes("-topmost", True)
            window.update_idletasks()
            window.update()
            time.sleep(0.3)
            image = _grab_best(window)
            target.parent.mkdir(parents=True, exist_ok=True)
            image.save(target)
            _say(f"Сохранено: {target} ({image.width}x{image.height})")
        except Exception as exc:  # noqa: BLE001
            _say(f"Не удалось сделать снимок: {exc}")
        finally:
            app.destroy()

    if title:
        app.after(1500, open_detail)
    app.after(delay_ms, capture)
    app.mainloop()
    return 0


def run_selftest() -> int:
    """Проверяет базу, поиск и отрисовку главного окна; пишет data/selftest.log."""
    from .config import DB_PATH
    from .database import MovieDB
    from .ui import MovieApp

    log = _log_path()
    lines: list[str] = [f"Python: {sys.version.split()[0]}", f"База: {DB_PATH}"]
    ok = True
    app = None
    try:
        db = MovieDB(DB_PATH)
        stats = db.stats()
        lines.append(
            f"Фильмов: {stats['total']}, с постером: {stats['with_poster']}, "
            f"годы: {stats['min_year']}–{stats['max_year']}"
        )
        if stats["total"] == 0:
            ok = False
            lines.append("ОШИБКА: база пуста")

        rows, total = db.search(limit=3)
        lines.append(f"Поиск без фильтров: {total}; первые: " + ", ".join(r["title"] for r in rows))

        issue = db.check_writable()
        lines.append("Запись в базу: " + ("OK" if not issue else f"ОШИБКА — {issue}"))
        if issue:
            ok = False

        app = MovieApp()
        app.suppress_dialogs = True
        _pump(app, 3.0)
        lines.append(f"Окно: карточек отрисовано {len(app.cards)}, счётчик {app._total}")
        if not app.cards:
            ok = False
            lines.append("ОШИБКА: карточки не отрисованы")
        if stats["total"] and len(app.cards) == 0:
            ok = False

        detail_ok = True
        if rows:
            from .ui import DetailWindow

            window = DetailWindow(app, rows[0])
            _pump(app, 0.8)
            text = window.text.get("1.0", "end").strip()
            detail_ok = bool(window.winfo_exists()) and bool(text)
            window.destroy()
            lines.append(f"Окно фильма: описание {len(text)} симв.")
            if not detail_ok:
                ok = False
                lines.append("ОШИБКА: окно фильма не открылось или пустое")
    except Exception as exc:  # noqa: BLE001 - отчёт важнее падения
        ok = False
        lines.append("ОШИБКА: " + str(exc))
        lines.append(traceback.format_exc())
    finally:
        if app is not None:
            try:
                app._on_close()  # noqa: SLF001 - штатное закрытие
            except Exception:  # noqa: BLE001
                pass

    lines.append("ИТОГ: " + ("OK" if ok else "ПРОБЛЕМЫ"))
    _write(log, lines)
    for line in lines:
        _say(line)
    return 0 if ok else 1


def run_repair() -> int:
    """Приводит базу в порядок: завершает WAL, проверяет целостность.

    Запуск: `Movie Finder.exe --repair` (пишет data/repair.log).
    """
    import sqlite3

    from .config import DB_PATH
    from .database import DatabaseError, MovieDB

    log_lines: list[str] = [f"База: {DB_PATH}"]
    ok = True

    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10)
        try:
            checkpoint = conn.execute("PRAGMA wal_checkpoint(TRUNCATE)").fetchone()
            log_lines.append(f"wal_checkpoint: {checkpoint}")
            integrity = conn.execute("PRAGMA integrity_check").fetchone()
            log_lines.append(f"integrity_check: {integrity}")
            if not integrity or str(integrity[0]).lower() != "ok":
                ok = False
        finally:
            conn.close()
    except sqlite3.Error as exc:
        ok = False
        log_lines.append(f"ОШИБКА при работе с файлом базы: {exc}")

    try:
        db = MovieDB(DB_PATH)
        log_lines.append(f"Фильмов: {db.count()}")
        issue = db.check_writable()
        log_lines.append("Запись в базу: " + ("OK" if not issue else f"ОШИБКА — {issue}"))
        if issue:
            ok = False
        deduped = db.remove_wiki_duplicates()
        if deduped:
            log_lines.append(f"Убрано дублей офлайн-каталога: {deduped}")
        db.close()
    except DatabaseError as exc:
        ok = False
        log_lines.append(f"ОШИБКА базы: {exc}")

    log_lines.append("ИТОГ: " + ("OK" if ok else "ПРОБЛЕМЫ"))
    _write(_log_path().with_name("repair.log"), log_lines)
    for line in log_lines:
        _say(line)
    return 0 if ok else 1


def screenshot_from_argv(argv: list[str]) -> Callable[[], int] | None:
    """Разбирает `--shot PATH [DELAY] [--movie Название]`."""
    if "--shot" not in argv:
        return None
    index = argv.index("--shot")
    target = Path(argv[index + 1]) if len(argv) > index + 1 else Path("data/shot.png")
    delay = 6000
    title = ""
    rest = argv[index + 2 :]
    if rest and rest[0].isdigit():
        delay = int(rest[0])
        rest = rest[1:]
    if "--movie" in rest:
        title = rest[rest.index("--movie") + 1] if len(rest) > rest.index("--movie") + 1 else ""
    return lambda: take_screenshot(target, delay, title)
