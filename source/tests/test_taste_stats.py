"""Tests for personal taste aggregates and their RU/EN presentation."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.database import MovieDB  # noqa: E402
from movie_search.ui import UI_TEXT_EN, MovieApp, MovieCard, TasteStatsWindow  # noqa: E402


class TasteStatsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "taste.db")
        self.db.upsert_many([
            {"id": 1, "title": "Drama one", "year": 2001, "genres": "драма,комедия"},
            {"id": 2, "title": "Drama two", "year": 2010, "genres": "драма"},
            {"id": 3, "title": "Unrated", "year": 2020, "genres": "ужасы"},
        ])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_stats_aggregate_only_personal_state_and_view_activity(self) -> None:
        self.db.set_personal_state(1, watched=True, personal_rating=9)
        self.db.set_personal_state(2, watched=False, personal_rating=7)
        self.db.toggle_bookmark(3)
        self.db.record_view(1)

        stats = self.db.taste_stats()

        self.assertEqual(stats["watched"], 1)
        self.assertEqual(stats["rated"], 2)
        self.assertEqual(stats["average_rating"], 8.0)
        self.assertEqual(stats["bookmarked"], 1)
        self.assertEqual(stats["history_count"], 1)
        self.assertEqual(stats["rating_distribution"], [
            {"rating": 7, "count": 1},
            {"rating": 9, "count": 1},
        ])
        self.assertEqual(stats["favorite_genres"][0]["genre"], "драма")
        self.assertEqual(stats["years"], [
            {"year": 2010, "count": 1},
            {"year": 2001, "count": 1},
        ])
        self.assertEqual(stats["activity_by_month"][0]["count"], 1)

    def test_empty_database_aggregates_have_explicit_empty_values(self) -> None:
        stats = self.db.taste_stats()
        self.assertIsNone(stats["average_rating"])
        self.assertEqual(stats["watched"], 0)
        self.assertEqual(stats["favorite_genres"], [])
        self.assertEqual(stats["years"], [])
        self.assertEqual(stats["activity_by_month"], [])

    def test_stats_window_has_localized_empty_and_error_states(self) -> None:
        class FakeText:
            value = ""

            def configure(self, **_kwargs) -> None:
                pass

            def delete(self, *_args) -> None:
                self.value = ""

            def insert(self, _index: str, value: str) -> None:
                self.value = value

        class FakeApp:
            is_english = True

            def _text(self, russian: str, english: str) -> str:
                return english if self.is_english else russian

            class db:
                @staticmethod
                def taste_stats():
                    return {
                        "watched": 0, "rated": 0, "average_rating": None,
                        "bookmarked": 0, "history_count": 0,
                        "rating_distribution": [], "favorite_genres": [],
                        "years": [], "activity_by_month": [],
                    }

        empty_window = SimpleNamespace(app=FakeApp(), text=FakeText(), title=lambda _value: None)
        TasteStatsWindow.refresh(empty_window)
        self.assertIn("No personal data yet", empty_window.text.value)
        empty_window.app.is_english = False
        TasteStatsWindow.refresh(empty_window)
        self.assertIn("Пока нет личных данных", empty_window.text.value)

        class BrokenDB:
            @staticmethod
            def taste_stats():
                raise RuntimeError("offline")

        FakeApp.db = BrokenDB
        error_window = SimpleNamespace(app=FakeApp(), text=FakeText(), title=lambda _value: None)
        TasteStatsWindow.refresh(error_window)
        self.assertIn("Could not load statistics", error_window.text.value)
        self.assertIn("offline", error_window.text.value)

    def test_recommendation_explanations_and_backup_labels_have_translations(self) -> None:
        reason = {"type": "genre", "value": "драма"}
        russian = MovieCard._recommendation_text(SimpleNamespace(
            movie={"recommendation_reasons": [reason]}, language="ru-RU"
        ))
        english = MovieCard._recommendation_text(SimpleNamespace(
            movie={"recommendation_reasons": [reason]}, language="en-US"
        ))
        self.assertIn("любимый жанр", russian)
        self.assertIn("favorite genre", english)
        self.assertEqual(UI_TEXT_EN["Просмотрено"], "Watched")
        self.assertEqual(UI_TEXT_EN["Любимые жанры"], "Favorite genres")
        russian_backup = MovieApp._backup_reminder_text(SimpleNamespace(
            _text=lambda russian, _english: russian
        ))
        english_backup = MovieApp._backup_reminder_text(SimpleNamespace(
            _text=lambda _russian, english: english
        ))
        self.assertIn("Резервная копия", russian_backup)
        self.assertIn("Backup reminder", english_backup)
        self.assertIn("ratings", english_backup)
        self.assertIn("saved filters", UI_TEXT_EN[
            "Просмотренное, личные оценки, закладки и сохранённые подборки. "
            "Каталог, постеры и ключи не экспортируются. Регулярно храните JSON-копию отдельно."
        ])


if __name__ == "__main__":
    unittest.main()
