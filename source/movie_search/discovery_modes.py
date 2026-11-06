"""Local-data services for the additional movie discovery modes."""

from __future__ import annotations

from typing import Any

from .const import COUNTRIES, COUNTRIES_EN, GENRE_NAMES_EN, genre_label
from .database import MovieDB

CHALLENGE_DEFINITIONS = (
    {"id": "decades", "target": 5},
    {"id": "countries", "target": 5},
    {"id": "genres", "target": 5},
    {"id": "watched", "target": 25},
)


def _tokens(value: Any) -> set[str]:
    return {
        item.strip().strip(",").upper()
        for item in str(value or "").split(",")
        if item.strip().strip(",")
    }


def blind_choice(
    db: MovieDB, language: str, *, exclude_id: int | None = None
) -> dict[str, Any] | None:
    """Returns only the allowed pre-reveal fields for a blind choice."""
    row = db.blind_movie_candidate(language, exclude_id)
    if row is None:
        return None
    genres = [
        item.strip().strip(",").casefold()
        for item in str(row.get("genres") or "").split(",")
        if item.strip().strip(",")
    ]
    genre = next(
        (item for item in genres if item in GENRE_NAMES_EN),
        None,
    )
    if genre is None:
        return None
    return {
        "movie_id": int(row["id"]),
        "year": int(row["year"]),
        "genre": GENRE_NAMES_EN[genre] if language == "en-US" else genre_label(genre),
        "overview": str(row["overview"]),
    }


def reveal_blind_choice(db: MovieDB, card: dict[str, Any]) -> dict[str, Any] | None:
    """Resolves the hidden movie only when the caller explicitly requests reveal."""
    movie_id = card.get("movie_id")
    if isinstance(movie_id, bool) or not isinstance(movie_id, int) or movie_id <= 0:
        raise ValueError("Карточка слепого выбора не содержит корректный ID.")
    return db.get(movie_id)


