"""Сборка офлайн-каталога: постеры и описания из русской Википедии.

Запуск:
    python tools/build_catalog.py            # полная сборка
    python tools/build_catalog.py --limit 20 # первые 20 фильмов (проверка)

Каждая запись из tools/catalog_seed.py ищется через API ru.wikipedia.org
(generator=search + prop=pageimages|extracts), затем постер скачивается в
data/posters. В итоге создаётся data/movies.db, с которым приложение
работает полностью без интернета.
"""

from __future__ import annotations

import argparse
import io
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from catalog_seed import SEED  # noqa: E402

from movie_search.config import DB_PATH, POSTER_DIR  # noqa: E402
from movie_search.const import COUNTRIES, GENRE_IDS  # noqa: E402
from movie_search.database import MovieDB, norm_countries, norm_list  # noqa: E402

API = "https://ru.wikipedia.org/w/api.php"
USER_AGENT = "MovieFinder/1.0 (offline catalog builder; personal use)"
VALID_GENRES = set(GENRE_IDS.values())
MAX_EXTRACT = 1200

# Уточнения в скобках, которые означают «это не тот фильм».
BAD_PAREN = (
    "франшиза",
    "саундтрек",
    "персонаж",
    "сериал",
    "телесериал",
    "игра",
    "роман",
    "книга",
    "альбом",
    "мюзикл",
    "песня",
    "сингл",
    "студия",
    "премия",
    "список",
    "категория",
    "шаблон",
    "комикс",
)

_tls = threading.local()

# Wikipedia ограничивает частоту: все запросы к API и к картинкам идут через
# общий «замок» с минимальным интервалом, плюс повторы при 429.
_api_lock = threading.Lock()
_api_last_at = [0.0]
API_INTERVAL = 0.65

_image_lock = threading.Lock()
_last_image_at = [0.0]
IMAGE_INTERVAL = 0.9


def _throttle(lock: threading.Lock, last_at: list[float], interval: float) -> None:
    with lock:
        wait = interval - (time.time() - last_at[0])
        if wait > 0:
            time.sleep(wait)
        last_at[0] = time.time()


def _throttle_api() -> None:
    _throttle(_api_lock, _api_last_at, API_INTERVAL)


def _throttle_image() -> None:
    _throttle(_image_lock, _last_image_at, IMAGE_INTERVAL)



