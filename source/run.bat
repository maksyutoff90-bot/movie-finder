@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"
title Movie Finder

rem ---------------------------------------------------------------------------
rem  1. Если рядом есть готовая сборка — запускаем её (Python не нужен).
rem ---------------------------------------------------------------------------
if exist "dist\Movie Finder\Movie Finder.exe" (
    start "" "dist\Movie Finder\Movie Finder.exe"
    exit /b 0
)

rem ---------------------------------------------------------------------------
rem  2. Ищем рабочий Python 3 (сначала python из PATH, затем лаунчер py).
rem ---------------------------------------------------------------------------
set "PY="
where python >nul 2>nul
if not errorlevel 1 (
    python -c "import sys" >nul 2>nul
    if not errorlevel 1 set "PY=python"
)
if not defined PY (
    where py >nul 2>nul
    if not errorlevel 1 (
        py -3 -c "import sys" >nul 2>nul
        if not errorlevel 1 set "PY=py -3"
    )
)
if not defined PY (
    echo.
    echo   Python не найден.
    echo.
    echo   Варианты:
    echo    - установить Python 3.9+ с python.org ^(галочка "Add python.exe to PATH"^);
    echo    - либо запустить готовую сборку: dist\Movie Finder\Movie Finder.exe
    echo.
    pause
    exit /b 1
)

rem ---------------------------------------------------------------------------
rem  3. Проверяем зависимости и при необходимости доставляем их.
rem ---------------------------------------------------------------------------
%PY% -c "import PIL, requests" >nul 2>nul
if errorlevel 1 (
    echo   Первый запуск: устанавливаю зависимости...
    %PY% -m pip install --disable-pip-version-check --quiet -r requirements.txt
    if errorlevel 1 (
        echo.
        echo   Не удалось установить зависимости.
        echo   Попробуйте вручную:  %PY% -m pip install -r requirements.txt
        echo.
        pause
        exit /b 1
    )
)

rem ---------------------------------------------------------------------------
rem  4. Запуск без лишней консоли.
rem ---------------------------------------------------------------------------
if /i "%PY%"=="python" (
    where pythonw >nul 2>nul
    if not errorlevel 1 (
        start "" pythonw "main.py"
        exit /b 0
    )
    python "main.py"
    if errorlevel 1 pause
    exit /b 0
)

start "" pyw -3 "main.py"
if errorlevel 1 (
    py -3 "main.py"
    if errorlevel 1 pause
)
exit /b 0
