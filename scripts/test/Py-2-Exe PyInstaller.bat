@echo off
chcp 65001 >nul
setlocal ENABLEDELAYEDEXPANSION
title PY → EXE — Interaktywne menu

REM ===============================================
REM  PY-TO-EXE — INTERAKTYWNE MENU (DZIAŁAJĄCE)
REM ===============================================

REM --- Zmienne domyślne ---
set "PY_FILE="
set "TRYB=onefile"
set "TYP=konsola"
set "PROFIL=dev"
set "IKONA="
set "EXE_NAME="

REM --- Start: przejdź od razu do menu ---
goto menu

REM --- Prosta pauza ---
:pauza
echo.
echo Nacisnij klawisz, aby kontynuowac...
pause >nul
goto menu

REM --- MENU GŁÓWNE ---
:menu
cls
echo ==============================================
echo      PY → EXE — INTERAKTYWNE MENU
echo ==============================================
echo.
echo  Aktualna konfiguracja:
echo    Plik:     %PY_FILE%
echo    Tryb:     %TRYB%
echo    Typ:      %TYP%
echo    Profil:   %PROFIL%
if defined IKONA (
    echo    Ikona:    %IKONA%
) else (
    echo    Ikona:    (brak)
)
echo.
echo  1. Wybierz plik .py
echo  2. Wybierz tryb: onefile / onedir
echo  3. Wybierz typ: konsola / okienkowy
echo  4. Wybierz profil: dev / prod
echo  5. Wybierz ikonę .ico
echo  6. Buduj EXE
echo  0. Wyjdz
echo.
set "opt="
set /p "opt=Twoj wybor: "

if "%opt%"=="1" goto wybierz_py
if "%opt%"=="2" goto wybierz_tryb
if "%opt%"=="3" goto wybierz_typ
if "%opt%"=="4" goto wybierz_profil
if "%opt%"=="5" goto wybierz_ikone
if "%opt%"=="6" goto buduj
if "%opt%"=="0" goto koniec
goto menu

REM --- WYBÓR PLIKU .PY ---
:wybierz_py
cls
echo Dostepne pliki .py w katalogu:
echo.

set "PY_FILE="
set i=0
for %%f in (*.py) do (
    set /a i+=1
    echo   !i!. %%f
    set "PY[!i!]=%%f"
)

if %i%==0 (
    echo.
    echo [BŁĄD] Brak plikow .py w tym katalogu.
    goto pauza
)

echo.
set "sel="
set /p "sel=Numer pliku: "
set "PY_FILE=!PY[%sel%]!"

if "%PY_FILE%"=="" (
    echo.
    echo [BŁĄD] Nieprawidlowy wybor.
    goto pauza
)

REM Nazwa EXE = nazwa pliku .py bez rozszerzenia
for %%x in ("%PY_FILE%") do set "EXE_NAME=%%~n"

echo.
echo Wybrano plik: %PY_FILE%
echo Nazwa EXE:   main.exe
goto pauza

REM --- WYBÓR TRYBU ---
:wybierz_tryb
cls
echo Wybierz tryb budowania:
echo.
echo  1. onefile (jeden plik EXE)
echo  2. onedir  (katalog)
echo.
set "sel="
set /p "sel=Twoj wybor: "

if "%sel%"=="1" (
    set "TRYB=onefile"
) else if "%sel%"=="2" (
    set "TRYB=onedir"
) else (
    echo.
    echo [BŁĄD] Nieprawidlowy wybor.
    goto pauza
)

echo.
echo Wybrano tryb: %TRYB%
goto pauza

REM --- WYBÓR TYPU APLIKACJI ---
:wybierz_typ
cls
echo Wybierz typ aplikacji:
echo.
echo  1. Konsola
echo  2. Okienkowy (bez konsoli)
echo.
set "sel="
set /p "sel=Twoj wybor: "

if "%sel%"=="1" (
    set "TYP=konsola"
) else if "%sel%"=="2" (
    set "TYP=okienkowy"
) else (
    echo.
    echo [BŁĄD] Nieprawidlowy wybor.
    goto pauza
)

