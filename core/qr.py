#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# web:     www.polsoft.gt.tc
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
# crossterm: {"id": "08", "aliases": ["qr", "qrcode", "nfc"], "description": "Generator kodów QR, Barcode oraz obsługa NFC", "version": "2.5", "author": "Sebastian Januchowski"}
"""
Moduł Multi-Generator v2.5 (QR, Barcode, NFC)
  qr <tekst> [flagi]              — generuj kod QR (opcjonalnie z kolorem)
  qr file <ścieżka> [flagi]       — generuj QR dla pełnej ścieżki pliku
  qr url <link>                   — generuj QR dla adresu URL (auto https://)
  qr wifi <s> <p> [t]             — generuj QR dla sieci WiFi (WPA/WEP/nopass)
  qr email <addr> [s] [b]         — generuj QR mailto (adres, temat, treść)
  qr sms <nr> [treść]             — generuj QR smsto
  qr geo <lat> <lon>              — generuj QR z lokalizacją GPS
  qr contact <name> <tel>         — generuj QR z wizytówką (vCard)
  qr clip                         — generuj QR ze schowka systemowego
  qr decode <plik>                — dekoduj QR/barcode z obrazka (PNG/JPG)
  qr bar <typ> <dane>             — generuj kod kreskowy (np. ean13, code128)
  qr nfc <read|write|list> [txt]  — obsługa tagów NFC (NDEF); list = typy rekordów
  qr save <t> <p> [flagi]         — zapisz kod: --bar <typ> | --png
  qr history [N|clear]            — historia kodów; N = pokaż i wyrenderuj wpis N
  qr otp <secret> [nazwa] [wyda.] — generuj QR dla TOTP/Google Authenticator
  qr multi <plik.txt> [flagi]     — batch: QR dla każdej linii pliku
  qr help                         — wyświetla to menu
  qrcode, nfc                     — aliasy -> menu
  Flagi (moduły): -r (czerw), -g (ziel), -b (nieb), -y (żół), -c (cyjan), -m (mag)
  Flagi (tło):    -br, -bg, -bb, -by, -bc, -bm, -bw (białe)
  Tryb:           --half  — render half-block (kompaktowy, 2x mniejszy)
"""

import sys
import os
import json
import datetime

_sys = sys

# Ścieżka pliku historii
_HISTORY_FILE = os.path.join(os.path.expanduser("~"), ".crossterm", "qr_history.json")
_HISTORY_MAX  = 50   # maksymalna liczba wpisów


def _w(s):
    _sys.stdout.write(s)
    _sys.stdout.flush()


class _C:
    RESET   = "\x1b[0m";  BOLD    = "\x1b[1m";  DIM     = "\x1b[2m"
    BCYAN   = "\x1b[96m"; BYELLOW = "\x1b[93m"; BGREEN  = "\x1b[92m"
    BWHITE  = "\x1b[97m"; RED     = "\x1b[91m"; CYAN    = "\x1b[36m"
    WHITE   = "\x1b[37m"

    FG_COLORS = {
        "-r": "\x1b[41m",
        "-g": "\x1b[42m",
        "-b": "\x1b[44m",
        "-y": "\x1b[43m",
        "-m": "\x1b[45m",
        "-c": "\x1b[46m",
    }

    BG_QUIET_COLORS = {
        "-br": "\x1b[41m",
        "-bg": "\x1b[42m",
        "-bb": "\x1b[44m",
        "-by": "\x1b[43m",
        "-bm": "\x1b[45m",
        "-bc": "\x1b[46m",
        "-bw": "\x1b[47m",
    }

    FG_TEXT_COLORS = {
        "\x1b[41m": "\x1b[31m",
        "\x1b[42m": "\x1b[32m",
        "\x1b[44m": "\x1b[34m",
        "\x1b[43m": "\x1b[33m",
        "\x1b[45m": "\x1b[35m",
        "\x1b[46m": "\x1b[36m",
        "\x1b[40m": "\x1b[30m",
        "\x1b[47m": "\x1b[37m",
    }


# ─── Zależności ───────────────────────────────────────────────────────────────

def _ensure_dependencies():
    potential_paths = [
        os.path.join(os.environ.get('APPDATA', ''), 'Python', 'Python312', 'site-packages'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'Python', 'Python312', 'Lib', 'site-packages'),
        os.path.join(os.path.dirname(sys.executable), "Lib", "site-packages"),
        os.path.join(os.path.dirname(sys.executable), "site-packages"),
    ]
    for p in potential_paths:
        if os.path.exists(p) and p not in sys.path:
            sys.path.append(p)


# ─── Historia ─────────────────────────────────────────────────────────────────

def _history_load() -> list:
    """Wczytuje historię z pliku JSON. Zwraca listę wpisów (najnowsze na początku)."""
    try:
        with open(_HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        pass
    return []


def _history_save(entries: list):
    """Zapisuje historię do pliku JSON (atomowo przez plik tymczasowy)."""
    try:
        os.makedirs(os.path.dirname(_HISTORY_FILE), exist_ok=True)
        tmp = _HISTORY_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries[:_HISTORY_MAX], f, ensure_ascii=False, indent=2)
        os.replace(tmp, _HISTORY_FILE)
    except OSError:
        pass


def _history_add(kind: str, payload: str, label: str = ""):
    """Dodaje wpis do historii. kind = typ komendy, payload = surowy tekst QR."""
    entries = _history_load()
    entry = {
        "ts":      datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "kind":    kind,
        "payload": payload,
        "label":   label or payload[:60],
    }
    # Deduplikacja: jeśli ten sam payload jest już na szczycie — nie dodawaj
    if entries and entries[0].get("payload") == payload:
        return
    entries.insert(0, entry)
    _history_save(entries)


