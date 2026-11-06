"""Focused tests for movie recommendations and personal library features."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.database import MovieDB  # noqa: E402


class PersonalFeatureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "movies.db")
        self.db.upsert_many([
            {
                "id": 1, "title": "Loved horror", "year": 2020, "genres": "ужасы",
                "runtime": 108, "countries": "US,JP",
            },
            {
                "id": 2, "title": "Horror pick", "year": 2021, "genres": "ужасы",
                "rating": 8.0, "votes": 500, "runtime": 100,
            },
            {
                "id": 3, "title": "Comedy pick", "year": 2021, "genres": "комедия",
                "rating": 9.0, "votes": 1000,
            },
            {
                "id": 4, "title": "Another horror", "year": 2018, "genres": "ужасы,триллер",
                "rating": 7.0, "votes": 100,
            },
            {
                "id": 5, "title": "Comedy alternative", "year": 2019, "genres": "комедия",
                "rating": 9.0, "votes": 1000,
            },
        ])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_recommendations_use_personal_ratings_and_skip_watched(self) -> None:
        self.db.set_personal_state(1, watched=True, personal_rating=10)
        self.db.set_personal_state(3, watched=True, personal_rating=2)
        self.db.set_keywords([(1, "space"), (2, "space")])
        self.db.set_cast([(1, "Loved Actor", 0), (2, "Loved Actor", 0)])

        recommendations = self.db.recommendations()

        self.assertEqual([row["id"] for row in recommendations], [2, 4])
        self.assertGreater(
            recommendations[0]["recommendation_score"],
            recommendations[1]["recommendation_score"],
        )
        self.assertEqual(
            {reason["type"] for reason in recommendations[0]["recommendation_reasons"]},
            {"genre", "keyword", "actor", "runtime"},
        )
        self.assertEqual(self.db.recommendations(0), [])

    def test_saved_filters_can_be_replaced_loaded_and_deleted(self) -> None:
        filters = {
            "genre": "ужасы", "category": "ghosts", "mood": "tense",
            "year_from": 2000, "year_to": 2026, "min_rating": 6.5,
            "min_votes": 10, "min_runtime": 90, "max_runtime": 150,
            "bookmarked_only": False, "hide_watched": True,
            "sort": "year_new",
        }
        self.db.save_filter("Weekend", filters)
        self.assertEqual(self.db.saved_filters()[0]["filters"], filters)

        changed = dict(filters, year_from=2010)
        self.db.save_filter("Weekend", changed)
        self.assertEqual(self.db.saved_filters()[0]["filters"]["year_from"], 2010)
        with self.assertRaises(ValueError):
            self.db.save_filter("Bad", {"unknown": "value"})
        self.assertTrue(self.db.delete_filter("Weekend"))
        self.assertFalse(self.db.delete_filter("Weekend"))

    def test_genre_theme_mood_and_year_filters_compose(self) -> None:
        rows, total = self.db.search(
            genre="ужасы", category="ghosts", mood="tense",
            year_from=2019, year_to=2022, limit=20,
        )

        self.assertEqual(total, 0)
        self.assertEqual(rows, [])

        self.db.set_keywords([(2, "haunted house")])
        rows, total = self.db.search(
            genre="ужасы", category="ghosts", mood="tense",
            year_from=2019, year_to=2022, limit=20,
        )
        self.assertEqual(total, 1)
        self.assertEqual([row["id"] for row in rows], [2])

    def test_json_export_import_is_validated_idempotent_and_catalog_safe(self) -> None:
        self.db.set_personal_state(1, watched=True, personal_rating=9)
        self.db.toggle_bookmark(1)
        saved = {
            "genre": "ужасы", "category": "ghosts", "mood": "tense",
            "year_from": 2000, "year_to": 2026, "sort": "year_new",
        }
        self.db.save_filter("Weekend", saved)
        exported = self.db.export_personal_data()
        self.assertEqual(exported["format"], "movie-finder-personal-data")
        self.assertEqual(exported["version"], 4)
        self.assertEqual(exported["movies"], [
            {"id": 1, "watched": True, "personal_rating": 9, "bookmarked": True}
        ])
        self.assertEqual(
            exported["saved_filters"], [{"name": "Weekend", "filters": saved}]
        )
        self.assertEqual(exported["watchlist"], [])
        self.assertEqual(exported["recommendation_feedback"], [])
        self.assertEqual(exported["plans"], [])
        self.assertEqual(exported["content_exclusions"], {"genre": [], "theme": []})
        self.assertNotIn("tmdb_api_key", exported)

        target = MovieDB(Path(self.temp_dir.name) / "target.db")
        target.upsert_many([
            {"id": 1, "title": "Unchanged title", "poster_path": "/original.jpg"},
            {"id": 2, "title": "Also unchanged"},
        ])
        target.set_personal_state(2, watched=True, personal_rating=4)
        incoming = dict(exported)
        incoming["movies"] = exported["movies"] + [
            {"id": 987654, "watched": True, "personal_rating": 7, "bookmarked": True}
        ]
        result = target.import_personal_data(incoming)
        self.assertEqual(result, {
            "imported": 1, "watchlist_imported": 0, "feedback_imported": 0,
            "plans_imported": 0, "content_exclusions_imported": 0,
            "unknown_ids": [987654],
        })
        self.assertEqual(target.get(1)["title"], "Unchanged title")
        self.assertEqual(target.get(1)["poster_path"], "/original.jpg")
        self.assertEqual(target.get(1)["watched"], 1)
        self.assertEqual(target.get(1)["personal_rating"], 9)
        self.assertTrue(target.is_bookmarked(1))
        self.assertEqual(target.saved_filters()[0]["filters"], saved)
        self.assertEqual(target.import_personal_data(incoming), result)

        invalid = dict(exported)
        invalid["movies"] = [
            {"id": 1, "watched": False, "personal_rating": 5, "bookmarked": False},
            {"id": 2, "watched": False, "personal_rating": 0, "bookmarked": False},
        ]
        with self.assertRaises(ValueError):
            target.import_personal_data(invalid)
        self.assertEqual(target.get(1)["personal_rating"], 9)
        self.assertEqual(target.get(1)["watched"], 1)
        self.assertEqual(target.get(2)["personal_rating"], 4)
        target.close()

    def test_version_one_personal_export_remains_importable(self) -> None:
        legacy = {
            "format": "movie-finder-personal-data",
            "version": 1,
            "exported_at": "2026-01-01T00:00:00",
            "movies": [
                {"id": 1, "watched": True, "personal_rating": 8, "bookmarked": False}
            ],
        }
        self.assertEqual(
            self.db.import_personal_data(legacy), {"imported": 1, "unknown_ids": []}
        )
        self.assertEqual(self.db.get(1)["personal_rating"], 8)

    def test_watchlist_and_feedback_are_idempotent_and_round_trip(self) -> None:
        self.db.set_watchlist(1, priority=5, note="See this weekend")
        self.db._conn.execute(
            "UPDATE watchlist SET updated_at = '2000-01-01T00:00:00' WHERE movie_id = 1"
        )
        self.db._conn.commit()
        original_updated = self.db.watchlist_entry(1)["updated_at"]
        self.db.set_watchlist(1, priority=5, note="See this weekend")
        self.assertEqual(self.db.watchlist_entry(1)["updated_at"], original_updated)
        self.db.set_recommendation_feedback(2, "like")
        self.db._conn.execute(
            "UPDATE recommendation_feedback SET updated_at = '2000-01-01T00:00:00' "
            "WHERE movie_id = 2"
        )
        self.db._conn.commit()
        feedback_updated = {
            row["id"]: row["feedback_updated_at"]
            for row in self.db.recommendation_feedback()
        }[2]
        self.db.set_recommendation_feedback(2, "like")
        self.assertEqual({
            row["id"]: row["feedback_updated_at"]
            for row in self.db.recommendation_feedback()
        }[2], feedback_updated)
        self.db.set_recommendation_feedback(3, "dislike")
        self.assertEqual(self.db.watchlist_count(), 1)
        self.assertEqual(self.db.watchlist()[0]["watchlist_note"], "See this weekend")
        self.assertEqual(len(self.db.recommendation_feedback()), 2)

        payload = self.db.export_personal_data()
        self.assertEqual(payload["watchlist"], [
            {"id": 1, "priority": 5, "note": "See this weekend"}
        ])
        self.assertEqual(payload["recommendation_feedback"], [
            {"id": 2, "feedback": "like"},
            {"id": 3, "feedback": "dislike"},
        ])
        target = MovieDB(Path(self.temp_dir.name) / "personal-roundtrip.db")
        target.upsert_many([{"id": movie_id, "title": f"Movie {movie_id}"} for movie_id in range(1, 6)])
        expected = {
            "imported": 0, "watchlist_imported": 1, "feedback_imported": 2,
            "plans_imported": 0, "content_exclusions_imported": 0,
            "unknown_ids": [],
        }
        self.assertEqual(target.import_personal_data(payload), expected)
        self.assertEqual(target.watchlist()[0]["watchlist_priority"], 5)
        self.assertEqual(target.watchlist()[0]["watchlist_note"], "See this weekend")
        self.assertEqual(
            {row["recommendation_feedback"] for row in target.recommendation_feedback()},
            {"like", "dislike"},
        )
        self.assertEqual(target.import_personal_data(payload), expected)

        invalid = dict(payload)
        invalid["movies"] = [
            {"id": 2, "watched": True, "personal_rating": 8, "bookmarked": False}
        ]
        invalid["watchlist"] = [{"id": 1, "priority": 6, "note": "invalid"}]
        with self.assertRaises(ValueError):
            target.import_personal_data(invalid)
        self.assertEqual(target.watchlist()[0]["watchlist_priority"], 5)
        self.assertEqual(target.watchlist()[0]["watchlist_note"], "See this weekend")
        self.assertEqual(target.get(2)["watched"], 0)
        self.assertIsNone(target.get(2)["personal_rating"])
        self.assertTrue(target.remove_from_watchlist(1))
        self.assertFalse(target.remove_from_watchlist(1))
        target.set_recommendation_feedback(2, None)
        self.assertEqual(
            [row["recommendation_feedback"] for row in target.recommendation_feedback()],
            ["dislike"],
        )
        for invalid_priority in (0, 6, True, 2.5):
            with self.subTest(priority=invalid_priority), self.assertRaises(ValueError):
                target.set_watchlist(2, priority=invalid_priority)
        with self.assertRaises(ValueError):
            target.set_watchlist(2, note="x" * 2001)
        with self.assertRaises(ValueError):
            target.set_recommendation_feedback(2, "neutral")
        target.close()

    def test_legacy_version_two_import_remains_supported(self) -> None:
        legacy = {
            "format": "movie-finder-personal-data",
            "version": 2,
            "exported_at": "2026-01-01T00:00:00",
            "movies": [
                {"id": 1, "watched": True, "personal_rating": 8, "bookmarked": False}
            ],
            "saved_filters": [],
        }
        self.assertEqual(
            self.db.import_personal_data(legacy), {"imported": 1, "unknown_ids": []}
        )
        self.assertEqual(self.db.get(1)["personal_rating"], 8)

    def test_recommendation_feedback_adjusts_ranking_and_can_start_without_ratings(self) -> None:
        self.assertEqual(self.db.recommendations(), [])
        self.db.set_recommendation_feedback(1, "like")
        self.db.set_recommendation_feedback(3, "dislike")
        rows = self.db.recommendations()
        self.assertTrue(rows)
        self.assertEqual(rows[0]["id"], 2)
        self.assertNotIn(3, [row["id"] for row in rows])
        self.assertNotIn(5, [row["id"] for row in rows])

    def test_catalog_quality_checks_are_read_only_and_report_metadata_flags(self) -> None:
        self.db.upsert_many([
            {
                "id": 6, "title": "Same Film", "year": 2020,
                "overview": "This description is comfortably long enough.", "source": "TMDb",
            },
            {
                "id": 7, "title": "Same-Film!", "year": 2020,
                "overview": "", "source": "Wikipedia",
            },
            {
                "id": 8, "title": "Old Cinema", "year": 1500,
                "release_date": "2020-01-01", "overview": "Tiny", "source": "offline",
            },
            {"id": 9, "title": "No year", "overview": "", "source": ""},
            {"id": 10, "title": "Future film", "year": 2027, "overview": "Long enough description."},
        ])
        before_changes = self.db._conn.total_changes
        before_rows = self.db._conn.execute(
            "SELECT id, title, year, release_date, overview, source FROM movies ORDER BY id"
        ).fetchall()
        issues = self.db.catalog_quality_issues(current_year=2026)
        after_rows = self.db._conn.execute(
            "SELECT id, title, year, release_date, overview, source FROM movies ORDER BY id"
        ).fetchall()
        self.assertEqual(self.db._conn.total_changes, before_changes)
        self.assertEqual(before_rows, after_rows)
        by_id = {row["id"]: row for row in issues}
        self.assertIn("duplicate_title", by_id[6]["flags"])
        self.assertIn(7, by_id[6]["duplicate_ids"])
        self.assertEqual(by_id[7]["source"], "Wikipedia")
        self.assertIn("invalid_year", by_id[8]["flags"])
        self.assertIn("year_mismatch", by_id[8]["flags"])
        self.assertIn("short_description", by_id[8]["flags"])
        self.assertIn("missing_year", by_id[9]["flags"])
        self.assertIn("empty_description", by_id[9]["flags"])
        self.assertIn("invalid_year", by_id[10]["flags"])

    def test_random_movie_respects_filters_and_excludes_watched(self) -> None:
        self.db.set_personal_state(1, watched=True, personal_rating=None)
        self.db.set_personal_state(2, watched=True, personal_rating=None)

        movie = self.db.random_movie({
            "genre": "ужасы", "year_from": 2017, "year_to": 2020,
            "min_rating": 6.0, "sort": "year_new",
        })

        self.assertIsNotNone(movie)
        self.assertEqual(movie["id"], 4)
        self.assertIsNone(self.db.random_movie({"genre": "ужасы", "year_from": 2021, "year_to": 2026}))

    def test_movie_details_read_existing_cast_country_runtime_and_provider_cache(self) -> None:
        self.db.set_cast([(1, "Actor One", 0), (1, "Actor Two", 1)])
        self.db.set_keywords([(1, "haunted house")])
        self.db.set_providers([(1, "JP", "Local Stream", "https://example.invalid/watch")])

        details = self.db.detail_metadata(1)

        self.assertEqual(details["runtime"], 108)
        self.assertEqual(details["countries"], ",US,JP,")
        self.assertEqual(details["cast"], ["Actor One", "Actor Two"])
        self.assertEqual(details["keywords"], ["haunted house"])
        self.assertEqual(details["providers"]["names"], "Local Stream")
        self.assertEqual(details["providers"]["region"], "JP")


if __name__ == "__main__":
    unittest.main()
