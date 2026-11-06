"""Ссылки на карточку фильма: TMDb, IMDb, Кинопоиск, трейлер, «где смотреть».

Ссылки-поисковики работают всегда, без ключа. Если ключ TMDb задан, приложение
дополнительно спрашивает трейлер и легальные площадки (данные JustWatch через
TMDb) и подменяет кнопки на прямые ссылки.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus

from .tmdb_sync import TMDBClient, TMDBError


def tmdb_url(movie: dict[str, Any]) -> str | None:
    link = (movie.get("link") or "").strip()
    if "themoviedb.org" in link:
        return link
    movie_id = movie.get("id")
    if isinstance(movie_id, int) and movie_id > 0:
        return f"https://www.themoviedb.org/movie/{movie_id}"
    return None


def imdb_url(movie: dict[str, Any]) -> str | None:
    imdb_id = (movie.get("imdb_id") or "").strip()
    if imdb_id.startswith("tt"):
        return f"https://www.imdb.com/title/{imdb_id}/"
    return None


def wikipedia_url(movie: dict[str, Any]) -> str | None:
    link = (movie.get("link") or "").strip()
    return link if "wikipedia.org" in link else None


def kinopoisk_url(movie: dict[str, Any]) -> str:
    query = f"{movie.get('title') or ''} {movie.get('year') or ''}".strip()
    return f"https://www.kinopoisk.ru/index.php?kp_query={quote_plus(query)}"


def trailer_search_url(movie: dict[str, Any]) -> str:
    query = f"{movie.get('title') or ''} {movie.get('year') or ''} трейлер"
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def watch_search_url(movie: dict[str, Any]) -> str:
    query = quote_plus(str(movie.get("title") or ""))
    return f"https://www.justwatch.com/ru/%D0%BF%D0%BE%D0%B8%D1%81%D0%BA?q={query}"


def free_catalog_links(movie: dict[str, Any]) -> list[tuple[str, str]]:
    """Бесплатные легальные каталоги: поиск по названию фильма."""
    title = str(movie.get("title") or "")
    year = str(movie.get("year") or "")
    query = quote_plus(f"{title} {year}".strip())
    return [
        ("Смотрим (ВГТРК)", f"https://smotrim.ru/search?query={query}"),
        ("Мосфильм", f"https://www.youtube.com/results?search_query={quote_plus('Мосфильм ' + title)}"),
        ("RuTube", f"https://rutube.ru/search/?query={query}"),
        ("VK Видео", f"https://vk.com/video?q={query}"),
        ("Культура.РФ", f"https://www.culture.ru/search?q={query}"),
        ("Internet Archive", f"https://archive.org/search?query={query}&and[]=mediatype%3A%22movies%22"),
        ("YouTube", f"https://www.youtube.com/results?search_query={quote_plus(title + ' ' + year + ' фильм полностью')}"),
    ]


def fetch_providers(
    movie_id: int, api_key: str, regions: tuple[str, ...] = ("RU", "US", "GB", "DE")
) -> tuple[str, str, str | None] | None:
    """Площадки показа для одного фильма: (регион, «A, B», ссылка)."""
    if not api_key or not isinstance(movie_id, int) or movie_id <= 0:
        return None
    try:
        data = TMDBClient(api_key, "ru-RU").get(f"/movie/{movie_id}/watch/providers")
    except TMDBError:
        return None

    available = data.get("results") or {}
    for code in regions:
        regional = available.get(code) or {}
        names: list[str] = []
        for group in ("flatrate", "free", "ads", "rent", "buy"):
            for provider in regional.get(group) or []:
                name = provider.get("provider_name")
                if name and name not in names:
                    names.append(name)
        if names:
            return code, ", ".join(names[:6]), regional.get("link")
    return None


def fetch_extras(
    movie_id: int,
    api_key: str,
    regions: tuple[str, ...] = ("RU", "US", "GB", "DE"),
    timeout: float = 12.0,
) -> dict[str, Any]:
    """Трейлер и площадки из TMDb (данные JustWatch). Требует API-ключ.

    TMDb не отдаёт площадки для России, поэтому берём первый регион из списка,
    где они есть, и сообщаем его в поле `region`.
    """
    result: dict[str, Any] = {"trailer": None, "watch": None, "providers": [], "region": ""}
    if not api_key or not isinstance(movie_id, int) or movie_id <= 0:
        return result

    client = TMDBClient(api_key, "ru-RU")
    try:
        videos = client.get(f"/movie/{movie_id}/videos")
        for item in videos.get("results") or []:
            if item.get("site") == "YouTube" and item.get("type") in ("Trailer", "Teaser"):
                result["trailer"] = f"https://www.youtube.com/watch?v={item['key']}"
                break
    except (TMDBError, KeyError):
        pass

    try:
        data = client.get(f"/movie/{movie_id}/watch/providers")
        available = data.get("results") or {}
        for code in regions:
            regional = available.get(code) or {}
            names: list[str] = []
            for group in ("flatrate", "free", "ads", "rent", "buy"):
                for provider in regional.get(group) or []:
                    name = provider.get("provider_name")
                    if name and name not in names:
                        names.append(name)
            if names:
                result.update(watch=regional.get("link"), providers=names, region=code)
                break
        if not result["watch"]:
            for code in regions:
                link = (available.get(code) or {}).get("link")
                if link:
                    result.update(watch=link, region=code)
                    break
    except (TMDBError, KeyError):
        pass

    return result
