"""Сборка автономного exe (PyInstaller) — запуск без установки Python.

Запуск:  python tools/build_exe.py
Результат: автономная папка с exe и runtime-файлами; личная data/ не копируется.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
APP_NAME = "Movie Finder"
# Куда собирать: по умолчанию dist, можно указать другой каталог аргументом
# (пригодится, если текущая сборка запущена и папку нельзя перезаписать).
DIST_ROOT = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else ROOT / "dist"
DIST_DIR = DIST_ROOT / APP_NAME
WORK_DIR = ROOT / "build"
ICON = ROOT / "data" / "app.ico"


def run(command: list[str]) -> None:
    print(">", " ".join(command))
    subprocess.run(command, check=True, cwd=ROOT)


def compile_check() -> None:
    """Ловит синтаксические ошибки до сборки: иначе модуль молча выпадает из exe."""
    import py_compile

    files = sorted((ROOT / "movie_search").glob("*.py")) + [ROOT / "main.py"]
    for path in files:
        try:
            py_compile.compile(str(path), doraise=True)
        except py_compile.PyCompileError as exc:
            raise SystemExit(f"Синтаксическая ошибка в {path.name}:\n{exc}") from exc
    print(f"Синтаксис проверен: {len(files)} файлов")


def ensure_safe_output(dist_dir: Path) -> None:
    """Refuses to overwrite a package directory that already contains user data."""
    if not dist_dir.exists():
        return
    # Проверяем не только базу и постеры: в папке сборки могут оказаться
    # config.json, логи, бэкапы и личный экспорт.
    protected = (dist_dir / "config.json", dist_dir / "data", dist_dir / "backups")
    existing = [
        path
        for path in protected
        if path.exists() and (not path.is_dir() or any(path.iterdir()))
    ]
    if existing:
        paths = "\n".join(f"  {path}" for path in existing)
        raise SystemExit(
            "Сборка остановлена: в выходной папке есть пользовательские данные "
            "или файлы приложения. Выберите новую пустую папку, не удаляя эти файлы:\n"
            + paths
        )


def copy_runtime_assets(dist_dir: Path, readme: Path | None = None) -> None:
    """Copies documentation only; never bundles a database, posters, or config."""
    shutil.copy2(readme or ROOT / "README.md", dist_dir / "README.md")


def main() -> int:
    compile_check()
    ensure_safe_output(DIST_DIR)
    if not ICON.exists():
        run([sys.executable, str(ROOT / "tools" / "make_icon.py")])

    run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--windowed",
            "--name",
            APP_NAME,
            "--icon",
            str(ICON),
            "--distpath",
            str(DIST_ROOT),
            "--workpath",
            str(WORK_DIR),
            "--specpath",
            str(WORK_DIR),
            # Диагностические модули импортируются «лениво» — подстраховываемся.
            "--hidden-import",
            "movie_search.diagnostics",
            "--hidden-import",
            "movie_search.ui",
            # Лишние тяжёлые модули в сборке не нужны: приложение использует
            # только tkinter, Pillow, requests и sqlite3.
            "--exclude-module",
            "numpy",
            "--exclude-module",
            "setuptools",
            "--exclude-module",
            "pkg_resources",
            "--exclude-module",
            "jinja2",
            "--exclude-module",
            "distutils",
            "--exclude-module",
            "unittest",
            "--exclude-module",
            "doctest",
            "--exclude-module",
            "pydoc",
            "--exclude-module",
            "multiprocessing",
            "--exclude-module",
            "pycparser",
            "--exclude-module",
            "cffi",
            str(ROOT / "main.py"),
        ]
    )

    # The target folder starts without user data; the app creates a fresh data/
    # directory and database on first launch. Existing folders are never cleaned.
    copy_runtime_assets(DIST_DIR)

    exe = DIST_DIR / f"{APP_NAME}.exe"
    size_mb = exe.stat().st_size / (1024 * 1024) if exe.exists() else 0
    print(f"\nГотово: {exe}")
    print(f"Размер exe: {size_mb:.1f} МБ (без личной базы, постеров и config.json)")
    print("Каталог data/ и пустая база создаются приложением при первом запуске.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
