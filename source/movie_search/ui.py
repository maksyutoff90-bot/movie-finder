"""Графический интерфейс Movie Finder (Tkinter, тёмная тема)."""

from __future__ import annotations

import json
import os
import queue
import re
import threading
import time
import tkinter as tk
import unicodedata
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Any

from PIL import ImageTk

from .config import BUNDLED_POSTER_DIR, DB_PATH, Config
from .const import (
    CATEGORY_LABELS,
    CATEGORY_ORDER,
    COUNTRIES,
    COUNTRIES_EN,
    GENRE_NAMES_EN,
    GENRE_ORDER,
    MAX_YEAR,
    MIN_YEAR,
    SORT_LABELS,
    SYNC_FROM_YEAR,
    SYNC_TO_YEAR,
    category_label,
    country_title,
    genre_label,
)
from .database import MovieDB
from .franchises import (
    check_watchlist_sequels,
    franchise_order,
    next_unwatched_in_order,
)
from .library import match_files
from .links import (
    fetch_extras,
    fetch_providers,
    free_catalog_links,
    imdb_url,
    kinopoisk_url,
    tmdb_url,
    trailer_search_url,
    watch_search_url,
    wikipedia_url,
)
from .players import default_player, detect_players, open_file
from .posters import PosterCache
from .tmdb_sync import SyncJob, TMDBClient, TMDBError

# --------------------------------------------------------------------- тема
BG = "#0e1116"
PANEL = "#151a23"
CARD = "#1b212b"
CARD_HOVER = "#222a36"
BORDER = "#28303d"
TEXT = "#e9edf4"
MUTED = "#8b95a7"
ACCENT = "#4c8dff"
GOLD = "#f0c15c"

FONT = "Segoe UI"
FONT_BOLD = (FONT, 9, "bold")
FONT_SMALL = (FONT, 8)
FONT_TEXT = (FONT, 10)
FONT_H1 = (FONT, 17, "bold")
FONT_H2 = (FONT, 20, "bold")

PAGE_SIZE = 60

# Новинки, которые догружает кнопка «Обновить новинки».
RECENT_YEARS_FROM = 2023

# Подписи кнопок для источников легального просмотра.
WATCH_LABELS = {
    "Мосфильм": "Смотреть на Мосфильме",
    "Internet Archive": "Смотреть в архиве",
}

SORT_LABELS_EN = {"rating": "Highest rated", "votes": "Most popular", "year_new": "Newest first", "year_old": "Oldest first", "title": "Alphabetical"}
UI_TEXT_EN = {
    "НАЗВАНИЕ": "TITLE", "АКТЁР ИЛИ РЕЖИССЁР": "ACTOR OR DIRECTOR",
    "ЖАНР": "GENRE", "ТЕМА": "THEME", "НАСТРОЕНИЕ": "MOOD",
    "СТРАНА": "COUNTRY", "ГОД ВЫХОДА": "RELEASE YEAR",
    "ДЛИТЕЛЬНОСТЬ": "RUNTIME", "МИНУТ": "MINUTES",
    "МИНИМАЛЬНЫЙ РЕЙТИНГ": "MINIMUM RATING", "ГОЛОСОВ ОТ": "MINIMUM VOTES",
    "СОРТИРОВКА": "SORT BY", "НАСТРОЕНИЕ / ТЕМА": "MOOD / THEME",
    "Любой": "Any genre", "Любая": "Any country",
    "Обновить базу (TMDb)": "Update database (TMDb)", "Обновить новинки": "Update new releases",
    "⚙ Настройки": "⚙ Settings", "Готово": "Ready", "Показать ещё": "Show more",
    "0 — без ограничений": "0 — no limit", "Только закладки": "Bookmarked only",
    "Скрывать просмотренные": "Hide watched", "Смотрел": "Watched",
    "Личная оценка:": "My rating:",
    "＋ Хочу посмотреть": "＋ Watchlist",
    "✓ В списке": "✓ In watchlist",
    "Приоритет и заметка": "Priority & note",
    "👍 Подходит": "👍 Fits me",
    "👎 Не моё": "👎 Not for me",
    "Отзывы к рекомендациям": "Recommendation feedback",
    "Проверка качества каталога": "Catalogue quality check",
    "Режим просмотра подборки": "Collection viewer",
    "Список «Хочу посмотреть»": "Watchlist",
    "Планировщик кинопросмотра": "Viewing planner",
    "Скрытие нежелательного контента": "Hide unwanted content",
    "Найти похожее…": "Find similar…",
    "Запланировать просмотр": "Plan a screening",
    "Приоритет": "Priority",
    "Заметка": "Note",
    "Сохранить": "Save",
    "Удалить из списка": "Remove from list",
    "Открыть фильм": "Open movie",
    "Удалить отзыв": "Clear feedback",
    "Фильм": "Movie",
    "Год": "Year",
    "Источник": "Source",
    "Проблемы": "Issues",
    "Не указан": "Not specified",
    "Проверка не нашла проблем.": "No catalogue issues found.",
    "Год не указан": "Year missing",
    "Подозрительный год": "Suspicious year",
    "Год не совпадает с датой": "Year differs from release date",
    "Пустое описание": "Empty description",
    "Слишком короткое описание": "Description is too short",
    "Похожее название": "Possible duplicate title",
    "Оценить и далее": "Rate & next",
    "Далее / пропустить": "Next / skip",
    "В подборке больше нет фильмов.": "No more movies in this collection.",
    "Серии и франшизы": "Series & franchises",
    "Осталось в очереди": "Remaining",
    "Просмотр завершён": "Queue complete",
    "Найти фильмы": "Find movies", "Сбросить фильтры": "Reset filters", "БАЗА": "DATABASE",
    "Постеры и описания — из TMDb и Википедии.": "Posters and descriptions from TMDb and Wikipedia.",
    "История просмотров": "Watch history", "Описание отсутствует.": "No description available.",
    "Ничего не найдено.": "No movies found.",
    "Измените год, жанр или минимальный рейтинг": "Adjust the year, genre or minimum rating",
    "и нажмите «Найти фильмы».": "and click “Find movies”.", "База фильмов пуста.": "The movie database is empty.",
    "Нажмите «Обновить базу (TMDb)» вверху справа и вставьте": "Click “Update database (TMDb)” above and enter",
    "бесплатный API-ключ TMDb — база наполнится за несколько минут.": "a free TMDb API key. The database will fill in a few minutes.",
    "Либо соберите офлайн-каталог:  python tools/build_catalog.py": "Or build an offline catalogue: python tools/build_catalog.py",
    "Ничего не найдено — попробуйте ослабить фильтры": "No results — try relaxing your filters",
    "Жанр: ": "Genre: ", "Страна: ": "Country: ", "Режиссёр: ": "Director: ",
    "В ролях: ": "Cast: ", "Ключевые слова: ": "Keywords: ", "Похожие:": "Similar:",
    " мин": " min", " голосов": " votes", "Закрыть": "Close", "▶ Смотреть": "▶ Play",
    "Трейлер": "Trailer", "Где смотреть": "Where to watch", "Бесплатно ▾": "Free ▾",
    "Проверить ключ": "Check API key", "Отмена": "Cancel",
    "Плеер:": "Player:", "Папка:": "Folder:", "Найти": "Detect", "Обзор…": "Browse…",
    "Найти файлы в папке": "Scan movie folder", "Страниц на год (1–10):": "Pages per year (1–10):",
    "20 фильмов на страницу": "20 movies per page", "Язык описаний:": "Language for database sync:",
    "Язык загрузки из TMDb:": "Language for TMDb download:",
    "Язык интерфейса:": "Interface language:",
    "подписи, кнопки и описания": "labels, buttons and overviews",
    "Моя коллекция и плеер": "My collection and player", "Настройки": "Settings",
    "Сначала вставьте ключ.": "Enter an API key first.", "Проверяю ключ…": "Checking API key…",
    "Ключ работает. Можно сохранять.": "The key works. You can save it.",
    "Смотреть на Мосфильме": "Watch on Mosfilm", "Смотреть в архиве": "Watch in the archive",
    "поиск фильмов": "discover films", "Закладки": "Bookmarks",
    "★ В закладках": "★ Bookmarked", "☆ В закладки": "☆ Bookmark",
    "Фильмы": "Movies",
    "Сохранённые фильтры": "Saved filters",
    "Применить": "Apply", "Удалить": "Delete", "Случайный фильм": "Random movie",
    "Выбрать фильм на вечер": "Pick a movie for tonight",
    "Новые режимы и подборки": "New discovery modes",
    "Рекомендации": "For you", "Импорт личных данных": "Import personal data",
    "Экспорт личных данных": "Export personal data",
    "Моя статистика": "My taste stats",
    "Резервная копия": "Backup reminder",
    "Экспортируйте личные данные регулярно и храните JSON отдельно от компьютера. "
    "В файл входят оценки, просмотренное, закладки, список просмотра и подборки; ключи и каталог — нет.":
        "Export personal data regularly and keep the JSON separate from this computer. "
        "It includes ratings, watched titles, bookmarks, watchlist and saved filters; no API keys or catalogue.",
    "Просмотренное, личные оценки, закладки и сохранённые подборки. "
    "Каталог, постеры и ключи не экспортируются. Регулярно храните JSON-копию отдельно.":
        "Watched titles, personal ratings, bookmarks and saved filters. "
        "The catalogue, posters and API keys are not exported. Keep a JSON copy separately.",
    "Просмотренное, личные оценки, закладки и сохранённые подборки. "
    "Список просмотра и отзывы к рекомендациям тоже экспортируются. "
        "Планы просмотра и исключения контента тоже экспортируются. "
        "Каталог, постеры и ключи не экспортируются. Регулярно храните JSON-копию отдельно.":
        "Watched titles, personal ratings, bookmarks and saved filters. "
        "The watchlist and recommendation feedback are included too. "
        "Viewing plans and content exclusions are included too. "
        "The catalogue, posters and API keys are not exported. Keep a JSON copy separately.",
    "Просмотрено": "Watched", "Оценено": "Rated", "Средняя оценка": "Average rating",
    "История открытий": "View history",
    "Оценки по шкале": "Rating distribution", "Любимые жанры": "Favorite genres",
    "Фильмы по годам": "Movies by year", "Активность по месяцам": "Activity by month",
    "Пока нет личных данных. Отметьте просмотренные фильмы или поставьте оценку.":
        "No personal data yet. Mark a movie watched or give it a rating.",
    "Нет данных для статистики.": "No statistics available.",
    "Похоже на ваш любимый жанр: ": "Matches your favorite genre: ",
    "Общая тема: ": "Shared theme: ", "В ролях знакомый актёр: ": "Features an actor you like: ",
    "Похожая длительность": "Similar runtime",
    "Выберите или сохраните фильтр": "Choose or save a filter",
    "Пока пусто — откройте любой фильм, и он появится здесь.": "Nothing here yet — open a movie and it will appear here.",
    "Пока пусто": "Nothing here yet",
}

MOOD_CATEGORIES = {
    "uplifting", "light", "tense", "romantic", "thoughtful", "family_night",
}



def _ellipsis(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    if len(text) <= limit:
        return text
    cut = text[:limit]
    space = cut.rfind(" ")
    if space > limit * 0.6:
        cut = cut[:space]
    return cut.rstrip(" ,.;:—-") + "…"


_LEAD_QUOTE = re.compile(r"^«[^»]{1,90}»\s*")
_LEAD_PAREN = re.compile(r"^\([^)]{0,140}\)\s*")


def _short_overview(text: str, limit: int = 66, *, empty: str = "Описание отсутствует.") -> str:
    """Короткое описание для карточки: без «Названия» и «(англ. …)» в начале."""
    cleaned = " ".join((text or "").split())
    previous = None
    while previous != cleaned:
        previous = cleaned
        cleaned = _LEAD_QUOTE.sub("", cleaned)
        cleaned = _LEAD_PAREN.sub("", cleaned)
        cleaned = cleaned.lstrip("—–-.,;: ")
    if not cleaned:
        return empty
    return _ellipsis(cleaned, limit)


class RatingSlider(tk.Canvas):
    """Ползунок рейтинга с явной «ручкой» — без сюрпризов системной темы."""

    def __init__(
        self,
        master: tk.Misc,
        variable: tk.DoubleVar,
        *,
        minimum: float = 0.0,
        maximum: float = 10.0,
        step: float = 0.5,
        length: int = 180,
        height: int = 28,
        command=None,
    ) -> None:
        super().__init__(
            master, width=length, height=height, bg=PANEL, highlightthickness=0, bd=0,
            cursor="hand2",
        )
        self.variable = variable
        self.minimum = minimum
        self.maximum = maximum
        self.step = step
        self.length = length
        self.height = height
        self.command = command
        self._pad = 8
        self.variable.trace_add("write", lambda *_: self._redraw())
        self.bind("<Button-1>", self._on_pointer)
        self.bind("<B1-Motion>", self._on_pointer)
        self._redraw()

    def _redraw(self) -> None:
        self.delete("all")
        y = self.height // 2
        x0, x1 = self._pad, self.length - self._pad
        value = max(self.minimum, min(self.maximum, float(self.variable.get())))
        ratio = (value - self.minimum) / (self.maximum - self.minimum or 1)
        x = x0 + ratio * (x1 - x0)
        self.create_line(x0, y, x1, y, fill=CARD, width=6, capstyle="round")
        if x - x0 > 1:
            self.create_line(x0, y, x, y, fill=ACCENT, width=6, capstyle="round")
        self.create_oval(x - 6, y - 6, x + 6, y + 6, fill="#eaf1ff", outline=ACCENT, width=2)

    def _on_pointer(self, event: tk.Event) -> None:
        x0, x1 = self._pad, self.length - self._pad
        ratio = min(1.0, max(0.0, (event.x - x0) / (x1 - x0)))
        raw = self.minimum + ratio * (self.maximum - self.minimum)
        value = round(round(raw / self.step) * self.step, 1)
        self.variable.set(value)
        if self.command:
            self.command(value)


class MovieCard(tk.Frame):
    """Карточка фильма: постер, название, год и рейтинг, короткое описание."""

    WIDTH = 174
    HEIGHT = 520
    POSTER_SIZE = (150, 225)

    def __init__(
        self,
        master: tk.Misc,
        movie: dict[str, Any],
        on_open,
        placeholder: ImageTk.PhotoImage,
        language: str = "ru-RU",
        on_personal_state=None,
        on_watchlist=None,
        on_watchlist_edit=None,
        on_feedback=None,
    ) -> None:
        super().__init__(
            master, bg=CARD, highlightthickness=1, highlightbackground=BORDER, bd=0
        )
        self.movie = movie
        self._on_open = on_open
        self.language = language
        self._on_personal_state = on_personal_state
        self._on_watchlist = on_watchlist
        self._on_watchlist_edit = on_watchlist_edit
        self._on_feedback = on_feedback
        self._photo: ImageTk.PhotoImage | None = None
        self.configure(width=self.WIDTH, height=self.HEIGHT)
        self.grid_propagate(False)
        self.pack_propagate(False)

        self.poster = tk.Label(self, bg=CARD, bd=0, image=placeholder)
        self.poster.image = placeholder
        self.poster.pack(pady=(9, 7))

        title = movie.get("title") or "Без названия"
        self.title_lbl = tk.Label(
            self,
            text=title,
            bg=CARD,
            fg=TEXT,
            font=FONT_BOLD,
            wraplength=self.WIDTH - 22,
            justify="left",
            anchor="w",
            height=2,
        )
        self.title_lbl.pack(fill="x", padx=11)

        year = movie.get("year")
        rating = movie.get("rating")
        rating_text = f"★ {rating:.1f}" if isinstance(rating, (int, float)) and rating else "★ —"
        meta = f"{year if year else '—'}  ·  {rating_text}"
        self.meta_lbl = tk.Label(
            self, text=meta, bg=CARD, fg=GOLD, font=FONT_SMALL, anchor="w"
        )
        self.meta_lbl.pack(fill="x", padx=11, pady=(3, 2))

        state_row = tk.Frame(self, bg=CARD)
        state_row.pack(fill="x", padx=8, pady=(2, 1))
        self.watched_var = tk.BooleanVar(value=bool(movie.get("watched", 0)))
        self.watched_check = tk.Checkbutton(
            state_row,
            text=self._t("Смотрел", "Watched"),
            variable=self.watched_var,
            command=self._save_personal_state,
            bg=CARD,
            fg=TEXT,
            selectcolor=PANEL,
            activebackground=CARD,
            activeforeground=ACCENT,
            font=FONT_SMALL,
            bd=0,
            highlightthickness=0,
            padx=0,
        )
        self.watched_check.pack(side="left")
        self.personal_rating_var = tk.StringVar(
            value=str(movie.get("personal_rating") or "—")
        )
        self.personal_rating_label = tk.Label(
            state_row, text=self._t("Личная оценка:", "My rating:"), bg=CARD, fg=MUTED, font=FONT_SMALL
        )
        self.personal_rating_label.pack(side="left", padx=(6, 3))
        self.personal_rating_combo = ttk.Combobox(
            state_row,
            textvariable=self.personal_rating_var,
            values=("—", *(str(value) for value in range(1, 11))),
            state="readonly",
            width=3,
        )
        self.personal_rating_combo.pack(side="left")
        self.personal_rating_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._save_personal_state()
        )
        self.watchlist_btn = ttk.Button(
            self,
            text=self._watchlist_label(),
            style="Ghost.TButton",
            command=self._toggle_watchlist,
        )
        self.watchlist_btn.pack(fill="x", padx=10, pady=(2, 0))
        self.watchlist_edit_btn = ttk.Button(
            self,
            text=self._t("Приоритет и заметка", "Priority & note"),
            style="Ghost.TButton",
            command=self._edit_watchlist,
        )
        self.watchlist_edit_btn.pack(fill="x", padx=10, pady=(2, 0))

        self.recommendation_lbl = tk.Label(
            self,
            text=self._recommendation_text(),
            bg=CARD,
            fg=ACCENT,
            font=FONT_SMALL,
            wraplength=self.WIDTH - 22,
            justify="left",
            anchor="w",
            height=2,
        )
        if self.movie.get("recommendation_reasons") or self.movie.get("_recommendation"):
            self.recommendation_lbl.pack(fill="x", padx=11, pady=(2, 0))
            self.feedback_frame = tk.Frame(self, bg=CARD)
            self.feedback_frame.pack(fill="x", padx=9, pady=(2, 0))
            ttk.Button(
                self.feedback_frame,
                text="👍 Подходит",
                style="Ghost.TButton",
                command=lambda: self._save_feedback("like"),
            ).pack(fill="x", pady=(0, 2))
            ttk.Button(
                self.feedback_frame,
                text="👎 Не моё",
                style="Ghost.TButton",
                command=lambda: self._save_feedback("dislike"),
            ).pack(fill="x")

        self.snippet_lbl = tk.Label(
            self,
            text=self._overview_text(),
            bg=CARD,
            fg=MUTED,
            font=FONT_SMALL,
            wraplength=self.WIDTH - 22,
            justify="left",
            anchor="nw",
            height=3,
        )
        self.snippet_lbl.pack(fill="x", padx=11)

        for widget in (self, self.poster, self.title_lbl, self.meta_lbl, self.snippet_lbl):
            widget.bind("<Button-1>", self._click)
            widget.bind("<Enter>", self._enter)
            widget.bind("<Leave>", self._leave)

    def _recommendation_text(self) -> str:
        reasons = self.movie.get("recommendation_reasons") or []
        if not reasons:
            return ""
        english = self.language.startswith("en")
        labels: list[str] = []
        for reason in reasons[:2]:
            kind = reason.get("type")
            value = reason.get("value")
            if kind == "genre":
                genre = GENRE_NAMES_EN.get(value, value) if english else genre_label(value)
                labels.append(
                    ("Matches your favorite genre: " if english else "Похоже на ваш любимый жанр: ")
                    + genre
                )
            elif kind == "keyword":
                labels.append(("Shared theme: " if english else "Общая тема: ") + str(value))
            elif kind == "actor":
                labels.append(("Features an actor you like: " if english else "В ролях знакомый актёр: ") + str(value))
            elif kind == "runtime":
                labels.append("Similar runtime" if english else "Похожая длительность")
        return " · ".join(labels)

    def update_personal_state(self, watched: bool, personal_rating: int | None) -> None:
        self.movie["watched"] = int(watched)
        self.movie["personal_rating"] = personal_rating
        self.watched_var.set(watched)
        self.personal_rating_var.set(str(personal_rating) if personal_rating is not None else "—")

    def _save_personal_state(self) -> None:
        if not self._on_personal_state:
            return
        selected = self.personal_rating_var.get()
        rating = int(selected) if selected.isdigit() else None
        if not self._on_personal_state(
            int(self.movie["id"]), bool(self.watched_var.get()), rating
        ):
            self.update_personal_state(
                bool(self.movie.get("watched", 0)), self.movie.get("personal_rating")
            )

    # ------------------------------------------------------------------ вид
    def _overview_text(self) -> str:
        english = self.language.startswith("en")
        overview = self.movie.get("overview_en") if english else self.movie.get("overview")
        if english and not overview:
            if self.movie.get("_english_overview_error"):
                empty = "English description could not be loaded. Search again to retry."
            elif self.movie.get("overview_en_checked"):
                empty = "No English description available."
            elif not self.movie.get("_english_api_available", True):
                empty = "Add a TMDb API key to load English descriptions."
            else:
                empty = "Loading English description…"
        else:
            empty = "No description available." if english else "Описание отсутствует."
        return _short_overview(overview or "", empty=empty)

    def set_overview(self) -> None:
        self.snippet_lbl.configure(text=self._overview_text())

    def set_recommendation(self) -> None:
        self.recommendation_lbl.configure(text=self._recommendation_text())

    def _watchlist_label(self) -> str:
        if self.language.startswith("en"):
            return "✓ In watchlist" if self.movie.get("watchlisted") else "＋ Watchlist"
        return "✓ В списке" if self.movie.get("watchlisted") else "＋ Хочу посмотреть"

    def _t(self, russian: str, english: str) -> str:
        """Подпись карточки на языке интерфейса (карточка живёт вне окон)."""
        return english if str(self.language).startswith("en") else russian

    def refresh_language(self) -> None:
        """Обновляет подписи карточки после смены языка интерфейса."""
        self.watched_check.configure(text=self._t("Смотрел", "Watched"))
        self.personal_rating_label.configure(
            text=self._t("Личная оценка:", "My rating:")
        )
        self.watchlist_edit_btn.configure(
            text=self._t("Приоритет и заметка", "Priority & note")
        )
        self.watchlist_btn.configure(text=self._watchlist_label())
        if hasattr(self, "feedback_frame"):
            buttons = self.feedback_frame.winfo_children()
            if len(buttons) == 2:
                buttons[0].configure(text=self._t("👍 Подходит", "👍 Fits me"))
                buttons[1].configure(text=self._t("👎 Не моё", "👎 Not for me"))
        self.set_overview()
        self.set_recommendation()

    def set_watchlist_status(self, watchlisted: bool) -> None:
        self.movie["watchlisted"] = bool(watchlisted)
        if not self.winfo_exists():
            return
        self.watchlist_btn.configure(text=self._watchlist_label())

    def _toggle_watchlist(self) -> None:
        if not self._on_watchlist:
            return
        target = not bool(self.movie.get("watchlisted"))
        # Сначала переключаем вид: в режиме рекомендаций колбэк перерисовывает
        # выдачу и уничтожает эту карточку, поэтому трогать кнопку после него нельзя.
        self.set_watchlist_status(target)
        if not self._on_watchlist(int(self.movie["id"]), target, 3, ""):
            if self.winfo_exists():
                self.set_watchlist_status(not target)

    def _edit_watchlist(self) -> None:
        if self._on_watchlist_edit:
            self._on_watchlist_edit(self.movie)

    def _save_feedback(self, feedback: str) -> None:
        if self._on_feedback:
            self._on_feedback(int(self.movie["id"]), feedback)

    def set_poster(self, photo: ImageTk.PhotoImage) -> None:
        self._photo = photo
        self.poster.configure(image=photo)
        self.poster.image = photo

    def _enter(self, _event=None) -> None:
        self.configure(highlightbackground=ACCENT)
        self.title_lbl.configure(fg=ACCENT)

    def _leave(self, _event=None) -> None:
        self.configure(highlightbackground=BORDER)
        self.title_lbl.configure(fg=TEXT)

    def _click(self, _event=None) -> None:
        self._on_open(self.movie)


