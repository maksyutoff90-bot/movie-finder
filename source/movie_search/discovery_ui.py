"""Window for local, personalized movie discovery modes."""

from __future__ import annotations

import threading
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable

from .const import COUNTRIES, COUNTRIES_EN
from .discovery_modes import (
    blind_choice,
    challenge_progress,
    filmography,
    indifferent_movies,
    movie_twin,
    reveal_blind_choice,
    yearly_summary,
)
from .ui import BG, CARD, FONT, FONT_H1, MUTED, TEXT, MovieApp


class DiscoveryModesWindow(tk.Toplevel):
    """Collects the requested local-data discovery modes in a single window."""

    def __init__(self, app: MovieApp) -> None:
        super().__init__(app)
        self.app = app
        self.tabs: dict[str, tk.Frame] = {}
        self.blind_card: dict[str, Any] | None = None
        self.blind_attempted = False
        self.filmography_rows: list[dict[str, Any]] = []
        self.franchise_rows: list[dict[str, Any]] = []
        self.twin_rows: list[dict[str, Any]] = []
        self.indifferent_rows: list[dict[str, Any]] = []
        self.filmography_attempted = False
        self.twin_attempted = False
        self.indifferent_attempted = False
        self.title("Новые режимы")
        self.geometry("850x650")
        self.minsize(700, 540)
        self.configure(bg=BG)
        self.transient(app)

        self.heading = tk.Label(self, bg=BG, fg=TEXT, font=FONT_H1, anchor="w")
        self.heading.pack(fill="x", padx=18, pady=(16, 10))
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=14, pady=(0, 16))
        self._build_blind_tab()
        self._build_challenge_tab()
        self._build_filmography_tab()
        self._build_franchise_tab()
        self._build_twin_tab()
        self._build_report_tab()
        self._build_indifferent_tab()
        self.refresh_language()
        app._register_window(self)
        self._refresh_challenges()

    def _text(self, russian: str, english: str) -> str:
        return self.app._text(russian, english)

    def _tab(self, key: str) -> tk.Frame:
        frame = tk.Frame(self.notebook, bg=BG)
        self.tabs[key] = frame
        self.notebook.add(frame, text="")
        return frame

    def _label(self, parent: tk.Misc, *, wrap: int = 720) -> tk.Label:
        return tk.Label(
            parent, bg=BG, fg=TEXT, font=(FONT, 10), anchor="w",
            justify="left", wraplength=wrap,
        )

    def _button(
        self, parent: tk.Misc, *, accent: bool = False, command: Callable[[], None]
    ) -> ttk.Button:
        return ttk.Button(
            parent, style="Accent.TButton" if accent else "Ghost.TButton",
            command=command,
        )

    def _tree(
        self, parent: tk.Misc, columns: tuple[str, ...], widths: tuple[int, ...]
    ) -> ttk.Treeview:
        tree = ttk.Treeview(parent, columns=columns, show="headings", selectmode="browse")
        for column, width in zip(columns, widths):
            tree.column(column, width=width, anchor="w")
        tree.pack(fill="both", expand=True, padx=12, pady=8)
        return tree

    def _run(
        self, operation: Callable[[], Any], callback: Callable[[Any], None]
    ) -> None:
        def worker() -> None:
            try:
                result = operation()
            except Exception as exc:
                self.app._post(lambda error=exc: self._show_error(error))
                return
            self.app._post(lambda value=result: self._deliver(callback, value))

        threading.Thread(
            target=worker, daemon=True, name="discovery-mode"
        ).start()

    def _deliver(self, callback: Callable[[Any], None], value: Any) -> None:
        if self.winfo_exists():
            callback(value)

    def _show_error(self, error: Exception) -> None:
        if self.winfo_exists():
            messagebox.showerror(
                self._text("Ошибка режима", "Discovery mode error"),
                str(error),
                parent=self,
            )

    def _build_blind_tab(self) -> None:
        self.blind_tab = self._tab("blind")
        self.blind_intro = self._label(self.blind_tab)
        self.blind_intro.pack(fill="x", padx=14, pady=(14, 8))
        self.blind_meta = self._label(self.blind_tab)
        self.blind_meta.configure(fg=MUTED)
        self.blind_meta.pack(fill="x", padx=14, pady=(4, 8))
        self.blind_overview = self._label(self.blind_tab, wrap=760)
        self.blind_overview.pack(fill="both", expand=True, padx=14, pady=8)
        actions = tk.Frame(self.blind_tab, bg=BG)
        actions.pack(fill="x", padx=14, pady=12)
        self.blind_pick_button = self._button(
            actions, accent=True, command=self._pick_blind
        )
        self.blind_pick_button.pack(side="left")
        self.blind_reveal_button = self._button(
            actions, command=self._reveal_blind, 
        )
        self.blind_reveal_button.pack(side="left", padx=8)
        self.blind_reveal_button.configure(state="disabled")

    def _build_challenge_tab(self) -> None:
        self.challenge_tab = self._tab("challenges")
        self.challenge_intro = self._label(self.challenge_tab)
        self.challenge_intro.pack(fill="x", padx=14, pady=(14, 8))
        self.challenge_empty = self._label(self.challenge_tab)
        self.challenge_empty.pack(fill="x", padx=14, pady=(0, 10))
        self.challenge_rows: dict[str, tk.Label] = {}
        self.challenge_names = {
            "decades": ("Пять десятилетий", "Five decades"),
            "countries": ("Пять стран", "Five countries"),
            "genres": ("Пять жанров", "Five genres"),
            "watched": ("25 просмотренных фильмов", "25 watched movies"),
        }
        for challenge_id in self.challenge_names:
            row = self._label(self.challenge_tab)
            row.pack(fill="x", padx=18, pady=9)
            self.challenge_rows[challenge_id] = row
        self.challenge_refresh_button = self._button(
            self.challenge_tab, command=self._refresh_challenges
        )
        self.challenge_refresh_button.pack(anchor="w", padx=14, pady=10)

    def _build_filmography_tab(self) -> None:
        self.filmography_tab = self._tab("filmography")
        row = tk.Frame(self.filmography_tab, bg=BG)
        row.pack(fill="x", padx=12, pady=(12, 4))
        self.person_var = tk.StringVar()
        self.person_entry = ttk.Entry(row, textvariable=self.person_var)
        self.person_entry.pack(side="left", fill="x", expand=True)
        self.person_search_button = self._button(
            row, command=self._search_people
        )
        self.person_search_button.pack(side="left", padx=(8, 0))
        self.person_list = tk.Listbox(
            self.filmography_tab, height=4, bg=CARD, fg=TEXT,
            selectbackground="#4c8dff", relief="flat",
        )
        self.person_list.pack(fill="x", padx=12, pady=4)
        self.person_list.bind("<<ListboxSelect>>", lambda _event: self._load_filmography())
        self.filmography_status = self._label(self.filmography_tab)
        self.filmography_status.pack(fill="x", padx=12, pady=4)
        self.filmography_tree = self._tree(
            self.filmography_tab, ("title", "year", "status"), (430, 80, 260)
        )
        self.filmography_open_button = self._button(
            self.filmography_tab, command=self._open_filmography_movie
        )
        self.filmography_open_button.pack(anchor="w", padx=12, pady=(0, 10))

    def _build_franchise_tab(self) -> None:
        self.franchise_tab = self._tab("franchise")
        row = tk.Frame(self.franchise_tab, bg=BG)
        row.pack(fill="x", padx=12, pady=(12, 4))
        self.franchise_query = tk.StringVar()
        self.franchise_entry = ttk.Entry(row, textvariable=self.franchise_query)
        self.franchise_entry.pack(side="left", fill="x", expand=True)
        self.franchise_search_button = self._button(
            row, command=self._search_franchise_seeds
        )
        self.franchise_search_button.pack(side="left", padx=(8, 0))
        self.franchise_intro = self._label(self.franchise_tab)
        self.franchise_intro.pack(fill="x", padx=12, pady=5)
        self.franchise_list = tk.Listbox(
            self.franchise_tab, bg=CARD, fg=TEXT,
            selectbackground="#4c8dff", relief="flat",
        )
        self.franchise_list.pack(fill="both", expand=True, padx=12, pady=6)
        self.franchise_open_button = self._button(
            self.franchise_tab, command=self._open_franchise
        )
        self.franchise_open_button.pack(anchor="w", padx=12, pady=(0, 10))

    def _build_twin_tab(self) -> None:
        self.twin_tab = self._tab("twin")
        row = tk.Frame(self.twin_tab, bg=BG)
        row.pack(fill="x", padx=12, pady=(12, 4))
        self.twin_query = tk.StringVar()
        self.twin_entry = ttk.Entry(row, textvariable=self.twin_query)
        self.twin_entry.pack(side="left", fill="x", expand=True)
        self.twin_search_button = self._button(row, command=self._search_twin_seed)
        self.twin_search_button.pack(side="left", padx=(8, 0))
        self.twin_list = tk.Listbox(
            self.twin_tab, height=4, bg=CARD, fg=TEXT,
            selectbackground="#4c8dff", relief="flat",
        )
        self.twin_list.pack(fill="x", padx=12, pady=4)
        self.twin_find_button = self._button(
            self.twin_tab, accent=True, command=self._find_twins
        )
        self.twin_find_button.pack(anchor="w", padx=12, pady=4)
        self.twin_status = self._label(self.twin_tab)
        self.twin_status.pack(fill="x", padx=12, pady=4)
        self.twin_tree = self._tree(
            self.twin_tab, ("title", "year", "evidence"), (300, 70, 400)
        )
        self.twin_open_button = self._button(self.twin_tab, command=self._open_twin)
        self.twin_open_button.pack(anchor="w", padx=12, pady=(0, 10))

    def _build_report_tab(self) -> None:
        self.report_tab = self._tab("report")
        row = tk.Frame(self.report_tab, bg=BG)
        row.pack(fill="x", padx=12, pady=(14, 8))
        self.report_year = tk.StringVar(value=str(datetime.now().year))
        self.report_entry = ttk.Entry(row, textvariable=self.report_year, width=10)
        self.report_entry.pack(side="left")
        self.report_button = self._button(
            row, accent=True, command=self._load_yearly_report
        )
        self.report_button.pack(side="left", padx=8)
        self.report_text = self._label(self.report_tab, wrap=760)
        self.report_text.pack(fill="both", expand=True, padx=14, pady=8)

    def _build_indifferent_tab(self) -> None:
        self.indifferent_tab = self._tab("indifferent")
        row = tk.Frame(self.indifferent_tab, bg=BG)
        row.pack(fill="x", padx=12, pady=(12, 4))
        self.runtime_var = tk.StringVar(value="0")
        self.runtime_entry = ttk.Spinbox(
            row, from_=0, to=1000, increment=5, textvariable=self.runtime_var, width=10
        )
        self.runtime_entry.pack(side="left")
        self.indifferent_pick_button = self._button(
            row, accent=True, command=self._pick_indifferent
        )
        self.indifferent_pick_button.pack(side="left", padx=8)
        self.indifferent_intro = self._label(self.indifferent_tab)
        self.indifferent_intro.pack(fill="x", padx=12, pady=4)
        self.indifferent_status = self._label(self.indifferent_tab)
        self.indifferent_status.pack(fill="x", padx=12, pady=4)
        self.indifferent_tree = self._tree(
            self.indifferent_tab, ("title", "year", "runtime", "why"),
            (260, 65, 85, 360),
        )
        self.indifferent_open_button = self._button(
            self.indifferent_tab, command=self._open_indifferent
        )
        self.indifferent_open_button.pack(anchor="w", padx=12, pady=(0, 10))

    def refresh_language(self) -> None:
        self.title(self._text("Новые режимы и подборки", "New discovery modes"))
        self.heading.configure(text=self._text(
            "Открывайте каталог по-новому", "Explore the catalogue in new ways"
        ))
        for key, russian, english in (
            ("blind", "Слепой выбор", "Blind choice"),
            ("challenges", "Челленджи", "Challenges"),
            ("filmography", "Фильмография", "Filmography"),
            ("franchise", "Франшиза", "Franchise route"),
            ("twin", "Двойник фильма", "Movie twin"),
            ("report", "Отчёт за год", "Yearly report"),
            ("indifferent", "Мне всё равно", "Surprise me"),
        ):
            self.notebook.tab(self.tabs[key], text=self._text(russian, english))
        self.blind_intro.configure(text=self._text(
            "До выбора видны только подтверждённый жанр, год и описание. "
            "Название и постер остаются скрытыми.",
            "Before revealing, only the confirmed genre, year and overview are shown. "
            "The title and poster stay hidden.",
        ))
        self.blind_pick_button.configure(text=self._text("Выбрать фильм", "Pick a movie"))
        self.blind_reveal_button.configure(text=self._text(
            "Выбран: открыть детали", "Reveal choice and open details"
        ))
        self.challenge_intro.configure(text=self._text(
            "Прогресс рассчитан по уникальным просмотренным фильмам из локального каталога.",
            "Progress is based on unique watched movies in your local catalogue.",
        ))
        self.challenge_refresh_button.configure(text=self._text("Обновить прогресс", "Refresh progress"))
        self.person_search_button.configure(text=self._text("Найти", "Search"))
        self.filmography_open_button.configure(text=self._text("Открыть фильм", "Open movie"))
        self.franchise_search_button.configure(text=self._text("Найти фильм", "Find movie"))
        self.franchise_intro.configure(text=self._text(
            "Выберите фильм, чтобы открыть подтверждённую TMDb-франшизу и следующий доступный фильм.",
            "Choose a movie to open its verified TMDb collection and next available film.",
        ))
        self.franchise_open_button.configure(text=self._text(
            "Показать порядок франшизы", "Show verified franchise order"
        ))
        self.twin_search_button.configure(text=self._text("Найти фильм", "Find movie"))
        self.twin_find_button.configure(text=self._text("Найти двойника", "Find a twin"))
        self.twin_open_button.configure(text=self._text("Открыть фильм", "Open movie"))
        self.report_button.configure(text=self._text("Показать отчёт", "Show report"))
        self.indifferent_pick_button.configure(text=self._text(
            "Предложить варианты", "Suggest options"
        ))
        self.indifferent_intro.configure(text=self._text(
            "Задайте предел длительности; просмотренное, оценённое и исключённое не попадёт в варианты.",
            "Set a runtime limit; watched, rated and excluded movies are omitted.",
        ))
        for tree, headings in (
            (self.filmography_tree, (
                ("Фильм", "Movie"), ("Год", "Year"), ("Статус", "Status"),
            )),
            (self.twin_tree, (
                ("Фильм", "Movie"), ("Год", "Year"),
                ("Совпадение и различия", "Matches and differences"),
            )),
            (self.indifferent_tree, (
                ("Фильм", "Movie"), ("Год", "Year"), ("Мин.", "Min."),
                ("Почему в подборке", "Why it is suggested"),
            )),
        ):
            for column, (russian, english) in zip(tree["columns"], headings):
                tree.heading(column, text=self._text(russian, english))
        self._render_challenges()
        self._render_blind()
        self._render_report()
        self._render_results()

    def _pick_blind(self) -> None:
        language = "en-US" if self.app.is_english else "ru-RU"
        exclude_id = self.blind_card.get("movie_id") if self.blind_card else None
        self.blind_attempted = True
        self.blind_pick_button.configure(state="disabled")
        self._run(
            lambda: blind_choice(self.app.db, language, exclude_id=exclude_id),
            self._blind_picked,
        )

    def _blind_picked(self, card: dict[str, Any] | None) -> None:
        self.blind_pick_button.configure(state="normal")
        self.blind_card = card
        self._render_blind()

    def _render_blind(self) -> None:
        if self.blind_card is None:
            self.blind_meta.configure(text="")
            self.blind_overview.configure(text=self._text(
                "Не найден фильм с локализованным описанием и подтверждённым жанром."
                if self.blind_attempted else "Нажмите «Выбрать фильм».",
                "No movie found with a localized overview and confirmed genre."
                if self.blind_attempted else "Press “Pick a movie”.",
            ))
            self.blind_reveal_button.configure(state="disabled")
            return
        self.blind_meta.configure(text=self._text(
            f"Жанр: {self.blind_card['genre']} · Год: {self.blind_card['year']}",
            f"Genre: {self.blind_card['genre']} · Year: {self.blind_card['year']}",
        ))
        self.blind_overview.configure(text=self.blind_card["overview"])
        self.blind_reveal_button.configure(state="normal")

    def _reveal_blind(self) -> None:
        if self.blind_card is None:
            return
        card = self.blind_card
        self._run(lambda: reveal_blind_choice(self.app.db, card), self._open_movie)

    def _refresh_challenges(self) -> None:
        self._run(lambda: challenge_progress(self.app.db), self._challenges_loaded)

    def _challenges_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.challenge_data = rows
        self._render_challenges()

    def _render_challenges(self) -> None:
        if not hasattr(self, "challenge_rows"):
            return
        rows = getattr(self, "challenge_data", [])
        watched_count = next(
            (row["progress"] for row in rows if row["id"] == "watched"), 0
        )
        self.challenge_empty.configure(text=self._text(
            "Пока нет просмотренных фильмов — отметьте просмотренное в деталях.",
            "No watched movies yet — mark a movie watched in its details.",
        ) if not watched_count else "")
        for row in rows:
            russian, english = self.challenge_names[row["id"]]
            self.challenge_rows[row["id"]].configure(text=self._text(
                f"{russian}: {row['progress']} / {row['target']}",
                f"{english}: {row['progress']} / {row['target']}",
            ))

    def _search_people(self) -> None:
        query = self.person_var.get().strip()
        self._run(lambda: self.app.db.filmography_search(query), self._people_loaded)

    def _people_loaded(self, names: list[str]) -> None:
        self.person_list.delete(0, "end")
        for name in names:
            self.person_list.insert("end", name)
        if not names:
            self.filmography_attempted = True
            self.filmography_rows = []
            self._render_results()
        else:
            self.filmography_status.configure(text=self._text(
                "Выберите имя, чтобы открыть фильмографию из локального каталога.",
                "Select a name to show its local catalogue filmography.",
            ))

    def _load_filmography(self) -> None:
        selection = self.person_list.curselection()
        if not selection:
            return
        person = self.person_list.get(selection[0])
        self._run(lambda: filmography(self.app.db, person), self._filmography_loaded)

    def _filmography_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.filmography_attempted = True
        self.filmography_rows = rows
        self._render_results()

    def _search_local_titles(
        self, query: str, callback: Callable[[list[dict[str, Any]]], None]
    ) -> None:
        query = query.strip()
        self._run(
            lambda: self.app.db.search(title=query, limit=30)[0] if query else [],
            callback,
        )

    def _search_franchise_seeds(self) -> None:
        self._search_local_titles(self.franchise_query.get(), self._franchise_seeds_loaded)

    def _franchise_seeds_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.franchise_rows = rows
        self.franchise_list.delete(0, "end")
        for row in rows:
            self.franchise_list.insert(
                "end", f"{row.get('title')} · {row.get('year') or '—'}"
            )

    def _open_franchise(self) -> None:
        selection = self.franchise_list.curselection()
        if selection and selection[0] < len(self.franchise_rows):
            self.app.open_franchise(self.franchise_rows[selection[0]])

    def _search_twin_seed(self) -> None:
        self._search_local_titles(self.twin_query.get(), self._twin_seeds_loaded)

    def _twin_seeds_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.twin_seed_rows = rows
        self.twin_list.delete(0, "end")
        for row in rows:
            self.twin_list.insert(
                "end", f"{row.get('title')} · {row.get('year') or '—'}"
            )

    def _find_twins(self) -> None:
        selection = self.twin_list.curselection()
        if not selection or selection[0] >= len(getattr(self, "twin_seed_rows", [])):
            return
        movie_id = int(self.twin_seed_rows[selection[0]]["id"])
        self._run(lambda: movie_twin(self.app.db, movie_id), self._twins_loaded)

    def _twins_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.twin_attempted = True
        self.twin_rows = rows
        self._render_results()

    def _load_yearly_report(self) -> None:
        try:
            year = int(self.report_year.get())
        except ValueError:
            self._show_error(ValueError(self._text(
                "Введите календарный год.", "Enter a calendar year."
            )))
            return
        self._run(lambda: yearly_summary(self.app.db, year), self._report_loaded)

    def _report_loaded(self, report: dict[str, Any]) -> None:
        self.report_data = report
        self._render_report()

    def _render_report(self) -> None:
        if not hasattr(self, "report_text"):
            return
        report = getattr(self, "report_data", None)
        if report is None:
            self.report_text.configure(text=self._text(
                "Выберите год и нажмите «Показать отчёт».",
                "Choose a year and press “Show report”.",
            ))
            return
        if not report["history_count"]:
            self.report_text.configure(text=self._text(
                f"В истории просмотров за {report['year']} год пока пусто.",
                f"No view history for {report['year']} yet.",
            ))
            return
        countries = COUNTRIES_EN if self.app.is_english else COUNTRIES
        country_text = ", ".join(
            f"{countries.get(code, code)} ({count})"
            for code, count in sorted(report["countries"].items())
        ) or "—"
        decades_text = ", ".join(
            f"{decade}s ({count})" for decade, count in sorted(report["decades"].items())
        ) or "—"
        avg = report["average_rating"]
        rating_text = (
            self._text(f"{avg:.2f}", f"{avg:.2f}") if avg is not None
            else self._text("нет оценок", "no ratings")
        )
        self.report_text.configure(text=self._text(
            f"Фильмов в истории: {report['history_count']} · "
            f"отмечено просмотренными: {report['watched_count']}\n"
            f"Страны: {country_text}\nДесятилетия: {decades_text}\n"
            f"Оценено: {report['rated_count']} · средняя личная оценка: {rating_text}",
            f"Movies in history: {report['history_count']} · "
            f"marked watched: {report['watched_count']}\n"
            f"Countries: {country_text}\nDecades: {decades_text}\n"
            f"Rated: {report['rated_count']} · average personal rating: {rating_text}",
        ))

    def _pick_indifferent(self) -> None:
        try:
            value = int(self.runtime_var.get() or "0")
        except ValueError:
            self._show_error(ValueError(self._text(
                "Длительность должна быть целым числом минут.",
                "Runtime must be a whole number of minutes.",
            )))
            return
        if value < 0:
            self._show_error(ValueError(self._text(
                "Длительность не может быть отрицательной.",
                "Runtime cannot be negative.",
            )))
            return
        language = "en-US" if self.app.is_english else "ru-RU"
        self._run(
            lambda: indifferent_movies(
                self.app.db, max_runtime=value or None, language=language
            ),
            self._indifferent_loaded,
        )

    def _indifferent_loaded(self, rows: list[dict[str, Any]]) -> None:
        self.indifferent_attempted = True
        self.indifferent_rows = rows
        self._render_results()

    def _open_movie(self, movie: dict[str, Any] | None) -> None:
        if movie:
            self.app.open_details(movie)

    def _open_filmography_movie(self) -> None:
        self._open_tree_movie(self.filmography_tree, self.filmography_rows)

    def _open_twin(self) -> None:
        self._open_tree_movie(self.twin_tree, self.twin_rows)

    def _open_indifferent(self) -> None:
        self._open_tree_movie(self.indifferent_tree, self.indifferent_rows)

    def _open_tree_movie(
        self, tree: ttk.Treeview, rows: list[dict[str, Any]]
    ) -> None:
        selection = tree.selection()
        if not selection:
            return
        movie_id = int(selection[0])
        movie = next((row for row in rows if int(row["id"]) == movie_id), None)
        self._open_movie(movie)

    def _render_results(self) -> None:
        if not hasattr(self, "filmography_tree"):
            return
        self.filmography_tree.delete(*self.filmography_tree.get_children())
        if self.filmography_attempted and not self.filmography_rows:
            self.filmography_status.configure(text=self._text(
                "В локальном каталоге нет фильмов с этой персоной.",
                "No films for this person are available in the local catalogue.",
            ))
        elif self.filmography_rows:
            self.filmography_status.configure(text="")
        for row in self.filmography_rows:
            labels = {
                "watched": self._text("Просмотрено", "Watched"),
                "watchlist": self._text("В списке", "Watchlist"),
                "planned": self._text("Запланировано", "Planned"),
                "not_started": self._text("Не начато", "Not started"),
            }
            status = ", ".join(labels[item] for item in row["statuses"])
            self.filmography_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(row.get("title"), row.get("year") or "—", status),
            )
        self.twin_tree.delete(*self.twin_tree.get_children())
        if self.twin_attempted and not self.twin_rows:
            self.twin_status.configure(text=self._text(
                "Не найден просмотренный фильм или локально подтверждённый двойник "
                "с подходящим отличием.",
                "No matching film or locally verified twin with a meaningful difference was found.",
            ))
        elif self.twin_rows:
            self.twin_status.configure(text=self._text(
                "Показаны совпадения и подтверждённые различия по локальным данным.",
                "Matches and verified differences are based on local data.",
            ))
        diff_names = {
            "actor": self._text("другой актёр", "different cast"),
            "country": self._text("другая страна", "different country"),
            "decade": self._text("другое десятилетие", "different decade"),
            "popularity": self._text("меньше голосов", "fewer votes"),
        }
        for row in self.twin_rows:
            match_names = {
                "actor": self._text("общий актёр", "shared cast"),
                "director": self._text("общий режиссёр", "shared director"),
                "keyword": self._text("общее ключевое слово", "shared keyword"),
                "genre": self._text("общий жанр", "shared genre"),
            }
            matches = ", ".join(
                f"{match_names.get(item['type'], item['type'])}: {item['value']}"
                for item in row["twin_matches"]
            )
            differences = ", ".join(
                f"{diff_names[item['type']]} "
                f"({item['source']} → {item['candidate']})"
                for item in row["twin_differences"]
            )
            self.twin_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row.get("title"), row.get("year") or "—",
                    f"{matches}; {differences}",
                ),
            )
        self.indifferent_tree.delete(*self.indifferent_tree.get_children())
        reason_names = {
            "highest_ranked": self._text("высокая позиция в каталоге", "highest catalogue rank"),
            "decade": self._text("новое десятилетие", "new decade"),
            "country": self._text("новая страна", "new country"),
            "genre": self._text("новый жанр", "new genre"),
            "quality": self._text("качество каталога", "catalogue ranking"),
        }
        countries = COUNTRIES_EN if self.app.is_english else COUNTRIES
        if self.indifferent_attempted and not self.indifferent_rows:
            self.indifferent_status.configure(text=self._text(
                "Подходящих вариантов нет: проверьте предел длительности и исключения.",
                "No eligible options. Check the runtime limit and content exclusions.",
            ))
        elif self.indifferent_rows:
            self.indifferent_status.configure(text="")
        for row in self.indifferent_rows:
            if row["diversity_reasons"] == ["highest_ranked"]:
                why = reason_names["highest_ranked"]
            else:
                evidence = row["diversity_evidence"]
                details = []
                if evidence["decade"] is not None:
                    details.append(f"{evidence['decade']}s")
                if evidence["countries"]:
                    details.extend(
                        countries.get(code, code) for code in evidence["countries"]
                    )
                if evidence["genres"]:
                    details.extend(
                        (
                            genre.title() if self.app.is_english else genre.capitalize()
                        )
                        for genre in evidence["genres"]
                    )
                why = ", ".join(details) or reason_names["quality"]
            values = (
                row.get("title"), row.get("year") or "—",
                row.get("runtime") or "—", why,
            )
            self.indifferent_tree.insert("", "end", iid=str(row["id"]), values=values)
