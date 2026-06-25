#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
# crossterm: {"id": "01", "aliases": ["cal", "calendar"], "description": "Kalendarz i czas", "version": "2.3", "author": "Sebastian Januchowski"}
"""
Moduł Calendar v2.3
  cal                          — bieżący miesiąc
  cal now                      — dashboard: kalendarz + panel dnia
  cal week                     — tydzień i dzień roku
  cal <mm>                     — miesiąc (bieżący rok)
  cal <mm yyyy>                — miesiąc i rok
  cal year [yyyy]              — pełny rok
  cal countdown <RRRR-MM-DD>   — odliczanie
  cal event add <RRRR-MM-DD> <opis> — dodaj wydarzenie
  cal event list               — lista wydarzeń
  cal event clear              — usuń wszystkie wydarzenia
  calendar                     — alias → cal year
"""

import calendar as _cal
import datetime as _dt
import sys     as _sys
import shutil  as _sh
import re      as _re
import os      as _os
import json    as _json
import bisect  as _bi
import platform as _plt
import subprocess as _sp
import urllib.request as _ur
import urllib.error as _ue
import urllib.parse as _up
import time as _tm
from collections import Counter as _Counter

def _w(s):
    """Standard write, but avoiding unnecessary flushes for performance."""
    _sys.stdout.write(s)

class _Buf:
    """Buforowane wyjście — zbiera fragmenty i zapisuje jednym write()."""
    __slots__ = ('_parts',)
    def __init__(self):    self._parts = []
    def w(self, s):        self._parts.append(s)
    def flush(self):
        if self._parts:
            _sys.stdout.write(''.join(self._parts))
            _sys.stdout.flush()
            self._parts.clear()

class _C:
    RESET   = "\x1b[0m";  BOLD    = "\x1b[1m";  DIM     = "\x1b[2m"
    UNDERLINE = "\x1b[4m"; INV     = "\x1b[7m"
    # Kolory ustawiane dynamicznie przez _apply_theme
    BCYAN = ""; BYELLOW = ""; BGREEN = ""; BWHITE = ""
    RED = ""; CYAN = ""; MAGENTA = ""; YELLOW = ""; BLUE = ""

_THEMES = {
    "dark": {
        "BCYAN": "\x1b[96m", "BYELLOW": "\x1b[93m", "BGREEN": "\x1b[92m",
        "BWHITE": "\x1b[97m", "RED": "\x1b[91m", "CYAN": "\x1b[96m",
        "MAGENTA": "\x1b[95m", "YELLOW": "\x1b[93m", "BLUE": "\x1b[94m"
    },
    "light": {
        "BCYAN": "\x1b[36m", "BYELLOW": "\x1b[33m", "BGREEN": "\x1b[32m",
        "BWHITE": "\x1b[1m",  "RED": "\x1b[31m", "CYAN": "\x1b[36m",
        "MAGENTA": "\x1b[35m", "YELLOW": "\x1b[33m", "BLUE": "\x1b[34m"
    }
}

# Globalna lista wydarzeń i ustawienia
_EVENTS = []   # Format: [{'date': datetime.date, 'desc': str, 'tags': list}]
_PERSONAL_NAMEDAYS = [] # Format: [{'date': 'MM-DD', 'name': str}]
_RECURRING = []  # Format: [{'freq': 'yearly'|'monthly'|'weekly', 'start': str, 'desc': str, 'end': str|None}]
_NOTES     = {}  # Format: {'RRRR-MM-DD': ['notatka1', 'notatka2', ...]}
_CONFIG    = {"interval": 60, "last_notified": None, "theme": "light", "city": ""}
_REMIND_CONFIG = {}  # Format: {'event_desc_hash': days_before} — przechowywany jako lista w JSON

# Kolory per element (nadpisują motyw gdy ustawione)
_COLOR_CONFIG = {}  # np. {"today": "\x1b[92m", "event": "\x1b[95m", "weekend": "\x1b[33m"}
_COLOR_ELEMENTS = {
    "today":   ("Dzisiejsza data",       "\x1b[7m\x1b[1m\x1b[92m"),
    "event":   ("Dzień z wydarzeniem",   "\x1b[4m\x1b[1m\x1b[95m"),
    "weekend": ("Dzień weekendu",        "\x1b[33m"),
    "header":  ("Nagłówek miesiąca",     "\x1b[1m\x1b[34m"),
    "title":   ("Tytuł roku/miesiąca",   "\x1b[1m\x1b[33m"),
}

_KNOWN_CONFIG_KEYS = {"interval", "last_notified", "theme", "city", "remind_days"}

_CACHE_SPECIAL = {"date": None, "text": None} # Cache w pamięci dla bieżącego uruchomienia

def _apply_theme(name):
    """Aplikuje wybrany motyw kolorystyczny do klasy _C."""
    theme = _THEMES.get(name, _THEMES["light"])
    _C.BCYAN = theme["BCYAN"]; _C.BYELLOW = theme["BYELLOW"]; _C.BGREEN = theme["BGREEN"]
    _C.BWHITE = theme["BWHITE"]; _C.RED = theme["RED"]; _C.CYAN = theme["CYAN"]
    _C.MAGENTA = theme["MAGENTA"]; _C.YELLOW = theme["YELLOW"]; _C.BLUE = theme["BLUE"]
    _CONFIG["theme"] = name

# Domyślne zaaplikowanie motywu przy starcie (zostanie nadpisane przez load_db)
_apply_theme("light")

_ANSI = _re.compile(r'\x1b\[[0-9;]*[mA-Z]')

def _vis(s):
    """Visible length of string (no ANSI)."""
    return len(_ANSI.sub('', s))

def _pad(s, width):
    """Right-pad to visible width."""
    return s + ' ' * max(0, width - _vis(s))

# Cache dla pogody
_WEATHER_CACHE_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "weather_cache.json")
_CACHE_WEATHER = {"time": 0, "text": None}

# Nowy księżyc referencyjny (6 stycznia 2000)
_NEW_MOON_REF_DATE = _dt.date(2000, 1, 6)
_SYNODIC_MONTH_DAYS = 29.53058867

def _get_moon_phase_info(date_obj):
    """
    Calculates the approximate moon phase for a given date.
    Returns a tuple: (phase_name, emoji).
    """
    # Oblicz liczbę dni od referencyjnego nowego księżyca
    days_since_ref = (date_obj - _NEW_MOON_REF_DATE).days
    
    # Oblicz wiek księżyca w bieżącym cyklu synodycznym
    moon_age = days_since_ref % _SYNODIC_MONTH_DAYS

    # Mapuj wiek księżyca na fazy i emoji
    if 0 <= moon_age < 1.84:
        return "Nowy Księżyc", "🌑" # New Moon
    elif 1.84 <= moon_age < 5.53:
        return "Wschodzący Sierp", "🌒" # Waxing Crescent
    elif 5.53 <= moon_age < 9.22:
        return "Pierwsza Kwadra", "🌓" # First Quarter
    elif 9.22 <= moon_age < 12.91:
        return "Wschodzący Garbaty", "🌔" # Waxing Gibbous
    elif 12.91 <= moon_age < 16.61:
        return "Pełnia", "🌕" # Full Moon
    elif 16.61 <= moon_age < 20.30:
        return "Malejący Garbaty", "🌖" # Waning Gibbous
    elif 20.30 <= moon_age < 23.99:
        return "Ostatnia Kwadra", "🌗" # Last Quarter
    else: # 23.99 <= moon_age < 29.53
        return "Malejący Sierp", "🌘" # Waning Crescent

def _get_weather_info():
    """Pobiera pogodę z wttr.in z użyciem cache (1h)."""
    global _CACHE_WEATHER
    now_ts = _tm.time()

    # 1. Pamięć
    if _CACHE_WEATHER["text"] and (now_ts - _CACHE_WEATHER["time"] < 3600):
        return _CACHE_WEATHER["text"]

    # 2. Plik
    if _os.path.exists(_WEATHER_CACHE_FILE):
        try:
            with open(_WEATHER_CACHE_FILE, "r", encoding="utf-8") as f:
                data = _json.load(f)
                if now_ts - data.get("time", 0) < 3600:
                    _CACHE_WEATHER = data
                    return data["text"]
        except: pass

    # 3. API
    try:
        city = _CONFIG.get("city", "")
        quoted_city = _up.quote(city)
        # format=%t+%C daje np. "+15°C Clear"
        url = f"https://wttr.in/{quoted_city}?format=%t+%C"
        req = _ur.Request(url, headers={'User-Agent': 'CrossTerm/1.6'})
        with _ur.urlopen(req, timeout=1.5) as response:
            text = response.read().decode('utf-8').strip()
            if text and "unknown" not in text.lower():
                # Mapowanie opisów na emoji
                m = {
                    "Clear": "☀️", "Sunny": "☀️", "Partly cloudy": "⛅",
                    "Cloudy": "☁️", "Overcast": "☁️", "Mist": "🌫️", "Fog": "🌫️",
                    "Rain": "🌧️", "Drizzle": "🌧️", "Showers": "🌦️", "Snow": "❄️",
                    "Thunderstorm": "⛈️"
                }
                for cond, emoji in m.items():
                    if cond in text:
                        text = text.replace(cond, f"{emoji} {cond}")
                        break
                _CACHE_WEATHER = {"time": now_ts, "text": text}
                with open(_WEATHER_CACHE_FILE, "w", encoding="utf-8") as f:
                    _json.dump(_CACHE_WEATHER, f)
                return text
    except: pass
    return None

# Plik cache dla imienin
_NAMEDAY_CACHE_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "nameday_cache.json")
# Stała lokalna baza imienin (fallback offline)
_NAMEDAY_LOCAL_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "namedays_local.json")

_NAMEDAY_LOCAL_DB_CACHE = None  # cache w pamięci dla namedays_local.json

def _get_nameday_from_local_db(month, day):
    """Pobiera imieniny z lokalnego pliku JSON (format {"MM-DD": "Imiona"})."""
    global _NAMEDAY_LOCAL_DB_CACHE
    if _NAMEDAY_LOCAL_DB_CACHE is None:
        if not _os.path.exists(_NAMEDAY_LOCAL_FILE):
            _NAMEDAY_LOCAL_DB_CACHE = {}
            return None
        try:
            with open(_NAMEDAY_LOCAL_FILE, "r", encoding="utf-8") as f:
                _NAMEDAY_LOCAL_DB_CACHE = _json.load(f)
        except Exception:
            _NAMEDAY_LOCAL_DB_CACHE = {}
            return None
    key = f"{month:02d}-{day:02d}"
    return _NAMEDAY_LOCAL_DB_CACHE.get(key)

def _load_nameday_cache_from_file():
    """Ładuje informacje o imieninach z pliku cache, jeśli dotyczą dzisiejszej daty."""
    if not _os.path.exists(_NAMEDAY_CACHE_FILE):
        return None
    try:
        with open(_NAMEDAY_CACHE_FILE, "r", encoding="utf-8") as f:
            data = _json.load(f)
            if isinstance(data, dict) and "date" in data and "names" in data:
                cached_date = _dt.datetime.strptime(data["date"], "%Y-%m-%d").date()
                if cached_date == _dt.date.today():
                    return data["names"]
    except Exception as e:
        _sys.stderr.write(f"Błąd ładowania cache imienin z pliku: {e}\n")
    return None

def _save_nameday_cache_to_file(date_obj, names_str):
    """Zapisuje informacje o imieninach do pliku cache."""
    try:
        data = {"date": date_obj.strftime("%Y-%m-%d"), "names": names_str}
        with open(_NAMEDAY_CACHE_FILE, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        _sys.stderr.write(f"Błąd zapisu cache imienin do pliku: {e}\n")

def _get_special_info():
    """Pobiera informacje o imieninach z API z użyciem cache i timeoutu."""
    global _CACHE_SPECIAL
    today = _dt.date.today()

    # 1. Sprawdź cache w pamięci (dla wielu wywołań w tej samej sesji)
    if _CACHE_SPECIAL["date"] == today:
        return _CACHE_SPECIAL["text"]

    # 2. Sprawdź cache w pliku
    file_cached_names = _load_nameday_cache_from_file()
    if file_cached_names:
        _CACHE_SPECIAL = {"date": today, "text": file_cached_names} # Zaktualizuj cache w pamięci
        return file_cached_names

    # 3. Próba pobrania danych z API (timeout 1.5s, aby nie blokować terminala)
    try:
        url = "https://nameday.abalin.net/api/V1/today?country=pl"
        req = _ur.Request(url, headers={'User-Agent': 'CrossTerm/1.6'})
        with _ur.urlopen(req, timeout=1.5) as response:
            data = _json.loads(response.read().decode())
            names = data.get('nameday', {}).get('pl', '')
            if names:
                _CACHE_SPECIAL = {"date": today, "text": names} # Zaktualizuj cache w pamięci
                _save_nameday_cache_to_file(today, names) # Zapisz do cache w pliku
                return names
    except Exception:
        pass

    # 4. Fallback: Stała lokalna baza danych (offline)
    local_names = _get_nameday_from_local_db(today.month, today.day)
    if local_names:
        _CACHE_SPECIAL = {"date": today, "text": local_names}
        return local_names

    return None

_DB_FILE = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "events.json")

