"""SQLite-хранилище фильмов: схема, запись, поиск с фильтрами."""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import time
from datetime import date, datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any, Callable, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS movies (
    id             INTEGER PRIMARY KEY,
    title          TEXT NOT NULL,
    title_lower    TEXT NOT NULL DEFAULT '',
    original_title TEXT,
    year           INTEGER,
    release_date   TEXT,
    overview       TEXT,
    overview_en    TEXT,
    overview_en_checked INTEGER NOT NULL DEFAULT 0,
    tagline        TEXT,
    rating         REAL,
    votes          INTEGER,
    genres         TEXT NOT NULL DEFAULT '',
    countries      TEXT NOT NULL DEFAULT '',
    runtime        INTEGER,
    director       TEXT,
    poster_path    TEXT,
    poster_file    TEXT,
    poster_url     TEXT,
    source         TEXT,
    imdb_id        TEXT,
    link           TEXT,
    updated_at     TEXT,
    watched        INTEGER NOT NULL DEFAULT 0,
    personal_rating INTEGER
);
CREATE INDEX IF NOT EXISTS idx_movies_year   ON movies(year);
CREATE INDEX IF NOT EXISTS idx_movies_rating ON movies(rating);
CREATE INDEX IF NOT EXISTS idx_movies_votes  ON movies(votes);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS watch_links (
    movie_id INTEGER NOT NULL,
    source   TEXT NOT NULL,
    url      TEXT NOT NULL,
    title    TEXT,
    PRIMARY KEY (movie_id, source)
);
CREATE TABLE IF NOT EXISTS movie_cast (
    movie_id INTEGER NOT NULL,
    name     TEXT NOT NULL,
    position INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (movie_id, name)
);
CREATE TABLE IF NOT EXISTS movie_keywords (
    movie_id INTEGER NOT NULL,
    keyword  TEXT NOT NULL,
    PRIMARY KEY (movie_id, keyword)
);
CREATE TABLE IF NOT EXISTS bookmarks (
    movie_id INTEGER PRIMARY KEY,
    added_at TEXT
);
CREATE TABLE IF NOT EXISTS watchlist (
    movie_id INTEGER PRIMARY KEY,
    priority INTEGER NOT NULL DEFAULT 3 CHECK(priority BETWEEN 1 AND 5),
    note TEXT NOT NULL DEFAULT '',
    added_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS recommendation_feedback (
    movie_id INTEGER PRIMARY KEY,
    feedback TEXT NOT NULL CHECK(feedback IN ('like', 'dislike')),
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS providers (
    movie_id   INTEGER NOT NULL,
    region     TEXT NOT NULL,
    names      TEXT NOT NULL DEFAULT '',
    link       TEXT,
    updated_at TEXT,
    PRIMARY KEY (movie_id, region)
);
CREATE TABLE IF NOT EXISTS history (
    movie_id  INTEGER PRIMARY KEY,
    viewed_at TEXT
);
CREATE TABLE IF NOT EXISTS saved_filters (
    name         TEXT PRIMARY KEY,
    filters_json TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS viewing_plans (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    movie_id      INTEGER NOT NULL,
    planned_date  TEXT NOT NULL,
    note          TEXT NOT NULL DEFAULT '',
    status        TEXT NOT NULL DEFAULT 'planned'
                  CHECK(status IN ('planned', 'completed')),
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    UNIQUE(movie_id, planned_date)
);
CREATE INDEX IF NOT EXISTS idx_viewing_plans_date
    ON viewing_plans(planned_date, status);
CREATE TABLE IF NOT EXISTS content_exclusions (
    kind  TEXT NOT NULL CHECK(kind IN ('genre', 'theme')),
    value TEXT NOT NULL,
    PRIMARY KEY(kind, value)
);
CREATE TABLE IF NOT EXISTS sequel_monitor (
    anchor_movie_id INTEGER PRIMARY KEY,
    collection_id   INTEGER,
    checked_at      TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sequel_collection_state (
    collection_id    INTEGER PRIMARY KEY,
    known_movie_ids  TEXT NOT NULL,
    checked_at       TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sequel_notifications (
    collection_id INTEGER NOT NULL,
    movie_id      INTEGER NOT NULL,
    title         TEXT NOT NULL,
    year          INTEGER,
    release_date  TEXT,
    url           TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    is_read       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (collection_id, movie_id)
);
CREATE INDEX IF NOT EXISTS idx_cast_movie ON movie_cast(movie_id);
CREATE INDEX IF NOT EXISTS idx_keywords_movie ON movie_keywords(movie_id);
CREATE INDEX IF NOT EXISTS idx_keywords_keyword ON movie_keywords(keyword);
CREATE INDEX IF NOT EXISTS idx_cast_name ON movie_cast(name);
CREATE TABLE IF NOT EXISTS movie_title_grams (
    movie_id INTEGER NOT NULL,
    gram     TEXT NOT NULL,
    PRIMARY KEY (movie_id, gram)
);
CREATE INDEX IF NOT EXISTS idx_title_grams_gram ON movie_title_grams(gram);
"""

# Поля, которые пишутся из словаря фильма.
FIELDS: tuple[str, ...] = (
    "id",
    "title",
    "original_title",
    "year",
    "release_date",
    "overview",
    "tagline",
    "rating",
    "votes",
    "genres",
    "countries",
    "runtime",
    "director",
    "poster_path",
    "poster_file",
    "poster_url",
    "source",
    "imdb_id",
    "link",
    "file_path",
)

SORTS: dict[str, str] = {
    # Взвешенный рейтинг (как у IMDb/TMDb): фильм с 3 голосами и оценкой 10
    # не обгоняет классику с тысячами оценок.
    "rating": (
        "((COALESCE(rating, 0) * COALESCE(votes, 0) + 6.5 * 300.0) "
        "/ (COALESCE(votes, 0) + 300.0)) DESC, COALESCE(votes, 0) DESC"
    ),
    "votes": "COALESCE(votes, 0) DESC, COALESCE(rating, 0) DESC",
    "year_new": "COALESCE(year, 0) DESC, COALESCE(rating, 0) DESC",
    "year_old": "COALESCE(year, 0) ASC, COALESCE(rating, 0) DESC",
    "title": "title COLLATE NOCASE ASC",
    "random": "RANDOM()",
}

PERSONAL_FILTER_KEYS = {
    "title", "credit", "genre", "category", "mood", "country", "year_from",
    "year_to", "min_rating", "min_votes", "min_runtime", "max_runtime",
    "bookmarked_only", "hide_watched", "sort",
}

# Строки, которые «переезжают» на запись-двойника при дедупликации:
# (SQL, target_id, source_id). Внешних ключей в схеме нет, поэтому все
# зависимые таблицы обрабатываются явно.
_MERGE_STATEMENTS: tuple[str, ...] = (
    "INSERT OR IGNORE INTO bookmarks (movie_id, added_at) "
    "SELECT ?, added_at FROM bookmarks WHERE movie_id = ?",
    "INSERT OR IGNORE INTO watchlist (movie_id, priority, note, added_at, updated_at) "
    "SELECT ?, priority, note, added_at, updated_at FROM watchlist WHERE movie_id = ?",
    "INSERT OR IGNORE INTO recommendation_feedback (movie_id, feedback, updated_at) "
    "SELECT ?, feedback, updated_at FROM recommendation_feedback WHERE movie_id = ?",
    "INSERT OR IGNORE INTO providers (movie_id, region, names, link, updated_at) "
    "SELECT ?, region, names, link, updated_at FROM providers WHERE movie_id = ?",
    "INSERT OR IGNORE INTO watch_links (movie_id, source, url, title) "
    "SELECT ?, source, url, title FROM watch_links WHERE movie_id = ?",
    "INSERT OR IGNORE INTO movie_cast (movie_id, name, position) "
    "SELECT ?, name, position FROM movie_cast WHERE movie_id = ?",
    "INSERT OR IGNORE INTO movie_keywords (movie_id, keyword) "
    "SELECT ?, keyword FROM movie_keywords WHERE movie_id = ?",
    "INSERT OR IGNORE INTO viewing_plans "
    "(movie_id, planned_date, note, status, created_at, updated_at) "
    "SELECT ?, planned_date, note, status, created_at, updated_at "
    "FROM viewing_plans WHERE movie_id = ?",
    "INSERT OR IGNORE INTO sequel_monitor "
    "(anchor_movie_id, collection_id, checked_at) "
    "SELECT ?, collection_id, checked_at FROM sequel_monitor "
    "WHERE anchor_movie_id = ?",
    "INSERT INTO history (movie_id, viewed_at) "
    "SELECT ?, viewed_at FROM history WHERE movie_id = ? "
    "ON CONFLICT(movie_id) DO UPDATE SET viewed_at = "
    "CASE WHEN excluded.viewed_at > COALESCE(history.viewed_at, '') "
    "THEN excluded.viewed_at ELSE history.viewed_at END",
)

# Таблицы с колонкой movie_id, строки которых после переноса удаляются.
_MERGE_SOURCE_TABLES: tuple[str, ...] = (
    "bookmarks", "watchlist", "recommendation_feedback", "providers",
    "watch_links", "viewing_plans", "history", "movie_cast", "movie_keywords",
    "movie_title_grams",
)

# Только эти сбои SQLite имеет смысл повторять; ошибки схемы и запросов — нет.
_RETRYABLE_MARKERS: tuple[str, ...] = (
    "database is locked", "table is locked", "database is busy",
    "disk i/o error", "attempt to write a readonly database",
    "unable to open database file", "read-only database",
)


def _is_retryable_error(exc: sqlite3.OperationalError) -> bool:
    message = str(exc).lower()
    return any(marker in message for marker in _RETRYABLE_MARKERS)


def escape_like(value: str) -> str:
    """Экранирует спецсимволы LIKE: '%' и '_' ищутся как обычные символы."""
    return str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")

# Версия алгоритма индекса опечаток: меняется вместе с _title_grams.
GRAM_INDEX_VERSION = "1"

# Частичные наборы (IMDb, MovieLens, повторная синхронизация TMDb) присылают
# эти поля пустыми или None. Без защиты повторный импорт стирал описания,
# скачанные постеры и путь к локальному файлу пользователя.
KEEP_IF_EMPTY: frozenset[str] = frozenset({
    "original_title", "release_date", "overview", "tagline", "genres",
    "countries", "director", "poster_path", "poster_file", "poster_url",
    "imdb_id", "link", "file_path",
})
KEEP_IF_ZERO: frozenset[str] = frozenset({"rating", "votes", "runtime", "year"})


def _upsert_update_clause() -> str:
    """SET-часть upsert: пустые значения не затирают уже сохранённые."""
    parts: list[str] = []
    for field in FIELDS:
        if field == "id":
            continue
        if field in KEEP_IF_EMPTY:
            parts.append(
                f"{field} = COALESCE(NULLIF(excluded.{field}, ''), movies.{field})"
            )
        elif field in KEEP_IF_ZERO:
            parts.append(
                f"{field} = COALESCE(NULLIF(excluded.{field}, 0), movies.{field})"
            )
        else:
            parts.append(f"{field} = excluded.{field}")
    parts.append("title_lower = excluded.title_lower")
    parts.append("updated_at = excluded.updated_at")
    return ", ".join(parts)


UPSERT_UPDATES = _upsert_update_clause()

_CLEAN_RE = re.compile(r"\s+")
_TITLE_CLEAN_RE = re.compile(r"[^0-9a-zа-яё]+", re.IGNORECASE)


def _normalize_title(value: str | None) -> str:
    value = (value or "").casefold().replace("ё", "е")
    return " ".join(_TITLE_CLEAN_RE.sub(" ", value).split())


def _title_grams(value: str) -> set[str]:
    if not value:
        return set()
    width = min(3, len(value))
    return {value[index:index + width] for index in range(len(value) - width + 1)}


def norm_list(values: Iterable[str] | str) -> str:
    """Приводит список к виду ',драма,триллер,' для поиска через LIKE '%,драма,%'."""
    if isinstance(values, str):
        values = values.split(",")
    items: list[str] = []
    for value in values:
        item = _CLEAN_RE.sub(" ", str(value or "")).strip().lower()
        if item and item not in items:
            items.append(item)
    return "," + ",".join(items) + "," if items else ""


def norm_countries(values: Iterable[str] | str) -> str:
    """Страны приводятся к верхнему регистру ISO-кодов."""
    if isinstance(values, str):
        values = values.split(",")
    items: list[str] = []
    for value in values:
        item = str(value or "").strip().upper()
        if item and item not in items:
            items.append(item)
    return "," + ",".join(items) + "," if items else ""


class DatabaseError(RuntimeError):
    """База недоступна для чтения или записи."""


class MovieDB:
    """Тонкая обёртка над sqlite3 с блокировкой для многопоточного доступа.

    Если файл базы стал недоступен (папку переместили, файлы WAL удалили,
    диск заблокирован синхронизацией), соединение переоткрывается и операция
    повторяется, а пользователь получает понятное сообщение вместо текста
    «unable to open database file».
    """

    def __init__(self, path: str | Path, *, defer_index: bool = False) -> None:
        self.path = Path(path)
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise DatabaseError(
                f"Не удалось создать папку для базы {self.path.parent}: {exc}"
            ) from exc
        self._lock = threading.RLock()
        self._index_lock = threading.Lock()
        self._conn: sqlite3.Connection | None = None
        try:
            self._open()
        except sqlite3.Error as exc:
            raise DatabaseError(
                f"Не удалось открыть базу {self.path}: {exc}. "
                "Проверьте, что файл не занят другой программой и доступен для записи."
            ) from exc
        if not defer_index:
            # Скрипты и тесты получают готовый индекс сразу; приложение
            # (defer_index=True) строит его в фоне, чтобы окно открылось без задержки.
            self.ensure_title_gram_index()

    # ----------------------------------------------------------- соединение
    def _open(self) -> None:
        """Открывает соединение и применяет идемпотентные миграции."""
        self._conn = self._connect()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=10000")  # ждём чужую запись, а не падаем
        conn.executescript(SCHEMA)
        # Идемпотентные миграции: локальные данные, кэши и персональное состояние.
        columns = {row[1] for row in conn.execute("PRAGMA table_info(movies)")}
        if "file_path" not in columns:
            conn.execute("ALTER TABLE movies ADD COLUMN file_path TEXT")
        if "poster_checked" not in columns:
            conn.execute(
                "ALTER TABLE movies ADD COLUMN poster_checked INTEGER NOT NULL DEFAULT 0"
            )
        if "overview_en" not in columns:
            conn.execute("ALTER TABLE movies ADD COLUMN overview_en TEXT")
        if "overview_en_checked" not in columns:
            conn.execute(
                "ALTER TABLE movies ADD COLUMN overview_en_checked INTEGER NOT NULL DEFAULT 0"
            )
        if "watched" not in columns:
            conn.execute(
                "ALTER TABLE movies ADD COLUMN watched INTEGER NOT NULL DEFAULT 0"
            )
        if "personal_rating" not in columns:
            conn.execute("ALTER TABLE movies ADD COLUMN personal_rating INTEGER")
        conn.commit()
        return conn

    def ensure_title_gram_index(
        self, *, batch_size: int = 500, progress: Callable[[int], None] | None = None
    ) -> bool:
        """Строит индекс опечаток, если его нет. Возвращает True, если строил.

        Работа идёт пачками по несколько сотен фильмов с отдельными
        транзакциями, поэтому поиск ждёт максимум одну пачку (~0,3 с), а не всю
        постройку. Авто-checkpoint WAL на время постройки выключен: иначе каждая
        пачка упирается в сброс журнала и время растёт в разы.
        """
        if not self._index_lock.acquire(blocking=False):
            return False  # индекс уже строит другой поток
        try:
            with self._lock:
                if self._conn is None:
                    return False
                row = self._db.execute(
                    "SELECT value FROM meta WHERE key = 'title_gram_index_version'"
                ).fetchone()
                if row is not None and str(row[0]) == GRAM_INDEX_VERSION:
                    return False
                # Частично построенный индекс не оставляем: строим заново.
                self._db.execute("DELETE FROM movie_title_grams")
                self._db.execute(
                    "DELETE FROM meta WHERE key = 'title_gram_index_version'"
                )
                self._db.execute("PRAGMA wal_autocheckpoint=0")
                self._db.commit()
            try:
                last_id = 0
                built = 0
                while True:
                    with self._lock:
                        if self._conn is None:
                            return False
                        rows = self._db.execute(
                            "SELECT id, title, original_title FROM movies "
                            "WHERE id > ? ORDER BY id LIMIT ?",
                            (last_id, max(100, int(batch_size))),
                        ).fetchall()
                        if not rows:
                            break
                        gram_rows: set[tuple[int, str]] = set()
                        for item in rows:
                            names = {
                                _normalize_title(item["title"]),
                                _normalize_title(item["original_title"]),
                            }
                            for name in names:
                                gram_rows.update(
                                    (int(item["id"]), gram)
                                    for gram in _title_grams(name)
                                )
                        if gram_rows:
                            self._db.executemany(
                                "INSERT OR IGNORE INTO movie_title_grams "
                                "(movie_id, gram) VALUES (?, ?)",
                                sorted(gram_rows),
                            )
                        self._db.commit()
                        last_id = int(rows[-1]["id"])
                        built += len(rows)
                    if progress is not None:
                        progress(built)

                with self._lock:
                    if self._conn is None:
                        return False
                    self._db.execute(
                        "INSERT INTO meta (key, value) "
                        "VALUES ('title_gram_index_version', ?) "
                        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                        (GRAM_INDEX_VERSION,),
                    )
                    self._db.commit()
                return True
            finally:
                # Возвращаем обычный режим журнала и один раз сбрасываем WAL.
                with self._lock:
                    if self._conn is not None:
                        try:
                            self._db.execute("PRAGMA wal_checkpoint(PASSIVE)")
                            self._db.execute("PRAGMA wal_autocheckpoint=1000")
                            self._db.commit()
                        except sqlite3.Error:
                            pass
        finally:
            self._index_lock.release()

    def _reopen(self) -> None:
        """Переоткрывает базу. Старое соединение живо, пока новое не откроется."""
        with self._lock:
            conn = self._connect()
            old, self._conn = self._conn, conn
            if old is not None:
                try:
                    old.close()
                except sqlite3.Error:
                    pass

    @property
    def _db(self) -> sqlite3.Connection:
        """Соединение с базой; после `close()` — понятная ошибка.

        Без этого геттера любой вызов после закрытия падал бы с `AttributeError`
        на `None`, а не с сообщением, которое можно показать пользователю.
        """
        if self._conn is None:
            raise DatabaseError(
                f"Соединение с базой {self.path} закрыто. Перезапустите приложение."
            )
        return self._conn

    def _call(self, action, attempts: int = 2):
        """Выполняет операцию, повторяя только временные сбои SQLite.

        Ошибки схемы и запросов («no such column») повторять бессмысленно, а
        совет «проверьте папку» только путает. Откат делается при любой ошибке,
        иначе открытая транзакция ломает следующий BEGIN IMMEDIATE.
        Немедемпотентные операции вызывают с attempts=0.
        """
        last: Exception | None = None
        for attempt in range(attempts + 1):
            if self._conn is None:
                raise DatabaseError(
                    f"Соединение с базой {self.path} закрыто. Перезапустите приложение."
                )
            try:
                return action()
            except sqlite3.OperationalError as exc:
                last = exc
                # Незавершённая транзакция держала бы блокировку — откатываем.
                self._rollback_quiet()
                if attempt >= attempts or not _is_retryable_error(exc):
                    break
                time.sleep(0.5 * (attempt + 1))
                try:
                    self._reopen()
                except (sqlite3.Error, OSError) as reopen_error:
                    last = reopen_error
                    time.sleep(0.3)
            except sqlite3.Error as exc:
                self._rollback_quiet()
                raise DatabaseError(
                    f"Ошибка базы {self.path}: {exc}"
                ) from exc
            except Exception:
                self._rollback_quiet()
                raise
        raise DatabaseError(
            f"Не удалось обратиться к базе {self.path}: {last}. "
            "Проверьте, что папка доступна для записи и не перемещается во время работы."
        ) from last

    def _rollback_quiet(self) -> None:
        try:
            with self._lock:
                if self._conn is not None:
                    self._db.rollback()
        except sqlite3.Error:
            pass

    def backup_to(self, target: str | Path) -> Path:
        """Создаёт согласованную копию базы (включая данные из WAL)."""
        target = Path(target)
        target.parent.mkdir(parents=True, exist_ok=True)
        destination = sqlite3.connect(str(target))

        def action() -> None:
            with self._lock:
                self._db.backup(destination)

        try:
            self._call(action, attempts=1)
        except DatabaseError:
            destination.close()
            raise
        destination.close()
        return target

    def check_writable(self) -> str | None:
        """Проверяет, что базу можно менять. Возвращает текст ошибки или None."""

        def action() -> None:
            with self._lock:
                version = self._db.execute("PRAGMA user_version").fetchone()[0]
                self._db.execute(f"PRAGMA user_version = {int(version)}")
                self._db.commit()

        try:
            self._call(action, attempts=1)
        except DatabaseError as exc:
            return str(exc)
        return None

    # ---------------------------------------------------------------- запись
    def upsert_many(self, movies: Iterable[dict[str, Any]]) -> int:
        """Вставляет/обновляет фильмы. Возвращает количество записей."""
        rows = [self._prepare(m) for m in movies]
        if not rows:
            return 0
        placeholders = ",".join("?" * len(FIELDS))
        sql = (
            f"INSERT INTO movies ({','.join(FIELDS)}, title_lower, updated_at) "
            f"VALUES ({placeholders}, ?, ?) "
            f"ON CONFLICT(id) DO UPDATE SET {UPSERT_UPDATES}"
        )
        now = datetime.now().isoformat(timespec="seconds")
        payload = []
        for row in rows:
            payload.append([row.get(f) for f in FIELDS] + [row["title_lower"], now])

        def action() -> int:
            with self._lock:
                self._db.executemany(sql, payload)
                self._refresh_title_grams([int(row["id"]) for row in rows])
                self._db.commit()
            return len(payload)

        return self._call(action, attempts=4)

    def _refresh_title_grams(self, movie_ids: list[int]) -> None:
        """Keeps the bounded fuzzy-search candidate index aligned with titles."""
        if not movie_ids:
            return
        grams: set[tuple[int, str]] = set()
        for offset in range(0, len(movie_ids), 500):
            batch_ids = movie_ids[offset:offset + 500]
            self._db.executemany(
                "DELETE FROM movie_title_grams WHERE movie_id = ?",
                [(movie_id,) for movie_id in batch_ids],
            )
            placeholders = ",".join("?" for _ in batch_ids)
            rows = self._db.execute(
                f"SELECT id, title, original_title FROM movies WHERE id IN ({placeholders})",
                batch_ids,
            ).fetchall()
            for row in rows:
                names = {
                    _normalize_title(row["title"]),
                    _normalize_title(row["original_title"]),
                }
                for name in names:
                    grams.update((int(row["id"]), gram) for gram in _title_grams(name))
        if grams:
            self._db.executemany(
                "INSERT OR IGNORE INTO movie_title_grams (movie_id, gram) "
                "VALUES (?, ?)",
                sorted(grams),
            )

    def _fuzzy_title_ids(self, query: str, *, limit: int = 500) -> list[int]:
        normalized = _normalize_title(query)[:160]
        grams = _title_grams(normalized)
        if not grams:
            return []

        def action() -> list[int]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT movie_id, COUNT(*) AS overlap "
                    "FROM movie_title_grams WHERE gram IN ("
                    + ",".join("?" for _ in grams)
                    + ") GROUP BY movie_id ORDER BY overlap DESC, movie_id LIMIT ?",
                    [*sorted(grams), int(limit)],
                ).fetchall()
                candidates = [
                    (int(row["movie_id"]), int(row["overlap"])) for row in rows
                ]
                if not candidates:
                    return []
                placeholders = ",".join("?" for _ in candidates)
                titles = self._db.execute(
                    f"SELECT id, title, original_title FROM movies "
                    f"WHERE id IN ({placeholders})",
                    [movie_id for movie_id, _ in candidates],
                ).fetchall()
            by_id = {int(row["id"]): row for row in titles}
            scored: list[tuple[float, int]] = []
            threshold = max(0.62, 1.0 - 2.0 / max(1, len(normalized)))
            for movie_id, _overlap in candidates:
                row = by_id.get(movie_id)
                if row is None:
                    continue
                similarity = max(
                    SequenceMatcher(None, normalized, _normalize_title(row["title"])).ratio(),
                    SequenceMatcher(None, normalized, _normalize_title(row["original_title"])).ratio(),
                )
                if similarity >= threshold:
                    scored.append((similarity, movie_id))
            scored.sort(key=lambda item: (-item[0], item[1]))
            return [movie_id for _, movie_id in scored]

        return self._call(action)

    @staticmethod
    def _prepare(movie: dict[str, Any]) -> dict[str, Any]:
        row = {f: movie.get(f) for f in FIELDS}
        row["title"] = (row.get("title") or "Без названия").strip()
        row["genres"] = norm_list(row.get("genres") or "")
        row["countries"] = norm_countries(row.get("countries") or "")
        row["title_lower"] = (
            f"{row['title']} {row.get('original_title') or ''}".lower().strip()
        )
        return row

    # ---------------------------------------------------------------- чтение
    def count(self) -> int:
        def action() -> int:
            with self._lock:
                return int(self._db.execute("SELECT COUNT(*) FROM movies").fetchone()[0])

        return self._call(action)

    def stats(self) -> dict[str, Any]:
        def action():
            with self._lock:
                return self._db.execute(
                    "SELECT COUNT(*) AS total, MIN(year) AS min_year, MAX(year) AS max_year, "
                    "SUM(CASE WHEN COALESCE(poster_file, '') <> '' THEN 1 ELSE 0 END) AS with_poster, "
                    "SUM(CASE WHEN COALESCE(poster_file, '') <> '' "
                    "OR COALESCE(poster_path, '') <> '' OR COALESCE(poster_url, '') <> '' "
                    "THEN 1 ELSE 0 END) AS with_poster_any "
                    "FROM movies"
                ).fetchone()

        row = self._call(action)
        data = dict(row) if row else {}
        data["total"] = int(data.get("total") or 0)
        data["min_year"] = int(data.get("min_year") or 0)
        data["max_year"] = int(data.get("max_year") or 0)
        data["with_poster"] = int(data.get("with_poster") or 0)
        data["with_poster_any"] = int(data.get("with_poster_any") or 0)
        data["last_sync"] = self.get_meta("last_sync") or ""
        return data

    def get(self, movie_id: int) -> dict[str, Any] | None:
        def action():
            with self._lock:
                return self._db.execute(
                    "SELECT * FROM movies WHERE id = ?", (movie_id,)
                ).fetchone()

        row = self._call(action)
        return dict(row) if row else None

    def existing_ids(self, with_details: bool = False) -> set[int]:
        sql = "SELECT id FROM movies"
        if with_details:
            sql += " WHERE COALESCE(countries, '') <> '' AND COALESCE(overview, '') <> ''"

        def action() -> set[int]:
            with self._lock:
                return {int(r[0]) for r in self._db.execute(sql).fetchall()}

        return self._call(action)

    def existing_imdb_ids(self) -> set[str]:
        """Уже сохранённые IMDb id (в нижнем регистре) — для дедупликации импорта."""

        def action() -> set[str]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT imdb_id FROM movies "
                    "WHERE imdb_id IS NOT NULL AND TRIM(imdb_id) <> ''"
                ).fetchall()
            return {str(row[0]).strip().lower() for row in rows}

        return self._call(action)

    def missing_posters(self) -> list[dict[str, Any]]:
        """Записи, у которых есть ссылка на постер, но нет локального файла."""

        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT * FROM movies "
                    "WHERE COALESCE(poster_file, '') = '' AND COALESCE(poster_url, '') <> ''"
                ).fetchall()
            return [dict(r) for r in rows]

        return self._call(action)

    def rows_by_source(self, source: str) -> list[dict[str, Any]]:
        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT * FROM movies WHERE source = ?", (source,)
                ).fetchall()
            return [dict(r) for r in rows]

        return self._call(action)

    def remove_wiki_duplicates(self) -> int:
        """Убирает офлайн-записи, если тот же фильм уже пришёл из TMDb.

        Постер офлайн-записи «переезжает» на запись TMDb, а личное состояние
        (просмотр, оценка, закладка, список, планы, история, площадки, ссылки)
        переносится на неё же: иначе отметки пользователя терялись бы при каждой
        синхронизации, а строки зависимых таблиц оставались бы без фильма —
        внешних ключей в схеме нет. Сравнение идёт в Python: SQL-вариант с
        коррелированными подзапросами на тысячах строк работает минутами.
        """

        def action() -> int:
            with self._lock:
                tmdb = self._db.execute(
                    "SELECT id, title, year, poster_file FROM movies WHERE source <> 'wiki'"
                ).fetchall()
                wiki = self._db.execute(
                    "SELECT id, title, year, poster_file, poster_url FROM movies "
                    "WHERE source = 'wiki'"
                ).fetchall()
                if not tmdb or not wiki:
                    return 0

                by_name: dict[tuple[str, int], dict[str, Any]] = {}
                for row in tmdb:
                    key = ((row["title"] or "").lower(), int(row["year"] or 0))
                    by_name.setdefault(key, dict(row))

                merged = 0
                for row in wiki:
                    key = ((row["title"] or "").lower(), int(row["year"] or 0))
                    twin = by_name.get(key)
                    if not twin:
                        continue
                    wiki_id, twin_id = int(row["id"]), int(twin["id"])
                    if row["poster_file"] and not twin.get("poster_file"):
                        self._db.execute(
                            "UPDATE movies SET poster_file = ?, poster_url = ? WHERE id = ?",
                            (row["poster_file"], row["poster_url"], twin_id),
                        )
                        twin["poster_file"] = row["poster_file"]
                    self._merge_movie(wiki_id, twin_id)
                    merged += 1
                self._db.commit()
                return merged

        return self._call(action)

    def _merge_movie(self, source_id: int, target_id: int) -> None:
        """Переносит личное состояние и связанные строки на запись-двойника.

        Вызывается внутри транзакции remove_wiki_duplicates.
        """
        self._db.execute(
            "UPDATE movies SET "
            " overview = COALESCE(NULLIF(overview, ''), "
            "   (SELECT overview FROM movies WHERE id = ?)), "
            " watched = MAX(COALESCE(watched, 0), "
            "   COALESCE((SELECT watched FROM movies WHERE id = ?), 0)), "
            " personal_rating = COALESCE(personal_rating, "
            "   (SELECT personal_rating FROM movies WHERE id = ?)), "
            " file_path = COALESCE(NULLIF(file_path, ''), "
            "   (SELECT file_path FROM movies WHERE id = ?)) "
            "WHERE id = ?",
            (source_id, source_id, source_id, source_id, target_id),
        )
        for statement in _MERGE_STATEMENTS:
            self._db.execute(statement, (target_id, source_id))
        for table in _MERGE_SOURCE_TABLES:
            self._db.execute(f"DELETE FROM {table} WHERE movie_id = ?", (source_id,))
        self._db.execute(
            "DELETE FROM sequel_monitor WHERE anchor_movie_id = ?", (source_id,)
        )
        self._db.execute("DELETE FROM movies WHERE id = ?", (source_id,))

    def titles_index(self) -> list[tuple[int, str, str, int]]:
        """(id, title, original_title, year) для сопоставления с файлами на диске."""

        def action() -> list[tuple[int, str, str, int]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT id, title, COALESCE(original_title, ''), COALESCE(year, 0) FROM movies"
                ).fetchall()
            return [
                (int(r[0]), str(r[1] or ""), str(r[2] or ""), int(r[3] or 0)) for r in rows
            ]

        return self._call(action)

    def set_watch_links(self, rows: list[tuple[int, str, str, str]]) -> int:
        """Ссылки «где смотреть легально»: [(movie_id, source, url, title)]."""

        def action() -> int:
            with self._lock:
                cursor = self._db.executemany(
                    "INSERT INTO watch_links (movie_id, source, url, title) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(movie_id, source) DO UPDATE SET "
                    "url = excluded.url, title = excluded.title",
                    rows,
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def watch_link(self, movie_id: int) -> dict[str, Any] | None:
        def action():
            with self._lock:
                return self._db.execute(
                    "SELECT source, url, title FROM watch_links "
                    "WHERE movie_id = ? ORDER BY source LIMIT 1",
                    (movie_id,),
                ).fetchone()

        row = self._call(action)
        return dict(row) if row else None

    def watch_links_count(self) -> int:
        def action() -> int:
            with self._lock:
                return int(
                    self._db.execute("SELECT COUNT(*) FROM watch_links").fetchone()[0]
                )

        return self._call(action)

    def set_cast(self, rows: list[tuple[int, str, int]]) -> int:
        """Актёры: [(movie_id, имя, позиция в титрах)]."""

        def action() -> int:
            with self._lock:
                cursor = self._db.executemany(
                    "INSERT OR IGNORE INTO movie_cast (movie_id, name, position) "
                    "VALUES (?, ?, ?)",
                    rows,
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def set_keywords(self, rows: list[tuple[int, str]]) -> int:
        def action() -> int:
            with self._lock:
                cursor = self._db.executemany(
                    "INSERT OR IGNORE INTO movie_keywords (movie_id, keyword) VALUES (?, ?)",
                    rows,
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def cast_of(self, movie_id: int, limit: int = 8) -> list[str]:
        def action() -> list[str]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT name FROM movie_cast WHERE movie_id = ? "
                    "ORDER BY position LIMIT ?",
                    (movie_id, limit),
                ).fetchall()
            return [str(r[0]) for r in rows]

        return self._call(action)

    def keywords_of(self, movie_id: int, limit: int = 12) -> list[str]:
        def action() -> list[str]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT keyword FROM movie_keywords WHERE movie_id = ? LIMIT ?",
                    (movie_id, limit),
                ).fetchall()
            return [str(r[0]) for r in rows]

        return self._call(action)

    def detail_metadata(self, movie_id: int) -> dict[str, Any]:
        """Возвращает только уже сохранённые детали и пользовательские кэши."""
        movie = self.get(movie_id) or {}
        return {
            "runtime": movie.get("runtime"),
            "countries": movie.get("countries") or "",
            "cast": self.cast_of(movie_id, 8),
            "keywords": self.keywords_of(movie_id, 10),
            "providers": self.providers_of(movie_id),
            "watch_link": self.watch_link(movie_id),
        }

    def blind_movie_candidate(self, language: str, exclude_id: int | None = None) -> dict[str, Any] | None:
        """Picks a blind-card candidate without returning its title or poster."""
        if language not in {"ru-RU", "en-US"}:
            raise ValueError("Язык должен быть ru-RU или en-US.")
        from .const import GENRE_ORDER

        overview_column = "overview_en" if language == "en-US" else "overview"
        checked_condition = (
            "AND overview_en_checked = 1 " if language == "en-US" else ""
        )
        confirmed_genre_condition = "(" + " OR ".join(
            "genres LIKE ?" for _ in GENRE_ORDER
        ) + ")"
        query = (
            "SELECT id, year, genres, " + overview_column + " AS overview "
            "FROM movies WHERE year IS NOT NULL AND " + confirmed_genre_condition + " "
            f"AND {overview_column} IS NOT NULL AND TRIM({overview_column}) <> '' "
            + checked_condition
            + ("AND id <> ? " if exclude_id is not None else "")
            + "ORDER BY RANDOM() LIMIT 1"
        )
        args: tuple[Any, ...] = tuple(f"%,{genre},%" for genre in GENRE_ORDER)
        if exclude_id is not None:
            args += (exclude_id,)

        def action() -> dict[str, Any] | None:
            with self._lock:
                row = self._db.execute(query, args).fetchone()
            return dict(row) if row else None

        return self._call(action)

    def watched_movies(self) -> list[dict[str, Any]]:
        """Returns the local catalogue rows marked as watched."""
        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT id, title, year, countries, genres, personal_rating "
                    "FROM movies WHERE watched = 1 ORDER BY id"
                ).fetchall()
            return [dict(row) for row in rows]

        return self._call(action)

    def filmography_search(self, query: str, limit: int = 20) -> list[str]:
        """Finds actor/director names already present in the local catalogue."""
        query = str(query or "").strip()
        if not query:
            return []
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Лимит должен быть положительным целым числом.")
        pattern = f"%{escape_like(query)}%"

        def action() -> list[str]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT name FROM ("
                    "SELECT DISTINCT name FROM movie_cast WHERE name LIKE ? ESCAPE '\\' "
                    "UNION SELECT DISTINCT director AS name FROM movies "
                    "WHERE director IS NOT NULL AND director LIKE ? ESCAPE '\\'"
                    ") ORDER BY name COLLATE NOCASE LIMIT ?",
                    (pattern, pattern, limit),
                ).fetchall()
            return [str(row[0]) for row in rows]

        return self._call(action)

    def filmography(self, person: str, limit: int = 500) -> list[dict[str, Any]]:
        """Returns exact local actor/director credits with personal viewing status."""
        person = str(person or "").strip()
        if not person:
            return []
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError("Лимит должен быть положительным целым числом.")

        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT m.*, EXISTS(SELECT 1 FROM movie_cast c "
                    "WHERE c.movie_id=m.id AND LOWER(TRIM(c.name))=LOWER(?)) AS is_actor, "
                    "EXISTS(SELECT 1 FROM watchlist w WHERE w.movie_id=m.id) AS watchlisted, "
                    "(SELECT MIN(planned_date) FROM viewing_plans p "
                    "WHERE p.movie_id=m.id AND p.status='planned') AS planned_date "
                    "FROM movies m WHERE LOWER(TRIM(COALESCE(m.director, ''))) = LOWER(?) "
                    "OR EXISTS(SELECT 1 FROM movie_cast c WHERE c.movie_id=m.id "
                    "AND LOWER(TRIM(c.name))=LOWER(?)) "
                    "ORDER BY COALESCE(m.year, 0), m.title COLLATE NOCASE, m.id LIMIT ?",
                    (person, person, person, limit),
                ).fetchall()
            return [dict(row) for row in rows]

        return self._call(action)

    def history_for_year(self, year: int) -> list[dict[str, Any]]:
        """Returns distinct films whose latest local view falls in a calendar year."""
        if isinstance(year, bool) or not isinstance(year, int) or not 1 <= year <= 9998:
            raise ValueError("Год должен быть целым числом от 1 до 9998.")
        start, end = f"{year:04d}-01-01", f"{year + 1:04d}-01-01"

        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT m.*, h.viewed_at FROM history h "
                    "JOIN movies m ON m.id=h.movie_id "
                    "WHERE h.viewed_at >= ? AND h.viewed_at < ? "
                    "ORDER BY h.viewed_at, m.id",
                    (start, end),
                ).fetchall()
            return [dict(row) for row in rows]

        return self._call(action)

    def cast_names_for_movies(self, movie_ids: Iterable[int]) -> dict[int, set[str]]:
        """Returns cast names for a set of local films in one query."""
        ids = sorted({int(movie_id) for movie_id in movie_ids if int(movie_id) > 0})
        if not ids:
            return {}

        def action() -> dict[int, set[str]]:
            result: dict[int, set[str]] = {}
            with self._lock:
                for offset in range(0, len(ids), 500):
                    batch = ids[offset:offset + 500]
                    placeholders = ",".join("?" for _ in batch)
                    for movie_id, name in self._db.execute(
                        f"SELECT movie_id, name FROM movie_cast "
                        f"WHERE movie_id IN ({placeholders})",
                        batch,
                    ):
                        result.setdefault(int(movie_id), set()).add(str(name))
            return result

        return self._call(action)

    def similar(self, movie_id: int, limit: int = 6) -> list[dict[str, Any]]:
        """Похожие фильмы по локальным ключевым словам и жанрам."""
        return self.similar_by(movie_id, ("genres", "keywords"), limit)

    def similar_by(
        self, movie_id: int, signals: Iterable[str], limit: int = 60
    ) -> list[dict[str, Any]]:
        """Ranks matches using only selected signals already stored locally."""
        allowed = {"actors", "director", "genres", "keywords"}
        selected = set(signals)
        if selected - allowed:
            raise ValueError("Неизвестный признак для поиска похожих фильмов.")
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 0:
            raise ValueError("Лимит должен быть неотрицательным целым числом.")
        if not selected or limit == 0:
            return []
        source = self.get(movie_id)
        if source is None:
            return []

        actors = self.cast_of(movie_id, 100) if "actors" in selected else []
        keywords = self.keywords_of(movie_id, 500) if "keywords" in selected else []
        genres = [item for item in (source.get("genres") or "").split(",") if item] \
            if "genres" in selected else []
        director = str(source.get("director") or "").strip() if "director" in selected else ""
        conditions: list[str] = []
        args: list[Any] = [movie_id]
        if actors:
            conditions.append(
                "EXISTS (SELECT 1 FROM movie_cast c WHERE c.movie_id=m.id "
                f"AND LOWER(c.name) IN ({','.join('LOWER(?)' for _ in actors)}))"
            )
            args.extend(actors)
        if director:
            conditions.append("LOWER(TRIM(COALESCE(m.director, ''))) = LOWER(?)")
            args.append(director)
        if genres:
            conditions.append("(" + " OR ".join(["m.genres LIKE ?"] * len(genres)) + ")")
            args.extend(f"%,{genre},%" for genre in genres)
        if keywords:
            conditions.append(
                "EXISTS (SELECT 1 FROM movie_keywords k WHERE k.movie_id=m.id "
                f"AND LOWER(k.keyword) IN ({','.join('LOWER(?)' for _ in keywords)}))"
            )
            args.extend(keywords)
        if not conditions:
            return []
        exclusion_sql, exclusion_args = self._content_exclusion_conditions("m")
        query = (
            "SELECT m.* FROM movies m WHERE m.id <> ? AND ("
            + " OR ".join(conditions) + ")"
        )
        if exclusion_sql:
            query += " AND NOT (" + exclusion_sql + ")"
            args.extend(exclusion_args)
        query += (
            f" ORDER BY {SORTS['rating']} LIMIT 1000"
        )

        def action() -> list[dict[str, Any]]:
            with self._lock:
                candidates = [dict(row) for row in self._db.execute(query, args)]
                candidate_ids = [int(row["id"]) for row in candidates]
                candidate_cast: dict[int, set[str]] = {}
                candidate_keywords: dict[int, set[str]] = {}
                for offset in range(0, len(candidate_ids), 500):
                    ids = candidate_ids[offset:offset + 500]
                    if not ids:
                        continue
                    placeholders = ",".join("?" for _ in ids)
                    for candidate_id, name in self._db.execute(
                        f"SELECT movie_id, name FROM movie_cast WHERE movie_id IN ({placeholders})",
                        ids,
                    ):
                        candidate_cast.setdefault(int(candidate_id), set()).add(name)
                    for candidate_id, keyword in self._db.execute(
                        f"SELECT movie_id, keyword FROM movie_keywords "
                        f"WHERE movie_id IN ({placeholders})",
                        ids,
                    ):
                        candidate_keywords.setdefault(int(candidate_id), set()).add(keyword)

            results = []
            source_actors = {actor.casefold(): actor for actor in actors}
            source_keywords = {keyword.casefold(): keyword for keyword in keywords}
            source_genres = set(genres)
            for candidate in candidates:
                candidate_id = int(candidate["id"])
                reasons: list[dict[str, str]] = []
                score = 0
                if director and (candidate.get("director") or "").strip().casefold() == director.casefold():
                    score += 4
                    reasons.append({"type": "director", "value": director})
                matching_actors = {
                    source_actors[value.casefold()]
                    for value in candidate_cast.get(candidate_id, set())
                    if value.casefold() in source_actors
                }
                for actor in sorted(matching_actors):
                    score += 3
                    reasons.append({"type": "actor", "value": actor})
                matching_keywords = {
                    source_keywords[value.casefold()]
                    for value in candidate_keywords.get(candidate_id, set())
                    if value.casefold() in source_keywords
                }
                for keyword in sorted(matching_keywords):
                    score += 2
                    reasons.append({"type": "keyword", "value": keyword})
                other_genres = set((candidate.get("genres") or "").split(",")) - {""}
                for genre in sorted(source_genres & other_genres):
                    score += 1
                    reasons.append({"type": "genre", "value": genre})
                candidate["similarity_score"] = score
                candidate["similarity_reasons"] = reasons
                results.append(candidate)
            results.sort(key=lambda row: (
                -row["similarity_score"],
                -float(row.get("rating") or 0),
                -int(row.get("votes") or 0),
                int(row["id"]),
            ))
            return results[:limit]

        return self._call(action)

    def _content_exclusion_conditions(
        self, alias: str = "movies"
    ) -> tuple[str, list[Any]]:
        with self._lock:
            rows = self._db.execute(
                "SELECT kind, value FROM content_exclusions ORDER BY kind, value"
            ).fetchall()
        conditions: list[str] = []
        args: list[Any] = []
        from .const import CATEGORY_FILTERS

        for row in rows:
            kind, value = str(row["kind"]), str(row["value"])
            if kind == "genre":
                conditions.append(f"{alias}.genres LIKE ?")
                args.append(f"%,{value},%")
            elif kind == "theme" and value in CATEGORY_FILTERS:
                definition = CATEGORY_FILTERS[value]
                parts = []
                for genre in definition["genres"]:
                    parts.append(f"{alias}.genres LIKE ?")
                    args.append(f"%,{genre},%")
                for term in definition["terms"]:
                    variants = {term.casefold()}
                    if any(ord(char) > 127 for char in term):
                        variants.add(term[:1].upper() + term[1:])
                        variants.add(term.upper())
                    for variant in variants:
                        pattern = f"%{variant}%"
                        parts.append(
                            f"(LOWER(COALESCE({alias}.title, '') || ' ' || "
                            f"COALESCE({alias}.original_title, '') || ' ' || "
                            f"COALESCE({alias}.overview, '') || ' ' || "
                            f"COALESCE({alias}.overview_en, '')) LIKE ? OR EXISTS "
                            f"(SELECT 1 FROM movie_keywords k WHERE k.movie_id={alias}.id "
                            "AND LOWER(k.keyword) LIKE ?))"
                        )
                        args.extend([pattern, pattern])
                if parts:
                    conditions.append("(" + " OR ".join(parts) + ")")
        return " OR ".join(conditions), args

    # ------------------------------------------------- закладки и история
    def poster_candidates(self, limit: int, only_unchecked: bool = True) -> list[tuple[int, str]]:
        """Фильмы с постером: (id, путь). Для массовой проверки ссылок."""

        def action() -> list[tuple[int, str]]:
            with self._lock:
                where = "COALESCE(poster_path, '') <> ''"
                if only_unchecked:
                    where += " AND COALESCE(poster_checked, 0) = 0"
                rows = self._db.execute(
                    f"SELECT id, poster_path FROM movies WHERE {where} "
                    "ORDER BY COALESCE(votes, 0) DESC, id LIMIT ?",
                    (limit,),
                ).fetchall()
            return [(int(r[0]), str(r[1])) for r in rows]

        return self._call(action)

    def update_poster(self, movie_id: int, poster_path: str) -> None:
        def action() -> None:
            with self._lock:
                self._db.execute(
                    "UPDATE movies SET poster_path = ?, poster_checked = 1 WHERE id = ?",
                    (poster_path, movie_id),
                )
                self._db.commit()

        self._call(action)

    def update_overview(self, movie_id: int, overview: str) -> None:
        def action() -> None:
            with self._lock:
                self._db.execute(
                    "UPDATE movies SET overview = ? WHERE id = ?", (overview, movie_id)
                )
                self._db.commit()

        self._call(action)

    def set_english_overview(self, movie_id: int, overview: str | None) -> None:
        """Кэширует английское описание независимо от русского и постеров."""

        def action() -> None:
            with self._lock:
                self._db.execute(
                    "UPDATE movies SET overview_en = ?, overview_en_checked = 1 WHERE id = ?",
                    ((overview or "").strip() or None, int(movie_id)),
                )
                self._db.commit()

        self._call(action)

    def films_without_overview(self, limit: int) -> list[int]:
        def action() -> list[int]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT id FROM movies "
                    "WHERE id > 0 AND LENGTH(COALESCE(overview, '')) <= 40 "
                    "ORDER BY COALESCE(votes, 0) DESC LIMIT ?",
                    (int(limit),),
                ).fetchall()
            return [int(r[0]) for r in rows]

        return self._call(action)

    def mark_posters_checked(self, ids: list[int]) -> int:
        def action() -> int:
            with self._lock:
                cursor = self._db.executemany(
                    "UPDATE movies SET poster_checked = 1 WHERE id = ?",
                    [(movie_id,) for movie_id in ids],
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def poster_stats(self) -> dict[str, int]:
        def action() -> dict[str, int]:
            with self._lock:
                total = int(self._db.execute("SELECT COUNT(*) FROM movies").fetchone()[0])
                with_path = int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM movies WHERE COALESCE(poster_path, '') <> ''"
                    ).fetchone()[0]
                )
                checked = int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM movies WHERE COALESCE(poster_checked, 0) = 1"
                    ).fetchone()[0]
                )
                local = int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM movies WHERE COALESCE(poster_file, '') <> ''"
                    ).fetchone()[0]
                )
            return {"total": total, "with_path": with_path, "checked": checked, "local": local}

        return self._call(action)

    def set_providers(self, rows: list[tuple[int, str, str, str | None]]) -> int:
        """Площадки показа: [(movie_id, регион, «Netflix, Okko», ссылка)]."""

        def action() -> int:
            with self._lock:
                cursor = self._db.executemany(
                    "INSERT INTO providers (movie_id, region, names, link, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(movie_id, region) DO UPDATE SET "
                    "names = excluded.names, link = excluded.link, "
                    "updated_at = excluded.updated_at",
                    [
                        (row[0], row[1], row[2], row[3], datetime.now().isoformat(timespec="seconds"))
                        for row in rows
                    ],
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def providers_of(self, movie_id: int) -> dict[str, Any] | None:
        def action():
            with self._lock:
                return self._db.execute(
                    "SELECT region, names, link, updated_at FROM providers "
                    "WHERE movie_id = ? AND names <> '' "
                    "ORDER BY CASE region WHEN 'RU' THEN 0 WHEN 'US' THEN 1 ELSE 2 END "
                    "LIMIT 1",
                    (movie_id,),
                ).fetchone()

        row = self._call(action)
        return dict(row) if row else None

    def providers_missing(self, from_year: int, limit: int = 300) -> list[int]:
        """Фильмы, для которых площадки ещё не записаны."""

        def action() -> list[int]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT m.id FROM movies AS m "
                    "WHERE m.id > 0 AND COALESCE(m.year, 0) >= ? "
                    "AND NOT EXISTS (SELECT 1 FROM providers AS p "
                    "                WHERE p.movie_id = m.id AND p.names <> '') "
                    "ORDER BY COALESCE(m.votes, 0) DESC LIMIT ?",
                    (int(from_year), int(limit)),
                ).fetchall()
            return [int(r[0]) for r in rows]

        return self._call(action)

    def providers_count(self) -> int:
        def action() -> int:
            with self._lock:
                return int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM providers WHERE names <> ''"
                    ).fetchone()[0]
                )

        return self._call(action)

    def toggle_bookmark(self, movie_id: int) -> bool:
        """Ставит/снимает закладку. Возвращает True, если теперь в закладках."""

        def action() -> bool:
            with self._lock:
                exists = self._db.execute(
                    "SELECT 1 FROM bookmarks WHERE movie_id = ?", (movie_id,)
                ).fetchone()
                if exists:
                    self._db.execute(
                        "DELETE FROM bookmarks WHERE movie_id = ?", (movie_id,)
                    )
                    result = False
                else:
                    self._db.execute(
                        "INSERT INTO bookmarks (movie_id, added_at) VALUES (?, ?)",
                        (movie_id, datetime.now().isoformat(timespec="seconds")),
                    )
                    result = True
                self._db.commit()
                return result

        # Переключатель немедемпотентен: повтор после сбоя вернул бы прежнее
        # состояние и показал пользователю обратное.
        return self._call(action, attempts=0)

    def is_bookmarked(self, movie_id: int) -> bool:
        def action() -> bool:
            with self._lock:
                return (
                    self._db.execute(
                        "SELECT 1 FROM bookmarks WHERE movie_id = ?", (movie_id,)
                    ).fetchone()
                    is not None
                )

        return self._call(action)

    def bookmarks_count(self) -> int:
        def action() -> int:
            with self._lock:
                return int(
                    self._db.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
                )

        return self._call(action)

    @staticmethod
    def _validate_watchlist_values(priority: int, note: str) -> tuple[int, str]:
        if isinstance(priority, bool) or not isinstance(priority, int) or not 1 <= priority <= 5:
            raise ValueError("Приоритет должен быть целым числом от 1 до 5.")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Заметка должна быть текстом длиной не более 2000 символов.")
        return priority, note.strip()

    def set_watchlist(self, movie_id: int, *, priority: int = 3, note: str = "") -> None:
        """Добавляет фильм в список или идемпотентно обновляет его приоритет и заметку."""
        if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
            raise ValueError("ID фильма должен быть положительным целым числом.")
        priority, note = self._validate_watchlist_values(priority, note)
        now = datetime.now().isoformat(timespec="seconds")

        def action() -> None:
            with self._lock:
                exists = self._db.execute(
                    "SELECT 1 FROM movies WHERE id = ?", (movie_id,)
                ).fetchone()
                if exists is None:
                    raise ValueError(f"Фильм с id={movie_id} не найден.")
                self._db.execute(
                    "INSERT INTO watchlist (movie_id, priority, note, added_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(movie_id) DO UPDATE SET "
                    "priority = excluded.priority, note = excluded.note, "
                    "updated_at = excluded.updated_at "
                    "WHERE watchlist.priority <> excluded.priority "
                    "OR watchlist.note <> excluded.note",
                    (movie_id, priority, note, now, now),
                )
                self._db.commit()

        self._call(action)

    def add_to_watchlist(
        self, movie_id: int, *, priority: int = 3, note: str = ""
    ) -> bool:
        """Добавляет фильм, не затирая уже сохранённые приоритет и заметку.

        Возвращает True, если запись создана; False — если фильм уже в списке.
        """
        if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
            raise ValueError("ID фильма должен быть положительным целым числом.")
        priority, note = self._validate_watchlist_values(priority, note)
        now = datetime.now().isoformat(timespec="seconds")

        def action() -> bool:
            with self._lock:
                if self._db.execute(
                    "SELECT 1 FROM movies WHERE id = ?", (movie_id,)
                ).fetchone() is None:
                    raise ValueError(f"Фильм с id={movie_id} не найден.")
                cursor = self._db.execute(
                    "INSERT INTO watchlist (movie_id, priority, note, added_at, updated_at) "
                    "VALUES (?, ?, ?, ?, ?) ON CONFLICT(movie_id) DO NOTHING",
                    (movie_id, priority, note, now, now),
                )
                self._db.commit()
                return bool(cursor.rowcount)

        return self._call(action)

    def watchlist_entry(self, movie_id: int) -> dict[str, Any] | None:
        if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
            raise ValueError("ID фильма должен быть положительным целым числом.")

        def action() -> dict[str, Any] | None:
            with self._lock:
                row = self._db.execute(
                    "SELECT movie_id, priority, note, added_at, updated_at "
                    "FROM watchlist WHERE movie_id = ?", (movie_id,)
                ).fetchone()
            return dict(row) if row else None

        return self._call(action)

    def watchlist(self) -> list[dict[str, Any]]:
        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT m.*, w.priority AS watchlist_priority, "
                    "w.note AS watchlist_note, w.added_at AS watchlist_added_at, "
                    "w.updated_at AS watchlist_updated_at "
                    "FROM watchlist AS w JOIN movies AS m ON m.id = w.movie_id "
                    "ORDER BY w.priority DESC, w.updated_at DESC, m.title COLLATE NOCASE"
                ).fetchall()
            return [dict(row) for row in rows]

        return self._call(action)

    def remove_from_watchlist(self, movie_id: int) -> bool:
        if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
            raise ValueError("ID фильма должен быть положительным целым числом.")

        def action() -> bool:
            with self._lock:
                cursor = self._db.execute(
                    "DELETE FROM watchlist WHERE movie_id = ?", (movie_id,)
                )
                self._db.commit()
                return cursor.rowcount > 0

        return self._call(action)

    def watchlist_count(self) -> int:
        def action() -> int:
            with self._lock:
                return int(self._db.execute("SELECT COUNT(*) FROM watchlist").fetchone()[0])

        return self._call(action)

    @staticmethod
    def _validate_plan_values(planned_date: str, note: str) -> tuple[str, str]:
        if not isinstance(planned_date, str):
            raise ValueError("Дата плана должна быть в формате ГГГГ-ММ-ДД.")
        try:
            clean_date = date.fromisoformat(planned_date).isoformat()
        except ValueError as exc:
            raise ValueError("Дата плана должна быть в формате ГГГГ-ММ-ДД.") from exc
        if clean_date != planned_date:
            raise ValueError("Дата плана должна быть в формате ГГГГ-ММ-ДД.")
        if not isinstance(note, str) or len(note) > 2000:
            raise ValueError("Заметка не должна превышать 2000 символов.")
        return clean_date, note.strip()

    def add_plan(self, movie_id: int, planned_date: str, note: str = "") -> int:
        if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
            raise ValueError("ID фильма должен быть положительным целым числом.")
        clean_date, clean_note = self._validate_plan_values(planned_date, note)

        def action() -> int:
            with self._lock:
                try:
                    if self._db.execute(
                        "SELECT 1 FROM movies WHERE id=?", (int(movie_id),)
                    ).fetchone() is None:
                        raise ValueError(f"Фильм с id={movie_id} не найден.")
                    now = datetime.now().isoformat(timespec="seconds")
                    cursor = self._db.execute(
                        "INSERT INTO viewing_plans "
                        "(movie_id, planned_date, note, status, created_at, updated_at) "
                        "VALUES (?, ?, ?, 'planned', ?, ?)",
                        (int(movie_id), clean_date, clean_note, now, now),
                    )
                    self._db.commit()
                    return int(cursor.lastrowid or 0)
                except sqlite3.IntegrityError as exc:
                    self._db.rollback()
                    if self._db.execute(
                        "SELECT 1 FROM movies WHERE id=?", (int(movie_id),)
                    ).fetchone() is None:
                        raise ValueError(f"Фильм с id={movie_id} не найден.") from exc
                    raise ValueError("Для этого фильма на выбранную дату план уже есть.") from exc

        return self._call(action)

    def update_plan(
        self, plan_id: int, planned_date: str, note: str = ""
    ) -> None:
        if isinstance(plan_id, bool) or not isinstance(plan_id, int) or plan_id <= 0:
            raise ValueError("ID плана должен быть положительным целым числом.")
        clean_date, clean_note = self._validate_plan_values(planned_date, note)

        def action() -> None:
            with self._lock:
                try:
                    cursor = self._db.execute(
                        "UPDATE viewing_plans SET planned_date=?, note=?, "
                        "updated_at=? WHERE id=?",
                        (clean_date, clean_note, datetime.now().isoformat(timespec="seconds"),
                         int(plan_id)),
                    )
                    if cursor.rowcount == 0:
                        raise ValueError(f"План с id={plan_id} не найден.")
                    self._db.commit()
                except sqlite3.IntegrityError as exc:
                    self._db.rollback()
                    raise ValueError("Для этого фильма на выбранную дату план уже есть.") from exc

        self._call(action)

    def complete_plan(self, plan_id: int) -> None:
        """Only explicit user action completes a plan and marks its movie watched."""
        if isinstance(plan_id, bool) or not isinstance(plan_id, int) or plan_id <= 0:
            raise ValueError("ID плана должен быть положительным целым числом.")
        def action() -> None:
            with self._lock:
                try:
                    self._db.execute("BEGIN IMMEDIATE")
                    row = self._db.execute(
                        "SELECT movie_id FROM viewing_plans WHERE id=?", (int(plan_id),)
                    ).fetchone()
                    if row is None:
                        raise ValueError(f"План с id={plan_id} не найден.")
                    watched_cursor = self._db.execute(
                        "UPDATE movies SET watched=1 WHERE id=?", (int(row["movie_id"]),)
                    )
                    if watched_cursor.rowcount == 0:
                        raise ValueError(f"Фильм с id={row['movie_id']} не найден.")
                    self._db.execute(
                        "UPDATE viewing_plans SET status='completed', updated_at=? WHERE id=?",
                        (datetime.now().isoformat(timespec="seconds"), int(plan_id)),
                    )
                    self._db.commit()
                except Exception:
                    self._db.rollback()
                    raise

        self._call(action, attempts=1)

    def delete_plan(self, plan_id: int) -> bool:
        if isinstance(plan_id, bool) or not isinstance(plan_id, int) or plan_id <= 0:
            raise ValueError("ID плана должен быть положительным целым числом.")
        def action() -> bool:
            with self._lock:
                cursor = self._db.execute(
                    "DELETE FROM viewing_plans WHERE id=?", (int(plan_id),)
                )
                self._db.commit()
                return cursor.rowcount > 0

        return self._call(action)

    def plans(self, *, upcoming_only: bool = False) -> list[dict[str, Any]]:
        def action() -> list[dict[str, Any]]:
            with self._lock:
                where = "WHERE p.status='planned' AND p.planned_date >= ?" if upcoming_only else ""
                today = date.today().isoformat()
                args = (today, today) if upcoming_only else (today,)
                rows = self._db.execute(
                    "SELECT p.*, m.title, m.year, m.poster_path FROM viewing_plans p "
                    "JOIN movies m ON m.id=p.movie_id " + where
                    + " ORDER BY CASE WHEN p.status='planned' AND p.planned_date >= ? "
                    "THEN 0 WHEN p.status='planned' THEN 1 ELSE 2 END, p.planned_date, p.id",
                    args,
                ).fetchall()
            return [dict(row) for row in rows]

        return self._call(action)

    def content_exclusions(self) -> dict[str, list[str]]:
        def action() -> dict[str, list[str]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT kind, value FROM content_exclusions ORDER BY kind, value"
                ).fetchall()
            return {
                kind: [str(row["value"]) for row in rows if row["kind"] == kind]
                for kind in ("genre", "theme")
            }

        return self._call(action)

    def set_content_exclusions(
        self, *, genres: Iterable[str] = (), themes: Iterable[str] = ()
    ) -> None:
        from .const import CATEGORY_FILTERS

        mood_categories = {
            "uplifting", "light", "tense", "romantic", "thoughtful", "family_night",
        }

        def clean(values: Iterable[str], allowed: set[str] | None = None) -> list[str]:
            if isinstance(values, str):
                raise ValueError("Исключения должны быть списком.")
            result = []
            for value in values:
                if not isinstance(value, str) or not value.strip() or len(value) > 100:
                    raise ValueError("Некорректное значение исключения.")
                value = value.strip().casefold()
                if allowed is not None and value not in allowed:
                    raise ValueError("Выбрана неизвестная тема.")
                if value not in result:
                    result.append(value)
            return result

        clean_genres = clean(genres)
        allowed_themes = set(CATEGORY_FILTERS) - mood_categories
        clean_themes = clean(themes, allowed_themes)

        def action() -> None:
            with self._lock:
                try:
                    self._db.execute("BEGIN IMMEDIATE")
                    self._db.execute("DELETE FROM content_exclusions")
                    self._db.executemany(
                        "INSERT INTO content_exclusions(kind, value) VALUES ('genre', ?)",
                        [(value,) for value in clean_genres],
                    )
                    self._db.executemany(
                        "INSERT INTO content_exclusions(kind, value) VALUES ('theme', ?)",
                        [(value,) for value in clean_themes],
                    )
                    self._db.commit()
                except Exception:
                    self._db.rollback()
                    raise

        self._call(action, attempts=1)

    def save_sequel_check(
        self,
        anchor_movie_id: int,
        collection_id: int | None,
        parts: list[dict[str, Any]] | None = None,
    ) -> int:
        """Stores a collection baseline and returns newly discovered parts."""
        if isinstance(anchor_movie_id, bool) or not isinstance(anchor_movie_id, int) or anchor_movie_id <= 0:
            raise ValueError("ID фильма должен быть положительным целым числом.")
        if collection_id is not None and (
            isinstance(collection_id, bool)
            or not isinstance(collection_id, int)
            or collection_id <= 0
        ):
            raise ValueError("ID коллекции TMDb должен быть положительным целым числом.")
        now = datetime.now().isoformat(timespec="seconds")
        valid_parts: dict[int, dict[str, Any]] = {}
        for part in parts or []:
            movie_id = part.get("id")
            if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
                continue
            title = str(part.get("title") or part.get("name") or "").strip()
            if not title:
                continue
            release_date = str(part.get("release_date") or "").strip() or None
            release_year = (
                int(release_date[:4])
                if release_date and release_date[:4].isdigit()
                else None
            )
            valid_parts[movie_id] = {
                "title": title,
                "release_date": release_date,
                "year": release_year,
                "url": f"https://www.themoviedb.org/movie/{movie_id}",
            }

        def action() -> int:
            with self._lock:
                self._db.execute(
                    "INSERT INTO sequel_monitor (anchor_movie_id, collection_id, checked_at) "
                    "VALUES (?, ?, ?) ON CONFLICT(anchor_movie_id) DO UPDATE SET "
                    "collection_id = excluded.collection_id, checked_at = excluded.checked_at",
                    (anchor_movie_id, collection_id, now),
                )
                if collection_id is None:
                    self._db.commit()
                    return 0

                state = self._db.execute(
                    "SELECT known_movie_ids FROM sequel_collection_state "
                    "WHERE collection_id = ?",
                    (collection_id,),
                ).fetchone()
                previous_ids = (
                    {int(value) for value in json.loads(state["known_movie_ids"])}
                    if state is not None
                    else None
                )
                new_parts = (
                    {movie_id: part for movie_id, part in valid_parts.items()
                     if movie_id not in previous_ids}
                    if previous_ids is not None
                    else {}
                )
                inserted_count = 0
                if new_parts:
                    for movie_id, part in new_parts.items():
                        cursor = self._db.execute(
                            "INSERT OR IGNORE INTO sequel_notifications "
                            "(collection_id, movie_id, title, year, release_date, url, created_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            (
                                collection_id, movie_id, part["title"], part["year"],
                                part["release_date"], part["url"], now,
                            ),
                        )
                        inserted_count += int(cursor.rowcount or 0)
                known_ids = (previous_ids or set()) | set(valid_parts)
                self._db.execute(
                    "INSERT INTO sequel_collection_state "
                    "(collection_id, known_movie_ids, checked_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(collection_id) DO UPDATE SET "
                    "known_movie_ids = excluded.known_movie_ids, checked_at = excluded.checked_at",
                    (collection_id, json.dumps(sorted(known_ids)), now),
                )
                self._db.commit()
                return inserted_count

        return self._call(action)

    def sequel_notifications(self, *, unread_only: bool = False) -> list[dict[str, Any]]:
        def action() -> list[dict[str, Any]]:
            with self._lock:
                where = "WHERE is_read = 0 " if unread_only else ""
                rows = self._db.execute(
                    "SELECT collection_id, movie_id, title, year, release_date, url, "
                    "created_at, is_read FROM sequel_notifications "
                    f"{where}ORDER BY COALESCE(release_date, ''), title COLLATE NOCASE"
                ).fetchall()
                return [dict(row) for row in rows]

        return self._call(action)

    def sequel_notification_count(self) -> int:
        def action() -> int:
            with self._lock:
                return int(
                    self._db.execute(
                        "SELECT COUNT(*) FROM sequel_notifications WHERE is_read = 0"
                    ).fetchone()[0]
                )

        return self._call(action)

    def sequel_anchors_checked_since(self, since: str) -> set[int]:
        """Anchor-фильмы, коллекции которых уже проверялись не раньше `since`.

        Нужно, чтобы автопроверка при запуске не опрашивала TMDb заново по
        всему списку «Хочу посмотреть» при каждом старте.
        """

        def action() -> set[int]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT anchor_movie_id FROM sequel_monitor WHERE checked_at >= ?",
                    (str(since),),
                ).fetchall()
            return {int(row[0]) for row in rows}

        return self._call(action)

    def mark_sequel_notifications_read(self) -> int:
        def action() -> int:
            with self._lock:
                cursor = self._db.execute(
                    "UPDATE sequel_notifications SET is_read = 1 WHERE is_read = 0"
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def set_recommendation_feedback(self, movie_id: int, feedback: str | None) -> None:
        """Sets or clears the user's like/dislike for a recommendation."""
        if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
            raise ValueError("ID фильма должен быть положительным целым числом.")
        if feedback not in (None, "like", "dislike"):
            raise ValueError("Отзыв должен быть like, dislike или null.")
        now = datetime.now().isoformat(timespec="seconds")

        def action() -> None:
            with self._lock:
                exists = self._db.execute(
                    "SELECT 1 FROM movies WHERE id = ?", (movie_id,)
                ).fetchone()
                if exists is None:
                    raise ValueError(f"Фильм с id={movie_id} не найден.")
                if feedback is None:
                    self._db.execute(
                        "DELETE FROM recommendation_feedback WHERE movie_id = ?",
                        (movie_id,),
                    )
                else:
                    self._db.execute(
                        "INSERT INTO recommendation_feedback (movie_id, feedback, updated_at) "
                        "VALUES (?, ?, ?) ON CONFLICT(movie_id) DO UPDATE SET "
                        "feedback = excluded.feedback, updated_at = excluded.updated_at "
                        "WHERE recommendation_feedback.feedback <> excluded.feedback",
                        (movie_id, feedback, now),
                    )
                self._db.commit()

        self._call(action)

    def recommendation_feedback(self) -> list[dict[str, Any]]:
        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT m.*, f.feedback AS recommendation_feedback, "
                    "f.updated_at AS feedback_updated_at "
                    "FROM recommendation_feedback AS f "
                    "JOIN movies AS m ON m.id = f.movie_id "
                    "ORDER BY f.updated_at DESC, m.title COLLATE NOCASE"
                ).fetchall()
            return [dict(row) for row in rows]

        return self._call(action)

    def catalog_quality_issues(
        self,
        *,
        short_description_chars: int = 30,
        min_year: int = 1874,
        current_year: int | None = None,
    ) -> list[dict[str, Any]]:
        """Inspects catalogue metadata only; this method never writes to the database."""
        if (isinstance(short_description_chars, bool)
                or not isinstance(short_description_chars, int)
                or short_description_chars < 1):
            raise ValueError("Минимальная длина описания должна быть положительным числом.")
        if isinstance(min_year, bool) or not isinstance(min_year, int) or min_year < 1:
            raise ValueError("Минимальный год должен быть положительным целым числом.")
        if current_year is None:
            current_year = datetime.now().year
        if isinstance(current_year, bool) or not isinstance(current_year, int):
            raise ValueError("Текущий год должен быть целым числом.")

        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT id, title, original_title, year, release_date, overview, "
                    "overview_en, source FROM movies ORDER BY id"
                ).fetchall()

            title_groups: dict[tuple[str, int | None], set[int]] = {}
            for row in rows:
                movie_id = int(row["id"])
                for title in {row["title"], row["original_title"]}:
                    normalized = _normalize_title(title)
                    if normalized:
                        title_groups.setdefault(
                            (normalized, row["year"]), set()
                        ).add(movie_id)
            duplicate_ids: dict[int, set[int]] = {}
            for ids in title_groups.values():
                if len(ids) < 2:
                    continue
                for movie_id in ids:
                    duplicate_ids.setdefault(movie_id, set()).update(ids - {movie_id})

            issues: list[dict[str, Any]] = []
            for row in rows:
                year = row["year"]
                descriptions = [
                    str(row[key] or "").strip()
                    for key in ("overview", "overview_en")
                    if str(row[key] or "").strip()
                ]
                flags: list[str] = []
                if int(row["id"]) in duplicate_ids:
                    flags.append("duplicate_title")
                if year is None:
                    flags.append("missing_year")
                elif int(year) < min_year or int(year) > current_year:
                    flags.append("invalid_year")
                release_date = str(row["release_date"] or "")
                date_year = release_date[:4]
                if year is not None and date_year.isdigit() and int(date_year) != int(year):
                    flags.append("year_mismatch")
                longest_description = max((len(text) for text in descriptions), default=0)
                if not descriptions:
                    flags.append("empty_description")
                elif longest_description < short_description_chars:
                    flags.append("short_description")
                if flags:
                    issues.append({
                        "id": int(row["id"]),
                        "title": str(row["title"] or ""),
                        "year": int(year) if year is not None else None,
                        "source": str(row["source"] or ""),
                        "flags": flags,
                        "duplicate_ids": sorted(duplicate_ids.get(int(row["id"]), set())),
                        "description_length": longest_description,
                    })
            return issues

        return self._call(action)

    def taste_stats(self) -> dict[str, Any]:
        """Aggregates only the user's saved ratings, watched state, and view history."""
        def action() -> dict[str, Any]:
            with self._lock:
                summary = self._db.execute(
                    "SELECT "
                    "SUM(CASE WHEN watched = 1 THEN 1 ELSE 0 END) AS watched, "
                    "COUNT(personal_rating) AS rated, AVG(personal_rating) AS average_rating "
                    "FROM movies WHERE watched = 1 OR personal_rating IS NOT NULL"
                ).fetchone()
                bookmarks = int(
                    self._db.execute("SELECT COUNT(*) FROM bookmarks").fetchone()[0]
                )
                history_count = int(
                    self._db.execute("SELECT COUNT(*) FROM history").fetchone()[0]
                )
                history = self._db.execute(
                    "SELECT substr(viewed_at, 1, 7) AS month, COUNT(*) AS count "
                    "FROM history WHERE viewed_at IS NOT NULL "
                    "GROUP BY month ORDER BY month DESC LIMIT 24"
                ).fetchall()
                rating_rows = self._db.execute(
                    "SELECT personal_rating, COUNT(*) AS count FROM movies "
                    "WHERE personal_rating IS NOT NULL GROUP BY personal_rating "
                    "ORDER BY personal_rating"
                ).fetchall()
                personal_movies = self._db.execute(
                    "SELECT year, genres, personal_rating FROM movies "
                    "WHERE watched = 1 OR personal_rating IS NOT NULL"
                ).fetchall()

            genre_totals: dict[str, list[float]] = {}
            year_counts: dict[int, int] = {}
            for row in personal_movies:
                year = row["year"]
                if year:
                    year_counts[int(year)] = year_counts.get(int(year), 0) + 1
                rating = row["personal_rating"]
                for genre in (row["genres"] or "").split(","):
                    if not genre:
                        continue
                    values = genre_totals.setdefault(genre, [0.0, 0.0, 0.0])
                    values[0] += 1
                    if rating is not None:
                        values[1] += float(rating)
                        values[2] += 1

            genres = [
                {
                    "genre": genre,
                    "count": int(values[0]),
                    "average_rating": round(values[1] / values[2], 2)
                    if values[2]
                    else None,
                }
                for genre, values in genre_totals.items()
            ]
            genres.sort(
                key=lambda item: (
                    -int(item["count"] or 0),
                    -float(item["average_rating"] or 0),
                    str(item["genre"]),
                )
            )
            return {
                "watched": int(summary["watched"] or 0),
                "rated": int(summary["rated"] or 0),
                "average_rating": round(float(summary["average_rating"]), 2)
                if summary["average_rating"] is not None
                else None,
                "bookmarked": bookmarks,
                "history_count": history_count,
                "rating_distribution": [
                    {"rating": int(row["personal_rating"]), "count": int(row["count"])}
                    for row in rating_rows
                ],
                "favorite_genres": genres[:10],
                "years": [
                    {"year": year, "count": year_counts[year]}
                    for year in sorted(year_counts, reverse=True)[:12]
                ],
                "activity_by_month": [
                    {"month": str(row["month"]), "count": int(row["count"])}
                    for row in history
                ],
            }

        return self._call(action)

    def saved_filters(self) -> list[dict[str, Any]]:
        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT name, filters_json, updated_at FROM saved_filters ORDER BY name COLLATE NOCASE"
                ).fetchall()
            return [
                {"name": str(row["name"]), "filters": json.loads(row["filters_json"]),
                 "updated_at": str(row["updated_at"])}
                for row in rows
            ]

        return self._call(action)

    def save_filter(self, name: str, filters: dict[str, Any]) -> None:
        if not isinstance(name, str):
            raise ValueError("Название подборки должно быть текстом.")
        clean_name = name.strip()
        if not clean_name or len(clean_name) > 80:
            raise ValueError("Название подборки должно содержать от 1 до 80 символов.")
        if not isinstance(filters, dict) or set(filters) - PERSONAL_FILTER_KEYS:
            raise ValueError("Подборка содержит неподдерживаемые параметры фильтра.")
        try:
            payload = json.dumps(filters, ensure_ascii=False, sort_keys=True)
        except (TypeError, ValueError) as exc:
            raise ValueError("Параметры фильтра не могут быть сохранены.") from exc

        def action() -> None:
            with self._lock:
                self._db.execute(
                    "INSERT INTO saved_filters (name, filters_json, updated_at) VALUES (?, ?, ?) "
                    "ON CONFLICT(name) DO UPDATE SET filters_json = excluded.filters_json, "
                    "updated_at = excluded.updated_at",
                    (clean_name, payload, datetime.now().isoformat(timespec="seconds")),
                )
                self._db.commit()

        self._call(action)

    def delete_filter(self, name: str) -> bool:
        def action() -> bool:
            with self._lock:
                cursor = self._db.execute("DELETE FROM saved_filters WHERE name = ?", (name,))
                self._db.commit()
                return cursor.rowcount > 0

        return self._call(action)

    def export_personal_data(self) -> dict[str, Any]:
        """Экспортирует только пользовательские состояния; без данных каталога и секретов."""
        def action() -> dict[str, Any]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT m.id, m.watched, m.personal_rating, "
                    "EXISTS (SELECT 1 FROM bookmarks b WHERE b.movie_id = m.id) AS bookmarked "
                    "FROM movies m WHERE m.watched = 1 OR m.personal_rating IS NOT NULL "
                    "OR EXISTS (SELECT 1 FROM bookmarks b WHERE b.movie_id = m.id) "
                    "ORDER BY m.id"
                ).fetchall()
                filters = self._db.execute(
                    "SELECT name, filters_json FROM saved_filters ORDER BY name COLLATE NOCASE"
                ).fetchall()
                watchlist = self._db.execute(
                    "SELECT movie_id, priority, note FROM watchlist ORDER BY movie_id"
                ).fetchall()
                feedback = self._db.execute(
                    "SELECT movie_id, feedback FROM recommendation_feedback ORDER BY movie_id"
                ).fetchall()
                plans = self._db.execute(
                    "SELECT movie_id, planned_date, note, status FROM viewing_plans "
                    "ORDER BY planned_date, movie_id"
                ).fetchall()
                exclusions = self.content_exclusions()
            return {
                "format": "movie-finder-personal-data",
                "version": 4,
                "exported_at": datetime.now().isoformat(timespec="seconds"),
                "movies": [
                    {"id": int(row["id"]), "watched": bool(row["watched"]),
                     "personal_rating": row["personal_rating"],
                     "bookmarked": bool(row["bookmarked"])}
                    for row in rows
                ],
                "saved_filters": [
                    {"name": str(row["name"]), "filters": json.loads(row["filters_json"])}
                    for row in filters
                ],
                "watchlist": [
                    {"id": int(row["movie_id"]), "priority": int(row["priority"]),
                     "note": str(row["note"])}
                    for row in watchlist
                ],
                "recommendation_feedback": [
                    {"id": int(row["movie_id"]), "feedback": str(row["feedback"])}
                    for row in feedback
                ],
                "plans": [
                    {"id": int(row["movie_id"]), "date": str(row["planned_date"]),
                     "note": str(row["note"]), "status": str(row["status"])}
                    for row in plans
                ],
                "content_exclusions": exclusions,
            }

        return self._call(action)

    def import_personal_data(self, payload: Any) -> dict[str, Any]:
        """Проверяет весь JSON до транзакции и атомарно применяет известные ID."""
        if not isinstance(payload, dict):
            raise ValueError("Некорректная структура файла персональных данных.")
        version = payload.get("version")
        expected_fields = (
            {"format", "version", "exported_at", "movies"}
            if version == 1
            else {"format", "version", "exported_at", "movies", "saved_filters"}
            if version == 2
            else {
                "format", "version", "exported_at", "movies", "saved_filters",
                "watchlist", "recommendation_feedback",
            }
            if version == 3
            else {
                "format", "version", "exported_at", "movies", "saved_filters",
                "watchlist", "recommendation_feedback", "plans", "content_exclusions",
            }
            if version == 4
            else set()
        )
        if set(payload) != expected_fields:
            raise ValueError("Некорректная структура файла персональных данных.")
        if (payload.get("format") != "movie-finder-personal-data"
                or type(version) is not int or version not in (1, 2, 3, 4)):
            raise ValueError("Неподдерживаемый формат или версия файла.")
        if not isinstance(payload.get("exported_at"), str) or not isinstance(payload.get("movies"), list):
            raise ValueError("Некорректные дата экспорта или список фильмов.")
        try:
            datetime.fromisoformat(payload["exported_at"])
        except ValueError as exc:
            raise ValueError("Дата экспорта должна быть в формате ISO 8601.") from exc

        validated: list[tuple[int, bool, int | None, bool]] = []
        seen: set[int] = set()
        for item in payload["movies"]:
            if not isinstance(item, dict) or set(item) != {
                "id", "watched", "personal_rating", "bookmarked"
            }:
                raise ValueError("Запись фильма имеет неподдерживаемые поля.")
            movie_id = item["id"]
            watched = item["watched"]
            rating = item["personal_rating"]
            bookmarked = item["bookmarked"]
            if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
                raise ValueError("ID фильма должен быть положительным целым числом.")
            if movie_id in seen:
                raise ValueError(f"В файле повторяется ID фильма {movie_id}.")
            if not isinstance(watched, bool) or not isinstance(bookmarked, bool):
                raise ValueError("Статус просмотра и закладки должны быть логическими.")
            if rating is not None and (
                isinstance(rating, bool) or not isinstance(rating, int) or not 1 <= rating <= 10
            ):
                raise ValueError("Личная оценка должна быть целым числом от 1 до 10 или null.")
            seen.add(movie_id)
            validated.append((movie_id, watched, rating, bookmarked))

        validated_watchlist: list[tuple[int, int, str]] = []
        validated_feedback: list[tuple[int, str]] = []
        if version in (3, 4):
            watchlist = payload["watchlist"]
            if not isinstance(watchlist, list):
                raise ValueError("Список «Хочу посмотреть» должен быть списком.")
            watchlist_ids: set[int] = set()
            for item in watchlist:
                if not isinstance(item, dict) or set(item) != {"id", "priority", "note"}:
                    raise ValueError("Запись списка «Хочу посмотреть» имеет неподдерживаемые поля.")
                movie_id, priority, note = item["id"], item["priority"], item["note"]
                if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
                    raise ValueError("ID фильма должен быть положительным целым числом.")
                if movie_id in watchlist_ids:
                    raise ValueError(f"В списке «Хочу посмотреть» повторяется ID фильма {movie_id}.")
                try:
                    priority, note = self._validate_watchlist_values(priority, note)
                except ValueError as exc:
                    raise ValueError(f"Некорректная запись списка: {exc}") from exc
                watchlist_ids.add(movie_id)
                seen.add(movie_id)
                validated_watchlist.append((movie_id, priority, note))

            feedback_rows = payload["recommendation_feedback"]
            if not isinstance(feedback_rows, list):
                raise ValueError("Отзывы к рекомендациям должны быть списком.")
            feedback_ids: set[int] = set()
            for item in feedback_rows:
                if not isinstance(item, dict) or set(item) != {"id", "feedback"}:
                    raise ValueError("Запись отзыва имеет неподдерживаемые поля.")
                movie_id, feedback = item["id"], item["feedback"]
                if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
                    raise ValueError("ID фильма должен быть положительным целым числом.")
                if movie_id in feedback_ids:
                    raise ValueError(f"В отзывах повторяется ID фильма {movie_id}.")
                if feedback not in ("like", "dislike"):
                    raise ValueError("Отзыв должен быть like или dislike.")
                feedback_ids.add(movie_id)
                seen.add(movie_id)
                validated_feedback.append((movie_id, feedback))

        validated_filters: list[tuple[str, str]] = []
        if version in (2, 3, 4):
            filters = payload["saved_filters"]
            if not isinstance(filters, list):
                raise ValueError("Подборки в файле должны быть списком.")
            filter_names: set[str] = set()
            for entry in filters:
                if not isinstance(entry, dict) or set(entry) != {"name", "filters"}:
                    raise ValueError("Запись подборки имеет неподдерживаемые поля.")
                name = entry["name"]
                filter_data = entry["filters"]
                if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
                    raise ValueError("Название подборки должно содержать от 1 до 80 символов.")
                clean_name = name.strip()
                if clean_name in filter_names:
                    raise ValueError(f"В файле повторяется подборка «{clean_name}».")
                if not isinstance(filter_data, dict) or set(filter_data) - PERSONAL_FILTER_KEYS:
                    raise ValueError("Подборка содержит неподдерживаемые параметры фильтра.")
                try:
                    serialized = json.dumps(
                        filter_data, ensure_ascii=False, sort_keys=True
                    )
                except (TypeError, ValueError) as exc:
                    raise ValueError("Параметры подборки не могут быть сохранены.") from exc
                filter_names.add(clean_name)
                validated_filters.append((clean_name, serialized))

        validated_plans: list[tuple[int, str, str, str]] = []
        validated_exclusions: dict[str, list[str]] = {"genre": [], "theme": []}
        if version == 4:
            if not isinstance(payload["plans"], list):
                raise ValueError("Планы просмотра должны быть списком.")
            plan_keys: set[tuple[int, str]] = set()
            for item in payload["plans"]:
                if not isinstance(item, dict) or set(item) != {"id", "date", "note", "status"}:
                    raise ValueError("Запись плана просмотра имеет неподдерживаемые поля.")
                movie_id, planned_date, note, status = (
                    item["id"], item["date"], item["note"], item["status"]
                )
                if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
                    raise ValueError("ID фильма в плане должен быть положительным целым числом.")
                planned_date, note = self._validate_plan_values(planned_date, note)
                if status not in ("planned", "completed"):
                    raise ValueError("Статус плана должен быть planned или completed.")
                key = (movie_id, planned_date)
                if key in plan_keys:
                    raise ValueError("В файле повторяется план фильма на ту же дату.")
                plan_keys.add(key)
                seen.add(movie_id)
                validated_plans.append((movie_id, planned_date, note, status))

            exclusions = payload["content_exclusions"]
            if not isinstance(exclusions, dict) or set(exclusions) != {"genre", "theme"}:
                raise ValueError("Некорректные исключения контента.")
            try:
                validated_exclusions = {
                    "genre": self._validate_exclusion_values(exclusions["genre"], kind="genre"),
                    "theme": self._validate_exclusion_values(exclusions["theme"], kind="theme"),
                }
            except ValueError as exc:
                raise ValueError(f"Некорректные исключения контента: {exc}") from exc

        def action() -> dict[str, Any]:
            with self._lock:
                try:
                    self._db.execute("BEGIN IMMEDIATE")
                    known = {
                        int(row[0])
                        for row in self._db.execute("SELECT id FROM movies").fetchall()
                    } & seen
                    imported = [row for row in validated if row[0] in known]
                    imported_watchlist = [
                        row for row in validated_watchlist if row[0] in known
                    ]
                    imported_feedback = [
                        row for row in validated_feedback if row[0] in known
                    ]
                    imported_plans = [
                        row for row in validated_plans if row[0] in known
                    ]
                    self._db.executemany(
                        "UPDATE movies SET watched = ?, personal_rating = ? WHERE id = ?",
                        [(int(watched), rating, movie_id)
                         for movie_id, watched, rating, _ in imported],
                    )
                    now = datetime.now().isoformat(timespec="seconds")
                    for movie_id, _, _, bookmarked in imported:
                        if bookmarked:
                            self._db.execute(
                                "INSERT INTO bookmarks (movie_id, added_at) VALUES (?, ?) "
                                "ON CONFLICT(movie_id) DO NOTHING",
                                (movie_id, now),
                            )
                        else:
                            self._db.execute(
                                "DELETE FROM bookmarks WHERE movie_id = ?", (movie_id,)
                            )
                    now = datetime.now().isoformat(timespec="seconds")
                    self._db.executemany(
                        "INSERT INTO watchlist (movie_id, priority, note, added_at, updated_at) "
                        "VALUES (?, ?, ?, ?, ?) ON CONFLICT(movie_id) DO UPDATE SET "
                        "priority = excluded.priority, note = excluded.note, "
                        "updated_at = excluded.updated_at "
                        "WHERE watchlist.priority <> excluded.priority "
                        "OR watchlist.note <> excluded.note",
                        [(movie_id, priority, note, now, now)
                         for movie_id, priority, note in validated_watchlist
                         if movie_id in known],
                    )
                    self._db.executemany(
                        "INSERT INTO recommendation_feedback (movie_id, feedback, updated_at) "
                        "VALUES (?, ?, ?) ON CONFLICT(movie_id) DO UPDATE SET "
                        "feedback = excluded.feedback, updated_at = excluded.updated_at "
                        "WHERE recommendation_feedback.feedback <> excluded.feedback",
                        [(movie_id, feedback, now)
                         for movie_id, feedback in validated_feedback
                         if movie_id in known],
                    )
                    now = datetime.now().isoformat(timespec="seconds")
                    self._db.executemany(
                        "INSERT INTO saved_filters (name, filters_json, updated_at) "
                        "VALUES (?, ?, ?) ON CONFLICT(name) DO UPDATE SET "
                        "filters_json = excluded.filters_json, "
                        "updated_at = excluded.updated_at",
                        [(name, filters_json, now) for name, filters_json in validated_filters],
                    )
                    if version == 4:
                        self._db.executemany(
                            "INSERT INTO viewing_plans "
                            "(movie_id, planned_date, note, status, created_at, updated_at) "
                            "VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(movie_id, planned_date) "
                            "DO UPDATE SET note=excluded.note, status=excluded.status, "
                            "updated_at=excluded.updated_at",
                            [
                                (movie_id, planned_date, note, status, now, now)
                                for movie_id, planned_date, note, status in imported_plans
                            ],
                        )
                        self._db.executemany(
                            "UPDATE movies SET watched=1 WHERE id=?",
                            [(movie_id,) for movie_id, _, _, status in imported_plans
                             if status == "completed"],
                        )
                        self._db.execute("DELETE FROM content_exclusions")
                        for kind in ("genre", "theme"):
                            self._db.executemany(
                                "INSERT INTO content_exclusions(kind, value) VALUES (?, ?)",
                                [(kind, value) for value in validated_exclusions[kind]],
                            )
                    self._db.commit()
                except Exception:
                    self._db.rollback()
                    raise
            return {
                "imported": len(imported),
                "unknown_ids": sorted(seen - known),
                **(
                    {
                        "watchlist_imported": len(imported_watchlist),
                        "feedback_imported": len(imported_feedback),
                    }
                    if version in (3, 4)
                    else {}
                ),
                **(
                    {
                        "plans_imported": len(imported_plans),
                        "content_exclusions_imported": sum(
                            len(values) for values in validated_exclusions.values()
                        ),
                    }
                    if version == 4
                    else {}
                ),
            }

        return self._call(action, attempts=1)

    @staticmethod
    def _validate_exclusion_values(values: Any, *, kind: str) -> list[str]:
        if not isinstance(values, list):
            raise ValueError("Список исключений должен быть массивом.")
        if kind == "theme":
            from .const import CATEGORY_FILTERS
            allowed = set(CATEGORY_FILTERS) - {
                "uplifting", "light", "tense", "romantic", "thoughtful", "family_night",
            }
        else:
            allowed = None
        result = []
        for value in values:
            if not isinstance(value, str) or not value.strip() or len(value) > 100:
                raise ValueError("Значение исключения должно быть непустой строкой до 100 символов.")
            clean_value = value.strip().casefold()
            if allowed is not None and clean_value not in allowed:
                raise ValueError("Неизвестный тематический фильтр.")
            if clean_value in result:
                raise ValueError("Значения исключений не должны повторяться.")
            result.append(clean_value)
        return result

    def record_view(self, movie_id: int) -> None:
        def action() -> None:
            with self._lock:
                self._db.execute(
                    "INSERT INTO history (movie_id, viewed_at) VALUES (?, ?) "
                    "ON CONFLICT(movie_id) DO UPDATE SET viewed_at = excluded.viewed_at",
                    (movie_id, datetime.now().isoformat(timespec="seconds")),
                )
                self._db.commit()

        self._call(action)

    def set_personal_state(
        self, movie_id: int, *, watched: bool, personal_rating: int | None
    ) -> None:
        """Сохраняет персональный статус и оценку фильма от 1 до 10."""
        if not isinstance(watched, bool):
            raise ValueError("Статус просмотра должен быть логическим значением.")
        if personal_rating is not None and (
            isinstance(personal_rating, bool)
            or not isinstance(personal_rating, int)
            or not 1 <= personal_rating <= 10
        ):
            raise ValueError("Личная оценка должна быть целым числом от 1 до 10.")

        def action() -> None:
            with self._lock:
                cursor = self._db.execute(
                    "UPDATE movies SET watched = ?, personal_rating = ? WHERE id = ?",
                    (int(watched), personal_rating, int(movie_id)),
                )
                if cursor.rowcount == 0:
                    raise ValueError(f"Фильм с id={movie_id} не найден.")
                self._db.commit()

        self._call(action)

    def recent_views(self, limit: int = 20) -> list[dict[str, Any]]:
        def action() -> list[dict[str, Any]]:
            with self._lock:
                rows = self._db.execute(
                    "SELECT m.* FROM history AS h JOIN movies AS m ON m.id = h.movie_id "
                    "ORDER BY h.viewed_at DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            return [dict(r) for r in rows]

        return self._call(action)

    def recommendations(self, limit: int = 60) -> list[dict[str, Any]]:
        """Ranks unseen, unrated movies from positive and negative personal feedback."""
        def action() -> list[dict[str, Any]]:
            with self._lock:
                profile = self._db.execute(
                    "SELECT m.id, m.genres, m.personal_rating, m.watched, m.runtime, "
                    "f.feedback FROM movies AS m LEFT JOIN recommendation_feedback AS f "
                    "ON f.movie_id = m.id WHERE m.watched = 1 OR m.personal_rating IS NOT NULL "
                    "OR f.feedback IS NOT NULL"
                ).fetchall()
                if not profile:
                    return []
                profile_ids = [int(row["id"]) for row in profile]
                genre_scores: dict[str, float] = {}
                movie_weights: dict[int, float] = {}
                preferred_runtime: list[tuple[float, int]] = []
                for row in profile:
                    rating = row["personal_rating"]
                    weight = (
                        (float(rating) - 5.0) / 5.0
                        if rating is not None
                        else (0.25 if row["watched"] else 0.0)
                    )
                    if row["feedback"] == "like":
                        weight += 0.75
                    elif row["feedback"] == "dislike":
                        weight -= 0.75
                    weight = max(-1.0, min(1.0, weight))
                    movie_weights[int(row["id"])] = weight
                    if weight > 0 and row["runtime"]:
                        preferred_runtime.append((weight, int(row["runtime"])))
                    for genre_name in (row["genres"] or "").split(","):
                        if genre_name:
                            genre_scores[genre_name] = genre_scores.get(genre_name, 0.0) + weight
                exclusion_sql, exclusion_args = self._content_exclusion_conditions()
                rows = self._db.execute(
                    "SELECT * FROM movies WHERE COALESCE(watched, 0) = 0 "
                    "AND personal_rating IS NULL "
                    "AND NOT EXISTS (SELECT 1 FROM recommendation_feedback f "
                    "WHERE f.movie_id = movies.id) "
                    "AND NOT EXISTS (SELECT 1 FROM watchlist w "
                    "WHERE w.movie_id = movies.id) "
                    + (
                        "AND NOT (" + exclusion_sql + ") "
                        if exclusion_sql else ""
                    )
                    + "ORDER BY COALESCE(rating, 0) DESC, COALESCE(votes, 0) DESC"
                , exclusion_args).fetchall()

                keyword_scores: dict[str, float] = {}
                cast_scores: dict[str, float] = {}
                for offset in range(0, len(profile_ids), 500):
                    ids = profile_ids[offset:offset + 500]
                    placeholders = ",".join("?" for _ in ids)
                    for movie_id, keyword in self._db.execute(
                        f"SELECT movie_id, keyword FROM movie_keywords "
                        f"WHERE movie_id IN ({placeholders})",
                        ids,
                    ):
                        keyword_scores[keyword] = keyword_scores.get(keyword, 0.0) + movie_weights[int(movie_id)]
                    for movie_id, name in self._db.execute(
                        f"SELECT movie_id, name FROM movie_cast "
                        f"WHERE movie_id IN ({placeholders})",
                        ids,
                    ):
                        cast_scores[name] = cast_scores.get(name, 0.0) + movie_weights[int(movie_id)]

                relevant_keywords = sorted(
                    (term for term, weight in keyword_scores.items() if weight != 0),
                    key=lambda term: (-abs(keyword_scores[term]), term),
                )[:500]
                relevant_cast = sorted(
                    (term for term, weight in cast_scores.items() if weight != 0),
                    key=lambda term: (-abs(cast_scores[term]), term),
                )[:500]
                matched_keywords: dict[int, set[str]] = {}
                matched_cast: dict[int, set[str]] = {}
                for terms, table, column, destination in (
                    (relevant_keywords, "movie_keywords", "keyword", matched_keywords),
                    (relevant_cast, "movie_cast", "name", matched_cast),
                ):
                    for offset in range(0, len(terms), 300):
                        batch = terms[offset:offset + 300]
                        if not batch:
                            continue
                        placeholders = ",".join("?" for _ in batch)
                        for movie_id, term in self._db.execute(
                            f"SELECT movie_id, {column} FROM {table} "
                            f"WHERE {column} IN ({placeholders})",
                            batch,
                        ):
                            destination.setdefault(int(movie_id), set()).add(term)

            runtime_preference = None
            if preferred_runtime:
                runtime_preference = sum(
                    weight * runtime for weight, runtime in preferred_runtime
                ) / sum(weight for weight, _ in preferred_runtime)
            has_positive_profile = any(weight > 0 for weight in movie_weights.values())
            has_negative_profile = any(weight < 0 for weight in movie_weights.values())

            candidates = []
            for row in rows:
                movie = dict(row)
                genres = {value for value in (movie.get("genres") or "").split(",") if value}
                keywords = matched_keywords.get(int(movie["id"]), set())
                cast = matched_cast.get(int(movie["id"]), set())
                genre_match = {value for value in genres if genre_scores.get(value, 0) > 0}
                keyword_match = {value for value in keywords if keyword_scores.get(value, 0) > 0}
                cast_match = {value for value in cast if cast_scores.get(value, 0) > 0}
                score = (
                    sum(genre_scores.get(value, 0.0) for value in genres)
                    + 0.8 * sum(keyword_scores.get(value, 0.0) for value in keywords)
                    + 0.8 * sum(cast_scores.get(value, 0.0) for value in cast)
                )
                if not has_positive_profile and has_negative_profile:
                    score += 1.0
                runtime_close = (
                    runtime_preference is not None
                    and movie.get("runtime") is not None
                    and abs(int(movie["runtime"]) - runtime_preference) <= 20
                )
                if runtime_close:
                    score += 0.25
                if score > 0:
                    reasons = [
                        {"type": "genre", "value": value}
                        for value in sorted(genre_match, key=lambda value: -genre_scores[value])
                    ]
                    reasons.extend(
                        {"type": "keyword", "value": value}
                        for value in sorted(keyword_match, key=lambda value: -keyword_scores[value])
                    )
                    reasons.extend(
                        {"type": "actor", "value": value}
                        for value in sorted(cast_match, key=lambda value: -cast_scores[value])
                    )
                    if runtime_close:
                        reasons.append({
                            "type": "runtime",
                            "value": int(runtime_preference or 0),
                        })
                    movie["recommendation_score"] = round(score, 4)
                    movie["recommendation_reasons"] = reasons[:4]
                    candidates.append(movie)
            candidates.sort(
                key=lambda movie: (
                    -movie["recommendation_score"],
                    -float(movie.get("rating") or 0),
                    -int(movie.get("votes") or 0),
                    int(movie["id"]),
                )
            )
            return candidates[:max(0, int(limit))]

        return self._call(action)

    def collection_queue(self, filters: dict[str, Any], *, page_size: int = 250) -> list[dict[str, Any]]:
        """Returns all unwatched films matching the supplied filters in search order."""
        if isinstance(page_size, bool) or not isinstance(page_size, int) or page_size < 1:
            raise ValueError("Размер страницы должен быть положительным целым числом.")
        queue: list[dict[str, Any]] = []
        offset = 0
        active_filters = dict(filters)
        active_filters["hide_watched"] = True
        while True:
            rows, total = self.search(
                **active_filters, limit=page_size, offset=offset
            )
            queue.extend(rows)
            offset += len(rows)
            if not rows or offset >= total:
                return queue

    def random_movie(
        self,
        filters: dict[str, Any] | None = None,
        *,
        max_runtime: int | None = None,
    ) -> dict[str, Any] | None:
        """Выбирает случайный непросмотренный фильм с учётом фильтров и лимита runtime."""
        supported = dict(filters or {})
        supported.pop("hide_watched", None)
        supported.pop("sort", None)
        filter_runtime = supported.pop("max_runtime", None)
        if max_runtime is None:
            max_runtime = filter_runtime
        rows, _ = self.search(
            **supported,
            max_runtime=max_runtime,
            hide_watched=True,
            exclude_personal_content=True,
            sort="random",
            limit=1,
        )
        return rows[0] if rows else None

    def set_file_paths(self, pairs: list[tuple[str, int]]) -> int:
        """Запоминает локальные файлы фильмов: [(путь, id)]."""

        def action() -> int:
            with self._lock:
                cursor = self._db.executemany(
                    "UPDATE movies SET file_path = ? WHERE id = ?", pairs
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def fill_directors(self, pairs: list[tuple[str, int]]) -> int:
        """Дописывает режиссёра там, где его ещё нет (импорт credits.csv)."""

        def action() -> int:
            with self._lock:
                cursor = self._db.executemany(
                    "UPDATE movies SET director = ? "
                    "WHERE id = ? AND COALESCE(director, '') = ''",
                    pairs,
                )
                self._db.commit()
                return int(cursor.rowcount or 0)

        return self._call(action)

    def search(
        self,
        *,
        title: str | None = None,
        credit: str | None = None,
        genre: str | None = None,
        category: str | None = None,
        mood: str | None = None,
        country: str | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        min_rating: float | None = None,
        min_votes: int | None = None,
        min_runtime: int | None = None,
        max_runtime: int | None = None,
        bookmarked_only: bool = False,
        hide_watched: bool = False,
        exclude_personal_content: bool = False,
        sort: str = "rating",
        limit: int = 60,
        offset: int = 0,
    ) -> tuple[list[dict[str, Any]], int]:
        """Возвращает (страница результатов, всего найдено)."""
        conds: list[str] = []
        args: list[Any] = []
        title_condition = ""

        if title and title.strip():
            title_condition = "title_lower LIKE ? ESCAPE '\\'"
            conds.append(title_condition)
            args.append(f"%{escape_like(title.strip().lower())}%")
        if credit and credit.strip():
            # Ищем и по актёрам (таблица movie_cast), и по режиссёру.
            pattern = f"%{escape_like(credit.strip())}%"
            conds.append(
                "(director LIKE ? ESCAPE '\\' OR EXISTS ("
                "SELECT 1 FROM movie_cast AS c "
                "WHERE c.movie_id = movies.id AND c.name LIKE ? ESCAPE '\\'))"
            )
            args.extend([pattern, pattern])
        if genre:
            conds.append("genres LIKE ?")
            args.append(f"%,{genre.strip().lower()},%")
        def append_category_filter(category_name: str | None) -> None:
            if not category_name:
                return
            from .const import CATEGORY_FILTERS

            definition = CATEGORY_FILTERS.get(category_name)
            if definition:
                category_conds: list[str] = []
                for category_genre in definition["genres"]:
                    category_conds.append("genres LIKE ?")
                    args.append(f"%,{category_genre},%")
                for term in definition["terms"]:
                    variants = {term.casefold()}
                    if any(ord(char) > 127 for char in term):
                        variants.add(term[:1].upper() + term[1:])
                        variants.add(term.upper())
                    for variant in variants:
                        pattern = f"%{variant}%"
                        category_conds.append(
                            "(LOWER(COALESCE(title, '') || ' ' || COALESCE(original_title, '') "
                            "|| ' ' || COALESCE(overview, '') || ' ' || COALESCE(overview_en, '')) LIKE ? "
                            "OR EXISTS (SELECT 1 FROM movie_keywords AS k "
                            "WHERE k.movie_id = movies.id AND LOWER(k.keyword) LIKE ?))"
                        )
                        args.extend([pattern, pattern])
                if category_conds:
                    conds.append("(" + " OR ".join(category_conds) + ")")
        append_category_filter(category)
        append_category_filter(mood)
        if country:
            conds.append("countries LIKE ?")
            args.append(f"%,{country.strip().upper()},%")
        if year_from:
            conds.append("COALESCE(year, 0) >= ?")
            args.append(int(year_from))
        if year_to:
            conds.append("COALESCE(year, 0) <= ?")
            args.append(int(year_to))
        if min_rating:
            conds.append("COALESCE(rating, 0) >= ?")
            args.append(float(min_rating))
        if min_votes:
            conds.append("COALESCE(votes, 0) >= ?")
            args.append(int(min_votes))
        for runtime_bound, label in (
            (min_runtime, "Минимальная"),
            (max_runtime, "Максимальная"),
        ):
            if runtime_bound is not None and (
                isinstance(runtime_bound, bool)
                or not isinstance(runtime_bound, int)
                or runtime_bound <= 0
            ):
                raise ValueError(f"{label} длительность должна быть положительным целым числом.")
        if min_runtime is not None and max_runtime is not None and min_runtime > max_runtime:
            raise ValueError("Минимальная длительность не может превышать максимальную.")
        if min_runtime is not None or max_runtime is not None:
            conds.append("runtime IS NOT NULL AND runtime > 0")
            if min_runtime is not None:
                conds.append("runtime >= ?")
                args.append(min_runtime)
            if max_runtime is not None:
                conds.append("runtime <= ?")
                args.append(max_runtime)
        if bookmarked_only:
            conds.append(
                "EXISTS (SELECT 1 FROM bookmarks AS b WHERE b.movie_id = movies.id)"
            )
        if hide_watched:
            conds.append("COALESCE(watched, 0) = 0")
        if exclude_personal_content:
            exclusion_sql, exclusion_args = self._content_exclusion_conditions()
            if exclusion_sql:
                conds.append("NOT (" + exclusion_sql + ")")
                args.extend(exclusion_args)

        where = " AND ".join(conds) if conds else "1=1"
        order = SORTS.get(sort, SORTS["rating"])

        def action():
            with self._lock:
                total = int(
                    self._db.execute(
                        f"SELECT COUNT(*) FROM movies WHERE {where}", args
                    ).fetchone()[0]
                )
                rows = self._db.execute(
                    f"SELECT movies.*, EXISTS (SELECT 1 FROM watchlist w "
                    f"WHERE w.movie_id = movies.id) AS watchlisted "
                    f"FROM movies WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                    args + [int(limit), int(offset)],
                ).fetchall()
            if total or not title:
                return [dict(r) for r in rows], total

            fuzzy_ids = self._fuzzy_title_ids(title)
            if not fuzzy_ids:
                return [], 0
            # Убираем условие по названию вместе с его аргументом: опечатки
            # ищутся по индексу, остальные фильтры остаются как есть.
            base_conds = [c for c in conds if c != title_condition]
            base_args = list(args[1:]) if title_condition else list(args)
            fuzzy_conds = [*base_conds, "id IN (" + ",".join("?" for _ in fuzzy_ids) + ")"]
            fuzzy_where = " AND ".join(fuzzy_conds) if fuzzy_conds else "1=1"
            fuzzy_args = base_args + fuzzy_ids
            with self._lock:
                fuzzy_total = int(
                    self._db.execute(
                        f"SELECT COUNT(*) FROM movies WHERE {fuzzy_where}", fuzzy_args
                    ).fetchone()[0]
                )
                fuzzy_rows = self._db.execute(
                    f"SELECT movies.*, EXISTS (SELECT 1 FROM watchlist w "
                    f"WHERE w.movie_id = movies.id) AS watchlisted "
                    f"FROM movies WHERE {fuzzy_where} ORDER BY {order} LIMIT ? OFFSET ?",
                    fuzzy_args + [int(limit), int(offset)],
                ).fetchall()
            return [dict(row) for row in fuzzy_rows], fuzzy_total

        return self._call(action)

    # ------------------------------------------------------------------ meta
    def set_meta(self, key: str, value: str) -> None:
        def action() -> None:
            with self._lock:
                self._db.execute(
                    "INSERT INTO meta (key, value) VALUES (?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                    (key, str(value)),
                )
                self._db.commit()

        self._call(action)

    def get_meta(self, key: str) -> str | None:
        def action():
            with self._lock:
                return self._db.execute(
                    "SELECT value FROM meta WHERE key = ?", (key,)
                ).fetchone()

        row = self._call(action)
        return str(row[0]) if row else None

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._db.close()
                self._conn = None

    # ------------------------------------------------------------- утилиты
    def genre_counts(self) -> list[tuple[str, int]]:
        """Сколько фильмов в базе по каждому жанру — для подсказок в интерфейсе."""
        result: dict[str, int] = {}
        with self._lock:
            rows = self._db.execute("SELECT genres FROM movies").fetchall()
        for (value,) in rows:
            for code in (value or "").split(","):
                if code:
                    result[code] = result.get(code, 0) + 1
        return sorted(result.items(), key=lambda kv: -kv[1])

    def country_counts(self) -> list[tuple[str, int]]:
        result: dict[str, int] = {}
        with self._lock:
            rows = self._db.execute("SELECT countries FROM movies").fetchall()
        for (value,) in rows:
            for code in (value or "").split(","):
                if code:
                    result[code] = result.get(code, 0) + 1
        return sorted(result.items(), key=lambda kv: -kv[1])
