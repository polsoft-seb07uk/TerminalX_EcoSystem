# Moduł DOS — PyTermOS

Moduł do uruchamiania gier i programów DOSowych przez **DOSBox**.
W pełni zgodny z systemem modułów **PyTerm v2.0.0.0**.

---

## Struktura katalogu

```
dos/
├── __init__.py       ← główny plik modułu (METADATA + init + list_commands + execute)
├── dosbox.conf       ← konfiguracja DOSBox
├── programs.json     ← lista zapisanych gier/programów (auto-tworzona)
├── README.md         ← ta dokumentacja
└── bin/
    ├── DOSBox.exe    ← ← ← SKOPIUJ TU z DOSBox.zip
    ├── SDL.dll       ← ← ← SKOPIUJ TU
    └── SDL_net.dll   ← ← ← SKOPIUJ TU
```

---

## Instalacja

### 1. Przygotowanie plików

Skopiuj zawartość `DOSBox.zip` do podkatalogu `bin/`:
- `DOSBox.exe`
- `SDL.dll`
- `SDL_net.dll`

### 2. Załadowanie modułu w PyTerm

```
mod set <ścieżka do folderu zawierającego katalog dos>
mod load dos
```

Przykład, jeśli moduł jest w `C:\PyTerm\modules\dos`:
```
mod set C:\PyTerm\modules
mod load dos
```

### 3. (Opcjonalnie) Autostart

Aby moduł ładował się automatycznie przy każdym uruchomieniu terminala:
```
ast add mod dos
```

---

## Komendy

| Komenda                            | Opis                                         |
|------------------------------------|----------------------------------------------|
| `dos`                              | Wyświetla listę dostępnych komend            |
| `dos run`                          | Uruchamia DOSBox (tryb interaktywnej konsoli)|
| `dos list`                         | Wyświetla listę zapisanych programów/gier    |
| `dos <nazwa>`                      | Uruchamia program o podanej nazwie           |
| `dos add <nazwa> <ścieżka> [args]` | Dodaje nowy program do listy                 |
| `dos remove <nazwa>`               | Usuwa program z listy                        |

---

## Przykłady użycia

```
dos
```
```
dos run
```
```
dos list
```
```
dos add doom C:\Games\DOOM\DOOM.EXE
dos doom
```
```
dos add wolf3d C:\Games\WOLF3D\WOLF3D.EXE
dos wolf3d
```
```
dos remove doom
```

---

## Jak działa integracja z ModuleManager

Moduł korzysta z **auto-bridge** PyTerm:

1. `METADATA` – dostarcza nazwę, wersję, opis i typ (`library`)
2. `init(terminal)` – wywoływane przy `mod load dos`
3. `teardown(terminal)` – wywoływane przy `mod unload dos`
4. `list_commands()` – zwraca słownik `{"dos": {...}}`
5. `execute(cmd, args)` – dispatcher wywoływany przez terminal

`ModuleManager._activate()` automatycznie rejestruje komendę `dos`
w systemie terminala — nie jest wymagana żadna ręczna rejestracja.

---

## Konfiguracja DOSBox

Edytuj `dosbox.conf`, aby dostosować zachowanie emulatora:

- `fullscreen=true` — uruchamiaj w pełnym ekranie
- `cycles=5000` — ręczne ustawienie prędkości CPU (dla starszych gier)
- Sekcja `[autoexec]` — komendy wykonywane automatycznie po starcie

Przykład sekcji `[autoexec]` dla gier w `C:\Games`:
```ini
[autoexec]
MOUNT C C:\Games
C:
```

---

## programs.json

Plik jest tworzony automatycznie po pierwszym `dos add`.
Możesz go też edytować ręcznie:

```json
{
  "doom": {
    "path": "C:\\Games\\DOOM\\DOOM.EXE"
  },
  "quake": {
    "path": "C:\\Games\\QUAKE\\QUAKE.EXE",
    "args": ["-winmem", "16"]
  }
}
```