def cmd_history(rest, fg_color, bg_color, half):
    """
    qr history          — wyświetl listę ostatnich kodów
    qr history <N>      — pokaż wpis N i wyrenderuj QR
    qr history clear    — wyczyść historię
    """
    # ── clear ────────────────────────────────────────────────────────────────
    if rest and rest[0].lower() == "clear":
        try:
            if os.path.exists(_HISTORY_FILE):
                os.remove(_HISTORY_FILE)
            _w(f"\n  {_C.BGREEN}[V] Historia wyczyszczona.{_C.RESET}\n\n")
        except OSError as e:
            _w(f"\n  {_C.RED}[!] Blad usuwania historii: {e}{_C.RESET}\n\n")
        return

    entries = _history_load()

    # ── renderuj wpis N ──────────────────────────────────────────────────────
    if rest and rest[0].isdigit():
        idx = int(rest[0]) - 1
        if idx < 0 or idx >= len(entries):
            _w(f"\n  {_C.RED}[!] Brak wpisu nr {rest[0]}. Historia ma {len(entries)} pozycji.{_C.RESET}\n\n")
            return
        e = entries[idx]
        _w(f"\n  {_C.BCYAN}[{idx+1}]{_C.RESET} {_C.DIM}{e['ts']}{_C.RESET}"
           f"  {_C.BYELLOW}{e['kind']}{_C.RESET}  {_C.BWHITE}{e['label']}{_C.RESET}\n")
        render_qr_terminal(_make_matrix(e["payload"]), fg_color, bg_color, half)
        _w(f"  {_C.DIM}Payload: {e['payload'][:80]}{_C.RESET}\n\n")
        return

    # ── lista ────────────────────────────────────────────────────────────────
    if not entries:
        _w(f"\n  {_C.BYELLOW}[?] Historia jest pusta.{_C.RESET}\n\n")
        return

    _w(f"\n  {_C.BOLD}{_C.BCYAN}Historia QR ({len(entries)} wpisów):{_C.RESET}\n\n")
    for i, e in enumerate(entries, 1):
        kind_col  = _C.BYELLOW
        ts_col    = _C.DIM
        label_col = _C.BWHITE
        payload_p = e["payload"][:55] + "..." if len(e["payload"]) > 55 else e["payload"]
        _w(f"  {_C.BOLD}{i:>3}.{_C.RESET} "
           f"{ts_col}{e['ts']}{_C.RESET}  "
           f"{kind_col}{e['kind']:<10}{_C.RESET}  "
           f"{label_col}{payload_p}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Uzyj: qr history <N> — wyrenderuj kod | qr history clear — wyczysc{_C.RESET}\n\n")


# ─── OTP / TOTP ───────────────────────────────────────────────────────────────

def cmd_otp(rest, fg_color, bg_color, half):
    """
    qr otp <secret> [nazwa] [wydawca]
    Generuje QR w formacie otpauth://totp/... gotowy do skanowania przez
    Google Authenticator, Aegis, Authy i inne aplikacje TOTP.

    secret  — Base32 secret key (np. JBSWY3DPEHPK3PXP)
    nazwa   — nazwa konta wyświetlana w aplikacji (domyślnie: konto)
    wydawca — opcjonalna nazwa serwisu (domyślnie: pusta)
    """
    if not rest:
        _w(f"\n  {_C.RED}[!] Uzycie: qr otp <secret> [nazwa] [wydawca]{_C.RESET}\n")
        _w("  Przyklad: qr otp JBSWY3DPEHPK3PXP MojeKonto GitHub\n\n")
        return

    secret  = rest[0].upper().replace(" ", "")
    name    = rest[1] if len(rest) > 1 else "konto"
    issuer  = rest[2] if len(rest) > 2 else ""

    # Walidacja znaków Base32
    import re
    if not re.fullmatch(r"[A-Z2-7=]+", secret):
        _w(f"\n  {_C.RED}[!] Nieprawidlowy format secret (oczekiwany Base32: A-Z, 2-7, =){_C.RESET}\n\n")
        return

    # Buduj URI otpauth
    from urllib.parse import quote as _q
    label  = _q(f"{issuer}:{name}" if issuer else name, safe="")
    uri    = f"otpauth://totp/{label}?secret={secret}&digits=6&period=30"
    if issuer:
        uri += f"&issuer={_q(issuer, safe='')}"

    _w(f"\n  {_C.BOLD}QR TOTP:{_C.RESET}\n")
    _w(f"  Konto:   {_C.BGREEN}{name}{_C.RESET}\n")
    if issuer:
        _w(f"  Serwis:  {_C.BCYAN}{issuer}{_C.RESET}\n")
    _w(f"  Secret:  {_C.BYELLOW}{secret}{_C.RESET}\n")
    _w(f"  {_C.DIM}Okres: 30s  |  Cyfry: 6  |  Algorytm: SHA1{_C.RESET}\n")

    render_qr_terminal(_make_matrix(uri), fg_color, bg_color, half)

    _w(f"  {_C.DIM}Wskazowka: Zeskanuj w Google Authenticator / Aegis / Authy.{_C.RESET}\n")
    _w(f"  {_C.RED}[!] Nie udostepniaj tego QR nikomu — zawiera klucz 2FA!{_C.RESET}\n\n")

    _history_add("otp", uri, f"OTP:{name}" + (f"@{issuer}" if issuer else ""))