def _load_db():
    """Ładuje wydarzenia z lokalnego pliku JSON przy starcie."""
    global _EVENTS, _CONFIG, _PERSONAL_NAMEDAYS, _RECURRING, _COLOR_CONFIG, _NOTES, _REMIND_CONFIG
    if not _os.path.exists(_DB_FILE):
        return
    try:
        with open(_DB_FILE, "r", encoding="utf-8") as f:
            data = _json.load(f)
        if isinstance(data, dict):
            _CONFIG.update(data.get("settings", {}))
            raw_events = data.get("events", [])
            _PERSONAL_NAMEDAYS[:] = data.get("personal_namedays", [])
            _RECURRING[:] = data.get("recurring", [])
            _COLOR_CONFIG.update(data.get("color_config", {}))
            _NOTES.clear(); _NOTES.update(data.get("notes", {}))
            _REMIND_CONFIG.clear(); _REMIND_CONFIG.update(data.get("remind_config", {}))
        else:
            raw_events = data

        _EVENTS.clear()
        for item in raw_events:
            d = _dt.datetime.strptime(item['date'], "%Y-%m-%d").date()
            _EVENTS.append({'date': d, 'desc': item['desc'], 'tags': item.get('tags', [])})
        _EVENTS.sort(key=lambda x: x['date'])

        _apply_theme(_CONFIG.get("theme", "light"))
    except Exception as e:
        _sys.stderr.write(f"Błąd ładowania bazy: {e}\n")

def _save_db():
    """Zapisuje aktualną listę wydarzeń do pliku JSON (zapis atomowy)."""
    tmp = _DB_FILE + ".tmp"
    try:
        data = {
            "settings": _CONFIG,
            "events": [{'date': str(e['date']), 'desc': e['desc'], 'tags': e.get('tags', [])} for e in _EVENTS],
            "personal_namedays": _PERSONAL_NAMEDAYS,
            "recurring": _RECURRING,
            "color_config": _COLOR_CONFIG,
            "notes": _NOTES,
            "remind_config": _REMIND_CONFIG,
        }
        with open(tmp, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2, ensure_ascii=False)
            f.flush()
            _os.fsync(f.fileno())
        _os.replace(tmp, _DB_FILE)
    except Exception as e:
        _sys.stderr.write(f"Błąd zapisu bazy: {e}\n")
        try: _os.remove(tmp)
        except: pass

def _send_notification(title, msg):
    """Wysyła natywne powiadomienie systemowe (cross-platform)."""
    sys_name = _plt.system()
    try:
        if sys_name == "Windows":
            # Escapowanie cudzysłowów dla PowerShell
            t = title.replace('"', '`"')
            m = msg.replace('"', '`"')
            ps_cmd = (
                f'[void][reflection.assembly]::loadwithpartialname("System.Windows.Forms");'
                f'$n = New-Object System.Windows.Forms.NotifyIcon;'
                f'$n.Icon = [System.Drawing.SystemIcons]::Information;'
                f'$n.Visible = $true;'
                f'$n.ShowBalloonTip(5000, "{t}", "{m}", [System.Windows.Forms.ToolTipIcon]::Info);'
            )
            _sp.run(["powershell", "-Command", ps_cmd], capture_output=True)
        elif sys_name == "Linux":
            _sp.run(["notify-send", title, msg], capture_output=True)
        elif sys_name == "Darwin":  # macOS
            t = title.replace('"', '\\"')
            m = msg.replace('"', '\\"')
            _sp.run(["osascript", "-e", f'display notification "{m}" with title "{t}"'], capture_output=True)
    except Exception:
        pass

def _do_notify_today(force=False):
    """Sprawdza dzisiejsze wydarzenia i wysyła powiadomienie z uwzględnieniem interwału."""
    now = _dt.datetime.now()
    last_str = _CONFIG.get("last_notified")
    interval = _CONFIG.get("interval", 60)

    if not force and last_str:
        try:
            last_dt = _dt.datetime.fromisoformat(last_str)
            if (now - last_dt).total_seconds() < interval * 60:
                return # Zbyt wcześnie na kolejne powiadomienie
        except Exception:
            pass

    today = _dt.date.today()
    events = [e['desc'] for e in _EVENTS if e['date'] == today]
    if events:
        _send_notification("Kalendarz: Dzisiejsze wydarzenia", " • " + "\n • ".join(events))
        _CONFIG["last_notified"] = now.isoformat()
        _save_db()

# ─── Święta polskie ────────────────────────────────────────────────────────────

def _easter(year):
    """Oblicza datę Wielkanocy dla danego roku (algorytm Gaussa)."""
    a = year % 19
    b = year % 4
    c = year % 7
    d = (19 * a + 24) % 30
    e = (2 * b + 4 * c + 6 * d + 5) % 7
    day = 22 + d + e
    if day > 31:
        day -= 31
        month = 4
        if day == 26: day = 19
        if day == 25 and d == 28 and e == 6 and a > 10: day = 18
    else:
        month = 3
    return _dt.date(year, month, day)

def _get_holidays(year):
    """Zwraca dict {date: name} świąt ustawowo wolnych od pracy w Polsce."""
    easter = _easter(year)
    h = {
        _dt.date(year, 1,  1):  "Nowy Rok",
        _dt.date(year, 1,  6):  "Trzech Króli",
        easter:                  "Wielkanoc",
        easter + _dt.timedelta(days=1): "Poniedziałek Wielkanocny",
        _dt.date(year, 5,  1):  "Święto Pracy",
        _dt.date(year, 5,  3):  "Święto Konstytucji 3 Maja",
        easter + _dt.timedelta(days=49): "Zesłanie Ducha Świętego",
        easter + _dt.timedelta(days=60): "Boże Ciało",
        _dt.date(year, 8, 15):  "Wniebowzięcie NMP",
        _dt.date(year, 11, 1):  "Wszystkich Świętych",
        _dt.date(year, 11, 11): "Święto Niepodległości",
        _dt.date(year, 12, 25): "Boże Narodzenie (I dzień)",
        _dt.date(year, 12, 26): "Boże Narodzenie (II dzień)",
    }
    return h

# ─── menu ──────────────────────────────────────────────────────────────────────

