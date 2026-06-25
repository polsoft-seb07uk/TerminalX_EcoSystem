@echo off
title polsoft.ITS(TM) PyLauncher by Sebastian Januchowski
setlocal enabledelayedexpansion

rem === Kolory ANSI ===
for /F %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"
set "Cyan=%ESC%[36m"
set "Green=%ESC%[92m"
set "Yellow=%ESC%[93m"
set "Magenta=%ESC%[95m"
set "Reset=%ESC%[0m"
set "C_RESET=%ESC%[0m"
set "C_HIGHLIGHT=%ESC%[30;42m"
set "C_NORMAL=%ESC%[97m"
set "C_TITLE=%ESC%[92m"
set "C_ERR=%ESC%[91m"

echo %Cyan%             _            __ _      _____  _____  __   
echo  _ __   ___ ^| ^|___  ___  / _^| ^|_    \_   \/__   \/ _\   
echo ^| '_ \ / _ \^| / __^|/ _ \^| ^|_^| __^|    / /\/  / /\/\ \    
echo ^| ^|_) ^| (_) ^| \__ \ (_) ^|  _^| ^|_ _/\/ /_   / /   _\ \   
echo ^| .__/ \___/^|_^|___/\___/^|_^|  \__(_)____/   \/    \__/   
echo ^|_^|%Reset%  [2mBatch v1.7 PyLauncher by Sebastian Januchowski[0m                                 
echo.

rem === Zbierz wszystkie pliki .py ===
:scan
cls
echo %C_TITLE%Skanowanie plikow...%C_RESET%
cd /d "%~dp0"
set count=0
set "spaces=                                             "
set "count_py=0"

rem === Grupa .py ===
for /r %%F in (*.py) do (
    if /i "%%~xF"==".py" (
        set /a count+=1
        set /a count_py+=1
        set /p "=%Green%.%Reset%" <nul
        set "file[!count!]=%%~fF"
        set "size[!count!]=%%~zF"
        set "date[!count!]=%%~tF"
        set "fname=%%~nxF"
        set "fdisplay=!fname!%spaces%"
        set "fdisplay=!fdisplay:~0,35!"
        set "fsize=%%~zF bytes"
        set "sdisplay=!fsize!%spaces%"
        set "sdisplay=!sdisplay:~0,15!"
        set "path[!count!]=%%~fF"
        set "line[!count!]=!fdisplay! !sdisplay! %%~tF"
    )
)

set /a start_pyw=count_py+1

rem === Grupa .pyw ===
set "count_pyw=0"
for /r %%F in (*.pyw) do (
    set /a count+=1
    set /a count_pyw+=1
    set /p "=%Magenta%.%Reset%" <nul
    set "file[!count!]=%%~fF"
    set "size[!count!]=%%~zF"
    set "date[!count!]=%%~tF"
    set "fname=%%~nxF"
    set "fdisplay=!fname!%spaces%"
    set "fdisplay=!fdisplay:~0,35!"
    set "fsize=%%~zF bytes"
    set "sdisplay=!fsize!%spaces%"
    set "sdisplay=!sdisplay:~0,15!"
    set "path[!count!]=%%~fF"
    set "line[!count!]=!fdisplay! !sdisplay! %%~tF"
)

rem === Brak plików .py ===
if %count%==0 (
    echo %C_ERR%Brak plikow .py w tym katalogu.%C_RESET%
    pause
    exit /b
)

set "pos=1"
set /a opt_new=count+1
set /a opt_exit=count+2
set /a total=count+2

:menu
cls
echo %Cyan%             _            __ _      _____  _____  __   
echo  _ __   ___ ^| ^|___  ___  / _^| ^|_    \_   \/__   \/ _\   
echo ^| '_ \ / _ \^| / __^|/ _ \^| ^|_^| __^|    / /\/  / /\/\ \    
echo ^| ^|_) ^| (_) ^| \__ \ (_) ^|  _^| ^|_ _/\/ /_   / /   _\ \   
echo ^| .__/ \___/^|_^|___/\___/^|_^|  \__(_)____/   \/    \__/   
echo ^|_^|%Reset%  [2mBatch (.bat) PyLauncher by Sebastian Januchowski[0m                                 
echo.
echo.
echo %C_TITLE%Wybierz plik Python (strzalki UP/DOWN, Enter):%C_RESET%
echo.
set "h_name=Nazwa%spaces%"
set "h_name=!h_name:~0,35!"
set "h_size=Rozmiar%spaces%"
set "h_size=!h_size:~0,15!"
echo      %Cyan%!h_name! !h_size! Data%Reset%

for /l %%i in (1,1,%count%) do (
    if %%i==1 if !count_py! GTR 0 echo %Magenta%--- Skrypty Python (!count_py!^) ---%Reset%
    if %%i==!start_pyw! (
        if !count_py! GTR 0 echo.
        echo %Magenta%--- Skrypty Bezokienne (!count_pyw!^) ---%Reset%
    )
    if %%i==!pos! (
        echo %C_HIGHLIGHT%  !line[%%i]!  %C_RESET%
    ) else (
        echo %C_NORMAL%  !line[%%i]!  %C_RESET%
    )
)

echo.
if !pos!==!opt_new! (
    echo %C_HIGHLIGHT%  Utworz nowy plik  %C_RESET%
) else (
    echo %C_NORMAL%  Utworz nowy plik  %C_RESET%
)
if !pos!==!opt_exit! (
    echo %C_HIGHLIGHT%  Wyjscie  %C_RESET%
) else (
    echo %C_NORMAL%  Wyjscie  %C_RESET%
)

echo.
if !pos! LEQ %count% (
    echo %C_TITLE%Lokalizacja: !path[%pos%]!%C_RESET%
) else (
    echo.
)

rem === Odczyt klawisza (strzalki + Enter) ===
call :getKey key

if "!key!"=="UP" (
    set /a pos-=1
    if !pos! LSS 1 set pos=!total!
)
if "!key!"=="DOWN" (
    set /a pos+=1
    if !pos! GTR !total! set pos=1
)
if "!key!"=="ENTER" (
    if !pos! LEQ %count% (
        set "selected_file=!file[%pos%]!"
        goto action_init
    )
    if !pos!==!opt_new! goto create_new
    if !pos!==!opt_exit! exit
)

goto menu

:action_init
set "act_pos=1"

:file_options_menu
cls
echo %C_TITLE%Wybrano: !selected_file!%C_RESET%
echo.
echo %C_TITLE%Wybierz akcje:%C_RESET%
if !act_pos!==1 (echo %C_HIGHLIGHT%  Uruchom  %C_RESET%) else (echo %C_NORMAL%  Uruchom  %C_RESET%)
if !act_pos!==2 (echo %C_HIGHLIGHT%  Edytuj  %C_RESET%) else (echo %C_NORMAL%  Edytuj  %C_RESET%)
if !act_pos!==3 (echo %C_HIGHLIGHT%  Zmien nazwe  %C_RESET%) else (echo %C_NORMAL%  Zmien nazwe  %C_RESET%)
if !act_pos!==4 (echo %C_HIGHLIGHT%  Usun  %C_RESET%) else (echo %C_NORMAL%  Usun  %C_RESET%)
if !act_pos!==5 (echo %C_HIGHLIGHT%  Otworz folder  %C_RESET%) else (echo %C_NORMAL%  Otworz folder  %C_RESET%)
if !act_pos!==6 (echo %C_HIGHLIGHT%  Wstecz  %C_RESET%) else (echo %C_NORMAL%  Wstecz  %C_RESET%)

call :getKey key
if "!key!"=="UP" (set /a act_pos-=1 & if !act_pos! LSS 1 set act_pos=6)
if "!key!"=="DOWN" (set /a act_pos+=1 & if !act_pos! GTR 6 set act_pos=1)

rem === Skroty klawiszowe ===
if /i "!key!"=="U" set "act_pos=1" & goto action_execute
if /i "!key!"=="E" set "act_pos=2" & goto action_execute
if /i "!key!"=="Z" set "act_pos=3" & goto action_execute
if /i "!key!"=="D" set "act_pos=4" & goto action_execute
if /i "!key!"=="O" set "act_pos=5" & goto action_execute
if /i "!key!"=="W" set "act_pos=6" & goto action_execute
if "!key!"=="ENTER" goto action_execute
goto file_options_menu

:action_execute
    if !act_pos!==1 goto console_init
    if !act_pos!==2 (
        start "" notepad "!selected_file!"
        goto menu
    )
    if !act_pos!==3 (
        cls
        echo %C_TITLE%Zmiana nazwy pliku: !selected_file!%C_RESET%
        echo.
        set /p "newname=Podaj nowa nazwe (z rozszerzeniem): "
        if defined newname (
            ren "!selected_file!" "!newname!"
            echo Zmieniono nazwe.
            timeout /t 1 >nul
            goto scan
        )
        goto file_options_menu
    )
    if !act_pos!==4 (
        cls
        echo %ESC%[41;97m                                             %C_RESET%
        echo %ESC%[41;97m           CZY NA PEWNO USUNAC PLIK?         %C_RESET%
        echo %ESC%[41;97m                                             %C_RESET%
        echo.
        echo %C_ERR%!selected_file!%C_RESET%
        echo.
        echo %C_ERR%Wcisnij 'T' aby potwierdzic, lub inny klawisz aby anulowac.%C_RESET%
        set /p "confirm="
        if /i "!confirm!"=="T" (
            del "!selected_file!"
            echo Usunieto plik.
            timeout /t 1 >nul
            goto scan
        )
        goto file_options_menu
    )
    if !act_pos!==5 (
        for %%I in ("!selected_file!") do start "" explorer "%%~dpI"
        goto menu
    )
    if !act_pos!==6 goto menu

:console_init
set "act_pos=1"

:console_menu
cls
echo %C_TITLE%Wybrano: !selected_file!%C_RESET%
echo.
echo %C_TITLE%Okno konsoli:%C_RESET%
if !act_pos!==1 (echo %C_HIGHLIGHT%  Widoczne  %C_RESET%) else (echo %C_NORMAL%  Widoczne  %C_RESET%)
if !act_pos!==2 (echo %C_HIGHLIGHT%  Ukryj  %C_RESET%) else (echo %C_NORMAL%  Ukryj  %C_RESET%)
if !act_pos!==3 (echo %C_HIGHLIGHT%  Wstecz  %C_RESET%) else (echo %C_NORMAL%  Wstecz  %C_RESET%)

call :getKey key
if "!key!"=="UP" (set /a act_pos-=1 & if !act_pos! LSS 1 set act_pos=3)
if "!key!"=="DOWN" (set /a act_pos+=1 & if !act_pos! GTR 3 set act_pos=1)
if "!key!"=="ENTER" (
    if !act_pos!==1 set "console_mode=visible" & goto perm_init
    if !act_pos!==2 set "console_mode=hidden" & goto perm_init
    if !act_pos!==3 goto action_init
)
goto console_menu

:perm_init
set "act_pos=1"

:perm_menu
cls
echo %C_TITLE%Wybrano: !selected_file!%C_RESET%
echo.
echo %C_TITLE%Uprawnienia:%C_RESET%
if !act_pos!==1 (echo %C_HIGHLIGHT%  Uruchom jako %USERNAME%  %C_RESET%) else (echo %C_NORMAL%  Uruchom jako %USERNAME%  %C_RESET%)
if !act_pos!==2 (echo %C_HIGHLIGHT%  Uruchom jako Admin  %C_RESET%) else (echo %C_NORMAL%  Uruchom jako Admin  %C_RESET%)
if !act_pos!==3 (echo %C_HIGHLIGHT%  Wstecz  %C_RESET%) else (echo %C_NORMAL%  Wstecz  %C_RESET%)

call :getKey key
if "!key!"=="UP" (set /a act_pos-=1 & if !act_pos! LSS 1 set act_pos=3)
if "!key!"=="DOWN" (set /a act_pos+=1 & if !act_pos! GTR 3 set act_pos=1)
if "!key!"=="ENTER" (
    if !act_pos!==1 set "perm_mode=user" & goto execute
    if !act_pos!==2 set "perm_mode=admin" & goto execute
    if !act_pos!==3 goto console_init
)
goto perm_menu

:execute
cls
echo %C_TITLE%Uruchamiam...%C_RESET%
for %%I in ("!selected_file!") do set "full_path=%%~fI"
set "prog=python"
where py >nul 2>&1 && set "prog=py"

if "!console_mode!"=="visible" (
    if "!perm_mode!"=="user" (
        call :runPython "!selected_file!"
        exit /b
    )
    if "!perm_mode!"=="admin" (
        powershell -Command "Start-Process cmd -ArgumentList '/c !prog! \"!full_path!\" & pause' -Verb RunAs"
        exit /b
    )
)

if "!console_mode!"=="hidden" (
    if "!perm_mode!"=="user" (
        powershell -WindowStyle Hidden -Command "!prog! '!full_path!'"
        exit /b
    )
    if "!perm_mode!"=="admin" (
        powershell -Command "Start-Process !prog! -ArgumentList '\"!full_path!\"' -Verb RunAs -WindowStyle Hidden"
        exit /b
    )
)
exit /b

rem === Funkcja: odczyt strzalek i Enter ===
:getKey
set "%~1="
for /f "delims=" %%a in ('powershell -NoProfile -Command "$k = $Host.UI.RawUI.ReadKey('NoEcho,IncludeKeyDown'); if($k.VirtualKeyCode -eq 38){'UP'}elseif($k.VirtualKeyCode -eq 40){'DOWN'}elseif($k.VirtualKeyCode -eq 13){'ENTER'}elseif($k.VirtualKeyCode -eq 85){'U'}elseif($k.VirtualKeyCode -eq 69){'E'}elseif($k.VirtualKeyCode -eq 90){'Z'}elseif($k.VirtualKeyCode -eq 68){'D'}elseif($k.VirtualKeyCode -eq 79){'O'}elseif($k.VirtualKeyCode -eq 87){'W'}"') do set "%~1=%%a"
exit /b

:runPython
rem === Funkcja uruchamiajaca Python ===
where py >nul 2>&1 && py "%~1" && exit /b
where python >nul 2>&1 && python "%~1" && exit /b
echo %C_ERR%Nie znaleziono interpretera Python.%C_RESET%
pause
exit /b

:create_new
cls
echo %C_TITLE%Tworzenie nowego pliku Python%C_RESET%
echo.
set /p "new_fname=Podaj nazwe pliku: "
if not defined new_fname goto menu
if /i not "!new_fname:~-3!"==".py" if /i not "!new_fname:~-4!"==".pyw" set "new_fname=!new_fname!.py"
if exist "!new_fname!" (
    echo %C_ERR%Plik juz istnieje!%C_RESET%
    timeout /t 2 >nul
    goto menu
)
type nul > "!new_fname!"
goto scan