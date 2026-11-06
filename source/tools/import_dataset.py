"""Импорт готовых баз фильмов в формате приложения.

Поддерживаются три распространённых набора:

  kaggle-tmdb   movies_metadata.csv из Kaggle «The Movies Dataset» (45 000 фильмов
                TMDb: описание, постер, страны, жанры, рейтинг)
  imdb          title.basics.tsv.gz + title.ratings.tsv.gz с datasets.imdbws.com
                (полный IMDb: год, жанры, рейтинг и число голосов)
  movielens     movies.csv (+ links.csv) с files.grouplens.org
                (названия, годы, жанры, привязка к imdb/tmdb)

Примеры:
    python tools/import_dataset.py kaggle-tmdb movies_metadata.csv
    python tools/import_dataset.py imdb title.basics.tsv.gz title.ratings.tsv.gz --min-votes 1000
    python tools/import_dataset.py movielens ml-latest-small\\movies.csv ml-latest-small\\links.csv

Постеры из Kaggle-набора скачиваются автоматически при показе карточки
(в файле есть poster_path — тот же TMDb CDN, ключ не нужен).
"""

from __future__ import annotations

import argparse
import ast
import csv
import gzip
import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Iterable, Iterator

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import DB_PATH  # noqa: E402
from movie_search.const import COUNTRIES  # noqa: E402
from movie_search.database import MovieDB, norm_countries, norm_list  # noqa: E402

# Английские названия жанров -> канонические русские (как в const.GENRE_IDS).
GENRE_EN_RU = {
    "action": "боевик",
    "adventure": "приключения",
    "animation": "мультфильм",
    "anime": "мультфильм",
    "comedy": "комедия",
    "crime": "криминал",
    "documentary": "документальный",
    "drama": "драма",
    "family": "семейный",
    "children": "семейный",
    "fantasy": "фэнтези",
    "history": "история",
    "horror": "ужасы",
    "music": "музыка",
    "musical": "музыка",
    "mystery": "детектив",
    "film-noir": "детектив",
    "romance": "мелодрама",
    "science fiction": "фантастика",
    "sci-fi": "фантастика",
    "thriller": "триллер",
    "war": "военный",
    "western": "вестерн",
    "tv movie": None,
    "talk-show": None,
    "imax": None,
    "(no genres listed)": None,
}

YEAR_RE = re.compile(r"\((\d{4})\)\s*$")
IMDB_ID_RE = re.compile(r"^tt(\d+)$")


def genre_ru(names: Iterable[str]) -> list[str]:
    result: list[str] = []
    for name in names:
        mapped = GENRE_EN_RU.get(str(name).strip().lower())
        if mapped and mapped not in result:
            result.append(mapped)
    return result


def year_of(value: Any) -> int | None:
    """Достаёт год из 'Toy Story (1995)', '1995-11-22' или 1995."""
    text = str(value or "").strip()
    match = YEAR_RE.search(text)
    if match:
        return int(match.group(1))
    match = re.match(r"^(\d{4})", text)
    return int(match.group(1)) if match else None


def parse_jsonish(value: Any) -> list[dict]:
    """Kaggle хранит списки Python-представлением: [{'id': 16, 'name': 'Animation'}]."""
    text = str(value or "").strip()
    if not text or text in ("[]", "nan"):
        return []
    try:
        data = ast.literal_eval(text)
    except (ValueError, SyntaxError):
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def imdb_key(imdb_id: str | None) -> int | None:
    """Стабильный отрицательный id для записей IMDb/MovieLens (TMDb — положительные)."""
    if not imdb_id:
        return None
    match = IMDB_ID_RE.match(str(imdb_id).strip())
    if not match:
        return None
    return -(int(match.group(1)) + 10_000_000)


def open_text(path: Path):
    # utf-8-sig отбрасывает BOM, если файл сохранён «как UTF-8 с BOM».
    if path.suffix == ".gz":
        return gzip.open(path, "rt", encoding="utf-8-sig", errors="replace", newline="")
    return path.open("r", encoding="utf-8-sig", errors="replace", newline="")


def reader(
    path: Path, delimiter: str = ",", quoting: int = csv.QUOTE_MINIMAL
) -> Iterator[dict[str, str]]:
    with open_text(path) as handle:
        sample = handle.read(4096)
        handle.seek(0)
        first_line = sample.splitlines()[0] if sample else ""
        dialect = csv.excel_tab if delimiter == "\t" or "\t" in first_line else csv.excel
        for row in csv.DictReader(handle, dialect=dialect, quoting=quoting):
            yield row


