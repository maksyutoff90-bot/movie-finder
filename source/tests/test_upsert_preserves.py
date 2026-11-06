"""Регрессии P0: повторная запись не стирает локальные данные фильма.

Покрывают:
  * upsert не затирает постер, путь к файлу и описание пустыми значениями;
  * реальные значения по-прежнему обновляются;
  * импорт IMDb/MovieLens не заводит дубль фильма, найденного по imdb_id;
  * индекс опечаток строится по требованию и переиспользуется;
  * добавление в список «Хочу посмотреть» не сбрасывает приоритет и заметку.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import import_dataset  # noqa: E402

from movie_search.database import SCHEMA, MovieDB  # noqa: E402


class UpsertKeepsLocalDataTests(unittest.TestCase):
    """Повторный upsert не должен обнулять поля, которых нет во входных данных."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "keep.db")
        self.db.upsert_many([
            {
                "id": 603,
                "title": "Матрица",
                "original_title": "The Matrix",
                "year": 1999,
                "overview": "Хакер узнаёт правду о мире.",
                "tagline": "Добро пожаловать в реальный мир",
                "rating": 8.2,
                "votes": 24000,
                "runtime": 136,
                "genres": ["фантастика", "боевик"],
                "countries": ["US"],
                "director": "Лана Вачовски",
                "poster_path": "/matrix.jpg",
                "poster_file": "tmdb_603.jpg",
                "poster_url": "https://image.tmdb.org/t/p/w500/matrix.jpg",
                "source": "tmdb",
                "imdb_id": "tt0133093",
            }
        ])
        self.db.set_file_paths([(r"D:\Movies\Матрица.1999.mkv", 603)])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_partial_upsert_keeps_poster_and_local_path(self) -> None:
        # Ровно то, что присылает повторная синхронизация деталей TMDb.
        self.db.upsert_many([
            {"id": 603, "title": "Матрица", "year": 1999, "source": "tmdb"}
        ])
        row = self.db.get(603)
        self.assertEqual(row["poster_file"], "tmdb_603.jpg")
        self.assertEqual(
            row["poster_url"], "https://image.tmdb.org/t/p/w500/matrix.jpg"
        )
        self.assertEqual(row["file_path"], r"D:\Movies\Матрица.1999.mkv")

    def test_partial_upsert_keeps_description_and_imdb_id(self) -> None:
        self.db.upsert_many([
            {
                "id": 603,
                "title": "Матрица",
                "overview": None,
                "tagline": "",
                "imdb_id": "",
                "director": None,
            }
        ])
        row = self.db.get(603)
        self.assertEqual(row["overview"], "Хакер узнаёт правду о мире.")
        self.assertEqual(row["tagline"], "Добро пожаловать в реальный мир")
        self.assertEqual(row["imdb_id"], "tt0133093")
        self.assertEqual(row["director"], "Лана Вачовски")

    def test_partial_upsert_keeps_rating_votes_runtime_and_genres(self) -> None:
        # IMDb/MovieLens присылают пустые жанры, страны и нулевые числа.
        self.db.upsert_many([
            {
                "id": 603,
                "title": "Матрица",
                "rating": None,
                "votes": 0,
                "runtime": 0,
                "genres": "",
                "countries": "",
            }
        ])
        row = self.db.get(603)
        self.assertEqual(row["rating"], 8.2)
        self.assertEqual(row["votes"], 24000)
        self.assertEqual(row["runtime"], 136)
        self.assertEqual(row["genres"], ",фантастика,боевик,")
        self.assertEqual(row["countries"], ",US,")

    def test_real_values_still_replace_old_ones(self) -> None:
        self.db.upsert_many([
            {
                "id": 603,
                "title": "Матрица",
                "overview": "Уточнённое описание.",
                "rating": 7.9,
                "votes": 25000,
                "runtime": 137,
                "poster_path": "/matrix-2026.jpg",
            }
        ])
        row = self.db.get(603)
        self.assertEqual(row["overview"], "Уточнённое описание.")
        self.assertEqual(row["rating"], 7.9)
        self.assertEqual(row["votes"], 25000)
        self.assertEqual(row["runtime"], 137)
        self.assertEqual(row["poster_path"], "/matrix-2026.jpg")


