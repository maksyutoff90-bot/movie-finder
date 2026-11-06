"""Кнопка «Обновить новинки»: свежие релизы, а не повторный топ по голосам.

Проверяет, что режим новинок:
  * запрашивает discover по дате выхода в заданном окне;
  * добавляет отсутствующие фильмы и пропускает уже известные с деталями;
  * отбрасывает телефильмы;
  * не трогает полную синхронизацию по годам.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.database import MovieDB  # noqa: E402
from movie_search.tmdb_sync import SyncJob  # noqa: E402


class FakeClient:
    """Минимальная заглушка TMDb: одна страница новинок и детали по запросу."""

    def __init__(self, *_args, **_kwargs) -> None:
        self.recent_calls: list[tuple[int, int, int]] = []
        self.year_calls: list[tuple] = []

    def check_key(self) -> None:
        pass

    def discover_recent(self, *, days: int, page: int, min_votes: int) -> dict:
        self.recent_calls.append((days, page, min_votes))
        if page > 1:
            return {"page": page, "total_pages": 1, "results": []}
        return {
            "page": 1,
            "total_pages": 1,
            "results": [
                {"id": 900001, "title": "Новый фильм", "release_date": "2026-11-01",
                 "genre_ids": [18]},
                {"id": 603, "title": "Матрица", "release_date": "1999-03-31",
                 "genre_ids": [28]},
                {"id": 900002, "title": "Телефильм", "release_date": "2026-11-02",
                 "genre_ids": [10770]},
            ],
        }

    def discover_year(self, *args, **kwargs) -> dict:
        self.year_calls.append((args, kwargs))
        return {"page": 1, "total_pages": 1, "results": []}

    def movie_details(self, movie_id: int) -> dict:
        return {
            "id": movie_id,
            "title": f"Фильм {movie_id}",
            "release_date": "2026-11-01",
            "overview": "Описание из TMDb.",
            "vote_average": 7.5,
            "vote_count": 120,
            "genres": [{"id": 18}],
            "production_countries": [{"iso_3166_1": "RU"}],
            "runtime": 100,
            "poster_path": "/x.jpg",
            "imdb_id": "tt0000001",
            "credits": {"crew": []},
        }


class RecentSyncTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "recent.db")
        # Матрица уже есть с деталями — её не должно перекачивать.
        self.db.upsert_many([{
            "id": 603,
            "title": "Матрица",
            "year": 1999,
            "countries": ["US"],
            "overview": "Хакер узнаёт правду о мире.",
        }])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_recent_mode_uses_date_window_and_adds_new_films(self) -> None:
        client = FakeClient()
        with patch("movie_search.tmdb_sync.TMDBClient", return_value=client):
            job = SyncJob(self.db, "test-key", recent_days=30, min_votes=40)
            job._sync()

        self.assertEqual(client.recent_calls, [(30, 1, 40)])
        self.assertEqual(client.year_calls, [])

        # Новый фильм добавлен с деталями, телефильм и дубль не попали.
        self.assertEqual(self.db.count(), 2)
        added = self.db.get(900001)
        self.assertIsNotNone(added)
        self.assertEqual(added["countries"], ",RU,")
        self.assertIsNotNone(self.db.get(603))
        self.assertIsNone(self.db.get(900002))

        messages = []
        while not job.queue.empty():
            messages.append(job.queue.get_nowait())
        done = [m for m in messages if m[0] == "done"]
        self.assertEqual(done, [("done", 1)])

    def test_full_sync_still_uses_years(self) -> None:
        client = FakeClient()
        with patch("movie_search.tmdb_sync.TMDBClient", return_value=client):
            job = SyncJob(self.db, "test-key", years=[2020], pages=1)
            job._sync()

        self.assertEqual(client.recent_calls, [])
        self.assertEqual(len(client.year_calls), 1)


if __name__ == "__main__":
    unittest.main()