# ─── Multi (batch) ────────────────────────────────────────────────────────────

def cmd_multi(rest, fg_color, bg_color, half):
    """
    qr multi <plik.txt> [flagi]
    Wczytuje plik linia po linii. Dla każdej niepustej linii generuje i
    wyświetla QR z numerem i podglądem treści.
    Puste linie i linie zaczynające się od '#' są pomijane.
    """
    if not rest:
        _w(f"\n  {_C.RED}[!] Uzycie: qr multi <plik.txt>{_C.RESET}\n")
        _w("  Kazda linia pliku staje sie osobnym kodem QR.\n")
        _w("  Linie puste i zaczynajace sie od '#' sa pomijane.\n\n")
        return

    filepath = rest[0]
    if not os.path.isfile(filepath):
        _w(f"\n  {_C.RED}[!] Plik nie istnieje: {filepath}{_C.RESET}\n\n")
        return

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            raw_lines = f.readlines()
    except OSError as e:
        _w(f"\n  {_C.RED}[!] Blad odczytu pliku: {e}{_C.RESET}\n\n")
        return

    lines = [l.rstrip("\n\r") for l in raw_lines
             if l.strip() and not l.lstrip().startswith("#")]

    if not lines:
        _w(f"\n  {_C.BYELLOW}[?] Plik nie zawiera zadnych linii do przetworzenia.{_C.RESET}\n\n")
        return

    total = len(lines)
    _w(f"\n  {_C.BOLD}{_C.BCYAN}Multi-QR:{_C.RESET} {_C.BWHITE}{filepath}{_C.RESET}"
       f"  {_C.DIM}({total} linii){_C.RESET}\n")
    _w(f"  {_C.DIM}{'─' * 52}{_C.RESET}\n")

    for i, line in enumerate(lines, 1):
        preview = line[:55] + "..." if len(line) > 55 else line
        _w(f"\n  {_C.BOLD}{_C.BYELLOW}[{i}/{total}]{_C.RESET}  {_C.BWHITE}{preview}{_C.RESET}\n")
        matrix = _make_matrix(line)
        if matrix is None:
            _w(f"  {_C.RED}[!] Nie mozna wygenerowac QR dla tej linii.{_C.RESET}\n")
            continue
        render_qr_terminal(matrix, fg_color, bg_color, half)
        _history_add("multi", line)

    _w(f"  {_C.BGREEN}[V] Wygenerowano {total} kod(ow) QR.{_C.RESET}\n\n")


# ─── NFC list ─────────────────────────────────────────────────────────────────

def _nfc_list_records(tag):
    """Wyświetla szczegółową listę rekordów NDEF z tagu NFC."""
    if not tag.ndef:
        _w(f"  {_C.BYELLOW}[?] Tag nie zawiera danych NDEF.{_C.RESET}\n")
        return

    records = tag.ndef.records
    capacity = getattr(tag.ndef, "capacity", "?")
    length   = getattr(tag.ndef, "length",   "?")

    _w(f"\n  {_C.BOLD}{_C.BGREEN}[V] Tag: {tag}{_C.RESET}\n")
    _w(f"  Pojemnosc: {_C.BYELLOW}{length}{_C.RESET}/{_C.BYELLOW}{capacity}{_C.RESET} bajtow"
       f"  |  Rekordy: {_C.BYELLOW}{len(records)}{_C.RESET}\n")
    _w(f"  {_C.DIM}{'─' * 52}{_C.RESET}\n\n")

    if not records:
        _w(f"  {_C.DIM}(brak rekordow){_C.RESET}\n")
        return

    # Mapa TNF (Type Name Format) na opis
    _TNF = {
        0x00: "Empty",
        0x01: "Well-Known",
        0x02: "MIME media",
        0x03: "Absolute URI",
        0x04: "External",
        0x05: "Unknown",
        0x06: "Unchanged",
        0x07: "Reserved",
    }

    for idx, rec in enumerate(records, 1):
        tnf      = getattr(rec, "tnf",  None)
        rtype    = getattr(rec, "type", b"")
        payload  = getattr(rec, "data", b"")
        tnf_desc = _TNF.get(tnf, f"0x{tnf:02X}" if tnf is not None else "?")

        # Dekoduj typ
        try:
            type_str = rtype.decode("ascii") if isinstance(rtype, bytes) else str(rtype)
        except Exception:
            type_str = repr(rtype)

        # Próba dekodowania payload jako tekstu
        try:
            if isinstance(payload, (bytes, bytearray)):
                # Dla Well-Known Text (TNF=1, type=T) pomijamy pierwszy bajt (lang)
                if tnf == 0x01 and rtype in (b"T", b"\x54"):
                    lang_len = payload[0] & 0x3F
                    text_val = payload[1 + lang_len:].decode("utf-8", errors="replace")
                    payload_str = f"[Text] {text_val}"
                elif tnf == 0x01 and rtype in (b"U", b"\x55"):
                    _URI_PREFIXES = [
                        "", "http://www.", "https://www.", "http://", "https://",
                        "tel:", "mailto:", "ftp://anonymous:anonymous@", "ftp://ftp.",
                        "ftps://", "sftp://", "smb://", "nfs://", "ftp://",
                        "dav://", "news:", "telnet://", "imap:", "rtsp://",
                        "urn:", "pop:", "sip:", "sips:", "tftp:", "btspp://",
                        "btl2cap://", "btgoep://", "tcpobex://", "irdaobex://",
                        "file://", "urn:epc:id:", "urn:epc:tag:", "urn:epc:pat:",
                        "urn:epc:raw:", "urn:epc:", "urn:nfc:",
                    ]
                    prefix_id = payload[0] if payload else 0
                    prefix    = _URI_PREFIXES[prefix_id] if prefix_id < len(_URI_PREFIXES) else ""
                    uri_val   = prefix + payload[1:].decode("utf-8", errors="replace")
                    payload_str = f"[URI] {uri_val}"
                else:
                    payload_str = payload.decode("utf-8", errors="replace")
            else:
                payload_str = str(payload)
        except Exception:
            payload_str = repr(payload)

        _w(f"  {_C.BOLD}[{idx}]{_C.RESET}\n")
        _w(f"    TNF:     {_C.BCYAN}{tnf_desc}{_C.RESET}\n")
        _w(f"    Typ:     {_C.BYELLOW}{type_str}{_C.RESET}\n")
        _w(f"    Payload: {_C.BWHITE}{payload_str[:120]}{_C.RESET}\n")
        if len(payload_str) > 120:
            _w(f"             {_C.DIM}... ({len(payload)} bajtow lacznie){_C.RESET}\n")
        _w("\n")


