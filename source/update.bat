@echo off
chcp 65001 >nul
setlocal enableextensions
cd /d "%~dp0"
title Обновление Movie Finder

set "NEW=dist_new\Movie Finder"
set "OLD=dist\Movie Finder"

if not exist "%NEW%\Movie Finder.exe" goto no_new
if not exist "%NEW%\_internal" goto no_new

rem Программа не должна быть запущена: exe и база заняты.
tasklist /fi "imagename eq Movie Finder.exe" 2>nul | find /i "Movie Finder.exe" >nul
if not errorlevel 1 goto running

rem ---------------------------------------------------------------------------
rem  Порядок безопасный: сначала готовим копию _internal рядом, и только потом
rem  подменяем папки. При любом сбое прежняя установка восстанавливается.
rem ---------------------------------------------------------------------------
echo Обновляю программу, сохраняю базу и ключ TMDb...

if exist "%OLD%\_internal.new" rmdir /s /q "%OLD%\_internal.new"
xcopy /e /i /y /q "%NEW%\_internal" "%OLD%\_internal.new" >nul
if errorlevel 1 goto failed_new

if exist "%OLD%\_internal.old" rmdir /s /q "%OLD%\_internal.old"
move "%OLD%\_internal" "%OLD%\_internal.old" >nul 2>nul
if errorlevel 1 goto failed_new

move "%OLD%\_internal.new" "%OLD%\_internal" >nul 2>nul
if errorlevel 1 goto failed_restore

copy /y "%OLD%\Movie Finder.exe" "%OLD%\Movie Finder.exe.old" >nul
if errorlevel 1 goto failed_restore
copy /y "%NEW%\Movie Finder.exe" "%OLD%\Movie Finder.exe" >nul
if errorlevel 1 goto failed_restore
if exist "%NEW%\README.md" copy /y "%NEW%\README.md" "%OLD%\README.md" >nul

echo Проверяю и чиню базу (пара секунд)...
start /wait "" "%OLD%\Movie Finder.exe" --repair
if errorlevel 1 goto failed_restore

if exist "%OLD%\Movie Finder.exe.old" del /q "%OLD%\Movie Finder.exe.old"
if exist "%OLD%\_internal.old" rmdir /s /q "%OLD%\_internal.old"
rmdir /s /q "dist_new" 2>nul

echo.
echo Готово. Запускаю Movie Finder...
start "" "%OLD%\Movie Finder.exe"
exit /b 0

:failed_restore
echo.
echo   Проверка новой сборки не прошла — возвращаю прежнюю версию.
if exist "%OLD%\_internal" rmdir /s /q "%OLD%\_internal"
if exist "%OLD%\_internal.old" move "%OLD%\_internal.old" "%OLD%\_internal" >nul 2>nul
if exist "%OLD%\Movie Finder.exe.old" move "%OLD%\Movie Finder.exe.old" "%OLD%\Movie Finder.exe" >nul 2>nul
if exist "%OLD%\_internal.new" rmdir /s /q "%OLD%\_internal.new"
echo   Прежняя версия восстановлена, база не тронута.
pause
exit /b 1

:failed_new
echo.
echo   Не удалось подготовить новую папку _internal.
echo   Установка не тронута, можно запускать прежнюю версию.
if exist "%OLD%\_internal.new" rmdir /s /q "%OLD%\_internal.new"
pause
exit /b 1

:running
echo.
echo   Movie Finder ещё запущен — файлы заняты.
echo   Закройте программу и запустите update.bat снова.
echo.
pause
exit /b 1

:no_new
echo.
echo   Папка dist_new не найдена — обновление не подготовлено.
echo.
pause
exit /b 1
