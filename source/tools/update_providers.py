"""Пакетное обновление «где смотреть» для новых фильмов.

Запрашивает у TMDb площадки показа (данные JustWatch) и складывает их в таблицу
providers — после этого карточка фильма показывает сервисы мгновенно, без запроса.

Запуск:
    python tools/update_providers.py                    # фильмы 2020–2026
    python tools/update_providers.py --from-year 2023   # только свежие
    python tools/update_providers.py --force            # перезапросить всё
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import DB_PATH, Config  # noqa: E402
from movie_search.database import MovieDB  # noqa: E402
from movie_search.links import fetch_providers  # noqa: E402


def load_api_key(explicit: str = "") -> str:
    if explicit:
        return explicit.strip()
    key = Config().api_key
    if key:
        return key
    for path in (
        Path(os.environ.get("USERPROFILE", "")) / "Movie Finder" / "config.json",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Movie Finder" / "config.json",
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("tmdb_api_key"):
            return str(data["tmdb_api_key"]).strip()
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(description="Обновление площадок показа")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--from-year", type=int, default=2020)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--min-votes", type=int, default=10)
    parser.add_argument("--limit", type=int, default=0, help="0 — все подходящие")
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--force", action="store_true", help="перезапросить уже известные")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key)
    if not api_key:
        print("Нужен ключ TMDb: укажите его в настройках приложения или через --api-key")
        return 1

    db = MovieDB(Path(args.db))
    sql = (
        "SELECT m.id FROM movies AS m "
        "WHERE m.id > 0 AND COALESCE(m.year, 0) BETWEEN ? AND ? "
        "AND COALESCE(m.votes, 0) >= ? "
        + ("" if args.force else "AND NOT EXISTS (SELECT 1 FROM providers AS p WHERE p.movie_id = m.id AND p.names <> '') ")
        + "ORDER BY COALESCE(m.year, 0) DESC, COALESCE(m.votes, 0) DESC"
    )
    params: list[int] = [args.from_year, args.to_year, args.min_votes]
    if args.limit:
        sql += " LIMIT ?"
        params.append(args.limit)

    with db._lock:  # noqa: SLF001 - служебный отбор кандидатов
        ids = [int(r[0]) for r in db._conn.execute(sql, params).fetchall()]  # noqa: SLF001
    print(f"К обновлению: {len(ids)} фильмов ({args.from_year}–{args.to_year})")
    if not ids:
        print("Всё уже обновлено — добавьте --force, чтобы перезапросить.")
        return 0

    started = time.time()
    rows: list[tuple[int, str, str, str | None]] = []
    failed = 0

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(fetch_providers, movie_id, api_key): movie_id for movie_id in ids}
        for done, future in enumerate(as_completed(futures), 1):
            try:
                result = future.result()
            except Exception:  # noqa: BLE001 - один фильм не должен ронять задачу
                result = None
                failed += 1
            if result:
                region, names, link = result
                rows.append((futures[future], region, names, link))
            if done % 100 == 0:
                print(f"  {done}/{len(ids)}, с площадками {len(rows)}", flush=True)

    for start in range(0, len(rows), 200):
        db.set_providers(rows[start : start + 200])

    elapsed = time.time() - started
    print("\n" + "=" * 52)
    print(f"Обработано: {len(ids)}  Найдено с площадками: {len(rows)}  Ошибок: {failed}")
    print(f"Всего фильмов с площадками в базе: {db.providers_count()}")
    print(f"Время: {elapsed:.0f} c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