class Importer:
    def __init__(self, db: MovieDB, *, limit: int = 0, skip_existing: bool = True) -> None:
        self.db = db
        self.limit = limit
        self.skip_existing = skip_existing
        self.existing = db.existing_ids()
        # Один и тот же фильм приходит из Kaggle с id TMDb, а из IMDb/MovieLens —
        # с отрицательным id. Дедупликация по imdb_id не даёт завести дубль.
        self.existing_imdb = db.existing_imdb_ids()
        self.added = 0
        self.skipped = 0
        self.seen: set[int] = set()
        self.seen_imdb: set[str] = set()
        self._batch: list[dict[str, Any]] = []
        self.started = time.time()

    def push(self, movie: dict[str, Any]) -> None:
        movie_id = int(movie["id"])
        if movie_id in self.seen:
            self.skipped += 1
            return
        self.seen.add(movie_id)
        imdb_id = str(movie.get("imdb_id") or "").strip().lower()
        if imdb_id:
            if imdb_id in self.seen_imdb:
                self.skipped += 1
                return
            if imdb_id in self.existing_imdb and movie_id not in self.existing:
                self.skipped += 1
                return
            self.seen_imdb.add(imdb_id)
        if self.skip_existing and movie_id in self.existing:
            self.skipped += 1
            return
        self._batch.append(movie)
        self.added += 1
        if len(self._batch) >= 500:
            self.flush()
        if self.added % 5000 == 0:
            self.report()

    def flush(self) -> None:
        if self._batch:
            self.db.upsert_many(self._batch)
            self._batch.clear()

    def report(self) -> None:
        elapsed = max(1.0, time.time() - self.started)
        print(
            f"  принято {self.added}, пропущено {self.skipped}, "
            f"{self.added / elapsed:.0f} фильмов/с",
            flush=True,
        )

    def finish(self) -> dict[str, Any]:
        self.flush()
        stats = self.db.stats()
        return {
            "added": self.added,
            "skipped": self.skipped,
            "total": stats["total"],
            "with_poster": stats["with_poster"],
            "years": f"{stats['min_year']}–{stats['max_year']}",
        }


# --------------------------------------------------------------------- наборы
def import_kaggle(imp: Importer, path: Path) -> None:
    """movies_metadata.csv из Kaggle «The Movies Dataset»."""
    for index, row in enumerate(reader(path)):
        if index == 0 and "title" not in (row or {}):
            continue
        if str(row.get("adult", "")).strip().lower() == "true":
            continue
        title = (row.get("title") or "").strip()
        release = (row.get("release_date") or "").strip()
        year = year_of(release)
        if not title or not year:
            continue

        genres = genre_ru(g["name"] for g in parse_jsonish(row.get("genres")) if g.get("name"))
        countries = [
            item.get("iso_3166_1", "")
            for item in parse_jsonish(row.get("production_countries"))
        ]
        countries = [code for code in countries if code in COUNTRIES]

        try:
            rating = round(float(row.get("vote_average") or 0), 1) or None
        except ValueError:
            rating = None
        try:
            votes = int(float(row.get("vote_count") or 0))
        except ValueError:
            votes = 0
        try:
            runtime = int(float(row.get("runtime") or 0)) or None
        except ValueError:
            runtime = None

        imp.push(
            {
                "id": int(row["id"]),
                "title": title,
                "original_title": (row.get("original_title") or "").strip() or None,
                "year": year,
                "release_date": release or None,
                "overview": (row.get("overview") or "").strip() or None,
                "tagline": (row.get("tagline") or "").strip() or None,
                "rating": rating,
                "votes": votes,
                "genres": norm_list(genres),
                "countries": norm_countries(countries),
                "runtime": runtime,
                "director": None,
                "poster_path": (row.get("poster_path") or "").strip() or None,
                "poster_file": None,
                "poster_url": None,
                "source": "kaggle",
                "imdb_id": (row.get("imdb_id") or "").strip() or None,
                "link": None,
            }
        )
        if imp.limit and imp.added >= imp.limit:
            print(f"  достигнут лимит {imp.limit}")
            return