class MovieApp(tk.Tk):
    """Главное окно приложения."""

    def __init__(
        self,
        *,
        db_path=None,
        posters_dir=None,
        config: Config | None = None,
    ) -> None:
        super().__init__()
        self.cfg = config or Config()
        self.ui_language = "en-US" if self.cfg.get("ui_language") == "en-US" else "ru-RU"
        self._english_api_available = bool(self.cfg.api_key)
        self._overview_pending: set[int] = set()
        self._overview_pending_lock = threading.Lock()
        self._detail_windows: set[DetailWindow] = set()
        self._showing_recommendations = False
        self._sequel_check_running = False
        self.data_note = ""
        self.suppress_dialogs = False  # в диагностических режимах окна не нужны
        db_file = Path(db_path or DB_PATH)
        self.db = MovieDB(db_file, defer_index=True)
        data_dir = db_file.parent
        if db_path is None:
            issue = self.db.check_writable()
            if issue and "locked" not in issue.lower():
                moved = self._relocate_database(db_file, issue)
                if moved is not None:
                    data_dir = moved.parent
        # Постеры из комплекта читаются из папки программы, если база вынесена.
        poster_dir = Path(posters_dir) if posters_dir else data_dir / "posters"
        extra_posters = [BUNDLED_POSTER_DIR] if poster_dir != BUNDLED_POSTER_DIR else []
        self.posters = PosterCache(poster_dir, extra_folders=extra_posters)
        self.poster_pool = ThreadPoolExecutor(max_workers=6, thread_name_prefix="poster")
        self.overview_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="overview")

        self.cards: list[MovieCard] = []
        self.card_by_id: dict[int, MovieCard] = {}
        self._photos: dict[int, ImageTk.PhotoImage] = {}
        self._total = 0
        self._offset = 0
        self._filters: dict[str, Any] = {}
        self._last_width = 0
        self._search_seq = 0
        self._closing = False
        self._ui_queue: "queue.Queue[Any]" = queue.Queue()
        self._windows: list[tk.Toplevel] = []
        self._after_ids: set[str] = set()
        self._drain_id = ""
        self._relayout_id = ""
        self._open_windows: dict[tuple[type, Any], tk.Toplevel] = {}
        # Индекс опечаток строится в фоне: на большом каталоге это десятки секунд,
        # и синхронная постройка задерживала появление окна.
        self._index_thread = threading.Thread(
            target=self._warm_search_index, daemon=True, name="title-index"
        )
        self._index_thread.start()

        self.title(self._text(
            f"Movie Finder — поиск фильмов {MIN_YEAR}–{MAX_YEAR}",
            f"Movie Finder — movie discovery {MIN_YEAR}–{MAX_YEAR}",
        ))
        geometry = self.cfg.get("window_geometry") or ""
        self.geometry(geometry if geometry else "1340x880")
        self.minsize(1080, 700)
        self.configure(bg=BG)

        self._setup_style()
        self._build_header()
        self._build_status()
        self._build_body()
        self._apply_language()
        self._refresh_saved_filters()

        self.placeholder_photo = self._make_photo(
            self.posters.placeholder(MovieCard.POSTER_SIZE)
        )
        self.detail_placeholder = self._make_photo(
            self.posters.placeholder((300, 450))
        )

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.bind("<Control-f>", lambda _e: self.title_entry.focus_set())
        self._after(40, self._drain_queue)
        self._after(80, self._refresh_stats)
        self._after(120, self.search)
        self._after(400, self._check_writable)
        self._after(700, self._dedupe_once)
        self._after(900, self._show_data_note)
        self._after(1100, lambda: self.check_sequel_updates(manual=False))
    # ------------------------------------------------------------- оформление
    def _setup_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure(".", background=PANEL, foreground=TEXT, font=(FONT, 9))
        style.configure(
            "TCombobox",
            fieldbackground=CARD,
            background=CARD,
            foreground=TEXT,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            lightcolor=CARD,
            darkcolor=CARD,
            padding=4,
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", CARD), ("disabled", PANEL)],
            foreground=[("readonly", TEXT)],
            selectbackground=[("readonly", CARD)],
            selectforeground=[("readonly", TEXT)],
            arrowcolor=[("readonly", MUTED)],
        )
        style.configure(
            "TSpinbox",
            fieldbackground=CARD,
            background=CARD,
            foreground=TEXT,
            arrowcolor=MUTED,
            bordercolor=BORDER,
            padding=3,
        )
        style.configure(
            "TEntry",
            fieldbackground=CARD,
            foreground=TEXT,
            bordercolor=BORDER,
            insertcolor=TEXT,
            padding=4,
        )
        style.configure(
            "Accent.TButton",
            background=ACCENT,
            foreground="#08101f",
            font=(FONT, 10, "bold"),
            borderwidth=0,
            padding=(10, 9),
        )
        style.map(
            "Accent.TButton",
            background=[("pressed", "#3d78e0"), ("active", "#6ba3ff"), ("disabled", "#2a3242")],
            foreground=[("disabled", "#6c7789")],
        )
        style.configure(
            "Ghost.TButton",
            background=CARD,
            foreground=TEXT,
            bordercolor=BORDER,
            padding=(8, 7),
        )
        style.map(
            "Ghost.TButton",
            background=[("active", CARD_HOVER), ("pressed", "#2b3444")],
            bordercolor=[("active", ACCENT)],
        )
        style.configure(
            "TProgressbar",
            troughcolor=CARD,
            background=ACCENT,
            bordercolor=CARD,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            thickness=10,
        )
        style.configure(
            "Vertical.TScrollbar",
            background=CARD,
            troughcolor=BG,
            bordercolor=BG,
            arrowcolor=MUTED,
            gripcount=0,
        )
        style.map("Vertical.TScrollbar", background=[("active", BORDER)])
        style.configure("TSeparator", background=BORDER)
        style.configure(
            "Rating.Horizontal.TScale",
            background=ACCENT,
            troughcolor=CARD,
            bordercolor=CARD,
            lightcolor=ACCENT,
            darkcolor=ACCENT,
            sliderthickness=13,
            troughthickness=5,
        )

        self.option_add("*TCombobox*Listbox.background", CARD)
        self.option_add("*TCombobox*Listbox.foreground", TEXT)
        self.option_add("*TCombobox*Listbox.selectBackground", ACCENT)
        self.option_add("*TCombobox*Listbox.selectForeground", "#08101f")

    def _make_photo(self, image) -> ImageTk.PhotoImage:
        return ImageTk.PhotoImage(image)

    # ---------------------------------------------------------------- шапка
    @property
    def is_english(self) -> bool:
        return self.ui_language.startswith("en")

    def _text(self, russian: str, english: str) -> str:
        return english if self.is_english else russian

    def _backup_reminder_text(self) -> str:
        return self._text(
            "Резервная копия\n"
            "Экспортируйте личные данные регулярно и храните JSON отдельно от компьютера. "
            "В файл входят оценки, просмотренное, планы и исключения; ключи и каталог — нет.",
            "Backup reminder\n"
            "Export personal data regularly and keep the JSON separate from this computer. "
            "It includes ratings, watched titles, viewing plans and exclusions; no API keys or catalogue.",
        )

    def _translate_tree(self, widget: tk.Misc, english: bool) -> None:
        translations = UI_TEXT_EN if english else {en: ru for ru, en in UI_TEXT_EN.items()}
        for child in widget.winfo_children():
            try:
                current = child.cget("text")
                translated = translations.get(current, current)
                if current == translated:
                    for source, target in translations.items():
                        if source.endswith(": ") and current.startswith(source):
                            translated = target + current[len(source):]
                            break
                        if source.startswith(" ") and current.endswith(source):
                            translated = current[:-len(source)] + target
                            break
                if current.startswith("Онлайн (") and english:
                    translated = "Online (" + current[len("Онлайн ("):]
                elif current.startswith("Онлайн:") and english:
                    translated = "Online:" + current[len("Онлайн:"):]
                elif current.startswith("Online (") and not english:
                    translated = "Онлайн (" + current[len("Online ("):]
                elif current.startswith("Online:") and not english:
                    translated = "Онлайн:" + current[len("Online:"):]
                if translated != current:
                    child.configure(text=translated)
            except tk.TclError:
                pass
            self._translate_tree(child, english)

    def _apply_language(self) -> None:
        english = self.is_english
        self._translate_tree(self, english)
        self.title(self._text(
            f"Movie Finder — поиск фильмов {MIN_YEAR}–{MAX_YEAR}",
            f"Movie Finder — movie discovery {MIN_YEAR}–{MAX_YEAR}",
        ))
        self.language_btn.configure(text="RU" if english else "EN")
        self.subtitle_lbl.configure(text=self._text(
            f"поиск фильмов {MIN_YEAR}–{MAX_YEAR} · постер, рейтинг, описание",
            f"discover films {MIN_YEAR}–{MAX_YEAR} · poster, rating, overview",
        ))
        if hasattr(self, "backup_reminder_lbl"):
            self.backup_reminder_lbl.configure(text=self._backup_reminder_text())
        if hasattr(self, "runtime_label"):
            self.runtime_label.configure(text=self._text(
                "ДЛИТЕЛЬНОСТЬ (ОТ — ДО), МИН.", "RUNTIME (MIN — MAX), MIN"
            ))
            self.runtime_note.configure(text=self._text(
                "0 — без границы. При заданной границе фильмы с неизвестной длительностью исключаются.",
                "0 means no bound. Unknown runtimes are excluded when a bound is set.",
            ))
        if hasattr(self, "sequel_button"):
            self._refresh_sequel_indicator()
            self.sequel_check_button.configure(
                text=self._text("Проверить", "Check")
            )
        genre_code = self._genre_by_label.get(self.genre_var.get().casefold()) if hasattr(self, "genre_var") else None
        any_genre = self._text("Любой", "Any genre")
        self._genre_by_label = {any_genre.casefold(): None}
        genre_values = [any_genre]
        for name in GENRE_ORDER:
            label = GENRE_NAMES_EN.get(name, name.title()) if english else genre_label(name)
            self._genre_by_label[label.casefold()] = name
            genre_values.append(label)
        if hasattr(self, "genre_combo"):
            self.genre_combo.configure(values=genre_values)
            self.genre_var.set(next((label for label in genre_values if self._genre_by_label[label.casefold()] == genre_code), any_genre))

        country_code = self._country_by_label.get(self.country_var.get()) if hasattr(self, "country_var") else None
        any_country = self._text("Любая", "Any country")
        self._country_by_label = {any_country: None}
        country_values = [any_country]
        for code, russian in COUNTRIES.items():
            label = COUNTRIES_EN.get(code, code) if english else russian
            self._country_by_label[label] = code
            country_values.append(label)
        if hasattr(self, "country_combo"):
            self.country_combo.configure(values=[country_values[0]] + sorted(country_values[1:]))
            self.country_var.set(next((label for label, code in self._country_by_label.items() if code == country_code), any_country))

        category_key = self._category_by_label.get(self.category_var.get()) if hasattr(self, "category_var") else None
        mood_key = self._mood_by_label.get(self.mood_var.get()) if hasattr(self, "mood_var") else None
        self._category_by_label = {}
        category_values = []
        for key in ["all", *(key for key in CATEGORY_ORDER if key not in MOOD_CATEGORIES)]:
            label = category_label(key, english)
            category_values.append(label)
            self._category_by_label[label] = None if key == "all" else key
        if hasattr(self, "category_combo"):
            self.category_combo.configure(values=category_values)
            self.category_var.set(next((label for label, key in self._category_by_label.items() if key == category_key), category_values[0]))
        self._mood_by_label = {}
        mood_values = [self._text("Любое настроение", "Any mood")]
        self._mood_by_label[mood_values[0]] = None
        for key in CATEGORY_ORDER:
            if key not in MOOD_CATEGORIES:
                continue
            label = category_label(key, english)
            mood_values.append(label)
            self._mood_by_label[label] = key
        if hasattr(self, "mood_combo"):
            self.mood_combo.configure(values=mood_values)
            self.mood_var.set(next(
                (label for label, key in self._mood_by_label.items() if key == mood_key),
                mood_values[0],
            ))

        sort_key = self._sort_by_label.get(self.sort_var.get(), "rating") if hasattr(self, "sort_var") else "rating"
        self._sort_by_label = {}
        sort_values = []
        for key, russian in SORT_LABELS.items():
            label = SORT_LABELS_EN[key] if english else russian
            self._sort_by_label[label] = key
            sort_values.append(label)
        if hasattr(self, "sort_combo"):
            self.sort_combo.configure(values=sort_values)
            self.sort_var.set(next((label for label, key in self._sort_by_label.items() if key == sort_key), sort_values[0]))

        for card in self.cards:
            card.language = self.ui_language
            card.refresh_language()
        for window in list(self._windows):
            if window.winfo_exists():
                self._translate_tree(window, english)
                if isinstance(window, DetailWindow):
                    window.refresh_overview()
                elif isinstance(window, TasteStatsWindow):
                    window.refresh()
                elif isinstance(
                    window,
                    (
                        EveningPickerWindow,
                        WatchlistWindow,
                        WatchlistEditWindow,
                        RecommendationFeedbackWindow,
                        CatalogQualityWindow,
                        CollectionViewerWindow,
                        ViewingPlannerWindow,
                        PlanMovieSelectWindow,
                        PlanEditWindow,
                        SimilarMoviesWindow,
                        ContentExclusionsWindow,
                        FranchiseWindow,
                        SequelNotificationsWindow,
                    ),
                ) or callable(getattr(window, "refresh_language", None)):
                    window.refresh_language()

    def _register_window(self, window: tk.Toplevel) -> tk.Toplevel:
        if window not in self._windows:
            self._windows.append(window)
            window.bind("<Destroy>", self._forget_window, add="+")
        self._translate_tree(window, self.is_english)
        return window

    def _forget_window(self, event: tk.Event) -> None:
        if event.widget in self._windows:
            self._windows.remove(event.widget)
        for key, window in list(self._open_windows.items()):
            if window is event.widget:
                self._open_windows.pop(key, None)

    def _find_window(self, window_type: type, key: Any = None) -> tk.Toplevel | None:
        """Уже открытое окно того же типа (и того же ключа, если он задан)."""
        window = self._open_windows.get((window_type, key))
        if window is not None and window.winfo_exists():
            return window
        self._open_windows.pop((window_type, key), None)
        return None

    def _show_window(self, window_type: type, factory, key: Any = None):
        """Открывает окно один раз: повторный вызов поднимает существующее."""
        existing = self._find_window(window_type, key)
        if existing is not None:
            existing.deiconify()
            existing.lift()
            try:
                existing.focus_set()
            except tk.TclError:
                pass
            return existing
        window = factory()
        if window is not None:
            self._open_windows[(window_type, key)] = window
        return window

    def toggle_language(self) -> None:
        self.set_ui_language("ru-RU" if self.is_english else "en-US")

    def set_ui_language(self, code: str) -> None:
        """Переключает язык интерфейса и сохраняет выбор в config.json."""
        target = "en-US" if str(code).lower().startswith("en") else "ru-RU"
        if target == self.ui_language:
            return
        self.ui_language = target
        self.cfg.set("ui_language", target)
        self._apply_language()
        self._refresh_stats()
        if self.is_english:
            open_movies = [
                window.movie
                for window in list(self._detail_windows)
                if window.winfo_exists()
            ]
            self._fetch_english_overviews(open_movies)
        self.search()

    def _build_header(self) -> None:
        header = tk.Frame(self, bg=BG, height=76)
        header.pack(side="top", fill="x")
        header.pack_propagate(False)

        left = tk.Frame(header, bg=BG)
        left.pack(side="left", padx=20, pady=12)
        tk.Label(
            left, text="🎬 Movie Finder", bg=BG, fg=TEXT, font=FONT_H1
        ).pack(anchor="w")
        self.subtitle_lbl = tk.Label(
            left,
            text=self._text(
                f"поиск фильмов {MIN_YEAR}–{MAX_YEAR} · постер, рейтинг, описание",
                f"discover films {MIN_YEAR}–{MAX_YEAR} · poster, rating, overview",
            ),
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
        )
        self.subtitle_lbl.pack(anchor="w")

        right = tk.Frame(header, bg=BG)
        right.pack(side="right", padx=20, pady=12)

        self.header_stats = tk.Label(
            right, text="", bg=BG, fg=MUTED, font=(FONT, 9), justify="right"
        )
        self.header_stats.pack(side="left", padx=(0, 14))

        ttk.Button(
            right, text="Обновить базу (TMDb)", style="Ghost.TButton", command=self.open_sync
        ).pack(side="left", padx=4)
        ttk.Button(
            right, text="Обновить новинки", style="Ghost.TButton", command=self.open_novelties
        ).pack(side="left", padx=4)
        ttk.Button(
            right, text="⚙ Настройки", style="Ghost.TButton", command=self.open_settings
        ).pack(side="left", padx=4)

        self.language_btn = ttk.Button(
            right, text="RU" if self.is_english else "EN", style="Ghost.TButton",
            command=self.toggle_language,
        )
        self.language_btn.pack(side="left", padx=(4, 0))

        tk.Frame(self, bg=BORDER, height=1).pack(side="top", fill="x")

    def _build_status(self) -> None:
        status = tk.Frame(self, bg=PANEL, height=32)
        status.pack(side="bottom", fill="x")
        status.pack_propagate(False)
        self.status_lbl = tk.Label(
            status, text="Готово", bg=PANEL, fg=MUTED, font=(FONT, 9), anchor="w"
        )
        self.status_lbl.pack(side="left", padx=18)
        self.status_right = tk.Label(
            status, text="", bg=PANEL, fg=MUTED, font=(FONT, 9), anchor="e"
        )
        self.status_right.pack(side="right", padx=18)

    def _build_body(self) -> None:
        body = tk.Frame(self, bg=BG)
        body.pack(side="top", fill="both", expand=True)

        self._build_sidebar(body)

        main = tk.Frame(body, bg=BG)
        main.pack(side="left", fill="both", expand=True)

        self.footer = tk.Frame(main, bg=BG, height=46)
        self.footer.pack(side="bottom", fill="x", padx=16)
        self.footer.pack_propagate(False)
        self.more_btn = ttk.Button(
            self.footer, text="Показать ещё", style="Ghost.TButton", command=self.load_more
        )

        wrap = tk.Frame(main, bg=BG)
        wrap.pack(side="top", fill="both", expand=True, padx=(6, 10), pady=(4, 0))

        self.canvas = tk.Canvas(wrap, bg=BG, highlightthickness=0, bd=0)
        self.scrollbar = ttk.Scrollbar(
            wrap, orient="vertical", command=self.canvas.yview
        )
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)

        self.cards_frame = tk.Frame(self.canvas, bg=BG)
        self._canvas_window = self.canvas.create_window(
            (0, 0), window=self.cards_frame, anchor="nw"
        )
        self.canvas.bind("<Configure>", self._on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel, add="+")

    # ------------------------------------------------------------- сайдбар
    def _label(self, parent, text: str, *, muted: bool = True, top: int = 0) -> tk.Label:
        label = tk.Label(
            parent,
            text=text,
            bg=PANEL,
            fg=MUTED if muted else TEXT,
            font=(FONT, 8, "bold") if muted else (FONT, 9),
            anchor="w",
        )
        label.pack(fill="x", padx=16, pady=(top, 4))
        return label

    def _build_sidebar(self, parent: tk.Misc) -> None:
        sidebar_outer = tk.Frame(parent, bg=PANEL, width=286)
        sidebar_outer.pack(side="left", fill="y")
        sidebar_outer.pack_propagate(False)
        self.sidebar_canvas = tk.Canvas(sidebar_outer, bg=PANEL, highlightthickness=0, bd=0)
        self.sidebar_scrollbar = ttk.Scrollbar(
            sidebar_outer, orient="vertical", command=self.sidebar_canvas.yview
        )
        self.sidebar_canvas.configure(yscrollcommand=self.sidebar_scrollbar.set)
        self.sidebar_scrollbar.pack(side="right", fill="y")
        self.sidebar_canvas.pack(side="left", fill="both", expand=True)
        sidebar = tk.Frame(self.sidebar_canvas, bg=PANEL)
        sidebar_window = self.sidebar_canvas.create_window(
            (0, 0), window=sidebar, anchor="nw"
        )
        sidebar.bind(
            "<Configure>",
            lambda _event: self.sidebar_canvas.configure(
                scrollregion=self.sidebar_canvas.bbox("all")
            ),
        )
        self.sidebar_canvas.bind(
            "<Configure>",
            lambda event: self.sidebar_canvas.itemconfigure(sidebar_window, width=event.width),
        )
        self.sidebar_canvas.bind(
            "<MouseWheel>",
            lambda event: self.sidebar_canvas.yview_scroll(
                -1 if event.delta > 0 else 1, "units"
            ),
        )
        tk.Frame(parent, bg=BORDER, width=1).pack(side="left", fill="y")

        self._label(sidebar, "НАЗВАНИЕ", top=14)
        self.title_var = tk.StringVar()
        self.title_entry = ttk.Entry(sidebar, textvariable=self.title_var)
        self.title_entry.pack(fill="x", padx=16)
        self.title_entry.bind("<Return>", lambda _e: self.search())

        self._label(sidebar, "АКТЁР ИЛИ РЕЖИССЁР", top=9)
        self.credit_var = tk.StringVar()
        self.credit_entry = ttk.Entry(sidebar, textvariable=self.credit_var)
        self.credit_entry.pack(fill="x", padx=16)
        self.credit_entry.bind("<Return>", lambda _e: self.search())

        self._label(sidebar, "ЖАНР", top=9)
        self.genre_var = tk.StringVar(value="Любой")
        self._genre_by_label = {}
        self.genre_combo = ttk.Combobox(sidebar, textvariable=self.genre_var, state="readonly", height=12)
        self.genre_combo.pack(fill="x", padx=16)

        self._label(sidebar, "НАСТРОЕНИЕ", top=9)
        self.mood_var = tk.StringVar(value="Любое настроение")
        self.mood_combo = ttk.Combobox(sidebar, textvariable=self.mood_var, state="readonly", height=8)
        self.mood_combo.pack(fill="x", padx=16)
        self._mood_by_label = {}

        self._label(sidebar, "ТЕМА", top=9)
        self.category_var = tk.StringVar(value=CATEGORY_LABELS["all"][0])
        self.category_combo = ttk.Combobox(sidebar, textvariable=self.category_var, state="readonly", height=12)
        self.category_combo.pack(fill="x", padx=16)
        self._category_by_label = {}

        self.country_var = tk.StringVar(value="Любая")
        self._country_by_label = {}
        self.country_combo = ttk.Combobox(sidebar, textvariable=self.country_var, state="readonly", height=14)
        self.country_combo.pack(fill="x", padx=16)

        self._label(sidebar, "ГОД ВЫХОДА", top=9)
        years = tk.Frame(sidebar, bg=PANEL)
        years.pack(fill="x", padx=16)
        self.year_from_var = tk.StringVar(value=str(MIN_YEAR))
        self.year_to_var = tk.StringVar(value=str(MAX_YEAR))
        ttk.Spinbox(
            years,
            from_=MIN_YEAR,
            to=MAX_YEAR,
            textvariable=self.year_from_var,
            width=8,
        ).pack(side="left")
        tk.Label(years, text="—", bg=PANEL, fg=MUTED).pack(side="left", padx=6)
        ttk.Spinbox(
            years,
            from_=MIN_YEAR,
            to=MAX_YEAR,
            textvariable=self.year_to_var,
            width=8,
        ).pack(side="left")

        self.runtime_label = self._label(
            sidebar, "ДЛИТЕЛЬНОСТЬ (ОТ — ДО), МИН.", top=9
        )
        runtime_row = tk.Frame(sidebar, bg=PANEL)
        runtime_row.pack(fill="x", padx=16)
        self.runtime_min_var = tk.StringVar(value="0")
        self.runtime_max_var = tk.StringVar(value="0")
        ttk.Spinbox(
            runtime_row, from_=0, to=1000, increment=5,
            textvariable=self.runtime_min_var, width=7,
        ).pack(side="left")
        tk.Label(runtime_row, text="—", bg=PANEL, fg=MUTED).pack(side="left", padx=5)
        ttk.Spinbox(
            runtime_row, from_=0, to=1000, increment=5,
            textvariable=self.runtime_max_var, width=7,
        ).pack(side="left")
        self.runtime_note = tk.Label(
            sidebar, bg=PANEL, fg=MUTED, font=FONT_SMALL, anchor="w",
            justify="left", wraplength=250,
        )
        self.runtime_note.pack(fill="x", padx=16, pady=(3, 0))

        self._label(sidebar, "МИНИМАЛЬНЫЙ РЕЙТИНГ", top=9)
        rating_row = tk.Frame(sidebar, bg=PANEL)
        rating_row.pack(fill="x", padx=16)
        self.rating_var = tk.DoubleVar(value=6.0)
        self.rating_value_lbl = tk.Label(
            rating_row, text="6.0", bg=PANEL, fg=GOLD, font=(FONT, 11, "bold"), width=4
        )
        self.rating_value_lbl.pack(side="right")
        self.rating_scale = RatingSlider(
            rating_row,
            self.rating_var,
            length=180,
            command=lambda v: self.rating_value_lbl.configure(text=f"{float(v):.1f}"),
        )
        self.rating_scale.pack(side="left")

        self._label(sidebar, "ГОЛОСОВ ОТ", top=8)
        votes_row = tk.Frame(sidebar, bg=PANEL)
        votes_row.pack(fill="x", padx=16)
        self.votes_var = tk.StringVar(value="0")
        ttk.Spinbox(
            votes_row,
            from_=0,
            to=100000,
            increment=50,
            textvariable=self.votes_var,
            width=10,
        ).pack(side="left")
        tk.Label(
            votes_row, text="0 — без ограничений", bg=PANEL, fg=MUTED, font=FONT_SMALL
        ).pack(side="left", padx=8)
        self._label(sidebar, "СОРТИРОВКА", top=9)
        self.sort_var = tk.StringVar(value=SORT_LABELS["rating"])
        self._sort_by_label = {}
        self.sort_combo = ttk.Combobox(sidebar, textvariable=self.sort_var, state="readonly")
        self.sort_combo.pack(fill="x", padx=16)

        self.bookmark_only_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            sidebar,
            text="Только закладки",
            variable=self.bookmark_only_var,
            bg=PANEL,
            fg=TEXT,
            selectcolor=CARD,
            activebackground=PANEL,
            activeforeground=ACCENT,
            font=(FONT, 9),
            anchor="w",
            bd=0,
            highlightthickness=0,
            command=self.search,
        ).pack(fill="x", padx=12, pady=(10, 0))
        self.hide_watched_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            sidebar,
            text="Скрывать просмотренные",
            variable=self.hide_watched_var,
            bg=PANEL,
            fg=TEXT,
            selectcolor=CARD,
            activebackground=PANEL,
            activeforeground=ACCENT,
            font=(FONT, 9),
            anchor="w",
            bd=0,
            highlightthickness=0,
            command=self.search,
        ).pack(fill="x", padx=12, pady=(4, 0))

        self._label(sidebar, "Сохранённые фильтры", top=9)
        self.saved_filters_var = tk.StringVar(value="")
        self.saved_filters_combo = ttk.Combobox(
            sidebar, textvariable=self.saved_filters_var, state="readonly", height=8
        )
        self.saved_filters_combo.pack(fill="x", padx=16, pady=(10, 4))
        saved_buttons = tk.Frame(sidebar, bg=PANEL)
        saved_buttons.pack(fill="x", padx=16)
        ttk.Button(
            saved_buttons, text="Сохранить", style="Ghost.TButton",
            command=self.save_current_filter,
        ).pack(side="left", fill="x", expand=True)
        ttk.Button(
            saved_buttons, text="Применить", style="Ghost.TButton",
            command=self.apply_saved_filter,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))
        ttk.Button(
            saved_buttons, text="Удалить", style="Ghost.TButton",
            command=self.delete_saved_filter,
        ).pack(side="left", fill="x", expand=True, padx=(4, 0))

        buttons = tk.Frame(sidebar, bg=PANEL)
        buttons.pack(fill="x", padx=16, pady=(16, 6))
        self.search_btn = ttk.Button(
            buttons, text="Найти фильмы", style="Accent.TButton", command=self.search
        )
        self.search_btn.pack(fill="x")
        ttk.Button(
            buttons, text="Сбросить фильтры", style="Ghost.TButton", command=self.reset
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons, text="Случайный фильм", style="Ghost.TButton", command=self.open_random_movie
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons,
            text="Выбрать фильм на вечер",
            style="Ghost.TButton",
            command=self.open_evening_picker,
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons,
            text="Новые режимы и подборки",
            style="Ghost.TButton",
            command=self.open_discovery_modes,
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons, text="Рекомендации", style="Ghost.TButton", command=self.show_recommendations
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons,
            text="Режим просмотра подборки",
            style="Ghost.TButton",
            command=self.open_collection_viewer,
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons,
            text="Список «Хочу посмотреть»",
            style="Ghost.TButton",
            command=self.open_watchlist,
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons,
            text="Планировщик кинопросмотра",
            style="Ghost.TButton",
            command=self.open_viewing_planner,
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons,
            text="Скрытие нежелательного контента",
            style="Ghost.TButton",
            command=self.open_content_exclusions,
        ).pack(fill="x", pady=(8, 0))
        sequel_actions = tk.Frame(buttons, bg=PANEL)
        sequel_actions.pack(fill="x", pady=(8, 0))
        self.sequel_button = ttk.Button(
            sequel_actions, text="", style="Ghost.TButton",
            command=self.open_sequel_notifications,
        )
        self.sequel_button.pack(side="left", fill="x", expand=True)
        self.sequel_check_button = ttk.Button(
            sequel_actions, text="", style="Ghost.TButton",
            command=lambda: self.check_sequel_updates(manual=True),
        )
        self.sequel_check_button.pack(side="left", padx=(5, 0))
        self._refresh_sequel_indicator()
        ttk.Button(
            buttons,
            text="Отзывы к рекомендациям",
            style="Ghost.TButton",
            command=self.open_recommendation_feedback,
        ).pack(fill="x", pady=(8, 0))
        ttk.Button(
            buttons,
            text="Проверка качества каталога",
            style="Ghost.TButton",
            command=self.open_catalog_quality,
        ).pack(fill="x", pady=(8, 0))

        ttk.Separator(sidebar, orient="horizontal").pack(fill="x", padx=16, pady=14)

        self._label(sidebar, "БАЗА", muted=True, top=0)
        self.db_stats_lbl = tk.Label(
            sidebar,
            text="",
            bg=PANEL,
            fg=TEXT,
            font=(FONT, 9),
            justify="left",
            anchor="w",
        )
        self.db_stats_lbl.pack(fill="x", padx=16)

        tk.Label(
            sidebar,
            text="Постеры и описания — из TMDb и Википедии.",
            bg=PANEL,
            fg=MUTED,
            font=FONT_SMALL,
            justify="left",
            anchor="w",
        ).pack(fill="x", padx=16, pady=(10, 5))

        ttk.Button(
            sidebar, text="История просмотров", style="Ghost.TButton", command=self.open_history
        ).pack(fill="x", padx=16, pady=(2, 10))
        ttk.Button(
            sidebar, text="Моя статистика", style="Ghost.TButton", command=self.open_taste_stats
        ).pack(fill="x", padx=16, pady=(0, 8))
        self.backup_reminder_lbl = tk.Label(
            sidebar,
            text=self._backup_reminder_text(),
            bg=PANEL,
            fg=MUTED,
            font=FONT_SMALL,
            justify="left",
            anchor="w",
            wraplength=250,
        )
        self.backup_reminder_lbl.pack(fill="x", padx=16, pady=(0, 12))

    # ------------------------------------------------------------- фильтры
    def _collect_filters(self) -> dict[str, Any] | None:
        try:
            year_from = int(self.year_from_var.get().strip() or MIN_YEAR)
            year_to = int(self.year_to_var.get().strip() or MAX_YEAR)
        except ValueError:
            messagebox.showerror(
                "Проверьте год", f"Год должен быть числом от {MIN_YEAR} до {MAX_YEAR}.", parent=self
            )
            return None

        year_from = max(MIN_YEAR, min(MAX_YEAR, year_from))
        year_to = max(MIN_YEAR, min(MAX_YEAR, year_to))
        if year_from > year_to:
            year_from, year_to = year_to, year_from

        try:
            min_votes = int(float(self.votes_var.get().strip() or 0))
        except ValueError:
            min_votes = 0
        min_votes = max(0, min_votes)

        genre = self._genre_by_label.get(self.genre_var.get().casefold())
        category = self._category_by_label.get(self.category_var.get())
        mood = self._mood_by_label.get(self.mood_var.get())
        country = self._country_by_label.get(self.country_var.get())
        try:
            min_runtime = self._parse_runtime_bound(self.runtime_min_var)
            max_runtime = self._parse_runtime_bound(self.runtime_max_var)
        except ValueError as exc:
            messagebox.showerror(
                self._text("Проверьте длительность", "Check runtime"),
                str(exc) if not self.is_english else "Runtime must be a non-negative whole number of minutes.",
                parent=self,
            )
            return None
        if min_runtime is not None and max_runtime is not None and min_runtime > max_runtime:
            messagebox.showerror(
                self._text("Проверьте длительность", "Check runtime"),
                self._text(
                    "Минимум не может быть больше максимума.",
                    "The minimum cannot exceed the maximum.",
                ),
                parent=self,
            )
            return None

        return {
            "title": self.title_var.get().strip() or None,
            "credit": self.credit_var.get().strip() or None,
            "genre": genre,
            "category": category,
            "mood": mood,
            "country": country,
            "year_from": year_from,
            "year_to": year_to,
            "min_rating": round(float(self.rating_var.get()), 1),
            "min_votes": min_votes,
            "min_runtime": min_runtime,
            "max_runtime": max_runtime,
            "bookmarked_only": bool(self.bookmark_only_var.get()),
            "hide_watched": bool(self.hide_watched_var.get()),
            "sort": self._sort_by_label.get(self.sort_var.get(), "rating"),
        }

    def _parse_runtime_bound(self, variable: tk.StringVar) -> int | None:
        value = variable.get().strip()
        try:
            minutes = int(value or "0")
        except ValueError as exc:
            raise ValueError("Длительность должна быть целым числом минут.") from exc
        if minutes < 0:
            raise ValueError("Длительность не может быть отрицательной.")
        return minutes or None

    def reset(self) -> None:
        self.title_var.set("")
        self.credit_var.set("")
        self.genre_var.set(self._text("Любой", "Any genre"))
        self.category_var.set(self._text("Любая", "Any"))
        self.mood_var.set(self._text("Любое настроение", "Any mood"))
        self.country_var.set(self._text("Любая", "Any country"))
        self.year_from_var.set(str(MIN_YEAR))
        self.year_to_var.set(str(MAX_YEAR))
        self.runtime_min_var.set("0")
        self.runtime_max_var.set("0")
        self.rating_var.set(6.0)
        self.rating_value_lbl.configure(text="6.0")
        self.votes_var.set("0")
        self.bookmark_only_var.set(False)
        self.hide_watched_var.set(False)
        self.sort_var.set(next(label for label, key in self._sort_by_label.items() if key == "rating"))
        self.search()

    def _refresh_saved_filters(self) -> None:
        self._saved_filters_by_name = {
            entry["name"]: entry["filters"] for entry in self.db.saved_filters()
        }
        names = list(self._saved_filters_by_name)
        self.saved_filters_combo.configure(values=names)
        if self.saved_filters_var.get() not in names:
            self.saved_filters_var.set(names[0] if names else "")

    def save_current_filter(self) -> None:
        name = simpledialog.askstring(
            self._text("Сохранить фильтр", "Save filter"),
            self._text("Название подборки:", "Filter name:"),
            parent=self,
        )
        if name is None:
            return
        filters = self._collect_filters()
        if filters is None:
            return
        try:
            self.db.save_filter(name, filters)
            self._refresh_saved_filters()
            self.saved_filters_var.set(name.strip())
        except Exception as exc:
            messagebox.showerror(
                self._text("Не удалось сохранить", "Could not save"), str(exc), parent=self
            )

    def apply_saved_filter(self) -> None:
        name = self.saved_filters_var.get()
        filters = getattr(self, "_saved_filters_by_name", {}).get(name)
        if not filters:
            return
        self.title_var.set(filters.get("title") or "")
        self.credit_var.set(filters.get("credit") or "")
        self.genre_var.set(next(
            (label for label, key in self._genre_by_label.items() if key == filters.get("genre")),
            self._text("Любой", "Any genre"),
        ))
        self.category_var.set(next(
            (label for label, key in self._category_by_label.items() if key == filters.get("category")),
            self._text("Любая", "Any"),
        ))
        self.mood_var.set(next(
            (label for label, key in self._mood_by_label.items() if key == filters.get("mood")),
            self._text("Любое настроение", "Any mood"),
        ))
        self.country_var.set(next(
            (label for label, key in self._country_by_label.items() if key == filters.get("country")),
            self._text("Любая", "Any country"),
        ))
        self.year_from_var.set(str(filters.get("year_from") or MIN_YEAR))
        self.year_to_var.set(str(filters.get("year_to") or MAX_YEAR))
        self.rating_var.set(float(filters.get("min_rating") or 0))
        self.rating_value_lbl.configure(text=f"{self.rating_var.get():.1f}")
        self.votes_var.set(str(filters.get("min_votes") or 0))
        self.runtime_min_var.set(str(filters.get("min_runtime") or 0))
        self.runtime_max_var.set(str(filters.get("max_runtime") or 0))
        self.bookmark_only_var.set(bool(filters.get("bookmarked_only")))
        self.hide_watched_var.set(bool(filters.get("hide_watched")))
        sort = filters.get("sort", "rating")
        self.sort_var.set(next(
            (label for label, key in self._sort_by_label.items() if key == sort),
            next(iter(self._sort_by_label)),
        ))
        self.search()

    def delete_saved_filter(self) -> None:
        name = self.saved_filters_var.get()
        if not name:
            return
        if not messagebox.askyesno(
            self._text("Удалить подборку?", "Delete saved filter?"),
            self._text(f"Удалить «{name}»?", f"Delete “{name}”?"),
            parent=self,
        ):
            return
        if self.db.delete_filter(name):
            self._refresh_saved_filters()

    def open_random_movie(self) -> None:
        filters = self._collect_filters()
        if filters is None:
            return
        try:
            movie = self.db.random_movie(filters)
        except Exception as exc:
            messagebox.showerror(
                self._text("Ошибка выбора", "Could not pick a movie"), str(exc), parent=self
            )
            return
        if movie:
            self.open_details(movie)
        else:
            messagebox.showinfo(
                self._text("Фильмы не найдены", "No movies found"),
                self._text(
                    "По текущим фильтрам не найдено непросмотренных фильмов.",
                    "No unwatched movies match the current filters.",
                ),
                parent=self,
            )

    def open_evening_picker(self) -> None:
        self._show_window(EveningPickerWindow, lambda: EveningPickerWindow(self))

    def open_discovery_modes(self) -> None:
        from .discovery_ui import DiscoveryModesWindow

        self._show_window(DiscoveryModesWindow, lambda: DiscoveryModesWindow(self))

    def open_watchlist(self) -> None:
        self._show_window(WatchlistWindow, lambda: WatchlistWindow(self))

    def open_viewing_planner(self) -> None:
        self._show_window(ViewingPlannerWindow, lambda: ViewingPlannerWindow(self))

    def open_content_exclusions(self) -> None:
        self._show_window(ContentExclusionsWindow, lambda: ContentExclusionsWindow(self))

    def open_franchise(self, movie: dict[str, Any]) -> None:
        movie_id = int(movie.get("id") or 0)
        self._show_window(
            FranchiseWindow, lambda: FranchiseWindow(self, movie), key=movie_id
        )

    def open_sequel_notifications(self) -> None:
        self._show_window(
            SequelNotificationsWindow, lambda: SequelNotificationsWindow(self)
        )

    def _refresh_sequel_indicator(self) -> None:
        if not hasattr(self, "sequel_button"):
            return
        count = self.db.sequel_notification_count()
        self.sequel_button.configure(text=self._text(
            f"Продолжения ({count})", f"Sequels ({count})"
        ))

    def check_sequel_updates(self, *, manual: bool) -> None:
        if self._sequel_check_running:
            return
        api_key = self.cfg.api_key
        if not api_key:
            self._set_status(self._text(
                "Проверка продолжений недоступна без ключа TMDb.",
                "Sequel checks need a TMDb API key.",
            ))
            if manual and not self.suppress_dialogs:
                messagebox.showinfo(
                    self._text("Ключ TMDb не задан", "TMDb key not configured"),
                    self._text(
                        "Добавьте API-ключ TMDb в настройки, чтобы проверять продолжения.",
                        "Add a TMDb API key in Settings to check for sequels.",
                    ),
                    parent=self,
                )
            return
        self._sequel_check_running = True
        self._set_status(self._text(
            "Проверяю продолжения списка «Хочу посмотреть»…",
            "Checking watchlist sequels…",
        ))
        threading.Thread(
            target=self._sequel_check_worker,
            args=(api_key, manual),
            daemon=True,
            name="sequel-check",
        ).start()

    def _sequel_check_worker(self, api_key: str, manual: bool) -> None:
        try:
            result = check_watchlist_sequels(
                self.db,
                api_key,
                language=self.cfg.get("language") or "ru-RU",
                # Автопроверка не дёргает TMDb чаще раза в сутки на фильм.
                recheck_after_hours=0.0 if manual else 24.0,
            )
        except Exception as exc:
            self._post(lambda error=exc: self._sequel_check_failed(error, manual))
            return
        self._post(lambda: self._sequel_check_finished(result, manual))

    def _sequel_check_failed(self, error: Exception, manual: bool = False) -> None:
        self._sequel_check_running = False
        self._refresh_sequel_indicator()
        self._set_status(self._text(
            "Ошибка проверки продолжений.", "Sequel check failed."
        ))
        # Автопроверка при запуске не должна показывать модальное окно:
        # пользователь к ней не причастен, а TMDb может быть недоступен.
        if manual and not self.suppress_dialogs and not self._closing:
            messagebox.showerror(
                self._text("Ошибка TMDb", "TMDb error"), str(error), parent=self
            )

    def _sequel_check_finished(self, result: dict[str, Any], manual: bool) -> None:
        self._sequel_check_running = False
        self._refresh_sequel_indicator()
        if result["status"] == "empty_watchlist":
            message = self._text(
                "Список «Хочу посмотреть» пуст — проверять нечего.",
                "Your watchlist is empty; there is nothing to check.",
            )
        else:
            message = self._text(
                f"Проверено фильмов: {result['checked']}; новых продолжений: "
                f"{result['new_notifications']}; без подтверждённой серии: {result['unverified']}.",
                f"Movies checked: {result['checked']}; new sequels: "
                f"{result['new_notifications']}; no verified collection: {result['unverified']}.",
            )
        self._set_status(message)
        if manual and result.get("new_notifications") and not self.suppress_dialogs:
            messagebox.showinfo(
                self._text("Найдено продолжение", "Sequel found"),
                message,
                parent=self,
            )

    def open_recommendation_feedback(self) -> None:
        self._show_window(
            RecommendationFeedbackWindow, lambda: RecommendationFeedbackWindow(self)
        )

    def open_catalog_quality(self) -> None:
        self._show_window(CatalogQualityWindow, lambda: CatalogQualityWindow(self))

    def open_collection_viewer(self) -> None:
        filters = self._collect_filters()
        if filters is not None:
            self._show_window(
                CollectionViewerWindow, lambda: CollectionViewerWindow(self, filters)
            )

    def show_recommendations(self) -> None:
        try:
            rows = self.db.recommendations(PAGE_SIZE)
        except Exception as exc:
            messagebox.showerror(
                self._text("Ошибка рекомендаций", "Recommendation error"), str(exc), parent=self
            )
            return
        self._search_seq += 1
        self._showing_recommendations = True
        for movie in rows:
            movie["_recommendation"] = True
        self.search_btn.configure(state="normal")
        self.more_btn.pack_forget()
        self._clear_results()
        self._render(rows, append=False)
        self._total = len(rows)
        self._offset = len(rows)
        self._set_status(self._text(
            f"Персональные рекомендации: {len(rows)}",
            f"Personal recommendations: {len(rows)}",
        ) if rows else self._text(
            "Отметьте просмотренные фильмы и поставьте им оценку — появятся рекомендации.",
            "Mark watched movies and rate them to get recommendations.",
        ))
        self.status_right.configure(text=self._text(
            f"{self.db.count()} фильмов в базе", f"{self.db.count()} movies in database"
        ))

    # -------------------------------------------------------------- поиск
    def search(self) -> None:
        filters = self._collect_filters()
        if filters is None:
            return
        self._showing_recommendations = False
        self._filters = filters
        self._search_seq += 1
        seq = self._search_seq
        self.search_btn.configure(state="disabled")
        self.more_btn.pack_forget()
        self._set_status(self._text("Ищу фильмы…", "Searching movies…"))
        self._clear_results()
        threading.Thread(
            target=self._search_worker,
            args=(filters, 0, seq),
            daemon=True,
            name="search",
        ).start()

    def load_more(self) -> None:
        if not self._filters or self._offset >= self._total:
            return
        self.more_btn.pack_forget()
        self._set_status(self._text("Загружаю ещё…", "Loading more…"))
        threading.Thread(
            target=self._search_worker,
            args=(self._filters, self._offset, self._search_seq),
            daemon=True,
        ).start()

    def _search_worker(self, filters: dict[str, Any], offset: int, seq: int) -> None:
        try:
            rows, total = self.db.search(limit=PAGE_SIZE, offset=offset, **filters)
        except Exception as exc:  # noqa: BLE001 - показываем текст ошибки пользователю
            # error=exc обязателен: после выхода из except имя exc удаляется,
            # и лямбда в очереди UI упала бы с NameError.
            self._post(lambda error=exc: self._search_failed(error, seq))
            return
        self._post(lambda: self._on_results(rows, total, offset, seq))

    def _post(self, callback) -> None:
        """Передаёт вызов из фонового потока в главный через очередь.

        Tkinter нельзя трогать из другого потока, поэтому поток только кладёт
        функцию в очередь, а главный поток забирает её в _drain_queue.
        """
        if self._closing:
            return
        self._ui_queue.put(callback)

    def _after(self, delay_ms: int, callback) -> str:
        """`after` с учётом закрытия: все таймеры отменяются в `_on_close`."""
        after_id = self.after(delay_ms, callback)
        self._after_ids.add(after_id)
        return after_id

    def _drain_queue(self) -> None:
        try:
            if self._closing or not self.winfo_exists():
                return
        except tk.TclError:
            return  # окно уже уничтожено
        try:
            while True:
                try:
                    callback = self._ui_queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    callback()
                except tk.TclError:
                    pass  # виджет уже уничтожен
                except Exception as exc:  # noqa: BLE001 - очередь не должна умирать
                    self._report_ui_error(exc)
        finally:
            # Перевзвод обязателен: иначе один сбой в колбэке навсегда
            # останавливает обновление постеров, выдачи и описаний.
            if not self._closing:
                self._drain_id = self.after(40, self._drain_queue)

    def _report_ui_error(self, exc: BaseException) -> None:
        """Пишет сбой фонового обновления в crash.log рядом с базой."""
        import traceback
        from datetime import datetime

        text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))
        try:
            log = self.db.path.parent / "crash.log"
            with log.open("a", encoding="utf-8") as handle:
                handle.write(f"\n=== {datetime.now():%Y-%m-%d %H:%M:%S} UI ===\n{text}\n")
        except OSError:
            pass

    def _search_failed(self, exc: Exception, seq: int | None = None) -> None:
        if seq is not None and seq != self._search_seq:
            return  # устаревшая ошибка: пользователь уже запустил другой поиск
        self.search_btn.configure(state="normal")
        if self._offset and self._offset < self._total:
            self.more_btn.pack(pady=8)  # догрузка не удалась — кнопку вернуть
        self._set_status(self._text("Ошибка поиска", "Search failed"))
        messagebox.showerror(self._text("Ошибка поиска", "Search failed"), str(exc), parent=self)

    def _on_results(self, rows: list[dict], total: int, offset: int, seq: int) -> None:
        if seq != self._search_seq:
            return  # пользователь уже запустил другой поиск
        self.search_btn.configure(state="normal")
        self._total = total
        self._offset = offset + len(rows)
        self._render(rows, append=offset > 0)

        shown = self._offset if rows else 0
        if total:
            self._set_status(self._text(
                f"Найдено: {total} · показано {shown}",
                f"Found: {total} · showing {shown}",
            ))
        else:
            self._set_status(self._text(
                "Ничего не найдено — попробуйте ослабить фильтры",
                "No results — try relaxing your filters",
            ))
        self.status_right.configure(text=self._text(
            f"{self.db.count()} фильмов в базе", f"{self.db.count()} movies in database"
        ))

        if self._offset < self._total:
            self.more_btn.pack(pady=8)
        else:
            self.more_btn.pack_forget()

    def _clear_results(self) -> None:
        for card in self.cards:
            card.destroy()
        for child in self.cards_frame.winfo_children():
            child.destroy()
        self.cards = []
        self.card_by_id = {}
        self._photos = {}
        self._total = 0
        self._offset = 0
        self.canvas.yview_moveto(0)
        self.canvas.configure(scrollregion=(0, 0, 0, 0))

    def _render(self, rows: list[dict], append: bool) -> None:
        if not append:
            for child in self.cards_frame.winfo_children():
                child.destroy()
            self.cards = []
            self.card_by_id = {}

        if not rows and not self.cards:
            empty_db = self.db.count() == 0
            if empty_db:
                text = self._text(
                    "База фильмов пуста.\n\n"
                    "Нажмите «Обновить базу (TMDb)» вверху справа и вставьте\n"
                    "бесплатный API-ключ TMDb — база наполнится за несколько минут.\n\n"
                    "Либо соберите офлайн-каталог:  python tools/build_catalog.py",
                    "The movie database is empty.\n\n"
                    "Click “Update database (TMDb)” above and enter a free TMDb API key.\n"
                    "The database will fill in a few minutes.\n\n"
                    "Or build an offline catalogue: python tools/build_catalog.py",
                )
            else:
                text = self._text(
                    "Ничего не найдено.\n\n"
                    "Измените год, жанр или минимальный рейтинг\n"
                    "и нажмите «Найти фильмы».",
                    "No movies found.\n\n"
                    "Adjust the year, genre or minimum rating\n"
                    "and click “Find movies”.",
                )
            hint = tk.Label(
                self.cards_frame,
                text=text,
                bg=BG,
                fg=MUTED,
                font=(FONT, 11),
                justify="center",
            )
            hint.pack(pady=60)
            self.canvas.configure(scrollregion=self.canvas.bbox("all"))
            return

        for movie in rows:
            movie["_english_api_available"] = self._english_api_available
            card = MovieCard(
                self.cards_frame, movie, self.open_details, self.placeholder_photo,
                language=self.ui_language, on_personal_state=self._save_card_personal_state,
                on_watchlist=self._save_watchlist_state,
                on_watchlist_edit=self._edit_watchlist_movie,
                on_feedback=self._save_recommendation_feedback,
            )
            self.cards.append(card)
            self.card_by_id[int(movie["id"])] = card

        self._relayout()
        for movie in rows:
            self.poster_pool.submit(self._load_card_poster, movie)
        if self.is_english:
            self._fetch_english_overviews(rows)

    # ------------------------------------------------------------- сетка
    def _on_canvas_configure(self, event: tk.Event) -> None:
        if event.width > 50:
            self.canvas.itemconfigure(self._canvas_window, width=event.width)
        if abs(event.width - self._last_width) < 6:
            return
        self._last_width = event.width
        # Отменяем предыдущую отложенную перекладку: при частом ресайзе они
        # копились и срабатывали по уже устаревшей ширине.
        if self._relayout_id:
            try:
                self.after_cancel(self._relayout_id)
            except tk.TclError:
                pass
        self._relayout_id = self.after(100, self._relayout)

    def _relayout(self) -> None:
        width = self.canvas.winfo_width()
        if width <= 1:
            width = 900
        step = MovieCard.WIDTH + 12
        cols = max(1, int((width - 10) // step))
        for index, card in enumerate(self.cards):
            row, col = divmod(index, cols)
            card.grid(row=row, column=col, padx=6, pady=7, sticky="n")
        for col in range(cols):
            self.cards_frame.grid_columnconfigure(col, weight=1, uniform=f"col{col}")
        self.cards_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    # ------------------------------------------------------------ постеры
    def _load_card_poster(self, movie: dict[str, Any]) -> None:
        image = self.posters.image(movie, MovieCard.POSTER_SIZE)
        if image is None:
            return
        self._post(lambda: self._apply_poster(int(movie["id"]), image))

    def _apply_poster(self, movie_id: int, image) -> None:
        card = self.card_by_id.get(movie_id)
        if card is None or not card.winfo_exists():
            return
        photo = ImageTk.PhotoImage(image)
        self._photos[movie_id] = photo
        card.set_poster(photo)

    # ------------------------------------------------------------- детали
    def open_details(self, movie: dict[str, Any]) -> None:
        movie_id = int(movie.get("id") or 0)
        try:
            window = self._show_window(
                DetailWindow, lambda: DetailWindow(self, movie), key=movie_id
            )
        except Exception as exc:  # noqa: BLE001 - окно не должно ронять приложение
            self._report_ui_error(exc)
            messagebox.showerror(
                self._text("Не удалось открыть фильм", "Could not open movie"),
                str(exc),
                parent=self,
            )
            return
        if self.is_english and window is not None:
            self._fetch_english_overviews([movie])

    def _save_card_personal_state(
        self, movie_id: int, watched: bool, personal_rating: int | None
    ) -> bool:
        try:
            self.db.set_personal_state(
                movie_id, watched=watched, personal_rating=personal_rating
            )
        except Exception as exc:
            messagebox.showerror(
                self._text("Не удалось сохранить", "Could not save"),
                str(exc),
                parent=self,
            )
            return False
        self._refresh_personal_state_views(movie_id, watched, personal_rating)
        return True

    def _save_watchlist_state(
        self, movie_id: int, watchlisted: bool, priority: int = 3, note: str = ""
    ) -> bool:
        try:
            if watchlisted:
                # Карточка добавляет фильм со значениями по умолчанию: уже
                # выставленные приоритет и заметку не затираем.
                self.db.add_to_watchlist(movie_id, priority=priority, note=note)
            else:
                self.db.remove_from_watchlist(movie_id)
        except Exception as exc:
            messagebox.showerror(
                self._text("Не удалось сохранить", "Could not save"),
                str(exc),
                parent=self,
            )
            return False
        self._refresh_watchlist_views(movie_id)
        if self._showing_recommendations:
            self.show_recommendations()
        return True

    def _refresh_watchlist_views(self, movie_id: int | None = None) -> None:
        if movie_id is not None:
            card = self.card_by_id.get(movie_id)
            if card is not None:
                card.set_watchlist_status(self.db.watchlist_entry(movie_id) is not None)
            for window in list(self._detail_windows):
                if window.winfo_exists() and window.movie_id == movie_id:
                    window._refresh_watchlist()
        for window in list(self._windows):
            if isinstance(window, WatchlistWindow) and window.winfo_exists():
                window.refresh()

    def _edit_watchlist_movie(self, movie: dict[str, Any]) -> None:
        WatchlistEditWindow(self, movie)

    def _save_recommendation_feedback(self, movie_id: int, feedback: str | None) -> bool:
        try:
            self.db.set_recommendation_feedback(movie_id, feedback)
        except Exception as exc:
            messagebox.showerror(
                self._text("Не удалось сохранить", "Could not save"),
                str(exc),
                parent=self,
            )
            return False
        for window in list(self._windows):
            if isinstance(window, RecommendationFeedbackWindow) and window.winfo_exists():
                window.refresh()
        if self._showing_recommendations:
            self.show_recommendations()
        return True

    def _refresh_personal_state_views(
        self, movie_id: int, watched: bool, personal_rating: int | None
    ) -> None:
        card = self.card_by_id.get(movie_id)
        if card is not None:
            card.update_personal_state(watched, personal_rating)
        for window in list(self._detail_windows):
            if window.winfo_exists() and window.movie_id == movie_id:
                window.movie["watched"] = int(watched)
                window.movie["personal_rating"] = personal_rating
                window._refresh_personal_controls()
        self._refresh_stats()
        if self._showing_recommendations:
            self.show_recommendations()
        elif self.hide_watched_var.get():
            self.search()

    # ---------------------------------------------------------- вспомогательное
    def _fetch_english_overviews(self, rows: list[dict[str, Any]]) -> None:
        candidates: list[dict[str, Any]] = []
        with self._overview_pending_lock:
            for movie in rows:
                movie_id = int(movie.get("id") or 0)
                if movie_id == 0 or movie.get("overview_en_checked") or movie_id in self._overview_pending:
                    continue
                self._overview_pending.add(movie_id)
                candidates.append(movie)
        if not candidates:
            return
        if not self.cfg.api_key:
            with self._overview_pending_lock:
                self._overview_pending.difference_update(int(row["id"]) for row in candidates)
            self._english_api_available = False
            for movie in candidates:
                movie["_english_api_available"] = False
                card = self.card_by_id.get(int(movie["id"]))
                if card:
                    card.set_overview()
            self._set_status(self._text(
                "Для английских описаний добавьте ключ TMDb в настройках.",
                "Add a TMDb API key in Settings to load English descriptions.",
            ))
            return
        client = TMDBClient(self.cfg.api_key, "en-US")
        self._english_api_available = True
        for movie in candidates:
            self.overview_pool.submit(self._fetch_english_overview, client, movie)

    @staticmethod
    def _normalized_title(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value or "").casefold()
        return re.sub(r"[^\w]+", "", normalized, flags=re.UNICODE)

    def _english_tmdb_id(self, client: TMDBClient, movie: dict[str, Any]) -> int | None:
        movie_id = int(movie.get("id") or 0)
        year = str(movie.get("year") or "")
        if movie.get("source") == "tmdb" and movie_id > 0:
            return movie_id
        imdb_id = str(movie.get("imdb_id") or "").strip()
        if imdb_id:
            found = client.get(f"/find/{imdb_id}", external_source="imdb_id")
            matches = [item for item in (found.get("movie_results") or []) if item.get("id")]
            matches.sort(key=lambda item: (
                str(item.get("release_date") or "")[:4] == year,
                bool(item.get("overview")),
            ), reverse=True)
            if matches:
                return int(matches[0]["id"])
        wanted = {
            self._normalized_title(str(movie.get("title") or "")),
            self._normalized_title(str(movie.get("original_title") or "")),
        } - {""}
        if not wanted or not year:
            return None
        for query in dict.fromkeys((movie.get("original_title"), movie.get("title"))):
            if not query:
                continue
            result = client.get("/search/movie", query=str(query), primary_release_year=year, include_adult="false")
            for match in result.get("results") or []:
                names = {
                    self._normalized_title(str(match.get("title") or "")),
                    self._normalized_title(str(match.get("original_title") or "")),
                } - {""}
                if (str(match.get("release_date") or "")[:4] == year
                        and wanted.intersection(names) and match.get("id")):
                    return int(match["id"])
        return None

    def _fetch_english_overview(self, client: TMDBClient, movie: dict[str, Any]) -> None:
        movie_id = int(movie["id"])
        try:
            tmdb_id = self._english_tmdb_id(client, movie)
            details = client.get(f"/movie/{tmdb_id}") if tmdb_id else {}
            overview = (details.get("overview") or "").strip()
            self.db.set_english_overview(movie_id, overview)
            movie["overview_en"] = overview
            movie["overview_en_checked"] = 1
        except Exception as exc:
            self._post(lambda mid=movie_id, error=exc: self._english_overview_failed(mid, error))
        else:
            self._post(lambda mid=movie_id, text=overview: self._apply_english_overview(mid, text))
        finally:
            with self._overview_pending_lock:
                self._overview_pending.discard(movie_id)

    def _english_overview_failed(self, movie_id: int, error: Exception) -> None:
        card = self.card_by_id.get(movie_id)
        if card is not None:
            card.movie["_english_overview_error"] = True
            card.set_overview()
        for window in list(self._detail_windows):
            if window.winfo_exists() and int(window.movie.get("id") or 0) == movie_id:
                window.movie["_english_overview_error"] = True
                window.refresh_overview()
        self._set_status(self._text(
            f"Не удалось загрузить английское описание: {error}",
            f"Could not load English description: {error}",
        ))

    def _apply_english_overview(self, movie_id: int, overview: str) -> None:
        card = self.card_by_id.get(movie_id)
        if card is not None:
            card.movie["overview_en"] = overview
            card.movie["overview_en_checked"] = 1
            card.set_overview()
        for window in list(self._detail_windows):
            if window.winfo_exists() and int(window.movie.get("id") or 0) == movie_id:
                window.movie["overview_en"] = overview
                window.movie["overview_en_checked"] = 1
                window.refresh_overview()

    def localized_overview(self, movie: dict[str, Any]) -> str:
        if self.is_english:
            overview = (movie.get("overview_en") or "").strip()
            if overview:
                return overview
            if movie.get("_english_overview_error"):
                return "English description could not be loaded. Search again to retry."
            if movie.get("overview_en_checked"):
                return "No English description available."
            if not self.cfg.api_key:
                return "Add a TMDb API key in Settings to load English descriptions."
            return "Loading English description…"
        return (movie.get("overview") or "").strip() or "Описание отсутствует."

    def _set_status(self, text: str) -> None:
        self.status_lbl.configure(text=text)

    def _refresh_stats(self) -> None:
        try:
            stats = self.db.stats()
        except Exception as exc:  # noqa: BLE001 - статистика не должна ронять окно
            self.db_stats_lbl.configure(text=self._text("База недоступна", "Database unavailable"))
            self.header_stats.configure(text=self._text("нет данных", "no data"))
            self.status_right.configure(text=str(exc)[:60])
            return
        total = stats["total"]
        if total:
            years = (
                f"{stats['min_year']}–{stats['max_year']}"
                if stats["min_year"] and stats["max_year"]
                else "—"
            )
            local_posters = stats["with_poster"]
            remote = max(0, stats.get("with_poster_any", local_posters) - local_posters)
            poster_line = self._text(
                f"Постеров: {local_posters} (+{remote})" if remote else f"Постеров: {local_posters}",
                f"Posters: {local_posters} (+{remote})" if remote else f"Posters: {local_posters}",
            )
            pretty_total = f"{total:,}".replace(",", " ")
            self.db_stats_lbl.configure(text=self._text(
                f"Фильмов: {pretty_total}  ·  годы {years}\n{poster_line}",
                f"Movies: {pretty_total}  ·  years {years}\n{poster_line}",
            ))
            self.header_stats.configure(text=self._text(
                f"{pretty_total} фильмов · {years}", f"{pretty_total} movies · {years}"
            ))
        else:
            self.db_stats_lbl.configure(text=self._text("База пуста.\nОбновите её из TMDb.", "Database is empty.\nUpdate it from TMDb."))
            self.header_stats.configure(text=self._text("база пуста", "database is empty"))
        self.status_right.configure(text=self._text(f"{total} фильмов в базе", f"{total} movies in database"))

    def open_taste_stats(self) -> None:
        self._show_window(
            TasteStatsWindow, lambda: self._register_window(TasteStatsWindow(self))
        )

    def _on_mousewheel(self, event: tk.Event) -> None:
        widget = self.winfo_containing(event.x_root, event.y_root)
        if widget is None or not self._is_inside(widget, self.canvas):
            return
        delta = -1 if event.delta > 0 else 1
        self.canvas.yview_scroll(delta * 2, "units")

    def _relocate_database(self, source: Path, issue: str) -> Path | None:
        """Если рядом с программой писать нельзя — переносим базу в профиль."""
        from .config import fallback_data_dir

        try:
            target_dir = fallback_data_dir()
            target = target_dir / "movies.db"
            if source.resolve() == target.resolve():
                return None
            self.db.backup_to(target)
            self.db.close()
            self.db = MovieDB(target, defer_index=True)
            self.data_note = (
                "Папка рядом с программой недоступна для записи, поэтому база "
                f"перенесена в:\n{target_dir}\n\n"
                "Поиск и обновление из TMDb работают как обычно, постеры из "
                "комплекта подхватываются из папки программы."
            )
            return target
        except Exception:  # noqa: BLE001 - остаёмся на прежней базе
            return None

    def _show_data_note(self) -> None:
        if not self.data_note:
            return
        self._set_status("База перенесена в профиль пользователя")
        if not self.suppress_dialogs:
            messagebox.showinfo("База перенесена", self.data_note, parent=self)

    def _warm_search_index(self) -> None:
        """Строит индекс поиска по опечаткам в фоне, не задерживая запуск."""
        time.sleep(1.5)  # первый поиск и отрисовка должны пройти раньше
        try:
            self.db.ensure_title_gram_index()
        except Exception:  # noqa: BLE001 - без индекса поиск просто строже
            return

    def _dedupe_once(self) -> None:
        """Убирает офлайн-записи, которые уже пришли из TMDb (идемпотентно)."""
        try:
            removed = self.db.remove_wiki_duplicates()
        except Exception:  # noqa: BLE001 - база может быть только для чтения
            return
        if removed:
            self._refresh_stats()
            self.search()

    def _check_writable(self) -> None:
        """Предупреждает, если база доступна только для чтения."""
        issue = self.db.check_writable()
        if not issue:
            return
        self._set_status("База доступна только для чтения — изменения не сохранятся")
        self.status_right.configure(text="нет доступа к data/")
        if self.suppress_dialogs:
            return
        messagebox.showwarning(
            "Нет доступа к папке data",
            "База фильмов открыта только для чтения.\n\n"
            f"{issue}\n\n"
            "Поиск будет работать, но обновление базы из TMDb и сохранение "
            "постеров — нет.\n"
            f"Файл базы: {DB_PATH}",
            parent=self,
        )

    @staticmethod
    def _is_inside(widget: tk.Misc, parent: tk.Misc) -> bool:
        current: Any = widget
        while current is not None:
            if current is parent:
                return True
            current = getattr(current, "master", None)
        return False

    # ------------------------------------------------------------ диалоги
    def open_settings(self) -> None:
        self._show_window(
            SettingsWindow, lambda: self._register_window(SettingsWindow(self))
        )

    def open_sync(self) -> None:
        self._show_window(
            SyncWindow, lambda: self._register_window(SyncWindow(self)), key=False
        )

    def open_novelties(self) -> None:
        self._show_window(
            SyncWindow,
            lambda: self._register_window(SyncWindow(self, recent_only=True)),
            key=True,
        )

    def open_history(self) -> None:
        self._show_window(
            HistoryWindow, lambda: self._register_window(HistoryWindow(self))
        )

    def _on_close(self) -> None:
        self._closing = True
        try:
            self.cfg.set("window_geometry", self.geometry())
        except Exception:  # noqa: BLE001 - закрытие не должно падать
            pass
        for after_id in list(self._after_ids):
            try:
                self.after_cancel(after_id)
            except tk.TclError:
                pass
        self._after_ids.clear()
        for recurring_id in (self._drain_id, self._relayout_id):
            if recurring_id:
                try:
                    self.after_cancel(recurring_id)
                except tk.TclError:
                    pass
        self._drain_id = self._relayout_id = ""
        # Даём фоновой синхронизации остановиться до закрытия базы.
        for window in list(self._windows):
            job = getattr(window, "job", None)
            if job is not None and getattr(job, "running", False):
                try:
                    job.cancel()
                    job.wait(3.0)
                except Exception:  # noqa: BLE001 - закрытие важнее
                    pass
        self.poster_pool.shutdown(wait=False, cancel_futures=True)
        self.overview_pool.shutdown(wait=False, cancel_futures=True)
        try:
            self.db.close()
        except Exception:  # noqa: BLE001 - соединение могло уже закрыться
            pass
        self.destroy()


class WatchlistWindow(tk.Toplevel):
    """A separate, editable view of the user's watchlist."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.title(self._text("Список «Хочу посмотреть»", "Watchlist"))
        self.geometry("850x500")
        self.minsize(700, 380)
        self.configure(bg=BG)
        self.transient(app)

        self.summary = tk.Label(self, bg=BG, fg=MUTED, font=FONT_TEXT, anchor="w")
        self.summary.pack(fill="x", padx=16, pady=(14, 8))
        self.tree = ttk.Treeview(
            self, columns=("priority", "title", "year", "note"), show="headings",
            selectmode="browse",
        )
        self.tree.pack(fill="both", expand=True, padx=16)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_actions())
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())

        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=16, pady=12)
        self.open_btn = ttk.Button(actions, style="Accent.TButton", command=self._open_selected)
        self.open_btn.pack(side="left")
        self.remove_btn = ttk.Button(
            actions, style="Ghost.TButton", command=self._remove_selected
        )
        self.remove_btn.pack(side="left", padx=(8, 0))
        self.close_btn = ttk.Button(actions, style="Ghost.TButton", command=self.destroy)
        self.close_btn.pack(side="right")
        self.refresh_language()
        self.refresh()
        app._register_window(self)

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def refresh_language(self) -> None:
        self.title(self._text("Список «Хочу посмотреть»", "Watchlist"))
        for column, russian, english, width in (
            ("priority", "Приоритет", "Priority", 90),
            ("title", "Фильм", "Movie", 250),
            ("year", "Год", "Year", 70),
            ("note", "Заметка", "Note", 360),
        ):
            self.tree.heading(column, text=self._text(russian, english))
            self.tree.column(column, width=width, anchor="w")
        self.open_btn.configure(text=self._text("Открыть фильм", "Open movie"))
        self.remove_btn.configure(text=self._text("Удалить из списка", "Remove from list"))
        self.close_btn.configure(text=self._text("Закрыть", "Close"))
        self.refresh()

    def refresh(self) -> None:
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            rows = self.app.db.watchlist()
        except Exception as exc:
            messagebox.showerror(
                self._text("Ошибка списка", "Watchlist error"), str(exc), parent=self
            )
            rows = []
        self.summary.configure(text=self._text(
            f"В списке: {len(rows)} · фильмы упорядочены по приоритету",
            f"Items: {len(rows)} · sorted by priority",
        ))
        for movie in rows:
            movie_id = int(movie["id"])
            self.tree.insert(
                "", "end", iid=str(movie_id),
                values=(
                    movie["watchlist_priority"], movie.get("title") or "",
                    movie.get("year") or "—", movie.get("watchlist_note") or "",
                ),
            )
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
        self._sync_actions()

    def _selected_id(self) -> int | None:
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def _sync_actions(self) -> None:
        enabled = "normal" if self._selected_id() is not None else "disabled"
        self.open_btn.configure(state=enabled)
        self.remove_btn.configure(state=enabled)

    def _open_selected(self) -> None:
        movie_id = self._selected_id()
        movie = self.app.db.get(movie_id) if movie_id is not None else None
        if movie:
            self.app.open_details(movie)

    def _remove_selected(self) -> None:
        movie_id = self._selected_id()
        if movie_id is not None and self.app._save_watchlist_state(
            movie_id, False
        ):
            self.refresh()


class WatchlistEditWindow(tk.Toplevel):
    """Edits one watchlist entry without coupling it to catalogue fields."""

    def __init__(self, app: MovieApp, movie: dict[str, Any]) -> None:
        super().__init__(app)
        self.app = app
        self.movie_id = int(movie["id"])
        self.title(self._text("Список «Хочу посмотреть»", "Watchlist"))
        self.geometry("460x340")
        self.minsize(420, 300)
        self.configure(bg=BG)
        self.transient(app)
        self.entry = app.db.watchlist_entry(self.movie_id)

        tk.Label(
            self, text=movie.get("title") or "", bg=BG, fg=TEXT,
            font=(FONT, 12, "bold"), anchor="w", wraplength=420,
        ).pack(fill="x", padx=18, pady=(18, 12))
        self.priority_label = tk.Label(
            self, text=self._text(
                "Приоритет (1–5, 5 — высокий):", "Priority (1–5, 5 is highest):"
            ),
            bg=BG, fg=MUTED, anchor="w",
        )
        self.priority_label.pack(fill="x", padx=18)
        self.priority_var = tk.StringVar(
            value=str((self.entry or {}).get("priority", 3))
        )
        self.priority_combo = ttk.Combobox(
            self, textvariable=self.priority_var, values=tuple(str(n) for n in range(1, 6)),
            state="readonly", width=8,
        )
        self.priority_combo.pack(anchor="w", padx=18, pady=(4, 12))
        self.note_label = tk.Label(
            self, text=self._text("Заметка:", "Note:"), bg=BG, fg=MUTED, anchor="w"
        )
        self.note_label.pack(fill="x", padx=18)
        self.note_text = tk.Text(
            self, height=6, bg=CARD, fg=TEXT, insertbackground=TEXT, wrap="word",
            highlightthickness=1, highlightbackground=BORDER, bd=0,
        )
        self.note_text.pack(fill="both", expand=True, padx=18, pady=(4, 12))
        self.note_text.insert("1.0", (self.entry or {}).get("note", ""))
        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=18, pady=(0, 16))
        self.save_btn = ttk.Button(
            buttons, style="Accent.TButton", command=self._save
        )
        self.save_btn.pack(side="left")
        self.remove_btn = ttk.Button(
            buttons, style="Ghost.TButton", command=self._remove
        )
        self.remove_btn.pack(side="left", padx=(8, 0))
        self.close_btn = ttk.Button(buttons, style="Ghost.TButton", command=self.destroy)
        self.close_btn.pack(side="right")
        self.refresh_language()
        app._register_window(self)

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def refresh_language(self) -> None:
        self.title(self._text("Список «Хочу посмотреть»", "Watchlist"))
        self.priority_label.configure(text=self._text(
            "Приоритет (1–5, 5 — высокий):", "Priority (1–5, 5 is highest):"
        ))
        self.note_label.configure(text=self._text("Заметка:", "Note:"))
        self.save_btn.configure(text=self._text("Сохранить", "Save"))
        self.remove_btn.configure(text=self._text("Удалить из списка", "Remove from list"))
        self.close_btn.configure(text=self._text("Закрыть", "Close"))
        self.remove_btn.configure(state="normal" if self.entry else "disabled")

    def _save(self) -> None:
        try:
            priority = int(self.priority_var.get())
            note = self.note_text.get("1.0", "end-1c")
            self.app.db.set_watchlist(self.movie_id, priority=priority, note=note)
        except Exception as exc:
            messagebox.showerror(
                self._text("Не удалось сохранить", "Could not save"), str(exc), parent=self
            )
            return
        self.app._refresh_watchlist_views(self.movie_id)
        self.destroy()

    def _remove(self) -> None:
        if self.entry and self.app._save_watchlist_state(self.movie_id, False):
            self.destroy()


class RecommendationFeedbackWindow(tk.Toplevel):
    """Lists prior recommendation feedback so it can be reviewed or cleared."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.title(self._text("Отзывы к рекомендациям", "Recommendation feedback"))
        self.geometry("700x440")
        self.minsize(580, 340)
        self.configure(bg=BG)
        self.transient(app)
        self.summary = tk.Label(self, bg=BG, fg=MUTED, font=FONT_TEXT, anchor="w")
        self.summary.pack(fill="x", padx=16, pady=(14, 8))
        self.tree = ttk.Treeview(
            self, columns=("feedback", "title", "year"), show="headings",
            selectmode="browse",
        )
        self.tree.pack(fill="both", expand=True, padx=16)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_actions())
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())
        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=16, pady=12)
        self.open_btn = ttk.Button(actions, style="Ghost.TButton", command=self._open_selected)
        self.open_btn.pack(side="left")
        self.clear_btn = ttk.Button(actions, style="Ghost.TButton", command=self._clear_selected)
        self.clear_btn.pack(side="left", padx=(8, 0))
        self.close_btn = ttk.Button(actions, style="Ghost.TButton", command=self.destroy)
        self.close_btn.pack(side="right")
        self.refresh_language()
        app._register_window(self)

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def refresh_language(self) -> None:
        self.title(self._text("Отзывы к рекомендациям", "Recommendation feedback"))
        for column, russian, english, width in (
            ("feedback", "Отзыв", "Feedback", 120),
            ("title", "Фильм", "Movie", 390),
            ("year", "Год", "Year", 80),
        ):
            self.tree.heading(column, text=self._text(russian, english))
            self.tree.column(column, width=width, anchor="w")
        self.open_btn.configure(text=self._text("Открыть фильм", "Open movie"))
        self.clear_btn.configure(text=self._text("Удалить отзыв", "Clear feedback"))
        self.close_btn.configure(text=self._text("Закрыть", "Close"))
        self.refresh()

    def refresh(self) -> None:
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.tree.get_children():
            self.tree.delete(item)
        rows = self.app.db.recommendation_feedback()
        self.summary.configure(text=self._text(
            f"Сохранено отзывов: {len(rows)}",
            f"Saved feedback: {len(rows)}",
        ))
        for movie in rows:
            value = movie["recommendation_feedback"]
            label = self._text("Подходит", "Fits me") if value == "like" else self._text("Не моё", "Not for me")
            self.tree.insert(
                "", "end", iid=str(movie["id"]),
                values=(label, movie.get("title") or "", movie.get("year") or "—"),
            )
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
        self._sync_actions()

    def _selected_id(self) -> int | None:
        selection = self.tree.selection()
        return int(selection[0]) if selection else None

    def _sync_actions(self) -> None:
        enabled = "normal" if self._selected_id() is not None else "disabled"
        self.open_btn.configure(state=enabled)
        self.clear_btn.configure(state=enabled)

    def _open_selected(self) -> None:
        movie_id = self._selected_id()
        movie = self.app.db.get(movie_id) if movie_id is not None else None
        if movie:
            self.app.open_details(movie)

    def _clear_selected(self) -> None:
        movie_id = self._selected_id()
        if movie_id is not None and self.app._save_recommendation_feedback(
            movie_id, None
        ):
            self.refresh()


