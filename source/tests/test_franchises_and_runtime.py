"""Tests for franchise ordering, sequel monitoring, and runtime filtering."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.database import MovieDB  # noqa: E402
from movie_search.franchises import check_watchlist_sequels, franchise_order  # noqa: E402
from movie_search.tmdb_sync import TMDB_BASE, TMDBClient  # noqa: E402


class FakeTMDB:
    def __init__(
        self,
        _api_key: str,
        _language: str,
        *,
        collections: dict[int, dict],
        movie_collections: dict[int, int | None],
    ) -> None:
        self.collections = collections
        self.movie_collections = movie_collections

    def movie_details(self, movie_id: int) -> dict:
        collection_id = self.movie_collections.get(movie_id)
        collection = {"id": collection_id} if collection_id else None
        return {"belongs_to_collection": collection}

    def collection_details(self, collection_id: int) -> dict:
        return self.collections.get(collection_id, {})


class FranchiseAndSequelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "movies.db")
        self.db.upsert_many([
            {"id": 10, "title": "Franchise One", "year": 2000},
            {"id": 11, "title": "Franchise Two", "year": 2004},
        ])
        self.db.set_personal_state(10, watched=True, personal_rating=8)
        self.db.set_watchlist(10)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_franchise_order_uses_release_dates_and_local_watched_state(self) -> None:
        client = FakeTMDB(
            "unused",
            "ru-RU",
            collections={
                7: {
                    "name": "Verified collection",
                    "parts": [
                        {"id": 12, "title": "Third", "release_date": "2010-01-01"},
                        {"id": 10, "title": "First", "release_date": "2000-01-01"},
                        {"id": 11, "title": "Second", "release_date": "2004-01-01"},
                        {"id": 13, "title": "No date"},
                    ],
                }
            },
            movie_collections={10: 7},
        )

        result = franchise_order(self.db, client, 10)

        self.assertEqual(result["source"], "TMDb")
        self.assertEqual([part["id"] for part in result["parts"]], [10, 11, 12, 13])
        self.assertTrue(result["parts"][0]["watched"])
        self.assertTrue(result["parts"][0]["in_catalog"])
        self.assertFalse(result["parts"][1]["watched"])
        self.assertFalse(result["parts"][2]["in_catalog"])
        self.assertIsNone(result["parts"][-1]["year"])

    def test_sequel_baseline_then_new_part_is_saved_once(self) -> None:
        collections = {
            7: {
                "parts": [
                    {"id": 10, "title": "First", "release_date": "2000-01-01"},
                    {"id": 11, "title": "Second", "release_date": "2004-01-01"},
                ]
            }
        }

        def client_factory(key: str, language: str) -> FakeTMDB:
            return FakeTMDB(
                key, language, collections=collections, movie_collections={10: 7}
            )

        baseline = check_watchlist_sequels(
            self.db, "configured", client_factory=client_factory
        )
        self.assertEqual(baseline["status"], "checked")
        self.assertEqual(baseline["new_notifications"], 0)
        self.assertEqual(self.db.sequel_notification_count(), 0)

        collections[7]["parts"].append({
            "id": 12, "title": "New sequel", "release_date": "2027-06-01"
        })
        changed = check_watchlist_sequels(
            self.db, "configured", client_factory=client_factory
        )
        repeated = check_watchlist_sequels(
            self.db, "configured", client_factory=client_factory
        )

        self.assertEqual(changed["new_notifications"], 1)
        self.assertEqual(repeated["new_notifications"], 0)
        self.assertEqual(len(self.db.sequel_notifications()), 1)
        self.assertEqual(self.db.sequel_notifications()[0]["title"], "New sequel")
        self.assertEqual(self.db.sequel_notifications()[0]["year"], 2027)
        self.assertEqual(self.db.mark_sequel_notifications_read(), 1)
        self.assertEqual(self.db.sequel_notification_count(), 0)

    def test_missing_collection_is_reported_as_unverified(self) -> None:
        result = check_watchlist_sequels(
            self.db,
            "configured",
            client_factory=lambda key, language: FakeTMDB(
                key, language, collections={}, movie_collections={10: None}
            ),
        )

        self.assertEqual(result["checked"], 1)
        self.assertEqual(result["unverified"], 1)
        self.assertEqual(self.db.sequel_notifications(), [])

    def test_missing_key_gates_client_construction_for_startup_or_manual_check(self) -> None:
        constructed: list[bool] = []

        def client_factory(_key: str, _language: str) -> FakeTMDB:
            constructed.append(True)
            raise AssertionError("TMDb client must not be constructed without a key")

        result = check_watchlist_sequels(
            self.db, "", client_factory=client_factory
        )

        self.assertEqual(result["status"], "no_api_key")
        self.assertEqual(result["checked"], 0)
        self.assertEqual(constructed, [])

    def test_collection_details_uses_mocked_tmdb_http_endpoint(self) -> None:
        client = TMDBClient("test-key", "ru-RU")
        response = Mock(status_code=200, ok=True)
        response.json.return_value = {"id": 7, "parts": []}
        session = Mock()
        session.get.return_value = response

        with patch.object(client, "_session", return_value=session):
            payload = client.collection_details(7)

        self.assertEqual(payload, {"id": 7, "parts": []})
        args, kwargs = session.get.call_args
        self.assertEqual(args[0], f"{TMDB_BASE}/collection/7")
        self.assertEqual(kwargs["params"]["language"], "ru-RU")
        self.assertEqual(kwargs["params"]["api_key"], "test-key")


class RuntimeFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "runtime.db")
        self.db.upsert_many([
            {"id": 1, "title": "Alien comedy short", "year": 2020,
             "genres": "комедия", "runtime": 89},
            {"id": 2, "title": "Alien comedy lower edge", "year": 2020,
             "genres": "комедия", "runtime": 90},
            {"id": 3, "title": "Alien comedy upper edge", "year": 2020,
             "genres": "комедия", "runtime": 150},
            {"id": 4, "title": "Alien comedy long", "year": 2020,
             "genres": "комедия", "runtime": 151},
            {"id": 5, "title": "Alien comedy unknown", "year": 2020,
             "genres": "комедия"},
            {"id": 6, "title": "Alien comedy other year", "year": 2018,
             "genres": "комедия", "runtime": 110},
            {"id": 7, "title": "Alien drama", "year": 2020,
             "genres": "драма", "runtime": 110},
        ])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_lower_upper_and_unknown_runtime_boundaries(self) -> None:
        filters = {"genre": "комедия", "category": "aliens", "year_from": 2020,
                   "year_to": 2020}
        rows, total = self.db.search(
            **filters, min_runtime=90, max_runtime=150, limit=20
        )
        self.assertEqual(total, 2)
        self.assertEqual({row["id"] for row in rows}, {2, 3})

        lower_rows, _ = self.db.search(**filters, min_runtime=150, limit=20)
        self.assertEqual({row["id"] for row in lower_rows}, {3, 4})
        upper_rows, _ = self.db.search(**filters, max_runtime=90, limit=20)
        self.assertEqual({row["id"] for row in upper_rows}, {1, 2})
        self.assertNotIn(5, {row["id"] for row in lower_rows + upper_rows})

    def test_duration_composes_with_genre_theme_year_and_evening_picker_query(self) -> None:
        rows, total = self.db.search(
            genre="комедия",
            category="aliens",
            year_from=2020,
            year_to=2020,
            min_runtime=90,
            max_runtime=120,
            limit=20,
        )

        self.assertEqual(total, 1)
        self.assertEqual([row["id"] for row in rows], [2])
        chosen = self.db.random_movie(
            {
                "genre": "комедия",
                "category": "aliens",
                "year_from": 2020,
                "year_to": 2020,
                "min_runtime": 90,
                "max_runtime": 120,
            }
        )
        self.assertEqual(chosen["id"], 2)

    def test_invalid_runtime_bounds_are_rejected(self) -> None:
        for field in ("min_runtime", "max_runtime"):
            for value in (0, -1, 90.5, True):
                with self.subTest(field=field, value=value):
                    with self.assertRaises(ValueError):
                        self.db.search(**{field: value})
        with self.assertRaises(ValueError):
            self.db.search(min_runtime=151, max_runtime=150)


if __name__ == "__main__":
    unittest.main()
