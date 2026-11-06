"""Поиск локальных файлов фильмов и сопоставление их с базой.

Пользователь указывает папку, приложение разбирает имена файлов
(«Название (2010) 1080p.mkv»), сопоставляет с фильмами по названию и году
и запоминает путь — после этого в окне фильма появляется кнопка «Смотреть».
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Callable, Iterable

from .database import MovieDB

VIDEO_EXTENSIONS = {
    ".mkv", ".mp4", ".avi", ".wmv", ".mov", ".m4v", ".ts", ".m2ts",
    ".mpg", ".mpeg", ".webm", ".flv", ".ogm", ".divx",
}

# Теги релиза, которые не относятся к названию.
JUNK = {
    "1080p", "1080i", "720p", "2160p", "480p", "4k", "uhd", "hdr", "hdr10",
    "bdrip", "brrip", "bdremux", "webrip", "web-dl", "webdl", "web", "hdrip",
    "dvdrip", "dvdscr", "dvd", "ts", "tc", "cam", "bluray", "blu-ray", "remux",
    "x264", "x265", "h264", "h265", "hevc", "avc", "xvid", "divx", "av1",
    "aac", "ac3", "dts", "ddp", "dd5", "atmos", "truehd", "flac", "mp3",
    "rus", "eng", "ukr", "jpn", "kor", "fre", "ger", "ita", "spa",
    "лицензия", "дубляж", "многоголосый", "одноголосый", "оригинал", "субтитры",
    "sdr", "10bit", "8bit", "proper", "repack", "extended", "remastered",
}

YEAR_RE = re.compile(r"(?:^|[\s._\-(\[])((?:18|19|20)\d{2})(?:[\s._\-)\]]|$)")
BRACKETS_RE = re.compile(r"\[[^\]]*\]|\([^)]*\)")
CLEAN_RE = re.compile(r"[^0-9a-zа-яё]+")


def normalize(text: str) -> str:
    text = (text or "").lower().replace("ё", "е")
    text = CLEAN_RE.sub(" ", text)
    return " ".join(text.split())


def parse_filename(path: Path) -> tuple[str, int | None]:
    """'Начало.2010.1080p.BDRip.mkv' -> ('Начало', 2010)."""
    stem = path.stem
    year: int | None = None
    match = YEAR_RE.search(stem)
    if match:
        year = int(match.group(1))
        title_part = stem[: match.start()]
    else:
        title_part = stem

    title_part = BRACKETS_RE.sub(" ", title_part)
    words = [
        word
        for word in re.split(r"[\s._\-]+", title_part)
        if word and word.lower() not in JUNK and not word.isdigit()
    ]
    return " ".join(words).strip(), year


def iter_video_files(folder: Path, recursive: bool = True) -> Iterable[Path]:
    pattern = "**/*" if recursive else "*"
    for path in folder.glob(pattern):
        if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
            yield path


def match_files(
    db: MovieDB,
    folder: str | Path,
    recursive: bool = True,
    progress: Callable[[int, int], None] | None = None,
) -> dict:
    """Сопоставляет файлы в папке с фильмами базы и сохраняет пути."""
    root = Path(folder)
    if not root.exists():
        return {"error": f"Папка не найдена: {root}", "matched": 0, "total": 0, "unmatched": []}

    files = list(iter_video_files(root, recursive))
    if not files:
        return {"error": "В папке нет видеофайлов", "matched": 0, "total": 0, "unmatched": []}

    by_title_year: dict[tuple[str, int], int] = {}
    by_title: dict[str, list[tuple[int, int]]] = {}
    for movie_id, title, original_title, year in db.titles_index():
        # Файлы могут быть названы и по-русски, и по-английски — индексируем оба.
        for name in {normalize(title), normalize(original_title)}:
            if not name:
                continue
            if year:
                by_title_year.setdefault((name, year), movie_id)
            by_title.setdefault(name, []).append((movie_id, year))

    pairs: list[tuple[str, int]] = []
    unmatched: list[str] = []
    seen: set[int] = set()

    for index, file in enumerate(files, 1):
        file_title, file_year = parse_filename(file)
        key = normalize(file_title)
        match_id: int | None = None
        if key and file_year:
            match_id = (
                by_title_year.get((key, file_year))
                or by_title_year.get((key, file_year + 1))
                or by_title_year.get((key, file_year - 1))
            )
        if match_id is None and key:
            candidates = by_title.get(key) or []
            # Только если название однозначно (иначе легко перепутать ремейки).
            if len(candidates) == 1:
                match_id = candidates[0][0]
        if match_id is not None and match_id not in seen:
            seen.add(match_id)
            pairs.append((str(file), match_id))
        else:
            unmatched.append(file.name)
        if progress:
            progress(index, len(files))

    if pairs:
        db.set_file_paths(pairs)

    return {
        "error": None,
        "matched": len(pairs),
        "total": len(files),
        "unmatched": unmatched,
        "folder": str(root),
    }
