"""Focused tests for viewing plans, similar matching, and recommendation exclusions."""

from __future__ import annotations

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
from movie_search.const import category_label  # noqa: E402
from movie_search.database import MovieDB  # noqa: E402
from movie_search.ui import (  # noqa: E402
    UI_TEXT_EN,
    ContentExclusionsWindow,
    EveningPickerWindow,
    MovieApp,
    PlanEditWindow,
    PlanMovieSelectWindow,
    SimilarMoviesWindow,
    ViewingPlannerWindow,
)

pytestmark = pytest.mark.gui


class ViewingPlanTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.path = Path(self.temp_dir.name) / "plans.db"
        self.db = MovieDB(self.path)
        self.db.upsert_many([
            {"id": 1, "title": "Planned film", "watched": 0, "personal_rating": 8},
            {"id": 2, "title": "Another film"},
        ])
        self.db.set_personal_state(1, watched=False, personal_rating=8)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_plan_crud_and_only_manual_completion_marks_watched(self) -> None:
        plan_id = self.db.add_plan(1, "2099-12-31", "Cinema with friends")
        self.assertEqual(self.db.get(1)["watched"], 0)
        self.assertEqual(self.db.plans()[0]["status"], "planned")
        self.assertEqual(self.db.plans()[0]["note"], "Cinema with friends")

        self.db.update_plan(plan_id, "2099-12-30", "Home screening")
        self.assertEqual(self.db.plans()[0]["planned_date"], "2099-12-30")
        self.assertEqual(self.db.plans()[0]["note"], "Home screening")
        self.assertEqual(self.db.get(1)["watched"], 0)

        self.db.complete_plan(plan_id)
        self.assertEqual(self.db.get(1)["watched"], 1)
        self.assertEqual(self.db.get(1)["personal_rating"], 8)
        self.assertEqual(self.db.plans()[0]["status"], "completed")
        self.assertEqual(self.db.plans(upcoming_only=True), [])
        self.assertTrue(self.db.delete_plan(plan_id))
        self.assertFalse(self.db.delete_plan(plan_id))
        self.assertEqual(self.db.get(1)["watched"], 1)

    def test_plan_validation_and_idempotent_migration(self) -> None:
        with self.assertRaises(ValueError):
            self.db.add_plan(1, "2099-02-30")
        with self.assertRaises(ValueError):
            self.db.add_plan(999, "2099-12-31")
        self.db.add_plan(1, "2099-12-31")
        with self.assertRaises(ValueError):
            self.db.add_plan(1, "2099-12-31")
        self.db.close()
        self.db = MovieDB(self.path)
        self.db.close()
        self.db = MovieDB(self.path)
        self.assertEqual(len(self.db.plans()), 1)
        self.assertEqual(self.db._conn.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='viewing_plans'"
        ).fetchone()[0], 1)


class SimilarAndExclusionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "matches.db")
        self.db.upsert_many([
            {
                "id": 1, "title": "Source", "genres": "драма",
                "director": "Jane Director", "watched": 1, "personal_rating": 10,
                "runtime": 100,
            },
            {
                "id": 2, "title": "Strong match", "genres": "драма",
                "director": "Jane Director", "rating": 9.0, "votes": 100,
            },
            {
                "id": 3, "title": "Genre match", "genres": "драма",
                "rating": 8.0, "votes": 200,
            },
            {
                "id": 4, "title": "Avoided alien horror", "genres": "ужасы",
                "rating": 10.0, "votes": 1000,
            },
            {
                "id": 5, "title": "Comedy alternative", "genres": "комедия",
                "rating": 7.0, "votes": 30,
            },
        ])
        self.db.set_cast([(1, "Known actor", 0), (2, "Known actor", 0), (4, "Known actor", 0)])
        self.db.set_keywords([(1, "space"), (2, "space"), (4, "ufo invasion")])
        self.db.set_personal_state(1, watched=True, personal_rating=10)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_similar_modes_score_explain_and_limit_local_matches(self) -> None:
        rows = self.db.similar_by(
            1, ("actors", "director", "genres", "keywords"), limit=2
        )
        self.assertEqual([row["id"] for row in rows], [2, 4])
        self.assertEqual(rows[0]["similarity_score"], 10)
        self.assertEqual(
            {reason["type"] for reason in rows[0]["similarity_reasons"]},
            {"actor", "director", "genre", "keyword"},
        )
        self.assertEqual(
            self.db.similar_by(1, ("genres",), 1)[0]["id"], 2
        )
        self.assertEqual(self.db.similar_by(1, (), 10), [])
        self.assertEqual(self.db.similar_by(1, ("actors",), 0), [])
        with self.assertRaises(ValueError):
            self.db.similar_by(1, ("overview",), 10)

    def test_exclusions_cover_recommendations_random_and_similar_not_search(self) -> None:
        self.db.set_content_exclusions(genres=["ужасы"], themes=["aliens"])
        self.assertEqual(self.db.content_exclusions(), {
            "genre": ["ужасы"], "theme": ["aliens"],
        })
        self.assertNotIn(4, [row["id"] for row in self.db.recommendations()])
        self.assertNotEqual(self.db.random_movie()["id"], 4)
        self.assertNotIn(4, [
            row["id"] for row in self.db.similar_by(1, ("actors",), 60)
        ])
        self.assertEqual(self.db.similar_by(1, ("actors",), 60)[0]["id"], 2)

        ordinary, total = self.db.search(genre="ужасы", limit=20)
        self.assertEqual(total, 1)
        self.assertEqual([row["id"] for row in ordinary], [4])

        self.db.set_content_exclusions(
            genres=["драма", "ужасы", "комедия"]
        )
        self.assertIsNone(self.db.random_movie())
        self.assertEqual(self.db.recommendations(), [])
        self.assertEqual(self.db.similar_by(1, ("actors",), 60), [])

    def test_evening_picker_uses_the_same_exclusion_aware_random_path(self) -> None:
        from types import SimpleNamespace

        self.db.set_content_exclusions(genres=["ужасы"])
        picker = SimpleNamespace(app=SimpleNamespace(db=self.db))
        chosen = EveningPickerWindow._pick_filtered_movie(picker, {})
        self.assertIsNotNone(chosen)
        self.assertNotEqual(chosen["id"], 4)

        self.db.set_content_exclusions(
            genres=["драма", "ужасы", "комедия"]
        )
        self.assertIsNone(EveningPickerWindow._pick_filtered_movie(picker, {}))

    def test_exclusions_persist_and_personal_json_v4_is_atomic_and_compatible(self) -> None:
        self.db.add_plan(2, "2099-08-08", "Saved plan")
        self.db.set_content_exclusions(genres=["ужасы"], themes=["aliens"])
        payload = self.db.export_personal_data()
        self.assertEqual(payload["version"], 4)
        self.assertEqual(payload["plans"], [
            {"id": 2, "date": "2099-08-08", "note": "Saved plan", "status": "planned"}
        ])
        self.assertNotIn("tmdb_api_key", payload)

        target = MovieDB(Path(self.temp_dir.name) / "import.db")
        target.upsert_many([
            {"id": 1, "title": "Profile row"},
            {"id": 2, "title": "Catalog row", "poster_path": "/same.jpg"},
        ])
        self.assertEqual(target.import_personal_data(payload), {
            "imported": 1, "watchlist_imported": 0, "feedback_imported": 0,
            "plans_imported": 1, "content_exclusions_imported": 2,
            "unknown_ids": [],
        })
        self.assertEqual(target.plans()[0]["note"], "Saved plan")
        self.assertEqual(target.content_exclusions(), self.db.content_exclusions())
        self.assertEqual(target.get(2)["poster_path"], "/same.jpg")

        legacy_v3 = {
            "format": "movie-finder-personal-data",
            "version": 3,
            "exported_at": "2026-01-01T00:00:00",
            "movies": [],
            "saved_filters": [],
            "watchlist": [],
            "recommendation_feedback": [],
        }
        target.import_personal_data(legacy_v3)
        self.assertEqual(len(target.plans()), 1)
        self.assertEqual(target.content_exclusions(), self.db.content_exclusions())

        invalid = dict(payload)
        invalid["plans"] = [{"id": 2, "date": "bad-date", "note": "", "status": "planned"}]
        with self.assertRaises(ValueError):
            target.import_personal_data(invalid)
        self.assertEqual(target.plans()[0]["note"], "Saved plan")
        target.close()

    def test_bilingual_labels_for_new_controls_and_theme_options(self) -> None:
        self.assertEqual(UI_TEXT_EN["Планировщик кинопросмотра"], "Viewing planner")
        self.assertEqual(UI_TEXT_EN["Скрытие нежелательного контента"], "Hide unwanted content")
        self.assertEqual(category_label("aliens"), "Тема · НЛО и пришельцы")
        self.assertEqual(category_label("aliens", english=True), "Theme · UFOs & aliens")


