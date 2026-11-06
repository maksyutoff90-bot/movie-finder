"""Focused tests for thematic categories, SQL search, and bilingual labels."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.const import (  # noqa: E402
    CATEGORY_FILTERS,
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    category_label,
)
from movie_search.database import MovieDB  # noqa: E402


class CategoryFilterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "categories.db")
        self.db.upsert_many(
            [
                {
                    "id": 1,
                    "title": "Сигнал с неба",
                    "original_title": "Sky Signal",
                    "overview": "НЛО замечено над городом.",
                    "genres": "драма",
                },
                {
                    "id": 2,
                    "title": "Night Visitors",
                    "genres": "фантастика",
                },
                {
                    "id": 3,
                    "title": "Midnight Fever",
                    "genres": "ужасы",
                },
                {
                    "id": 4,
                    "title": "The Quiet Machine",
                    "genres": "драма",
                },
                {
                    "id": 5,
                    "title": "A Family Drama",
                    "genres": "ужасы",
                },
                {
                    "id": 6,
                    "title": "The Visitors",
                    "original_title": "Extraterrestrial Encounter",
                },
                {
                    "id": 7,
                    "title": "UFO Archive",
                },
            ]
        )
        self.db.set_english_overview(
            2, "An unidentified flying object appears."
        )
        self.db.set_keywords(
            [
                (3, "Zombie outbreak"),
                (4, "artificial intelligence"),
            ]
        )

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def ids_for(self, category: str, **filters: object) -> set[int]:
        rows, _ = self.db.search(category=category, limit=100, **filters)
        return {int(row["id"]) for row in rows}

    def test_existing_and_new_topics_classify_from_stored_metadata(self) -> None:
        self.assertEqual(self.ids_for("aliens"), {1, 2, 6, 7})
        self.assertEqual(self.ids_for("zombies"), {3})
        self.assertEqual(self.ids_for("ai_robots"), {4})

    def test_topic_and_genre_filters_are_combined(self) -> None:
        self.assertEqual(self.ids_for("aliens", genre="драма"), {1})
        self.assertEqual(self.ids_for("aliens", genre="ужасы"), set())

    def test_theme_filter_does_not_infer_tags_from_a_broad_genre(self) -> None:
        self.assertEqual(self.ids_for("zombies"), {3})
        self.assertNotIn(5, self.ids_for("zombies"))

    def test_new_topics_classify_from_matching_keywords(self) -> None:
        examples = {
            "disasters": "earthquake",
            "vampires": "vampire",
            "ghosts": "poltergeist",
            "witchcraft": "witchcraft",
            "time_travel": "time travel",
            "ai_robots": "android",
            "heists": "bank heist",
            "spies": "espionage",
            "martial_arts": "kung fu",
            "sports": "ice hockey",
            "pirates": "pirate ship",
            "revenge": "vengeance",
            "mythology": "norse mythology",
            "monsters": "kaiju",
        }
        self.db.upsert_many(
            [
                {"id": 100 + index, "title": f"Film {category}"}
                for index, category in enumerate(examples)
            ]
        )
        self.db.set_keywords(
            [
                (100 + index, keyword)
                for index, keyword in enumerate(examples.values())
            ]
        )
        for index, category in enumerate(examples):
            with self.subTest(category=category):
                expected = {100 + index}
                if category == "ai_robots":
                    expected.add(4)
                self.assertEqual(self.ids_for(category), expected)

    def test_category_labels_are_available_in_both_languages(self) -> None:
        self.assertEqual(set(CATEGORY_ORDER), set(CATEGORY_FILTERS))
        self.assertTrue(set(CATEGORY_FILTERS).issubset(CATEGORY_LABELS))
        self.assertEqual(
            category_label("aliens"),
            "Тема · НЛО и пришельцы",
        )
        self.assertEqual(
            category_label("aliens", english=True),
            "Theme · UFOs & aliens",
        )
        self.assertEqual(
            category_label("zombies", english=True),
            "Theme · Zombies & outbreaks",
        )
        self.assertEqual(
            category_label("time_travel"),
            "Тема · Путешествия во времени",
        )
        self.assertEqual(
            category_label("time_travel", english=True),
            "Theme · Time travel",
        )


if __name__ == "__main__":
    unittest.main()
