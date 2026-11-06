"""Проверка базы и постеров без графического интерфейса.

Запуск:  python tools/verify.py
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import DB_PATH, POSTER_DIR  # noqa: E402
from movie_search.database import DatabaseError, MovieDB  # noqa: E402
from movie_search.posters import PosterCache  # noqa: E402

failures: list[str] = []


def check(condition: bool, message: str) -> None:
    print(("  ok   " if condition else "  FAIL ") + message)
    if not condition:
        failures.append(message)


def check_recovery() -> None:
    """Сбой записи не должен ронять приложение: база переподключается и повторяет."""
    print("\nУстойчивость базы к сбоям записи:")
    work = Path(tempfile.mkdtemp())
    db = MovieDB(work / "test.db")
    db.upsert_many(
        [
            {
                "id": 1,
                "title": "Проверка",
                "year": 2024,
                "source": "test",
                "genres": "драма",
                "countries": "US",
                "overview": "тест",
            }
        ]
    )
    check(db.count() == 1, "тестовая база создана")

    attempts = {"count": 0}

    def flaky_write() -> None:
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise sqlite3.OperationalError("unable to open database file")
        with db._lock:  # noqa: SLF001 - проверяем восстановление после сбоя
            db._conn.execute(  # noqa: SLF001
                "INSERT INTO meta (key, value) VALUES ('probe', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = '1'"
            )
            db._conn.commit()  # noqa: SLF001

    try:
        db._call(flaky_write, attempts=2)  # noqa: SLF001
        check(db.get_meta("probe") == "1", "запись повторилась после сбоя SQLite")
    except DatabaseError as exc:
        check(False, f"восстановление не сработало: {exc}")

    check(db.check_writable() is None, "база доступна для записи")

    try:
        MovieDB(Path("Z:/no-such-drive/x.db"))
        check(False, "ожидалась понятная ошибка при недоступной базе")
    except DatabaseError as exc:
        text = str(exc)
        check(
            "Не удалось" in text and "Z:" in text,
            f"понятная ошибка вместо «unable to open database file»: {text[:70]}…",
        )


def main() -> int:
    print(f"База: {DB_PATH}")
    check(DB_PATH.exists(), "файл базы существует")
    db = MovieDB(DB_PATH)
    stats = db.stats()
    print(f"Фильмов: {stats['total']}, постеров: {stats['with_poster']}, "
          f"годы: {stats['min_year']}–{stats['max_year']}")
    check(stats["total"] > 100, "в базе больше 100 фильмов")
    check(stats["with_poster"] > 100, "у большинства фильмов есть постер")

    cases = [
        ("все фильмы", {}),
        ("драма 2010–2026, ★8+", {"genre": "драма", "year_from": 2010, "year_to": 2026, "min_rating": 8.0}),
        ("США, боевик", {"country": "US", "genre": "боевик"}),
        ("Россия", {"country": "RU"}),
        ("Япония, мультфильм", {"country": "JP", "genre": "мультфильм"}),
        ("поиск по названию 'матрица'", {"title": "матрица"}),
        ("поиск по названию 'ДЮНА'", {"title": "ДЮНА"}),
        ("Франция 1990–2000", {"country": "FR", "year_from": 1990, "year_to": 2000}),
    ]
    for name, filters in cases:
        rows, total = db.search(limit=5, **filters)
        print(f"\n{name}: найдено {total}")
        for row in rows[:3]:
            print(f"    {row['title']} ({row['year']}) ★{row['rating']} "
                  f"genres={row['genres']} countries={row['countries']}")
        check(total > 0, f"фильтры «{name}» дают результат")

    print("\nПроверка постеров:")
    cache = PosterCache(POSTER_DIR)
    rows, _ = db.search(limit=6)
    for row in rows:
        image = cache.image(row, (150, 225))
        check(
            image is not None and image.size == (150, 225),
            f"постер 150×225: {row['title']}",
        )

    sizes = sorted(p.stat().st_size for p in POSTER_DIR.glob("*.jpg"))
    if sizes:
        print(f"\nФайлов постеров: {len(sizes)}, средний размер: {sum(sizes) // len(sizes) // 1024} КБ")

    check_recovery()

    print("\n" + ("ВСЁ ХОРОШО" if not failures else f"ПРОБЛЕМЫ: {len(failures)}"))
    for failure in failures:
        print("  -", failure)
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
