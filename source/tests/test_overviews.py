"""Focused tests for localized movie descriptions and their independent cache."""

from __future__ import annotations

import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.database import MovieDB  # noqa: E402
from movie_search.ui import DetailWindow, MovieApp, MovieCard  # noqa: E402


class OverviewText:
    def __init__(self) -> None:
        self.value = ""

    def configure(self, **_kwargs) -> None:
        pass

    def delete(self, *_args) -> None:
        self.value = ""

    def insert(self, _index: str, text: str) -> None:
        self.value = text


class OverviewTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "overviews.db")
        self.db.upsert_many(
            [
                {
                    "id": 1,
                    "title": "Сигнал с неба",
                    "overview": "Русское описание фильма.",
                    "source": "tmdb",
                }
            ]
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_english_cache_does_not_replace_russian_overview(self) -> None:
        self.db.set_english_overview(1, "The English movie description.")

        movie = self.db.get(1)
        self.assertEqual(movie["overview"], "Русское описание фильма.")
        self.assertEqual(movie["overview_en"], "The English movie description.")
        self.assertEqual(movie["overview_en_checked"], 1)

        self.db.set_english_overview(1, None)
        movie = self.db.get(1)
        self.assertEqual(movie["overview"], "Русское описание фильма.")
        self.assertIsNone(movie["overview_en"])
        self.assertEqual(movie["overview_en_checked"], 1)

    def test_cards_never_use_russian_text_as_english_fallback(self) -> None:
        movie = {
            "overview": "Русское описание фильма.",
            "overview_en_checked": 1,
        }

        card = SimpleNamespace(movie=movie, language="en-US")
        self.assertEqual(
            MovieCard._overview_text(card),
            "No English description available.",
        )

        movie["overview_en_checked"] = 0
        movie["_english_api_available"] = False
        self.assertEqual(
            MovieCard._overview_text(card),
            "Add a TMDb API key to load English descriptions.",
        )

        movie["overview_en"] = "The English movie description."
        self.assertEqual(
            MovieCard._overview_text(card),
            "The English movie description.",
        )

    def test_open_detail_refreshes_in_each_language_without_fallback(self) -> None:
        movie = {
            "overview": "Русское описание фильма.",
            "overview_en": "The English movie description.",
        }
        app = SimpleNamespace(is_english=True, cfg=SimpleNamespace(api_key="key"))
        app.localized_overview = lambda row: MovieApp.localized_overview(app, row)
        detail = SimpleNamespace(
            text=OverviewText(),
            app=app,
            movie=movie,
            winfo_exists=lambda: 1,
        )

        DetailWindow.refresh_overview(detail)
        self.assertEqual(detail.text.value, "The English movie description.")

        app.is_english = False
        DetailWindow.refresh_overview(detail)
        self.assertEqual(detail.text.value, "Русское описание фильма.")

        app.is_english = True
        movie["overview_en"] = None
        movie["overview_en_checked"] = 1
        DetailWindow.refresh_overview(detail)
        self.assertEqual(detail.text.value, "No English description available.")

    def test_missing_api_key_has_explicit_english_state(self) -> None:
        app = SimpleNamespace(is_english=True, cfg=SimpleNamespace(api_key=""))
        self.assertEqual(
            MovieApp.localized_overview(app, {"overview": "Русский текст."}),
            "Add a TMDb API key in Settings to load English descriptions.",
        )

    def test_language_toggle_fetches_already_open_details(self) -> None:
        movie = {"id": 1}
        window = SimpleNamespace(movie=movie, winfo_exists=lambda: 1)

        class FakeConfig:
            def __init__(self) -> None:
                self.saved = {}

            def set(self, key: str, value: str) -> None:
                self.saved[key] = value

        class FakeApp:
            ui_language = "ru-RU"
            is_english = property(lambda self: self.ui_language.startswith("en"))

            def __init__(self) -> None:
                self.cfg = FakeConfig()
                self._detail_windows = [window]
                self.fetches = []

            def _apply_language(self) -> None:
                pass

            def _refresh_stats(self) -> None:
                pass

            def _fetch_english_overviews(self, movies) -> None:
                self.fetches.extend(movies)

            def search(self) -> None:
                pass

        app = FakeApp()
        MovieApp.set_ui_language(app, "en-US")

        self.assertEqual(app.cfg.saved["ui_language"], "en-US")
        self.assertEqual(app.fetches, [movie])

    @patch("movie_search.ui.TMDBClient")
    def test_english_requests_use_en_us(self, client_type) -> None:
        submitted = []
        movie = {"id": 1, "overview_en_checked": 0}
        app = SimpleNamespace(
            _overview_pending=set(),
            _overview_pending_lock=threading.Lock(),
            cfg=SimpleNamespace(api_key="test-key"),
            overview_pool=SimpleNamespace(submit=lambda *args: submitted.append(args)),
            _english_api_available=False,
            _fetch_english_overview=lambda *_args: None,
        )

        MovieApp._fetch_english_overviews(app, [movie])

        client_type.assert_called_once_with("test-key", "en-US")
        self.assertEqual(len(submitted), 1)
        self.assertIs(submitted[0][1], client_type.return_value)


if __name__ == "__main__":
    unittest.main()
