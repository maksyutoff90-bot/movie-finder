"""Запуск локального файла фильма во внешнем плеере (KMPlayer, VLC, PotPlayer…)."""

from __future__ import annotations

import os
import subprocess
import winreg
from pathlib import Path

# Имя для интерфейса -> возможные исполняемые файлы.
PLAYER_CANDIDATES: dict[str, list[str]] = {
    "KMPlayer": ["KMPlayer.exe", "KMPlayer64.exe", "KMP.exe"],
    "VLC": ["vlc.exe"],
    "PotPlayer": ["PotPlayerMini64.exe", "PotPlayerMini.exe"],
    "MPC-HC": ["mpc-hc64.exe", "mpc-hc.exe"],
    "mpv": ["mpv.exe"],
    "Windows": [],  # открыть системным приложением
}

SEARCH_DIRS = [
    r"C:\Program Files\KMPlayer",
    r"C:\Program Files (x86)\KMPlayer",
    r"C:\Program Files\DAUM\PotPlayer",
    r"C:\Program Files (x86)\DAUM\PotPlayer",
    r"C:\Program Files\VideoLAN\VLC",
    r"C:\Program Files (x86)\VideoLAN\VLC",
    r"C:\Program Files\MPC-HC",
    r"C:\Program Files (x86)\MPC-HC",
]


def _registry_path(exe: str) -> str | None:
    """Ищет зарегистрированный путь по имени exe в App Paths."""
    for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(
                root, rf"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\{exe}"
            )
            with key:
                value, _ = winreg.QueryValueEx(key, "")
            if value and Path(value).exists():
                return value
        except OSError:
            continue
    return None


def detect_players() -> dict[str, str]:
    """Возвращает найденные плееры: {название: путь к exe}."""
    found: dict[str, str] = {}
    for name, executables in PLAYER_CANDIDATES.items():
        if name == "Windows":
            found[name] = ""  # системное открытие доступно всегда
            continue
        for exe in executables:
            path = _registry_path(exe)
            if path:
                found[name] = path
                break
        if name in found:
            continue
        for folder in SEARCH_DIRS:
            for exe in executables:
                candidate = Path(folder) / exe
                if candidate.exists():
                    found[name] = str(candidate)
                    break
            if name in found:
                break
    return found


def default_player(found: dict[str, str] | None = None) -> tuple[str, str]:
    """Первый найденный плеер; иначе — системное открытие."""
    players = found if found is not None else detect_players()
    for preferred in ("KMPlayer", "PotPlayer", "VLC", "MPC-HC", "mpv"):
        if players.get(preferred):
            return preferred, players[preferred]
    return "Windows", ""


def open_file(file_path: str | Path, player_path: str = "") -> tuple[bool, str]:
    """Открывает файл в плеере. Возвращает (успех, сообщение)."""
    path = Path(file_path)
    if not path.exists():
        return False, f"Файл не найден: {path}"

    try:
        if player_path and Path(player_path).exists():
            subprocess.Popen([player_path, str(path)], close_fds=True)
            return True, f"Открываю в {Path(player_path).stem}"
        os.startfile(str(path))  # noqa: S606 - системное сопоставление
        return True, "Открываю системным плеером"
    except OSError as exc:
        return False, f"Не удалось открыть: {exc}"
