"""Регрессии P1: целостность при дедупликации, транзакции, LIKE и пути.

Покрывают:
  * перенос личного состояния на двойника при удалении офлайн-записи;
  * `%` и `_` в поиске ищутся буквально, а не как маски;
  * ошибка валидации не оставляет открытую транзакцию;
  * сбой переоткрытия базы даёт `DatabaseError`, а не `AttributeError`;
  * `poster_file` из импорта не выводит запись за пределы папки постеров;
  * `Config.save()` сообщает о неудаче, а `set()` возвращает результат;
  * недавно проверенные коллекции пропускаются автопроверкой.
"""

from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import Config  # noqa: E402
from movie_search.database import DatabaseError, MovieDB  # noqa: E402
from movie_search.franchises import check_watchlist_sequels  # noqa: E402
from movie_search.posters import PosterCache  # noqa: E402


class WikiMergeTests(unittest.TestCase):
    """Личные отметки не должны исчезать при удалении офлайн-дубля."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "merge.db")
        self.db.upsert_many([
            {
                "id": 900,
                "title": "Матрица",
                "year": 1999,
                "source": "wiki",
                "overview": "Описание из Википедии.",
                "poster_file": "wiki_555.jpg",
                "poster_url": "https://wiki/555.jpg",
            },
            {
                "id": 603,
                "title": "Матрица",
                "year": 1999,
                "source": "tmdb",
                "overview": "",
            },
        ])
        self.db.set_personal_state(900, watched=True, personal_rating=9)
        self.db.toggle_bookmark(900)
        self.db.set_watchlist(900, priority=5, note="в выходные")
        self.db.record_view(900)
        self.db.add_plan(900, "2026-12-31", "смотреть")
        self.db.set_providers([(900, "RU", "Okko", None)])
        self.db.set_watch_links([(900, "Мосфильм", "https://mosfilm/555", "Матрица")])
        self.db.set_cast([(900, "Киану Ривз", 0)])
        self.db.set_keywords([(900, "матрица")])
        self.db.save_sequel_check(900, 42)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_state_moves_to_twin(self) -> None:
        self.assertEqual(self.db.remove_wiki_duplicates(), 1)
        twin = self.db.get(603)
        self.assertEqual(twin["watched"], 1)
        self.assertEqual(twin["personal_rating"], 9)
        self.assertEqual(twin["poster_file"], "wiki_555.jpg")
        self.assertEqual(twin["overview"], "Описание из Википедии.")
        self.assertTrue(self.db.is_bookmarked(603))
        entry = self.db.watchlist_entry(603)
        self.assertEqual((entry["priority"], entry["note"]), (5, "в выходные"))
        self.assertEqual(self.db.watch_link(603)["url"], "https://mosfilm/555")
        self.assertEqual(self.db.providers_of(603)["names"], "Okko")
        self.assertIn("Киану Ривз", self.db.cast_of(603))
        self.assertEqual(self.db.count(), 1)

    def test_dependent_rows_of_wiki_record_are_removed(self) -> None:
        self.db.remove_wiki_duplicates()
        for table, column in (
            ("bookmarks", "movie_id"),
            ("watchlist", "movie_id"),
            ("history", "movie_id"),
            ("viewing_plans", "movie_id"),
            ("providers", "movie_id"),
            ("watch_links", "movie_id"),
            ("movie_cast", "movie_id"),
            ("movie_keywords", "movie_id"),
            ("movie_title_grams", "movie_id"),
            ("sequel_monitor", "anchor_movie_id"),
        ):
            with self.db._lock:
                left = self.db._conn.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (900,)
                ).fetchone()[0]
            self.assertEqual(left, 0, f"остались строки в {table}")


class EscapeLikeTests(unittest.TestCase):
    """Спецсимволы LIKE не должны превращаться в маски."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "like.db")
        self.db.upsert_many([
            {"id": 1, "title": "100% волк"},
            {"id": 2, "title": "Драма"},
            {"id": 3, "title": "Комедия"},
        ])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_percent_is_literal(self) -> None:
        # До исправления «%» возвращал все три фильма, теперь — только с «%».
        _, total = self.db.search(title="%")
        self.assertEqual(total, 1)
        rows, total = self.db.search(title="100%")
        self.assertEqual(total, 1)
        self.assertEqual(rows[0]["id"], 1)

    def test_underscore_is_literal(self) -> None:
        _, total = self.db.search(title="_")
        self.assertEqual(total, 0)


