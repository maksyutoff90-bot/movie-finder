"""Tests for local discovery modes using temporary SQLite databases."""

from __future__ import annotations

import queue
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.database import MovieDB  # noqa: E402
from movie_search.discovery_modes import (  # noqa: E402
    blind_choice,
    challenge_progress,
    filmography,
    indifferent_movies,
    movie_twin,
    reveal_blind_choice,
    yearly_summary,
)
from movie_search.franchises import next_unwatched_in_order  # noqa: E402

pytestmark = pytest.mark.gui


class DiscoveryModesTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "temporary.db")

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_blind_card_masks_identity_until_explicit_reveal(self) -> None:
        self.db.upsert_many([
            {
                "id": 1, "title": "Secret Title", "year": 2001,
                "genres": "драма", "overview": "Локальное русское описание.",
            },
        ])
        self.db.set_english_overview(1, "A local English overview.")

        russian = blind_choice(self.db, "ru-RU")
        english = blind_choice(self.db, "en-US")

        self.assertEqual(set(russian), {"movie_id", "year", "genre", "overview"})
        self.assertNotIn("title", russian)
        self.assertNotIn("poster_path", russian)
        self.assertEqual(russian["genre"], "Драма")
        self.assertEqual(russian["overview"], "Локальное русское описание.")
        self.assertEqual(english["overview"], "A local English overview.")
        self.assertEqual(english["genre"], "Drama")
        self.assertEqual(reveal_blind_choice(self.db, russian)["title"], "Secret Title")
        with self.assertRaises(ValueError):
            blind_choice(self.db, "fr-FR")

    def test_blind_window_opens_details_only_after_reveal_action(self) -> None:
        self.db.upsert_many([
            {
                "id": 1, "title": "Hidden movie", "year": 2001,
                "genres": "драма", "overview": "Описание без названия.",
            },
        ])
        try:
            root = tk.Tk()
            root.withdraw()
        except tk.TclError as exc:
            self.skipTest(f"Tk is unavailable: {exc}")
        callbacks: queue.Queue = queue.Queue()
        root.db = self.db
        root.is_english = False
        root._text = lambda russian, english: english if root.is_english else russian
        root._register_window = lambda _window: None
        root._post = callbacks.put
        root.open_details = Mock()
        from movie_search.discovery_ui import DiscoveryModesWindow

        window = DiscoveryModesWindow(root)
        try:
            card = blind_choice(self.db, "ru-RU")
            window._blind_picked(card)
            self.assertNotIn("Hidden movie", window.blind_overview.cget("text"))
            self.assertNotIn("Hidden movie", window.blind_meta.cget("text"))
            root.open_details.assert_not_called()

            window._reveal_blind()
            for _ in range(30):
                try:
                    callback = callbacks.get(timeout=0.2)
                except queue.Empty:
                    continue
                callback()
                if root.open_details.called:
                    break
            root.open_details.assert_called_once()
            self.assertEqual(root.open_details.call_args.args[0]["title"], "Hidden movie")
        finally:
            window.destroy()
            root.destroy()

    def test_challenges_count_unique_watched_metadata(self) -> None:
        self.db.upsert_many([
            {"id": 1, "title": "A", "year": 1981, "countries": "US,FR",
             "genres": "драма,комедия"},
            {"id": 2, "title": "B", "year": 1989, "countries": "US,JP",
             "genres": "драма"},
            {"id": 3, "title": "C", "year": 1990, "countries": "FR",
             "genres": "боевик"},
            {"id": 4, "title": "D", "year": 2000, "countries": "DE",
             "genres": "триллер"},
        ])
        for movie_id in (1, 2, 3):
            self.db.set_personal_state(movie_id, watched=True, personal_rating=None)

        progress = {item["id"]: item for item in challenge_progress(self.db)}

        self.assertEqual(len(progress), 4)
        self.assertEqual(progress["decades"], {"id": "decades", "target": 5, "progress": 2})
        self.assertEqual(progress["countries"]["progress"], 3)
        self.assertEqual(progress["genres"]["progress"], 3)
        self.assertEqual(progress["watched"]["progress"], 3)
        empty_db = MovieDB(Path(self.temp_dir.name) / "empty.db")
        try:
            self.assertEqual(challenge_progress(empty_db)[0]["progress"], 0)
        finally:
            empty_db.close()

    def test_filmography_filters_exact_credit_and_reports_personal_status(self) -> None:
        self.db.upsert_many([
            {"id": 1, "title": "Actor film", "year": 2000},
            {"id": 2, "title": "Director film", "year": 2001, "director": "A. Person"},
            {"id": 3, "title": "Unrelated", "year": 2002},
        ])
        self.db.set_cast([(1, "A. Person", 0), (3, "Other Person", 0)])
        self.db.set_personal_state(1, watched=True, personal_rating=8)
        self.db.set_watchlist(1)
        self.db.add_plan(2, "2099-12-31")

        rows = filmography(self.db, "a. person")

        self.assertEqual([row["id"] for row in rows], [1, 2])
        self.assertEqual(rows[0]["statuses"], ["watched", "watchlist"])
        self.assertEqual(rows[1]["statuses"], ["planned"])
        self.assertEqual(self.db.filmography_search("A. Per"), ["A. Person"])

    def test_franchise_next_is_dated_ordered_catalogued_and_unwatched(self) -> None:
        collection = {
            "parts": [
                {"id": 1, "release_date": "2000-01-01", "in_catalog": True, "watched": True},
                {"id": 2, "release_date": "2005-01-01", "in_catalog": True, "watched": True},
                {"id": 3, "release_date": "2010-01-01", "in_catalog": True, "watched": False},
                {"id": 4, "release_date": "2015-01-01", "in_catalog": False, "watched": False},
                {"id": 5, "release_date": None, "in_catalog": True, "watched": False},
            ]
        }

        next_movie = next_unwatched_in_order(collection, 1)

        self.assertEqual(next_movie["id"], 3)
        self.assertIn("дате выхода", next_movie["explanation"])
        self.assertIsNone(next_unwatched_in_order(collection, 4))
        self.assertIsNone(next_unwatched_in_order(
            {"parts": [{"id": 1, "in_catalog": True}, {"id": 2, "watched": False}]}, 1
        ))
        self.assertIsNone(next_unwatched_in_order(
            {"parts": [
                {"id": 1, "release_date": "2020", "in_catalog": True, "watched": True},
                {"id": 2, "release_date": "2021-01-01", "in_catalog": True, "watched": False},
            ]}, 1
        ))

    def test_twins_require_match_and_supported_actor_country_or_decade_difference(self) -> None:
        self.db.upsert_many([
            {"id": 1, "title": "Source", "year": 2001, "countries": "US",
             "genres": "драма", "director": "Shared Director", "votes": 500},
            {"id": 2, "title": "Twin", "year": 1980, "countries": "FR",
             "genres": "драма", "director": "Shared Director", "votes": 100},
            {"id": 3, "title": "Watched twin", "year": 1980, "countries": "FR",
             "genres": "драма", "director": "Shared Director", "votes": 50},
            {"id": 4, "title": "No difference data", "genres": "драма",
             "director": "Shared Director", "votes": 300},
        ])
        self.db.set_cast([(1, "Actor A", 0), (2, "Actor B", 0), (3, "Actor C", 0)])
        self.db.set_personal_state(3, watched=True, personal_rating=None)

        results = movie_twin(self.db, 1)

        self.assertEqual([row["id"] for row in results], [2])
        self.assertEqual({item["type"] for item in results[0]["twin_differences"]},
                         {"actor", "country", "decade", "popularity"})
        self.assertTrue(results[0]["twin_matches"])

    def test_yearly_summary_uses_calendar_year_exclusive_end_boundary(self) -> None:
        self.db.upsert_many([
            {"id": 1, "title": "New Year", "year": 1981, "countries": "US,FR"},
            {"id": 2, "title": "Year end", "year": 1999, "countries": "JP"},
            {"id": 3, "title": "Previous year", "year": 2000, "countries": "US"},
            {"id": 4, "title": "Next year", "year": 2010, "countries": "DE"},
        ])
        self.db.set_personal_state(1, watched=True, personal_rating=8)
        self.db.set_personal_state(2, watched=False, personal_rating=6)
        with self.db._lock:
            self.db._conn.executemany(
                "INSERT INTO history (movie_id, viewed_at) VALUES (?, ?)",
                [
                    (1, "2024-01-01T00:00:00"),
                    (2, "2024-12-31T23:59:59"),
                    (3, "2023-12-31T23:59:59"),
                    (4, "2025-01-01T00:00:00"),
                ],
            )
            self.db._conn.commit()

        summary = yearly_summary(self.db, 2024)

        self.assertEqual(summary["history_count"], 2)
        self.assertEqual(summary["watched_count"], 1)
        self.assertEqual(summary["countries"], {"US": 1, "FR": 1, "JP": 1})
        self.assertEqual(summary["decades"], {1980: 1, 1990: 1})
        self.assertEqual(summary["rated_count"], 2)
        self.assertEqual(summary["average_rating"], 7.0)
        self.assertEqual(yearly_summary(self.db, 2022)["history_count"], 0)
        with self.assertRaises(ValueError):
            yearly_summary(self.db, True)

    def test_indifferent_mode_applies_limits_exclusions_and_diversifies(self) -> None:
        movies = [
            {"id": 1, "title": "Top drama", "year": 1981, "countries": "US",
             "genres": "драма", "runtime": 100, "rating": 9, "votes": 100},
            {"id": 2, "title": "Second drama", "year": 1982, "countries": "US",
             "genres": "драма", "runtime": 90, "rating": 8.8, "votes": 90},
            {"id": 3, "title": "Different comedy", "year": 2001, "countries": "FR",
             "genres": "комедия", "runtime": 95, "rating": 8, "votes": 80},
            {"id": 4, "title": "Too long", "year": 2011, "countries": "JP",
             "genres": "боевик", "runtime": 130, "rating": 10, "votes": 200},
            {"id": 5, "title": "Rated", "year": 2012, "countries": "DE",
             "genres": "триллер", "runtime": 90, "rating": 9.5, "votes": 200},
            {"id": 6, "title": "Disliked", "year": 2013, "countries": "IT",
             "genres": "комедия", "runtime": 90, "rating": 9, "votes": 150},
            {"id": 7, "title": "Watched", "year": 2014, "countries": "CA",
             "genres": "фэнтези", "runtime": 90, "rating": 8, "votes": 100},
            {"id": 8, "title": "Excluded", "year": 2015, "countries": "AU",
             "genres": "ужасы", "runtime": 90, "rating": 8.5, "votes": 120},
        ]
        self.db.upsert_many(movies)
        self.db.set_personal_state(5, watched=False, personal_rating=7)
        self.db.set_personal_state(7, watched=True, personal_rating=None)
        self.db.set_recommendation_feedback(6, "dislike")
        self.db.set_content_exclusions(genres=["ужасы"])

        selected = indifferent_movies(self.db, max_runtime=100, limit=5)

        self.assertEqual([movie["id"] for movie in selected], [1, 3, 2])
        self.assertEqual(selected[0]["diversity_reasons"], ["highest_ranked"])
        self.assertIn("decade", selected[1]["diversity_reasons"])
        self.assertTrue(all(movie["runtime"] <= 100 for movie in selected))
        self.assertFalse({movie["id"] for movie in selected} & {4, 5, 6, 7, 8})

    def test_indifferent_mode_handles_empty_catalogue(self) -> None:
        self.db.set_content_exclusions(genres=["ужасы"])
        self.assertEqual(indifferent_movies(self.db, max_runtime=90), [])

    def test_indifferent_mode_considers_candidates_beyond_first_search_page(self) -> None:
        candidates = [
            {
                "id": movie_id, "title": f"Movie {movie_id}", "year": 1981,
                "countries": ",US,", "genres": ",драма,", "runtime": 100,
                "rating": 9 if movie_id == 1 else 8, "votes": 100,
                "watched": 0, "personal_rating": None,
            }
            for movie_id in range(1, 1001)
        ]
        candidates.append({
            "id": 1001, "title": "Beyond page one", "year": 2001,
            "countries": ",FR,", "genres": ",комедия,", "runtime": 95,
            "rating": 7, "votes": 50, "watched": 0, "personal_rating": None,
        })
        with patch.object(self.db, "collection_queue", return_value=candidates) as queue:
            results = indifferent_movies(self.db, max_runtime=100, limit=2)

        self.assertEqual([movie["id"] for movie in results], [1, 1001])
        queue.assert_called_once_with(
            {"max_runtime": 100, "exclude_personal_content": True},
            page_size=500,
        )


if __name__ == "__main__":
    unittest.main()