# ─── Generowanie QR ───────────────────────────────────────────────────────────

def _make_matrix(text: str):
    _ensure_dependencies()
    try:
        import qrcode
    except ImportError:
        _w("\n  [!] Brak biblioteki 'qrcode'. Zainstaluj: pip install qrcode\n\n")
        return None
    qr = qrcode.QRCode(error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=1, border=0)
    qr.add_data(text)
    qr.make(fit=True)
    return qr.get_matrix()


def render_qr_terminal(matrix, fg_ansi="\x1b[40m", bg_ansi="\x1b[47m", half=False):
    if matrix is None:
        return
    if half:
        _render_qr_half(matrix, fg_ansi, bg_ansi)
    else:
        _render_qr_block(matrix, fg_ansi, bg_ansi)


def _render_qr_block(matrix, fg_ansi, bg_ansi):
    margin = 2
    width  = len(matrix[0]) + margin * 2
    blank  = bg_ansi + "  " + _C.RESET
    black  = fg_ansi + "  " + _C.RESET
    pad    = "    "
    lines  = ["\n"]
    border = pad + bg_ansi + "  " * width + _C.RESET + "\n"
    for _ in range(margin):
        lines.append(border)
    for row in matrix:
        buf  = pad + bg_ansi + "  " * margin + _C.RESET
        buf += "".join(black if cell else blank for cell in row)
        buf += bg_ansi + "  " * margin + _C.RESET + "\n"
        lines.append(buf)
    for _ in range(margin):
        lines.append(border)
    lines.append("\n")
    _w("".join(lines))


def _render_qr_half(matrix, fg_ansi, bg_ansi):
    fg_text = _C.FG_TEXT_COLORS.get(fg_ansi, "\x1b[30m")
    bg_text = _C.FG_TEXT_COLORS.get(bg_ansi, "\x1b[37m")
    margin  = 2
    cols    = len(matrix[0])
    pad     = "  "
    R       = _C.RESET
    empty_r = lambda: [False] * cols
    padded  = [empty_r() for _ in range(margin)] + list(matrix) + [empty_r() for _ in range(margin)]
    if len(padded) % 2:
        padded.append(empty_r())

    def _cell(t, b):
        if t and b:   return fg_ansi + fg_text + "\u2588" + R
        if t:         return fg_ansi + fg_text + "\u2580" + R
        if b:         return fg_ansi + fg_text + "\u2584" + R
        return bg_ansi + bg_text + " " + R

    lines = ["\n"]
    for i in range(0, len(padded), 2):
        top = padded[i]; bot = padded[i + 1]
        buf  = pad + (bg_ansi + bg_text + " " + R) * margin
        buf += "".join(_cell(top[j], bot[j]) for j in range(cols))
        buf += (bg_ansi + bg_text + " " + R) * margin + "\n"
        lines.append(buf)
    lines.append("\n")
    _w("".join(lines))


# ─── Generowanie Barcode ──────────────────────────────────────────────────────

def _make_barcode(code_type: str, data: str):
    _ensure_dependencies()
    try:
        import barcode
    except ImportError:
        _w("\n  [!] Brak biblioteki 'python-barcode'. Zainstaluj: pip install python-barcode\n\n")
        return None
    try:
        code_class = barcode.get_barcode_class(code_type)
        return code_class(data).build()
    except Exception as e:
        _w(f"\n  [!] Blad: {e}\n")
        _w(f"  Dostepne typy: {', '.join(barcode.PROVIDED_BARCODES)}\n\n")
        return None


def render_barcode_terminal(encoded, fg_ansi="\x1b[40m", bg_ansi="\x1b[47m"):
    if not encoded or not encoded[0]:
        return
    row_data = encoded[0]
    height   = 6
    margin_h = 2
    width    = len(row_data) + margin_h * 2
    blank    = bg_ansi + "  " + _C.RESET
    black    = fg_ansi + "  " + _C.RESET
    pad      = "    "
    border   = pad + bg_ansi + "  " * width + _C.RESET + "\n"
    lines    = ["\n", border]
    for _ in range(height):
        buf  = pad + bg_ansi + "  " * margin_h + _C.RESET
        buf += "".join(black if cell == "1" else blank for cell in row_data)
        buf += bg_ansi + "  " * margin_h + _C.RESET + "\n"
        lines.append(buf)
    lines += [border, "\n"]
    _w("".join(lines))


