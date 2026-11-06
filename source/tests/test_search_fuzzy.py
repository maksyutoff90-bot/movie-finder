"""Tests for typo-tolerant search and its bounded candidate set."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.database import MovieDB  # noqa: E402


class FuzzySearchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "fuzzy.db")
        self.db.upsert_many([
            {
                "id": 1,
                "title": "Путешествие",
                "original_title": "Spirited Away",
                "year": 2001,
            },
            {"id": 2, "title": "Avatar", "year": 2009},
        ])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_typo_and_original_title_are_found(self) -> None:
        rows, total = self.db.search(title="Avatr")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["id"], 2)

        rows, total = self.db.search(title="Spirited Awy")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["id"], 1)

    def test_title_index_stays_updated_after_upsert(self) -> None:
        self.db.upsert_many([{"id": 2, "title": "New Name", "year": 2009}])
        rows, total = self.db.search(title="Avatr")
        self.assertEqual((rows, total), ([], 0))
        rows, total = self.db.search(title="New Nme")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["id"], 2)

    def test_fuzzy_candidates_are_capped_on_large_catalogs(self) -> None:
        self.db.upsert_many(
            {"id": 1000 + index, "title": "Common Name"}
            for index in range(650)
        )
        self.db.upsert_many(
            {"id": 10000 + index, "title": f"Catalog Entry {index:05d}"}
            for index in range(12000)
        )

        candidates = self.db._fuzzy_title_ids("Comon Name")
        rows, total = self.db.search(title="Comon Name", limit=600)

        self.assertLessEqual(len(candidates), 500)
        self.assertLessEqual(total, 500)
        self.assertEqual(total, len(rows))
        self.assertTrue(all(row["title"] == "Common Name" for row in rows))


if __name__ == "__main__":
    unittest.main()