echo.
echo Wybrano typ: %TYP%
goto pauza

REM --- WYBÓR PROFILU ---
:wybierz_profil
cls
echo Wybierz profil:
echo.
echo  1. dev  (szybki build)
echo  2. prod (czyszczenie build/dist przed buildem)
echo.
set "sel="
set /p "sel=Twoj wybor: "

if "%sel%"=="1" (
    set "PROFIL=dev"
) else if "%sel%"=="2" (
    set "PROFIL=prod"
) else (
    echo.
    echo [BŁĄD] Nieprawidlowy wybor.
    goto pauza
)

echo.
echo Wybrano profil: %PROFIL%
goto pauza

REM --- WYBÓR IKONY ---
:wybierz_ikone
cls
echo Dostepne ikony .ico w katalogu:
echo.

set "IKONA="
set i=0
for %%f in (*.ico) do (
    set /a i+=1
    echo   !i!. %%f
    set "ICO[!i!]=%%f"
)

if %i%==0 (
    echo.
    echo [INFO] Brak plikow .ico. Kontynuujesz bez ikony.
    goto pauza
)

echo.
set "sel="
set /p "sel=Numer ikony (lub puste aby anulowac): "

if "%sel%"=="" (
    echo.
    echo Wyczyszczono ikonę. Budowanie bedzie bez ikony.
    set "IKONA="
    goto pauza
)

set "IKONA=!ICO[%sel%]!"

if "%IKONA%"=="" (
    echo.
    echo [BŁĄD] Nieprawidlowy wybor.
    goto pauza
)

echo.
echo Wybrano ikonę: %IKONA%
goto pauza

REM --- BUDOWANIE EXE ---
:buduj
cls

if "%PY_FILE%"=="" (
    echo [BŁĄD] Nie wybrano pliku .py.
    goto pauza
)

if "%EXE_NAME%"=="" (
    for %%x in ("%PY_FILE%") do set "EXE_NAME=%%~n"
)

echo ==============================================
echo          PODSUMOWANIE KONFIGURACJI
echo ==============================================
echo   Plik:     %PY_FILE%
echo   EXE:      %EXE_NAME%.exe
echo   Tryb:     %TRYB%
echo   Typ:      %TYP%
echo   Profil:   %PROFIL%
if defined IKONA (
    echo   Ikona:    %IKONA%
) else (
    echo   Ikona:    (brak)
)
echo ==============================================
echo.
set "c="
set /p "c=Czy kontynuowac? (T/N): "

if /I "%c%" NEQ "T" goto menu

REM --- Sprawdzenie Pythona ---
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [BŁĄD] Python nie jest dostępny w PATH.
    goto pauza
)

REM --- Sprawdzenie PyInstaller ---
python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo [BŁĄD] Brak PyInstaller. Zainstaluj:
    echo   python -m pip install pyinstaller
    goto pauza
)

REM --- Parametry PyInstaller ---
set "PARAM_MODE="
set "PARAM_WIN="
set "PARAM_ICON="

if /I "%TRYB%"=="onefile" (
    set "PARAM_MODE=--onefile"
) else (
    set "PARAM_MODE=--onedir"
)

if /I "%TYP%"=="okienkowy" (
    set "PARAM_WIN=--windowed"
)

if defined IKONA (
    set "PARAM_ICON=--icon=%IKONA%"
)

REM --- Profil prod: czyszczenie ---
if /I "%PROFIL%"=="prod" (
    if exist build rmdir /s /q build
    if exist dist rmdir /s /q dist
)

echo.
echo [INFO] Uruchamiam PyInstaller...
echo.

python -m PyInstaller ^
 %PARAM_MODE% ^
 %PARAM_WIN% ^
 %PARAM_ICON% ^
 --name "%EXE_NAME%" ^
 "%PY_FILE%"

if errorlevel 1 (
    echo.
    echo [BŁĄD] PyInstaller zwrocil blad. Sprawdz komunikaty powyzej.
    goto pauza
)

echo.
echo [SUKCES] Zbudowano EXE.
echo   dist\%EXE_NAME%.exe
goto pauza

:koniec
echo.
echo Koniec.
endlocal