class CatalogQualityWindow(tk.Toplevel):
    """Read-only report over suspicious catalogue metadata."""

    FLAG_LABELS = {
        "duplicate_title": ("Похожее название", "Possible duplicate title"),
        "missing_year": ("Год не указан", "Year missing"),
        "invalid_year": ("Подозрительный год", "Suspicious year"),
        "year_mismatch": ("Год не совпадает с датой", "Year differs from release date"),
        "empty_description": ("Пустое описание", "Empty description"),
        "short_description": ("Слишком короткое описание", "Description is too short"),
    }

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.title(self._text("Проверка качества каталога", "Catalogue quality check"))
        self.geometry("920x500")
        self.minsize(720, 380)
        self.configure(bg=BG)
        self.transient(app)
        self.summary = tk.Label(self, bg=BG, fg=MUTED, font=FONT_TEXT, anchor="w")
        self.summary.pack(fill="x", padx=16, pady=(14, 8))
        self.tree = ttk.Treeview(
            self, columns=("title", "year", "source", "flags"), show="headings",
            selectmode="browse",
        )
        self.tree.pack(fill="both", expand=True, padx=16)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_actions())
        self.tree.bind("<Double-1>", lambda _event: self._open_selected())
        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=16, pady=12)
        self.open_btn = ttk.Button(actions, style="Accent.TButton", command=self._open_selected)
        self.open_btn.pack(side="left")
        self.close_btn = ttk.Button(actions, style="Ghost.TButton", command=self.destroy)
        self.close_btn.pack(side="right")
        self.refresh_language()
        self.refresh()
        app._register_window(self)

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def refresh_language(self) -> None:
        self.title(self._text("Проверка качества каталога", "Catalogue quality check"))
        for column, russian, english, width in (
            ("title", "Фильм", "Movie", 260),
            ("year", "Год", "Year", 70),
            ("source", "Источник", "Source", 150),
            ("flags", "Проблемы", "Issues", 380),
        ):
            self.tree.heading(column, text=self._text(russian, english))
            self.tree.column(column, width=width, anchor="w")
        self.open_btn.configure(text=self._text("Открыть фильм", "Open movie"))
        self.close_btn.configure(text=self._text("Закрыть", "Close"))
        self.refresh()

    def refresh(self) -> None:
        selected = self.tree.selection()
        selected_id = selected[0] if selected else None
        for item in self.tree.get_children():
            self.tree.delete(item)
        try:
            rows = self.app.db.catalog_quality_issues()
        except Exception as exc:
            messagebox.showerror(
                self._text("Ошибка проверки", "Quality check failed"), str(exc), parent=self
            )
            rows = []
        self.summary.configure(text=(
            self._text("Проверка только читает каталог; исправления не выполняются. ",
                       "This report only reads the catalogue; it makes no changes. ")
            + self._text(f"Записей с замечаниями: {len(rows)}",
                         f"Records with issues: {len(rows)}")
        ))
        for row in rows:
            labels = [
                self._text(*self.FLAG_LABELS[flag])
                for flag in row["flags"]
            ]
            self.tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["title"], row["year"] or "—",
                    row["source"] or self._text("Не указан", "Not specified"),
                    ", ".join(labels),
                ),
            )
        if not rows:
            self.tree.insert(
                "", "end", iid="empty",
                values=(self._text("Проверка не нашла проблем.", "No catalogue issues found."),
                        "", "", ""),
            )
        if selected_id and self.tree.exists(selected_id):
            self.tree.selection_set(selected_id)
        self._sync_actions()

    def _selected_id(self) -> int | None:
        selection = self.tree.selection()
        if not selection or selection[0] == "empty":
            return None
        return int(selection[0])

    def _sync_actions(self) -> None:
        self.open_btn.configure(
            state="normal" if self._selected_id() is not None else "disabled"
        )

    def _open_selected(self) -> None:
        movie_id = self._selected_id()
        movie = self.app.db.get(movie_id) if movie_id is not None else None
        if movie:
            self.app.open_details(movie)


