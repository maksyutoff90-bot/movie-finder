"""Verified franchise ordering and watchlist sequel checks using TMDb."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any, Callable

from .database import MovieDB
from .tmdb_sync import TMDBClient


def _positive_id(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError):
        return None
    return result if result > 0 else None


def _verified_release_date(value: Any) -> str | None:
    release_date = str(value or "").strip()
    try:
        parsed = date.fromisoformat(release_date)
    except ValueError:
        return None
    return release_date if parsed.isoformat() == release_date else None


def franchise_order(
    db: MovieDB, client: TMDBClient, movie_id: int
) -> dict[str, Any] | None:
    """Returns TMDb collection parts in release-date order, or None if unverified."""
    details = client.movie_details(movie_id)
    collection = details.get("belongs_to_collection")
    collection_id = _positive_id(collection.get("id")) if isinstance(collection, dict) else None
    if collection_id is None:
        return None

    collection_details = client.collection_details(collection_id)
    parts_by_id: dict[int, dict[str, Any]] = {}
    for part in collection_details.get("parts") or []:
        if not isinstance(part, dict):
            continue
        part_id = _positive_id(part.get("id"))
        title = str(part.get("title") or part.get("name") or "").strip()
        if part_id is None or not title:
            continue
        release_date = _verified_release_date(part.get("release_date"))
        local = db.get(part_id)
        parts_by_id[part_id] = {
            "id": part_id,
            "title": title,
            "release_date": release_date,
            "year": (
                int(release_date[:4])
                if release_date and release_date[:4].isdigit()
                else None
            ),
            "watched": bool(local and local.get("watched")),
            "in_catalog": local is not None,
            "url": f"https://www.themoviedb.org/movie/{part_id}",
        }

    parts = sorted(
        parts_by_id.values(),
        key=lambda part: (
            part["release_date"] is None,
            part["release_date"] or "",
            part["id"],
        ),
    )
    return {
        "collection_id": collection_id,
        "title": str(collection_details.get("name") or "TMDb collection"),
        "source": "TMDb",
        "url": f"https://www.themoviedb.org/collection/{collection_id}",
        "parts": parts,
    }


def next_unwatched_in_order(
    collection: dict[str, Any] | None, anchor_movie_id: int
) -> dict[str, Any] | None:
    """Finds the next locally known unwatched part after a dated anchor."""
    if not collection or isinstance(anchor_movie_id, bool):
        return None
    parts = collection.get("parts")
    if not isinstance(parts, list):
        return None
    anchor = next(
        (part for part in parts if part.get("id") == anchor_movie_id),
        None,
    )
    anchor_date = _verified_release_date(anchor.get("release_date")) if anchor else None
    if anchor_date is None:
        return None
    later_parts = sorted(
        (
            part for part in parts
            if (
                (release_date := _verified_release_date(part.get("release_date")))
                is not None
                and release_date > anchor_date
            )
        ),
        key=lambda part: (
            _verified_release_date(part.get("release_date")) or "",
            int(part["id"]),
        ),
    )
    for part in later_parts:
        if part.get("in_catalog") and not part.get("watched"):
            return {
                **part,
                "explanation": (
                    "Следующий по подтверждённой дате выхода фильм в коллекции; "
                    "он есть в каталоге и ещё не отмечен просмотренным."
                ),
            }
    return None


def check_watchlist_sequels(
    db: MovieDB,
    api_key: str,
    *,
    client_factory: Callable[[str, str], TMDBClient] = TMDBClient,
    language: str = "ru-RU",
    recheck_after_hours: float = 0.0,
) -> dict[str, Any]:
    """Checks watchlist collections; `recheck_after_hours` skips recent checks.

    Автопроверка при запуске передаёт 24 часа, чтобы не опрашивать TMDb по
    всему списку «Хочу посмотреть» при каждом старте. Ручная проверка
    передаёт 0 и всегда перепроверяет коллекции.
    """

    def result(
        status: str,
        *,
        checked: int = 0,
        unverified: int = 0,
        new_notifications: int = 0,
        skipped: int = 0,
    ) -> dict[str, Any]:
        return {
            "status": status,
            "checked": checked,
            "unverified": unverified,
            "new_notifications": new_notifications,
            "skipped": skipped,
        }

    if not api_key or not api_key.strip():
        return result("no_api_key")

    anchors = db.watchlist()
    if not anchors:
        return result("empty_watchlist")

    fresh: set[int] = set()
    if recheck_after_hours and recheck_after_hours > 0:
        since = (
            datetime.now() - timedelta(hours=float(recheck_after_hours))
        ).isoformat(timespec="seconds")
        fresh = db.sequel_anchors_checked_since(since)

    client = client_factory(api_key, language)
    unverified = 0
    new_notifications = 0
    checked = 0
    skipped = 0
    for anchor in anchors:
        anchor_id = int(anchor["id"])
        if anchor_id in fresh:
            skipped += 1
            continue
        details = client.movie_details(anchor_id)
        collection = details.get("belongs_to_collection")
        collection_id = (
            _positive_id(collection.get("id")) if isinstance(collection, dict) else None
        )
        if collection_id is None:
            db.save_sequel_check(anchor_id, None)
            unverified += 1
            checked += 1
            continue
        collection_details = client.collection_details(collection_id)
        parts = collection_details.get("parts") or []
        if not parts:
            unverified += 1
        new_notifications += db.save_sequel_check(anchor_id, collection_id, parts)
        checked += 1

    return result(
        "checked",
        checked=checked,
        unverified=unverified,
        new_notifications=new_notifications,
        skipped=skipped,
    )