# ─── Eksport PNG ──────────────────────────────────────────────────────────────

def _save_qr_png(matrix, filename: str) -> bool:
    _ensure_dependencies()
    try:
        from PIL import Image
    except ImportError:
        _w("\n  [!] Brak biblioteki 'Pillow'. Zainstaluj: pip install Pillow\n\n")
        return False
    scale  = 10
    margin = 4
    size   = len(matrix[0])
    dim    = (size + margin * 2) * scale
    img    = Image.new("RGB", (dim, dim), "white")
    pixels = img.load()
    for y, row in enumerate(matrix):
        for x, cell in enumerate(row):
            if cell:
                px = (x + margin) * scale
                py = (y + margin) * scale
                for dy in range(scale):
                    for dx in range(scale):
                        pixels[px + dx, py + dy] = (0, 0, 0)
    try:
        img.save(filename)
    except Exception as e:
        _w(f"\n  {_C.RED}[!] Blad zapisu PNG: {e}{_C.RESET}\n\n")
        return False
    return True


# ─── Dekodowanie QR ───────────────────────────────────────────────────────────

def _decode_image(filepath: str):
    _ensure_dependencies()
    try:
        from PIL import Image
    except ImportError:
        _w("\n  [!] Brak biblioteki 'Pillow'. Zainstaluj: pip install Pillow\n\n")
        return
    try:
        from pyzbar import pyzbar
    except ImportError:
        _w("\n  [!] Brak biblioteki 'pyzbar'. Zainstaluj: pip install pyzbar\n\n")
        return
    if not os.path.isfile(filepath):
        _w(f"\n  {_C.RED}[!] Plik nie istnieje: {filepath}{_C.RESET}\n\n")
        return
    try:
        img   = Image.open(filepath).convert("RGB")
        codes = pyzbar.decode(img)
    except Exception as e:
        _w(f"\n  {_C.RED}[!] Blad otwarcia obrazka: {e}{_C.RESET}\n\n")
        return
    if not codes:
        _w(f"\n  {_C.BYELLOW}[?] Nie znaleziono kodow w obrazku.{_C.RESET}\n\n")
        return
    _w(f"\n  {_C.BGREEN}[V] Znaleziono {len(codes)} kod(y):{_C.RESET}\n\n")
    for i, code in enumerate(codes, 1):
        data = code.data.decode("utf-8", errors="replace")
        _w(f"  {_C.BYELLOW}[{i}] Typ:{_C.RESET} {_C.BCYAN}{code.type}{_C.RESET}\n")
        _w(f"      {_C.BWHITE}{data}{_C.RESET}\n\n")


# ─── Schowek systemowy ────────────────────────────────────────────────────────

def _get_clipboard():
    _ensure_dependencies()
    try:
        import pyperclip
        return pyperclip.paste()
    except ImportError:
        pass
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            text = root.clipboard_get()
        except tk.TclError:
            text = None
        finally:
            root.destroy()
        return text
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            CF_UNICODETEXT = 13
            ctypes.windll.user32.OpenClipboard(0)
            handle = ctypes.windll.user32.GetClipboardData(CF_UNICODETEXT)
            text   = ctypes.wstring_at(handle) if handle else None
            ctypes.windll.user32.CloseClipboard()
            return text
        except Exception:
            pass
    return None


# ─── Menu ─────────────────────────────────────────────────────────────────────

def cml_menu():
    _w(f"\n{_C.BOLD}{_C.BCYAN}  +------------------------------------------+{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  |   Module: QR Generator v2.5              |{_C.RESET}\n")
    _w(f"{_C.BOLD}{_C.BCYAN}  +------------------------------------------+{_C.RESET}\n\n")
    cmds = [
        ("qr <txt> [flagi]",                    "Generuj QR (kolor: -r | tlo: -bw)"),
        ("qr file <path>",                      "Generuj QR dla sciezki pliku"),
        ("qr url <link>",                       "Generuj QR URL (auto https://)"),
        ("qr wifi <s> <p> [t]",                 "Generuj QR WiFi (WPA/WEP/nopass)"),
        ("qr email <a> [subj] [body]",          "Generuj QR mailto"),
        ("qr sms <nr> [tresc]",                 "Generuj QR smsto"),
        ("qr geo <lat> <lon>",                  "Generuj QR GPS (geo:lat,lon)"),
        ("qr contact <n> <t>",                  "Generuj QR vCard"),
        ("qr clip",                             "Generuj QR ze schowka systemowego"),
        ("qr decode <plik>",                    "Dekoduj QR/barcode z obrazka"),
        ("qr bar <typ> <data>",                 "Generuj Barcode (ean13, code128...)"),
        ("qr nfc <read|write|list> [txt]",      "Obsługa NFC: read/write/list rekordow"),
        ("qr save <t> <p> [--bar <t>|--png]",  "Zapisz kod do pliku"),
        ("qr history [N|clear]",                "Historia kodow; N = ponowny render"),
        ("qr otp <secret> [n] [wyd]",           "QR TOTP dla 2FA (Google Auth itp.)"),
        ("qr multi <plik.txt>",                 "Batch: QR dla kazdej linii pliku"),
        ("qr help",                             "Wyswietla to menu"),
    ]
    for c, d in cmds:
        _w(f"  {_C.BYELLOW}{c:<42}{_C.RESET} {_C.DIM}{d}{_C.RESET}\n")
    _w(f"\n  {_C.DIM}Flaga --half: kompaktowy render half-block (2x mniejszy){_C.RESET}\n")
    _w(f"  {_C.DIM}Komendy globalne: {_C.RESET}{_C.BYELLOW}qr  qrcode{_C.RESET}\n\n")


