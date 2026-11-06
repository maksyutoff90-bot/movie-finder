"""Tests for SQL filtering and the bilingual evening movie picker."""

from __future__ import annotations

import os
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
    CatalogQualityWindow,
    CollectionViewerWindow,
    EveningPickerWindow,
    MovieApp,
    RecommendationFeedbackWindow,
    WatchlistEditWindow,
    WatchlistWindow,
)

pytestmark = pytest.mark.gui


class EveningPickerDatabaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "evening.db")
        self.db.upsert_many(
            [
                {
                    "id": 1, "title": "Alien comedy short", "genres": "комедия",
                    "runtime": 85,
                },
                {
                    "id": 2, "title": "Alien comedy long", "genres": "комедия",
                    "runtime": 115,
                },
                {
                    "id": 3, "title": "Alien comedy unknown runtime",
                    "genres": "комедия",
                },
                {
                    "id": 4, "title": "Alien comedy watched",
                    "genres": "комедия", "runtime": 75,
                },
                {
                    "id": 5, "title": "Alien drama", "genres": "драма",
                    "runtime": 80,
                },
            ]
        )
        self.db.set_personal_state(4, watched=True, personal_rating=None)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_sql_combines_mood_theme_genre_runtime_and_watched_filters(self) -> None:
        rows, total = self.db.search(
            genre="комедия",
            mood="light",
            category="aliens",
            max_runtime=90,
            hide_watched=True,
            limit=20,
        )

        self.assertEqual(total, 1)
        self.assertEqual([row["id"] for row in rows], [1])

    def test_random_choice_honors_duration_and_excludes_unknown_and_watched(self) -> None:
        for _ in range(5):
            movie = self.db.random_movie(
                {"genre": "комедия", "mood": "light", "category": "aliens"},
                max_runtime=90,
            )
            self.assertIsNotNone(movie)
            self.assertEqual(movie["id"], 1)

    def test_unlimited_choice_can_include_movies_with_unknown_runtime(self) -> None:
        rows, total = self.db.search(
            genre="комедия", category="aliens", hide_watched=True, limit=20
        )

        self.assertEqual(total, 3)
        self.assertEqual({row["id"] for row in rows}, {1, 2, 3})

    def test_collection_queue_applies_filters_and_excludes_watched(self) -> None:
        self.db.upsert_many([
            {"id": 6, "title": "Comedy queue one", "year": 2022, "genres": "комедия"},
            {"id": 7, "title": "Comedy queue two", "year": 2023, "genres": "комедия"},
            {"id": 8, "title": "Comedy queue watched", "year": 2024, "genres": "комедия"},
            {"id": 9, "title": "Drama excluded", "year": 2024, "genres": "драма"},
        ])
        self.db.set_personal_state(8, watched=True, personal_rating=None)
        queue = self.db.collection_queue({
            "genre": "комедия", "year_from": 2022, "year_to": 2026,
        }, page_size=1)
        self.assertEqual({movie["id"] for movie in queue}, {6, 7})
        self.assertNotIn(8, [movie["id"] for movie in queue])
        self.assertNotIn(9, [movie["id"] for movie in queue])

    def test_no_candidates_and_invalid_runtime_limit(self) -> None:
        self.assertIsNone(self.db.random_movie(
            {"genre": "ужасы", "category": "aliens"}, max_runtime=90
        ))
        for invalid in (0, -1, 90.5, True):
            with self.subTest(max_runtime=invalid):
                with self.assertRaises(ValueError):
                    self.db.search(max_runtime=invalid)


class EveningPickerUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "ui-evening.db"
        seed = MovieDB(self.db_path)
        seed.upsert_many(
            [{
                "id": 1, "title": "Alien comedy for tonight",
                "year": 2024, "genres": "комедия", "runtime": 85,
            }]
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

    def tearDown(self) -> None:
        if hasattr(self, "app") and self.app.winfo_exists():
            self.app._on_close()
        if hasattr(self, "app"):
            self.app.db.close()
        self.temp_dir.cleanup()

    @staticmethod
    def _label_for(options: dict[str, str | None], value: str | None) -> str:
        return next(label for label, key in options.items() if key == value)

    def test_picker_translates_controls_and_opens_selected_movie(self) -> None:
        picker = EveningPickerWindow(self.app)
        picker.genre_var.set(self._label_for(picker._genre_by_label, "комедия"))
        picker.mood_var.set(self._label_for(picker._mood_by_label, "light"))
        picker.category_var.set(self._label_for(picker._category_by_label, "aliens"))
        runtime_label = self._label_for(picker._runtime_by_label, 90)
        picker.runtime_var.set(runtime_label)

        self.assertEqual(picker.pick_button.cget("text"), "Выбрать фильм")
        self.assertEqual(picker.runtime_var.get(), runtime_label)
        self.assertEqual(picker._runtime_by_label[runtime_label], 90)
        picker._pick_movie()
        self.assertEqual(picker.movie["id"], 1)
        self.assertEqual(picker.result_title.cget("text"), "Alien comedy for tonight")
        picker.again_button.invoke()
        self.assertEqual(picker.movie["id"], 1)

        opened: list[int] = []
        self.app.open_details = lambda movie: opened.append(movie["id"])
        picker._open_details()
        self.assertEqual(opened, [1])

        self.app.toggle_language()
        self.assertIn("Comedy", picker.genre_combo.cget("values"))
        self.assertIn("Mood · Light & funny", picker.mood_combo.cget("values"))
        self.assertIn("Theme · UFOs & aliens", picker.category_combo.cget("values"))
        self.assertIn("Up to 90 min", picker.runtime_combo.cget("values"))
        self.assertEqual(picker.open_button.cget("text"), "Open details")
        self.assertEqual(picker.movie["id"], 1)
        picker.genre_var.set(self._label_for(picker._genre_by_label, "ужасы"))
        picker._pick_movie()
        self.assertIsNone(picker.movie)
        self.assertEqual(picker.result_title.cget("text"), "No matching movies")
        picker.destroy()

    def test_collection_viewer_skip_watched_rating_flow_and_language(self) -> None:
        self.app.db.upsert_many([
            {
                "id": 2, "title": "Second queue film", "year": 2022,
                "genres": "комедия", "overview": "Second movie overview.",
            },
            {
                "id": 3, "title": "Third queue film", "year": 2023,
                "genres": "комедия", "overview": "Third movie overview.",
            },
            {
                "id": 4, "title": "Already watched", "year": 2024,
                "genres": "комедия",
            },
        ])
        self.app.db.set_personal_state(4, watched=True, personal_rating=None)
        viewer = CollectionViewerWindow(
            self.app, {"genre": "комедия", "year_from": 2022, "year_to": 2023}
        )
        self.assertEqual(len(viewer.movies), 2)
        self.assertEqual(viewer.watched_btn.cget("text"), "Смотрел")

        viewer._skip()
        skipped_id = viewer.movies[0]["id"]
        self.assertEqual(self.app.db.get(skipped_id)["watched"], 0)
        watched_id = viewer.movies[1]["id"]
        viewer._mark_watched()
        self.assertEqual(self.app.db.get(watched_id)["watched"], 1)
        self.assertEqual(viewer.index, 2)

        rated_id = viewer.movies[0]["id"]
        self.app.db.set_personal_state(rated_id, watched=False, personal_rating=None)
        viewer.index = 0
        viewer.rating_var.set("9")
        viewer._rate_and_next()
        self.assertEqual(self.app.db.get(rated_id)["watched"], 1)
        self.assertEqual(self.app.db.get(rated_id)["personal_rating"], 9)

        watchlist = WatchlistWindow(self.app)
        feedback = RecommendationFeedbackWindow(self.app)
        quality = CatalogQualityWindow(self.app)
        edit = WatchlistEditWindow(self.app, self.app.db.get(1))
        self.app.toggle_language()
        self.assertEqual(viewer.watched_btn.cget("text"), "Watched")
        self.assertEqual(watchlist.title(), "Watchlist")
        self.assertEqual(edit.priority_label.cget("text"), "Priority (1–5, 5 is highest):")
        self.assertEqual(feedback.title(), "Recommendation feedback")
        self.assertEqual(quality.title(), "Catalogue quality check")

        for window in (viewer, watchlist, feedback, quality, edit):
            window.destroy()


if __name__ == "__main__":
    unittest.main()