class NewModeUITests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        root = Path(self.temp_dir.name)
        config = Config(root / "config.json")
        config.data["tmdb_api_key"] = ""
        config.data["ui_language"] = "ru-RU"
        try:
            with patch.dict("os.environ", {"TMDB_API_KEY": ""}):
                self.app = MovieApp(
                    db_path=root / "ui.db", posters_dir=root / "posters", config=config
                )
        except tk.TclError as exc:
            self.temp_dir.cleanup()
            self.skipTest(f"Tkinter display unavailable: {exc}")
        self.app.suppress_dialogs = True
        self.app.db.upsert_many([
            {
                "id": 1, "title": "Source", "genres": "драма",
                "director": "A Director", "rating": 7.0,
            },
            {
                "id": 2, "title": "Similar", "genres": "драма",
                "director": "A Director", "rating": 8.0,
            },
        ])
        self.app.db.set_cast([(1, "A Actor", 0), (2, "A Actor", 0)])

    def tearDown(self) -> None:
        if hasattr(self, "app") and self.app.winfo_exists():
            self.app._on_close()
        if hasattr(self, "app"):
            self.app.db.close()
        self.temp_dir.cleanup()

    def test_similar_planner_and_exclusion_windows_localize_and_persist(self) -> None:
        similar = SimilarMoviesWindow(self.app, self.app.db.get(1))
        similar.find()
        self.assertIn("Актёр:", similar.listbox.get(0))

        selector = PlanMovieSelectWindow(self.app)
        selector.query_var.set("Source")
        selector.search()
        self.assertEqual(len(selector.rows), 1)
        selector.listbox.selection_set(0)
        selector.choose()
        editor = next(
            window for window in self.app._windows
            if isinstance(window, PlanEditWindow)
        )
        editor.date_var.set("2099-12-01")
        editor.note_text.insert("1.0", "For later")
        editor._save()
        self.assertEqual(self.app.db.plans()[0]["note"], "For later")

        planner = ViewingPlannerWindow(self.app)
        planner.refresh()
        self.assertIn("For later", planner.listbox.get(0))
        planner.listbox.selection_set(0)
        planner.complete()
        self.assertEqual(self.app.db.get(1)["watched"], 1)

        exclusions = ContentExclusionsWindow(self.app)
        exclusions.genre_vars["ужасы"].set(True)
        exclusions.save()
        self.assertEqual(self.app.db.content_exclusions()["genre"], ["ужасы"])

        self.app.toggle_language()
        self.assertEqual(similar.find_button.cget("text"), "Find similar")
        self.assertIn("Actor:", similar.listbox.get(0))
        self.assertEqual(planner.heading.cget("text"), "Viewing plans")
        self.assertEqual(exclusions.save_button.cget("text"), "Save")

        similar.destroy()
        planner.destroy()
        exclusions.destroy()


if __name__ == "__main__":
    unittest.main()
