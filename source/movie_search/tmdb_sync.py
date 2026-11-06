"""Синхронизация локальной базы с TMDb (нужен бесплатный API-ключ)."""

from __future__ import annotations

import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Iterable

import requests

from .const import GENRE_IDS, MAX_YEAR, MIN_YEAR, SYNC_FROM_YEAR, SYNC_TO_YEAR
from .database import DatabaseError, MovieDB, norm_countries, norm_list

TMDB_BASE = "https://api.themoviedb.org/3"
USER_AGENT = "MovieFinder/1.0"


class TMDBError(RuntimeError):
    """Ошибка обращения к TMDb."""


class TMDBClient:
    """Минимальный клиент TMDb с повторами и обработкой лимитов."""

    def __init__(self, api_key: str, language: str = "ru-RU") -> None:
        self.api_key = api_key
        self.language = language
        self._local = threading.local()

    def _session(self) -> requests.Session:
        session = getattr(self._local, "session", None)
        if session is None:
            session = requests.Session()
            session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})
            self._local.session = session
        return session

    def get(self, path: str, **params: Any) -> dict[str, Any]:
        params.setdefault("api_key", self.api_key)
        params.setdefault("language", self.language)
        url = TMDB_BASE + path
        last_error: Exception | None = None

        for attempt in range(4):
            try:
                resp = self._session().get(url, params=params, timeout=25)
            except requests.RequestException as exc:
                last_error = exc
                time.sleep(1.0 + attempt)
                continue

            if resp.status_code == 429:
                try:
                    delay = float(resp.headers.get("Retry-After", "1.5"))
                except ValueError:
                    delay = 1.5
                time.sleep(min(delay, 10.0))
                continue
            if resp.status_code == 401:
                raise TMDBError(
                    "TMDb отклонил ключ (401). Проверьте API Key (v3) в настройках."
                )
            if resp.status_code == 404:
                return {}
            if resp.status_code >= 500:
                last_error = TMDBError(f"TMDb вернул {resp.status_code}")
                time.sleep(1.0 + attempt)
                continue
            if not resp.ok:
                raise TMDBError(f"TMDb {resp.status_code}: {resp.text[:180]}")
            try:
                return resp.json()
            except ValueError as exc:
                raise TMDBError("TMDb вернул некорректный JSON") from exc

        raise TMDBError(f"Не удалось получить данные TMDb: {last_error}")

    def check_key(self) -> None:
        """Проверяет, что ключ рабочий."""
        self.get("/configuration")

    def discover_year(
        self, year: int, page: int, min_votes: int, countries: str = ""
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "vote_count.gte": min_votes,
            "primary_release_date.gte": f"{year}-01-01",
            "primary_release_date.lte": f"{year}-12-31",
            "include_adult": "false",
            "without_genres": "10770",
            "page": page,
        }
        if countries:
            # TMDb принимает несколько стран через «|», например "JP|HK".
            params["with_origin_country"] = countries
        return self.get("/discover/movie", sort_by="vote_count.desc", **params)

    def movie_details(self, movie_id: int) -> dict[str, Any]:
        return self.get(f"/movie/{movie_id}", append_to_response="credits")

    def collection_details(self, collection_id: int) -> dict[str, Any]:
        return self.get(f"/collection/{collection_id}")


def details_to_row(details: dict[str, Any]) -> dict[str, Any] | None:
    """Превращает ответ /movie/{id} в запись для локальной базы."""
    release = (details.get("release_date") or "").strip()
    year = int(release[:4]) if len(release) >= 4 and release[:4].isdigit() else None
    if not year or not (MIN_YEAR <= year <= MAX_YEAR):
        return None

    genres = [
        GENRE_IDS[g["id"]]
        for g in (details.get("genres") or [])
        if isinstance(g, dict) and g.get("id") in GENRE_IDS
    ]
    countries = [
        c.get("iso_3166_1", "")
        for c in (details.get("production_countries") or [])
        if isinstance(c, dict)
    ]
    crew = ((details.get("credits") or {}).get("crew")) or []
    directors = [p.get("name", "") for p in crew if p.get("job") == "Director"]
    director = ", ".join([d for d in directors if d])[:160] or None

    return {
        "id": int(details["id"]),
        "title": details.get("title") or details.get("original_title") or "Без названия",
        "original_title": details.get("original_title"),
        "year": year,
        "release_date": release or None,
        "overview": (details.get("overview") or "").strip() or None,
        "tagline": (details.get("tagline") or "").strip() or None,
        "rating": float(details.get("vote_average") or 0) or None,
        "votes": int(details.get("vote_count") or 0),
        "genres": norm_list(genres),
        "countries": norm_countries(countries),
        "runtime": int(details.get("runtime") or 0) or None,
        "director": director,
        "poster_path": details.get("poster_path"),
        "poster_file": None,
        "poster_url": None,
        "source": "tmdb",
        "imdb_id": details.get("imdb_id"),
        "link": f"https://www.themoviedb.org/movie/{details['id']}",
    }