def import_imdb(imp: Importer, basics: Path, ratings: Path, min_votes: int) -> None:
    """title.basics.tsv.gz + title.ratings.tsv.gz: полный IMDb без постеров."""
    print("  читаю рейтинги…", flush=True)
    votes: dict[str, tuple[float, int]] = {}
    for row in reader(ratings, "\t", csv.QUOTE_NONE):
        tconst = (row.get("tconst") or "").strip()
        try:
            votes[tconst] = (float(row["averageRating"]), int(row["numVotes"]))
        except (KeyError, ValueError):
            continue
    print(f"  рейтингов: {len(votes)}", flush=True)

    for row in reader(basics, "\t", csv.QUOTE_NONE):
        if (row.get("titleType") or "").strip() != "movie":
            continue
        if str(row.get("isAdult") or "0").strip() == "1":
            continue
        tconst = (row.get("tconst") or "").strip()
        stats = votes.get(tconst)
        if not stats or stats[1] < min_votes:
            continue
        year = year_of(row.get("startYear"))
        title = (row.get("primaryTitle") or "").strip()
        movie_id = imdb_key(tconst)
        if not title or not year or movie_id is None:
            continue

        genres = genre_ru((row.get("genres") or "").split(","))
        try:
            runtime = int(row.get("runtimeMinutes") or 0) or None
        except ValueError:
            runtime = None

        imp.push(
            {
                "id": movie_id,
                "title": title,
                "original_title": (row.get("originalTitle") or "").strip() or None,
                "year": year,
                "release_date": None,
                "overview": None,
                "tagline": None,
                "rating": round(stats[0], 1),
                "votes": stats[1],
                "genres": norm_list(genres),
                "countries": "",
                "runtime": runtime,
                "director": None,
                "poster_path": None,
                "poster_file": None,
                "poster_url": None,
                "source": "imdb",
                "imdb_id": tconst,
                "link": f"https://www.imdb.com/title/{tconst}/",
            }
        )
        if imp.limit and imp.added >= imp.limit:
            print(f"  достигнут лимит {imp.limit}")
            return


def import_movielens(imp: Importer, movies: Path, links: Path | None) -> None:
    """movies.csv (+ links.csv) с files.grouplens.org."""
    by_movie: dict[str, dict[str, str]] = {}
    if links and links.exists():
        for row in reader(links):
            by_movie[(row.get("movieId") or "").strip()] = row

    for row in reader(movies):
        raw_title = (row.get("title") or "").strip()
        year = year_of(raw_title)
        if not raw_title or not year:
            continue
        title = YEAR_RE.sub("", raw_title).strip()
        genres = genre_ru((row.get("genres") or "").split("|"))
        link = by_movie.get((row.get("movieId") or "").strip(), {})
        imdb_id = f"tt{int(link['imdbId']):07d}" if link.get("imdbId") else None
        movie_id = imdb_key(imdb_id) or -(int(float(row.get("movieId") or 0)) + 20_000_000)
        tmdb_id = link.get("tmdbId")

        imp.push(
            {
                "id": movie_id,
                "title": title,
                "original_title": None,
                "year": year,
                "release_date": None,
                "overview": None,
                "tagline": None,
                "rating": None,
                "votes": None,
                "genres": norm_list(genres),
                "countries": "",
                "runtime": None,
                "director": None,
                "poster_path": None,
                "poster_file": None,
                "poster_url": None,
                "source": "movielens",
                "imdb_id": imdb_id,
                "link": f"https://www.themoviedb.org/movie/{tmdb_id}" if tmdb_id else None,
            }
        )
        if imp.limit and imp.added >= imp.limit:
            print(f"  достигнут лимит {imp.limit}")
            return


def apply_credits(db: MovieDB, path: Path) -> tuple[int, int]:
    """Режиссёры и актёры из credits.csv (crew → Director, cast → первые 10)."""
    # В Kaggle-файле поля длиннее стандартного лимита csv (131 072 байта).
    csv.field_size_limit(10**7)

    def parse(raw: str) -> list:
        """Поля записаны как Python-repr: [{'job': 'Director', ...}]."""
        raw = (raw or "").strip()
        if not raw:
            return []
        for parser in (json.loads, ast.literal_eval):
            try:
                data = parser(raw)
            except (ValueError, SyntaxError):
                continue
            return data if isinstance(data, list) else []
        return []

    directors = 0
    cast_rows: list[tuple[int, str, int]] = []
    cast_total = 0

    for row in reader(path):
        raw_id = (row.get("id") or "").strip()
        if not raw_id.isdigit():
            continue
        movie_id = int(raw_id)

        names: list[str] = []
        for person in parse(row.get("crew")):
            if isinstance(person, dict) and person.get("job") == "Director":
                name = str(person.get("name") or "").strip()
                if name and name not in names:
                    names.append(name)
        if names:
            directors += db.fill_directors([(", ".join(names)[:160], movie_id)])

        cast: list[tuple[int, str]] = []
        for person in parse(row.get("cast")):
            if not isinstance(person, dict):
                continue
            name = str(person.get("name") or "").strip()
            if not name:
                continue
            try:
                position = int(person.get("order") or 0)
            except (TypeError, ValueError):
                position = 0
            cast.append((position, name))
        cast.sort()
        for position, name in cast[:10]:
            cast_rows.append((movie_id, name, position))
        if len(cast_rows) >= 5000:
            cast_total += db.set_cast(cast_rows)
            cast_rows.clear()

    if cast_rows:
        cast_total += db.set_cast(cast_rows)
    return directors, cast_total


