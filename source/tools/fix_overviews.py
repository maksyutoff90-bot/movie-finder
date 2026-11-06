"""Догрузка описаний для фильмов, у которых текста нет.

Запрашивает у TMDb данные фильма на русском и записывает описание, если оно
нашлось (иногда TMDb отдаёт только английское — тогда берётся и оно).

Запуск:
    python tools/fix_overviews.py --limit 3000
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
from movie_search.tmdb_sync import TMDBClient, TMDBError  # noqa: E402


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


def main() -> int:
    parser = argparse.ArgumentParser(description="Догрузка описаний из TMDb")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--limit", type=int, default=3000)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    api_key = load_api_key(args.api_key)
    if not api_key:
        print("Нужен ключ TMDb")
        return 1

    db = MovieDB(Path(args.db))
    ids = db.films_without_overview(args.limit)
    print(f"Без описания: к обработке {len(ids)}")
    if not ids:
        return 0

    clients = [TMDBClient(api_key, "ru-RU"), TMDBClient(api_key, "en-US")]
    started = time.time()
    fixed = 0

    def fetch(movie_id: int) -> tuple[int, str]:
        for client in clients:
            for _attempt in range(2):
                try:
                    data = client.get(f"/movie/{movie_id}")
                except TMDBError:
                    continue
                text = (data.get("overview") or "").strip()
                if len(text) > 40:
                    return movie_id, text
            break
        return movie_id, ""

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(fetch, movie_id) for movie_id in ids]
        for done, future in enumerate(as_completed(futures), 1):
            movie_id, text = future.result()
            if text:
                db.update_overview(movie_id, text)
                fixed += 1
            if done % 200 == 0:
                print(f"  {done}/{len(ids)}, найдено {fixed}", flush=True)

    print("\n" + "=" * 52)
    print(f"Обработано: {len(ids)}  Описаний добавлено: {fixed}")
    print(f"Время: {time.time() - started:.0f} c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