class SyncJob:
    """Фоновая задача: собрать фильмы 1990–2026 из TMDb и сохранить в базу.

    Сообщения складываются в queue:
        ("log", text)
        ("progress", done, total, label)
        ("error", text)
        ("done", added_count)
    """

    def __init__(
        self,
        db: MovieDB,
        api_key: str,
        *,
        language: str = "ru-RU",
        pages: int = 3,
        min_votes: int = 40,
        workers: int = 8,
        years: Iterable[int] | None = None,
        countries: str = "",
    ) -> None:
        self.db = db
        self.api_key = api_key
        self.language = language
        self.pages = max(1, min(10, pages))
        self.min_votes = max(0, min_votes)
        self.workers = max(1, min(16, workers))
        self.countries = countries
        self.years = list(years or range(SYNC_FROM_YEAR, SYNC_TO_YEAR + 1))
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.saved = 0  # сколько записей реально записано в базу

    # -------------------------------------------------------------- запуск
    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="tmdb-sync", daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._stop.set()

    @property
    def running(self) -> bool:
        return bool(self._thread and self._thread.is_alive())

    def wait(self, timeout: float = 3.0) -> bool:
        """Ждёт завершения задачи. True — поток остановился."""
        if self._thread is None:
            return True
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _emit(self, *message: Any) -> None:
        self.queue.put(message)

    # ------------------------------------------------------------- процесс
    def _run(self) -> None:
        try:
            self._sync()
        except DatabaseError as exc:
            self._emit(
                "error",
                "Не удалось записать данные в базу.\n"
                f"{exc}\n"
                f"Уже сохранено фильмов: {self.saved}.\n"
                "Запустите загрузку ещё раз — уже сохранённые записи повторно не скачиваются.",
            )
        except TMDBError as exc:
            self._emit("error", str(exc))
        except Exception as exc:  # noqa: BLE001 - показываем пользователю любую ошибку
            self._emit("error", f"Неожиданная ошибка: {exc}")

    def _sync(self) -> None:
        client = TMDBClient(self.api_key, self.language)
        self._emit("log", "Проверяю API-ключ…")
        client.check_key()

        # Убираем офлайн-записи, которые уже есть в TMDb (в том числе после
        # прерванной прошлой загрузки).
        try:
            removed = self.db.remove_wiki_duplicates()
            if removed:
                self._emit("log", f"Убрано дублей офлайн-каталога: {removed}")
        except DatabaseError as exc:
            self._emit("log", f"Предупреждение: не удалось убрать дубли — {exc}")

        self._emit("log", "Ключ принят. Сканирую годы " f"{self.years[0]}–{self.years[-1]}.")

        collected: dict[int, dict] = {}
        total_years = len(self.years)
        for index, year in enumerate(self.years, 1):
            if self._stop.is_set():
                self._emit("log", "Остановлено пользователем.")
                return
            for page in range(1, self.pages + 1):
                data = client.discover_year(year, page, self.min_votes, self.countries)
                results = data.get("results") or []
                for movie in results:
                    genre_ids = movie.get("genre_ids") or []
                    if 10770 in genre_ids:  # телефильмы не нужны
                        continue
                    collected[int(movie["id"])] = movie
                last_page = min(int(data.get("total_pages") or 1), self.pages)
                if page >= last_page:
                    break
            self._emit(
                "progress", index, total_years, f"Список фильмов: {year} ({len(collected)} шт.)"
            )

        if not collected:
            self._emit("error", "TMDb не вернул ни одного фильма. Проверьте ключ и фильтры.")
            return

        already = self.db.existing_ids(with_details=True)
        todo = [mid for mid in sorted(collected) if mid not in already]
        self._emit(
            "log",
            f"Всего фильмов: {len(collected)}. Уже в базе с деталями: {len(already & set(collected))}.",
        )
        self._emit("log", f"Загружаю детали, постеры и страны: {len(todo)} шт.")

        batch: list[dict] = []
        added = 0
        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            futures = {pool.submit(self._fetch_details, client, mid): mid for mid in todo}
            for done, future in enumerate(as_completed(futures), 1):
                if self._stop.is_set():
                    for pending in futures:
                        pending.cancel()
                    self._emit("log", "Остановлено пользователем.")
                    break
                try:
                    row = future.result()
                except Exception:  # noqa: BLE001 - один фильм не должен ронять задачу
                    row = None
                if row:
                    batch.append(row)
                    added += 1
                if len(batch) >= 100:
                    self.saved += self.db.upsert_many(batch)
                    batch.clear()
                if done % 10 == 0 or done == len(todo):
                    self._emit("progress", done, len(todo), f"Детали: {done}/{len(todo)}")

        if batch:
            self.saved += self.db.upsert_many(batch)

        # Завершающие операции не должны обнулять уже проделанную работу:
        # фильмы к этому моменту сохранены, поэтому любые сбои здесь — предупреждение.
        try:
            removed = self.db.remove_wiki_duplicates()
            if removed:
                self._emit("log", f"Убрано дублей офлайн-каталога: {removed}")
        except DatabaseError as exc:
            self._emit("log", f"Предупреждение: не удалось убрать дубли — {exc}")

        try:
            self.db.set_meta("last_sync", datetime.now().strftime("%Y-%m-%d %H:%M"))
        except DatabaseError as exc:
            self._emit("log", f"Предупреждение: не удалось записать дату обновления — {exc}")

        self._emit("done", added)

    def _fetch_details(self, client: TMDBClient, movie_id: int) -> dict[str, Any] | None:
        if self._stop.is_set():
            return None
        details = client.movie_details(movie_id)
        if not details:
            return None
        return details_to_row(details)