def _session() -> requests.Session:
    session = getattr(_tls, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        _tls.session = session
    return session


def _api(params: dict) -> dict:
    base = {"action": "query", "format": "json", "formatversion": 2}
    base.update(params)
    last_error: Exception | None = None
    for attempt in range(6):
        _throttle_api()
        try:
            resp = _session().get(API, params=base, timeout=30)
        except requests.RequestException as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
            continue
        if resp.status_code == 429:
            retry_after = resp.headers.get("Retry-After") or ""
            delay = float(retry_after) if retry_after.isdigit() else 5.0 * (attempt + 1)
            time.sleep(min(delay, 30.0))
            last_error = RuntimeError("HTTP 429")
            continue
        if resp.status_code >= 500:
            time.sleep(2.0 * (attempt + 1))
            last_error = RuntimeError(f"HTTP {resp.status_code}")
            continue
        if not resp.ok:
            raise RuntimeError(f"Wikipedia API: HTTP {resp.status_code}")
        try:
            return resp.json()
        except ValueError as exc:
            last_error = exc
            time.sleep(1.0 * (attempt + 1))
    raise RuntimeError(f"Wikipedia API error: {last_error}")


def normalize_title(text: str) -> str:
    """Сравнение названий: без регистра, «ё», кавычек, лишних пробелов и пунктуации."""
    text = (text or "").lower().replace("ё", "е")
    for ch in "«»\"'`":
        text = text.replace(ch, "")
    text = text.replace("·", "-").replace("•", "-")
    text = re.sub(r"\s*№\s*", "№", text)  # «Район № 9» == «Район №9»
    return " ".join(text.split()).strip(" .,:;!-—–")


_YEAR_RE = re.compile(r"\b(19[0-9]{2}|20[0-3][0-9])\b")

FILM_WORDS = (
    "фильм",
    "мультфильм",
    "кинокартина",
    "боевик",
    "комеди",
    "драм",
    "триллер",
    "мелодрам",
    "вестерн",
    "ужас",
    "фэнтези",
    "детектив",
    "аниме",
    "экранизац",
)


def score_page(page: dict, title: str, year: int) -> int:
    """Оценивает кандидата: название статьи, уточнение в скобках, год."""
    page_title = page.get("title") or ""
    if normalize_title(page_title.split("(")[0]) != normalize_title(title):
        return -1  # «Один дома» не должен превращаться в «Один дома 2»

    lowered = page_title.lower()
    paren = lowered[lowered.find("(") + 1 : -1] if "(" in lowered else ""
    if any(bad in paren for bad in BAD_PAREN):
        return -1
    if "франшиза" in lowered or "саундтрек" in lowered:
        return -1

    score = 5
    if any(key in paren for key in ("фильм", "мультфильм", "кинокартина")):
        score += 3
    paren_years = set(_YEAR_RE.findall(paren))
    if str(year) in paren_years:
        score += 4
    elif paren_years:
        score -= 8  # «Король Лев (мультфильм, 2019)» — не фильм 1994 года
    if str(year) in page_title:
        score += 4
    category_years_value = category_years(page)
    if category_years_value:
        if year in category_years_value:
            score += 5
        else:
            score -= 6
    if page.get("thumbnail"):
        score += 1
    return score


def category_years(page: dict) -> set[int]:
    """Годы из категорий вида «Фильмы 1999 года» (десятилетия вроде «1990-х» не в счёт)."""
    years: set[int] = set()
    for category in page.get("categories") or []:
        title = category.get("title") or ""
        if not any(word in title for word in ("ильм", "ульт", "ино", "Аниме")):
            continue
        match = re.search(r"\b(19[0-9]{2}|20[0-3][0-9]) года\b", title)
        if match:
            years.add(int(match.group(1)))
    return years


def looks_like_film(page: dict, year: int) -> bool:
    text = (page.get("extract") or "").strip()
    if len(text) < 80:
        return False
    head = text.lower()[:900]
    page_title = (page.get("title") or "").lower()

    filmish = any(word in head for word in FILM_WORDS) or "фильм" in page_title
    if not filmish:
        return False

    # Самый надёжный признак — категория «Фильмы <год> года».
    strict_years = category_years(page)
    if strict_years:
        return year in strict_years

    # Если категорий нет: год должен стоять в самом начале статьи, иначе
    # легко поймать ремейк, упоминающий оригинал в середине текста.
    if str(year) in head:
        return True
    if set(_YEAR_RE.findall(head)):
        return False
    return str(year) in text


def find_page(title: str, year: int, hint: str | None = None) -> dict | None:
    """Один запрос на фильм: поиск, постер, описание и категории сразу."""
    queries: list[str] = []
    if hint:
        queries.append(f'intitle:"{hint}"')
    queries.append(f'intitle:"{title}" {year}')
    queries.append(f'intitle:"{title}"')
    queries.append(f"{title} {year} фильм")
    queries.append(f"{title} {year}")

    seen_queries: set[str] = set()
    for query in queries:
        if query in seen_queries:
            continue
        seen_queries.add(query)
        try:
            data = _api(
                {
                    "generator": "search",
                    "gsrsearch": query,
                    "gsrlimit": 6,
                    "prop": "pageimages|extracts|categories",
                    "exintro": 1,
                    "explaintext": 1,
                    "exlimit": 6,
                    "cllimit": "max",
                    "piprop": "thumbnail",
                    "pithumbsize": 500,
                    "pilicense": "any",
                    "redirects": 1,
                }
            )
        except RuntimeError as exc:
            print(f"    ! запрос не удался: {exc}")
            continue

        best: tuple[int, dict] | None = None
        # Если задана подсказка (точное имя статьи), сверяем название и с ней:
        # «Паддингтон» может лежать в статье «Приключения Паддингтона».
        variants = [title]
        if hint:
            variants.append(hint.split("(")[0].strip())
        for page in ((data.get("query") or {}).get("pages")) or []:
            score = max(score_page(page, variant, year) for variant in variants)
            if score < 5 or not looks_like_film(page, year):
                continue
            if best is None or score > best[0]:
                best = (score, page)
        if best:
            return best[1]
    return None


def clean_extract(text: str) -> str:
    text = " ".join((text or "").replace("\u200b", "").split())
    if len(text) <= MAX_EXTRACT:
        return text
    cut = text[:MAX_EXTRACT]
    for sep in (". ", "! ", "? "):
        pos = cut.rfind(sep)
        if pos > 200:
            return cut[: pos + 1].strip()
    return cut.rsplit(" ", 1)[0].strip() + "…"


def download_poster(url: str, target: Path) -> bool:
    url = url.split("?")[0]
    for attempt in range(4):
        _throttle_image()
        try:
            resp = _session().get(
                url, timeout=30, headers={"Referer": "https://ru.wikipedia.org/"}
            )
            if resp.status_code == 429:
                time.sleep(2.0 * (attempt + 1))
                continue
            resp.raise_for_status()
            content = resp.content
            if len(content) < 3000:
                return False
            with Image.open(io.BytesIO(content)) as probe:
                probe.verify()
            with Image.open(io.BytesIO(content)) as img:
                img = img.convert("RGB")
                if img.width > 600:
                    ratio = 600 / img.width
                    img = img.resize((600, max(1, int(img.height * ratio))), Image.LANCZOS)
                img.save(target, "JPEG", quality=88, optimize=True)
            return True
        except (requests.RequestException, OSError, ValueError):
            time.sleep(0.8 * (attempt + 1))
    return False


def build_one(item: tuple, index: int) -> tuple[dict | None, str]:
    """Возвращает (запись для БД, причина пропуска)."""
    title, en_title, year, genres, countries, rating = item[:6]
    hint = item[6] if len(item) > 6 else None

    page = find_page(title, year, hint)
    if not page:
        return None, "статья не найдена"

    extract = clean_extract(page.get("extract") or "")
    if len(extract) < 80:
        return None, "пустое описание"

    numeric_id = -(index + 1)
    poster_file = f"wiki_{abs(numeric_id)}.jpg"
    poster_url = ((page.get("thumbnail") or {}).get("source") or "").split("?")[0] or None
    if poster_url:
        if not download_poster(poster_url, POSTER_DIR / poster_file):
            poster_file = ""
    else:
        poster_file = ""

    if not poster_file and not poster_url:
        return None, "нет постера"

    genre_list = [g.strip().lower() for g in genres.split(",") if g.strip()]
    unknown = [g for g in genre_list if g not in VALID_GENRES]
    genre_list = [g for g in genre_list if g in VALID_GENRES]
    country_list = [c.strip().upper() for c in countries.split(",") if c.strip()]
    country_list = [c for c in country_list if c in COUNTRIES]

    record = {
        "id": numeric_id,
        "title": title,
        "original_title": en_title,
        "year": year,
        "release_date": None,
        "overview": extract,
        "tagline": None,
        "rating": rating,
        "votes": None,
        "genres": norm_list(genre_list),
        "countries": norm_countries(country_list),
        "runtime": None,
        "director": None,
        "poster_path": None,
        "poster_file": poster_file,
        "poster_url": poster_url,
        "source": "wiki",
        "imdb_id": None,
        "link": f"https://ru.wikipedia.org/?curid={page.get('pageid')}",
    }
    suffix = f" [жанры: {', '.join(unknown)}]" if unknown else ""
    status = f"ok ({page.get('title')}){suffix}"
    return record, status


def main() -> int:
    parser = argparse.ArgumentParser(description="Сборка офлайн-каталога фильмов")
    parser.add_argument("--limit", type=int, default=0, help="обработать только N записей")
    parser.add_argument("--workers", type=int, default=3, help="параллельных потоков")
    parser.add_argument(
        "--clean", action="store_true", help="удалить прежние wiki-записи перед сборкой"
    )
    args = parser.parse_args()

    POSTER_DIR.mkdir(parents=True, exist_ok=True)
    db = MovieDB(DB_PATH)

    items = SEED[: args.limit] if args.limit else SEED
    print(f"Записей к обработке: {len(items)}")

    if args.clean:
        with db._lock:  # noqa: SLF001 - служебная очистка при полной пересборке
            db._conn.execute("DELETE FROM movies WHERE source = 'wiki'")  # noqa: SLF001
            db._conn.commit()

    started = time.time()
    records: list[dict] = []
    skipped: list[tuple[str, int, str]] = []
    done = 0

    # Уже собранные фильмы (с постером и описанием) повторно не запрашиваем:
    # сборку можно прерывать и продолжать.
    existing: dict[int, dict] = {}
    for row in db.rows_by_source("wiki"):
        try:
            existing[abs(int(row["id"])) - 1] = row
        except (TypeError, ValueError):
            continue

    pending: list[tuple[int, tuple]] = []
    for idx, item in enumerate(items):
        row = existing.get(idx)
        if row and (row.get("poster_file") or "") and len(row.get("overview") or "") > 200:
            records.append(row)
            continue
        pending.append((idx, item))
    if records:
        print(f"Уже в базе: {len(records)} — пропускаю")

    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {
            pool.submit(build_one, item, idx): (item, idx) for idx, item in pending
        }
        for future in as_completed(futures):
            item, idx = futures[future]
            try:
                record, status = future.result()
            except Exception as exc:  # noqa: BLE001 - сборщик не должен падать целиком
                record, status = None, f"ошибка: {exc}"
            done += 1
            if record:
                records.append(record)
                print(f"[{done}/{len(pending)}] + {item[0]} ({item[2]}) — {status}")
                # Периодически сохраняем, чтобы прерванная сборка не теряла прогресс.
                if len(records) % 10 == 0:
                    db.upsert_many(records)
            else:
                skipped.append((item[0], item[2], status))
                print(f"[{done}/{len(pending)}] - {item[0]} ({item[2]}) — {status}")

    records.sort(key=lambda r: r["id"] * -1)
    if records:
        db.upsert_many(records)

    # Добиваем постеры, которые не скачались с первого раза (лимиты Wikimedia).
    missing = db.missing_posters()
    if missing:
        print(f"\nДокачиваю постеры: {len(missing)}")
        fixed = 0
        for row in missing:
            target = POSTER_DIR / f"wiki_{abs(row['id'])}.jpg"
            if download_poster(row.get("poster_url") or "", target):
                row["poster_file"] = target.name
                db.upsert_many([row])
                fixed += 1
                print(f"  + {row['title']}")
        print(f"Докачано постеров: {fixed}")

    db.set_meta("catalog_built", time.strftime("%Y-%m-%d %H:%M"))

    elapsed = time.time() - started
    stats = db.stats()
    print("\n" + "=" * 60)
    print(f"Обработано сейчас: {len(pending)}  Пропущено: {len(skipped)}  Время: {elapsed:.0f} c")
    print(f"В базе: {stats['total']} фильмов, постеров: {stats['with_poster']}")
    if skipped:
        print("\nПропущенные:")
        for title, year, why in skipped:
            print(f"  - {title} ({year}): {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
