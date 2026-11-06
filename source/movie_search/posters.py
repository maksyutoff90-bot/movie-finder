"""Загрузка и кэширование постеров (локальные файлы + TMDb CDN)."""

from __future__ import annotations

import io
import os
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

import requests
from PIL import Image

TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
USER_AGENT = "MovieFinder/1.0 (personal offline app)"
MAX_POSTER_BYTES = 12 * 1024 * 1024

Image.MAX_IMAGE_PIXELS = 40_000_000

_tls = threading.local()

# Символы, которых не должно быть в имени файла: постеры приходят из импорта.
_BAD_NAME_CHARS = set('/\\:*?"<>|')


def _safe_file_name(value: str) -> str:
    """Оставляет только безопасное имя файла, иначе пустую строку.

    `poster_file` попадает в базу из импортированных наборов, поэтому путь
    вида `..\\..\\x.jpg` или `C:\\x.jpg` недопустим.
    """
    text = str(value or "").strip()
    if not text or "\x00" in text or any(char in _BAD_NAME_CHARS for char in text):
        return ""
    if text in (".", "..") or text.startswith("."):
        return ""
    return text


def _looks_like_image(response: requests.Response, payload: bytes) -> bool:
    """Отсекает HTML-страницы ошибок и слишком большие файлы до записи на диск."""
    if not 900 <= len(payload) <= MAX_POSTER_BYTES:
        return False
    content_type = (response.headers.get("Content-Type") or "").lower()
    if content_type and not content_type.startswith("image/"):
        return False
    try:
        with Image.open(io.BytesIO(payload)) as probe:
            probe.verify()
    except (OSError, ValueError):
        return False
    return True


def _session() -> requests.Session:
    session = getattr(_tls, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update({"User-Agent": USER_AGENT})
        _tls.session = session
    return session


class PosterCache:
    """Хранит постеры на диске и в памяти, отдаёт готовые миниатюры.

    `extra_folders` — каталоги только для чтения (например, постеры из комплекта),
    которые используются, если файла нет в основном каталоге.
    """

    def __init__(
        self,
        folder: str | Path,
        memory_limit: int = 220,
        extra_folders: list[str | Path] | None = None,
    ) -> None:
        self.folder = Path(folder)
        self.folder.mkdir(parents=True, exist_ok=True)
        self.extra_folders = [Path(item) for item in (extra_folders or []) if Path(item) != self.folder]
        self.memory_limit = memory_limit
        self._mem: OrderedDict[tuple[int, int, int], Image.Image] = OrderedDict()
        self._mem_lock = threading.Lock()
        self._file_locks: dict[str, threading.Lock] = {}
        self._file_locks_guard = threading.Lock()

    # ----------------------------------------------------------- служебное
    @staticmethod
    def file_name(movie: dict[str, Any]) -> str:
        name = _safe_file_name(movie.get("poster_file") or "")
        if name:
            return name
        source = _safe_file_name(movie.get("source") or "") or "x"
        return f"{source}_{int(movie.get('id') or 0)}.jpg"

    def path_for(self, movie: dict[str, Any]) -> Path:
        """Путь для записи (основной каталог)."""
        return self.folder / self.file_name(movie)

    def _candidates(self, movie: dict[str, Any]) -> list[Path]:
        name = self.file_name(movie)
        return [self.folder / name] + [extra / name for extra in self.extra_folders]

    def local_path(self, movie: dict[str, Any]) -> Path | None:
        for path in self._candidates(movie):
            try:
                if path.exists() and path.stat().st_size > 900:
                    return path
            except OSError:
                continue
        return None

    def _url_for(self, movie: dict[str, Any]) -> str | None:
        url = (movie.get("poster_url") or "").strip()
        if url:
            return url
        path = (movie.get("poster_path") or "").strip()
        if not path:
            return None
        if path.startswith("http"):
            return path
        return TMDB_IMAGE_BASE + path

    def _lock_for(self, key: str) -> threading.Lock:
        with self._file_locks_guard:
            lock = self._file_locks.get(key)
            if lock is None:
                lock = threading.Lock()
                self._file_locks[key] = lock
            return lock

    # --------------------------------------------------------- скачивание
    def ensure(self, movie: dict[str, Any], timeout: float = 20.0) -> Path | None:
        """Гарантирует наличие файла постера на диске (при необходимости скачивает)."""
        local = self.local_path(movie)
        if local:
            return local

        url = self._url_for(movie)
        if not url:
            return None

        target = self.path_for(movie)
        tmp = target.with_suffix(".part")
        lock = self._lock_for(target.name)
        with lock:
            local = self.local_path(movie)
            if local:
                return local
            try:
                resp = _session().get(url, timeout=timeout)
                resp.raise_for_status()
                payload = resp.content
                if not _looks_like_image(resp, payload):
                    return None
                tmp.write_bytes(payload)
                os.replace(tmp, target)
            except (requests.RequestException, OSError):
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                return None
        return target

    # ------------------------------------------------------------ картинки
    def image(
        self,
        movie: dict[str, Any],
        size: tuple[int, int],
        *,
        pad: bool = True,
        background: tuple[int, int, int] = (27, 31, 38),
    ) -> Image.Image | None:
        """Возвращает изображение нужного размера (с полями при pad=True)."""
        key = (int(movie.get("id") or 0), int(size[0]), int(size[1]))
        with self._mem_lock:
            cached = self._mem.get(key)
            if cached is not None:
                self._mem.move_to_end(key)
                return cached

        path = self.ensure(movie)
        if not path:
            return None
        try:
            with Image.open(path) as raw:
                img = raw.convert("RGB")
        except (OSError, ValueError):
            return None

        img.thumbnail(size, Image.LANCZOS)
        if pad:
            canvas = Image.new("RGB", size, background)
            offset = ((size[0] - img.width) // 2, (size[1] - img.height) // 2)
            canvas.paste(img, offset)
            img = canvas

        with self._mem_lock:
            self._mem[key] = img
            while len(self._mem) > self.memory_limit:
                self._mem.popitem(last=False)
        return img

    def placeholder(self, size: tuple[int, int]) -> Image.Image:
        """Заглушка «нет постера»."""
        from PIL import ImageDraw, ImageFont

        img = Image.new("RGB", size, (24, 27, 34))
        draw = ImageDraw.Draw(img)
        width, height = size
        draw.rectangle([6, 6, width - 6, height - 6], outline=(46, 52, 64), width=2)

        box_w, box_h = int(width * 0.34), int(height * 0.18)
        left = (width - box_w) // 2
        top = int(height * 0.38)
        draw.rectangle([left, top, left + box_w, top + box_h], outline=(58, 66, 80), width=2)
        for offset in (0.25, 0.5, 0.75):
            draw.line(
                [left + 4, top + box_h * offset, left + box_w - 4, top + box_h * offset],
                fill=(48, 55, 68),
                width=1,
            )

        try:
            font = ImageFont.truetype("segoeui.ttf", max(11, width // 13))
        except OSError:
            font = ImageFont.load_default()
        text = "нет постера"
        bbox = draw.textbbox((0, 0), text, font=font)
        draw.text(
            ((width - (bbox[2] - bbox[0])) / 2, top + box_h + 14),
            text,
            fill=(104, 114, 132),
            font=font,
        )
        return img
