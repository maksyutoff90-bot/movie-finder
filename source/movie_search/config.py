"""Пути приложения и пользовательские настройки (config.json)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any


def _source_base_dir(source_root: Path) -> Path:
    """Uses the installed app folder when its source tree is nested beside the EXE."""
    app_root = source_root.parent
    if (
        source_root.name.casefold() == "source"
        and app_root.name.casefold() == "movie finder"
        and (app_root / "Movie Finder.exe").is_file()
    ):
        return app_root
    return source_root


def _base_dir() -> Path:
    """Resolve data/config beside the EXE, or beside standalone source code."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return _source_base_dir(Path(__file__).resolve().parent.parent)


def is_writable(folder: Path) -> bool:
    """Проверяет, можно ли писать в каталог (создаёт и удаляет пробный файл)."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


ROOT = _base_dir()
BUNDLED_DATA_DIR = ROOT / "data"  # база и постеры, которые идут в комплекте
BUNDLED_POSTER_DIR = BUNDLED_DATA_DIR / "posters"


def _fallback_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "Movie Finder" / "data"


def _parent_config_path(path: Path) -> Path | None:
    """Find the config beside the enclosing Movie Finder app folder."""
    for ancestor in path.parent.resolve().parents:
        if ancestor.name.casefold() == "movie finder":
            candidate = ancestor / "config.json"
            return candidate if candidate.is_file() else None
    return None


def fallback_data_dir() -> Path:
    """Каталог в профиле пользователя — используется, если рядом писать нельзя."""
    return _fallback_dir()


def _resolve_data_dir(primary: Path) -> Path:
    """Оставлено для совместимости: база всегда открывается из комплектной папки.

    Если писать туда нельзя, приложение само переносит её в профиль пользователя
    (MovieApp._relocate_database) — вместе со всеми уже загруженными фильмами.
    """
    return primary


DATA_DIR = BUNDLED_DATA_DIR
POSTER_DIR = DATA_DIR / "posters"
DB_PATH = DATA_DIR / "movies.db"
CONFIG_PATH = ROOT / "config.json"
ALT_CONFIG_PATH = _fallback_dir().parent / "config.json"

DEFAULT_CONFIG: dict[str, Any] = {
    "tmdb_api_key": "",
    "language": "ru-RU",
    "ui_language": "ru-RU",
    "pages_per_year": 3,
    "min_vote_count": 40,
    "window_geometry": "",
    "player_path": "",
    "player_name": "",
    "movies_folder": "",
}


class Config:
    """Простой JSON-конфиг с доступом по ключу.

    Читается рядом с программой; вложенная frozen-сборка может использовать
    конфиг в корне приложения. Если рядом писать нельзя — используется профиль.
    """

    def __init__(
        self, path: Path = CONFIG_PATH, *, alt_path: Path | None = None
    ) -> None:
        self.path = Path(path)
        self.alt_path = Path(alt_path) if alt_path is not None else ALT_CONFIG_PATH
        self.parent_path = (
            _parent_config_path(self.path)
            if getattr(sys, "frozen", False) and not self.path.exists()
            else None
        )
        self._loaded_path: Path | None = None
        self.data: dict[str, Any] = dict(DEFAULT_CONFIG)
        self.load()

    def load(self) -> None:
        candidates = [self.path]
        if self.parent_path is not None:
            candidates.append(self.parent_path)
        candidates.append(self.alt_path)
        for candidate in candidates:
            try:
                if not candidate.exists():
                    continue
                # utf-8-sig: файл могли сохранить в Блокноте с BOM — без этого
                # весь конфиг молча игнорировался вместе с ключом и языком.
                raw = json.loads(candidate.read_text(encoding="utf-8-sig"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(raw, dict):
                for key, value in raw.items():
                    if key in DEFAULT_CONFIG:
                        self.data[key] = value
                self._loaded_path = candidate
                return

    def save(self) -> bool:
        """Пишет конфиг. False — ни один путь не оказался доступен для записи."""
        payload = json.dumps(self.data, ensure_ascii=False, indent=2)
        if self._loaded_path == self.parent_path and self.parent_path is not None:
            candidates = (self.parent_path, self.alt_path)
        else:
            candidates = (self.path, self.alt_path)
        tried: set[Path] = set()
        for candidate in candidates:
            if candidate in tried:
                continue
            tried.add(candidate)
            try:
                candidate.parent.mkdir(parents=True, exist_ok=True)
                candidate.write_text(payload, encoding="utf-8")
                return True
            except OSError:
                continue
        return False

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)

    def set(self, key: str, value: Any) -> bool:
        self.data[key] = value
        return self.save()

    @property
    def api_key(self) -> str:
        """Ключ TMDb: переменная окружения имеет приоритет над файлом."""
        return (os.environ.get("TMDB_API_KEY") or self.data.get("tmdb_api_key") or "").strip()

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def language(self) -> str:
        return str(self.data.get("language") or "ru-RU")

    @property
    def pages_per_year(self) -> int:
        try:
            return max(1, min(10, int(self.data.get("pages_per_year", 3))))
        except (TypeError, ValueError):
            return 3

    @property
    def min_vote_count(self) -> int:
        try:
            return max(0, int(self.data.get("min_vote_count", 40)))
        except (TypeError, ValueError):
            return 40