# ─── Parser flag ──────────────────────────────────────────────────────────────

def _parse_flags(args):
    fg_color = "\x1b[40m"
    bg_color = "\x1b[47m"
    half     = False
    clean    = []
    for a in args:
        if a in _C.FG_COLORS:
            fg_color = _C.FG_COLORS[a]
        elif a in _C.BG_QUIET_COLORS:
            bg_color = _C.BG_QUIET_COLORS[a]
        elif a == "--half":
            half = True
        else:
            clean.append(a)
    if fg_color == bg_color:
        fg_color = "\x1b[40m"
    return clean, fg_color, bg_color, half


# ─── Główna komenda ───────────────────────────────────────────────────────────

def cmd_qr(args, terminal):
    if not args:
        cml_menu(); return

    clean_args, fg_color, bg_color, half = _parse_flags(args)

    if not clean_args:
        cml_menu(); return

    sub  = clean_args[0].lower()
    rest = clean_args[1:]

    if sub == "help":
        cml_menu(); return

    # ── history ──────────────────────────────────────────────────────────────
    if sub == "history":
        cmd_history(rest, fg_color, bg_color, half)
        return

    # ── otp ──────────────────────────────────────────────────────────────────
    if sub == "otp":
        cmd_otp(rest, fg_color, bg_color, half)
        return

    # ── multi ─────────────────────────────────────────────────────────────────
    if sub == "multi":
        cmd_multi(rest, fg_color, bg_color, half)
        return

    # ── save ─────────────────────────────────────────────────────────────────
    if sub == "save":
        if len(rest) < 2:
            _w(f"\n  {_C.RED}[!] Uzycie: qr save <tekst> <plik> [--bar <typ>|--png]{_C.RESET}\n\n")
            return
        text, filename = rest[0], rest[1]
        save_rest = clean_args[3:]
        if "--bar" in save_rest:
            idx = save_rest.index("--bar")
            if idx + 1 >= len(save_rest):
                _w(f"  {_C.RED}[!] Podaj typ barcode po --bar{_C.RESET}\n\n"); return
            btype   = save_rest[idx + 1].lower()
            encoded = _make_barcode(btype, text)
            if encoded:
                try:
                    with open(filename, "w", encoding="utf-8") as f:
                        row  = encoded[0]
                        line = "".join("\u2588\u2588" if cell == "1" else "  " for cell in row)
                        for _ in range(6):
                            f.write(line + "\n")
                    _w(f"  {_C.BGREEN}[V] Barcode zapisano: {filename}{_C.RESET}\n\n")
                except Exception as e:
                    _w(f"  {_C.RED}[!] Blad zapisu: {e}{_C.RESET}\n\n")
            return
        if "--png" in save_rest:
            matrix = _make_matrix(text)
            if matrix and _save_qr_png(matrix, filename):
                _w(f"  {_C.BGREEN}[V] PNG zapisano: {filename}{_C.RESET}\n\n")
            return
        matrix = _make_matrix(text)
        if matrix is None: return
        try:
            with open(filename, "w", encoding="utf-8") as f:
                for row in matrix:
                    f.write("".join("\u2588\u2588" if cell else "  " for cell in row) + "\n")
            _w(f"  {_C.BGREEN}[V] QR zapisano: {filename}{_C.RESET}\n\n")
        except Exception as e:
            _w(f"  {_C.RED}[!] Blad zapisu: {e}{_C.RESET}\n\n")
        return

    # ── file ─────────────────────────────────────────────────────────────────
    if sub == "file":
        if not rest:
            _w(f"\n  {_C.RED}[!] Uzycie: qr file <sciezka>{_C.RESET}\n\n"); return
        path = os.path.abspath(rest[0])
        _w(f"\n  QR sciezka: {_C.BCYAN}{path}{_C.RESET}\n")
        render_qr_terminal(_make_matrix(path), fg_color, bg_color, half)
        _history_add("file", path)
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby przeslac sciezke.{_C.RESET}\n\n")
        return

    # ── url ──────────────────────────────────────────────────────────────────
    if sub == "url":
        if not rest:
            _w(f"\n  {_C.RED}[!] Uzycie: qr url <adres>{_C.RESET}\n\n"); return
        link = rest[0]
        if not link.startswith(("http://", "https://", "ftp://")):
            link = "https://" + link
        _w(f"\n  QR URL: {_C.BCYAN}{link}{_C.RESET}\n")
        render_qr_terminal(_make_matrix(link), fg_color, bg_color, half)
        _history_add("url", link)
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby otworzyc w przegladarce.{_C.RESET}\n\n")
        return

    # ── email ─────────────────────────────────────────────────────────────────
    if sub == "email":
        if not rest:
            _w(f"\n  {_C.RED}[!] Uzycie: qr email <adres> [temat] [tresc]{_C.RESET}\n\n"); return
        addr   = rest[0]
        params = []
        if len(rest) > 1: params.append(f"subject={rest[1]}")
        if len(rest) > 2: params.append(f"body={rest[2]}")
        mailto = "mailto:" + addr + ("?" + "&".join(params) if params else "")
        _w(f"\n  QR Email: {_C.BCYAN}{addr}{_C.RESET}\n")
        render_qr_terminal(_make_matrix(mailto), fg_color, bg_color, half)
        _history_add("email", mailto, addr)
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby otworzyc klienta pocztowego.{_C.RESET}\n\n")
        return

    # ── sms ──────────────────────────────────────────────────────────────────
    if sub == "sms":
        if not rest:
            _w(f"\n  {_C.RED}[!] Uzycie: qr sms <numer> [tresc]{_C.RESET}\n\n"); return
        nr   = rest[0]
        body = " ".join(rest[1:]) if len(rest) > 1 else ""
        sms  = f"smsto:{nr}:{body}" if body else f"smsto:{nr}"
        _w(f"\n  QR SMS: {_C.BCYAN}{nr}{_C.RESET}\n")
        render_qr_terminal(_make_matrix(sms), fg_color, bg_color, half)
        _history_add("sms", sms, nr)
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby otworzyc aplikacje SMS.{_C.RESET}\n\n")
        return

    # ── geo ──────────────────────────────────────────────────────────────────
    if sub == "geo":
        if len(rest) < 2:
            _w(f"\n  {_C.RED}[!] Uzycie: qr geo <lat> <lon>{_C.RESET}\n\n"); return
        try:
            lat, lon = float(rest[0]), float(rest[1])
        except ValueError:
            _w(f"\n  {_C.RED}[!] Wspolrzedne musza byc liczbami (np. 52.2297 21.0122){_C.RESET}\n\n"); return
        geo = f"geo:{lat},{lon}"
        _w(f"\n  QR GPS: {_C.BCYAN}{lat}, {lon}{_C.RESET}\n")
        render_qr_terminal(_make_matrix(geo), fg_color, bg_color, half)
        _history_add("geo", geo)
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby otworzyc lokalizacje w mapach.{_C.RESET}\n\n")
        return

    # ── wifi ─────────────────────────────────────────────────────────────────
    if sub == "wifi":
        if len(rest) < 2:
            _w(f"\n  {_C.RED}[!] Uzycie: qr wifi <SSID> <Haslo> [WPA|WEP|nopass]{_C.RESET}\n\n"); return
        ssid     = rest[0]
        pwd      = rest[1]
        security = rest[2].upper() if len(rest) > 2 else "WPA"
        wifi_str = (f"WIFI:S:{ssid};T:nopass;;" if security == "NOPASS"
                    else f"WIFI:S:{ssid};T:{security};P:{pwd};;")
        _w(f"\n  QR WiFi: {_C.BGREEN}{ssid}{_C.RESET}  [{_C.BYELLOW}{security}{_C.RESET}]\n")
        render_qr_terminal(_make_matrix(wifi_str), fg_color, bg_color, half)
        _history_add("wifi", wifi_str, f"WiFi:{ssid}")
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby polaczyc sie z siecia.{_C.RESET}\n\n")
        return

    # ── contact ───────────────────────────────────────────────────────────────
    if sub == "contact":
        if len(rest) < 2:
            _w(f"\n  {_C.RED}[!] Uzycie: qr contact <Imie> <Telefon>{_C.RESET}\n\n"); return
        name, phone = rest[0], rest[1]
        vcard = f"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:{name}\r\nN:{name};;;;\r\nTEL;TYPE=CELL:{phone}\r\nEND:VCARD"
        _w(f"\n  QR vCard: {_C.BGREEN}{name}{_C.RESET} ({phone})\n")
        render_qr_terminal(_make_matrix(vcard), fg_color, bg_color, half)
        _history_add("contact", vcard, f"{name} {phone}")
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby dodac do kontaktow.{_C.RESET}\n\n")
        return

    # ── clip ─────────────────────────────────────────────────────────────────
    if sub == "clip":
        text = _get_clipboard()
        if not text or not text.strip():
            _w(f"\n  {_C.RED}[!] Schowek jest pusty lub niedostepny.{_C.RESET}\n")
            _w("  Zainstaluj pyperclip: pip install pyperclip\n\n")
            return
        text    = text.strip()
        preview = text[:60] + "..." if len(text) > 60 else text
        _w(f"\n  QR ze schowka: {_C.BWHITE}{preview}{_C.RESET}\n")
        render_qr_terminal(_make_matrix(text), fg_color, bg_color, half)
        _history_add("clip", text)
        _w(f"  {_C.DIM}Wskazowka: Zeskanuj, aby przeniesc zawartosc schowka.{_C.RESET}\n\n")
        return

    # ── decode ────────────────────────────────────────────────────────────────
    if sub == "decode":
        if not rest:
            _w(f"\n  {_C.RED}[!] Uzycie: qr decode <plik.png|plik.jpg>{_C.RESET}\n\n"); return
        _decode_image(rest[0])
        return

    # ── bar ──────────────────────────────────────────────────────────────────
    if sub == "bar":
        if len(rest) < 2:
            _w(f"\n  {_C.RED}[!] Uzycie: qr bar <typ> <data>{_C.RESET}\n")
            _w("  Dostepne typy: ean13, code128, code39, itf, upca, etc.\n\n"); return
        btype, bdata = rest[0].lower(), rest[1]
        _w(f"\n  Barcode ({_C.BYELLOW}{btype}{_C.RESET}): {_C.BWHITE}{bdata}{_C.RESET}\n")
        render_barcode_terminal(_make_barcode(btype, bdata), fg_color, bg_color)
        _history_add("bar", f"{btype}:{bdata}", bdata)
        return

    # ── nfc ──────────────────────────────────────────────────────────────────
    if sub == "nfc":
        if not rest:
            _w(f"\n  {_C.RED}[!] Uzycie: qr nfc <read|write|list> [tekst]{_C.RESET}\n\n"); return
        nfc_sub = rest[0].lower()
        _ensure_dependencies()
        try:
            import nfc
        except ImportError:
            _w(f"\n  {_C.RED}[!] Brak 'nfcpy'. Zainstaluj: pip install nfcpy{_C.RESET}\n\n"); return

        def get_clf():
            try:
                return nfc.ContactlessFrontend('usb')
            except Exception as e:
                _w(f"  {_C.RED}[!] Blad czytnika NFC: {e}{_C.RESET}\n")
                return None

        if nfc_sub == "read":
            clf = get_clf()
            if not clf: return
            _w(f"\n  {_C.BCYAN}>>> Przyloz tag NFC...{_C.RESET}\n")
            try:
                def on_connect(tag):
                    _w(f"  {_C.BGREEN}[V] Tag: {tag}{_C.RESET}\n")
                    if tag.ndef:
                        for rec in tag.ndef.records:
                            _w(f"    - {rec}\n")
                    return True
                clf.connect(rdwr={'on-connect': on_connect})
            finally:
                clf.close()
            return

        # ── nfc list — szczegółowa lista rekordów NDEF ────────────────────────
        if nfc_sub == "list":
            clf = get_clf()
            if not clf: return
            _w(f"\n  {_C.BCYAN}>>> Przyloz tag NFC (odczyt rekordow)...{_C.RESET}\n")
            try:
                def on_connect_list(tag):
                    _nfc_list_records(tag)
                    return True
                clf.connect(rdwr={'on-connect': on_connect_list})
            finally:
                clf.close()
            return

        if nfc_sub == "write":
            if len(rest) < 2:
                _w(f"\n  {_C.RED}[!] Podaj tekst do zapisu.{_C.RESET}\n\n"); return
            txt = " ".join(rest[1:])
            clf = get_clf()
            if not clf: return
            _w(f"\n  {_C.BCYAN}>>> Przyloz tag, aby zapisac: '{txt}'...{_C.RESET}\n")
            try:
                import ndef
            except ImportError:
                _w(f"  {_C.RED}[!] Brak biblioteki 'ndef'. Zainstaluj: pip install ndeflib{_C.RESET}\n\n")
                clf.close()
                return
            try:
                def on_connect(tag):
                    if not tag.ndef:
                        _w(f"  {_C.RED}[!] Tag nie obsluguje NDEF.{_C.RESET}\n")
                        return False
                    tag.ndef.records = [ndef.TextRecord(txt)]
                    _w(f"  {_C.BGREEN}[V] Zapisano na tagu NFC!{_C.RESET}\n")
                    return True
                clf.connect(rdwr={'on-connect': on_connect})
            finally:
                clf.close()
            return

        _w(f"\n  {_C.RED}[!] Nieznana komenda NFC: '{nfc_sub}'. Uzyj: read | write | list{_C.RESET}\n\n")
        return

    # ── dowolny tekst ─────────────────────────────────────────────────────────
    text = " ".join(clean_args)
    _w(f"\n  QR: {_C.BWHITE}{text}{_C.RESET}\n")
    render_qr_terminal(_make_matrix(text), fg_color, bg_color, half)
    _history_add("text", text)
    _w(f"  {_C.DIM}Wskazowka: Zeskanuj telefonem bezposrednio z ekranu.{_C.RESET}\n\n")