class CollectionViewerWindow(tk.Toplevel):
    """Steps through the current filtered set, always excluding watched films."""

    def __init__(self, app: MovieApp, filters: dict[str, Any]) -> None:
        super().__init__(app)
        self.app = app
        self.index = 0
        try:
            self.movies = app.db.collection_queue(filters)
        except Exception as exc:
            messagebox.showerror(
                self._text("Ошибка подборки", "Collection error"), str(exc), parent=app
            )
            self.destroy()
            return
        self.title(self._text("Режим просмотра подборки", "Collection viewer"))
        self.geometry("620x460")
        self.minsize(520, 390)
        self.configure(bg=BG)
        self.transient(app)
        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=20)
        self.progress = tk.Label(body, bg=BG, fg=MUTED, font=FONT_TEXT, anchor="w")
        self.progress.pack(fill="x", pady=(0, 12))
        self.title_label = tk.Label(
            body, bg=CARD, fg=TEXT, font=FONT_H1, justify="left", anchor="w",
            wraplength=550, padx=16, pady=16,
        )
        self.title_label.pack(fill="x")
        self.meta_label = tk.Label(body, bg=BG, fg=GOLD, font=FONT_TEXT, anchor="w")
        self.meta_label.pack(fill="x", pady=(10, 8))
        self.overview_label = tk.Label(
            body, bg=BG, fg=MUTED, font=FONT_TEXT, justify="left", anchor="nw",
            wraplength=560,
        )
        self.overview_label.pack(fill="both", expand=True)
        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(18, 0))
        self.watched_btn = ttk.Button(
            actions, style="Accent.TButton", command=self._mark_watched
        )
        self.watched_btn.pack(side="left", fill="x", expand=True)
        self.rating_var = tk.StringVar(value="8")
        self.rating_combo = ttk.Combobox(
            actions, textvariable=self.rating_var, values=tuple(str(n) for n in range(1, 11)),
            state="readonly", width=4,
        )
        self.rating_combo.pack(side="left", padx=(8, 4))
        self.rate_btn = ttk.Button(
            actions, style="Ghost.TButton", command=self._rate_and_next
        )
        self.rate_btn.pack(side="left")
        self.skip_btn = ttk.Button(
            actions, style="Ghost.TButton", command=self._skip
        )
        self.skip_btn.pack(side="left", padx=(8, 0))
        self.open_btn = ttk.Button(
            body, style="Ghost.TButton", command=self._open_movie
        )
        self.open_btn.pack(anchor="w", pady=(12, 0))
        self.refresh_language()
        app._register_window(self)

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def refresh_language(self) -> None:
        self.title(self._text("Режим просмотра подборки", "Collection viewer"))
        self.watched_btn.configure(text=self._text("Смотрел", "Watched"))
        self.rate_btn.configure(text=self._text("Оценить и далее", "Rate & next"))
        self.skip_btn.configure(text=self._text("Далее / пропустить", "Next / skip"))
        self.open_btn.configure(text=self._text("Открыть фильм", "Open movie"))
        self._show_current()

    def _show_current(self) -> None:
        if not self.winfo_exists():
            return
        if self.index >= len(self.movies):
            self.progress.configure(text=self._text(
                "В подборке больше нет фильмов.", "No more movies in this collection."
            ))
            self.title_label.configure(text=self._text("Просмотр завершён", "Queue complete"))
            self.meta_label.configure(text="")
            self.overview_label.configure(text="")
            for button in (self.watched_btn, self.rate_btn, self.skip_btn, self.open_btn):
                button.configure(state="disabled")
            self.rating_combo.configure(state="disabled")
            return
        movie = self.movies[self.index]
        self.progress.configure(text=self._text(
            f"Фильм {self.index + 1} из {len(self.movies)} · осталось {len(self.movies) - self.index}",
            f"Movie {self.index + 1} of {len(self.movies)} · remaining {len(self.movies) - self.index}",
        ))
        self.title_label.configure(text=movie.get("title") or self._text("Без названия", "Untitled"))
        rating = movie.get("rating")
        rating_text = f"★ {rating:.1f}" if isinstance(rating, (int, float)) and rating else "★ —"
        self.meta_label.configure(text=f"{movie.get('year') or '—'} · {rating_text}")
        self.overview_label.configure(text=self.app.localized_overview(movie))
        for button in (self.watched_btn, self.rate_btn, self.skip_btn, self.open_btn):
            button.configure(state="normal")
        self.rating_combo.configure(state="readonly")

    def _advance(self) -> None:
        self.index += 1
        self._show_current()

    def _mark_watched(self) -> None:
        if self.index < len(self.movies):
            movie = self.movies[self.index]
            if self.app._save_card_personal_state(
                int(movie["id"]), True, movie.get("personal_rating")
            ):
                self._advance()

    def _rate_and_next(self) -> None:
        if self.index >= len(self.movies):
            return
        try:
            rating = int(self.rating_var.get())
        except ValueError:
            messagebox.showerror(
                self._text("Проверьте оценку", "Invalid rating"),
                self._text("Выберите оценку от 1 до 10.", "Choose a rating from 1 to 10."),
                parent=self,
            )
            return
        movie = self.movies[self.index]
        if self.app._save_card_personal_state(int(movie["id"]), True, rating):
            self._advance()

    def _skip(self) -> None:
        if self.index < len(self.movies):
            self._advance()

    def _open_movie(self) -> None:
        if self.index < len(self.movies):
            self.app.open_details(self.movies[self.index])


