"""Tests for config lookup and persistence."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from movie_search.config import Config, _source_base_dir  # noqa: E402


class ConfigPathTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "Movie Finder"
        self.app_dir = self.root / "source" / "dist" / "Movie Finder"
        self.app_dir.mkdir(parents=True)
        self.local_path = self.app_dir / "config.json"
        self.parent_path = self.root / "config.json"
        self.alt_path = Path(self.temp_dir.name) / "profile" / "config.json"

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    @staticmethod
    def _write_config(path: Path, **values: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(values), encoding="utf-8")

    def _frozen_config(self) -> Config:
        with patch.object(sys, "frozen", True, create=True):
            return Config(self.local_path, alt_path=self.alt_path)

    def test_reads_config_from_enclosing_app_folder(self) -> None:
        self._write_config(self.parent_path, tmdb_api_key="parent-test-key")
        self._write_config(
            self.root / "source" / "config.json",
            tmdb_api_key="intermediate-test-key",
        )

        with patch.dict("os.environ", {"TMDB_API_KEY": ""}):
            config = self._frozen_config()

        self.assertEqual(config.api_key, "parent-test-key")
        self.assertEqual(config.parent_path, self.parent_path)

    def test_local_config_takes_priority_over_parent_config(self) -> None:
        self._write_config(self.parent_path, tmdb_api_key="parent-test-key")
        self._write_config(self.local_path, tmdb_api_key="local-test-key")

        with patch.dict("os.environ", {"TMDB_API_KEY": ""}):
            config = self._frozen_config()
            config.set("language", "en-US")

        self.assertEqual(config.api_key, "local-test-key")
        self.assertIsNone(config.parent_path)
        self.assertEqual(
            json.loads(self.local_path.read_text(encoding="utf-8"))["language"],
            "en-US",
        )
        self.assertEqual(
            json.loads(self.parent_path.read_text(encoding="utf-8"))["tmdb_api_key"],
            "parent-test-key",
        )

    def test_parent_config_remains_write_source_until_settings_change(self) -> None:
        self._write_config(
            self.parent_path, tmdb_api_key="parent-test-key", language="ru-RU"
        )

        with patch.dict("os.environ", {"TMDB_API_KEY": ""}):
            config = self._frozen_config()
            self.assertFalse(self.local_path.exists())
            config.set("language", "en-US")

        self.assertFalse(self.local_path.exists())
        self.assertEqual(
            json.loads(self.parent_path.read_text(encoding="utf-8"))["language"],
            "en-US",
        )

    def test_environment_key_overrides_config_key(self) -> None:
        self._write_config(self.parent_path, tmdb_api_key="file-test-key")

        with patch.dict("os.environ", {"TMDB_API_KEY": "env-test-key"}):
            config = self._frozen_config()
            self.assertEqual(config.api_key, "env-test-key")

    def test_profile_fallback_is_used_when_parent_config_is_invalid(self) -> None:
        self.parent_path.write_text("{", encoding="utf-8")
        self._write_config(self.alt_path, tmdb_api_key="profile-test-key")

        with patch.dict("os.environ", {"TMDB_API_KEY": ""}):
            config = self._frozen_config()

        self.assertEqual(config.api_key, "profile-test-key")

    def test_nested_source_uses_existing_app_data_and_config_root(self) -> None:
        source_root = self.root / "source"
        source_root.mkdir(parents=True, exist_ok=True)
        (self.root / "Movie Finder.exe").touch()

        self.assertEqual(_source_base_dir(source_root), self.root)

    def test_standalone_source_keeps_its_own_root(self) -> None:
        source_root = self.root / "standalone"
        source_root.mkdir()

        self.assertEqual(_source_base_dir(source_root), source_root)


if __name__ == "__main__":
    unittest.main()