def apply_keywords(db: MovieDB, path: Path) -> int:
    """Ключевые слова из keywords.csv (нужны для «похожих фильмов»)."""
    csv.field_size_limit(10**7)
    total = 0
    batch: list[tuple[int, str]] = []

    for row in reader(path):
        raw_id = (row.get("id") or "").strip()
        if not raw_id.isdigit():
            continue
        movie_id = int(raw_id)
        raw = (row.get("keywords") or "").strip()
        if not raw:
            continue
        try:
            items = json.loads(raw)
        except ValueError:
            try:
                items = ast.literal_eval(raw)
            except (ValueError, SyntaxError):
                continue
        for item in items if isinstance(items, list) else []:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip().lower()
            if name:
                batch.append((movie_id, name))
        if len(batch) >= 5000:
            total += db.set_keywords(batch)
            batch.clear()

    if batch:
        total += db.set_keywords(batch)
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Импорт готовой базы фильмов")
    parser.add_argument(
        "preset", choices=["kaggle-tmdb", "imdb", "movielens"], help="формат набора"
    )
    parser.add_argument("files", nargs="+", help="файлы набора")
    parser.add_argument("--db", default=str(DB_PATH), help="куда импортировать")
    parser.add_argument("--limit", type=int, default=0, help="взять только N фильмов")
    parser.add_argument(
        "--overwrite", action="store_true", help="перезаписывать уже существующие записи"
    )
    parser.add_argument(
        "--min-votes", type=int, default=500, help="для imdb: минимум голосов (по умолчанию 500)"
    )
    parser.add_argument(
        "--credits", default="", help="для kaggle: credits.csv — режиссёры и актёры"
    )
    parser.add_argument(
        "--keywords", default="", help="для kaggle: keywords.csv — ключевые слова"
    )
    args = parser.parse_args()

    files = [Path(item) for item in args.files]
    for path in files:
        if not path.exists():
            print(f"Файл не найден: {path}")
            return 1

    db = MovieDB(Path(args.db))
    imp = Importer(db, limit=args.limit, skip_existing=not args.overwrite)
    print(f"До импорта: {db.stats()['total']} фильмов")

    started = time.time()
    if args.preset == "kaggle-tmdb":
        import_kaggle(imp, files[0])
    elif args.preset == "imdb":
        if len(files) < 2:
            print("Для imdb нужны два файла: title.basics.tsv.gz и title.ratings.tsv.gz")
            return 1
        import_imdb(imp, files[0], files[1], args.min_votes)
    elif args.preset == "movielens":
        import_movielens(imp, files[0], files[1] if len(files) > 1 else None)

    result = imp.finish()
    if args.credits:
        print("\nЧитаю credits.csv (режиссёры и актёры)…", flush=True)
        directors, cast = apply_credits(db, Path(args.credits))
        print(f"  режиссёров: {directors}, актёров: {cast}")
        result = imp.finish()
    if args.keywords:
        print("\nЧитаю keywords.csv…", flush=True)
        keywords = apply_keywords(db, Path(args.keywords))
        print(f"  ключевых слов: {keywords}")
    elapsed = time.time() - started
    print("\n" + "=" * 52)
    print(f"Принято: {result['added']}  Пропущено: {result['skipped']}  ({elapsed:.0f} c)")
    print(f"В базе: {result['total']} фильмов, постеров: {result['with_poster']}, годы: {result['years']}")
    if args.preset == "kaggle-tmdb":
        print("Постеры TMDb подгрузятся при показе карточек (ключ не нужен).")
    else:
        print(
            "В этом наборе нет постеров и описаний — их добавят «Обновить базу (TMDb)»\n"
            "или импорт Kaggle-набора."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
