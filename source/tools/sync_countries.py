"""Догрузка фильмов отдельных стран из TMDb (по умолчанию Япония и Гонконг).

Примеры:
    python tools/sync_countries.py --countries "JP|HK" --from-year 1990 --pages 6
    python tools/sync_countries.py --countries "JP" --from-year 1950 --to-year 1989 --pages 3
"""

from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import DB_PATH, Config  # noqa: E402
from movie_search.database import MovieDB  # noqa: E402
from movie_search.tmdb_sync import SyncJob  # noqa: E402


def load_api_key(explicit: str = "") -> str:
    if explicit:
        return explicit.strip()
    key = Config().api_key
    if key:
        return key
    for path in (
        Path(os.environ.get("USERPROFILE", "")) / "Movie Finder" / "config.json",
        Path("E:/Movie Finder/config.json"),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Movie Finder" / "config.json",
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("tmdb_api_key"):
            return str(data["tmdb_api_key"]).strip()
    return ""


def country_counts(db: MovieDB, codes: list[str]) -> dict[str, int]:
    result: dict[str, int] = {}
    with db._lock:  # noqa: SLF001 - служебная статистика
        for code in codes:
            result[code] = int(
                db._conn.execute(  # noqa: SLF001
                    "SELECT COUNT(*) FROM movies WHERE countries LIKE ?", (f"%,{code},%",)
                ).fetchone()[0]
            )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Догрузка фильмов выбранных стран")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--countries", default="JP|HK")
    parser.add_argument("--from-year", type=int, default=1990)
    parser.add_argument("--to-year", type=int, default=2026)
    parser.add_argument("--pages", type=int, default=6)
    parser.add_argument("--min-votes", type=int, default=25)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key)
    if not api_key:
        print("Нужен ключ TMDb")
        return 1

    db = MovieDB(Path(args.db))
    codes = [c.strip() for c in args.countries.split("|") if c.strip()]
    before_counts = country_counts(db, codes)
    before_total = db.count()
    print(f"До: всего {before_total}, " + ", ".join(f"{c}: {n}" for c, n in before_counts.items()))

    job = SyncJob(
        db,
        api_key,
        pages=args.pages,
        min_votes=args.min_votes,
        workers=args.workers,
        years=range(args.from_year, args.to_year + 1),
        countries="|".join(codes),
    )
    started = time.time()
    job.start()
    last = 0.0
    while job.running or not job.queue.empty():
        try:
            message = job.queue.get(timeout=1)
        except queue.Empty:
            continue
        kind = message[0]
        if kind == "progress":
            label, done, total = message[3], message[1], message[2]
            if time.time() - last > 8:
                print(f"  {label} ({done}/{total})", flush=True)
                last = time.time()
        elif kind in ("log", "error"):
            print("  >>", message[1], flush=True)
        elif kind == "done":
            print(f"  готово, добавлено: {message[1]}", flush=True)

    after_counts = country_counts(db, codes)
    print("\n" + "=" * 52)
    print(f"Всего фильмов: {before_total} → {db.count()}")
    for code in codes:
        print(f"  {code}: {before_counts.get(code, 0)} → {after_counts.get(code, 0)}")
    print(f"Время: {time.time() - started:.0f} c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