class TransactionTests(unittest.TestCase):
    """Ошибка валидации не должна оставлять открытую транзакцию."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "tx.db")
        self.db.upsert_many([{"id": 1, "title": "Фильм"}])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_failed_update_does_not_block_next_transaction(self) -> None:
        with self.assertRaises(ValueError):
            self.db.update_plan(999, "2026-01-01")  # плана нет — ValueError
        # До исправления здесь падало «cannot start a transaction within a transaction».
        self.db.set_content_exclusions(genres=["драма"])
        self.assertEqual(self.db.content_exclusions()["genre"], ["драма"])

    def test_duplicate_plan_does_not_block_next_transaction(self) -> None:
        self.db.add_plan(1, "2026-02-01")
        with self.assertRaises(ValueError):
            self.db.add_plan(1, "2026-02-01")
        self.db.set_content_exclusions(genres=["ужасы"])
        self.assertEqual(self.db.content_exclusions()["genre"], ["ужасы"])


class ReopenFailureTests(unittest.TestCase):
    """Сбой переоткрытия базы не должен превращаться в AttributeError."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "reopen.db")
        self.db.upsert_many([{"id": 1, "title": "Фильм"}])

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_reopen_failure_is_reported_as_database_error(self) -> None:
        def broken_connect():
            raise sqlite3.OperationalError("database is locked")

        def failing_action():
            raise sqlite3.OperationalError("database is locked")

        self.db._connect = broken_connect  # type: ignore[method-assign]
        with self.assertRaises(DatabaseError):
            self.db._call(failing_action, attempts=1)

        # Прежнее соединение осталось рабочим.
        del self.db._connect
        self.assertEqual(self.db.count(), 1)


class PosterNameTests(unittest.TestCase):
    """`poster_file` из импортированного набора не должен быть путём."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp_dir.name) / "posters"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_path_like_names_are_replaced(self) -> None:
        for bad in (r"..\..\evil.jpg", "../../evil.jpg", r"C:\Windows\x.jpg", ".."):
            name = PosterCache.file_name(
                {"id": 5, "poster_file": bad, "source": "tmdb"}
            )
            self.assertEqual(name, "tmdb_5.jpg", bad)
        self.assertEqual(
            PosterCache.file_name({"id": 5, "poster_file": "wiki_5.jpg"}), "wiki_5.jpg"
        )

    def test_path_for_stays_inside_poster_folder(self) -> None:
        cache = PosterCache(self.folder)
        path = cache.path_for({"id": 5, "poster_file": r"..\..\evil.jpg"})
        self.assertEqual(path.parent.resolve(), self.folder.resolve())


class ConfigSaveTests(unittest.TestCase):
    """`Config.save()` сообщает о неудаче, а не молчит."""

    def test_unwritable_path_returns_false(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            blocker = Path(temp) / "file.txt"
            blocker.write_text("x", encoding="utf-8")
            config = Config(
                blocker / "config.json", alt_path=blocker / "alt" / "config.json"
            )
            self.assertFalse(config.set("language", "en-US"))
            self.assertEqual(config.get("language"), "en-US")  # в памяти осталось

    def test_writable_alt_path_returns_true(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            blocker = Path(temp) / "file.txt"
            blocker.write_text("x", encoding="utf-8")
            alt = Path(temp) / "profile" / "config.json"
            config = Config(blocker / "config.json", alt_path=alt)
            self.assertTrue(config.set("language", "en-US"))
            self.assertTrue(alt.exists())


class ConfigBomTests(unittest.TestCase):
    """Конфиг с BOM (сохранён в Блокноте) должен читаться, а не игнорироваться."""

    def test_config_with_bom_is_read(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "config.json"
            path.write_text(
                '\ufeff{"ui_language": "en-US", "tmdb_api_key": "test-key"}',
                encoding="utf-8",
            )
            config = Config(path, alt_path=Path(temp) / "alt.json")
            with patch.dict("os.environ", {"TMDB_API_KEY": ""}):
                self.assertEqual(config.get("ui_language"), "en-US")
                self.assertEqual(config.api_key, "test-key")


class SequelTtlTests(unittest.TestCase):
    """Автопроверка не должна опрашивать TMDb заново в тот же день."""

    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = MovieDB(Path(self.temp_dir.name) / "sequel.db")
        self.db.upsert_many([{"id": 10, "title": "Фильм"}])
        self.db.set_watchlist(10)
        self.db.save_sequel_check(10, None)

    def tearDown(self) -> None:
        self.db.close()
        self.temp_dir.cleanup()

    def test_recent_check_is_skipped_and_manual_check_is_not(self) -> None:
        calls: list[int] = []

        class FakeClient:
            def __init__(self, *_args, **_kwargs) -> None:
                pass

            def movie_details(self, movie_id: int) -> dict:
                calls.append(movie_id)
                return {}

        factory = lambda key, language: FakeClient(key, language)  # noqa: E731

        auto = check_watchlist_sequels(
            self.db, "key", client_factory=factory, recheck_after_hours=24
        )
        self.assertEqual(auto["skipped"], 1)
        self.assertEqual(calls, [])

        manual = check_watchlist_sequels(
            self.db, "key", client_factory=factory, recheck_after_hours=0
        )
        self.assertEqual(manual["checked"], 1)
        self.assertEqual(calls, [10])


if __name__ == "__main__":
    unittest.main()
