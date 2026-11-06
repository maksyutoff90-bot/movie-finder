"""Guards against packaging or overwriting private app data."""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import build_exe  # noqa: E402


class BuildPackagingTests(unittest.TestCase):
    def test_existing_database_posters_and_config_stop_rebuild(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "Movie Finder"
            (output / "data" / "posters").mkdir(parents=True)
            (output / "data" / "movies.db").write_bytes(b"private")
            (output / "config.json").write_text("{}", encoding="utf-8")

            with self.assertRaises(SystemExit) as raised:
                build_exe.ensure_safe_output(output)

            self.assertIn("пользовательские данные", str(raised.exception))
            self.assertTrue((output / "data" / "movies.db").exists())
            self.assertTrue((output / "config.json").exists())

    def test_runtime_assets_copy_never_packages_data_or_secrets(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "Movie Finder"
            output.mkdir()
            readme = Path(temp_dir) / "README.md"
            readme.write_text("safe build", encoding="utf-8")

            build_exe.copy_runtime_assets(output, readme)

            self.assertEqual((output / "README.md").read_text(encoding="utf-8"), "safe build")
            self.assertFalse((output / "data").exists())
            self.assertFalse((output / "config.json").exists())


if __name__ == "__main__":
    unittest.main()
