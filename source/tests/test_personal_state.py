"""Tests for persisted personal movie state and its Tkinter controls."""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import Config  # noqa: E402
from movie_search.database import MovieDB  # noqa: E402
from movie_search.ui import (  # noqa: E402
    DetailWindow,
    MovieApp,
    MovieCard,
    WatchlistEditWindow,
)

pytestmark = pytest.mark.gui


class PersonalStateDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "movies.db"
        self.db = MovieDB(self.db_path)
        self.db.upsert_many(
            [
                {
                    "id": 1,
                    "title": "Alien drama watched",
                    "year": 2020,
                    "rating": 8.0,
                    "votes": 100,
                    "genres": "драма",
                    "overview": "An alien signal arrives.",
                },
                {
                    "id": 2,
                    "title": "Alien drama unwatched",
                    "year": 2021,
                    "rating": 8.5,
                    "votes": 120,
                    "genres": "драма",
                    "overview": "The aliens return.",
                },
                {
                    "id": 3,
                    "title": "Another drama",
                    "year": 2022,
                    "rating": 8.0,
                    "votes": 100,
                    "genres": "драма",
                },
            ]
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_state_is_saved_and_filter_composes_with_existing_filters(self) -> None:
        self.db.set_personal_state(1, watched=True, personal_rating=9)
        self.db.toggle_bookmark(1)
        self.db.toggle_bookmark(2)
        self.db.set_personal_state(2, watched=False, personal_rating=None)
        self.db.upsert_many(
            [
                {
                    "id": 1,
                    "title": "Alien drama watched",
                    "year": 2020,
                    "rating": 8.0,
                    "votes": 100,
                    "genres": "драма",
                    "overview": "An alien signal arrives.",
                }
            ]
        )

        rows, total = self.db.search(
            genre="драма",
            category="aliens",
            bookmarked_only=True,
            hide_watched=True,
            min_rating=6.0,
        )
        self.assertEqual(total, 1)
        self.assertEqual([row["id"] for row in rows], [2])
        self.assertEqual(self.db.get(1)["watched"], 1)
        self.assertEqual(self.db.get(1)["personal_rating"], 9)

        self.db.set_personal_state(1, watched=False, personal_rating=7)
        self.assertEqual(self.db.get(1)["watched"], 0)
        self.assertEqual(self.db.get(1)["personal_rating"], 7)

    def test_personal_rating_is_limited_to_integers_one_through_ten(self) -> None:
        for rating in (0, 11, 4.5, True):
            with self.subTest(rating=rating):
                with self.assertRaises(ValueError):
                    self.db.set_personal_state(
                        1, watched=False, personal_rating=rating
                    )

    def test_existing_database_migration_is_idempotent(self) -> None:
        self.db.close()
        legacy_path = Path(self.temp_dir.name) / "legacy.db"
        connection = sqlite3.connect(legacy_path)
        connection.execute(
            "CREATE TABLE movies ("
            "id INTEGER PRIMARY KEY, title TEXT NOT NULL, title_lower TEXT NOT NULL DEFAULT '', "
            "original_title TEXT, year INTEGER, release_date TEXT, overview TEXT, tagline TEXT, "
            "rating REAL, votes INTEGER, genres TEXT NOT NULL DEFAULT '', "
            "countries TEXT NOT NULL DEFAULT '', runtime INTEGER, director TEXT, "
            "poster_path TEXT, poster_file TEXT, poster_url TEXT, source TEXT, "
            "imdb_id TEXT, link TEXT, updated_at TEXT)"
        )
        connection.execute(
            "INSERT INTO movies (id, title, title_lower) VALUES (10, 'Legacy film', 'legacy film')"
        )
        connection.commit()
        connection.close()

        migrated = MovieDB(legacy_path)
        migrated.set_personal_state(10, watched=True, personal_rating=10)
        migrated.close()

        migrated = MovieDB(legacy_path)
        state = migrated.get(10)
        self.assertEqual(state["watched"], 1)
        self.assertEqual(state["personal_rating"], 10)
        columns = {
            row[1]: row for row in migrated._conn.execute("PRAGMA table_info(movies)")
        }
        self.assertEqual(columns["watched"][4], "0")
        self.assertIsNone(columns["personal_rating"][4])
        migrated.close()


class PersonalStateUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "movies.db"
        seed = MovieDB(self.db_path)
        seed.upsert_many(
            [
                {
                    "id": 1,
                    "title": "Movie with saved state",
                    "year": 2020,
                    "rating": 8.0,
                    "votes": 100,
                    "genres": "драма",
                    "overview": "A test description.",
                }
            ]
        )
        seed.close()
        config = Config(Path(self.temp_dir.name) / "config.json")
        config.data["tmdb_api_key"] = ""
        config.data["ui_language"] = "ru-RU"
        try:
            with patch.dict(os.environ, {"TMDB_API_KEY": ""}):
                self.app = MovieApp(
                    db_path=self.db_path,
                    posters_dir=Path(self.temp_dir.name) / "posters",
                    config=config,
                )
        except tk.TclError as exc:
            self.temp_dir.cleanup()
            self.skipTest(f"Tkinter display unavailable: {exc}")
        self.app.suppress_dialogs = True

    def tearDown(self) -> None:
        if hasattr(self, "app") and self.app.winfo_exists():
            self.app._on_close()
        if hasattr(self, "app"):
            self.app.db.close()
        self.temp_dir.cleanup()

    def test_detail_controls_save_and_reload_personal_state(self) -> None:
        self.assertTrue(hasattr(self.app, "hide_watched_var"))
        with patch.object(DetailWindow, "_start_extras", lambda _self: None):
            first = DetailWindow(self.app, self.app.db.get(1))
            self.assertFalse(first.watched_var.get())
            self.assertEqual(first.personal_rating_var.get(), "—")

            first.personal_rating_var.set("8")
            first._save_personal_state()
            self.assertEqual(self.app.db.get(1)["personal_rating"], 8)
            first.destroy()

            reopened = DetailWindow(self.app, self.app.db.get(1))
            self.assertFalse(reopened.watched_var.get())
            self.assertEqual(reopened.personal_rating_var.get(), "8")
            reopened.watched_var.set(True)
            reopened._save_personal_state()
            self.assertEqual(self.app.db.get(1)["watched"], 1)
            reopened.destroy()

        self.app.hide_watched_var.set(True)
        filters = self.app._collect_filters()
        self.assertTrue(filters["hide_watched"])
        rows, total = self.app.db.search(**filters)
        self.assertEqual(total, 0)
        self.assertEqual(rows, [])

    def test_card_quick_actions_persist_and_sync_open_detail(self) -> None:
        card = MovieCard(
            self.app.cards_frame,
            self.app.db.get(1),
            self.app.open_details,
            self.app.placeholder_photo,
            language=self.app.ui_language,
            on_personal_state=self.app._save_card_personal_state,
        )
        card.pack()
        self.app.card_by_id[1] = card
        self.app.cards.append(card)
        self.app.update_idletasks()
        self.assertLessEqual(
            card.snippet_lbl.winfo_y() + card.snippet_lbl.winfo_height(),
            MovieCard.HEIGHT,
        )
        self.assertEqual(str(card.personal_rating_combo.cget("state")), "readonly")
        with patch.object(DetailWindow, "_start_extras", lambda _self: None):
            detail = DetailWindow(self.app, self.app.db.get(1))

            card.watched_var.set(True)
            card._save_personal_state()
            self.assertEqual(self.app.db.get(1)["watched"], 1)
            self.assertTrue(detail.watched_var.get())

            card.personal_rating_var.set("8")
            card._save_personal_state()
            self.assertEqual(self.app.db.get(1)["personal_rating"], 8)
            self.assertEqual(detail.personal_rating_var.get(), "8")
            self.assertEqual(card.movie["personal_rating"], 8)
            detail.destroy()

    def test_card_watchlist_and_feedback_actions_are_editable_and_localized(self) -> None:
        movie = self.app.db.get(1)
        movie["recommendation_reasons"] = [{"type": "genre", "value": "драма"}]
        movie["_recommendation"] = True
        card = MovieCard(
            self.app.cards_frame,
            movie,
            self.app.open_details,
            self.app.placeholder_photo,
            language=self.app.ui_language,
            on_watchlist=self.app._save_watchlist_state,
            on_watchlist_edit=self.app._edit_watchlist_movie,
            on_feedback=self.app._save_recommendation_feedback,
        )
        card.pack()
        self.app.cards.append(card)
        self.app.card_by_id[1] = card
        self.assertTrue(hasattr(card, "feedback_frame"))

        card._toggle_watchlist()
        self.assertEqual(self.app.db.watchlist_count(), 1)
        editor = WatchlistEditWindow(self.app, movie)
        editor.priority_var.set("5")
        editor.note_text.insert("1.0", "Priority note")
        editor._save()
        self.assertEqual(self.app.db.watchlist_entry(1)["priority"], 5)
        self.assertEqual(self.app.db.watchlist_entry(1)["note"], "Priority note")

        card._save_feedback("like")
        self.assertEqual(self.app.db.recommendation_feedback()[0]["recommendation_feedback"], "like")
        self.app.ui_language = "en-US"
        self.app._apply_language()
        self.assertEqual(card.watchlist_btn.cget("text"), "✓ In watchlist")
        self.assertEqual(card.watchlist_edit_btn.cget("text"), "Priority & note")
        self.assertEqual(card.feedback_frame.winfo_children()[0].cget("text"), "👍 Fits me")
        self.assertTrue(self.app._save_recommendation_feedback(1, None))
        card._toggle_watchlist()
        self.assertEqual(self.app.db.watchlist_count(), 0)


if __name__ == "__main__":
    unittest.main()