class EveningPickerWindow(tk.Toplevel):
    """Фильтрованный выбор фильма для вечера, исключающий просмотренное."""

    RUNTIME_LIMITS = (None, 90, 120, 150, 180)

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.movie: dict[str, Any] | None = None
        self._has_picked = False
        self.title(self._text("Фильм на вечер", "Movie for tonight"))
        self.geometry("510x540")
        self.minsize(480, 500)
        self.configure(bg=BG)
        self.transient(app)

        self.genre_var = tk.StringVar(value=app.genre_var.get())
        self.mood_var = tk.StringVar(value=app.mood_var.get())
        self.category_var = tk.StringVar(value=app.category_var.get())
        self.runtime_var = tk.StringVar()
        self._genre_by_label: dict[str, str | None] = {}
        self._mood_by_label: dict[str, str | None] = {}
        self._category_by_label: dict[str, str | None] = {}
        self._runtime_by_label: dict[str, int | None] = {}

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=22, pady=18)
        self.heading = tk.Label(body, bg=BG, fg=TEXT, font=FONT_H1, anchor="w")
        self.heading.pack(fill="x", pady=(0, 12))

        self.genre_label = self._field_label(body)
        self.genre_combo = ttk.Combobox(
            body, textvariable=self.genre_var, state="readonly", height=12
        )
        self.genre_combo.pack(fill="x", pady=(0, 8))

        self.mood_label = self._field_label(body)
        self.mood_combo = ttk.Combobox(
            body, textvariable=self.mood_var, state="readonly", height=8
        )
        self.mood_combo.pack(fill="x", pady=(0, 8))

        self.category_label = self._field_label(body)
        self.category_combo = ttk.Combobox(
            body, textvariable=self.category_var, state="readonly", height=12
        )
        self.category_combo.pack(fill="x", pady=(0, 8))

        self.runtime_label = self._field_label(body)
        self.runtime_combo = ttk.Combobox(
            body, textvariable=self.runtime_var, state="readonly", height=6
        )
        self.runtime_combo.pack(fill="x")
        self.runtime_note = tk.Label(
            body, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w", justify="left",
            wraplength=450,
        )
        self.runtime_note.pack(fill="x", pady=(4, 12))

        self.result_card = tk.Frame(
            body, bg=CARD, highlightthickness=1, highlightbackground=BORDER
        )
        self.result_title = tk.Label(
            self.result_card, bg=CARD, fg=TEXT, font=(FONT, 13, "bold"),
            anchor="w", justify="left", wraplength=440,
        )
        self.result_title.pack(fill="x", padx=12, pady=(10, 4))
        self.result_meta = tk.Label(
            self.result_card, bg=CARD, fg=GOLD, font=FONT_TEXT,
            anchor="w", justify="left", wraplength=440,
        )
        self.result_meta.pack(fill="x", padx=12)
        self.result_genres = tk.Label(
            self.result_card, bg=CARD, fg=MUTED, font=FONT_SMALL,
            anchor="w", justify="left", wraplength=440,
        )
        self.result_genres.pack(fill="x", padx=12, pady=(4, 10))
        self.result_card.pack(fill="x", pady=(0, 10))

        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", side="bottom", pady=(12, 0))
        self.pick_button = ttk.Button(
            actions, style="Accent.TButton", command=self._pick_movie
        )
        self.pick_button.pack(fill="x")
        secondary = tk.Frame(actions, bg=BG)
        secondary.pack(fill="x", pady=(8, 0))
        self.open_button = ttk.Button(
            secondary, style="Ghost.TButton", command=self._open_details
        )
        self.open_button.pack(side="left", fill="x", expand=True)
        self.again_button = ttk.Button(
            secondary, style="Ghost.TButton", command=self._pick_movie
        )
        self.again_button.pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.refresh_language()
        self.app._register_window(self)

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def _field_label(self, parent: tk.Misc) -> tk.Label:
        label = tk.Label(
            parent, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w"
        )
        label.pack(fill="x", pady=(0, 4))
        return label

    def _sync_choices(self) -> None:
        genre = self._genre_by_label.get(self.genre_var.get())
        mood = self._mood_by_label.get(self.mood_var.get())
        category = self._category_by_label.get(self.category_var.get())
        runtime = self._runtime_by_label.get(self.runtime_var.get())

        self._genre_by_label = dict(self.app._genre_by_label)
        self._mood_by_label = dict(self.app._mood_by_label)
        self._category_by_label = dict(self.app._category_by_label)
        self.genre_combo.configure(values=self.app.genre_combo.cget("values"))
        self.mood_combo.configure(values=self.app.mood_combo.cget("values"))
        self.category_combo.configure(values=self.app.category_combo.cget("values"))
        self.genre_var.set(self._label_for(self._genre_by_label, genre))
        self.mood_var.set(self._label_for(self._mood_by_label, mood))
        self.category_var.set(self._label_for(self._category_by_label, category))

        self._runtime_by_label = {}
        runtime_values = []
        for minutes in self.RUNTIME_LIMITS:
            label = self._text(
                "Без ограничения" if minutes is None else f"До {minutes} мин",
                "No limit" if minutes is None else f"Up to {minutes} min",
            )
            self._runtime_by_label[label] = minutes
            runtime_values.append(label)
        self.runtime_combo.configure(values=runtime_values)
        self.runtime_var.set(self._label_for(self._runtime_by_label, runtime))

    @staticmethod
    def _label_for(options: dict[str, Any], value: Any) -> str:
        return next((label for label, key in options.items() if key == value), next(iter(options)))

    def refresh_language(self) -> None:
        self._sync_choices()
        self.title(self._text("Фильм на вечер", "Movie for tonight"))
        self.heading.configure(text=self._text(
            "Подберём фильм на вечер", "Find a movie for tonight"
        ))
        self.genre_label.configure(text=self._text("ЖАНР", "GENRE"))
        self.mood_label.configure(text=self._text("НАСТРОЕНИЕ", "MOOD"))
        self.category_label.configure(text=self._text("ТЕМА", "THEME"))
        self.runtime_label.configure(text=self._text(
            "МАКСИМАЛЬНАЯ ДЛИТЕЛЬНОСТЬ", "MAXIMUM RUNTIME"
        ))
        self.runtime_note.configure(text=self._text(
            "Если задан предел, фильмы без указанной длительности не предлагаются.",
            "With a limit set, movies with no recorded runtime are excluded.",
        ))
        self.pick_button.configure(text=self._text("Выбрать фильм", "Pick a movie"))
        self.open_button.configure(text=self._text("Открыть детали", "Open details"))
        self.again_button.configure(text=self._text("Выбрать ещё", "Pick another"))
        self._set_result(
            self.movie, no_candidates=self._has_picked and self.movie is None
        )

    def _pick_movie(self) -> None:
        main_filters = self.app._collect_filters()
        if main_filters is None:
            return
        filters = {
            "genre": self._genre_by_label.get(self.genre_var.get()),
            "mood": self._mood_by_label.get(self.mood_var.get()),
            "category": self._category_by_label.get(self.category_var.get()),
            "year_from": main_filters["year_from"],
            "year_to": main_filters["year_to"],
            "min_runtime": main_filters["min_runtime"],
            "max_runtime": main_filters["max_runtime"],
        }
        evening_max = self._runtime_by_label.get(self.runtime_var.get())
        current_max = filters.get("max_runtime")
        if evening_max is not None:
            filters["max_runtime"] = (
                min(evening_max, current_max)
                if current_max is not None
                else evening_max
            )
        if (
            filters.get("min_runtime") is not None
            and filters.get("max_runtime") is not None
            and filters["min_runtime"] > filters["max_runtime"]
        ):
            movie = None
        else:
            movie = self._pick_filtered_movie(filters)
        self._has_picked = True
        self._set_result(movie, no_candidates=movie is None)

    def _pick_filtered_movie(self, filters: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return self.app.db.random_movie(filters)
        except Exception as exc:
            messagebox.showerror(
                self._text("Ошибка выбора", "Could not pick a movie"),
                str(exc),
                parent=self,
            )
            return None

    def _set_result(
        self, movie: dict[str, Any] | None, *, no_candidates: bool = False
    ) -> None:
        self.movie = movie
        if movie is None:
            if no_candidates:
                self.result_title.configure(text=self._text(
                    "Подходящих фильмов нет", "No matching movies"
                ))
                self.result_meta.configure(text=self._text(
                    "Попробуйте изменить жанр, настроение, тему или длительность.",
                    "Try changing the genre, mood, theme or runtime limit.",
                ))
            else:
                self.result_title.configure(text=self._text(
                    "Пока нет результата", "No result yet"
                ))
                self.result_meta.configure(text=self._text(
                    "Нажмите «Выбрать фильм», чтобы начать.",
                    "Press “Pick a movie” to start.",
                ))
            self.result_genres.configure(text="")
            self.open_button.configure(state="disabled")
            return

        self.result_title.configure(text=movie.get("title") or self._text("Без названия", "Untitled"))
        year = movie.get("year") or "—"
        runtime = movie.get("runtime")
        runtime_text = (
            self._text(f"{runtime} мин", f"{runtime} min")
            if isinstance(runtime, (int, float)) and runtime > 0
            else self._text("Длительность не указана", "Runtime not recorded")
        )
        rating = movie.get("rating")
        rating_text = f"★ {rating:.1f}" if isinstance(rating, (int, float)) and rating else "★ —"
        self.result_meta.configure(text=f"{year}   ·   {runtime_text}   ·   {rating_text}")
        genres = [item for item in (movie.get("genres") or "").split(",") if item]
        genre_names = [
            GENRE_NAMES_EN.get(item, item.title()) if self.app.is_english else genre_label(item)
            for item in genres
        ]
        self.result_genres.configure(
            text=self._text("Жанры: ", "Genres: ") + (", ".join(genre_names) or "—")
        )
        self.open_button.configure(state="normal")

    def _open_details(self) -> None:
        if self.movie is not None:
            self.app.open_details(self.movie)


class PlanMovieSelectWindow(tk.Toplevel):
    """Search the local catalogue and choose a movie to schedule."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.rows: list[dict[str, Any]] = []
        self.title("")
        self.geometry("560x500")
        self.configure(bg=BG)
        self.transient(app)
        self.heading = tk.Label(self, bg=BG, fg=TEXT, font=(FONT, 14, "bold"), anchor="w")
        self.heading.pack(fill="x", padx=20, pady=(16, 10))
        search_row = tk.Frame(self, bg=BG)
        search_row.pack(fill="x", padx=20, pady=(0, 10))
        self.query_var = tk.StringVar()
        self.query_entry = ttk.Entry(search_row, textvariable=self.query_var)
        self.query_entry.pack(side="left", fill="x", expand=True)
        self.query_entry.bind("<Return>", lambda _event: self.search())
        self.search_button = ttk.Button(search_row, style="Ghost.TButton", command=self.search)
        self.search_button.pack(side="left", padx=(8, 0))
        self.listbox = tk.Listbox(
            self, bg=CARD, fg=TEXT, font=FONT_TEXT, bd=0, activestyle="none",
            selectbackground=ACCENT, selectforeground="#08101f",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.listbox.pack(fill="both", expand=True, padx=20)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.choose())
        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", padx=20, pady=14)
        self.choose_button = ttk.Button(actions, style="Accent.TButton", command=self.choose)
        self.choose_button.pack(side="left")
        self.close_button = ttk.Button(actions, style="Ghost.TButton", command=self.destroy)
        self.close_button.pack(side="right")
        self.refresh_language()
        self.search()
        app._register_window(self)

    def refresh_language(self) -> None:
        self.title(self.app._text("Выберите фильм", "Choose a movie"))
        self.heading.configure(text=self.app._text(
            "Фильм из локального каталога", "Movie from the local catalogue"
        ))
        self.search_button.configure(text=self.app._text("Найти", "Search"))
        self.choose_button.configure(text=self.app._text("Выбрать фильм", "Select movie"))
        self.close_button.configure(text=self.app._text("Закрыть", "Close"))
        self._render()

    def search(self) -> None:
        query = self.query_var.get().strip()
        try:
            self.rows, _total = self.app.db.search(
                title=query or None, sort="rating", limit=100
            )
        except Exception as exc:
            messagebox.showerror(
                self.app._text("Ошибка поиска", "Search failed"), str(exc), parent=self
            )
            return
        self._render()

    def _render(self) -> None:
        if not hasattr(self, "listbox"):
            return
        self.listbox.delete(0, "end")
        if not self.rows:
            self.listbox.insert("end", self.app._text("Фильмы не найдены.", "No movies found."))
        for movie in self.rows:
            self.listbox.insert(
                "end", f"{movie['title']} ({movie.get('year') or '—'})"
            )

    def choose(self) -> None:
        selection = self.listbox.curselection()
        if selection and selection[0] < len(self.rows):
            movie = self.rows[selection[0]]
            PlanEditWindow(self.app, movie)
            self.destroy()


class PlanEditWindow(tk.Toplevel):
    """Create or edit one planned screening without changing watched state."""

    def __init__(
        self,
        app: MovieApp,
        movie: dict[str, Any],
        plan: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(app)
        self.app = app
        self.movie_id = int((plan or {}).get("movie_id") or movie["id"])
        self.plan = plan
        self.title("")
        self.geometry("460x300")
        self.resizable(False, False)
        self.configure(bg=BG)
        self.transient(app)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=20, pady=18)
        self.heading = tk.Label(body, bg=BG, fg=TEXT, font=(FONT, 14, "bold"), anchor="w")
        self.heading.pack(fill="x", pady=(0, 14))
        self.date_label = tk.Label(body, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w")
        self.date_label.pack(fill="x")
        self.date_var = tk.StringVar(value=(plan or {}).get("planned_date") or date.today().isoformat())
        self.date_entry = ttk.Entry(body, textvariable=self.date_var)
        self.date_entry.pack(fill="x", pady=(4, 12))
        self.note_label = tk.Label(body, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w")
        self.note_label.pack(fill="x")
        self.note_text = tk.Text(
            body, bg=CARD, fg=TEXT, insertbackground=TEXT, height=4, wrap="word",
            bd=0, highlightthickness=1, highlightbackground=BORDER,
        )
        self.note_text.pack(fill="both", expand=True, pady=(4, 12))
        if plan:
            self.note_text.insert("1.0", plan.get("note") or "")
        self.save_button = ttk.Button(
            body, style="Accent.TButton", command=self._save
        )
        self.save_button.pack(side="right")
        ttk.Button(
            body, style="Ghost.TButton", command=self.destroy
        ).pack(side="right", padx=(0, 8))
        self.refresh_language()
        app._register_window(self)

    def refresh_language(self) -> None:
        editing = self.plan is not None
        self.title(self.app._text(
            "Изменить план" if editing else "Запланировать просмотр",
            "Edit plan" if editing else "Plan a screening",
        ))
        self.heading.configure(text=self.app._text(
            "План просмотра", "Viewing plan"
        ))
        self.date_label.configure(text=self.app._text(
            "Дата (ГГГГ-ММ-ДД)", "Date (YYYY-MM-DD)"
        ))
        self.note_label.configure(text=self.app._text("Заметка (необязательно)", "Note (optional)"))
        self.save_button.configure(text=self.app._text("Сохранить", "Save"))
        buttons = self.winfo_children()[0].winfo_children()
        if buttons:
            buttons[-1].configure(text=self.app._text("Отмена", "Cancel"))

    def _save(self) -> None:
        try:
            if self.plan:
                self.app.db.update_plan(
                    int(self.plan["id"]), self.date_var.get(),
                    self.note_text.get("1.0", "end-1c"),
                )
            else:
                self.app.db.add_plan(
                    self.movie_id, self.date_var.get(),
                    self.note_text.get("1.0", "end-1c"),
                )
        except Exception as exc:
            messagebox.showerror(
                self.app._text("Не удалось сохранить план", "Could not save plan"),
                str(exc), parent=self,
            )
            return
        self.destroy()
        for window in list(self.app._windows):
            if isinstance(window, ViewingPlannerWindow) and window.winfo_exists():
                window.refresh()


class ViewingPlannerWindow(tk.Toplevel):
    """Local calendar-style list of planned and manually completed viewings."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.rows: list[dict[str, Any]] = []
        self.title("")
        self.geometry("760x560")
        self.minsize(620, 420)
        self.configure(bg=BG)
        self.transient(app)
        self.bind("<Escape>", lambda _event: self.destroy())

        self.heading = tk.Label(self, bg=BG, fg=TEXT, font=(FONT, 15, "bold"), anchor="w")
        self.heading.pack(fill="x", padx=20, pady=(16, 8))
        self.hint = tk.Label(self, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w", justify="left")
        self.hint.pack(fill="x", padx=20, pady=(0, 8))
        self.listbox = tk.Listbox(
            self, bg=CARD, fg=TEXT, font=FONT_TEXT, bd=0, activestyle="none",
            selectbackground=ACCENT, selectforeground="#08101f",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.listbox.pack(fill="both", expand=True, padx=20)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.open_movie())
        self.actions = tk.Frame(self, bg=BG)
        self.actions.pack(fill="x", padx=20, pady=14)
        self.add_button = ttk.Button(self.actions, style="Accent.TButton", command=self.add)
        self.add_button.pack(side="left")
        self.edit_button = ttk.Button(self.actions, style="Ghost.TButton", command=self.edit)
        self.edit_button.pack(side="left", padx=(6, 0))
        self.done_button = ttk.Button(self.actions, style="Ghost.TButton", command=self.complete)
        self.done_button.pack(side="left", padx=(6, 0))
        self.open_button = ttk.Button(self.actions, style="Ghost.TButton", command=self.open_movie)
        self.open_button.pack(side="left", padx=(6, 0))
        self.delete_button = ttk.Button(self.actions, style="Ghost.TButton", command=self.delete)
        self.delete_button.pack(side="left", padx=(6, 0))
        self.refresh_language()
        self.refresh()
        app._register_window(self)

    def refresh_language(self) -> None:
        self.title(self.app._text("Планировщик кинопросмотра", "Viewing planner"))
        self.heading.configure(text=self.app._text("Планы просмотра", "Viewing plans"))
        self.hint.configure(text=self.app._text(
            "Отметка «Просмотрено» меняет watched только после нажатия кнопки завершения.",
            "A plan marks a movie watched only after you explicitly choose Complete.",
        ))
        self.add_button.configure(text=self.app._text("Добавить", "Add"))
        self.edit_button.configure(text=self.app._text("Изменить", "Edit"))
        self.done_button.configure(text=self.app._text("Завершить просмотр", "Mark completed"))
        self.open_button.configure(text=self.app._text("Открыть фильм", "Open movie"))
        self.delete_button.configure(text=self.app._text("Удалить", "Delete"))
        self.refresh()

    def refresh(self) -> None:
        self.rows = self.app.db.plans()
        self.listbox.delete(0, "end")
        if not self.rows:
            self.listbox.insert("end", self.app._text("Планов пока нет.", "No viewing plans yet."))
        for row in self.rows:
            status = self.app._text("Просмотрено", "Completed") if row["status"] == "completed" \
                else self.app._text("Запланировано", "Planned")
            note = f" — {row['note']}" if row.get("note") else ""
            self.listbox.insert(
                "end", f"{row['planned_date']}  ·  {row['title']} ({row.get('year') or '—'})"
                f"  ·  {status}{note}"
            )

    def _selected(self) -> dict[str, Any] | None:
        selection = self.listbox.curselection()
        if not selection or selection[0] >= len(self.rows):
            return None
        return self.rows[selection[0]]

    def add(self) -> None:
        PlanMovieSelectWindow(self.app)

    def edit(self) -> None:
        row = self._selected()
        if row and row["status"] == "planned":
            PlanEditWindow(self.app, row, row)

    def complete(self) -> None:
        row = self._selected()
        if not row or row["status"] != "planned":
            return
        try:
            self.app.db.complete_plan(int(row["id"]))
        except Exception as exc:
            messagebox.showerror(
                self.app._text("Не удалось завершить план", "Could not complete plan"),
                str(exc), parent=self,
            )
            return
        movie = self.app.db.get(int(row["movie_id"])) or {}
        self.app._refresh_personal_state_views(
            int(row["movie_id"]), True, movie.get("personal_rating")
        )
        self.refresh()

    def open_movie(self) -> None:
        row = self._selected()
        if row:
            self.app.open_details(self.app.db.get(int(row["movie_id"])) or {})

    def delete(self) -> None:
        row = self._selected()
        if row and messagebox.askyesno(
            self.app._text("Удалить план?", "Delete plan?"),
            self.app._text("Удалить выбранный план просмотра?", "Delete the selected viewing plan?"),
            parent=self,
        ):
            self.app.db.delete_plan(int(row["id"]))
            self.refresh()


class ContentExclusionsWindow(tk.Toplevel):
    """Select genres and predefined themes to hide from recommendation modes."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.genre_vars: dict[str, tk.BooleanVar] = {}
        self.theme_vars: dict[str, tk.BooleanVar] = {}
        self.title("")
        self.geometry("600x700")
        self.minsize(520, 520)
        self.configure(bg=BG)
        self.transient(app)

        self.heading = tk.Label(self, bg=BG, fg=TEXT, font=(FONT, 15, "bold"), anchor="w")
        self.heading.pack(fill="x", padx=20, pady=(16, 8))
        self.hint = tk.Label(self, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w", justify="left")
        self.hint.pack(fill="x", padx=20, pady=(0, 8))
        frame = tk.Frame(self, bg=BG)
        frame.pack(fill="both", expand=True, padx=20)
        canvas = tk.Canvas(frame, bg=BG, highlightthickness=0, bd=0)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        self.options = tk.Frame(canvas, bg=BG)
        canvas.create_window((0, 0), window=self.options, anchor="nw")
        self.options.bind(
            "<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        self.genre_heading = tk.Label(self.options, bg=BG, fg=TEXT, font=(FONT, 11, "bold"))
        self.genre_heading.pack(anchor="w", pady=(4, 4))
        genres = dict.fromkeys([*GENRE_ORDER, *(name for name, _count in app.db.genre_counts())])
        self.genre_widgets: dict[str, tk.Checkbutton] = {}
        for genre in genres:
            var = tk.BooleanVar()
            self.genre_vars[genre] = var
            widget = tk.Checkbutton(
                self.options, variable=var, bg=BG, fg=TEXT, selectcolor=CARD,
                activebackground=BG, activeforeground=ACCENT, font=FONT_TEXT,
                anchor="w", bd=0, highlightthickness=0,
            )
            widget.pack(fill="x")
            self.genre_widgets[genre] = widget
        self.theme_heading = tk.Label(self.options, bg=BG, fg=TEXT, font=(FONT, 11, "bold"))
        self.theme_heading.pack(anchor="w", pady=(14, 4))
        self.theme_widgets: dict[str, tk.Checkbutton] = {}
        for theme in CATEGORY_ORDER:
            if theme in MOOD_CATEGORIES:
                continue
            var = tk.BooleanVar()
            self.theme_vars[theme] = var
            widget = tk.Checkbutton(
                self.options, variable=var, bg=BG, fg=TEXT, selectcolor=CARD,
                activebackground=BG, activeforeground=ACCENT, font=FONT_TEXT,
                anchor="w", bd=0, highlightthickness=0,
            )
            widget.pack(fill="x")
            self.theme_widgets[theme] = widget
        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=20, pady=14)
        self.clear_button = ttk.Button(buttons, style="Ghost.TButton", command=self.clear)
        self.clear_button.pack(side="left")
        self.save_button = ttk.Button(buttons, style="Accent.TButton", command=self.save)
        self.save_button.pack(side="right")
        selected = app.db.content_exclusions()
        for genre, variable in self.genre_vars.items():
            variable.set(genre in selected["genre"])
        for theme, variable in self.theme_vars.items():
            variable.set(theme in selected["theme"])
        self.refresh_language()
        app._register_window(self)

    def refresh_language(self) -> None:
        english = self.app.is_english
        self.title(self.app._text("Нежелательный контент", "Unwanted content"))
        self.heading.configure(text=self.app._text(
            "Исключать из подборок", "Exclude from recommendations"
        ))
        self.hint.configure(text=self.app._text(
            "Эти исключения действуют на рекомендации, случайный выбор, фильм на вечер и похожие фильмы, но не на обычный поиск.",
            "These exclusions apply to recommendations, random picks, movie-for-tonight and similar results, not normal search.",
        ))
        self.genre_heading.configure(text=self.app._text("Жанры", "Genres"))
        self.theme_heading.configure(text=self.app._text("Темы", "Themes"))
        for genre in self.genre_vars:
            self.genre_widgets[genre].configure(
                text=GENRE_NAMES_EN.get(genre, genre.title())
                if english else genre_label(genre)
            )
        for theme, widget in self.theme_widgets.items():
            widget.configure(text=category_label(theme, english))
        self.clear_button.configure(text=self.app._text("Снять все исключения", "Clear all exclusions"))
        self.save_button.configure(text=self.app._text("Сохранить", "Save"))

    def clear(self) -> None:
        for variable in (*self.genre_vars.values(), *self.theme_vars.values()):
            variable.set(False)
        self.save()

    def save(self) -> None:
        try:
            self.app.db.set_content_exclusions(
                genres=[value for value, var in self.genre_vars.items() if var.get()],
                themes=[value for value, var in self.theme_vars.items() if var.get()],
            )
        except Exception as exc:
            messagebox.showerror(
                self.app._text("Не удалось сохранить исключения", "Could not save exclusions"),
                str(exc), parent=self,
            )
            return
        if self.app._showing_recommendations:
            self.app.show_recommendations()


class SimilarMoviesWindow(tk.Toplevel):
    """User-selectable local-signal matching with per-result explanations."""

    SIGNALS = ("actors", "director", "genres", "keywords")

    def __init__(self, app: MovieApp, movie: dict[str, Any]) -> None:
        super().__init__(app)
        self.app = app
        self.movie = movie
        self.results: list[dict[str, Any]] = []
        self.signal_vars = {signal: tk.BooleanVar(value=True) for signal in self.SIGNALS}
        self.title("")
        self.geometry("760x590")
        self.minsize(600, 440)
        self.configure(bg=BG)
        self.transient(app)
        self.heading = tk.Label(self, bg=BG, fg=TEXT, font=(FONT, 14, "bold"), anchor="w")
        self.heading.pack(fill="x", padx=20, pady=(16, 10))
        self.options = tk.Frame(self, bg=BG)
        self.options.pack(fill="x", padx=20)
        self.signal_widgets: dict[str, tk.Checkbutton] = {}
        labels = {
            "actors": ("Актёры", "Actors"),
            "director": ("Режиссёр", "Director"),
            "genres": ("Жанры", "Genres"),
            "keywords": ("Темы / ключевые слова", "Themes / keywords"),
        }
        for signal in self.SIGNALS:
            widget = tk.Checkbutton(
                self.options, variable=self.signal_vars[signal], bg=BG, fg=TEXT,
                selectcolor=CARD, activebackground=BG, font=FONT_TEXT,
                bd=0, highlightthickness=0,
            )
            widget.pack(side="left", padx=(0, 10))
            self.signal_widgets[signal] = widget
            widget._labels = labels[signal]
        self.find_button = ttk.Button(
            self, style="Accent.TButton", command=self.find
        )
        self.find_button.pack(anchor="w", padx=20, pady=10)
        self.listbox = tk.Listbox(
            self, bg=CARD, fg=TEXT, font=FONT_TEXT, bd=0, activestyle="none",
            selectbackground=ACCENT, selectforeground="#08101f",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self.listbox.pack(fill="both", expand=True, padx=20)
        self.listbox.bind("<Double-Button-1>", lambda _event: self.open_selected())
        self.bottom = tk.Frame(self, bg=BG)
        self.bottom.pack(fill="x", padx=20, pady=12)
        self.open_button = ttk.Button(self.bottom, style="Ghost.TButton", command=self.open_selected)
        self.open_button.pack(side="left")
        self.close_button = ttk.Button(self.bottom, style="Ghost.TButton", command=self.destroy)
        self.close_button.pack(side="right")
        self.refresh_language()
        app._register_window(self)

    def refresh_language(self) -> None:
        self.title(self.app._text("Найти похожее", "Find similar movies"))
        self.heading.configure(text=self.app._text(
            f"Похожие на «{self.movie.get('title', '')}»",
            f"Similar to “{self.movie.get('title', '')}”",
        ))
        for widget in self.signal_widgets.values():
            widget.configure(text=self.app._text(*widget._labels))
        self.find_button.configure(text=self.app._text("Найти похожие", "Find similar"))
        self.open_button.configure(text=self.app._text("Открыть фильм", "Open movie"))
        self.close_button.configure(text=self.app._text("Закрыть", "Close"))
        self._render_results()

    def find(self) -> None:
        signals = [signal for signal, variable in self.signal_vars.items() if variable.get()]
        try:
            self.results = self.app.db.similar_by(int(self.movie["id"]), signals, 60)
        except Exception as exc:
            messagebox.showerror(
                self.app._text("Ошибка поиска", "Search failed"), str(exc), parent=self
            )
            return
        self._render_results()

    def _reason_text(self, reason: dict[str, str]) -> str:
        kind, value = reason["type"], reason["value"]
        if kind == "genre":
            value = GENRE_NAMES_EN.get(value, value.title()) if self.app.is_english else genre_label(value)
        labels = {
            "actor": ("Актёр", "Actor"),
            "director": ("Режиссёр", "Director"),
            "genre": ("Жанр", "Genre"),
            "keyword": ("Тема", "Theme"),
        }
        label = self.app._text(*labels[kind])
        return f"{label}: {value}"

    def _render_results(self) -> None:
        if not hasattr(self, "listbox"):
            return
        self.listbox.delete(0, "end")
        if not self.results:
            self.listbox.insert(
                "end", self.app._text(
                    "Выберите признаки и нажмите «Найти похожие».",
                    "Select signals and press “Find similar”.",
                )
            )
            return
        for movie in self.results:
            reasons = "; ".join(self._reason_text(item) for item in movie["similarity_reasons"])
            self.listbox.insert(
                "end",
                f"{movie['title']} ({movie.get('year') or '—'})  ·  "
                f"{self.app._text('Совпадения', 'Matches')}: {reasons}",
            )

    def open_selected(self) -> None:
        selection = self.listbox.curselection()
        if selection and selection[0] < len(self.results):
            movie = self.results[selection[0]]
            self.app.open_details(self.app.db.get(int(movie["id"])) or movie)


class DetailWindow(tk.Toplevel):
    """Окно с крупным постером и полным описанием фильма."""

    def __init__(self, app: MovieApp, movie: dict[str, Any]) -> None:
        super().__init__(app)
        self.app = app
        movie_id = movie.get("id")
        if isinstance(movie_id, int):
            stored_movie = self.app.db.get(movie_id)
            if stored_movie:
                movie.update(stored_movie)
        self.movie = movie
        self.movie_id = movie_id if isinstance(movie_id, int) else None
        self._photo: ImageTk.PhotoImage | None = None

        self.title(f"{movie.get('title')} ({movie.get('year') or '—'})")
        self.geometry("1040x690")
        self.minsize(940, 620)
        self.configure(bg=BG)
        self.transient(app)
        self.bind("<Escape>", lambda _e: self.destroy())

        poster_frame = tk.Frame(self, bg=BG, width=340)
        poster_frame.pack(side="left", fill="y", padx=(20, 10), pady=20)
        poster_frame.pack_propagate(False)

        self.poster_lbl = tk.Label(
            poster_frame, bg=CARD, bd=0, image=app.detail_placeholder
        )
        self.poster_lbl.pack()

        info = tk.Frame(self, bg=BG)
        info.pack(side="left", fill="both", expand=True, padx=(6, 20), pady=20)

        tk.Label(
            info,
            text=movie.get("title") or "Без названия",
            bg=BG,
            fg=TEXT,
            font=FONT_H2,
            wraplength=600,
            justify="left",
            anchor="w",
        ).pack(fill="x")

        original = (movie.get("original_title") or "").strip()
        if original and original.lower() != (movie.get("title") or "").lower():
            tk.Label(
                info,
                text=original,
                bg=BG,
                fg=MUTED,
                font=(FONT, 10, "italic"),
                anchor="w",
                wraplength=600,
                justify="left",
            ).pack(fill="x", pady=(2, 0))

        meta_parts: list[str] = []
        if movie.get("year"):
            meta_parts.append(str(movie["year"]))
        if movie.get("runtime"):
            meta_parts.append(f"{movie['runtime']} мин")
        rating = movie.get("rating")
        meta_parts.append(f"★ {rating:.1f}" if isinstance(rating, (int, float)) and rating else "★ —")
        if movie.get("votes"):
            meta_parts.append(f"{int(movie['votes']):,} голосов".replace(",", " "))

        tk.Label(
            info,
            text="   ·   ".join(meta_parts),
            bg=BG,
            fg=GOLD,
            font=(FONT, 11, "bold"),
            anchor="w",
        ).pack(fill="x", pady=(10, 6))

        state_row = tk.Frame(info, bg=BG)
        state_row.pack(fill="x", pady=(0, 8))
        self.watched_var = tk.BooleanVar(value=bool(movie.get("watched", 0)))
        self.watched_check = tk.Checkbutton(
            state_row,
            text="Смотрел",
            variable=self.watched_var,
            command=self._save_personal_state,
            bg=BG,
            fg=TEXT,
            selectcolor=CARD,
            activebackground=BG,
            activeforeground=ACCENT,
            font=(FONT, 9),
            bd=0,
            highlightthickness=0,
        )
        self.watched_check.pack(side="left")
        self.personal_rating_var = tk.StringVar()
        self.personal_rating_label = tk.Label(
            state_row, text="Личная оценка:", bg=BG, fg=MUTED, font=FONT_SMALL
        )
        self.personal_rating_label.pack(side="left", padx=(14, 6))
        self.personal_rating_combo = ttk.Combobox(
            state_row,
            textvariable=self.personal_rating_var,
            values=("—", *(str(value) for value in range(1, 11))),
            state="readonly",
            width=5,
        )
        self.personal_rating_combo.pack(side="left")
        self.personal_rating_combo.bind(
            "<<ComboboxSelected>>", lambda _event: self._save_personal_state()
        )
        self._refresh_personal_controls()

        details_lines: list[str] = []
        genres = [g for g in (movie.get("genres") or "").split(",") if g]
        if genres:
            details_lines.append("Жанр: " + ", ".join(genre_label(g) for g in genres))
        countries = movie.get("countries") or ""
        if countries.strip(","):
            details_lines.append("Страна: " + country_title(countries))
        if movie.get("director"):
            details_lines.append("Режиссёр: " + str(movie["director"]))

        for line in details_lines:
            tk.Label(
                info,
                text=line,
                bg=BG,
                fg=TEXT,
                font=(FONT, 10),
                anchor="w",
                wraplength=600,
                justify="left",
            ).pack(fill="x")

        movie_id = self.movie_id
        if movie_id is not None:
            self.detail_metadata = self.app.db.detail_metadata(movie_id)
            cast = self.detail_metadata["cast"]
            if cast:
                tk.Label(
                    info,
                    text="В ролях: " + ", ".join(cast),
                    bg=BG,
                    fg=TEXT,
                    font=(FONT, 10),
                    anchor="w",
                    wraplength=600,
                    justify="left",
                ).pack(fill="x")
            keywords = self.detail_metadata["keywords"]
            if keywords:
                tk.Label(
                    info,
                    text="Ключевые слова: " + ", ".join(keywords),
                    bg=BG,
                    fg=MUTED,
                    font=FONT_SMALL,
                    anchor="w",
                    wraplength=600,
                    justify="left",
                ).pack(fill="x", pady=(4, 0))

        tagline = (movie.get("tagline") or "").strip()
        if tagline:
            tk.Label(
                info,
                text=f"«{tagline}»",
                bg=BG,
                fg=MUTED,
                font=(FONT, 10, "italic"),
                anchor="w",
                wraplength=600,
                justify="left",
            ).pack(fill="x", pady=(10, 0))

        actions = tk.Frame(info, bg=BG)
        actions.pack(side="bottom", fill="x", pady=(12, 0))
        mode_actions = tk.Frame(info, bg=BG)
        mode_actions.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Button(
            actions, text="Закрыть", style="Ghost.TButton", command=self.destroy
        ).pack(side="right")

        if movie_id is not None:
            ttk.Button(
                mode_actions,
                text="Найти похожее…",
                style="Ghost.TButton",
                command=lambda: SimilarMoviesWindow(self.app, self.movie),
            ).pack(side="left", fill="x", expand=True, padx=(0, 4))
            ttk.Button(
                mode_actions,
                text="Запланировать просмотр",
                style="Ghost.TButton",
                command=lambda: PlanEditWindow(self.app, self.movie),
            ).pack(side="left", fill="x", expand=True, padx=(4, 0))
            ttk.Button(
                actions,
                text="Серии и франшизы",
                style="Ghost.TButton",
                command=lambda: self.app.open_franchise(self.movie),
            ).pack(side="left", padx=(0, 8))
            self.bookmark_btn = ttk.Button(
                actions, text="", style="Ghost.TButton", command=self._toggle_bookmark
            )
            self.bookmark_btn.pack(side="right", padx=(0, 8))
            self._refresh_bookmark()
            self.watchlist_btn = ttk.Button(
                actions,
                text="",
                style="Ghost.TButton",
                command=self._edit_watchlist,
            )
            self.watchlist_btn.pack(side="right", padx=(0, 8))
            self._refresh_watchlist()
            similar = self.app.db.similar(movie_id, 3)
            if similar:
                similar_row = tk.Frame(info, bg=BG)
                similar_row.pack(side="bottom", fill="x", pady=(10, 0))
                tk.Label(
                    similar_row,
                    text="Похожие:",
                    bg=BG,
                    fg=MUTED,
                    font=FONT_SMALL,
                ).pack(side="left", padx=(0, 8))
                for item in similar:
                    label = f"{item['title']} ({item['year']})" if item.get("year") else str(item["title"])
                    ttk.Button(
                        similar_row,
                        text=label[:24],
                        style="Ghost.TButton",
                        command=lambda mid=item["id"]: self.app.open_details(
                            self.app.db.get(mid) or {}
                        ),
                    ).pack(side="left", padx=(0, 6))
            self.app.db.record_view(movie_id)

        if movie.get("file_path"):
            ttk.Button(
                actions, text="▶ Смотреть", style="Accent.TButton", command=self._play
            ).pack(side="left")
        else:
            ttk.Button(
                actions,
                text="▶ Смотреть",
                style="Ghost.TButton",
                command=self._how_to_watch_local,
            ).pack(side="left")

        watch = self.detail_metadata.get("watch_link") if movie_id is not None else None
        if isinstance(movie.get("id"), int):
            if not hasattr(self, "detail_metadata"):
                try:
                    watch = self.app.db.watch_link(int(movie["id"]))
                except Exception:  # noqa: BLE001 - без ссылки окно тоже должно открыться
                    watch = None
        if watch:
            source = str(watch["source"])
            ttk.Button(
                actions,
                text=WATCH_LABELS.get(source, f"Смотреть: {source}"),
                style="Accent.TButton" if not movie.get("file_path") else "Ghost.TButton",
                command=lambda u=watch["url"]: webbrowser.open(u),
            ).pack(side="left", padx=(6, 0))

        self.trailer_btn = ttk.Button(
            actions,
            text="Трейлер",
            style="Ghost.TButton",
            command=lambda: webbrowser.open(trailer_search_url(movie)),
        )
        self.trailer_btn.pack(side="left", padx=(6, 0))
        stored = self.detail_metadata.get("providers") if movie_id is not None else None
        if movie_id is not None and not hasattr(self, "detail_metadata"):
            try:
                stored = self.app.db.providers_of(movie_id)
            except Exception:  # noqa: BLE001 - кэш площадок не критичен
                stored = None

        watch_target = (stored or {}).get("link") or watch_search_url(movie)
        self.watch_btn = ttk.Button(
            actions,
            text="Где смотреть",
            style="Ghost.TButton",
            command=lambda u=watch_target: webbrowser.open(u),
        )
        self.watch_btn.pack(side="left", padx=(6, 0))
        self.free_btn = ttk.Button(
            actions, text="Бесплатно ▾", style="Ghost.TButton", command=self._show_free_menu
        )
        self.free_btn.pack(side="left", padx=(6, 0))

        links_row = tk.Frame(info, bg=BG)
        links_row.pack(side="bottom", fill="x", pady=(6, 0))
        for label, url in (
            ("TMDb", tmdb_url(movie)),
            ("IMDb", imdb_url(movie)),
            ("Кинопоиск", kinopoisk_url(movie)),
            ("Википедия", wikipedia_url(movie)),
        ):
            if not url:
                continue
            ttk.Button(
                links_row,
                text=label,
                style="Ghost.TButton",
                command=lambda u=url: webbrowser.open(u),
            ).pack(side="left", padx=(0, 6))

        self.providers_lbl = tk.Label(
            info,
            text="",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
            anchor="w",
            justify="left",
            wraplength=600,
        )
        self.providers_lbl.pack(side="bottom", fill="x", pady=(8, 0))
        self._stored_providers = bool(stored)
        if stored:
            self.providers_lbl.configure(
                text=f"Онлайн ({stored['region']}): {stored['names']}"
            )

        tk.Frame(info, bg=BORDER, height=1).pack(side="bottom", fill="x", pady=12)

        text_wrap = tk.Frame(info, bg=BG)
        text_wrap.pack(fill="both", expand=True)
        self.text = tk.Text(
            text_wrap,
            bg=CARD,
            fg=TEXT,
            font=FONT_TEXT,
            wrap="word",
            bd=0,
            height=8,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=BORDER,
            padx=14,
            pady=12,
            spacing1=2,
            spacing3=4,
            insertbackground=TEXT,
        )
        scroll = ttk.Scrollbar(text_wrap, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        self.refresh_overview()

        self.app._detail_windows.add(self)
        self.app._register_window(self)
        self.bind("<Destroy>", self._on_destroy, add="+")
        self.app.poster_pool.submit(self._load_poster)
        self._start_extras()
        self.after(60, self.focus_set)

    def _on_destroy(self, event: tk.Event) -> None:
        if event.widget is self:
            self.app._detail_windows.discard(self)

    def refresh_overview(self) -> None:
        if not hasattr(self, "text") or not self.winfo_exists():
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", self.app.localized_overview(self.movie))
        self.text.configure(state="disabled")

    def _load_poster(self) -> None:
        image = self.app.posters.image(self.movie, (300, 450))
        if image is None:
            return
        self.app._post(lambda: self._apply(image))  # noqa: SLF001 - единая очередь UI

    def _apply(self, image) -> None:
        if not self.winfo_exists():
            return
        photo = ImageTk.PhotoImage(image)
        self._photo = photo
        self.poster_lbl.configure(image=photo, width=0, height=0)

    # ------------------------------------------------------- ссылки и плеер
    def _refresh_bookmark(self) -> None:
        movie_id = self.movie.get("id")
        if not isinstance(movie_id, int):
            return
        marked = self.app.db.is_bookmarked(movie_id)
        self.bookmark_btn.configure(text="★ В закладках" if marked else "☆ В закладки")

    def _refresh_watchlist(self) -> None:
        if not hasattr(self, "watchlist_btn") or self.movie_id is None:
            return
        entry = self.app.db.watchlist_entry(self.movie_id)
        self.movie["watchlisted"] = entry is not None
        self.watchlist_btn.configure(
            text=self.app._text(
                "✓ В списке" if entry else "＋ Хочу посмотреть",
                "✓ In watchlist" if entry else "＋ Watchlist",
            )
        )

    def _edit_watchlist(self) -> None:
        if self.movie_id is not None:
            WatchlistEditWindow(self.app, self.movie)

    def _refresh_personal_controls(self) -> None:
        self.watched_var.set(bool(self.movie.get("watched", 0)))
        rating = self.movie.get("personal_rating")
        self.personal_rating_var.set(str(rating) if rating is not None else "—")

    def _save_personal_state(self) -> None:
        movie_id = self.movie_id
        if not isinstance(movie_id, int):
            return
        selected_rating = self.personal_rating_var.get()
        personal_rating = int(selected_rating) if selected_rating.isdigit() else None
        watched = bool(self.watched_var.get())
        try:
            self.app.db.set_personal_state(
                movie_id, watched=watched, personal_rating=personal_rating
            )
        except Exception as exc:  # noqa: BLE001 - уведомляем, если состояние не сохранилось
            self._refresh_personal_controls()
            messagebox.showerror(
                self.app._text("Не удалось сохранить", "Could not save"),
                str(exc),
                parent=self,
            )
            return
        self.movie["watched"] = int(watched)
        self.movie["personal_rating"] = personal_rating
        self.app._refresh_personal_state_views(movie_id, watched, personal_rating)

    def _toggle_bookmark(self) -> None:
        movie_id = self.movie.get("id")
        if not isinstance(movie_id, int):
            return
        self.app.db.toggle_bookmark(movie_id)
        self._refresh_bookmark()
        self.app._refresh_stats()
        if self.app.bookmark_only_var.get():
            self.app.search()

    def _play(self) -> None:
        file_path = (self.movie.get("file_path") or "").strip()
        if not file_path:
            self._how_to_watch_local()
            return
        player = (self.app.cfg.get("player_path") or "").strip()
        ok, message = open_file(file_path, player)
        if not ok:
            messagebox.showerror("Не удалось открыть", message, parent=self)

    def _how_to_watch_local(self) -> None:        messagebox.showinfo(
            "Смотреть локальный файл",
            "У этого фильма не найден файл на диске.\n\n"
            "Откройте «Настройки» → «Моя коллекция», укажите папку с фильмами "
            "и нажмите «Найти файлы»: приложение сопоставит имена файлов с базой, "
            "и кнопка «Смотреть» появится здесь.",
            parent=self,
        )

    def _show_free_menu(self) -> None:
        """Список бесплатных легальных каталогов для поиска этого фильма."""
        menu = tk.Menu(
            self,
            tearoff=0,
            bg=CARD,
            fg=TEXT,
            activebackground=ACCENT,
            activeforeground="#08101f",
            bd=0,
        )
        for name, url in free_catalog_links(self.movie):
            menu.add_command(label=name, command=lambda u=url: webbrowser.open(u))
        try:
            x = self.free_btn.winfo_rootx()
            y = self.free_btn.winfo_rooty() + self.free_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    def _start_extras(self) -> None:
        """Трейлер и площадки подтягиваются в фоне, если их ещё нет в базе."""
        if self._stored_providers or not self.app.cfg.has_api_key:
            return
        movie_id = self.movie.get("id")
        if not isinstance(movie_id, int) or movie_id <= 0:
            return

        def worker() -> None:
            extras = fetch_extras(movie_id, self.app.cfg.api_key)
            if extras.get("trailer") or extras.get("watch") or extras.get("providers"):
                self.app._post(lambda: self._apply_extras(extras))  # noqa: SLF001

        threading.Thread(target=worker, daemon=True).start()

    def _apply_extras(self, extras: dict) -> None:
        if not self.winfo_exists():
            return
        trailer = extras.get("trailer")
        if trailer:
            self.trailer_btn.configure(
                text="▶ Трейлер", command=lambda: webbrowser.open(trailer)
            )
        watch = extras.get("watch")
        if watch:
            self.watch_btn.configure(command=lambda: webbrowser.open(watch))
        providers = extras.get("providers") or []
        if providers:
            region = extras.get("region") or ""
            prefix = f"Онлайн ({region}): " if region else "Онлайн: "
            self.providers_lbl.configure(text=prefix + ", ".join(providers[:5]))
            movie_id = self.movie.get("id")
            if isinstance(movie_id, int):
                try:
                    self.app.db.set_providers(
                        [(movie_id, region, ", ".join(providers[:6]), extras.get("watch"))]
                    )
                except Exception:  # noqa: BLE001 - кэш не критичен
                    pass


class HistoryWindow(tk.Toplevel):
    """Последние открытые фильмы."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.movies = app.db.recent_views(50)

        self.title("История просмотров")
        self.geometry("640x520")
        self.configure(bg=BG)
        self.transient(app)
        self.bind("<Escape>", lambda _e: self.destroy())

        tk.Label(
            self, text="История просмотров", bg=BG, fg=TEXT, font=(FONT, 15, "bold")
        ).pack(anchor="w", padx=20, pady=(16, 4))

        if not self.movies:
            tk.Label(
                self,
                text="Пока пусто — откройте любой фильм, и он появится здесь.",
                bg=BG,
                fg=MUTED,
                font=FONT_TEXT,
            ).pack(anchor="w", padx=20, pady=10)
            ttk.Button(self, text="Закрыть", style="Ghost.TButton", command=self.destroy).pack(
                side="bottom", pady=12
            )
            return

        self.listbox = tk.Listbox(
            self,
            bg=CARD,
            fg=TEXT,
            font=FONT_TEXT,
            bd=0,
            highlightthickness=1,
            highlightbackground=BORDER,
            selectbackground=ACCENT,
            selectforeground="#08101f",
            activestyle="none",
        )
        for movie in self.movies:
            self.listbox.insert("end", f"{movie['title']} ({movie['year'] or '—'})")
        self.listbox.pack(fill="both", expand=True, padx=20, pady=(6, 10))
        self.listbox.bind("<Double-Button-1>", self._open_selected)

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", padx=20, pady=(0, 14))
        ttk.Button(
            buttons, text="Открыть фильм", style="Accent.TButton", command=self._open_selected
        ).pack(side="left")
        ttk.Button(
            buttons, text="Закрыть", style="Ghost.TButton", command=self.destroy
        ).pack(side="right")

    def _open_selected(self, _event=None) -> None:
        selection = self.listbox.curselection()
        if not selection:
            return
        self.app.open_details(self.movies[selection[0]])


class TasteStatsWindow(tk.Toplevel):
    """Aggregated view of the user's saved taste and viewing activity."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.title(app._text("Моя статистика вкусов", "My taste stats"))
        self.geometry("720x640")
        self.minsize(580, 460)
        self.configure(bg=BG)
        self.transient(app)
        self.bind("<Escape>", lambda _event: self.destroy())

        tk.Label(
            self,
            text=app._text("Моя статистика", "My taste stats"),
            bg=BG,
            fg=TEXT,
            font=(FONT, 15, "bold"),
        ).pack(anchor="w", padx=20, pady=(16, 8))
        content = tk.Frame(self, bg=BG)
        content.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        self.text = tk.Text(
            content,
            bg=CARD,
            fg=TEXT,
            font=FONT_TEXT,
            wrap="word",
            bd=0,
            height=16,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=14,
            pady=12,
            state="disabled",
        )
        scroll = ttk.Scrollbar(content, orient="vertical", command=self.text.yview)
        self.text.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True)
        ttk.Button(
            self,
            text="Закрыть",
            style="Ghost.TButton",
            command=self.destroy,
        ).pack(side="bottom", pady=(0, 14))
        self.refresh()

    def refresh(self) -> None:
        english = self.app.is_english
        text = self.app._text
        self.title(text("Моя статистика вкусов", "My taste stats"))
        try:
            stats = self.app.db.taste_stats()
        except Exception as exc:
            content = text(
                f"Не удалось загрузить статистику:\n{exc}",
                f"Could not load statistics:\n{exc}",
            )
        else:
            has_personal_data = any(
                stats[key] for key in ("watched", "rated", "bookmarked", "history_count")
            )
            if not has_personal_data:
                content = text(
                    "Пока нет личных данных. Отметьте просмотренные фильмы или поставьте оценку.",
                    "No personal data yet. Mark a movie watched or give it a rating.",
                )
            else:
                average = (
                    f"{stats['average_rating']:.2f}"
                    if stats["average_rating"] is not None
                    else "—"
                )
                lines = [
                    text(
                        f"Просмотрено: {stats['watched']}    Оценено: {stats['rated']}",
                        f"Watched: {stats['watched']}    Rated: {stats['rated']}",
                    ),
                    text(
                        f"Средняя оценка: {average}    Закладки: {stats['bookmarked']}",
                        f"Average rating: {average}    Bookmarks: {stats['bookmarked']}",
                    ),
                    text(
                        f"История открытий: {stats['history_count']}",
                        f"View history: {stats['history_count']}",
                    ),
                ]

                def section(title: str) -> None:
                    lines.extend(["", title])

                section(text("Оценки по шкале", "Rating distribution"))
                if stats["rating_distribution"]:
                    lines.extend(
                        f"  {item['rating']}/10 — {item['count']}"
                        for item in stats["rating_distribution"]
                    )
                else:
                    lines.append("  " + text("Нет данных для статистики.", "No statistics available."))

                section(text("Любимые жанры", "Favorite genres"))
                if stats["favorite_genres"]:
                    for item in stats["favorite_genres"]:
                        name = (
                            GENRE_NAMES_EN.get(item["genre"], item["genre"])
                            if english
                            else genre_label(item["genre"])
                        )
                        rating = (
                            f", ★ {item['average_rating']:.2f}"
                            if item["average_rating"] is not None
                            else ""
                        )
                        lines.append(f"  {name} — {item['count']}{rating}")
                else:
                    lines.append("  " + text("Нет данных для статистики.", "No statistics available."))

                section(text("Фильмы по годам", "Movies by year"))
                lines.extend(
                    f"  {item['year']} — {item['count']}" for item in stats["years"]
                )
                if not stats["years"]:
                    lines.append("  " + text("Нет данных для статистики.", "No statistics available."))

                section(text("Активность по месяцам", "Activity by month"))
                lines.extend(
                    f"  {item['month']} — {item['count']}" for item in stats["activity_by_month"]
                )
                if not stats["activity_by_month"]:
                    lines.append("  " + text("Нет данных для статистики.", "No statistics available."))
                content = "\n".join(lines)

        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", content)
        self.text.configure(state="disabled")


class SettingsWindow(tk.Toplevel):
    """Ключ TMDb и параметры загрузки базы."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.cfg = app.cfg

        self.title("Настройки")
        self.geometry("660x820")
        self.configure(bg=BG)
        self.transient(app)
        self.resizable(False, False)
        self.bind("<Escape>", lambda _e: self.destroy())

        pad = {"padx": 22}
        tk.Label(
            self, text="Настройки", bg=BG, fg=TEXT, font=(FONT, 15, "bold")
        ).pack(anchor="w", pady=(18, 4), **pad)

        tk.Label(
            self,
            text="Ключ TMDb API (v3). Получить бесплатно:\n"
            "themoviedb.org → Настройки → API → API Key (v3 auth)",
            bg=BG,
            fg=MUTED,
            font=(FONT, 9),
            justify="left",
        ).pack(anchor="w", pady=(0, 8), **pad)

        self.key_var = tk.StringVar(value=self.cfg.api_key)
        self.key_entry = ttk.Entry(self, textvariable=self.key_var, show="•")
        self.key_entry.pack(fill="x", pady=(0, 8), **pad)

        row = tk.Frame(self, bg=BG)
        row.pack(fill="x", pady=(4, 0), **pad)
        tk.Label(
            row, text="Страниц на год (1–10):", bg=BG, fg=TEXT, font=FONT_TEXT
        ).pack(side="left")
        self.pages_var = tk.StringVar(value=str(self.cfg.pages_per_year))
        ttk.Spinbox(
            row, from_=1, to=10, textvariable=self.pages_var, width=5
        ).pack(side="left", padx=8)
        tk.Label(
            row,
            text="20 фильмов на страницу",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
        ).pack(side="left")

        row2 = tk.Frame(self, bg=BG)
        row2.pack(fill="x", pady=(10, 0), **pad)
        tk.Label(
            row2, text="Язык загрузки из TMDb:", bg=BG, fg=TEXT, font=FONT_TEXT
        ).pack(side="left")
        self.lang_var = tk.StringVar(value=self.cfg.language)
        ttk.Combobox(
            row2,
            textvariable=self.lang_var,
            values=["ru-RU", "en-US"],
            state="readonly",
            width=10,
        ).pack(side="left", padx=8)

        row3 = tk.Frame(self, bg=BG)
        row3.pack(fill="x", pady=(8, 0), **pad)
        tk.Label(
            row3, text="Язык интерфейса:", bg=BG, fg=TEXT, font=FONT_TEXT
        ).pack(side="left")
        self.ui_lang_var = tk.StringVar(
            value="English" if self.app.is_english else "Русский"
        )
        ttk.Combobox(
            row3,
            textvariable=self.ui_lang_var,
            values=["Русский", "English"],
            state="readonly",
            width=10,
        ).pack(side="left", padx=8)
        tk.Label(
            row3,
            text="подписи, кнопки и описания",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
        ).pack(side="left")

        self.hint = tk.Label(
            self, text="", bg=BG, fg=MUTED, font=(FONT, 9), justify="left", wraplength=540
        )
        self.hint.pack(anchor="w", pady=(14, 0), **pad)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=12, **pad)
        tk.Label(
            self, text="Моя коллекция и плеер", bg=BG, fg=TEXT, font=(FONT, 11, "bold")
        ).pack(anchor="w", **pad)
        tk.Label(
            self,
            text="Укажите папку с фильмами — приложение сопоставит файлы с базой,\n"
            "и в окне фильма появится кнопка «Смотреть» (откроется в вашем плеере).",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
            justify="left",
        ).pack(anchor="w", pady=(2, 8), **pad)

        player_row = tk.Frame(self, bg=BG)
        player_row.pack(fill="x", pady=(0, 6), **pad)
        tk.Label(player_row, text="Плеер:", bg=BG, fg=TEXT, font=FONT_TEXT, width=8, anchor="w").pack(side="left")
        self.player_var = tk.StringVar(value=str(self.cfg.get("player_path") or ""))
        ttk.Entry(player_row, textvariable=self.player_var).pack(side="left", fill="x", expand=True)
        ttk.Button(
            player_row, text="Найти", style="Ghost.TButton", command=self._detect_player
        ).pack(side="left", padx=(6, 0))
        ttk.Button(
            player_row, text="Обзор…", style="Ghost.TButton", command=self._browse_player
        ).pack(side="left", padx=(6, 0))

        folder_row = tk.Frame(self, bg=BG)
        folder_row.pack(fill="x", pady=(0, 6), **pad)
        tk.Label(folder_row, text="Папка:", bg=BG, fg=TEXT, font=FONT_TEXT, width=8, anchor="w").pack(side="left")
        self.folder_var = tk.StringVar(value=str(self.cfg.get("movies_folder") or ""))
        ttk.Entry(folder_row, textvariable=self.folder_var).pack(side="left", fill="x", expand=True)
        ttk.Button(
            folder_row, text="Обзор…", style="Ghost.TButton", command=self._browse_folder
        ).pack(side="left", padx=(6, 0))

        self.scan_btn = ttk.Button(
            self, text="Найти файлы в папке", style="Ghost.TButton", command=self._scan_files
        )
        self.scan_btn.pack(anchor="w", pady=(2, 0), **pad)
        self.scan_status = tk.Label(
            self, text="", bg=BG, fg=MUTED, font=FONT_SMALL, justify="left", wraplength=560
        )
        self.scan_status.pack(anchor="w", pady=(6, 0), **pad)

        tk.Frame(self, bg=BORDER, height=1).pack(fill="x", pady=12, **pad)
        tk.Label(
            self, text="Личные данные", bg=BG, fg=TEXT, font=(FONT, 11, "bold")
        ).pack(anchor="w", **pad)
        tk.Label(
            self,
            text=(
                "Просмотренное, личные оценки, закладки и сохранённые подборки. "
                "Список просмотра и отзывы к рекомендациям тоже экспортируются. "
                "Планы просмотра и исключения контента тоже экспортируются. "
                "Каталог, постеры и ключи не экспортируются. Регулярно храните JSON-копию отдельно."
            ),
            bg=BG, fg=MUTED, font=FONT_SMALL, wraplength=560, justify="left",
        ).pack(anchor="w", pady=(3, 7), **pad)
        personal_row = tk.Frame(self, bg=BG)
        personal_row.pack(fill="x", pady=(0, 4), **pad)
        ttk.Button(
            personal_row, text="Экспорт личных данных", style="Ghost.TButton",
            command=self.export_personal_data,
        ).pack(side="left")
        ttk.Button(
            personal_row, text="Импорт личных данных", style="Ghost.TButton",
            command=self.import_personal_data,
        ).pack(side="left", padx=(8, 0))

        tk.Label(
            self,
            text="Ключ хранится только в файле config.json рядом с программой\n"
            "и используется для запросов к api.themoviedb.org.\n"
            "Обновление базы не заменяет офлайн-каталог, а дополняет его.",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
            justify="left",
        ).pack(anchor="w", pady=(14, 0), **pad)

        tk.Label(
            self,
            text=f"База: {DB_PATH}",
            bg=BG,
            fg=MUTED,
            font=FONT_SMALL,
            justify="left",
            wraplength=540,
        ).pack(anchor="w", pady=(8, 0), **pad)

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", side="bottom", pady=18, **pad)
        ttk.Button(
            buttons, text="Проверить ключ", style="Ghost.TButton", command=self.check_key
        ).pack(side="left")
        ttk.Button(
            buttons, text="Сохранить", style="Accent.TButton", command=self.save
        ).pack(side="right")
        ttk.Button(
            buttons, text="Отмена", style="Ghost.TButton", command=self.destroy
        ).pack(side="right", padx=8)

    def _values(self) -> tuple[str, int, str]:
        try:
            pages = max(1, min(10, int(self.pages_var.get())))
        except ValueError:
            pages = 3
        return self.key_var.get().strip(), pages, self.lang_var.get()

    def check_key(self) -> None:
        key, _, language = self._values()
        if not key:
            self.hint.configure(text="Сначала вставьте ключ.", fg=GOLD)
            return
        self.hint.configure(text="Проверяю ключ…", fg=MUTED)

        def worker() -> None:
            try:
                TMDBClient(key, language).check_key()
                message = "Ключ работает. Можно сохранять."
                color = "#5ad18a"
            except TMDBError as exc:
                message = str(exc)
                color = "#ff7b72"
            except Exception as exc:  # noqa: BLE001
                message = f"Ошибка проверки: {exc}"
                color = "#ff7b72"
            self.app._post(  # noqa: SLF001 - единая очередь UI
                lambda: self.hint.configure(text=message, fg=color)
                if self.winfo_exists()
                else None
            )

        threading.Thread(target=worker, daemon=True).start()

    def _detect_player(self) -> None:
        players = detect_players()
        name, path = default_player(players)
        if path:
            self.player_var.set(path)
            self.scan_status.configure(text=f"Найден плеер: {name} — {path}")
        else:
            found = ", ".join(key for key, value in players.items() if value) or "ничего"
            self.scan_status.configure(
                text=f"Плееры не найдены (проверено: {found}). Укажите путь вручную."
            )

    def _browse_player(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title="Выберите программу-плеер",
            filetypes=[("Программа", "*.exe"), ("Все файлы", "*.*")],
        )
        if path:
            self.player_var.set(path)

    def _browse_folder(self) -> None:
        path = filedialog.askdirectory(parent=self, title="Папка с фильмами")
        if path:
            self.folder_var.set(path)

    def _scan_files(self) -> None:
        folder = self.folder_var.get().strip()
        if not folder:
            self.scan_status.configure(text="Сначала выберите папку с фильмами.")
            return
        self.scan_btn.configure(state="disabled")
        self.scan_status.configure(text="Ищу файлы и сопоставляю с базой…")

        def worker() -> None:
            try:
                result = match_files(self.app.db, folder)
            except Exception as exc:  # noqa: BLE001 - показываем причину в окне
                self.app._post(  # noqa: SLF001
                    lambda error=exc: self._scan_done({"error": str(error)})
                )
                return
            self.app._post(lambda: self._scan_done(result))  # noqa: SLF001

        threading.Thread(target=worker, daemon=True).start()

    def _scan_done(self, result: dict) -> None:
        self.scan_btn.configure(state="normal")
        if result.get("error"):
            self.scan_status.configure(text=f"Ошибка: {result['error']}")
            return
        matched = result.get("matched", 0)
        total = result.get("total", 0)
        self.scan_status.configure(
            text=f"Сопоставлено фильмов: {matched} из {total} файлов. "
            "Откройте фильм — там будет кнопка «Смотреть»."
        )
        if self.folder_var.get().strip():
            self.cfg.set("movies_folder", self.folder_var.get().strip())
        self.app.search()

    def export_personal_data(self) -> None:
        path = filedialog.asksaveasfilename(
            parent=self,
            title=self.app._text("Экспорт личных данных", "Export personal data"),
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="movie-finder-personal-data.json",
        )
        if not path:
            return
        target = Path(path)
        # Пишем через временный файл рядом: обрыв не испортит прежний бэкап.
        temp = target.with_name(target.name + ".tmp")
        try:
            payload = self.app.db.export_personal_data()
            temp.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
            )
            os.replace(temp, target)
        except Exception as exc:
            try:
                temp.unlink(missing_ok=True)
            except OSError:
                pass
            messagebox.showerror(
                self.app._text("Ошибка экспорта", "Export failed"), str(exc), parent=self
            )
            return
        messagebox.showinfo(
            self.app._text("Экспорт завершён", "Export complete"),
            self.app._text(
                f"Фильмов: {len(payload['movies'])}, в списке: {len(payload['watchlist'])}, "
                f"отзывов: {len(payload['recommendation_feedback'])}, "
                f"подборок: {len(payload['saved_filters'])}, "
                f"планов: {len(payload['plans'])}, "
                f"исключений: {sum(len(values) for values in payload['content_exclusions'].values())}.",
                f"Movies: {len(payload['movies'])}, watchlist: {len(payload['watchlist'])}, "
                f"feedback: {len(payload['recommendation_feedback'])}, "
                f"saved filters: {len(payload['saved_filters'])}, "
                f"plans: {len(payload['plans'])}, "
                f"exclusions: {sum(len(values) for values in payload['content_exclusions'].values())}.",
            ),
            parent=self,
        )

    def import_personal_data(self) -> None:
        path = filedialog.askopenfilename(
            parent=self,
            title=self.app._text("Импорт личных данных", "Import personal data"),
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception as exc:
            messagebox.showerror(
                self.app._text("Ошибка импорта", "Import failed"), str(exc), parent=self
            )
            return
        if not isinstance(payload, dict) or not isinstance(payload.get("movies"), list):
            messagebox.showerror(
                self.app._text("Ошибка импорта", "Import failed"),
                self.app._text(
                    "Файл не похож на выгрузку Movie Finder.",
                    "The file does not look like a Movie Finder export.",
                ),
                parent=self,
            )
            return
        # Импорт заменяет отметки для всех фильмов из файла — спрашиваем явно.
        if not messagebox.askyesno(
            self.app._text("Импорт личных данных", "Import personal data"),
            self.app._text(
                f"В файле фильмов: {len(payload['movies'])}.\n\n"
                "Текущие отметки, оценки и закладки для этих фильмов будут "
                "заменены данными из файла. Продолжить?",
                f"Movies in the file: {len(payload['movies'])}.\n\n"
                "Current watched marks, ratings and bookmarks for those movies "
                "will be replaced with the file data. Continue?",
            ),
            parent=self,
        ):
            return
        try:
            result = self.app.db.import_personal_data(payload)
        except Exception as exc:
            messagebox.showerror(
                self.app._text("Ошибка импорта", "Import failed"), str(exc), parent=self
            )
            return
        unknown = result["unknown_ids"]
        details = self.app._text(
            f"Состояний фильмов: {result['imported']}, в списке: "
            f"{result.get('watchlist_imported', 0)}, отзывов: "
            f"{result.get('feedback_imported', 0)}, планов: "
            f"{result.get('plans_imported', 0)}, исключений: "
            f"{result.get('content_exclusions_imported', 0)}. "
            "Неизвестные ID (не импортированы): "
            f"{', '.join(map(str, unknown[:20])) or 'нет'}"
            + (f" и ещё {len(unknown) - 20}" if len(unknown) > 20 else ""),
            f"Movie states: {result['imported']}, watchlist: "
            f"{result.get('watchlist_imported', 0)}, feedback: "
            f"{result.get('feedback_imported', 0)}, plans: "
            f"{result.get('plans_imported', 0)}, exclusions: "
            f"{result.get('content_exclusions_imported', 0)}. Unknown IDs (skipped): "
            f"{', '.join(map(str, unknown[:20])) or 'none'}"
            + (f" and {len(unknown) - 20} more" if len(unknown) > 20 else ""),
        )
        messagebox.showinfo(
            self.app._text("Импорт завершён", "Import complete"), details, parent=self
        )
        self.app._refresh_saved_filters()
        self.app.search()

    def save(self) -> None:
        key, pages, language = self._values()
        env_key = (os.environ.get("TMDB_API_KEY") or "").strip()
        results: list[bool] = []
        # Ключ из переменной окружения не копируем в файл: это секрет среды.
        if not (env_key and key.strip() == env_key):
            results.append(self.cfg.set("tmdb_api_key", key))
        results.extend([
            self.cfg.set("pages_per_year", pages),
            self.cfg.set("language", language),
            self.cfg.set("player_path", self.player_var.get().strip()),
            self.cfg.set("movies_folder", self.folder_var.get().strip()),
        ])
        if not all(results):
            messagebox.showwarning(
                self.app._text("Настройки не сохранены", "Settings were not saved"),
                self.app._text(
                    "Не удалось записать config.json: папка программы недоступна "
                    "для записи. Настройки будут действовать до закрытия программы.",
                    "config.json could not be written: the program folder is "
                    "read-only. Settings will apply until the app is closed.",
                ),
                parent=self,
            )
            return
        # Язык интерфейса применяется сразу; язык загрузки TMDb — отдельная настройка.
        self.app.set_ui_language(
            "en-US" if self.ui_lang_var.get().startswith("English") else "ru-RU"
        )
        self.app._refresh_stats()
        self.destroy()


class SyncWindow(tk.Toplevel):
    """Окно загрузки/обновления базы из TMDb."""

    def __init__(self, app: MovieApp, recent_only: bool = False) -> None:
        super().__init__(app)
        self.app = app
        self.job: SyncJob | None = None
        self._finished = False
        self.recent_only = recent_only

        self.title(
            "Обновление новинок" if recent_only else "Обновление базы из TMDb"
        )
        self.geometry("760x520")
        self.configure(bg=BG)
        self.transient(app)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        pad = {"padx": 20}
        tk.Label(
            self, text="Обновление новинок" if recent_only else "Обновление базы из TMDb",
            bg=BG, fg=TEXT, font=(FONT, 15, "bold"),
        ).pack(anchor="w", pady=(18, 6), **pad)

        key = app.cfg.api_key
        self.info = tk.Label(
            self,
            text=(
                f"Ключ: …{key[-4:]}  ·  страниц на год: "
                f"{3 if recent_only else app.cfg.pages_per_year}  ·  "
                + (
                    f"годы {RECENT_YEARS_FROM}–{SYNC_TO_YEAR} (только новинки)"
                    if recent_only
                    else f"годы {SYNC_FROM_YEAR}–{SYNC_TO_YEAR}"
                )
                if key
                else "Ключ TMDb не задан. Откройте «Настройки» и вставьте API Key (v3)."
            ),
            bg=BG,
            fg=TEXT if key else "#ff9f7b",
            font=(FONT, 9),
            justify="left",
        )
        self.info.pack(anchor="w", **pad)

        self.progress = ttk.Progressbar(self, mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(14, 6), **pad)
        self.progress_lbl = tk.Label(
            self, text="Ожидание", bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w"
        )
        self.progress_lbl.pack(fill="x", **pad)

        buttons = tk.Frame(self, bg=BG)
        buttons.pack(fill="x", side="bottom", pady=(0, 16), **pad)
        self.start_btn = ttk.Button(
            buttons, text="Начать загрузку", style="Accent.TButton", command=self.start
        )
        self.start_btn.pack(side="left")
        self.close_btn = ttk.Button(
            buttons, text="Закрыть", style="Ghost.TButton", command=self._on_close
        )
        self.close_btn.pack(side="right")

        log_wrap = tk.Frame(self, bg=BG)
        log_wrap.pack(fill="both", expand=True, pady=(10, 10), **pad)
        self.log = tk.Text(
            log_wrap,
            bg=CARD,
            fg=MUTED,
            font=(FONT, 9),
            wrap="word",
            bd=0,
            height=6,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=10,
            pady=8,
        )
        scroll = ttk.Scrollbar(log_wrap, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set, state="disabled")
        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        self.log_message(
            "Загрузка занимает несколько минут: приложение скачает список фильмов "
            f"за каждый год ({SYNC_FROM_YEAR}–{SYNC_TO_YEAR}), затем детали, страны и постеры."
        )
        if not key:
            self.start_btn.configure(state="disabled")

    # ------------------------------------------------------------- сервис
    def log_message(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def start(self) -> None:
        if self.job and self.job.running:
            return
        self.start_btn.configure(state="disabled")
        self._finished = False
        self.job = SyncJob(
            self.app.db,
            self.app.cfg.api_key,
            language=self.app.cfg.language,
            pages=3 if self.recent_only else self.app.cfg.pages_per_year,
            min_votes=self.app.cfg.min_vote_count,
            years=range(RECENT_YEARS_FROM, SYNC_TO_YEAR + 1) if self.recent_only else None,
        )
        self.job.start()
        self.after(120, self._poll)

    def _poll(self) -> None:
        if not self.winfo_exists():
            return
        job = self.job
        if job is None:
            return
        try:
            while True:
                message = job.queue.get_nowait()
                kind = message[0]
                if kind == "log":
                    self.log_message(str(message[1]))
                elif kind == "progress":
                    done, total, label = message[1], message[2], message[3]
                    percent = (done / total * 100) if total else 0
                    self.progress.configure(value=percent)
                    self.progress_lbl.configure(text=f"{label} · {percent:.0f}%")
                elif kind == "error":
                    self.progress_lbl.configure(text="Ошибка")
                    self.log_message(f"ОШИБКА: {message[1]}")
                    self.start_btn.configure(state="normal")
                    self._finished = True
                    # Часть данных могла успеть сохраниться — показываем актуальное.
                    self.app._refresh_stats()  # noqa: SLF001
                    self.app.search()
                elif kind == "done":
                    added = message[1]
                    self._finished = True
                    self.progress.configure(value=100)
                    self.progress_lbl.configure(text="Готово")
                    self.log_message(f"Готово. Добавлено/обновлено фильмов: {added}")
                    self.start_btn.configure(state="normal")
                    self.app._refresh_stats()
                    self.app.search()
                    if self.recent_only:
                        self._update_providers()
        except queue.Empty:
            pass
        if not self._finished:
            self.after(150, self._poll)

    def _update_providers(self) -> None:
        """После догрузки новинок подтягиваем площадки показа для них."""
        key = self.app.cfg.api_key
        if not key:
            return
        self.log_message("Обновляю площадки показа для новинок…")
        db = self.app.db

        def worker() -> None:
            ids = db.providers_missing(2020, 300)
            saved = 0
            if ids:
                with ThreadPoolExecutor(max_workers=6) as pool:
                    futures = {pool.submit(fetch_providers, mid, key): mid for mid in ids}
                    for future in as_completed(futures):
                        try:
                            result = future.result()
                        except Exception:  # noqa: BLE001 - один фильм не критичен
                            continue
                        if result:
                            region, names, link = result
                            try:
                                db.set_providers([(futures[future], region, names, link)])
                                saved += 1
                            except Exception:  # noqa: BLE001
                                continue
            self.app._post(  # noqa: SLF001
                lambda: self.log_message(f"Площадки обновлены: {saved}")
            )

        threading.Thread(target=worker, daemon=True).start()

    def _on_close(self) -> None:
        if self.job and self.job.running and not self._finished:
            if not messagebox.askyesno(
                "Остановить загрузку?",
                "Загрузка ещё идёт. Остановить её и закрыть окно?",
                parent=self,
            ):
                return
            self.job.cancel()
        self.destroy()


class FranchiseWindow(tk.Toplevel):
    """Displays the verified TMDb release order for the selected movie's collection."""

    def __init__(self, app: MovieApp, movie: dict[str, Any]) -> None:
        super().__init__(app)
        self.app = app
        self.movie = movie
        self.collection: dict[str, Any] | None = None
        self.error: Exception | None = None
        api_key = app.cfg.api_key
        self.no_api_key = not bool(api_key)
        self.loading = False
        self.parts_by_id: dict[int, dict[str, Any]] = {}
        self.title(self._text("Серии и франшизы", "Series & franchises"))
        self.geometry("760x470")
        self.minsize(620, 360)
        self.configure(bg=BG)
        self.transient(app)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=16)
        self.heading = tk.Label(
            body, bg=BG, fg=TEXT, font=FONT_H1, anchor="w", justify="left"
        )
        self.heading.pack(fill="x")
        self.source_label = tk.Label(
            body, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w"
        )
        self.source_label.pack(fill="x", pady=(4, 10))
        self.next_label = tk.Label(
            body, bg=CARD, fg=TEXT, font=FONT_TEXT, anchor="w",
            justify="left", wraplength=700,
        )
        self.next_label.pack(fill="x", pady=(0, 8), ipady=6)
        self.tree = ttk.Treeview(
            body, columns=("order", "title", "year", "watched"),
            show="headings", selectmode="browse",
        )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_actions())
        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(10, 0))
        self.open_btn = ttk.Button(
            actions, style="Accent.TButton", command=self._open_selected, state="disabled"
        )
        self.open_btn.pack(side="left")
        self.next_btn = ttk.Button(
            actions, style="Ghost.TButton", command=self._open_next, state="disabled"
        )
        self.next_btn.pack(side="left", padx=(8, 0))
        self.close_btn = ttk.Button(
            actions, style="Ghost.TButton", command=self.destroy
        )
        self.close_btn.pack(side="right")
        self.refresh_language()
        app._register_window(self)
        if not api_key:
            self.loading = False
            self._show_status()
        else:
            self.loading = True
            self._show_status()
            threading.Thread(
                target=self._load_worker,
                args=(api_key,),
                daemon=True,
                name="franchise-order",
            ).start()

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def refresh_language(self) -> None:
        self.title(self._text("Серии и франшизы", "Series & franchises"))
        self.heading.configure(text=str(self.movie.get("title") or ""))
        for column, russian, english, width in (
            ("order", "Порядок", "Order", 70),
            ("title", "Фильм", "Movie", 390),
            ("year", "Год", "Year", 80),
            ("watched", "Просмотр", "Watched", 150),
        ):
            self.tree.heading(column, text=self._text(russian, english))
            self.tree.column(column, width=width, anchor="w")
        self.open_btn.configure(text=self._text("Открыть фильм", "Open movie"))
        self.next_btn.configure(text=self._text(
            "Открыть следующий", "Open next movie"
        ))
        self.close_btn.configure(text=self._text("Закрыть", "Close"))
        self._show_status()
        self._populate()

    def _show_status(self) -> None:
        if self.loading:
            text = self._text("Загружаю порядок из TMDb…", "Loading order from TMDb…")
        elif self.no_api_key:
            text = self._text(
                "Нужен ключ TMDb; запрос не выполнялся.",
                "A TMDb API key is required; no request was made.",
            )
        elif self.error is not None:
            text = self._text("Не удалось загрузить данные TMDb.", "Could not load TMDb data.")
        elif self.collection is None:
            text = self._text(
                "TMDb не подтвердил принадлежность фильма к франшизе.",
                "TMDb did not verify that this movie belongs to a franchise.",
            )
        else:
            text = self._text(
                f"Источник: {self.collection['source']} · порядок по датам выхода.",
                f"Source: {self.collection['source']} · ordered by release date.",
            )
        self.source_label.configure(text=text)

    def _load_worker(self, api_key: str) -> None:
        try:
            result = franchise_order(
                self.app.db,
                TMDBClient(api_key, self.app.cfg.get("language") or "ru-RU"),
                int(self.movie["id"]),
            )
        except Exception as exc:
            self.app._post(lambda error=exc: self._load_failed(error))
            return
        self.app._post(lambda: self._loaded(result))

    def _load_failed(self, error: Exception) -> None:
        if not self.winfo_exists():
            return
        self.loading = False
        self.error = error
        self._show_status()
        messagebox.showerror(
            self._text("Ошибка TMDb", "TMDb error"), str(error), parent=self
        )

    def _loaded(self, collection: dict[str, Any] | None) -> None:
        if not self.winfo_exists():
            return
        self.loading = False
        self.collection = collection
        self._show_status()
        self._populate()

    def _populate(self) -> None:
        if not hasattr(self, "tree"):
            return
        self.tree.delete(*self.tree.get_children())
        self.parts_by_id = {}
        self.next_movie = next_unwatched_in_order(
            self.collection, int(self.movie["id"])
        )
        if self.next_movie:
            self.next_label.configure(text=self._text(
                f"Следующий подтверждённый фильм: {self.next_movie['title']} "
                f"({self.next_movie.get('year') or '—'}). "
                f"{self.next_movie['explanation']}",
                f"Next verified movie: {self.next_movie['title']} "
                f"({self.next_movie.get('year') or '—'}). "
                "Next by confirmed release date; in the catalogue and not marked watched.",
            ))
            self.next_btn.configure(state="normal")
        else:
            self.next_label.configure(text=self._text(
                "Следующий фильм не подтверждён: не хватает дат, каталожных данных "
                "или непосмотренной части после выбранного фильма.",
                "No next movie can be verified: release dates, local catalogue data, "
                "or an unwatched later part are missing.",
            ))
            self.next_btn.configure(state="disabled")
        if not self.collection:
            self._sync_actions()
            return
        self.heading.configure(text=self.collection["title"])
        for index, part in enumerate(self.collection["parts"], 1):
            self.parts_by_id[int(part["id"])] = part
            if not part["in_catalog"]:
                watched = self._text("Нет в каталоге", "Not in catalogue")
            else:
                watched = self._text(
                    "Просмотрено" if part["watched"] else "Не просмотрено",
                    "Watched" if part["watched"] else "Not watched",
                )
            self.tree.insert(
                "", "end", iid=str(part["id"]),
                values=(index, part["title"], part["year"] or "—", watched),
            )
        self._sync_actions()

    def _sync_actions(self) -> None:
        selection = self.tree.selection() if hasattr(self, "tree") else ()
        self.open_btn.configure(state="normal" if selection else "disabled")

    def _open_selected(self) -> None:
        selection = self.tree.selection()
        part = self.parts_by_id.get(int(selection[0])) if selection else None
        if part is None:
            return
        movie = self.app.db.get(part["id"])
        if movie:
            self.app.open_details(movie)
        else:
            webbrowser.open(part["url"])

    def _open_next(self) -> None:
        part = getattr(self, "next_movie", None)
        if part is None:
            return
        movie = self.app.db.get(int(part["id"]))
        if movie is not None:
            self.app.open_details(movie)