def cml_menu():
    _w(f"\n{_C.BOLD}{_C.BCYAN}  ╔════════════════════════════════╗{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  ║   📅  Moduł: Calendar  v2.3    ║{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  ╚════════════════════════════════╝{_C.RESET}\n\n")
    cmds = [
        ("cal",                        "Kalendarz bieżącego miesiąca"),
        ("cal now",                    "Dashboard: kalendarz + panel dnia"),
        ("cal week",                   "Tydzień roku i dzień roku"),
        ("cal <mm>",                   "Miesiąc (bieżący rok)"),
        ("cal <mm yyyy>",              "Miesiąc i rok"),
        ("cal year [yyyy]",            "Pełny kalendarz roku"),
        ("cal countdown <RRRR-MM-DD>", "Odliczanie do daty"),
        ("cal config [interval|theme|city|export|import]", "Konfiguracja modułu"),
        ("cal notify",                 "Sprawdź i wyświetl powiadomienia na dziś"),
        ("cal remind set <nr> <dni>",      "Ustaw przypomnienie X dni przed wydarzeniem"),
        ("cal remind list",                 "Lista przypomnień"),
        ("cal remind check",                "Sprawdź aktywne przypomnienia"),
        ("cal note add <data> <tekst>",     "Dodaj notatkę do daty"),
        ("cal note list [data]",            "Lista notatek (opcjonalnie dla daty)"),
        ("cal note remove <data> [nr]",     "Usuń notatkę"),
        ("cal holiday [yyyy] [mm]",         "Święta polskie dla roku/miesiąca"),
        ("cal moon [RRRR-MM-DD]",           "Faza księżyca dla daty lub dziś"),
        ("cal work [mm [yyyy]]",            "Rozliczenie dni roboczych"),
        ("cal work [yyyy]",                 "Tabela dni roboczych dla całego roku"),
        ("cal tag add <nr> <tag>",          "Dodaj tag do wydarzenia"),
        ("cal tag filter <tag>",            "Filtruj wydarzenia po tagu"),
        ("cal tag list",                    "Lista wszystkich tagów z licznikami"),
        ("cal tag remove <nr> <tag>",       "Usuń tag z wydarzenia"),
        ("cal recurring list",              "Lista wydarzeń cyklicznych"),
        ("cal recurring show [dni]",        "Najbliższe wystąpienia cyklicznych"),
        ("cal recurring remove <nr>",       "Usuń wydarzenie cykliczne"),
        ("cal diff <data1> <data2>",        "Różnica między datami (dni, robocze, tygodnie)"),
        ("cal event export ics [plik]",     "Eksport do iCalendar (.ics)"),
        ("cal config color [element] [kolor]", "Konfiguracja kolorów per element"),
        ("cal agenda [dni]",               "Agenda: dni z wydarzeniami (domyślnie 30)"),
        ("cal stats",                      "Statystyki wydarzeń"),
        ("cal event edit <nr> [data] [opis]", "Edytuj istniejące wydarzenie"),
        ("cal event nameday add <MM-DD> <imię>", "Dodaj imieniny bliskiej osoby"),
        ("cal event nameday list",      "Lista zapisanych imienin"),
        ("cal event nameday remove <nr>", "Usuń imieniny z listy"),
        ("cal event export <json|txt>", "Eksportuj wydarzenia do pliku"),
        ("cal event import <plik>",    "Importuj wydarzenia z pliku (.json, .txt, .ics)"),
        ("cal event list",             "Lista wydarzeń"),
        ("cal event remove <nr>",      "Usuń wydarzenie o danym numerze"),
        ("cal event clear",            "Usuń wszystkie wydarzenia"),
        ("calendar",                   "Alias → cal year (bieżący rok)"),
    ]
    for c, d in cmds:
        _w(f"  {_C.BYELLOW}{c:<46}{_C.RESET} {_C.DIM}{d}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Tylko 2 komendy globalne: {_C.RESET}"
       f"{_C.BYELLOW}cal{_C.RESET}  {_C.BYELLOW}calendar{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_now — dashboard ───────────────────────────────────────────────────────

# Przeniesione pomocniki poza funkcję, aby uniknąć re-definicji
def _bar(pct, w=18):
    f = int(pct * w)
    return (f"{_C.BGREEN}{'█' * f}{_C.DIM}{'░' * (w - f)}{_C.RESET}"
            f" {_C.RESET}{pct*100:.1f}%{_C.RESET}")

def _row(label, value, vc=None):
    vc = vc if vc is not None else _C.BWHITE
    return f"  {_C.BLUE}{label:<13}{_C.RESET}{vc}{value}{_C.RESET}"

def _hsep():
    return f"  {_C.BLUE}{'─' * 30}{_C.RESET}"

def _do_now():
    now     = _dt.datetime.now()
    cols, _ = _sh.get_terminal_size((80, 24))

    DAY_PL = ["Poniedziałek","Wtorek","Środa","Czwartek","Piątek","Sobota","Niedziela"]
    MON_PL = ["","Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec",
               "Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"]

    week_num  = now.isocalendar()[1]
    yday      = now.timetuple().tm_yday
    days_in_y = 366 if _cal.isleap(now.year) else 365
    days_left = days_in_y - yday
    days_in_m = _cal.monthrange(now.year, now.month)[1]
    days_left_m = days_in_m - now.day
    is_weekend  = now.weekday() >= 5
    quarter     = (now.month - 1) // 3 + 1

    bar_year = _bar(yday / days_in_y)
    bar_mon  = _bar(now.day / days_in_m)

    # Pora dnia
    h = now.hour
    if   5  <= h < 12: pora = ("Rano",        "🌅")
    elif 12 <= h < 17: pora = ("Południe",     "☀️ ")
    elif 17 <= h < 21: pora = ("Wieczór",      "🌆")
    else:              pora = ("Noc",           "🌙")

    # Strefa czasowa — jedno wywołanie
    try:    tz = _dt.datetime.now(_dt.timezone.utc).astimezone().tzname() or 'LT'
    except: tz = 'LT'

    # Pobieramy dni z wydarzeniami dla bieżącego miesiąca
    event_days = {e['date'].day for e in _EVENTS if e['date'].year == now.year and e['date'].month == now.month}

    # Pre-kompilacja regexów dla wydajności (raz, nie w pętli)
    today_pattern = _re.compile(r'(?<!\d)' + str(now.day) + r'(?!\d)')
    today_replacement = f"{_C.INV}{_C.BOLD}{_C.BGREEN}{now.day:2d}{_C.RESET}"
    event_day_patterns = {
        d: (_re.compile(r'(?<!\d)' + str(d) + r'(?!\d)'),
            f"{_C.UNDERLINE}{_C.BOLD}{_C.MAGENTA}{d:2d}{_C.RESET}")
        for d in event_days
    }


    # ── Lewa kolumna: kalendarz miesięczny ────────────────────────────────────
    _cal.setfirstweekday(0)
    raw = _cal.month(now.year, now.month).splitlines()

    CAL_INNER = 20   # szerokość tekstu kalendarza

    cal_lines = []
    for i, line in enumerate(raw):
        if i == 0:
            s = f"{_C.BOLD}{_C.BLUE}{line:^{CAL_INNER}}{_C.RESET}"
        elif i == 1:
            # nagłówek — weekend na żółto, reszta standardowa (kontrast)
            parts = line.split()   # Mo Tu We Th Fr Sa Su
            colored = []
            for j, p in enumerate(parts):
                if j >= 5:   colored.append(f"{_C.YELLOW}{p}{_C.RESET}")
                else:        colored.append(f"{_C.RESET}{p}{_C.RESET}")
            s = ' '.join(colored)
        else:
            # Wyróżniamy dni z wydarzeniami (podkreślenie)
            for d, (pat, repl) in event_day_patterns.items():
                line = pat.sub(repl, line, count=1)
            # Wyróżniamy dzisiejszą datę (ma priorytet)
            s = today_pattern.sub(today_replacement, line, count=1)
        cal_lines.append(s)

    # Uzupełnij do 8 wierszy
    while len(cal_lines) < 8:
        cal_lines.append('')

    # ── Prawa kolumna: panel informacyjny ─────────────────────────────────────
    C = _C

    special = _get_special_info()
    
    # Pobieranie personalnych imienin
    today_md = now.strftime('%m-%d')
    personal = [e['name'] for e in _PERSONAL_NAMEDAYS if e['date'] == today_md]
    if personal:
        p_str = f"{C.BGREEN}{', '.join(personal)}{C.RESET}"
        special = f"{special} | {p_str}" if special else p_str

    moon_name, moon_emoji = _get_moon_phase_info(now.date())
    weather = _get_weather_info()
    weekend_tag = f"  {C.RED}weekend{C.RESET}" if is_weekend else ""

    info = [
        # Godzina + strefa
        f"  {C.BOLD}{C.BLUE}{now.strftime('%H:%M:%S')}{C.RESET}"
        f"  {C.DIM}{tz}{C.RESET}"
        f"  {C.DIM}{pora[1]} {pora[0]}{C.RESET}",
        # Dzień tygodnia
        f"  {C.BLUE}Księżyc:    {C.RESET}{C.BWHITE}{moon_emoji} {moon_name}{C.RESET}",
        # Dzień tygodnia
        f"  {C.BOLD}{C.BWHITE}{DAY_PL[now.weekday()]}{C.RESET}{weekend_tag}",
        # Data pełna
        f"  {C.BWHITE}{now.day} {MON_PL[now.month]} {now.year}{C.RESET}"
        f"  {C.DIM}({now.strftime('%d.%m.%Y')}){C.RESET}",
    ]

    if special:
        info.append(f"  {C.BLUE}Imieniny:  {C.RESET}{C.YELLOW}{special}{C.RESET}")

    if weather:
        info.append(f"  {C.BLUE}Pogoda:     {C.RESET}{C.CYAN}{weather}{C.RESET}")

    info += [
        _hsep(),
        _row("Tydzień roku",  str(week_num)),
        _row("Dzień roku",    f"{yday}  {C.DIM}/ {days_in_y}  (zostało {days_left}){C.RESET}"),
        _row("Kwartał",       f"Q{quarter}"),
        _row("Dni w mies.",   f"{now.day} / {days_in_m}"
            + (f"  {C.DIM}(zostało {days_left_m}){C.RESET}" if days_left_m > 0 else f"  {C.BGREEN}ostatni!{C.RESET}")),
        _hsep(),
        f"  {C.BLUE}Rok    {C.RESET}{bar_year}",
        f"  {C.BLUE}Mies.  {C.RESET}{bar_mon}",
    ]

    # ── Nadchodzące wydarzenia (max 3) ────────────────────────────────────────
    idx = _bi.bisect_left(_EVENTS, now.date(), key=lambda x: x['date'])
    upcoming = _EVENTS[idx:idx+3]
    if upcoming:
        info.append(_hsep())
        for e in upcoming:
            d_str = e['date'].strftime('%d.%m')
            desc  = (e['desc'][:17] + '...') if len(e['desc']) > 20 else e['desc']
            info.append(f"  {C.YELLOW}{d_str}{C.RESET}  {desc}")

    # ── Złożenie ──────────────────────────────────────────────────────────────
    CAL_COL = CAL_INNER + 6   # widoczna szerokość lewej kolumny z marginesami
    VSEP    = f"{C.BLUE}│{C.RESET}"
    n       = max(len(cal_lines), len(info))

    while len(cal_lines) < n: cal_lines.append('')
    while len(info)      < n: info.append('')

    _w("\n")
    for cl, il in zip(cal_lines, info):
        left = _pad(f"  {cl}", CAL_COL)
        _w(f"{left}  {VSEP}  {il}\n")
    _w("\n")
    _sys.stdout.flush()

# ─── _do_month ─────────────────────────────────────────────────────────────────

def _do_month(month, year):
    now   = _dt.datetime.now()
    _cal.setfirstweekday(0)
    lines = _cal.month(year, month).splitlines()
    event_days = {e['date'].day for e in _EVENTS if e['date'].year == year and e['date'].month == month}
    today = now.day if (month == now.month and year == now.year) else -1

    col_today  = _COLOR_CONFIG.get("today",   f"{_C.INV}{_C.BOLD}{_C.BGREEN}")
    col_event  = _COLOR_CONFIG.get("event",   f"{_C.UNDERLINE}{_C.BOLD}{_C.MAGENTA}")
    col_header = _COLOR_CONFIG.get("header",  f"{_C.BOLD}{_C.BLUE}")
    col_we     = _COLOR_CONFIG.get("weekend", _C.YELLOW)

    event_day_patterns = {
        d: (_re.compile(r'(?<!\d)' + str(d) + r'(?!\d)'),
            f"{col_event}{d:2d}{_C.RESET}")
        for d in event_days
    }
    today_pat  = _re.compile(r'(?<!\d)' + str(today) + r'(?!\d)') if today > 0 else None
    today_repl = f"{col_today}{today:2d}{_C.RESET}" if today > 0 else ""

    buf = _Buf()
    buf.w("\n")
    for i, line in enumerate(lines):
        if i == 0:
            buf.w(f"  {col_header}{line:^22}{_C.RESET}\n")
        elif i == 1:
            parts   = line.split()
            colored = [f"{col_we}{p}{_C.RESET}" if j >= 5 else f"{_C.DIM}{p}{_C.RESET}" for j, p in enumerate(parts)]
            buf.w("  " + ' '.join(colored) + "\n")
        else:
            for d, (pat, repl) in event_day_patterns.items():
                line = pat.sub(repl, line, count=1)
            if today_pat:
                line = today_pat.sub(today_repl, line, count=1)
            buf.w(f"  {line}\n")
    buf.w("\n")
    buf.flush()

# ─── _do_year ──────────────────────────────────────────────────────────────────

def _do_year(year):
    today = _dt.date.today()
    _cal.setfirstweekday(0)

    col_today  = _COLOR_CONFIG.get("today",   f"{_C.INV}{_C.BOLD}{_C.BGREEN}")
    col_event  = _COLOR_CONFIG.get("event",   f"{_C.UNDERLINE}{_C.BOLD}{_C.MAGENTA}")
    col_title  = _COLOR_CONFIG.get("title",   f"{_C.BOLD}{_C.YELLOW}")
    col_we     = _COLOR_CONFIG.get("weekend", _C.YELLOW)

    buf = _Buf()
    buf.w(f"\n{_C.BOLD}{_C.BLUE}  {'Kalendarz ' + str(year):^72}{_C.RESET}\n\n")

    year_event_days = {}
    for e in _EVENTS:
        if e['date'].year == year:
            year_event_days.setdefault(e['date'].month, set()).add(e['date'].day)

    for row_start in range(1, 13, 3):
        month_blocks = []
        for m in range(row_start, row_start + 3):
            event_days = year_event_days.get(m, set())
            is_today   = today.day if (year == today.year and m == today.month) else -1

            ev_patterns = {
                d: (_re.compile(r'(?<!\d)' + str(d) + r'(?!\d)'),
                    f"{col_event}{d:2d}{_C.RESET}")
                for d in event_days
            }
            today_pat_y  = _re.compile(r'(?<!\d)' + str(is_today) + r'(?!\d)') if is_today > 0 else None
            today_repl_y = f"{col_today}{is_today:2d}{_C.RESET}" if is_today > 0 else ""

            raw_lines = _cal.month(year, m).splitlines()
            styled = []
            for i, line in enumerate(raw_lines):
                if i == 0:
                    styled.append(f"{col_title}{line:^20}{_C.RESET}")
                elif i == 1:
                    parts = line.split()
                    colored = [f"{col_we}{p}{_C.RESET}" if j >= 5 else f"{_C.DIM}{p}{_C.RESET}" for j, p in enumerate(parts)]
                    styled.append(" ".join(colored))
                else:
                    for d, (pat, repl) in ev_patterns.items():
                        line = pat.sub(repl, line, count=1)
                    if today_pat_y:
                        line = today_pat_y.sub(today_repl_y, line, count=1)
                    styled.append(line)
            month_blocks.append(styled)

        max_lines = max(len(b) for b in month_blocks)
        for i in range(max_lines):
            line_out = "  "
            for b in month_blocks:
                content = b[i] if i < len(b) else ""
                line_out += _pad(content, 22) + "  "
            buf.w(line_out.rstrip() + "\n")
        buf.w("\n")
    buf.flush()

# ─── _do_week ──────────────────────────────────────────────────────────────────

def _do_week():
    now       = _dt.datetime.now()
    week      = now.isocalendar()[1]
    yday      = now.timetuple().tm_yday
    days_in_y = 366 if _cal.isleap(now.year) else 365
    days_left = days_in_y - yday

    DAY_PL = ["Pn","Wt","Śr","Cz","Pt","Sb","Nd"]
    MON_PL_SHORT = ["","Sty","Lut","Mar","Kwi","Maj","Cze","Lip","Sie","Wrz","Paź","Lis","Gru"]
    # Poniedziałek bieżącego tygodnia
    mon = now.date() - _dt.timedelta(days=now.weekday())
    week_days = [mon + _dt.timedelta(days=i) for i in range(7)]
    # Dni z wydarzeniami w tym tygodniu
    event_day_set = {e['date'] for e in _EVENTS if mon <= e['date'] <= week_days[-1]}

    _w(f"\n  {_C.BCYAN}Tydzień roku:{_C.RESET}  {_C.BOLD}{week}{_C.RESET}\n")
    _w(f"  {_C.BCYAN}Dzień roku:  {_C.RESET}  {_C.BOLD}{yday}{_C.RESET}"
       f"  {_C.DIM}(zostało {days_left}){_C.RESET}\n\n")
    _w(f"  {_C.BOLD}{_C.BLUE}{'':4}{'Dzień':<5}  {'Data':<12}{'Dz':>3}{_C.RESET}\n")
    _w(f"  {_C.BLUE}{'─'*32}{_C.RESET}\n")
    for d in week_days:
        wi = d.weekday()
        is_today = d == now.date()
        is_we    = wi >= 5
        has_ev   = d in event_day_set
        day_col  = _C.YELLOW if is_we else _C.RESET
        mark     = f" {_C.MAGENTA}●{_C.RESET}" if has_ev else "  "
        prefix   = f"{_C.INV}{_C.BGREEN}" if is_today else day_col
        suffix   = _C.RESET
        num_col  = _C.DIM
        _w(f"  {prefix}{DAY_PL[wi]}{suffix}  "
           f"{prefix}{d.day:2d} {MON_PL_SHORT[d.month]} {d.year}{suffix}"
           f"{mark}  {num_col}{d.timetuple().tm_yday:3d}{_C.RESET}\n")
    _w("\n")
    _sys.stdout.flush()

# ─── _do_countdown ─────────────────────────────────────────────────────────────

def _do_countdown(date_str):
    try:
        target = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
        today  = _dt.date.today()
        delta  = (target - today).days
        if   delta > 0:  _w(f"\n  {_C.BGREEN}Do {target} pozostało: {_C.BOLD}{delta}{_C.RESET}{_C.BGREEN} dni{_C.RESET}\n\n")
        elif delta == 0: _w(f"\n  {_C.BYELLOW}To jest dzisiaj! 🎉{_C.RESET}\n\n")
        else:            _w(f"\n  {_C.DIM}{target} minęło {abs(delta)} dni temu.{_C.RESET}\n\n")
    except ValueError:
        _w(f"  {_C.RED}Zły format. Użyj: RRRR-MM-DD (np. 2025-12-31){_C.RESET}\n")
    _sys.stdout.flush()

# ─── import/export ─────────────────────────────────────────────────────────────

def _do_event_export(fmt, filename=None):
    if not filename:
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"events_export_{ts}.{fmt}"
    try:
        if fmt == "json":
            data = [{'date': str(e['date']), 'desc': e['desc']} for e in _EVENTS]
            with open(filename, "w", encoding="utf-8") as f:
                _json.dump(data, f, indent=2, ensure_ascii=False)
        else: # txt
            with open(filename, "w", encoding="utf-8") as f:
                for e in _EVENTS:
                    f.write(f"{e['date']}: {e['desc']}\n")
        _w(f"\n  {_C.BGREEN}✓ Eksport zapisany: {filename}{_C.RESET}\n\n")
        _sys.stdout.flush()
    except Exception as e:
        _w(f"\n  {_C.RED}✗ Błąd eksportu: {e}{_C.RESET}\n\n")

def _do_event_import(filename):
    if not _os.path.exists(filename):
        _w(f"\n  {_C.RED}✗ Plik nie istnieje: {filename}{_C.RESET}\n\n"); return
    try:
        added = 0
        skipped = 0
        # Zbiór istniejących wydarzeń do szybkiego sprawdzania duplikatów
        seen = {(e['date'], e['desc']) for e in _EVENTS}

        new_items = []
        if filename.endswith(".json"):
            with open(filename, "r", encoding="utf-8") as f:
                data = _json.load(f)
            if not isinstance(data, list):
                raise ValueError("Plik JSON musi zawierać listę wydarzeń")
            for i, item in enumerate(data):
                if not isinstance(item, dict) or 'date' not in item or 'desc' not in item:
                    raise ValueError(f"Błędny format rekordu #{i+1}")
                if not _re.match(r'^\d{4}-\d{2}-\d{2}$', str(item['date'])):
                    raise ValueError(f"Błędna data w rekordzie #{i+1}: {item['date']}")
                d    = _dt.datetime.strptime(item['date'], "%Y-%m-%d").date()
                desc = str(item['desc']).strip()
                new_items.append((d, desc, item.get('tags', [])))
        elif filename.endswith(".ics"):
            with open(filename, "r", encoding="utf-8") as f:
                content = _re.sub(r'\r?\n[ \t]', '', f.read())
            vevents = _re.findall(r'BEGIN:VEVENT(.*?)END:VEVENT', content, _re.DOTALL)
            for block in vevents:
                dt_m   = _re.search(r'DTSTART(?:;[^:]*)?:(\d{8})', block)
                summ_m = _re.search(r'SUMMARY:(.*)', block)
                if dt_m and summ_m:
                    d    = _dt.datetime.strptime(dt_m.group(1), "%Y%m%d").date()
                    desc = summ_m.group(1).strip().replace('\\n', '\n').replace('\\,', ',')
                    new_items.append((d, desc, []))
        else:  # txt
            with open(filename, "r", encoding="utf-8") as f:
                for lineno, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or ":" not in line:
                        continue
                    ds, desc = line.split(":", 1)
                    ds = ds.strip()
                    if not _re.match(r'^\d{4}-\d{2}-\d{2}$', ds):
                        raise ValueError(f"Błędna data w linii {lineno}: '{ds}'")
                    d = _dt.datetime.strptime(ds, "%Y-%m-%d").date()
                    new_items.append((d, desc.strip(), []))

        # Batch insert: O(n log n) zamiast O(n²) insort w pętli
        for d, desc, tags in new_items:
            if (d, desc) not in seen:
                _EVENTS.append({'date': d, 'desc': desc, 'tags': tags})
                seen.add((d, desc))
                added += 1
            else:
                skipped += 1
        _EVENTS.sort(key=lambda x: x['date'])
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Zaimportowano: {added} | Pominięto duplikaty: {skipped}{_C.RESET}\n\n")
        _sys.stdout.flush()
    except Exception as e:
        _w(f"\n  {_C.RED}✗ Błąd importu: {e}{_C.RESET}\n\n")

def _do_config_export(filename):
    """Eksportuje całą bazę (ustawienia, wydarzenia, imieniny, notatki, cykliczne) do pliku JSON."""
    try:
        data = {
            "settings":         _CONFIG,
            "events":           [{'date': str(e['date']), 'desc': e['desc'], 'tags': e.get('tags', [])} for e in _EVENTS],
            "personal_namedays": _PERSONAL_NAMEDAYS,
            "recurring":        _RECURRING,
            "color_config":     _COLOR_CONFIG,
            "notes":            _NOTES,
            "remind_config":    _REMIND_CONFIG,
        }
        with open(filename, "w", encoding="utf-8") as f:
            _json.dump(data, f, indent=2, ensure_ascii=False)
        _w(f"\n  {_C.BGREEN}✓ Konfiguracja wyeksportowana do: {filename}{_C.RESET}\n\n")
    except Exception as e:
        _w(f"\n  {_C.RED}✗ Błąd eksportu: {e}{_C.RESET}\n\n")

def _do_config_import(filename):
    """Importuje całą bazę z pliku JSON (nadpisuje obecną)."""
    if not _os.path.exists(filename):
        _w(f"\n  {_C.RED}✗ Plik nie istnieje: {filename}{_C.RESET}\n\n"); return
    try:
        with open(filename, "r", encoding="utf-8") as f:
            data = _json.load(f)
            
            # Walidacja struktury
            if not isinstance(data, dict):
                raise ValueError("Główny element musi być słownikiem")
            
            settings   = data.get("settings", {})
            p_namedays = data.get("personal_namedays", [])
            events     = data.get("events", [])

            if not isinstance(settings, dict):
                raise ValueError("Klucz 'settings' musi być słownikiem")
            if not isinstance(p_namedays, list):
                raise ValueError("Klucz 'personal_namedays' musi być listą")
            if not isinstance(events, list):
                raise ValueError("Klucz 'events' musi być listą")

            for i, item in enumerate(p_namedays):
                if not isinstance(item, dict) or "date" not in item or "name" not in item:
                    raise ValueError(f"Błędny format imienin #{i+1}")
                if not _re.match(r'^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$', item['date']):
                    raise ValueError(f"Błędna data imienin #{i+1} (wymagane MM-DD)")
            for i, item in enumerate(events):
                if not isinstance(item, dict) or "date" not in item or "desc" not in item:
                    raise ValueError(f"Błędny format wydarzenia #{i+1}")
                _dt.datetime.strptime(item['date'], "%Y-%m-%d")
            
            # Aplikowanie zmian tylko znanych kluczy (bez zanieczyszczenia _CONFIG)
            filtered_settings = {k: v for k, v in settings.items() if k in _KNOWN_CONFIG_KEYS}
            _CONFIG.update(filtered_settings)
            _PERSONAL_NAMEDAYS[:] = p_namedays
            _EVENTS.clear()
            for item in events:
                d = _dt.datetime.strptime(item['date'], "%Y-%m-%d").date()
                _bi.insort(_EVENTS, {'date': d, 'desc': item['desc']}, key=lambda x: x['date'])
            
            _apply_theme(_CONFIG.get("theme", "light"))
            _save_db()
            _w(f"\n  {_C.BGREEN}✓ Konfiguracja i dane zaimportowane pomyślnie.{_C.RESET}\n\n")
    except Exception as e:
        _w(f"\n  {_C.RED}✗ Błąd walidacji lub importu: {e}{_C.RESET}\n\n")

# ─── helpers: kolory per element i cykliczne ──────────────────────────────────

def _get_color(element, fallback=""):
    """Zwraca kolor dla elementu z _COLOR_CONFIG lub fallback z motywu."""
    return _COLOR_CONFIG.get(element, fallback)

def _recurring_occurrences(rec, from_date, to_date):
    """
    Generuje listę dat wystąpień wydarzenia cyklicznego w przedziale [from_date, to_date].
    rec: {'freq': 'yearly'|'monthly'|'weekly', 'start': 'RRRR-MM-DD', 'desc': str, 'end': str|None}
    """
    try:
        start = _dt.datetime.strptime(rec['start'], "%Y-%m-%d").date()
        end   = _dt.datetime.strptime(rec['end'],   "%Y-%m-%d").date() if rec.get('end') else None
        freq  = rec['freq']
        desc  = rec['desc']
    except (KeyError, ValueError):
        return []

    results = []
    if freq == 'weekly':
        # Przeskocz do pierwszego poniedziałku >= from_date z właściwym dniem tygodnia
        days_ahead = (start.weekday() - from_date.weekday()) % 7
        cur = from_date + _dt.timedelta(days=days_ahead)
        if cur < start:
            cur += _dt.timedelta(weeks=1)
        while cur <= to_date:
            if end and cur > end: break
            if cur >= start:
                results.append((cur, desc))
            cur += _dt.timedelta(weeks=1)

    elif freq == 'monthly':
        # Szukamy dnia miesiąca start.day w każdym miesiącu przedziału
        cur_year, cur_month = from_date.year, from_date.month
        end_year, end_month = to_date.year, to_date.month
        while (cur_year, cur_month) <= (end_year, end_month):
            try:
                d = _dt.date(cur_year, cur_month, start.day)
                if from_date <= d <= to_date and d >= start:
                    if not end or d <= end:
                        results.append((d, desc))
            except ValueError:
                pass  # np. 31 lutego
            cur_month += 1
            if cur_month > 12:
                cur_month = 1
                cur_year += 1

    elif freq == 'yearly':
        for yr in range(from_date.year, to_date.year + 1):
            try:
                d = _dt.date(yr, start.month, start.day)
                if from_date <= d <= to_date and d >= start:
                    if not end or d <= end:
                        results.append((d, desc))
            except ValueError:
                pass  # np. 29 lutego w roku nieprzestępnym

    return results

# ─── _do_event — zarządzanie wydarzeniami ──────────────────────────────────────

def _do_event(args):
    sub = args[0].lower() if args else ''

    if sub == "nameday":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal event nameday add|list|remove{_C.RESET}\n\n"); return
        cmd = args[1].lower()
        if cmd == "add":
            if len(args) < 4:
                _w(f"\n  {_C.RED}✗ Użycie: cal event nameday add <MM-DD> <imię>{_C.RESET}\n\n"); return
            date_str, name = args[2], " ".join(args[3:])
            if not _re.match(r'^(0[1-9]|1[0-2])-(0[1-9]|[12][0-9]|3[01])$', date_str):
                _w(f"\n  {_C.RED}✗ Format daty musi być MM-DD (np. 12-24){_C.RESET}\n\n"); return
            _PERSONAL_NAMEDAYS.append({'date': date_str, 'name': name})
            _PERSONAL_NAMEDAYS.sort(key=lambda x: x['date'])
            _save_db()
            _w(f"\n  {_C.BGREEN}✓ Dodano do kalendarza: {date_str} - {name}{_C.RESET}\n\n")
        elif cmd == "list":
            if not _PERSONAL_NAMEDAYS:
                _w(f"\n  {_C.DIM}(brak zapisanych imienin){_C.RESET}\n\n"); return
            _w(f"\n  {_C.BOLD}{_C.BCYAN}ID  Data   Imię/Opis{_C.RESET}\n")
            for i, e in enumerate(_PERSONAL_NAMEDAYS, 1):
                _w(f"  {_C.DIM}{i:<2}{_C.RESET}  {_C.BYELLOW}{e['date']}{_C.RESET}  {e['name']}\n")
            _w("\n")
        elif cmd in ("remove", "rm", "delete"):
            if len(args) < 3:
                _w(f"\n  {_C.RED}✗ Użycie: cal event nameday remove <nr>{_C.RESET}\n\n"); return
            try:
                idx = int(args[2]) - 1
                if 0 <= idx < len(_PERSONAL_NAMEDAYS):
                    removed = _PERSONAL_NAMEDAYS.pop(idx)
                    _save_db()
                    _w(f"\n  {_C.BGREEN}✓ Usunięto: {removed['date']} - {removed['name']}{_C.RESET}\n\n")
                else:
                    _w(f"\n  {_C.RED}✗ Nieprawidłowy numer ID.{_C.RESET}\n\n")
            except ValueError:
                _w(f"\n  {_C.RED}✗ Podaj poprawny numer.{_C.RESET}\n\n")
        return

    if sub in ("edit", "edytuj"):
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal event edit <nr> [RRRR-MM-DD] [opis]{_C.RESET}\n\n"); return
        try:
            idx = int(args[1]) - 1
            if not (0 <= idx < len(_EVENTS)):
                _w(f"\n  {_C.RED}✗ Nieprawidłowy numer ID.{_C.RESET}\n\n"); return
            rest = args[2:]
            if not rest:
                _w(f"\n  {_C.RED}✗ Podaj nową datę i/lub opis.{_C.RESET}\n\n"); return
            e = _EVENTS[idx]
            # Sprawdź czy pierwszy token to data
            new_date = e['date']
            new_desc = e['desc']
            if rest and _re.match(r'^\d{4}-\d{2}-\d{2}$', rest[0]):
                new_date = _dt.datetime.strptime(rest[0], "%Y-%m-%d").date()
                rest = rest[1:]
            if rest:
                new_desc = " ".join(rest)
            old_tags = e.get('tags', [])
            _EVENTS.pop(idx)
            _bi.insort(_EVENTS, {'date': new_date, 'desc': new_desc, 'tags': old_tags}, key=lambda x: x['date'])
            _save_db()
            _w(f"\n  {_C.BGREEN}✓ Zaktualizowano: {new_date} — {new_desc}{_C.RESET}\n\n")
        except ValueError:
            _w(f"\n  {_C.RED}✗ Nieprawidłowy format daty lub numeru.{_C.RESET}\n\n")
        return

    if sub == "add":
        if len(args) < 3:
            _w(f"\n  {_C.RED}✗ Użycie: cal event add <RRRR-MM-DD> <opis>{_C.RESET}\n\n")
            return
        date_str = args[1]
        desc = " ".join(args[2:])
        try:
            event_date = _dt.datetime.strptime(date_str, "%Y-%m-%d").date()
            # Użycie bisect.insort utrzymuje listę posortowaną w O(n) zamiast O(n log n)
            _bi.insort(_EVENTS, {'date': event_date, 'desc': desc}, key=lambda x: x['date'])
            _save_db()
            _w(f"\n  {_C.BGREEN}✓ Dodano wydarzenie: {event_date} - {desc}{_C.RESET}\n\n")
        except ValueError:
            _w(f"\n  {_C.RED}✗ Nieprawidłowy format daty. Użyj: RRRR-MM-DD{_C.RESET}\n\n")
        return

    if sub == "export":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal event export <json|txt|ics> [plik]{_C.RESET}\n\n"); return
        fmt = args[1].lower()
        fname = args[2] if len(args) > 2 else None
        if fmt == "ics":
            _do_export_ics([fname] if fname else []); return
        _do_event_export(fmt, fname); return

    if sub == "import":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal event import <plik>{_C.RESET}\n\n"); return
        _do_event_import(args[1]); return

    if sub == "list":
        if not _EVENTS:
            _w(f"\n  {_C.DIM}(brak wydarzeń){_C.RESET}\n\n")
            return
        today = _dt.date.today()
        _w(f"\n  {_C.BOLD}{_C.BCYAN}ID  Data        Opis{_C.RESET}\n")
        _w(f"  {_C.BLUE}{'─'*56}{_C.RESET}\n")
        for i, event in enumerate(_EVENTS, 1):
            delta = (event['date'] - today).days
            if   delta == 0: when = f" {_C.BGREEN}dziś{_C.RESET}"
            elif delta > 0:  when = f" {_C.DIM}+{delta}d{_C.RESET}"
            else:            when = f" {_C.DIM}{delta}d{_C.RESET}"
            desc = event['desc']
            if len(desc) > 38: desc = desc[:37] + "…"
            tags_str = ""
            if event.get('tags'):
                tags_str = "  " + " ".join(f"{_C.CYAN}#{t}{_C.RESET}" for t in event['tags'])
            _w(f"  {_C.DIM}{i:<3}{_C.RESET}{_C.BYELLOW}{event['date']}{_C.RESET}  {desc}{tags_str}{when}\n")
        _w("\n")
        return

    if sub in ("remove", "rm", "delete"):
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal event remove <numer>{_C.RESET}\n\n")
            return
        try:
            idx = int(args[1]) - 1
            if 0 <= idx < len(_EVENTS):
                removed = _EVENTS.pop(idx)
                _save_db()
                _w(f"\n  {_C.BGREEN}✓ Usunięto: {removed['date']} - {removed['desc']}{_C.RESET}\n\n")
            else:
                _w(f"\n  {_C.RED}✗ Nieprawidłowy numer ID.{_C.RESET}\n\n")
        except ValueError:
            _w(f"\n  {_C.RED}✗ Podaj poprawny numer.{_C.RESET}\n\n")
        return

    if sub == "clear":
        _EVENTS.clear()
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Usunięto wszystkie wydarzenia.{_C.RESET}\n\n")
        return
    
    _w(f"\n  {_C.RED}✗ Nieznana subkomenda: cal event {sub}{_C.RESET}\n")
    _w(f"  {_C.DIM}Dostępne: add | list | edit | remove | clear | export | import | nameday{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_config ────────────────────────────────────────────────────────────────

def _do_config(args):
    """Zarządzanie konfiguracją modułu."""
    if not args:
        _w(f"\n  {_C.BCYAN}Aktualna konfiguracja:{_C.RESET}\n")
        _w(f"  {_C.DIM}Interwał powiadomień: {_C.RESET}{_C.BOLD}{_CONFIG.get('interval', 60)} min{_C.RESET}\n")
        _w(f"  {_C.DIM}Motyw kolorystyczny:  {_C.RESET}{_C.BOLD}{_CONFIG.get('theme', 'light')}{_C.RESET}\n")
        _w(f"  {_C.DIM}Miasto (pogoda):      {_C.RESET}{_C.BOLD}{_CONFIG.get('city') or 'automatyczne'}{_C.RESET}\n")
        last = _CONFIG.get('last_notified')
        last_disp = last.replace('T', ' ')[:19] if last else "brak"
        _w(f"  {_C.DIM}Ostatnie wysłane:     {_C.RESET}{_C.BOLD}{last_disp}{_C.RESET}\n")
        if _COLOR_CONFIG:
            _w(f"  {_C.DIM}Kolory per element:   {_C.RESET}")
            _w("  ".join(f"{k}={v}■{_C.RESET}" for k, v in _COLOR_CONFIG.items()) + "\n")
        remind_count = len(_REMIND_CONFIG)
        if remind_count:
            _w(f"  {_C.DIM}Aktywne przypomnienia:{_C.RESET}{_C.BOLD} {remind_count}{_C.RESET}\n")
        _w("\n")
        _sys.stdout.flush()
        return

    sub = args[0].lower()
    if sub == "interval":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal config interval <minuty>{_C.RESET}\n\n")
        else:
            try:
                val = int(args[1])
                if val < 1: raise ValueError
                _CONFIG["interval"] = val
                _save_db()
                _w(f"\n  {_C.BGREEN}✓ Interwał powiadomień ustawiony na {val} min.{_C.RESET}\n\n")
            except ValueError:
                _w(f"\n  {_C.RED}✗ Podaj poprawną liczbę dodatnią (minuty).{_C.RESET}\n\n")
    elif sub == "theme":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal config theme <light|dark>{_C.RESET}\n\n")
        else:
            theme_name = args[1].lower()
            if theme_name in _THEMES:
                _apply_theme(theme_name)
                _save_db()
                _w(f"\n  {_C.BGREEN}✓ Motyw został zmieniony na: {theme_name}{_C.RESET}\n\n")
            else:
                _w(f"\n  {_C.RED}✗ Nieznany motyw. Dostępne: light, dark{_C.RESET}\n\n")
    elif sub == "city":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal config city <nazwa_miasta>{_C.RESET}\n\n")
        else:
            new_city = " ".join(args[1:])
            _CONFIG["city"] = new_city
            _save_db()
            # Wymuszamy odświeżenie pogody przez usunięcie cache
            _CACHE_WEATHER["text"] = None
            if _os.path.exists(_WEATHER_CACHE_FILE):
                try: _os.remove(_WEATHER_CACHE_FILE)
                except: pass
            _w(f"\n  {_C.BGREEN}✓ Miasto dla prognozy ustawione na: {new_city}{_C.RESET}\n\n")
    elif sub == "color":
        _do_config_color(args[1:])
    elif sub == "export":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal config export <plik.json>{_C.RESET}\n\n")
        else:
            _do_config_export(args[1])
    elif sub == "import":
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal config import <plik.json>{_C.RESET}\n\n")
        else:
            _do_config_import(args[1])
    else:
        _w(f"\n  {_C.RED}✗ Nieznana opcja: {sub}{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_recurring ────────────────────────────────────────────────────────────

_FREQ_LABELS = {"yearly": "co rok", "monthly": "co miesiąc", "weekly": "co tydzień"}
_FREQ_VALID  = set(_FREQ_LABELS)

def _do_recurring(args):
    """Zarządzanie wydarzeniami cyklicznymi."""
    sub = args[0].lower() if args else ''

    if sub == "add":
        # cal recurring add <yearly|monthly|weekly> <RRRR-MM-DD> [end RRRR-MM-DD] <opis>
        if len(args) < 4:
            _w(f"\n  {_C.RED}✗ Użycie: cal recurring add <yearly|monthly|weekly> <RRRR-MM-DD> [end RRRR-MM-DD] <opis>{_C.RESET}\n\n")
            return
        freq = args[1].lower()
        if freq not in _FREQ_VALID:
            _w(f"\n  {_C.RED}✗ Częstotliwość: yearly | monthly | weekly{_C.RESET}\n\n"); return
        try:
            start_date = _dt.datetime.strptime(args[2], "%Y-%m-%d").date()
        except ValueError:
            _w(f"\n  {_C.RED}✗ Nieprawidłowa data startowa. Użyj: RRRR-MM-DD{_C.RESET}\n\n"); return

        rest = args[3:]
        end_date = None
        if rest and rest[0].lower() == "end":
            if len(rest) < 2:
                _w(f"\n  {_C.RED}✗ Brakuje daty końcowej po 'end'.{_C.RESET}\n\n"); return
            try:
                end_date = _dt.datetime.strptime(rest[1], "%Y-%m-%d").date()
                rest = rest[2:]
            except ValueError:
                _w(f"\n  {_C.RED}✗ Nieprawidłowa data końcowa. Użyj: RRRR-MM-DD{_C.RESET}\n\n"); return

        if not rest:
            _w(f"\n  {_C.RED}✗ Podaj opis wydarzenia.{_C.RESET}\n\n"); return
        desc = " ".join(rest)

        _RECURRING.append({
            "freq":  freq,
            "start": str(start_date),
            "end":   str(end_date) if end_date else None,
            "desc":  desc,
        })
        _save_db()
        label = _FREQ_LABELS[freq]
        end_info = f" (do {end_date})" if end_date else ""
        _w(f"\n  {_C.BGREEN}✓ Dodano cykliczne [{label}] od {start_date}{end_info}: {desc}{_C.RESET}\n\n")

    elif sub == "list":
        if not _RECURRING:
            _w(f"\n  {_C.DIM}(brak wydarzeń cyklicznych){_C.RESET}\n\n"); return
        today = _dt.date.today()
        _w(f"\n  {_C.BOLD}{_C.BCYAN}ID  Częst.       Start       Koniec      Opis{_C.RESET}\n")
        _w(f"  {_C.BLUE}{'─'*60}{_C.RESET}\n")
        for i, r in enumerate(_RECURRING, 1):
            freq_lbl = _FREQ_LABELS.get(r.get('freq',''), r.get('freq',''))
            end_str  = r.get('end') or '—'
            # Najbliższe wystąpienie
            occ = _recurring_occurrences(r, today, today + _dt.timedelta(days=365))
            next_occ = f"  {_C.DIM}→ {occ[0][0]}{_C.RESET}" if occ else f"  {_C.DIM}(brak w roku){_C.RESET}"
            _w(f"  {_C.DIM}{i:<2}{_C.RESET}  {_C.BYELLOW}{freq_lbl:<12}{_C.RESET}"
               f"{r.get('start',''):<12}{end_str:<12}{r.get('desc','')}{next_occ}\n")
        _w("\n")

    elif sub in ("remove", "rm", "delete"):
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal recurring remove <nr>{_C.RESET}\n\n"); return
        try:
            idx = int(args[1]) - 1
            if 0 <= idx < len(_RECURRING):
                removed = _RECURRING.pop(idx)
                _save_db()
                _w(f"\n  {_C.BGREEN}✓ Usunięto: [{removed['freq']}] {removed['desc']}{_C.RESET}\n\n")
            else:
                _w(f"\n  {_C.RED}✗ Nieprawidłowy numer ID.{_C.RESET}\n\n")
        except ValueError:
            _w(f"\n  {_C.RED}✗ Podaj poprawny numer.{_C.RESET}\n\n")

    elif sub == "show":
        # Pokaż wystąpienia w ciągu N dni
        try:    days = int(args[1]) if len(args) > 1 else 30
        except: days = 30
        today = _dt.date.today()
        end   = today + _dt.timedelta(days=days)
        hits  = []
        for r in _RECURRING:
            for d, desc in _recurring_occurrences(r, today, end):
                hits.append((d, r['freq'], desc))
        hits.sort()
        if not hits:
            _w(f"\n  {_C.DIM}Brak cyklicznych w ciągu {days} dni.{_C.RESET}\n\n"); return
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Cykliczne — najbliższe {days} dni:{_C.RESET}\n\n")
        for d, freq, desc in hits:
            delta = (d - today).days
            when = f"{_C.BGREEN}dziś{_C.RESET}" if delta == 0 else f"{_C.DIM}za {delta} dni{_C.RESET}"
            _w(f"  {_C.BYELLOW}{d}{_C.RESET}  {_C.DIM}[{_FREQ_LABELS.get(freq,freq)}]{_C.RESET}  {desc}  {when}\n")
        _w("\n")

    elif sub == "clear":
        _RECURRING.clear()
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Usunięto wszystkie wydarzenia cykliczne.{_C.RESET}\n\n")

    else:
        _w(f"\n  {_C.RED}✗ Użycie: cal recurring add|list|remove|show|clear{_C.RESET}\n\n")
    _sys.stdout.flush()



def get_upcoming_events(days=7):
    """Zwraca listę nadchodzących wydarzeń (domyślnie do 7 dni od dzisiaj)."""
    today = _dt.date.today()
    upcoming = []
    start_idx = _bi.bisect_left(_EVENTS, today, key=lambda x: x['date'])
    for i in range(start_idx, len(_EVENTS)):
        event = _EVENTS[i]
        if (event['date'] - today).days <= days:
            upcoming.append((event['date'], event['desc']))
    return upcoming





# ─── _do_search ───────────────────────────────────────────────────────────────

def _do_search(args):
    """Szuka frazy w opisach i datach wydarzeń oraz imieninach."""
    if not args:
        _w(f"\n  {_C.RED}✗ Użycie: cal search <fraza>{_C.RESET}\n\n"); return
    phrase = " ".join(args).lower()
    today  = _dt.date.today()

    hits_ev = [e for e in _EVENTS if phrase in e['desc'].lower() or phrase in str(e['date'])]
    hits_nd = [n for n in _PERSONAL_NAMEDAYS if phrase in n['name'].lower() or phrase in n['date']]

    if not hits_ev and not hits_nd:
        _w(f"\n  {_C.DIM}Brak wyników dla: {_C.RESET}{_C.BOLD}\"{' '.join(args)}\"{_C.RESET}\n\n")
        return

    _w(f"\n  {_C.BOLD}{_C.BCYAN}Wyniki dla: \"{' '.join(args)}\"{_C.RESET}\n\n")

    if hits_ev:
        _w(f"  {_C.BOLD}{_C.BLUE}Wydarzenia ({len(hits_ev)}):{_C.RESET}\n")
        for i, e in enumerate(hits_ev, 1):
            delta = (e['date'] - today).days
            if   delta > 0:  when = f"{_C.DIM}(za {delta} dni){_C.RESET}"
            elif delta == 0: when = f"{_C.BGREEN}(dziś){_C.RESET}"
            else:            when = f"{_C.DIM}({abs(delta)} dni temu){_C.RESET}"
            # Podświetl frazę w opisie
            desc_hl = _re.sub(f"(?i)({_re.escape(' '.join(args))})",
                               f"{_C.BYELLOW}\\1{_C.RESET}", e['desc'])
            _w(f"  {_C.DIM}{i:<2}{_C.RESET}  {_C.BYELLOW}{e['date']}{_C.RESET}  {desc_hl}  {when}\n")
        _w("\n")

    if hits_nd:
        _w(f"  {_C.BOLD}{_C.BLUE}Imieniny ({len(hits_nd)}):{_C.RESET}\n")
        for n in hits_nd:
            name_hl = _re.sub(f"(?i)({_re.escape(' '.join(args))})",
                               f"{_C.BYELLOW}\\1{_C.RESET}", n['name'])
            _w(f"  {_C.YELLOW}{n['date']}{_C.RESET}  {name_hl}\n")
        _w("\n")

    _sys.stdout.flush()

# ─── _do_agenda ───────────────────────────────────────────────────────────────

def _do_agenda(args):
    """Wyświetla agendę: dni z wydarzeniami w ciągu N dni od dziś."""
    try:    days = int(args[0]) if args else 30
    except: days = 30
    if days < 1 or days > 3650:
        _w(f"\n  {_C.RED}✗ Zakres: 1–3650 dni.{_C.RESET}\n\n"); return

    today = _dt.date.today()
    end   = today + _dt.timedelta(days=days)

    # Zbierz wydarzenia i imieniny w przedziale
    ev_in_range = [e for e in _EVENTS if today <= e['date'] <= end]

    # Grupuj wydarzenia po dacie
    by_date = {}
    for e in ev_in_range:
        by_date.setdefault(e['date'], []).append(e['desc'])

    # Dodaj imieniny do odpowiednich dat
    for nd in _PERSONAL_NAMEDAYS:
        mm, dd = nd['date'].split('-')
        # Szukamy wystąpień tej daty MM-DD w przedziale
        for yr in {today.year, today.year + 1}:
            try:
                d = _dt.date(yr, int(mm), int(dd))
            except ValueError:
                continue
            if today <= d <= end:
                by_date.setdefault(d, []).append(f"🎂 Imieniny: {nd['name']}")

    if not by_date:
        _w(f"\n  {_C.DIM}Brak wydarzeń w ciągu {days} dni.{_C.RESET}\n\n"); return

    DAY_PL = ["Pn","Wt","Śr","Cz","Pt","Sb","Nd"]
    MON_PL = ["","Sty","Lut","Mar","Kwi","Maj","Cze","Lip","Sie","Wrz","Paź","Lis","Gru"]

    _w(f"\n  {_C.BOLD}{_C.BCYAN}Agenda — najbliższe {days} dni{_C.RESET}"
       f"  {_C.DIM}({today} → {end}){_C.RESET}\n\n")

    for date in sorted(by_date):
        delta = (date - today).days
        is_today   = delta == 0
        is_weekend = date.weekday() >= 5
        day_lbl    = DAY_PL[date.weekday()]
        date_str   = f"{date.day:2d} {MON_PL[date.month]} {date.year}"

        if is_today:
            hdr_col = f"{_C.INV}{_C.BGREEN}"
            tag     = f"  {_C.RESET}{_C.BGREEN}← dziś{_C.RESET}"
        elif delta <= 3:
            hdr_col = _C.BYELLOW
            tag     = f"  {_C.DIM}za {delta} {'dzień' if delta==1 else 'dni'}{_C.RESET}"
        elif is_weekend:
            hdr_col = _C.YELLOW
            tag     = ""
        else:
            hdr_col = _C.BWHITE
            tag     = ""

        _w(f"  {hdr_col}{day_lbl} {date_str}{_C.RESET}{tag}\n")
        for desc in by_date[date]:
            _w(f"    {_C.CYAN}•{_C.RESET} {desc}\n")
        _w("\n")

    _sys.stdout.flush()

# ─── _do_stats ────────────────────────────────────────────────────────────────

def _do_stats():
    """Wyświetla statystyki wydarzeń."""
    today   = _dt.date.today()
    total   = len(_EVENTS)

    if total == 0:
        _w(f"\n  {_C.DIM}Brak wydarzeń w bazie.{_C.RESET}\n\n"); return

    # Jedna iteracja przez _EVENTS zamiast 5 osobnych list comprehension
    week_end  = today + _dt.timedelta(days=7)
    n_past = n_today = n_future = n_week = n_month = 0
    mon_counts = _Counter()
    yr_counts  = _Counter()
    nearest = most_recent = None

    for e in _EVENTS:
        d = e['date']
        mon_counts[d.month] += 1
        yr_counts[d.year]   += 1
        if d < today:
            n_past += 1
            most_recent = e          # _EVENTS posortowane — ostatni miniony
        elif d == today:
            n_today += 1
        else:
            n_future += 1
            if nearest is None:
                nearest = e          # pierwszy przyszły
        if today <= d <= week_end:
            n_week += 1
        if d.year == today.year and d.month == today.month:
            n_month += 1

    MON_PL = ["","Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec",
               "Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"]
    busiest_m  = mon_counts.most_common(1)[0] if mon_counts else None
    busiest_yr = yr_counts.most_common(1)[0]  if yr_counts  else None

    _w(f"\n  {_C.BOLD}{_C.BCYAN}╔══════════════════════════════════╗{_C.RESET}\n")
    _w(f"  {_C.BOLD}{_C.BCYAN}║   📊  Statystyki kalendarza       ║{_C.RESET}\n")
    _w(f"  {_C.BOLD}{_C.BCYAN}╚══════════════════════════════════╝{_C.RESET}\n\n")

    def _stat(label, value, vc=None):
        vc = vc or _C.BWHITE
        _w(f"  {_C.BLUE}{label:<26}{_C.RESET}{vc}{value}{_C.RESET}\n")

    _stat("Wszystkich wydarzeń:",    str(total))
    _stat("Minione:",                str(n_past),   _C.DIM)
    _stat("Dziś:",                   str(n_today),  _C.BGREEN if n_today else _C.DIM)
    _stat("Przyszłe:",               str(n_future), _C.BYELLOW)
    _w(f"  {_C.BLUE}{'─'*34}{_C.RESET}\n")
    _stat("W tym tygodniu (7 dni):", str(n_week))
    _stat("W tym miesiącu:",         str(n_month))
    _w(f"  {_C.BLUE}{'─'*34}{_C.RESET}\n")

    if nearest:
        delta = (nearest['date'] - today).days
        desc  = nearest['desc']
        _stat("Najbliższe:",
              f"{nearest['date']}  {_C.DIM}{desc[:28]}{'…' if len(desc)>28 else ''}{_C.RESET}"
              f"  {_C.BGREEN}za {delta} {'dzień' if delta==1 else 'dni'}{_C.RESET}")
    if most_recent:
        delta = (today - most_recent['date']).days
        desc  = most_recent['desc']
        _stat("Ostatnie minione:",
              f"{most_recent['date']}  {_C.DIM}{desc[:28]}{'…' if len(desc)>28 else ''}{_C.RESET}"
              f"  {_C.DIM}{delta} dni temu{_C.RESET}")

    if busiest_m:
        _stat("Najaktywniejszy mies.:", f"{MON_PL[busiest_m[0]]}  {_C.DIM}({busiest_m[1]} wydarzeń){_C.RESET}")
    if busiest_yr:
        _stat("Najaktywniejszy rok:",   f"{busiest_yr[0]}  {_C.DIM}({busiest_yr[1]} wydarzeń){_C.RESET}")

    _stat("Zapisanych imienin:", str(len(_PERSONAL_NAMEDAYS)))
    _w("\n")
    _sys.stdout.flush()

# ─── _do_diff ─────────────────────────────────────────────────────────────────

def _do_diff(args):
    """Oblicza różnicę między dwiema datami."""
    if len(args) < 2:
        _w(f"\n  {_C.RED}✗ Użycie: cal diff <RRRR-MM-DD> <RRRR-MM-DD>{_C.RESET}\n\n"); return
    try:
        d1 = _dt.datetime.strptime(args[0], "%Y-%m-%d").date()
        d2 = _dt.datetime.strptime(args[1], "%Y-%m-%d").date()
    except ValueError:
        _w(f"\n  {_C.RED}✗ Nieprawidłowy format daty. Użyj: RRRR-MM-DD{_C.RESET}\n\n"); return

    if d1 > d2:
        d1, d2 = d2, d1
        swapped = True
    else:
        swapped = False

    delta      = (d2 - d1).days
    weeks, rem = divmod(delta, 7)
    months     = (d2.year - d1.year) * 12 + (d2.month - d1.month)
    years      = d2.year - d1.year
    if (d2.month, d2.day) < (d1.month, d1.day):
        years -= 1
    if d2.day < d1.day:
        months -= 1

    # Dni robocze (Pn–Pt, bez weekendów; bez świąt — wymagałoby bazy świąt)
    workdays = sum(1 for i in range(delta) if (d1 + _dt.timedelta(days=i)).weekday() < 5)

    MON_PL = ["","Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec",
               "Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"]
    DAY_PL = ["poniedziałek","wtorek","środa","czwartek","piątek","sobota","niedziela"]

    dir_str = f"{_C.DIM}(kolejność zamieniona){_C.RESET}" if swapped else ""
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Różnica dat{_C.RESET}  {dir_str}\n\n")
    _w(f"  {_C.BLUE}Od:{_C.RESET}  {_C.BWHITE}{d1}{_C.RESET}  {_C.DIM}{DAY_PL[d1.weekday()]}, {MON_PL[d1.month]} {d1.year}{_C.RESET}\n")
    _w(f"  {_C.BLUE}Do:{_C.RESET}  {_C.BWHITE}{d2}{_C.RESET}  {_C.DIM}{DAY_PL[d2.weekday()]}, {MON_PL[d2.month]} {d2.year}{_C.RESET}\n")
    _w(f"  {_C.BLUE}{'─'*38}{_C.RESET}\n")

    def _drow(label, val):
        _w(f"  {_C.BLUE}{label:<22}{_C.RESET}{_C.BWHITE}{val}{_C.RESET}\n")

    _drow("Łącznie dni:",        str(delta))
    _drow("Tygodnie + dni:",     f"{weeks} tyg. + {rem} dni")
    if months > 0:
        _drow("Przybliżone miesiące:", str(months))
    if years > 0:
        _drow("Przybliżone lata:",    str(years))
    _drow("Dni roboczych:",      str(workdays))
    _drow("Dni weekendowych:",   str(delta - workdays))

    # Czy obejmuje przełom roku
    if d1.year != d2.year:
        _w(f"  {_C.DIM}Obejmuje {d2.year - d1.year} przełom{'y' if d2.year-d1.year>1 else ''} roku.{_C.RESET}\n")
    _w("\n")
    _sys.stdout.flush()

# ─── _do_export_ics ───────────────────────────────────────────────────────────

def _do_export_ics(args):
    """Eksportuje wydarzenia i cykliczne do pliku .ics (iCalendar)."""
    filename = args[0] if args else None
    if not filename:
        ts = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"calendar_export_{ts}.ics"

    def _ics_escape(s):
        return s.replace('\\', '\\\\').replace(';', '\\;').replace(',', '\\,').replace('\n', '\\n')

    def _ics_dt(d):
        return d.strftime("%Y%m%d")

    try:
        lines = [
            "BEGIN:VCALENDAR",
            "VERSION:2.0",
            "PRODID:-//polsoft.ITS Group//CrossTerm Calendar//PL",
            "CALSCALE:GREGORIAN",
            "METHOD:PUBLISH",
        ]

        uid_base = _dt.datetime.now().strftime("%Y%m%d%H%M%S")

        # Jednorazowe wydarzenia
        for i, e in enumerate(_EVENTS):
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid_base}-ev{i}@crossterm",
                f"DTSTART;VALUE=DATE:{_ics_dt(e['date'])}",
                f"DTEND;VALUE=DATE:{_ics_dt(e['date'] + _dt.timedelta(days=1))}",
                f"SUMMARY:{_ics_escape(e['desc'])}",
                f"DTSTAMP:{_dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                "END:VEVENT",
            ]

        # Imieniny osobiste
        for i, nd in enumerate(_PERSONAL_NAMEDAYS):
            mm, dd = nd['date'].split('-')
            yr = _dt.date.today().year
            try:
                d = _dt.date(yr, int(mm), int(dd))
            except ValueError:
                continue
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid_base}-nd{i}@crossterm",
                f"DTSTART;VALUE=DATE:{_ics_dt(d)}",
                f"DTEND;VALUE=DATE:{_ics_dt(d + _dt.timedelta(days=1))}",
                f"SUMMARY:Imieniny: {_ics_escape(nd['name'])}",
                f"DTSTAMP:{_dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                "RRULE:FREQ=YEARLY",
                "END:VEVENT",
            ]

        # Cykliczne
        _freq_ics = {"yearly": "YEARLY", "monthly": "MONTHLY", "weekly": "WEEKLY"}
        for i, r in enumerate(_RECURRING):
            try:
                start = _dt.datetime.strptime(r['start'], "%Y-%m-%d").date()
            except ValueError:
                continue
            freq_ics = _freq_ics.get(r.get('freq', ''), 'YEARLY')
            rrule = f"RRULE:FREQ={freq_ics}"
            if r.get('end'):
                try:
                    end_d = _dt.datetime.strptime(r['end'], "%Y-%m-%d").date()
                    rrule += f";UNTIL={_ics_dt(end_d)}T000000Z"
                except ValueError:
                    pass
            lines += [
                "BEGIN:VEVENT",
                f"UID:{uid_base}-rec{i}@crossterm",
                f"DTSTART;VALUE=DATE:{_ics_dt(start)}",
                f"DTEND;VALUE=DATE:{_ics_dt(start + _dt.timedelta(days=1))}",
                f"SUMMARY:{_ics_escape(r['desc'])}",
                f"DTSTAMP:{_dt.datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')}",
                rrule,
                "END:VEVENT",
            ]

        lines.append("END:VCALENDAR")

        with open(filename, "w", encoding="utf-8", newline="\r\n") as f:
            f.write("\r\n".join(lines) + "\r\n")

        total = len(_EVENTS) + len(_PERSONAL_NAMEDAYS) + len(_RECURRING)
        _w(f"\n  {_C.BGREEN}✓ Wyeksportowano {total} rekordów do: {filename}{_C.RESET}\n\n")
    except Exception as e:
        _w(f"\n  {_C.RED}✗ Błąd eksportu ICS: {e}{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_config_color ─────────────────────────────────────────────────────────

def _do_config_color(args):
    """Konfiguracja kolorów per element kalendarza."""
    _ANSI_COLORS = {
        "czarny": "30", "czerwony": "31", "zielony": "32", "żółty": "33",
        "niebieski": "34", "magenta": "35", "cyan": "36", "biały": "37",
        "jasnyczarny": "90", "jasnyczerwony": "91", "jasnyzielony": "92",
        "jasnyżółty": "93", "jasnyniebieski": "94", "jasnymagenta": "95",
        "jasnycyan": "96", "jasnybiały": "97",
    }
    _ANSI_ATTRS = {
        "bold": "1", "dim": "2", "underline": "4", "inv": "7", "reset": "0",
    }

    if not args or args[0].lower() == "list":
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Elementy kolorów kalendarza:{_C.RESET}\n\n")
        for key, (label, default) in _COLOR_ELEMENTS.items():
            cur = _COLOR_CONFIG.get(key, "")
            sample = f"{cur or default}■■■{_C.RESET}"
            src    = f"{_C.DIM}(własny){_C.RESET}" if cur else f"{_C.DIM}(motyw){_C.RESET}"
            _w(f"  {_C.BYELLOW}{key:<10}{_C.RESET}  {sample}  {label}  {src}\n")
        _w(f"\n  {_C.DIM}Użycie: cal config color <element> <kolor> [bold|dim|underline|inv]{_C.RESET}\n")
        _w(f"  {_C.DIM}Kolory: czarny czerwony zielony żółty niebieski magenta cyan biały (+ jasny*){_C.RESET}\n")
        _w(f"  {_C.DIM}Reset:  cal config color <element> reset{_C.RESET}\n\n")
        _sys.stdout.flush()
        return

    if len(args) < 2:
        _w(f"\n  {_C.RED}✗ Użycie: cal config color <element> <kolor|reset> [atrybuty]{_C.RESET}\n\n"); return

    element = args[0].lower()
    if element not in _COLOR_ELEMENTS:
        _w(f"\n  {_C.RED}✗ Nieznany element: {element}. Dostępne: {', '.join(_COLOR_ELEMENTS)}{_C.RESET}\n\n"); return

    if args[1].lower() == "reset":
        _COLOR_CONFIG.pop(element, None)
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Kolor '{element}' zresetowany do domyślnego motywu.{_C.RESET}\n\n")
        _sys.stdout.flush()
        return

    # Buduj sekwencję ANSI z podanych tokenów
    codes = []
    for token in args[1:]:
        t = token.lower()
        if t in _ANSI_COLORS:
            codes.append(_ANSI_COLORS[t])
        elif t in _ANSI_ATTRS:
            codes.append(_ANSI_ATTRS[t])
        else:
            _w(f"\n  {_C.RED}✗ Nieznany kolor/atrybut: '{token}'{_C.RESET}\n\n"); return

    if not codes:
        _w(f"\n  {_C.RED}✗ Podaj kolor lub 'reset'.{_C.RESET}\n\n"); return

    ansi_seq = f"\x1b[{';'.join(codes)}m"
    _COLOR_CONFIG[element] = ansi_seq
    _save_db()
    sample = f"{ansi_seq}■■■{_C.RESET}"
    _w(f"\n  {_C.BGREEN}✓ Kolor '{element}' ustawiony: {sample}{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_remind ───────────────────────────────────────────────────────────────

def _remind_key(e):
    """Stabilny klucz dla przypomnienia — niezależny od pozycji na liście."""
    return f"{e['date']}|{e['desc']}"

def _do_remind(args):
    """Zarządzanie przypomnieniami i ich wysyłanie przy on_load."""
    sub = args[0].lower() if args else 'list'

    if sub == "set":
        if len(args) < 3:
            _w(f"\n  {_C.RED}✗ Użycie: cal remind set <nr_wydarzenia> <dni_przed>{_C.RESET}\n\n"); return
        try:
            idx  = int(args[1]) - 1
            days = int(args[2])
            if not (0 <= idx < len(_EVENTS)): raise IndexError
            if days < 0: raise ValueError
        except (ValueError, IndexError):
            _w(f"\n  {_C.RED}✗ Nieprawidłowy numer lub liczba dni.{_C.RESET}\n\n"); return
        e   = _EVENTS[idx]
        key = _remind_key(e)
        _REMIND_CONFIG[key] = days
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Przypomnienie ustawione: {e['date']} — {e['desc']}  "
           f"({days} dni przed){_C.RESET}\n\n")

    elif sub in ("remove", "rm"):
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal remind remove <nr_wydarzenia>{_C.RESET}\n\n"); return
        try:
            idx = int(args[1]) - 1
            if not (0 <= idx < len(_EVENTS)): raise IndexError
        except (ValueError, IndexError):
            _w(f"\n  {_C.RED}✗ Nieprawidłowy numer.{_C.RESET}\n\n"); return
        key = _remind_key(_EVENTS[idx])
        if key in _REMIND_CONFIG:
            _REMIND_CONFIG.pop(key)
            _save_db()
            _w(f"\n  {_C.BGREEN}✓ Usunięto przypomnienie #{int(args[1])}.{_C.RESET}\n\n")
        else:
            _w(f"\n  {_C.RED}✗ Brak przypomnienia dla #{args[1]}.{_C.RESET}\n\n")

    elif sub == "check":
        _do_remind_check(verbose=True)

    else:  # list
        if not _REMIND_CONFIG:
            _w(f"\n  {_C.DIM}(brak przypomnień){_C.RESET}\n\n"); return
        today = _dt.date.today()
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Przypomnienia:{_C.RESET}\n\n")
        for e in _EVENTS:
            key  = _remind_key(e)
            days = _REMIND_CONFIG.get(key)
            if days is None: continue
            delta = (e['date'] - today).days
            warn  = f"  {_C.BGREEN}← aktywne!{_C.RESET}" if 0 <= delta <= days else ""
            _w(f"  {_C.BYELLOW}{e['date']}{_C.RESET}  {e['desc']}  "
               f"{_C.DIM}[{days} dni przed]{_C.RESET}{warn}\n")
        _w("\n")
    _sys.stdout.flush()

def _do_remind_check(verbose=False):
    """Sprawdza przypomnienia i wysyła powiadomienia. Wywoływane przez on_load."""
    today = _dt.date.today()
    fired = []
    for e in _EVENTS:
        key  = _remind_key(e)
        days = _REMIND_CONFIG.get(key)
        if days is None: continue
        try:
            delta = (e['date'] - today).days
            if 0 <= delta <= days:
                fired.append((delta, e['date'], e['desc']))
        except Exception:
            continue
    if fired:
        fired.sort()
        if verbose:
            _w(f"\n  {_C.BOLD}{_C.BYELLOW}⏰ Przypomnienia:{_C.RESET}\n")
        for delta, date, desc in fired:
            when = "dziś!" if delta == 0 else f"za {delta} {'dzień' if delta==1 else 'dni'}"
            if verbose:
                _w(f"  {_C.BYELLOW}•{_C.RESET} {date}  {desc}  {_C.BGREEN}({when}){_C.RESET}\n")
            _send_notification(f"Przypomnienie: {when}", f"{date}: {desc}")
        if verbose:
            _w("\n")
            _sys.stdout.flush()

# ─── _do_note ─────────────────────────────────────────────────────────────────

def _do_note(args):
    """Notatki powiązane z datą."""
    sub = args[0].lower() if args else 'list'

    if sub == "add":
        if len(args) < 3:
            _w(f"\n  {_C.RED}✗ Użycie: cal note add <RRRR-MM-DD> <tekst>{_C.RESET}\n\n"); return
        try:
            d = _dt.datetime.strptime(args[1], "%Y-%m-%d").date()
        except ValueError:
            _w(f"\n  {_C.RED}✗ Nieprawidłowy format daty.{_C.RESET}\n\n"); return
        text = " ".join(args[2:])
        key  = str(d)
        _NOTES.setdefault(key, []).append(text)
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Notatka dodana do {d}: {text}{_C.RESET}\n\n")

    elif sub in ("list", "show"):
        if len(args) >= 2:
            # Pokaż notatki dla konkretnej daty
            try:
                d   = _dt.datetime.strptime(args[1], "%Y-%m-%d").date()
                key = str(d)
                notes = _NOTES.get(key, [])
                if not notes:
                    _w(f"\n  {_C.DIM}Brak notatek dla {d}.{_C.RESET}\n\n"); return
                _w(f"\n  {_C.BOLD}{_C.BCYAN}Notatki — {d}:{_C.RESET}\n\n")
                for i, n in enumerate(notes, 1):
                    _w(f"  {_C.DIM}{i}.{_C.RESET}  {n}\n")
                _w("\n")
            except ValueError:
                _w(f"\n  {_C.RED}✗ Nieprawidłowy format daty.{_C.RESET}\n\n")
        else:
            # Wszystkie notatki
            if not _NOTES:
                _w(f"\n  {_C.DIM}(brak notatek){_C.RESET}\n\n"); return
            today = _dt.date.today()
            _w(f"\n  {_C.BOLD}{_C.BCYAN}Wszystkie notatki:{_C.RESET}\n\n")
            for key in sorted(_NOTES):
                notes = _NOTES[key]
                if not notes: continue
                try:    d = _dt.date.fromisoformat(key)
                except: continue
                delta = (d - today).days
                if   delta > 0:  when = f"{_C.DIM}(za {delta} dni){_C.RESET}"
                elif delta == 0: when = f"{_C.BGREEN}(dziś){_C.RESET}"
                else:            when = f"{_C.DIM}({abs(delta)} dni temu){_C.RESET}"
                _w(f"  {_C.BYELLOW}{key}{_C.RESET}  {when}\n")
                for i, n in enumerate(notes, 1):
                    _w(f"    {_C.DIM}{i}.{_C.RESET} {n}\n")
            _w("\n")

    elif sub in ("remove", "rm"):
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal note remove <RRRR-MM-DD> [nr]{_C.RESET}\n\n"); return
        try:
            d   = _dt.datetime.strptime(args[1], "%Y-%m-%d").date()
            key = str(d)
        except ValueError:
            _w(f"\n  {_C.RED}✗ Nieprawidłowy format daty.{_C.RESET}\n\n"); return
        if len(args) >= 3:
            try:
                idx = int(args[2]) - 1
                if not (0 <= idx < len(_NOTES.get(key, []))): raise IndexError
                removed = _NOTES[key].pop(idx)
                if not _NOTES[key]: del _NOTES[key]
                _save_db()
                _w(f"\n  {_C.BGREEN}✓ Usunięto notatkę #{idx+1} z {d}.{_C.RESET}\n\n")
            except (ValueError, IndexError):
                _w(f"\n  {_C.RED}✗ Nieprawidłowy numer notatki.{_C.RESET}\n\n")
        else:
            count = len(_NOTES.pop(key, []))
            _save_db()
            _w(f"\n  {_C.BGREEN}✓ Usunięto {count} notatek z {d}.{_C.RESET}\n\n")

    elif sub == "clear":
        _NOTES.clear()
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Usunięto wszystkie notatki.{_C.RESET}\n\n")

    else:
        _w(f"\n  {_C.RED}✗ Użycie: cal note add|list|show|remove|clear{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_holiday ──────────────────────────────────────────────────────────────

def _do_holiday(args):
    """Wyświetla święta polskie dla roku/miesiąca."""
    now  = _dt.datetime.now()
    try:  year = int(args[0]) if args else now.year
    except: year = now.year

    month_filter = None
    if len(args) >= 2:
        try:
            month_filter = int(args[1])
            if not 1 <= month_filter <= 12: month_filter = None
        except: pass

    holidays = _get_holidays(year)
    today    = _dt.date.today()

    MON_PL = ["","Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec",
               "Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"]
    DAY_PL = ["Pn","Wt","Śr","Cz","Pt","Sb","Nd"]

    title = f"Święta polskie {year}"
    if month_filter:
        title += f" — {MON_PL[month_filter]}"
    _w(f"\n  {_C.BOLD}{_C.BCYAN}{title}{_C.RESET}\n\n")

    prev_month = None
    for d in sorted(holidays):
        if month_filter and d.month != month_filter:
            continue
        if d.month != prev_month:
            _w(f"  {_C.BOLD}{_C.BLUE}{MON_PL[d.month]}{_C.RESET}\n")
            prev_month = d.month
        is_today = d == today
        delta    = (d - today).days
        col      = f"{_C.INV}{_C.BGREEN}" if is_today else (
                   _C.BYELLOW if 0 < delta <= 30 else _C.RESET)
        when = ""
        if   delta == 0: when = f"  {_C.BGREEN}← dziś{_C.RESET}"
        elif 0 < delta <= 30: when = f"  {_C.DIM}za {delta} dni{_C.RESET}"
        _w(f"  {col}{d}  {DAY_PL[d.weekday()]}{_C.RESET}  {holidays[d]}{when}\n")
    _w("\n")
    _sys.stdout.flush()

# ─── _do_moon ─────────────────────────────────────────────────────────────────

def _do_moon(args):
    """Wyświetla fazę księżyca dla daty lub dzisiaj."""
    if args:
        try:    d = _dt.datetime.strptime(args[0], "%Y-%m-%d").date()
        except: _w(f"\n  {_C.RED}✗ Użycie: cal moon [RRRR-MM-DD]{_C.RESET}\n\n"); return
    else:
        d = _dt.date.today()

    phase_name, emoji = _get_moon_phase_info(d)

    days_since = (d - _NEW_MOON_REF_DATE).days
    phase_days = days_since % _SYNODIC_MONTH_DAYS
    phase_frac = phase_days / _SYNODIC_MONTH_DAYS

    days_to_new  = _SYNODIC_MONTH_DAYS - phase_days
    days_to_full = (_SYNODIC_MONTH_DAYS / 2 - phase_days) % _SYNODIC_MONTH_DAYS

    bar_w  = 20
    filled = round(phase_frac * bar_w)
    bar    = f"{_C.BYELLOW}{'●' * filled}{_C.DIM}{'○' * (bar_w - filled)}{_C.RESET}"

    _w(f"\n  {_C.BOLD}{_C.BCYAN}Faza Księżyca — {d}{_C.RESET}\n\n")
    _w(f"  {emoji}  {_C.BOLD}{phase_name}{_C.RESET}\n\n")
    _w(f"  {bar}  {_C.DIM}{phase_frac*100:.1f}% cyklu{_C.RESET}\n\n")
    _w(f"  {_C.BLUE}{'Dni od nowiu:':<22}{_C.RESET}{_C.BWHITE}{phase_days:.1f}{_C.RESET}\n")
    _w(f"  {_C.BLUE}{'Do kolejnego nowiu:':<22}{_C.RESET}{_C.BWHITE}{days_to_new:.1f} dni{_C.RESET}\n")
    _w(f"  {_C.BLUE}{'Do pełni:':<22}{_C.RESET}{_C.BWHITE}{days_to_full:.1f} dni{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_work ─────────────────────────────────────────────────────────────────

def _do_work(args):
    """Rozliczenie dni roboczych w miesiącu lub roku."""
    now   = _dt.datetime.now()
    today = _dt.date.today()

    # Parsowanie argumentów: [mm [yyyy]] lub [yyyy]
    try:
        if len(args) == 0:
            month, year = now.month, now.year
        elif len(args) == 1:
            v = int(args[0])
            if 1 <= v <= 12: month, year = v, now.year
            else:            month, year = None, v
        else:
            month, year = int(args[0]), int(args[1])
    except ValueError:
        _w(f"\n  {_C.RED}✗ Użycie: cal work [mm [yyyy]] lub [yyyy]{_C.RESET}\n\n"); return

    holidays = _get_holidays(year)
    MON_PL   = ["","Styczeń","Luty","Marzec","Kwiecień","Maj","Czerwiec",
                 "Lipiec","Sierpień","Wrzesień","Październik","Listopad","Grudzień"]

    def _month_stats(y, m):
        """Zwraca (wszystkie, robocze, wolne_ustawowe, weekendy, przepracowane_do_dziś)."""
        _, days_in = _cal.monthrange(y, m)
        total = days_in
        workdays = free = weekends = worked = 0
        for day in range(1, days_in + 1):
            d = _dt.date(y, m, day)
            if d.weekday() >= 5:
                weekends += 1
            elif d in holidays:
                free += 1
            else:
                workdays += 1
                if d <= today and y == today.year and m == today.month:
                    worked += 1
                elif _dt.date(y, m, day) < today:
                    worked += 1
        return total, workdays, free, weekends, worked

    if month:
        # Widok miesięczny
        total, workdays, free, weekends, worked = _month_stats(year, month)
        remaining = workdays - worked if year == today.year and month == today.month else 0
        title = f"Dni robocze — {MON_PL[month]} {year}"
        _w(f"\n  {_C.BOLD}{_C.BCYAN}{title}{_C.RESET}\n\n")
        def _wr(label, val, vc=None):
            vc = vc or _C.BWHITE
            _w(f"  {_C.BLUE}{label:<28}{_C.RESET}{vc}{val}{_C.RESET}\n")
        _wr("Wszystkich dni:",        str(total))
        _wr("Dni roboczych:",         str(workdays), _C.BGREEN)
        _wr("Weekendy:",              str(weekends), _C.YELLOW)
        _wr("Święta ustawowe:",       str(free),     _C.BYELLOW)
        if year == today.year and month == today.month:
            pct = worked / workdays * 100 if workdays else 0
            _wr("Przepracowane (do dziś):", f"{worked}  {_C.DIM}({pct:.1f}%){_C.RESET}", _C.BCYAN)
            _wr("Pozostałe:",           str(remaining), _C.MAGENTA)
        # Wypisz święta tego miesiąca
        h_month = {d: n for d, n in holidays.items() if d.month == month and d.year == year}
        if h_month:
            _w(f"\n  {_C.BOLD}{_C.BLUE}Święta w tym miesiącu:{_C.RESET}\n")
            for hd in sorted(h_month):
                _w(f"  {_C.DIM}{hd}{_C.RESET}  {h_month[hd]}\n")
        _w("\n")
    else:
        # Widok roczny — tabela miesięcy
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Dni robocze — {year}{_C.RESET}\n\n")
        _w(f"  {_C.BOLD}{_C.BLUE}{'Miesiąc':<12}{'Wszystkie':>11}{'Robocze':>9}{'Weekendy':>10}{'Święta':>8}{'Przeprac.':>11}{_C.RESET}\n")
        _w(f"  {_C.BLUE}{'─'*55}{_C.RESET}\n")
        tot_all = tot_work = tot_free = tot_we = tot_done = 0
        for m in range(1, 13):
            total, workdays, free, weekends, worked = _month_stats(year, m)
            tot_all  += total; tot_work += workdays; tot_free += free
            tot_we   += weekends; tot_done += worked
            is_cur    = year == today.year and m == today.month
            col       = _C.BYELLOW if is_cur else _C.RESET
            is_past = (year < today.year) or (year == today.year and m < today.month)
            is_cur  = year == today.year and m == today.month
            done_str = str(worked) if (is_past or is_cur) else "—"
            _w(f"  {col}{MON_PL[m]:<12}{_C.RESET}"
               f"{total:>11}{workdays:>9}{weekends:>10}{free:>8}"
               f"{_C.DIM}{done_str:>11}{_C.RESET}\n")
        _w(f"  {_C.BLUE}{'─'*55}{_C.RESET}\n")
        _w(f"  {_C.BOLD}{'RAZEM':<12}{tot_all:>11}{tot_work:>9}{tot_we:>10}{tot_free:>8}{tot_done:>11}{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── _do_tag ──────────────────────────────────────────────────────────────────

def _do_tag(args):
    """Tagowanie wydarzeń i filtrowanie po tagu."""
    sub = args[0].lower() if args else 'list'

    if sub == "add":
        # cal tag add <nr_wydarzenia> <tag> [tag2 ...]
        if len(args) < 3:
            _w(f"\n  {_C.RED}✗ Użycie: cal tag add <nr_wydarzenia> <tag> [tag2 ...]{_C.RESET}\n\n"); return
        try:
            idx = int(args[1]) - 1
            if not (0 <= idx < len(_EVENTS)): raise IndexError
        except (ValueError, IndexError):
            _w(f"\n  {_C.RED}✗ Nieprawidłowy numer wydarzenia.{_C.RESET}\n\n"); return
        new_tags = [t.lower().lstrip('#') for t in args[2:]]
        existing = _EVENTS[idx].setdefault('tags', [])
        added    = [t for t in new_tags if t not in existing]
        existing.extend(added)
        _save_db()
        e = _EVENTS[idx]
        _w(f"\n  {_C.BGREEN}✓ Dodano tagi [{', '.join('#'+t for t in added)}] do: {e['date']} — {e['desc']}{_C.RESET}\n\n")

    elif sub in ("remove", "rm"):
        # cal tag remove <nr_wydarzenia> <tag>
        if len(args) < 3:
            _w(f"\n  {_C.RED}✗ Użycie: cal tag remove <nr_wydarzenia> <tag>{_C.RESET}\n\n"); return
        try:
            idx = int(args[1]) - 1
            if not (0 <= idx < len(_EVENTS)): raise IndexError
        except (ValueError, IndexError):
            _w(f"\n  {_C.RED}✗ Nieprawidłowy numer wydarzenia.{_C.RESET}\n\n"); return
        tag    = args[2].lower().lstrip('#')
        tags   = _EVENTS[idx].get('tags', [])
        if tag in tags:
            tags.remove(tag)
            _save_db()
            _w(f"\n  {_C.BGREEN}✓ Usunięto tag #{tag}.{_C.RESET}\n\n")
        else:
            _w(f"\n  {_C.RED}✗ Tag #{tag} nie istnieje na tym wydarzeniu.{_C.RESET}\n\n")

    elif sub == "filter":
        # cal tag filter <tag>
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal tag filter <tag>{_C.RESET}\n\n"); return
        tag   = args[1].lower().lstrip('#')
        today = _dt.date.today()
        hits  = [(i, e) for i, e in enumerate(_EVENTS, 1) if tag in [t.lower() for t in e.get('tags', [])]]
        if not hits:
            _w(f"\n  {_C.DIM}Brak wydarzeń z tagiem #{tag}.{_C.RESET}\n\n"); return
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Filtr: #{tag}  ({len(hits)} wyników){_C.RESET}\n\n")
        for i, e in hits:
            delta = (e['date'] - today).days
            if   delta > 0:  when = f"{_C.DIM}za {delta} dni{_C.RESET}"
            elif delta == 0: when = f"{_C.BGREEN}dziś{_C.RESET}"
            else:            when = f"{_C.DIM}{abs(delta)} dni temu{_C.RESET}"
            tags_str = "  " + " ".join(f"{_C.CYAN}#{t}{_C.RESET}" for t in e.get('tags', []))
            _w(f"  {_C.DIM}{i:<2}{_C.RESET}  {_C.BYELLOW}{e['date']}{_C.RESET}  {e['desc']}{tags_str}  {when}\n")
        _w("\n")

    elif sub == "list":
        # Wszystkie tagi z licznikami
        tag_counts = _Counter(t for e in _EVENTS for t in e.get('tags', []))
        if not tag_counts:
            _w(f"\n  {_C.DIM}Brak tagów.{_C.RESET}\n\n"); return
        _w(f"\n  {_C.BOLD}{_C.BCYAN}Wszystkie tagi:{_C.RESET}\n\n")
        for tag, cnt in tag_counts.most_common():
            _w(f"  {_C.CYAN}#{tag:<20}{_C.RESET}  {_C.DIM}{cnt} wydarz.{_C.RESET}\n")
        _w("\n")

    elif sub == "clear":
        # cal tag clear <nr_wydarzenia> — usuń wszystkie tagi z wydarzenia
        if len(args) < 2:
            _w(f"\n  {_C.RED}✗ Użycie: cal tag clear <nr_wydarzenia>{_C.RESET}\n\n"); return
        try:
            idx = int(args[1]) - 1
            if not (0 <= idx < len(_EVENTS)): raise IndexError
        except (ValueError, IndexError):
            _w(f"\n  {_C.RED}✗ Nieprawidłowy numer wydarzenia.{_C.RESET}\n\n"); return
        _EVENTS[idx]['tags'] = []
        _save_db()
        _w(f"\n  {_C.BGREEN}✓ Usunięto wszystkie tagi z #{int(args[1])}.{_C.RESET}\n\n")

    else:
        _w(f"\n  {_C.RED}✗ Użycie: cal tag add|remove|filter|list|clear{_C.RESET}\n\n")
    _sys.stdout.flush()

# ─── komenda główna ────────────────────────────────────────────────────────────

def cmd_cal(args, terminal):
    """cal [now|week|year|countdown|notify|mm|mm yyyy] — kalendarz i czas."""
    now = _dt.datetime.now()
    sub = args[0].lower() if args else ''

    if   sub == '':           _do_month(now.month, now.year)
    elif sub == 'now':        _do_now()
    elif sub == 'notify':
        _do_notify_today(force=True)
        _w(f"\n  {_C.BGREEN}✓ Sprawdzono powiadomienia na dziś.{_C.RESET}\n\n")
        _sys.stdout.flush()
    elif sub == 'week':       _do_week()
    elif sub in ('year','rok'):
        try:    year = int(args[1]) if len(args) > 1 else now.year
        except: year = now.year
        _do_year(year)
    elif sub == 'remind':      _do_remind(args[1:])
    elif sub == 'note':        _do_note(args[1:])
    elif sub == 'holiday':     _do_holiday(args[1:])
    elif sub == 'moon':        _do_moon(args[1:])
    elif sub == 'work':        _do_work(args[1:])
    elif sub == 'tag':         _do_tag(args[1:])
    elif sub == 'recurring':   _do_recurring(args[1:])
    elif sub == 'diff':
        if len(args) < 3: _w(f"  {_C.RED}Użycie: cal diff <RRRR-MM-DD> <RRRR-MM-DD>{_C.RESET}\n")
        else:             _do_diff(args[1:])
    elif sub == 'search':      _do_search(args[1:])
    elif sub == 'agenda':      _do_agenda(args[1:])
    elif sub == 'stats':       _do_stats()
    elif sub == 'event':
        _do_event(args[1:])
    elif sub == 'config':
        _do_config(args[1:])
    elif sub == 'countdown':
        if len(args) < 2: _w(f"  {_C.RED}Użycie: cal countdown RRRR-MM-DD{_C.RESET}\n")
        else:             _do_countdown(args[1])
    elif sub.isdigit():
        try:
            month = int(sub)
            year  = int(args[1]) if len(args) > 1 else now.year
            if not 1 <= month <= 12: raise ValueError
            _do_month(month, year)
        except ValueError:
            _w(f"  {_C.RED}Użycie: cal [mm [yyyy]]  (mm = 1–12){_C.RESET}\n")
    else:
        _w(f"  {_C.RED}cal: nieznana subkomenda '{sub}'{_C.RESET}\n")
        cml_menu()

def cmd_calendar(args, terminal):
    """calendar [rok] — pełny kalendarz roku."""
    now = _dt.datetime.now()
    try:    year = int(args[0]) if args else now.year
    except: year = now.year
    _do_year(year)

# ─── rejestr — 2 komendy globalne ─────────────────────────────────────────────

CML_COMMANDS = {
    "cal"      : cmd_cal,
    "calendar" : cmd_calendar,
}

def on_load():
    """Inicjalizacja modułu."""
    _load_db()
    _do_remind_check(verbose=False)  # Sprawdź przypomnienia przy starcie (cicho)

if __name__ == "__main__":
    # Ten blok uruchamia się, gdy skrypt jest wywoływany bezpośrednio (np. z crona lub harmonogramu zadań)
    on_load() # Załaduj bazę danych wydarzeń
    # Przekaż argumenty wiersza poleceń do funkcji obsługującej komendy
    cmd_cal(_sys.argv[1:], None)


# ─── EcoSystem core integration ───────────────────────────────────────────────

def setup(terminal):
    """Rejestruje komendy cal/calendar w TerminalX EcoSystem."""
    cat = terminal.t("cat_general")

    def _cal(args):
        cmd_cal(args, terminal)

    def _calendar(args):
        cmd_calendar(args, terminal)

    terminal.register_command(
        "cal", _cal,
        description=terminal.t("cmd_cal"),
        category=cat,
    )
    terminal.register_command(
        "calendar", _calendar,
        description=terminal.t("cmd_calendar"),
        category=cat,
    )

    on_load()


def teardown(terminal):
    """Wyrejestrowuje komendy cal/calendar z TerminalX EcoSystem."""
    for cmd in ("cal", "calendar"):
        terminal.commands.pop(cmd, None)