def challenge_progress(db: MovieDB) -> list[dict[str, Any]]:
    """Counts unique decades, countries, and genres in watched catalogue movies."""
    movies = db.watched_movies()
    decades: set[int] = set()
    countries: set[str] = set()
    genres: set[str] = set()
    for movie in movies:
        year = movie.get("year")
        if isinstance(year, int) and not isinstance(year, bool) and year > 0:
            decades.add(year // 10 * 10)
        countries.update(_tokens(movie.get("countries")))
        genres.update(
            item.strip().strip(",").casefold()
            for item in str(movie.get("genres") or "").split(",")
            if item.strip().strip(",")
        )
    values = {
        "decades": len(decades),
        "countries": len(countries),
        "genres": len(genres),
        "watched": len(movies),
    }
    return [
        {**definition, "progress": values[definition["id"]]}
        for definition in CHALLENGE_DEFINITIONS
    ]


def filmography(db: MovieDB, person: str) -> list[dict[str, Any]]:
    rows = db.filmography(person)
    for row in rows:
        statuses: list[str] = []
        if row.get("watched"):
            statuses.append("watched")
        if row.get("watchlisted"):
            statuses.append("watchlist")
        if row.get("planned_date"):
            statuses.append("planned")
        row["statuses"] = statuses or ["not_started"]
    return rows


def movie_twin(db: MovieDB, movie_id: int, limit: int = 8) -> list[dict[str, Any]]:
    """Finds less-known similar films with a verified cast, country, or era difference."""
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Лимит должен быть положительным целым числом.")
    source = db.get(movie_id)
    if source is None:
        return []
    source_votes = source.get("votes")
    if not isinstance(source_votes, int) or isinstance(source_votes, bool) or source_votes <= 0:
        return []
    source_cast = db.cast_names_for_movies([movie_id]).get(movie_id, set())
    source_countries = _tokens(source.get("countries"))
    source_year = source.get("year")
    source_decade = (
        source_year // 10 * 10
        if isinstance(source_year, int) and not isinstance(source_year, bool)
        else None
    )
    candidates = db.similar_by(
        movie_id, ("actors", "director", "genres", "keywords"), limit=1000
    )
    casts = db.cast_names_for_movies(int(row["id"]) for row in candidates)
    results: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate.get("watched"):
            continue
        candidate_votes = candidate.get("votes")
        if (
            not isinstance(candidate_votes, int)
            or isinstance(candidate_votes, bool)
            or candidate_votes < 0
            or candidate_votes >= source_votes
        ):
            continue
        candidate_id = int(candidate["id"])
        differences: list[dict[str, str]] = []
        candidate_cast = casts.get(candidate_id, set())
        if source_cast and candidate_cast and source_cast.isdisjoint(candidate_cast):
            differences.append({
                "type": "actor",
                "source": ", ".join(sorted(source_cast)),
                "candidate": ", ".join(sorted(candidate_cast)),
            })
        candidate_countries = _tokens(candidate.get("countries"))
        if (
            source_countries
            and candidate_countries
            and source_countries.isdisjoint(candidate_countries)
        ):
            differences.append({
                "type": "country",
                "source": ", ".join(sorted(source_countries)),
                "candidate": ", ".join(sorted(candidate_countries)),
            })
        year = candidate.get("year")
        decade = (
            year // 10 * 10
            if isinstance(year, int) and not isinstance(year, bool)
            else None
        )
        if source_decade is not None and decade is not None and source_decade != decade:
            differences.append({
                "type": "decade",
                "source": str(source_decade),
                "candidate": str(decade),
            })
        if not differences or not candidate.get("similarity_reasons"):
            continue
        differences.append({
            "type": "popularity",
            "source": str(source_votes),
            "candidate": str(candidate_votes),
        })
        candidate["twin_matches"] = candidate["similarity_reasons"]
        candidate["twin_differences"] = differences
        results.append(candidate)
        if len(results) >= limit:
            break
    return results


def yearly_summary(db: MovieDB, year: int) -> dict[str, Any]:
    movies = db.history_for_year(year)
    countries: dict[str, int] = {}
    decades: dict[int, int] = {}
    ratings: dict[int, int] = {}
    rated = [
        int(movie["personal_rating"])
        for movie in movies
        if movie.get("personal_rating") is not None
    ]
    for movie in movies:
        for country in _tokens(movie.get("countries")):
            countries[country] = countries.get(country, 0) + 1
        movie_year = movie.get("year")
        if isinstance(movie_year, int) and not isinstance(movie_year, bool) and movie_year > 0:
            decade = movie_year // 10 * 10
            decades[decade] = decades.get(decade, 0) + 1
    for rating in rated:
        ratings[rating] = ratings.get(rating, 0) + 1
    return {
        "year": year,
        "history_count": len(movies),
        "watched_count": sum(bool(movie.get("watched")) for movie in movies),
        "countries": countries,
        "decades": decades,
        "rated_count": len(rated),
        "average_rating": round(sum(rated) / len(rated), 2) if rated else None,
        "ratings": ratings,
        "movies": movies,
    }


def _country_label(code: str, language: str) -> str:
    names = COUNTRIES_EN if language == "en-US" else COUNTRIES
    return names.get(code, code)


def indifferent_movies(
    db: MovieDB, *, max_runtime: int | None = None, limit: int = 5, language: str = "ru-RU"
) -> list[dict[str, Any]]:
    """Selects unrated, eligible movies with deterministic variety across options."""
    if language not in {"ru-RU", "en-US"}:
        raise ValueError("Язык должен быть ru-RU или en-US.")
    if max_runtime is not None and (
        isinstance(max_runtime, bool)
        or not isinstance(max_runtime, int)
        or max_runtime < 1
    ):
        raise ValueError("Максимальная длительность должна быть положительным числом.")
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("Лимит должен быть положительным целым числом.")
    candidates = db.collection_queue(
        {"max_runtime": max_runtime, "exclude_personal_content": True},
        page_size=500,
    )
    dislikes = {
        int(row["id"])
        for row in db.recommendation_feedback()
        if row.get("recommendation_feedback") == "dislike"
    }
    candidates = [
        movie for movie in candidates
        if movie.get("personal_rating") is None
        and int(movie["id"]) not in dislikes
    ]
    candidates.sort(key=lambda movie: (
        -float(movie.get("rating") or 0),
        -int(movie.get("votes") or 0),
        int(movie["id"]),
    ))
    selected: list[dict[str, Any]] = []
    used_decades: set[int] = set()
    used_countries: set[str] = set()
    used_genres: set[str] = set()
    remaining = list(candidates)
    for index in range(min(limit, len(remaining))):
        if index == 0:
            chosen = remaining[0]
            reasons = ["highest_ranked"]
        else:
            def diversity_key(movie: dict[str, Any]) -> tuple[int, float, int, int]:
                year = movie.get("year")
                decade = year // 10 * 10 if isinstance(year, int) and year > 0 else None
                countries = _tokens(movie.get("countries"))
                genres = {
                    item.strip().strip(",").casefold()
                    for item in str(movie.get("genres") or "").split(",")
                    if item.strip().strip(",")
                }
                novelty = (
                    (2 if decade is not None and decade not in used_decades else 0)
                    + len(countries - used_countries)
                    + len(genres - used_genres)
                )
                return (
                    -novelty,
                    -float(movie.get("rating") or 0),
                    -int(movie.get("votes") or 0),
                    int(movie["id"]),
                )

            remaining.sort(key=diversity_key)
            chosen = remaining[0]
            reasons = []
            year = chosen.get("year")
            decade = year // 10 * 10 if isinstance(year, int) and year > 0 else None
            countries = _tokens(chosen.get("countries"))
            genres = {
                item.strip().strip(",").casefold()
                for item in str(chosen.get("genres") or "").split(",")
                if item.strip().strip(",")
            }
            if decade is not None and decade not in used_decades:
                reasons.append("decade")
            if countries - used_countries:
                reasons.append("country")
            if genres - used_genres:
                reasons.append("genre")
            if not reasons:
                reasons.append("quality")
        chosen_year = chosen.get("year")
        chosen_decade = (
            chosen_year // 10 * 10
            if isinstance(chosen_year, int) and chosen_year > 0
            else None
        )
        chosen_countries = _tokens(chosen.get("countries"))
        chosen_genres = {
            item.strip().strip(",").casefold()
            for item in str(chosen.get("genres") or "").split(",")
            if item.strip().strip(",")
        }
        chosen["diversity_evidence"] = {
            "decade": (
                chosen_decade
                if chosen_decade is not None and chosen_decade not in used_decades
                else None
            ),
            "countries": sorted(chosen_countries - used_countries),
            "genres": sorted(chosen_genres - used_genres),
        }
        remaining.remove(chosen)
        movie_year = chosen.get("year")
        if isinstance(movie_year, int) and movie_year > 0:
            used_decades.add(movie_year // 10 * 10)
        used_countries.update(_tokens(chosen.get("countries")))
        used_genres.update(
            item.strip().strip(",").casefold()
            for item in str(chosen.get("genres") or "").split(",")
            if item.strip().strip(",")
        )
        chosen["diversity_reasons"] = reasons
        chosen["diversity_labels"] = {
            "countries": [
                _country_label(country, language)
                for country in sorted(_tokens(chosen.get("countries")))
            ],
            "genres": [
                GENRE_NAMES_EN.get(genre, genre.title())
                if language == "en-US"
                else genre_label(genre)
                for genre in sorted({
                    item.strip().strip(",").casefold()
                    for item in str(chosen.get("genres") or "").split(",")
                    if item.strip().strip(",")
                })
            ],
        }
        selected.append(chosen)
    return selected