class SequelNotificationsWindow(tk.Toplevel):
    """Shows saved sequel discoveries for monitored watchlist collections."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.title(self._text("Продолжения", "Sequels"))
        self.geometry("720x430")
        self.minsize(600, 340)
        self.configure(bg=BG)
        self.transient(app)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=18, pady=16)
        self.heading = tk.Label(
            body, bg=BG, fg=TEXT, font=FONT_H1, anchor="w"
        )
        self.heading.pack(fill="x")
        self.source_label = tk.Label(
            body, bg=BG, fg=MUTED, font=FONT_SMALL, anchor="w"
        )
        self.source_label.pack(fill="x", pady=(4, 10))
        self.tree = ttk.Treeview(
            body, columns=("title", "year", "date", "status"),
            show="headings", selectmode="browse",
        )
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _event: self._sync_actions())
        actions = tk.Frame(body, bg=BG)
        actions.pack(fill="x", pady=(10, 0))
        self.open_btn = ttk.Button(
            actions, style="Accent.TButton", command=self._open_selected, state="disabled"
        )
        self.open_btn.pack(side="left")
        self.read_btn = ttk.Button(
            actions, style="Ghost.TButton", command=self._mark_read
        )
        self.read_btn.pack(side="left", padx=(8, 0))
        self.close_btn = ttk.Button(
            actions, style="Ghost.TButton", command=self.destroy
        )
        self.close_btn.pack(side="right")
        self.rows: dict[str, dict[str, Any]] = {}
        self.refresh_language()
        app._register_window(self)

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def refresh_language(self) -> None:
        self.title(self._text("Продолжения", "Sequels"))
        self.heading.configure(text=self._text(
            "Найденные продолжения", "Discovered sequels"
        ))
        self.source_label.configure(text=self._text(
            "Источник: подтверждённые коллекции TMDb · отслеживается список «Хочу посмотреть».",
            "Source: verified TMDb collections · monitoring the watchlist.",
        ))
        for column, russian, english, width in (
            ("title", "Фильм", "Movie", 360),
            ("year", "Год", "Year", 75),
            ("date", "Дата проверки", "Discovered", 150),
            ("status", "Статус", "Status", 110),
        ):
            self.tree.heading(column, text=self._text(russian, english))
            self.tree.column(column, width=width, anchor="w")
        self.open_btn.configure(text=self._text("Открыть фильм", "Open movie"))
        self.read_btn.configure(text=self._text("Отметить прочитанным", "Mark as read"))
        self.close_btn.configure(text=self._text("Закрыть", "Close"))
        self._populate()

    def _populate(self) -> None:
        self.rows = {}
        self.tree.delete(*self.tree.get_children())
        for row in self.app.db.sequel_notifications():
            iid = f"{row['collection_id']}:{row['movie_id']}"
            self.rows[iid] = row
            status = self._text(
                "Прочитано" if row["is_read"] else "Новое",
                "Read" if row["is_read"] else "New",
            )
            self.tree.insert(
                "", "end", iid=iid,
                values=(
                    row["title"], row["year"] or "—",
                    row["created_at"][:10], status,
                ),
            )
        if not self.rows:
            self.tree.insert(
                "", "end", iid="empty",
                values=(self._text(
                    "Пока нет подтверждённых новых частей.",
                    "No verified new installments yet.",
                ), "", "", ""),
            )
        self._sync_actions()

    def _sync_actions(self) -> None:
        selection = self.tree.selection() if hasattr(self, "tree") else ()
        selected = selection[0] if selection else ""
        row = self.rows.get(selected)
        self.open_btn.configure(state="normal" if row else "disabled")
        self.read_btn.configure(
            state="normal" if any(not item["is_read"] for item in self.rows.values())
            else "disabled"
        )

    def _open_selected(self) -> None:
        selection = self.tree.selection()
        row = self.rows.get(selection[0]) if selection else None
        if row is None:
            return
        movie = self.app.db.get(row["movie_id"])
        if movie:
            self.app.open_details(movie)
        else:
            webbrowser.open(row["url"])

    def _mark_read(self) -> None:
        self.app.db.mark_sequel_notifications_read()
        self.app._refresh_sequel_indicator()
        self._populate()


def main() -> None:
    """Точка входа GUI."""
    app = MovieApp()
    app.mainloop()


if __name__ == "__main__":
    main()