class ImporterDedupTests(unittest.TestCase):
    """Фильм с уже известным imdb_id не заводится вторым id."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "dedupe.db")
        self.db.upsert_many([
            {
                "id": 603,
                "title": "Матрица",
                "year": 1999,
                "overview": "Хакер узнаёт правду о мире.",
                "imdb_id": "tt0133093",
                "source": "tmdb",
            }
        ])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_existing_imdb_id_is_skipped_even_with_overwrite(self) -> None:
        importer = import_dataset.Importer(self.db, skip_existing=False)
        imdb_id = int("0133093")
        importer.push({
            "id": -(imdb_id + 10_000_000),  # отрицательный id IMDb-записи
            "title": "The Matrix",
            "year": 1999,
            "overview": None,
            "imdb_id": "tt0133093",
        })
        importer.flush()

        self.assertEqual(self.db.count(), 1)
        self.assertEqual(importer.skipped, 1)
        self.assertEqual(self.db.get(603)["overview"], "Хакер узнаёт правду о мире.")

    def test_new_imdb_id_is_imported(self) -> None:
        importer = import_dataset.Importer(self.db, skip_existing=False)
        importer.push({
            "id": -10_000_777,
            "title": "Новый фильм",
            "year": 2024,
            "imdb_id": "tt0000777",
        })
        importer.flush()

        self.assertEqual(self.db.count(), 2)
        self.assertEqual(importer.added, 1)


class DeferredIndexTests(unittest.TestCase):
    """Индекс опечаток строится по требованию, а не при открытии базы."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "index.db"
        # Готовим каталог «снаружи» — как база, скачанная без индекса.
        conn = sqlite3.connect(str(self.path))
        conn.executescript(SCHEMA)
        conn.executemany(
            "INSERT INTO movies (id, title, title_lower, year) VALUES (?, ?, ?, ?)",
            [
                (1, "Путешествие", "путешествие spirited away", 2001),
                (2, "Avatar", "avatar", 2009),
            ],
        )
        conn.commit()
        conn.close()
        self.db = MovieDB(self.path, defer_index=True)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_index_is_not_built_until_requested(self) -> None:
        rows, total = self.db.search(title="Путшествие")  # опечатка
        self.assertEqual((rows, total), ([], 0))

        self.assertTrue(self.db.ensure_title_gram_index())
        rows, total = self.db.search(title="Путшествие")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["id"], 1)

    def test_second_call_reuses_index(self) -> None:
        self.assertTrue(self.db.ensure_title_gram_index())
        self.assertFalse(self.db.ensure_title_gram_index())


class WatchlistPreserveTests(unittest.TestCase):
    """«＋ Хочу посмотреть» не сбрасывает уже выставленные приоритет и заметку."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "watchlist.db")
        self.db.upsert_many([{"id": 1, "title": "Первый"}, {"id": 2, "title": "Второй"}])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_repeat_add_keeps_priority_and_note(self) -> None:
        self.db.set_watchlist(1, priority=5, note="посмотреть в выходные")
        self.assertFalse(self.db.add_to_watchlist(1, priority=3, note=""))

        entry = self.db.watchlist_entry(1)
        self.assertEqual(entry["priority"], 5)
        self.assertEqual(entry["note"], "посмотреть в выходные")

    def test_new_add_uses_defaults(self) -> None:
        self.assertTrue(self.db.add_to_watchlist(2))
        self.assertEqual(self.db.watchlist_entry(2)["priority"], 3)


if __name__ == "__main__":
    unittest.main()
