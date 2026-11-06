"""Индекс легальных страниц фильмов на Мосфильме.

Каталог студии (1612 фильмов) отдаёт карточки со ссылками вида
/cinema/films/<slug>/, а на странице фильма есть «Смотреть фильм» с плеером
(YouTube / RuTube / VK). Скрипт собирает каталог, сопоставляет его с базой
по названию и году и сохраняет ссылки в таблицу watch_links.

Запуск:
    python tools/build_watch_index.py                # весь каталог (~65 страниц)
    python tools/build_watch_index.py --pages 5      # пробный прогон
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urljoin

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import DB_PATH, Config  # noqa: E402
from movie_search.database import MovieDB  # noqa: E402
from movie_search.library import normalize  # noqa: E402
from movie_search.tmdb_sync import TMDBClient, TMDBError, details_to_row  # noqa: E402

BASE = "https://www.mosfilm.ru/cinema/films/"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) MovieFinder/1.0"

CARD_RE = re.compile(
    r'href="/cinema/films/([a-z0-9\-]+)/"[\s\S]{0,600}?'
    r'card-shiny__title[^>]*>([^<]+)</div>[\s\S]{0,300}?<span>(\d{4})</span>'
)


def fetch_page(session: requests.Session, page: int) -> str:
    url = BASE if page == 1 else f"{BASE}?PAGEN_1={page}"
    response = session.get(url, timeout=40, headers={"User-Agent": USER_AGENT})
    response.raise_for_status()
    return response.text


def parse_cards(markup: str) -> list[tuple[str, str, int]]:
    """(slug, title, year) из HTML страницы каталога."""
    cards: list[tuple[str, str, int]] = []
    for slug, raw_title, year in CARD_RE.findall(markup):
        title = html_lib.unescape(raw_title or "").strip().strip('"')
        if title and year.isdigit():
            cards.append((slug, title, int(year)))
    return cards


ARCHIVE_SEARCH = "https://archive.org/advancedsearch.php"
ARCHIVE_QUERIES = (
    "collection:feature_films AND year:[1800 TO 1929]",
    "collection:silent_films",
)


def fetch_archive_items(rows_per_page: int = 1000) -> list[tuple[str, str, int]]:
    """(identifier, title, year) из Internet Archive — только общественное достояние."""
    session = requests.Session()
    items: list[tuple[str, str, int]] = []
    seen: set[str] = set()

    for query in ARCHIVE_QUERIES:
        page = 1
        while True:
            params = {
                "q": query,
                "fl[]": ["identifier", "title", "year"],
                "rows": rows_per_page,
                "page": page,
                "output": "json",
            }
            try:
                response = session.get(
                    ARCHIVE_SEARCH, params=params, timeout=60, headers={"User-Agent": USER_AGENT}
                )
                response.raise_for_status()
                docs = ((response.json().get("response") or {}).get("docs")) or []
            except (requests.RequestException, ValueError) as exc:
                print(f"  архив, страница {page}: {exc}")
                break
            if not docs:
                break
            for doc in docs:
                identifier = str(doc.get("identifier") or "").strip()
                title = str(doc.get("title") or "").strip()
                if not identifier or not title or identifier in seen:
                    continue
                year = 0
                raw_year = str(doc.get("year") or "").strip()
                if raw_year[:4].isdigit():
                    year = int(raw_year[:4])
                else:
                    match = re.search(r"(1[89]\d{2}|20\d{2})", title)
                    if match:
                        year = int(match.group(1))
                if not year:
                    continue
                title = re.sub(r"\s*\(\d{4}\)\s*$", "", title).strip()
                seen.add(identifier)
                items.append((identifier, title, year))
            print(f"  архив: {query[:40]}… страница {page} ({len(items)} записей)", flush=True)
            if len(docs) < rows_per_page:
                break
            page += 1
    return items


def lookup_movie(
    by_title_year: dict[tuple[str, int], int],
    by_title: dict[str, list[tuple[int, int]]],
    title: str,
    year: int,
) -> int | None:
    """Ищет фильм по названию и году (±1); однозначное название — без года."""
    key = normalize(title)
    if not key:
        return None
    movie_id = (
        by_title_year.get((key, year))
        or by_title_year.get((key, year + 1))
        or by_title_year.get((key, year - 1))
    )
    if movie_id is None:
        candidates = by_title.get(key) or []
        if len(candidates) == 1:
            movie_id = candidates[0][0]
    return movie_id


def match_via_api(
    cards: list[tuple[str, str, int]], api_key: str, workers: int = 4
) -> dict[str, int]:
    """Русское название Мосфильма -> id TMDb через поиск по названию и году.

    Каталог студии на русском, а база (Kaggle) — на английском, поэтому прямое
    сравнение названий работает плохо. Поиск TMDb решает это точно.
    """
    if not api_key:
        return {}
    client = TMDBClient(api_key, "ru-RU")
    found: dict[str, int] = {}

    def lookup(card: tuple[str, str, int]) -> tuple[str, int | None]:
        slug, title, year = card
        for _attempt in range(2):
            try:
                data = client.get(
                    "/search/movie", query=title, year=year, include_adult="false"
                )
            except TMDBError:
                continue
            for item in (data.get("results") or [])[:5]:
                release = str(item.get("release_date") or "")
                item_year = int(release[:4]) if release[:4].isdigit() else 0
                if item.get("id") and abs(item_year - year) <= 1:
                    return slug, int(item["id"])
            return slug, None
        return slug, None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(lookup, card) for card in cards]
        for done, future in enumerate(as_completed(futures), 1):
            slug, movie_id = future.result()
            if movie_id is not None:
                found[slug] = movie_id
            if done % 100 == 0:
                print(f"  поиск TMDb: {done}/{len(cards)}, найдено {len(found)}", flush=True)
    return found


def load_api_key(explicit: str = "") -> str:
    """Ключ TMDb: аргумент, конфиг проекта или конфиг установленного приложения."""
    if explicit:
        return explicit.strip()
    key = Config().api_key
    if key:
        return key
    candidates = [
        Path(os.environ.get("USERPROFILE", "")) / "Movie Finder" / "config.json",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Movie Finder" / "config.json",
    ]
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if data.get("tmdb_api_key"):
            return str(data["tmdb_api_key"]).strip()
    return ""


def add_missing_movies(
    db: MovieDB, api_key: str, movie_ids: list[int], workers: int = 5
) -> int:
    """Догружает фильмы Мосфильма, которых нет в базе (постеры + описания)."""
    if not api_key or not movie_ids:
        return 0
    client = TMDBClient(api_key, "ru-RU")
    batch: list[dict] = []
    added = 0

    def fetch(movie_id: int) -> dict | None:
        try:
            details = client.movie_details(movie_id)
        except TMDBError:
            return None
        return details_to_row(details) if details else None

    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(fetch, movie_id) for movie_id in movie_ids]
        for done, future in enumerate(as_completed(futures), 1):
            row = future.result()
            if row:
                batch.append(row)
                added += 1
            if len(batch) >= 200:
                db.upsert_many(batch)
                batch.clear()
            if done % 100 == 0:
                print(f"  догрузка фильмов: {done}/{len(movie_ids)}, добавлено {added}", flush=True)
    if batch:
        db.upsert_many(batch)
    return added


def run_archive(
    db: MovieDB,
    by_title_year: dict[tuple[str, int], int],
    by_title: dict[str, list[tuple[int, int]]],
) -> int:
    """Индекс Internet Archive: только фильмы в общественном достоянии (до 1930)."""
    print("Собираю каталог Internet Archive (общественное достояние)…")
    items = fetch_archive_items()
    print(f"  фильмов в каталоге: {len(items)}")

    rows: list[tuple[int, str, str, str]] = []
    matched: set[int] = set()
    for identifier, title, year in items:
        movie_id = lookup_movie(by_title_year, by_title, title, year)
        if movie_id is None or movie_id in matched:
            continue
        matched.add(movie_id)
        rows.append(
            (
                movie_id,
                "Internet Archive",
                f"https://archive.org/details/{identifier}",
                title,
            )
        )

    if rows:
        db.set_watch_links(rows)
    print("\n" + "=" * 52)
    print(f"В каталоге архива: {len(items)} фильмов")
    print(f"Сопоставлено с базой: {len(rows)}")
    print(f"Всего ссылок в базе: {db.watch_links_count()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Индекс легальных страниц фильмов")
    parser.add_argument(
        "--source",
        choices=["mosfilm", "archive"],
        default="mosfilm",
        help="mosfilm — каталог Мосфильма, archive — общественное достояние",
    )
    parser.add_argument("--db", default=str(DB_PATH))
    parser.add_argument("--pages", type=int, default=0, help="ограничить число страниц")
    parser.add_argument("--pause", type=float, default=0.4, help="пауза между запросами")
    parser.add_argument(
        "--via-api",
        action="store_true",
        help="сопоставлять русские названия через поиск TMDb (нужен ключ)",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--api-key", default="", help="ключ TMDb (иначе берётся из настроек)")
    parser.add_argument(
        "--add-missing",
        action="store_true",
        help="догрузить отсутствующие фильмы Мосфильма из TMDb (с постерами)",
    )
    args = parser.parse_args()

    db = MovieDB(Path(args.db))
    print(f"База: {args.db} ({db.count()} фильмов)")

    # Индекс названий из базы: (нормализованное название, год) -> id
    by_title_year: dict[tuple[str, int], int] = {}
    by_title: dict[str, list[tuple[int, int]]] = {}
    for movie_id, title, original, year in db.titles_index():
        for name in {normalize(title), normalize(original)}:
            if not name:
                continue
            if year:
                by_title_year.setdefault((name, year), movie_id)
            by_title.setdefault(name, []).append((movie_id, year))

    if args.source == "archive":
        return run_archive(db, by_title_year, by_title)

    session = requests.Session()
    seen: set[str] = set()
    catalog: list[tuple[str, str, int]] = []
    rows: list[tuple[int, str, str, str]] = []
    unmatched: list[tuple[str, str, int]] = []
    page = 1
    max_pages = args.pages or 70

    while page <= max_pages:
        try:
            markup = fetch_page(session, page)
        except requests.RequestException as exc:
            print(f"  страница {page}: ошибка {exc}")
            break
        cards = parse_cards(markup)
        if not cards:
            break
        new_cards = 0
        for slug, title, year in cards:
            if slug in seen:
                continue
            seen.add(slug)
            new_cards += 1
            catalog.append((slug, title, year))
            key = normalize(title)
            movie_id = by_title_year.get((key, year)) or by_title_year.get((key, year + 1)) \
                or by_title_year.get((key, year - 1))
            if movie_id is None:
                candidates = by_title.get(key) or []
                if len(candidates) == 1:
                    movie_id = candidates[0][0]
            if movie_id is None:
                unmatched.append((slug, title, year))
                continue
            rows.append((movie_id, "Мосфильм", urljoin(BASE, f"{slug}/"), title))
        print(
            f"  страница {page}: новых {new_cards}, всего в каталоге {len(catalog)}, "
            f"сопоставлено {len(rows)}",
            flush=True,
        )
        if not new_cards:
            break  # сайт начал повторять страницы
        page += 1
        time.sleep(args.pause)

    if args.via_api and unmatched:
        api_key = load_api_key(args.api_key)
        if not api_key:
            print("\nДля --via-api нужен ключ TMDb (Настройки приложения).")
        else:
            print(f"\nСопоставляю через TMDb: {len(unmatched)} фильмов…")
            existing = db.existing_ids()
            found = match_via_api(unmatched, api_key, args.workers)
            missing = [movie_id for movie_id in found.values() if movie_id not in existing]
            if args.add_missing and missing:
                print(f"Догружаю отсутствующие в базе: {len(missing)} фильмов…")
                added = add_missing_movies(db, api_key, missing, args.workers)
                print(f"  добавлено в базу: {added}")
                existing |= set(missing)
            used = 0
            by_slug = {slug: (title, year) for slug, title, year in unmatched}
            for slug, movie_id in found.items():
                if movie_id not in existing:
                    continue
                title, _year = by_slug.get(slug, ("", 0))
                rows.append((movie_id, "Мосфильм", urljoin(BASE, f"{slug}/"), title))
                used += 1
            print(f"  через TMDb сопоставлено: {used}")

    if rows:
        db.set_watch_links(rows)
    print("\n" + "=" * 52)
    print(f"В каталоге Мосфильма: {len(catalog)} фильмов")
    print(f"Сопоставлено с базой: {len(rows)}")
    print(f"Ссылок в базе: {db.watch_links_count()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
