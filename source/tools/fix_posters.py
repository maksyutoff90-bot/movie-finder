"""Починка битых постеров.

Пути к постерам из дампа Kaggle датированы 2018 годом — часть файлов уже удалена
с CDN TMDb, и карточки показывают «нет постера». Скрипт проверяет ссылки и для
битых запрашивает актуальный постер у TMDb (нужен API-ключ).

Запуск:
    python tools/fix_posters.py --limit 3000          # топ-3000 по популярности
    python tools/fix_posters.py --limit 500 --dry     # только проверка, без запросов
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import DB_PATH, Config  # noqa: E402
from movie_search.database import MovieDB  # noqa: E402
from movie_search.tmdb_sync import TMDBClient, TMDBError  # noqa: E402

IMAGE_BASE = "https://image.tmdb.org/t/p/w342"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MovieFinder/1.0"


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
    parser = argparse.ArgumentParser(description="Починка битых постеров")
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--limit", type=int, default=2000, help="сколько фильмов проверить")
    parser.add_argument("--workers", type=int, default=12)
    parser.add_argument("--dry", action="store_true", help="только проверить, не запрашивать TMDb")
    parser.add_argument("--api-key", default="")
    args = parser.parse_args()

    db = MovieDB(Path(args.db))
    started = time.time()
    stats = db.poster_stats()
    print(
        f"База: {stats['total']} фильмов, с путём к постеру: {stats['with_path']}, "
        f"проверено ранее: {stats['checked']}, локальных файлов: {stats['local']}"
    )

    candidates = db.poster_candidates(args.limit)
    print(f"К проверке: {len(candidates)}")
    if not candidates:
        print("Все проверены — добавьте --limit больше или сбросьте poster_checked.")
        return 0

    session = requests.Session()

    def check(item: tuple[int, str]) -> tuple[int, str, bool]:
        movie_id, path = item
        try:
            response = session.head(
                IMAGE_BASE + path, timeout=12, headers={"User-Agent": USER_AGENT}
            )
            return movie_id, path, response.status_code == 200
        except requests.RequestException:
            return movie_id, path, False

    dead: list[tuple[int, str]] = []
    alive = 0
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(check, item) for item in candidates]
        for done, future in enumerate(as_completed(futures), 1):
            movie_id, path, ok = future.result()
            if ok:
                alive += 1
            else:
                dead.append((movie_id, path))
            if done % 250 == 0:
                print(f"  проверено {done}/{len(candidates)}, битых {len(dead)}", flush=True)

    print(f"Живых: {alive}, битых: {len(dead)}")
    if args.dry:
        # Сухой прогон ничего не пишет: иначе все кандидаты помечаются
        # проверенными и настоящая починка потом их уже не находит.
        print("Сухой прогон: база не изменялась.")
        return 0
    if not dead:
        ids = [movie_id for movie_id, _ in candidates]
        db.mark_posters_checked(ids)
        print("Отмечено проверенными:", len(ids))
        return 0

    api_key = load_api_key(args.api_key)
    if not api_key:
        print("Нужен ключ TMDb, чтобы запросить новые постеры.")
        return 1

    client = TMDBClient(api_key, "ru-RU")
    fixed = 0

    def fetch(item: tuple[int, str]) -> tuple[int, str | None]:
        movie_id, _old = item
        for _attempt in range(2):
            try:
                data = client.get(f"/movie/{movie_id}")
            except TMDBError:
                continue
            return movie_id, (data.get("poster_path") or None)
        return movie_id, None

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch, item) for item in dead]
        for done, future in enumerate(as_completed(futures), 1):
            movie_id, poster_path = future.result()
            if poster_path:
                db.update_poster(movie_id, poster_path)
                fixed += 1
            if done % 100 == 0:
                print(f"  запрошено {done}/{len(dead)}, обновлено {fixed}", flush=True)

    all_ids = [movie_id for movie_id, _ in candidates]
    db.mark_posters_checked(all_ids)

    print("\n" + "=" * 52)
    print(f"Проверено: {len(candidates)}  Битых было: {len(dead)}  Заменено: {fixed}")
    print(f"Отмечено проверенными: {len(all_ids)}")
    print(f"Время: {time.time() - started:.0f} c")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