# ─── Rejestr ──────────────────────────────────────────────────────────────────

CML_COMMANDS = {
    "qr":     cmd_qr,
    "qrcode": lambda args, term: cml_menu(),
    "nfc":    cmd_qr,
}


def on_load():
    _ensure_dependencies()

    # Jedyna twarda zależność: qrcode — bez niej komenda qr nie działa.
    # python-barcode, nfcpy, pyzbar, pyperclip, Pillow są opcjonalne:
    # brak którejś blokuje tylko konkretną subkomendę (bar/nfc/decode/clip/save --png).
    # Komunikat o brakach drukujemy tylko dla qrcode, reszta zgłasza się sama przy użyciu.
    try:
        __import__("qrcode")
    except ImportError:
        _w("  \x1b[91m[!] qr: brak biblioteki 'qrcode'\x1b[0m\n")
        if getattr(sys, 'frozen', False):
            _w("  Sugestia: Przebuduj aplikacje (build.bat).\n")
        else:
            _w("  Sugestia: pip install qrcode\n")


# ─── EcoSystem core integration ───────────────────────────────────────────────

def setup(terminal):
    """Rejestruje komendy qr/qrcode/nfc w TerminalX EcoSystem."""
    cat = terminal.t("cat_general")

    def _qr(args):
        cmd_qr(args, terminal)

    terminal.register_command(
        "qr", _qr,
        description=terminal.t("cmd_qr"),
        category=cat,
    )
    terminal.register_command(
        "qrcode", lambda args: cml_menu(),
        description=terminal.t("cmd_qrcode"),
        category=cat,
    )
    terminal.register_command(
        "nfc", _qr,
        description=terminal.t("cmd_nfc"),
        category=cat,
    )

    on_load()


def teardown(terminal):
    """Wyrejestrowuje komendy qr/qrcode/nfc z TerminalX EcoSystem."""
    for cmd in ("qr", "qrcode", "nfc"):
        terminal.commands.pop(cmd, None)
