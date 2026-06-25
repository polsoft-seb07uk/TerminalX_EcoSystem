#!/usr/bin/env python3
# autor:   Sebastian Januchowski
# company: polsoft.ITS(TM) Group
# web:     www.polsoft.gt.tc
# github:  https://github.com/seb07uk
# email:   polsoft.its@fastservice.com
# license: MIT
# crossterm: {"id": "14", "aliases": ["vdrive", "iso", "vhd"], "description": "Dyski wirtualne — ISO i VHD/VMDK/QCOW2, montowanie, szyfrowanie", "version": "1.1.0", "author": "Sebastian Januchowski"}
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    PyTermOS EcoSystem v2.0.0.0                               ║
║                  VDRIVE Module (core)                                        ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Version     : 1.1.0                                                         ║
║  Type        : core module                                                   ║
║  Created     : 2026-04-27                                                    ║
║  Moved to core: 2026-06-25 — pełna integracja z resztą EcoSystemu            ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Author      : Sebastian Januchowski                                         ║
║  Company     : polsoft.ITS™ Group                                            ║
║  Web         : www.polsoft.gt.tc                                              ║
║  GitHub      : https://github.com/seb07uk                                    ║
║  E-mail      : polsoft.its@fastservice.com                                   ║
╠══════════════════════════════════════════════════════════════════════════════╣
║  Description:                                                                ║
║    Full management of ISO images and virtual hard disks (VHD/VHDX/VMDK/     ║
║    QCOW2/VDI/RAW). Create, inspect, extract, mount, convert, resize,         ║
║    compact, snapshot, clone, merge, encrypt, and check integrity.           ║
║                                                                                ║
║    Integracja z EcoSystemem (przez core/_integration.py):                    ║
║      - defender  : skan bezpieczeństwa przed montowaniem obrazów             ║
║      - sha256    : delegacja zapisu/odczytu sum kontrolnych                  ║
║      - trash     : bezpieczne usuwanie dysków (kosz, zamiast rm -f)          ║
║      - notify    : powiadomienia o tworzeniu/montowaniu/szyfrowaniu          ║
║      - debugger  : log zdarzeń bezpieczeństwa (szyfrowanie, integralność)    ║
║    vdrive rejestruje też własne API w _integration, aby inne moduły         ║
║    (monitor, docs, search) mogły odpytać o aktywne montowania bez           ║
║    bezpośredniego importu.                                                   ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

# ══════════════════════════════════════════════════════════════════════════════
#  MODULE METADATA  (wymagane przez core/modmenu.py przy komendzie '??')
# ══════════════════════════════════════════════════════════════════════════════

MODULE_CMD            = "vdrive"
MODULE_DESCRIPTION    = "Dyski wirtualne — ISO i VHD/VMDK/QCOW2, montowanie, szyfrowanie"
MODULE_DESCRIPTION_EN = "Virtual drives — ISO and VHD/VMDK/QCOW2, mounting, encryption"
MODULE_VERSION        = "1.1.0"

METADATA = {
    "name"       : "vdrive",
    "version"    : "1.1.0",
    "author"     : "Sebastian Januchowski",
    "company"    : "polsoft.ITS(TM) Group",
    "web"        : "www.polsoft.gt.tc",
    "github"     : "https://github.com/seb07uk",
    "email"      : "polsoft.its@fastservice.com",
    "description": "Virtual Drive Manager - ISO and VHD/VHDX/VMDK/QCOW2/VDI/RAW management",
    "type"       : "core",
    "depends"    : ["qemu-img", "genisoimage", "isoinfo", "fuseiso", "7z"],
    "exports"    : ["VirtualDriveManager", "AsyncVirtualDriveManager"],
    "min_pyterm" : "2.0.0",
}

import os
import sys
import json
import shutil
import struct
import hashlib
import subprocess
import platform
import tempfile
import datetime
import re
import mmap
import concurrent.futures
from typing import Optional, Dict, List, Tuple
import asyncio
from pathlib import Path

from ._shared import (
    ROOT_DIR, CACHE_DIR, TRASH_DIR, IS_WIN, IS_LIN, IS_MAC,
    RST, BOLD, DIM, YLW, ORG, RED, GRN, CYN, BCYN, MGT, BLU, WHT,
    _w, _strip, _pad,
)
from . import _integration

# Katalog stanu vdrive — pod ROOT_DIR/.cache/vdrive, zgodnie z konwencją
# pozostałych modułów (defender, docs, pkg, scripts, sha256...) zamiast
# starego HOME/.t_vdrives używanego gdy moduł żył w modules/.
VDRIVE_STATE_DIR = os.path.join(CACHE_DIR, "vdrive")

# --- Rich Progress Support ---
try:
    from rich.progress import (
        Progress, SpinnerColumn, TextColumn, BarColumn, 
        TaskProgressColumn, TimeRemainingColumn, DownloadColumn
    )
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# Import async operations if available
try:
    from terminal_core.async_operations import async_manager, create_async_task_id
    from terminal_core.performance_tuning import performance_monitor
    ASYNC_AVAILABLE = True
except ImportError:
    ASYNC_AVAILABLE = False


# ---------------------------------------------------------------------------
# Integracja z EcoSystemem (przez core._integration)
# ---------------------------------------------------------------------------
# Wzorzec identyczny jak w core/imgtools.py — moduły komunikują się przez
# centralny rejestr _integration, bez bezpośrednich importów (brak cykli).

def _defender_ok(path: str) -> bool:
    """Sprawdza obraz/dysk przez defendera przed montowaniem.

    Zwraca True jeśli plik jest bezpieczny LUB defender nie jest załadowany
    (nie blokujemy operacji, gdy moduł bezpieczeństwa jest wyłączony).
    """
    return _integration.defender_scan_file(path)


def _sha256_stamp(path: str) -> Optional[str]:
    """Oblicza SHA-256 pliku delegując do core/sha256.py (z fallbackiem)."""
    return _integration.compute_sha256(path)


def _vdrive_notify(terminal, message: str, kind: str = "ok", title: str = "VDRIVE") -> None:
    """Wysyła powiadomienie (chmurkę) o zdarzeniu dysku wirtualnego."""
    _integration.notify_event(terminal, message, kind=kind, title=title, compact=True)


def _vdrive_log(terminal, kind: str, message: str) -> None:
    """Loguje zdarzenie do debuggera (jeśli załadowany)."""
    _integration.log_debug_event(terminal, kind, message)


def _trash_move(path: str):
    """Przenosi plik do .trash przez moduł trash (lub bezpośrednio jako fallback).

    Używane przez vhd-delete (bez --wipe) tak, aby usunięte dyski wirtualne
    trafiały do kosza EcoSystemu zamiast być trwale usuwane, zgodnie z resztą
    ekosystemu (command.py, docs.py, imgtools.py robią to samo).
    Zwraca (True, dst_path) lub (False, error_msg).
    """
    from . import _integration as _intg
    ok = _intg.trash_move(path)
    return (ok, path if ok else "przeniesienie do kosza nie powiodło się")



def _run(cmd: List[str], env: Optional[dict] = None,
         cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Run subprocess; return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError as e:
        return 1, "", f"Narzędzie niedostępne: {e}"
    except Exception as e:
        return 1, "", str(e)


def _require_tool(name: str) -> Tuple[bool, str]:
    if shutil.which(name):
        return True, ""
    return False, f"❌ Wymagane narzędzie '{name}' nie jest zainstalowane."


def _size_human(bytes_: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} PB"


def _parse_size(s: str) -> int:
    """Parse '100M', '2G', '500K', '1024' → bytes."""
    s = s.strip().upper()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    for suffix, mult in units.items():
        if s.endswith(suffix):
            return int(s[:-1]) * mult
    return int(s)


class AsyncVirtualDriveManager:
    """Async version of VirtualDriveManager with performance monitoring"""
    
    def __init__(self):
        self._manager = None  # Will be set later
        self._async_available = ASYNC_AVAILABLE
    
    def set_manager(self, manager):
        """Set the sync manager instance"""
        self._manager = manager
    
    async def cmd_iso_create_async(self, args: List[str]) -> str:
        """Async ISO creation with progress tracking"""
        if not self._async_available:
            return self._manager.cmd_iso_create(args)
        
        task_id = create_async_task_id()
        
        async def create_iso():
            if len(args) < 2:
                return "Uycie: vdrive iso-create <output.iso> <katalog_ródowy> [--label ETYKIETA] [--joliet] [--rockridge]"
            
            output = self._manager._abs(args[0])
            source = self._manager._abs(args[1])
            
            if not os.path.isdir(source):
                return f" Katalog ródowy '{source}' nie istnieje."
            
            # Record task start
            if ASYNC_AVAILABLE and performance_monitor:
                performance_monitor.record_task_start(task_id)
            
            try:
                # Parse arguments
                label = "CDROM"
                joliet = False
                rockridge = False
                
                i = 2
                while i < len(args):
                    if args[i] == "--label" and i + 1 < len(args):
                        label = args[i + 1]; i += 2
                    elif args[i] == "--joliet":
                        joliet = True; i += 1
                    elif args[i] == "--rockridge":
                        rockridge = True; i += 1
                    else:
                        i += 1
                
                # Build command
                tool = "genisoimage" if shutil.which("genisoimage") else "mkisofs"
                cmd = [tool, "-o", output, "-V", label]
                if joliet:
                    cmd += ["-J"]
                if rockridge:
                    cmd += ["-r"]
                cmd.append(source)
                
                # Execute asynchronously
                code, out, err = await _run_async(cmd)
                
                if code != 0:
                    return f" Bd tworzenia ISO:\n{err or out}"
                
                size = os.path.getsize(output)
                result = (
                    " Plik ISO utworzony!\n"
                    f"   Plik    : {output}\n"
                    f"   Rozmiar : {_size_human(size)}\n"
                    f"   Etykieta: {label}"
                )
                
                # Record task completion
                if ASYNC_AVAILABLE and performance_monitor:
                    performance_monitor.record_task_completion(task_id, True)
                
                return result
                
            except Exception as e:
                if ASYNC_AVAILABLE and performance_monitor:
                    performance_monitor.record_task_completion(task_id, False)
                return f" Bd: {e}"
        
        # Execute async task
        if self._async_available and async_manager:
            _ = await async_manager.submit_task(
                task_id=task_id,
                name=f"iso_create_{Path(args[0]).name if args else 'unknown'}",
                coro=create_iso(),
                metadata={'operation': 'iso_create', 'args': args}
            )
            
            completed_task = await async_manager.wait_for_task(task_id)
            return completed_task.result if completed_task.status == 'completed' else f" Bd: {completed_task.error}"
        else:
            return await create_iso()
    
    async def cmd_vhd_create_async(self, args: List[str]) -> str:
        """Async VHD creation with progress tracking"""
        if not self._async_available:
            return self._manager.cmd_vhd_create(args)
        
        task_id = create_async_task_id()
        
        async def create_vhd():
            if len(args) < 2:
                return ("Uycie: vdrive vhd-create <plik> <rozmiar> "
                        "[--format vhd|vhdx|qcow2|vmdk|vdi|raw] "
                        "[--prealloc] [--backing <base_file>]")
            
            path = self._manager._abs(args[0])
            size_str = args[1]
            
            # Record task start
            if ASYNC_AVAILABLE and performance_monitor:
                performance_monitor.record_task_start(task_id)
            
            try:
                # Parse arguments
                fmt = None
                prealloc = False
                backing = None
                
                i = 2
                while i < len(args):
                    if args[i] in ("--format", "-") and i + 1 < len(args):
                        fmt = args[i + 1].lower(); i += 2
                    elif args[i] == "--prealloc":
                        prealloc = True; i += 1
                    elif args[i] == "--backing" and i + 1 < len(args):
                        backing = self._manager._abs(args[i + 1]); i += 2
                    else:
                        i += 1
                
                # Determine format
                if fmt is None:
                    ext = Path(path).suffix.lstrip(".").lower()
                    fmt = ext if ext in self._manager.SUPPORTED_VHD_FORMATS else "vhd"
                
                qfmt = self._manager.SUPPORTED_VHD_FORMATS.get(fmt, fmt)
                
                # Build command
                cmd = ["qemu-img", "create", "-", qfmt]
                
                if backing:
                    if not os.path.isfile(backing):
                        return f" Plik bazowy '{backing}' nie istnieje."
                    back_fmt = self._manager._qemu_fmt(backing)
                    cmd += ["-b", backing, "-F", back_fmt]
                
                if prealloc:
                    if qfmt == "qcow2":
                        cmd += ["-o", "preallocation=full"]
                    elif qfmt in ("raw", "vpc"):
                        cmd += ["-o", "preallocation=full"]
                
                cmd += [path, size_str]
                
                # Execute asynchronously
                code, out, err = await _run_async(cmd)
                
                if code != 0:
                    return f" Bd tworzenia dysku:\n{err or out}"
                
                # Get info
                info = self._manager._qemu_info(path)
                vsize = info.get("virtual-size", 0)
                asize = info.get("actual-size", info.get("disk-size", 0))
                
                result = (
                    " Wirtualny dysk utworzony!\n"
                    f"   Plik           : {path}\n"
                    f"   Format         : {qfmt} (.{fmt})\n"
                    f"   Rozmiar wirtualny: {_size_human(vsize)}\n"
                    f"   Rozmiar na dysku : {_size_human(asize)}\n"
                    + (f"   Plik bazowy    : {backing}\n" if backing else "")
                )
                
                # Record task completion
                if ASYNC_AVAILABLE and performance_monitor:
                    performance_monitor.record_task_completion(task_id, True)
                
                return result
                
            except Exception as e:
                if ASYNC_AVAILABLE and performance_monitor:
                    performance_monitor.record_task_completion(task_id, False)
                return f" Bd: {e}"
        
        # Execute async task
        if self._async_available and async_manager:
            _ = await async_manager.submit_task(
                task_id=task_id,
                name=f"vhd_create_{Path(args[0]).name if args else 'unknown'}",
                coro=create_vhd(),
                metadata={'operation': 'vhd_create', 'args': args}
            )
            
            completed_task = await async_manager.wait_for_task(task_id)
            return completed_task.result if completed_task.status == 'completed' else f" Bd: {completed_task.error}"
        else:
            return await create_vhd()
    
    async def cmd_vhd_convert_async(self, args: List[str]) -> str:
        """Async VHD conversion with progress tracking"""
        if not self._async_available:
            return self._manager.cmd_vhd_convert(args)
        
        task_id = create_async_task_id()
        
        async def convert_vhd():
            if len(args) < 2:
                return ("Uycie: vdrive vhd-convert <ród> <cel> "
                        "[--format vhd|vhdx|qcow2|vmdk|vdi|raw] [--compress]")
            
            src = self._manager._abs(args[0])
            dst = self._manager._abs(args[1])
            compress = "--compress" in args
            dst_fmt = None
            
            # Record task start
            if ASYNC_AVAILABLE and performance_monitor:
                performance_monitor.record_task_start(task_id)
            
            try:
                # Parse arguments
                i = 2
                while i < len(args):
                    if args[i] in ("--format", "-") and i + 1 < len(args):
                        dst_fmt = args[i + 1].lower(); i += 2
                    else:
                        i += 1
                
                # Determine formats
                src_fmt = self._manager._qemu_fmt(src)
                if dst_fmt is None:
                    ext = Path(dst).suffix.lstrip(".").lower()
                    dst_fmt = ext if ext in self._manager.SUPPORTED_VHD_FORMATS else "qcow2"
                dst_qfmt = self._manager.SUPPORTED_VHD_FORMATS.get(dst_fmt, dst_fmt)
                
                # Build command
                cmd = ["qemu-img", "convert", "-", src_fmt, "-O", dst_qfmt]
                if compress and dst_qfmt in ("qcow2", "qcow"):
                    cmd.append("-c")
                cmd += [src, dst]
                
                # Execute asynchronously
                code, out, err = await _run_async(cmd)
                
                if code != 0:
                    return f" Bd konwersji:\n{err or out}"
                
                # Calculate statistics
                src_size = os.path.getsize(src)
                dst_size = os.path.getsize(dst)
                ratio = (1 - dst_size / src_size) * 100 if src_size else 0
                
                result = (
                    " Konwersja zakoczona!\n"
                    f"   Ród  : {src} ({_size_human(src_size)}, {src_fmt})\n"
                    f"   Cel   : {dst} ({_size_human(dst_size)}, {dst_qfmt})\n"
                    f"   Oszczdno: {ratio:.1f}%"
                )
                
                # Record task completion
                if ASYNC_AVAILABLE and performance_monitor:
                    performance_monitor.record_task_completion(task_id, True)
                
                return result
                
            except Exception as e:
                if ASYNC_AVAILABLE and performance_monitor:
                    performance_monitor.record_task_completion(task_id, False)
                return f" Bd: {e}"
        
        # Execute async task
        if self._async_available and async_manager:
            _ = await async_manager.submit_task(
                task_id=task_id,
                name=f"vhd_convert_{Path(args[0]).name if args else 'unknown'}",
                coro=convert_vhd(),
                metadata={'operation': 'vhd_convert', 'args': args}
            )
            
            completed_task = await async_manager.wait_for_task(task_id)
            return completed_task.result if completed_task.status == 'completed' else f" Bd: {completed_task.error}"
        else:
            return await convert_vhd()

    async def cmd_vhd_compact_async(self, args: List[str]) -> str:
        """Async VHD compaction — runs qemu-img convert in a thread so terminal stays responsive."""
        if not args:
            return "Użycie: vhd compact <plik>"
        path = self._manager._abs(args[0])
        ok, msg = self._manager._require_file(path)
        if not ok:
            return msg
        ok2, msg2 = _require_tool("qemu-img")
        if not ok2:
            return msg2

        size_before = os.path.getsize(path)
        fmt = self._manager._qemu_fmt(path)
        tmp = path + ".compact.tmp"
        cmd = ["qemu-img", "convert", "-p", "-O", fmt, path, tmp]

        loop = asyncio.get_event_loop()
        code, out, err = await loop.run_in_executor(
            self._manager._executor,
            lambda: _run(cmd)
        )

        if code != 0:
            if os.path.exists(tmp):
                os.remove(tmp)
            return f"❌ Błąd kompaktowania:\n{err}"

        os.replace(tmp, path)
        size_after = os.path.getsize(path)
        saved = size_before - size_after
        return (
            "✅ Kompaktowanie zakończone!\n"
            f"   Plik         : {path}\n"
            f"   Przed        : {_size_human(size_before)}\n"
            f"   Po           : {_size_human(size_after)}\n"
            f"   Zaoszczędzono: {_size_human(saved)}"
        )

    async def cmd_vhd_check_async(self, args: List[str]) -> str:
        """Async VHD integrity check / repair — runs qemu-img check in a thread."""
        if not args:
            return "Użycie: vhd check <plik> [--repair]"
        path = self._manager._abs(args[0])
        ok, msg = self._manager._require_file(path)
        if not ok:
            return msg
        ok2, msg2 = _require_tool("qemu-img")
        if not ok2:
            return msg2

        repair = "--repair" in args
        cmd = ["qemu-img", "check"]
        if repair:
            cmd += ["-r", "all"]
        cmd.append(path)

        loop = asyncio.get_event_loop()
        code, out, err = await loop.run_in_executor(
            self._manager._executor,
            lambda: _run(cmd)
        )
        combined = (out + "\n" + err).strip()

        if code == 0:
            return (
                f"✅ Dysk '{os.path.basename(path)}' — OK\n"
                + (combined if combined else "Brak błędów.")
            )
        return (
            f"⚠️  Problemy w '{os.path.basename(path)}':\n{combined}\n"
            + ("Spróbuj: vhd check <plik> --repair" if not repair else "")
        )

    async def cmd_iso_checksum_async(self, args: List[str]) -> str:
        """Async checksum computation — offloads hashing to thread pool so terminal is responsive."""
        if not args:
            return "Użycie: iso checksum <plik.iso> [--sha256]"
        path = self._manager._abs(args[0])
        ok, msg = self._manager._require_file(path)
        if not ok:
            return msg

        use_sha = "--sha256" in args
        reader = ISOReader(path)

        loop = asyncio.get_event_loop()
        if use_sha:
            checksum = await loop.run_in_executor(self._manager._executor, reader.sha256)
            algo = "SHA-256"
        else:
            checksum = await loop.run_in_executor(self._manager._executor, reader.md5)
            algo = "MD5"

        return (
            f"🔒 {algo} checksum:\n"
            f"   Plik : {path}\n"
            f"   Hash : {checksum}"
        )

    async def cmd_vhd_delete_async(self, args: List[str]) -> str:
        """Async secure delete — offloads DOD wipe to thread pool."""
        if not args:
            return "Użycie: vhd delete <plik> [--force] [--wipe] [--passes N]"
        path = self._manager._abs(args[0])
        force = "--force" in args
        wipe = "--wipe" in args

        passes = 1
        if "--passes" in args:
            try:
                idx = args.index("--passes")
                passes = int(args[idx + 1])
            except (ValueError, IndexError):
                pass

        ok, msg = self._manager._require_file(path)
        if not ok:
            return msg

        if not force:
            size = os.path.getsize(path)
            wipe_msg = f" (BEZPIECZNE NADPISYWANIE - {passes} przebiegów)" if wipe else ""
            return (
                f"⚠️  Usuń '{os.path.basename(path)}' ({_size_human(size)}){wipe_msg}?\n"
                f"Potwierdź: vhd delete {args[0]} --force {'--wipe' if wipe else ''}"
            )

        mp = self._manager._mounts.find_by_image(path)
        if mp:
            return f"❌ Dysk jest zamontowany w '{mp}'. Najpierw odmontuj: vhd umount {mp}"

        if wipe:
            import secrets as _secrets
            size = os.path.getsize(path)

            def _do_wipe():
                with open(path, "ba+", buffering=0) as f:
                    for p in range(1, passes + 1):
                        chunk_size = 1024 * 1024
                        if p == 1:
                            chunk_base = b'\x00'
                        elif p == 2:
                            chunk_base = b'\xff'
                        else:
                            chunk_base = None
                        if chunk_base:
                            chunk = chunk_base * chunk_size
                        f.seek(0)
                        written = 0
                        while written < size:
                            to_write = min(chunk_size, size - written)
                            f.write(_secrets.token_bytes(to_write) if not chunk_base else chunk[:to_write])
                            written += to_write
                    f.flush()
                    os.fsync(f.fileno())

            loop = asyncio.get_event_loop()
            try:
                await loop.run_in_executor(self._manager._executor, _do_wipe)
            except Exception as e:
                return f"❌ Błąd bezpiecznego usuwania: {e}"

        os.remove(path)
        wipe_note = f" (bezpiecznie nadpisano {passes} przebieg{'ami' if passes != 1 else 'iem'})" if wipe else ""
        return f"✅ Usunięto{wipe_note}: {path}"


def _run(cmd: List[str], env: Optional[dict] = None,
         cwd: Optional[str] = None) -> Tuple[int, str, str]:
    """Run subprocess; return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=cwd)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError as e:
        return 1, "", f"Narzędzie niedostępne: {e}"
    except Exception as e:
        return 1, "", str(e)


def _require_tool(name: str) -> Tuple[bool, str]:
    if shutil.which(name):
        return True, ""
    return False, f"❌ Wymagane narzędzie '{name}' nie jest zainstalowane."


def _size_human(bytes_: int) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if bytes_ < 1024:
            return f"{bytes_:.1f} {unit}"
        bytes_ /= 1024
    return f"{bytes_:.1f} PB"


def _parse_size(s: str) -> int:
    """Parse '100M', '2G', '500K', '1024' → bytes."""
    s = s.strip().upper()
    units = {"K": 1024, "M": 1024**2, "G": 1024**3, "T": 1024**4}
    for suffix, mult in units.items():
        if s.endswith(suffix):
            return int(s[:-1]) * mult
    return int(s)


# ---------------------------------------------------------------------------
# ISO reader (pure Python — no external dep)
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# ISO reader (pure Python — no external dep)
# ---------------------------------------------------------------------------

class ISOReader:
    """
    Minimal ISO 9660 reader.
    Reads the Primary Volume Descriptor and directory tree from an ISO file.
    """

    SECTOR = 2048
    PVD_SECTOR = 16

    def __init__(self, path: str):
        self.path = path
        self._pvd: Optional[dict] = None

    def _read_sector(self, n: int, f) -> bytes:
        f.seek(n * self.SECTOR)
        return f.read(self.SECTOR)

    def read_pvd(self) -> dict:
        """Parse Primary Volume Descriptor (ISO 9660)."""
        if self._pvd:
            return self._pvd
        try:
            with open(self.path, "rb") as f:
                sector = self._read_sector(self.PVD_SECTOR, f)
                if len(sector) < 2048:
                    return {}
                vd_type = sector[0]
                identifier = sector[1:6].decode("ascii", errors="replace")
                if identifier != "CD001":
                    return {}
                pvd = {
                    "type":            vd_type,
                    "volume_id":       sector[40:72].decode("ascii", errors="replace").strip(),
                    "volume_set_id":   sector[190:318].decode("ascii", errors="replace").strip(),
                    "publisher":       sector[318:446].decode("ascii", errors="replace").strip(),
                    "data_preparer":   sector[446:574].decode("ascii", errors="replace").strip(),
                    "application":     sector[574:702].decode("ascii", errors="replace").strip(),
                    "volume_size_lba": struct.unpack_from("<I", sector, 80)[0],
                    "sector_size":     struct.unpack_from("<H", sector, 128)[0],
                    "logical_block_size": struct.unpack_from("<H", sector, 128)[0],
                    "creation_date":   sector[813:830].decode("ascii", errors="replace").strip(),
                    "modification_date": sector[830:847].decode("ascii", errors="replace").strip(),
                }
                pvd["total_size_bytes"] = pvd["volume_size_lba"] * self.SECTOR
                self._pvd = pvd
                return pvd
        except Exception as e:
            return {"error": str(e)}

    def list_files(self, max_files: int = 200) -> List[str]:
        """List files in ISO using isoinfo (if available) or pure-Python walk."""
        ok, _ = _require_tool("isoinfo")
        if ok:
            code, out, err = _run(["isoinfo", "-", "-i", self.path])
            if code == 0:
                return out.splitlines()[:max_files]

        # Fallback: pure Python directory entry walk
        files: List[str] = []
        try:
            with open(self.path, "rb") as f:
                pvd = self.read_pvd()
                if not pvd or "error" in pvd:
                    return []
                # Root directory record is at offset 156 in PVD
                f.seek(self.PVD_SECTOR * self.SECTOR + 156)
                root_dr = f.read(34)
                if len(root_dr) < 34:
                    return []
                root_lba = struct.unpack_from("<I", root_dr, 2)[0]
                root_size = struct.unpack_from("<I", root_dr, 10)[0]
                self._walk_dir(f, root_lba, root_size, "/", files, max_files)
        except Exception:
            pass
        return files

    def _walk_dir(self, f, lba: int, size: int, prefix: str,
                  out: List[str], max_files: int):
        if len(out) >= max_files:
            return
        try:
            f.seek(lba * self.SECTOR)
            data = f.read(size)
            pos = 0
            while pos < len(data) and len(out) < max_files:
                dr_len = data[pos]
                if dr_len == 0:
                    pos = (pos // self.SECTOR + 1) * self.SECTOR
                    if pos >= len(data):
                        break
                    continue
                flags = data[pos + 25]
                name_len = data[pos + 32]
                name_raw = data[pos + 33: pos + 33 + name_len]
                try:
                    name = name_raw.decode("ascii", errors="replace").split(";")[0]
                except Exception:
                    name = "?"

                if name not in ("", "\x00", "\x01"):
                    full = prefix.rstrip("/") + "/" + name
                    if flags & 0x02:   # directory
                        child_lba  = struct.unpack_from("<I", data, pos + 2)[0]
                        child_size = struct.unpack_from("<I", data, pos + 10)[0]
                        if child_lba != lba:  # avoid infinite loop
                            self._walk_dir(f, child_lba, child_size,
                                           full + "/", out, max_files)
                    else:
                        out.append(full)
                pos += dr_len
        except Exception:
            pass

    def extract_file(self, iso_path: str, dest_path: str) -> Tuple[bool, str]:
        """Extract one file from ISO. Requires isoinfo."""
        ok, msg = _require_tool("isoinfo")
        if not ok:
            return False, msg
        code, out, err = _run(
            ["isoinfo", "-i", self.path, "-x", iso_path])
        if code != 0:
            return False, f"Błąd ekstrakcji: {err}"
        try:
            with open(dest_path, "wb") as df:
                df.write(out.encode("latin-1"))
            return True, dest_path
        except Exception as e:
            return False, str(e)

    def md5(self) -> str:
        h = hashlib.md5()
        return self._hash_with_progress(h, "MD5")

    def sha256(self) -> str:
        h = hashlib.sha256()
        return self._hash_with_progress(h, "SHA256")

    def _hash_with_progress(self, hasher, label: str) -> str:
        try:
            total_size = os.path.getsize(self.path)
            if total_size == 0:
                return hasher.hexdigest()

            chunk_size = 1024 * 1024 # 1MB chunks
            
            with open(self.path, "rb") as f:
                # Use mmap for large files if possible
                mm = None
                try:
                    if total_size > 10 * 1024 * 1024: # > 10MB
                        mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                except Exception:
                    mm = None

                if RICH_AVAILABLE:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn(f"[bold cyan]{label}[/bold cyan] {Path(self.path).name}"),
                        BarColumn(),
                        DownloadColumn(),
                        TaskProgressColumn(),
                        TimeRemainingColumn(),
                        transient=True
                    ) as progress:
                        task = progress.add_task("Hashing...", total=total_size)
                        
                        if mm:
                            pos = 0
                            while pos < total_size:
                                end = min(pos + chunk_size, total_size)
                                hasher.update(mm[pos:end])
                                progress.update(task, advance=end-pos)
                                pos = end
                        else:
                            while chunk := f.read(chunk_size):
                                hasher.update(chunk)
                                progress.update(task, advance=len(chunk))
                else:
                    if mm:
                        pos = 0
                        while pos < total_size:
                            end = min(pos + chunk_size, total_size)
                            hasher.update(mm[pos:end])
                            pos = end
                    else:
                        while chunk := f.read(chunk_size):
                            hasher.update(chunk)
                
                if mm:
                    mm.close()

            return hasher.hexdigest()
        except Exception as e:
            return f"error: {e}"


# ---------------------------------------------------------------------------
# Mount tracker
# ---------------------------------------------------------------------------

class MountRegistry:
    """Tracks active mounts across commands (in-memory + JSON file)."""

    def __init__(self, state_dir: str):
        self._path = os.path.join(state_dir, ".vdrive_mounts.json")
        self._mounts: Dict[str, dict] = {}
        self._load()

    def _load(self):
        try:
            with open(self._path) as f:
                self._mounts = json.load(f)
        except Exception:
            self._mounts = {}

    def _save(self):
        try:
            with open(self._path, "w") as f:
                json.dump(self._mounts, f, indent=2)
        except Exception:
            pass

    def add(self, image: str, mountpoint: str, kind: str, loop_dev: str = ""):
        self._mounts[mountpoint] = {
            "image": image,
            "kind": kind,
            "loop_dev": loop_dev,
            "mounted_at": datetime.datetime.now().isoformat(),
        }
        self._save()

    def remove(self, mountpoint: str):
        self._mounts.pop(mountpoint, None)
        self._save()

    def all(self) -> Dict[str, dict]:
        return dict(self._mounts)

    def find_by_image(self, image: str) -> Optional[str]:
        for mp, info in self._mounts.items():
            if info["image"] == os.path.abspath(image):
                return mp
        return None


# ---------------------------------------------------------------------------
# Main manager
# ---------------------------------------------------------------------------

class VirtualDriveManager:
    """
    Full ISO + VHD/VHDX/VMDK/QCOW2/VDI/RAW virtual drive manager.
    All public cmd_* methods return printable strings.
    """

    SUPPORTED_VHD_FORMATS = {
        "vhd":   "vpc",     # VHD (Virtual PC / Hyper-V legacy)
        "vhdx":  "vhdx",    # VHDX (Hyper-V modern)
        "qcow2": "qcow2",   # QEMU Copy-On-Write v2
        "qcow":  "qcow",    # QEMU Copy-On-Write v1
        "vmdk":  "vmdk",    # VMware
        "vdi":   "vdi",     # VirtualBox
        "raw":   "raw",     # Raw disk image
        "img":   "raw",
    }

    # Formats that support snapshots natively in qemu-img
    SNAPSHOT_FORMATS = {"qcow2", "qcow"}

    def __init__(self):
        self._root = VDRIVE_STATE_DIR
        os.makedirs(self._root, exist_ok=True)
        self._mounts = MountRegistry(self._root)
        self._system = platform.system()
        self._executor = concurrent.futures.ThreadPoolExecutor(max_workers=4)
        # Referencja do instancji terminala — ustawiana w setup(); pozwala
        # metodom cmd_* wywoływać notify/debugger bez przekazywania jej
        # jako dodatkowego argumentu w każdym wywołaniu.
        self.terminal = None

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _abs(self, path: str) -> str:
        return os.path.abspath(os.path.expanduser(path))

    def _qemu_fmt(self, path: str) -> str:
        """Derive qemu-img format string from file extension."""
        ext = Path(path).suffix.lstrip(".").lower()
        return self.SUPPORTED_VHD_FORMATS.get(ext, "raw")

    def _qemu_info(self, path: str) -> dict:
        ok, msg = _require_tool("qemu-img")
        if not ok:
            return {"error": msg}
        code, out, err = _run(["qemu-img", "info", "--output=json", path])
        if code != 0:
            return {"error": err}
        try:
            return json.loads(out)
        except Exception:
            return {"error": f"JSON parse error: {out}"}

    def _check_path_free(self, path: str) -> Tuple[bool, str]:
        if os.path.exists(path):
            return False, f"❌ Plik '{path}' już istnieje."
        return True, ""

    def _require_file(self, path: str) -> Tuple[bool, str]:
        if not os.path.isfile(path):
            return False, f"❌ Plik '{path}' nie istnieje."
        return True, ""

    def _format_qemu_info(self, info: dict) -> str:
        if "error" in info:
            return f"❌ {info['error']}"
        lines = []
        lines.append(f"  Format          : {info.get('format', '?')}")
        lines.append(f"  Rozmiar wirtualny: {_size_human(info.get('virtual-size', 0))}")
        lines.append(f"  Rozmiar na dysku : {_size_human(info.get('actual-size', info.get('disk-size', 0)))}")
        if "cluster-size" in info:
            lines.append(f"  Cluster size    : {_size_human(info['cluster-size'])}")
        if info.get("snapshots"):
            lines.append(f"  Snapshoty       : {len(info['snapshots'])}")
            for s in info["snapshots"]:
                lines.append(f"    [{s.get('id','?')}] {s.get('name','?')}  "
                             f"({s.get('date-sec','')})")
        if info.get("format-specific"):
            fs = info["format-specific"]
            typ = fs.get("type", "")
            data = fs.get("data", {})
            if typ == "qcow2":
                lines.append(f"  Compat          : {data.get('compat','?')}")
                lines.append(f"  Lazy refcounts  : {data.get('lazy-refcounts','?')}")
            elif typ == "vpc":
                lines.append(f"  Subformat       : {data.get('subformat','?')}")
        if info.get("backing-filename"):
            lines.append(f"  Backing file    : {info['backing-filename']}")
        if info.get("encrypt"):
            lines.append(f"  Szyfrowanie     : {info['encrypt'].get('format','?')}")
        return "\n".join(lines)

    def _run_with_rich_progress(self, cmd: List[str], description: str) -> Tuple[int, str, str]:
        """Runs a command and parses its progress output to display a Rich progress bar."""
        if not RICH_AVAILABLE:
            return _run(cmd)

        stdout_lines = []
        stderr_lines = []
        
        # Determine parser based on tool
        is_qemu = "qemu-img" in cmd[0]
        is_iso  = any(t in cmd[0] for t in ("genisoimage", "mkisofs"))
        
        with Progress(
            SpinnerColumn(),
            TextColumn(f"[bold blue]{description}[/bold blue]"),
            BarColumn(),
            TaskProgressColumn(),
            TimeRemainingColumn(),
            transient=True
        ) as progress:
            task = progress.add_task("Working...", total=100)
            
            # Start process with pipes
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True
            )
            
            # Helper to read stream without blocking
            import threading
            def read_stream(stream, lines_list, is_stderr=False):
                for line in iter(stream.readline, ''):
                    lines_list.append(line.strip())
                    # Parse progress
                    if is_qemu and "(" in line and "%" in line:
                        # qemu-img format: (12.34/100%)
                        match = re.search(r"\((\d+\.?\d*)/100%\)", line)
                        if match:
                            progress.update(task, completed=float(match.group(1)))
                    elif is_iso and "% done" in line:
                        # genisoimage format:  12.34% done, estimate finish...
                        match = re.search(r"(\d+\.?\d*)%", line)
                        if match:
                            progress.update(task, completed=float(match.group(1)))
                stream.close()

            t1 = threading.Thread(target=read_stream, args=(process.stdout, stdout_lines))
            t2 = threading.Thread(target=read_stream, args=(process.stderr, stderr_lines, True))
            t1.start()
            t2.start()
            
            process.wait()
            t1.join()
            t2.join()
            
            return process.returncode, "\n".join(stdout_lines), "\n".join(stderr_lines)

    # ------------------------------------------------------------------ #
    #  ISO commands                                                        #
    # ------------------------------------------------------------------ #

    def cmd_iso_create(self, args: List[str]) -> str:
        """
        vdrive iso-create <output.iso> <source_dir> [--label MYLABEL] [--joliet] [--rockridge]
        Tworzy plik ISO z katalogu.
        """
        if len(args) < 2:
            return "Użycie: vdrive iso-create <output.iso> <katalog_źródłowy> [--label ETYKIETA] [--joliet] [--rockridge]"

        ok, msg = _require_tool("genisoimage")
        if not ok:
            ok2, msg2 = _require_tool("mkisofs")
            if not ok2:
                return "❌ Wymagane narzędzie 'genisoimage' lub 'mkisofs' nie jest zainstalowane.\nZainstaluj: apt-get install genisoimage"
            tool = "mkisofs"
        else:
            tool = "genisoimage"

        output = self._abs(args[0])
        source = self._abs(args[1])
        label = "CDROM"
        joliet = False
        rockridge = False

        i = 2
        while i < len(args):
            if args[i] == "--label" and i + 1 < len(args):
                label = args[i + 1]; i += 2
            elif args[i] == "--joliet":
                joliet = True; i += 1
            elif args[i] == "--rockridge":
                rockridge = True; i += 1
            else:
                i += 1

        if not os.path.isdir(source):
            return f"❌ Katalog źródłowy '{source}' nie istnieje."

        ok2, msg2 = self._check_path_free(output)
        if not ok2:
            return msg2

        cmd = [tool, "-o", output, "-V", label]
        if joliet:
            cmd += ["-J"]
        if rockridge:
            cmd += ["-r"]
        cmd.append(source)

        if RICH_AVAILABLE:
            # genisoimage requires -quiet to not dump too much, 
            # but we want progress. It outputs progress to stderr.
            code, out, err = self._run_with_rich_progress(cmd, f"Creating ISO: {Path(output).name}")
        else:
            code, out, err = _run(cmd)

        if code != 0:
            err_msg = f"❌ Błąd tworzenia ISO:\n{err or out}"
            _vdrive_notify(self.terminal, f"Błąd tworzenia ISO '{Path(output).name}'", kind="err")
            return err_msg

        size = os.path.getsize(output)
        _vdrive_notify(self.terminal, f"ISO utworzone: {Path(output).name} ({_size_human(size)})", kind="ok")
        _vdrive_log(self.terminal, "INFO", f"vdrive: ISO utworzone {output}")
        return (
            "✅ Plik ISO utworzony!\n"
            f"   Plik    : {output}\n"
            f"   Rozmiar : {_size_human(size)}\n"
            f"   Etykieta: {label}"
        )

    def cmd_iso_info(self, args: List[str]) -> str:
        """
        vdrive iso-info <plik.iso>
        Wyświetla informacje o pliku ISO 9660.
        """
        if not args:
            return "Użycie: vdrive iso-info <plik.iso>"
        path = self._abs(args[0])
        ok, msg = self._require_file(path)
        if not ok:
            return msg

        reader = ISOReader(path)
        pvd = reader.read_pvd()
        size = os.path.getsize(path)

        if "error" in pvd:
            return f"⚠️  Nie można odczytać PVD ISO: {pvd['error']}\n   (plik może nie być ISO 9660)"

        lines = [f"==== ISO INFO: {os.path.basename(path)} ====\n"]
        lines.append(f"  Plik            : {path}")
        lines.append(f"  Rozmiar pliku   : {_size_human(size)}")
        lines.append(f"  Volume ID       : {pvd.get('volume_id','?')}")
        lines.append(f"  Volume Set      : {pvd.get('volume_set_id','')}")
        lines.append(f"  Publisher       : {pvd.get('publisher','')}")
        lines.append(f"  Aplikacja       : {pvd.get('application','')}")
        lines.append(f"  Data tworzenia  : {pvd.get('creation_date','?')}")
        lines.append(f"  Rozmiar wolumenu: {_size_human(pvd.get('total_size_bytes',0))}")
        lines.append(f"  Sektor          : {pvd.get('sector_size',2048)} B")
        return "\n".join(lines)

    def cmd_iso_list(self, args: List[str]) -> str:
        """
        vdrive iso-list <plik.iso> [--max N]
        Wyświetla zawartość ISO (drzewo plików).
        """
        if not args:
            return "Użycie: vdrive iso-list <plik.iso> [--max N]"
        path = self._abs(args[0])
        ok, msg = self._require_file(path)
        if not ok:
            return msg

        max_files = 200
        for i, a in enumerate(args):
            if a == "--max" and i + 1 < len(args):
                try:
                    max_files = int(args[i + 1])
                except ValueError:
                    pass

        reader = ISOReader(path)
        files = reader.list_files(max_files)

        if not files:
            return "ℹ️  Nie znaleziono plików lub nie można odczytać struktury ISO."

        lines = [f"==== ZAWARTOŚĆ ISO: {os.path.basename(path)} ====\n"]
        for f in files:
            lines.append(f"  {f}")
        if len(files) >= max_files:
            lines.append(f"\n  ... (limit {max_files} plików, użyj --max N)")
        lines.append(f"\nRazem: {len(files)} plików")
        return "\n".join(lines)

    def cmd_iso_extract(self, args: List[str]) -> str:
        """
        vdrive iso-extract <plik.iso> <dest_dir>
        Wypakowuje całą zawartość ISO do katalogu.
        """
        if len(args) < 2:
            return "Użycie: vdrive iso-extract <plik.iso> <katalog_docelowy>"
        path = self._abs(args[0])
        dest = self._abs(args[1])
        ok, msg = self._require_file(path)
        if not ok:
            return msg

        ok2, msg2 = _require_tool("isoinfo")
        if not ok2:
            # Fallback: 7z or bsdtar
            for tool in ("7z", "bsdtar"):
                if shutil.which(tool):
                    os.makedirs(dest, exist_ok=True)
                    if tool == "7z":
                        cmd = ["7z", "x", path, f"-o{dest}", "-y"]
                    else:
                        cmd = ["bsdtar", "-xf", path, "-C", dest]
                    code, out, err = _run(cmd)
                    if code == 0:
                        return f"✅ Wypakowano ISO do '{dest}' (via {tool})"
                    return f"❌ Błąd ekstrakcji: {err}"
            return "❌ Brak narzędzia do ekstrakcji (isoinfo / 7z / bsdtar).\nZainstaluj: apt-get install genisoimage"

        # isoinfo based extraction
        reader = ISOReader(path)
        files = reader.list_files(2000)
        os.makedirs(dest, exist_ok=True)
        errors = []
        extracted = 0

        if RICH_AVAILABLE:
            with Progress(
                SpinnerColumn(),
                TextColumn(f"[bold yellow]Extracting ISO[/bold yellow] {Path(path).name}"),
                BarColumn(),
                TaskProgressColumn(),
                TimeRemainingColumn(),
                transient=True
            ) as progress:
                task = progress.add_task("Extracting...", total=len(files))
                for iso_file in files:
                    out_path = os.path.join(dest, iso_file.lstrip("/"))
                    os.makedirs(os.path.dirname(out_path), exist_ok=True)
                    code, out, err = _run(["isoinfo", "-i", path, "-x", iso_file])
                    if code == 0:
                        try:
                            with open(out_path, "wb") as f:
                                f.write(out.encode("latin-1"))
                            extracted += 1
                        except Exception as e:
                            errors.append(f"{iso_file}: {e}")
                    else:
                        errors.append(f"{iso_file}: {err}")
                    progress.update(task, advance=1)
        else:
            for iso_file in files:
                out_path = os.path.join(dest, iso_file.lstrip("/"))
                os.makedirs(os.path.dirname(out_path), exist_ok=True)
                code, out, err = _run(["isoinfo", "-i", path, "-x", iso_file])
                if code == 0:
                    try:
                        with open(out_path, "wb") as f:
                            f.write(out.encode("latin-1"))
                        extracted += 1
                    except Exception as e:
                        errors.append(f"{iso_file}: {e}")
                else:
                    errors.append(f"{iso_file}: {err}")

        result = [f"✅ Wypakowano {extracted}/{len(files)} plików do '{dest}'"]
        if errors:
            result.append(f"⚠️  Błędy ({len(errors)}):")
            result += [f"   {e}" for e in errors[:10]]
        return "\n".join(result)

    def cmd_iso_mount(self, args: List[str]) -> str:
        """
        vdrive iso-mount <plik.iso> <punkt_montowania>
        Montuje ISO (wymaga uprawnień root lub FUSE).
        """
        if len(args) < 2:
            return "Użycie: vdrive iso-mount <plik.iso> <punkt_montowania>"
        path = self._abs(args[0])
        mp = self._abs(args[1])
        ok, msg = self._require_file(path)
        if not ok:
            return msg

        if not _defender_ok(path):
            _vdrive_notify(self.terminal, f"Defender zablokował montowanie: {os.path.basename(path)}", kind="warn")
            return (
                f"🛑 Defender oznaczył '{os.path.basename(path)}' jako niebezpieczny.\n"
                "   Montowanie wstrzymane. Sprawdź: defender check {0}".format(path)
            )

        os.makedirs(mp, exist_ok=True)

        # Try fuseiso first
        if shutil.which("fuseiso"):
            code, out, err = _run(["fuseiso", path, mp])
            if code == 0:
                self._mounts.add(path, mp, "iso-fuse")
                _vdrive_notify(self.terminal, f"ISO zamontowane: {os.path.basename(path)} → {mp}", kind="ok")
                return (
                    "✅ ISO zamontowane (FUSE)!\n"
                    f"   Obraz : {path}\n"
                    f"   Punkt : {mp}\n"
                    f"Odmontuj : vdrive iso-umount {mp}"
                )
            # fuseiso failed, try mount
        
        # Try system mount (needs root/sudo)
        code, out, err = _run(
            ["mount", "-o", "loop,ro", path, mp])
        if code == 0:
            self._mounts.add(path, mp, "iso-loop")
            _vdrive_notify(self.terminal, f"ISO zamontowane: {os.path.basename(path)} → {mp}", kind="ok")
            return (
                "✅ ISO zamontowane (loop)!\n"
                f"   Obraz : {path}\n"
                f"   Punkt : {mp}\n"
                f"Odmontuj : vdrive iso-umount {mp}"
            )

        # No mount available — show alternative
        return (
            "⚠️  Montowanie nie powiodło się (brak uprawnień lub FUSE).\n"
            f"   Alternatywa: vdrive iso-list {path}\n"
            f"   Alternatywa: vdrive iso-extract {path} <katalog>\n"
            f"   Błąd systemu: {err}"
        )

    def cmd_iso_umount(self, args: List[str]) -> str:
        """
        vdrive iso-umount <punkt_montowania>
        Odmontowuje ISO.
        """
        if not args:
            return "Użycie: vdrive iso-umount <punkt_montowania>"
        mp = self._abs(args[0])

        # Try fusermount first
        code, out, err = _run(["fusermount", "-u", mp])
        if code == 0:
            self._mounts.remove(mp)
            _vdrive_notify(self.terminal, f"ISO odmontowane: {mp}", kind="ok")
            return f"✅ Odmontowano: {mp}"

        # Try umount
        code, out, err = _run(["umount", mp])
        if code == 0:
            self._mounts.remove(mp)
            _vdrive_notify(self.terminal, f"ISO odmontowane: {mp}", kind="ok")
            return f"✅ Odmontowano: {mp}"

        return f"❌ Błąd odmontowania: {err}"

    def cmd_iso_checksum(self, args: List[str]) -> str:
        """
        vdrive iso-checksum <plik.iso> [--sha256] [--save]
        Oblicza sume kontrolna ISO. --save zapisuje plik .md5 / .sha256 obok obrazu.
        """
        if not args:
            return "Uzycie: vdrive iso-checksum <plik.iso> [--sha256] [--save]"
        path = self._abs(args[0])
        ok, msg = self._require_file(path)
        if not ok:
            return msg

        use_sha = "--sha256" in args
        save = "--save" in args
        reader = ISOReader(path)

        # Offload hashing to thread pool - avoids blocking terminal on large files
        fn = reader.sha256 if use_sha else reader.md5
        future = self._executor.submit(fn)
        checksum = future.result()
        algo = "SHA-256" if use_sha else "MD5"
        ext = ".sha256" if use_sha else ".md5"

        result = (
            f"\U0001f512 {algo} checksum:\n"
            f"   Plik : {path}\n"
            f"   Hash : {checksum}"
        )

        if save:
            sidecar = path + ext
            try:
                if use_sha:
                    # Deleguj zapis do core/sha256.py — dzięki temu plik trafia
                    # do tego samego formatu i jest rozpoznawalny przez komendy
                    # `sha256 verify` / `sha256 list` w całym ekosystemie.
                    saved = _integration.call("sha256", "save", sidecar, checksum, os.path.basename(path))
                    if saved is None:
                        with open(sidecar, "w") as sf:
                            sf.write(f"{checksum}  {os.path.basename(path)}\n")
                else:
                    with open(sidecar, "w") as sf:
                        sf.write(f"{checksum}  {os.path.basename(path)}\n")
                result += f"\n   Zapisano: {sidecar}"
            except Exception as e:
                result += f"\n\u26a0\ufe0f  Nie udalo sie zapisac sidecar: {e}"

        return result


    # ------------------------------------------------------------------ #
    #  VHD / virtual disk commands                                         #
    # ------------------------------------------------------------------ #

    def cmd_vhd_create(self, args: List[str]) -> str:
        """
        vdrive vhd-create <plik> <rozmiar> [--format vhd|vhdx|qcow2|vmdk|vdi|raw]
                          [--prealloc] [--backing <base_file>]
        Tworzy nowy wirtualny dysk.
        """
        if len(args) < 2:
            return ("Użycie: vdrive vhd-create <plik> <rozmiar> "
                    "[--format vhd|vhdx|qcow2|vmdk|vdi|raw] "
                    "[--prealloc] [--backing <base_file>]")

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        size_str = args[1]
        fmt = None
        prealloc = False
        backing = None

        i = 2
        while i < len(args):
            if args[i] in ("--format", "-") and i + 1 < len(args):
                fmt = args[i + 1].lower(); i += 2
            elif args[i] == "--prealloc":
                prealloc = True; i += 1
            elif args[i] == "--backing" and i + 1 < len(args):
                backing = self._abs(args[i + 1]); i += 2
            else:
                i += 1

        if fmt is None:
            ext = Path(path).suffix.lstrip(".").lower()
            fmt = ext if ext in self.SUPPORTED_VHD_FORMATS else "vhd"

        qfmt = self.SUPPORTED_VHD_FORMATS.get(fmt, fmt)

        ok2, msg2 = self._check_path_free(path)
        if not ok2:
            return msg2

        cmd = ["qemu-img", "create", "-", qfmt]

        if backing:
            if not os.path.isfile(backing):
                return f"❌ Plik bazowy '{backing}' nie istnieje."
            back_fmt = self._qemu_fmt(backing)
            cmd += ["-b", backing, "-F", back_fmt]

        if prealloc:
            if qfmt == "qcow2":
                cmd += ["-o", "preallocation=full"]
            elif qfmt in ("raw", "vpc"):
                cmd += ["-o", "preallocation=full"]

        cmd += [path, size_str]
        
        if RICH_AVAILABLE:
            cmd.insert(1, "-p")
            code, out, err = self._run_with_rich_progress(cmd, f"Creating VHD: {Path(path).name}")
        else:
            code, out, err = _run(cmd)

        if code != 0:
            err_msg = f"❌ Błąd tworzenia dysku:\n{err or out}"
            _vdrive_notify(self.terminal, f"Błąd tworzenia dysku '{Path(path).name}'", kind="err")
            return err_msg

        info = self._qemu_info(path)
        vsize = info.get("virtual-size", 0)
        asize = info.get("actual-size", info.get("disk-size", 0))

        _vdrive_notify(self.terminal, f"Dysk wirtualny utworzony: {Path(path).name} ({qfmt}, {_size_human(vsize)})", kind="ok")
        _vdrive_log(self.terminal, "INFO", f"vdrive: dysk utworzony {path} ({qfmt})")
        return (
            "✅ Wirtualny dysk utworzony!\n"
            f"   Plik           : {path}\n"
            f"   Format         : {qfmt} (.{fmt})\n"
            f"   Rozmiar wirtualny: {_size_human(vsize)}\n"
            f"   Rozmiar na dysku : {_size_human(asize)}\n"
            + (f"   Plik bazowy    : {backing}\n" if backing else "")
        )

    def cmd_vhd_info(self, args: List[str]) -> str:
        """
        vdrive vhd-info <plik>
        Wyświetla szczegółowe informacje o wirtualnym dysku.
        """
        if not args:
            return "Użycie: vdrive vhd-info <plik>"
        path = self._abs(args[0])
        ok, msg = self._require_file(path)
        if not ok:
            return msg

        ok2, msg2 = _require_tool("qemu-img")
        if not ok2:
            return msg2

        info = self._qemu_info(path)
        size = os.path.getsize(path)

        lines = [f"==== VHD INFO: {os.path.basename(path)} ====\n"]
        lines.append(f"  Plik            : {path}")
        lines.append(f"  Rozmiar pliku   : {_size_human(size)}")
        lines.append(self._format_qemu_info(info))
        return "\n".join(lines)

    def cmd_vhd_convert(self, args: List[str]) -> str:
        """
        vdrive vhd-convert <źródło> <cel> [--format vhd|vhdx|qcow2|vmdk|vdi|raw] [--compress]
        Konwertuje między formatami wirtualnych dysków.
        """
        if len(args) < 2:
            return ("Użycie: vdrive vhd-convert <źródło> <cel> "
                    "[--format vhd|vhdx|qcow2|vmdk|vdi|raw] [--compress]")

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        src = self._abs(args[0])
        dst = self._abs(args[1])
        compress = "--compress" in args
        dst_fmt = None

        i = 2
        while i < len(args):
            if args[i] in ("--format", "-") and i + 1 < len(args):
                dst_fmt = args[i + 1].lower(); i += 2
            else:
                i += 1

        ok2, msg2 = self._require_file(src)
        if not ok2:
            return msg2
        ok3, msg3 = self._check_path_free(dst)
        if not ok3:
            return msg3

        src_fmt = self._qemu_fmt(src)
        if dst_fmt is None:
            ext = Path(dst).suffix.lstrip(".").lower()
            dst_fmt = ext if ext in self.SUPPORTED_VHD_FORMATS else "qcow2"
        dst_qfmt = self.SUPPORTED_VHD_FORMATS.get(dst_fmt, dst_fmt)

        cmd = ["qemu-img", "convert", "-", src_fmt, "-O", dst_qfmt]
        if compress and dst_qfmt in ("qcow2", "qcow"):
            cmd.append("-c")
        cmd += [src, dst]

        if RICH_AVAILABLE:
            cmd.insert(1, "-p")
            code, out, err = self._run_with_rich_progress(cmd, f"Converting VHD: {Path(dst).name}")
        else:
            code, out, err = _run(cmd)

        if code != 0:
            return f"❌ Błąd konwersji:\n{err or out}"

        src_size = os.path.getsize(src)
        dst_size = os.path.getsize(dst)
        ratio = (1 - dst_size / src_size) * 100 if src_size else 0

        return (
            "✅ Konwersja zakończona!\n"
            f"   Źródło  : {src} ({_size_human(src_size)}, {src_fmt})\n"
            f"   Cel     : {dst} ({_size_human(dst_size)}, {dst_qfmt})\n"
            f"   Oszczędność: {ratio:.1f}%"
        )

    def cmd_vhd_resize(self, args: List[str]) -> str:
        """
        vdrive vhd-resize <plik> <nowy_rozmiar> [--shrink]
        Zmienia rozmiar wirtualnego dysku.
        """
        if len(args) < 2:
            return "Użycie: vdrive vhd-resize <plik> <nowy_rozmiar> [--shrink]"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        size = args[1]
        shrink = "--shrink" in args

        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        info_before = self._qemu_info(path)
        size_before = info_before.get("virtual-size", 0)

        cmd = ["qemu-img", "resize"]
        if shrink:
            cmd.append("--shrink")
        cmd += [path, size]

        code, out, err = _run(cmd)
        if code != 0:
            return (
                f"❌ Błąd zmiany rozmiaru:\n{err or out}\n"
                + ("💡 Wskazówka: zmniejszanie wymaga --shrink i może uszkodzić dane." if not shrink else "")
            )

        info_after = self._qemu_info(path)
        size_after = info_after.get("virtual-size", 0)

        return (
            "✅ Rozmiar zmieniony!\n"
            f"   Plik   : {path}\n"
            f"   Przed  : {_size_human(size_before)}\n"
            f"   Po     : {_size_human(size_after)}"
        )

    def cmd_vhd_compact(self, args: List[str]) -> str:
        """
        vdrive vhd-compact <plik>
        Kompaktuje dysk (usuwa niepotrzebne dane, zmniejsza plik na dysku).
        """
        if not args:
            return "Użycie: vdrive vhd-compact <plik>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        size_before = os.path.getsize(path)
        fmt = self._qemu_fmt(path)

        # qemu-img convert to self with format re-write = compaction
        tmp = path + ".compact.tmp"
        cmd = ["qemu-img", "convert", "-O", fmt, path, tmp]
        
        if RICH_AVAILABLE:
            cmd.insert(1, "-p")
            code, out, err = self._run_with_rich_progress(cmd, f"Compacting VHD: {Path(path).name}")
        else:
            code, out, err = _run(cmd)

        if code != 0:
            if os.path.exists(tmp):
                os.remove(tmp)
            return f"❌ Błąd kompaktowania:\n{err}"

        os.replace(tmp, path)
        size_after = os.path.getsize(path)
        saved = size_before - size_after

        return (
            "✅ Kompaktowanie zakończone!\n"
            f"   Plik       : {path}\n"
            f"   Przed      : {_size_human(size_before)}\n"
            f"   Po         : {_size_human(size_after)}\n"
            f"   Zaoszczędzono: {_size_human(saved)}"
        )

    def cmd_vhd_snapshot_create(self, args: List[str]) -> str:
        """
        vdrive vhd-snap-create <plik.qcow2> <nazwa_snapshotu>
        Tworzy snapshot (tylko qcow2/qcow).
        """
        if len(args) < 2:
            return "Użycie: vdrive vhd-snap-create <plik.qcow2> <nazwa>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        name = args[1]
        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        fmt = self._qemu_fmt(path)
        if fmt not in self.SNAPSHOT_FORMATS:
            return (
                "❌ Snapshoty obsługuje tylko format qcow2/qcow.\n"
                f"   Format pliku: {fmt}\n"
                f"   Konwertuj: vdrive vhd-convert {path} {path}.qcow2 --format qcow2"
            )

        code, out, err = _run(["qemu-img", "snapshot", "-c", name, path])
        if code != 0:
            return f"❌ Błąd tworzenia snapshotu:\n{err}"

        _vdrive_notify(self.terminal, f"Snapshot '{name}' utworzony ({os.path.basename(path)})", kind="ok")
        return (
            f"✅ Snapshot '{name}' utworzony!\n"
            f"   Plik: {path}\n"
            f"   Sprawdź: vdrive vhd-snap-list {path}"
        )

    def cmd_vhd_snapshot_list(self, args: List[str]) -> str:
        """
        vdrive vhd-snap-list <plik.qcow2>
        Wyświetla listę snapshotów.
        """
        if not args:
            return "Użycie: vdrive vhd-snap-list <plik.qcow2>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        code, out, err = _run(["qemu-img", "snapshot", "-l", path])
        if code != 0:
            return f"❌ Błąd listowania snapshotów:\n{err}"

        if not out or "Snapshot list:" in out and len(out.splitlines()) <= 2:
            return f"ℹ️  Brak snapshotów w '{os.path.basename(path)}'."

        return f"==== SNAPSHOTY: {os.path.basename(path)} ====\n\n{out}"

    def cmd_vhd_snapshot_restore(self, args: List[str]) -> str:
        """
        vdrive vhd-snap-restore <plik.qcow2> <nazwa_snapshotu>
        Przywraca snapshot.
        """
        if len(args) < 2:
            return "Użycie: vdrive vhd-snap-restore <plik.qcow2> <nazwa>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        name = args[1]
        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        code, out, err = _run(["qemu-img", "snapshot", "-a", name, path])
        if code != 0:
            return f"❌ Błąd przywracania snapshotu '{name}':\n{err}"
        _vdrive_notify(self.terminal, f"Snapshot '{name}' przywrócony ({os.path.basename(path)})", kind="ok")
        return f"✅ Snapshot '{name}' przywrócony w '{os.path.basename(path)}'."

    def cmd_vhd_snapshot_delete(self, args: List[str]) -> str:
        """
        vdrive vhd-snap-delete <plik.qcow2> <nazwa_snapshotu>
        Usuwa snapshot.
        """
        if len(args) < 2:
            return "Użycie: vdrive vhd-snap-delete <plik.qcow2> <nazwa>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        name = args[1]
        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        code, out, err = _run(["qemu-img", "snapshot", "-d", name, path])
        if code != 0:
            return f"❌ Błąd usuwania snapshotu '{name}':\n{err}"
        _vdrive_notify(self.terminal, f"Snapshot '{name}' usunięty ({os.path.basename(path)})", kind="ok")
        return f"✅ Snapshot '{name}' usunięty z '{os.path.basename(path)}'."

    def cmd_vhd_clone(self, args: List[str]) -> str:
        """
        vdrive vhd-clone <źródło> <kopia> [--format <fmt>]
        Klonuje wirtualny dysk.
        """
        if len(args) < 2:
            return "Użycie: vdrive vhd-clone <źródło> <kopia> [--format fmt]"

        src = self._abs(args[0])
        dst = self._abs(args[1])
        dst_fmt = None

        i = 2
        while i < len(args):
            if args[i] in ("--format", "-") and i + 1 < len(args):
                dst_fmt = args[i + 1].lower(); i += 2
            else:
                i += 1

        # reuse convert for the actual copy
        convert_args = [src, dst]
        if dst_fmt:
            convert_args += ["--format", dst_fmt]
        return self.cmd_vhd_convert(convert_args)

    def cmd_vhd_merge(self, args: List[str]) -> str:
        """
        vdrive vhd-merge <plik_z_backing>
        Scala plik z jego backing file (commit).
        """
        if not args:
            return "Użycie: vdrive vhd-merge <plik_z_backing>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        info = self._qemu_info(path)
        if not info.get("backing-filename"):
            return f"❌ Plik '{os.path.basename(path)}' nie ma backing file."

        code, out, err = _run(["qemu-img", "commit", path])
        if code != 0:
            return f"❌ Błąd scalania:\n{err}"
        return (
            "✅ Scalono z backing file!\n"
            f"   Plik    : {path}\n"
            f"   Backing : {info['backing-filename']}"
        )

    def cmd_vhd_check(self, args: List[str]) -> str:
        """
        vdrive vhd-check <plik> [--repair]
        Sprawdza integralność wirtualnego dysku.
        """
        if not args:
            return "Użycie: vdrive vhd-check <plik> [--repair]"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        path = self._abs(args[0])
        repair = "--repair" in args
        ok2, msg2 = self._require_file(path)
        if not ok2:
            return msg2

        cmd = ["qemu-img", "check"]
        if repair:
            cmd += ["-r", "all"]
        cmd.append(path)

        code, out, err = _run(cmd)
        combined = (out + "\n" + err).strip()

        if code == 0:
            return (
                f"✅ Dysk '{os.path.basename(path)}' — OK\n"
                + (combined if combined else "Brak błędów.")
            )
        _vdrive_log(self.terminal, "WARN", f"vdrive: integralność naruszona {path}")
        _vdrive_notify(self.terminal, f"Problemy z integralnością: {os.path.basename(path)}", kind="warn")
        return (
            f"⚠️  Problemy w '{os.path.basename(path)}':\n{combined}\n"
            + ("Spróbuj: vdrive vhd-check <plik> --repair" if not repair else "")
        )

    def cmd_vhd_encrypt(self, args: List[str]) -> str:
        """
        vdrive vhd-encrypt <źródło> <cel.qcow2> <hasło>
        Tworzy zaszyfrowaną kopię dysku (LUKS, format qcow2).
        """
        if len(args) < 3:
            return "Użycie: vdrive vhd-encrypt <źródło> <cel.qcow2> <hasło>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        src = self._abs(args[0])
        dst = self._abs(args[1])
        password = args[2]

        ok2, msg2 = self._require_file(src)
        if not ok2:
            return msg2
        ok3, msg3 = self._check_path_free(dst)
        if not ok3:
            return msg3

        src_fmt = self._qemu_fmt(src)
        # Write password to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write(password)
            secret_file = f.name

        try:
            cmd = [
                "qemu-img", "convert",
                "-", src_fmt,
                "-O", "qcow2",
                "--object", f"secret,id=sec0,file={secret_file}",
                "-o", "encrypt.format=luks,encrypt.key-secret=sec0",
                src, dst
            ]
            code, out, err = _run(cmd)
        finally:
            os.unlink(secret_file)

        if code != 0:
            if os.path.exists(dst):
                os.remove(dst)
            _vdrive_notify(self.terminal, f"Błąd szyfrowania dysku '{Path(src).name}'", kind="err")
            return f"❌ Błąd szyfrowania:\n{err or out}"

        size = os.path.getsize(dst)
        _vdrive_log(self.terminal, "INFO", f"vdrive: dysk zaszyfrowany (LUKS) {dst}")
        _vdrive_notify(self.terminal, f"Dysk zaszyfrowany: {Path(dst).name}", kind="ok", title="VDRIVE/SEC")
        return (
            "✅ Zaszyfrowany dysk utworzony!\n"
            f"📁 Plik: {dst}\n"
            "🔐 Szyfrowanie: LUKS\n"
            f"📏 Rozmiar: {size:,} bajtów"
        )

    def cmd_vhd_decrypt(self, args: List[str]) -> str:
        """
        vdrive vhd-decrypt <zaszyfrowany> <cel.jawny> <hasło>
        Odszyfrowuje dysk LUKS do formatu jawnego.
        """
        if len(args) < 3:
            return "Użycie: vdrive vhd-decrypt <zaszyfrowany> <cel.jawny> <hasło>"

        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        src = self._abs(args[0])
        dst = self._abs(args[1])
        password = args[2]

        ok2, msg2 = self._require_file(src)
        if not ok2:
            return msg2
        ok3, msg3 = self._check_path_free(dst)
        if not ok3:
            return msg3

        # Write password to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            f.write(password)
            secret_file = f.name

        try:
            cmd = [
                "qemu-img", "convert",
                "-", "qcow2",
                "--object", f"secret,id=sec0,file={secret_file}",
                "-O", "raw",
                src, dst
            ]
            code, out, err = _run(cmd)
        finally:
            os.unlink(secret_file)

        if code != 0:
            if os.path.exists(dst):
                os.remove(dst)
            _vdrive_notify(self.terminal, f"Błąd deszyfrowania dysku '{Path(src).name}'", kind="err")
            return f"❌ Błąd deszyfrowania:\n{err or out}"

        size = os.path.getsize(dst)
        _vdrive_log(self.terminal, "INFO", f"vdrive: dysk odszyfrowany {dst}")
        _vdrive_notify(self.terminal, f"Dysk odszyfrowany: {Path(dst).name}", kind="ok", title="VDRIVE/SEC")
        return (
            "✅ Dysk odszyfrowany!\n"
            f"📁 Plik: {dst}\n"
            "🔓 Format: RAW (niezaszyfrowany)\n"
            f"📏 Rozmiar: {size:,} bajtów"
        )

    def cmd_vdrive_encrypt(self, args: List[str]) -> str:
        """
        vdrive encrypt <plik> [opcje]
        
        Opcje szyfrowania:
          --luks <hasło>           Szyfrowanie LUKS (domyślne)
          --veracrypt <hasło>      Szyfrowanie VeraCrypt
          --aes <hasło>            Szyfrowanie AES-256
          --algorithm <alg>       Algorytm (aes, serpent, twofish)
          --keyfile <plik>         Plik klucza zamiast hasła
          --mount <punkt>         Automatyczny montaż po zaszyfrowaniu
        """
        if len(args) < 1:
            return (
                "Użycie: vdrive encrypt <plik> [opcje]\n\n"
                "Opcje:\n"
                "  --luks <hasło>           Szyfrowanie LUKS (domyślne)\n"
                "  --veracrypt <hasło>      Szyfrowanie VeraCrypt\n"
                "  --aes <hasło>            Szyfrowanie AES-256\n"
                "  --algorithm <alg>       Algorytm (aes, serpent, twofish)\n"
                "  --keyfile <plik>         Plik klucza zamiast hasła\n"
                "  --mount <punkt>         Automatyczny montaż po zaszyfrowaniu"
            )

        src_file = self._abs(args[0])
        
        # Parse options
        encrypt_type = "luks"
        password = None
        keyfile = None
        algorithm = "aes"
        mount_point = None
        
        i = 1
        while i < len(args):
            if args[i] == "--luks" and i + 1 < len(args):
                encrypt_type = "luks"
                password = args[i + 1]
                i += 2
            elif args[i] == "--veracrypt" and i + 1 < len(args):
                encrypt_type = "veracrypt"
                password = args[i + 1]
                i += 2
            elif args[i] == "--aes" and i + 1 < len(args):
                encrypt_type = "aes"
                password = args[i + 1]
                i += 2
            elif args[i] == "--algorithm" and i + 1 < len(args):
                algorithm = args[i + 1]
                i += 2
            elif args[i] == "--keyfile" and i + 1 < len(args):
                keyfile = self._abs(args[i + 1])
                i += 2
            elif args[i] == "--mount" and i + 1 < len(args):
                mount_point = self._abs(args[i + 1])
                i += 2
            else:
                i += 1

        if encrypt_type == "luks":
            return self._encrypt_luks(src_file, password, keyfile, mount_point)
        elif encrypt_type == "veracrypt":
            return self._encrypt_veracrypt(src_file, password, keyfile, mount_point)
        elif encrypt_type == "aes":
            return self._encrypt_aes(src_file, password, algorithm, keyfile, mount_point)
        else:
            return f"❌ Nieznany typ szyfrowania: {encrypt_type}"

    def cmd_vdrive_decrypt(self, args: List[str]) -> str:
        """
        vdrive decrypt <plik> <hasło> [opcje]
        
        Opcje:
          --output <plik>         Zapisz odszyfrowany do pliku
          --mount <punkt>         Automatyczny montaż po odszyfrowaniu
          --keyfile <plik>        Użyj pliku klucza
        """
        if len(args) < 2:
            return (
                "Użycie: vdrive decrypt <plik> <hasło> [opcje]\n\n"
                "Opcje:\n"
                "  --output <plik>         Zapisz odszyfrowany do pliku\n"
                "  --mount <punkt>         Automatyczny montaż po odszyfrowaniu\n"
                "  --keyfile <plik>        Użyj pliku klucza"
            )

        src_file = self._abs(args[0])
        password = args[1]
        output_file = None
        mount_point = None
        keyfile = None

        # Parse options
        i = 2
        while i < len(args):
            if args[i] == "--output" and i + 1 < len(args):
                output_file = self._abs(args[i + 1])
                i += 2
            elif args[i] == "--mount" and i + 1 < len(args):
                mount_point = self._abs(args[i + 1])
                i += 2
            elif args[i] == "--keyfile" and i + 1 < len(args):
                keyfile = self._abs(args[i + 1])
                i += 2
            else:
                i += 1

        return self._decrypt_container(src_file, password, output_file, mount_point, keyfile)

    def _encrypt_luks(self, src_file: str, password: str, keyfile: str = None, mount_point: str = None) -> str:
        """Encrypt with LUKS using qemu-img"""
        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        if not password and not keyfile:
            return "❌ Wymagane hasło lub plik klucza"

        dst_file = src_file + ".encrypted.qcow2"
        
        if os.path.exists(dst_file):
            return f"❌ Plik docelowy już istnieje: {dst_file}"

        # Use password or keyfile
        secret_source = password
        secret_type = "password"
        
        if keyfile:
            if not os.path.exists(keyfile):
                return f"❌ Plik klucza nie istnieje: {keyfile}"
            secret_source = keyfile
            secret_type = "file"

        # Write secret to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            if secret_type == "password":
                f.write(secret_source)
            else:
                with open(secret_source, 'r') as kf:
                    f.write(kf.read())
            secret_file = f.name

        try:
            cmd = [
                "qemu-img", "convert",
                "-", self._qemu_fmt(src_file),
                "-O", "qcow2",
                "--object", f"secret,id=sec0,file={secret_file}",
                "-o", "encrypt.format=luks,encrypt.key-secret=sec0",
                src_file, dst_file
            ]
            code, out, err = _run(cmd)
        finally:
            os.unlink(secret_file)

        if code != 0:
            if os.path.exists(dst_file):
                os.remove(dst_file)
            return f"❌ Błąd szyfrowania LUKS:\n{err or out}"

        result = (
            "✅ Dysk zaszyfrowany LUKS!\n"
            f"📁 Plik: {dst_file}\n"
            "🔐 Szyfrowanie: LUKS\n"
            f"📏 Rozmiar: {os.path.getsize(dst_file):,} bajtów"
        )

        if mount_point:
            mount_result = self._mount_encrypted(dst_file, password, mount_point, "luks")
            result += f"\n{mount_result}"

        return result

    def _encrypt_veracrypt(self, src_file: str, password: str, keyfile: str = None, mount_point: str = None) -> str:
        """Encrypt source image as a VeraCrypt container (.hc).

        Workflow:
          1. Create an empty .hc container sized to hold the source data.
          2. Mount it to a temp directory.
          3. Copy the raw bytes of the source image into the container.
          4. Unmount and optionally re-mount at the user-supplied mount_point.
        """
        ok, msg = _require_tool("veracrypt")
        if not ok:
            return "\u274c VeraCrypt nie jest dostepny. Zainstaluj VeraCrypt."

        if not password and not keyfile:
            return "\u274c Wymagane haslo lub plik klucza"

        src_size = os.path.getsize(src_file)
        # Use .hc extension (VeraCrypt Hidden Container standard)
        dst_file = src_file + ".hc"

        if os.path.exists(dst_file):
            return f"\u274c Plik docelowy juz istnieje: {dst_file}"

        # Build veracrypt --create command (no duplicate --keyfiles)
        cmd = [
            "veracrypt", "--text",
            "--create", dst_file,
            "--type", "normal",
            "--encryption", "AES",
            "--hash", "SHA-512",
            "--filesystem", "FAT",
            "--size", str(src_size),
            "--password", password if password else "",
            "--force",
        ]
        if keyfile:
            cmd += ["--keyfiles", keyfile]

        code, out, err = _run(cmd)
        if code != 0:
            if os.path.exists(dst_file):
                os.remove(dst_file)
            return f"\u274c Blad tworzenia kontenera VeraCrypt:\n{err or out}"

        # --- Mount container to a temp dir and copy source data into it ---
        tmp_mp = tempfile.mkdtemp(prefix="vc_enc_")
        copy_ok = False
        copy_err = ""
        try:
            mount_cmd = ["veracrypt", "--text", "--mount", dst_file, tmp_mp,
                         "--password", password if password else "",
                         "--protect-hidden=no", "--force"]
            if keyfile:
                mount_cmd += ["--keyfiles", keyfile]

            mc, mo, me = _run(mount_cmd)
            if mc == 0:
                # Copy source file into container root
                dst_copy = os.path.join(tmp_mp, os.path.basename(src_file))
                try:
                    shutil.copy2(src_file, dst_copy)
                    copy_ok = True
                except Exception as ce:
                    copy_err = str(ce)

                # Unmount temp mount regardless of copy result
                _run(["veracrypt", "--text", "--dismount", tmp_mp, "--force"])
            else:
                copy_err = f"Montowanie temp nie powiodlo sie: {me or mo}"
        finally:
            try:
                os.rmdir(tmp_mp)
            except OSError:
                pass

        result_lines = [
            "\u2705 Kontener VeraCrypt utworzony!",
            f"\U0001f4c1 Plik      : {dst_file}",
            "\U0001f512 Szyfrowanie: VeraCrypt AES-256 + SHA-512",
            f"\U0001f4cf Rozmiar   : {_size_human(os.path.getsize(dst_file))}",
        ]
        if copy_ok:
            result_lines.append("\u2705 Dane skopiowane do kontenera.")
        else:
            result_lines.append(
                "\u26a0\ufe0f  Dane nie zostaly skopiowane automatycznie"
                + (f": {copy_err}" if copy_err else "")
                + f"\n   Zamontuj recznie: veracrypt {dst_file} <punkt> i skopiuj plik."
            )

        if mount_point:
            mount_result = self._mount_veracrypt(dst_file, password, mount_point, keyfile)
            result_lines.append(mount_result)

        return "\n".join(result_lines)

    def _encrypt_aes(self, src_file: str, password: str, algorithm: str = "aes", keyfile: str = None, mount_point: str = None) -> str:
        """Encrypt with AES using OpenSSL"""
        ok, msg = _require_tool("openssl")
        if not ok:
            return msg

        if not password and not keyfile:
            return "❌ Wymagane hasło lub plik klucza"

        dst_file = src_file + ".aes"
        
        if os.path.exists(dst_file):
            return f"❌ Plik docelowy już istnieje: {dst_file}"

        try:
            # Get encryption command based on algorithm
            alg_map = {
                "aes": "aes-256-cbc",
                "serpent": "aes-256-cbc",  # OpenSSL doesn't have serpent, fallback to AES
                "twofish": "aes-256-cbc"   # OpenSSL doesn't have twofish, fallback to AES
            }
            cipher = alg_map.get(algorithm.lower(), "aes-256-cbc")

            # Get password/key
            if keyfile:
                if not os.path.exists(keyfile):
                    return f"❌ Plik klucza nie istnieje: {keyfile}"
                pass_cmd = ["openssl", "enc", "-d", "-pbkdf2", "-in", keyfile]
            else:
                pass_cmd = ["echo", password]

            # Encrypt the file
            cmd = [
                "openssl", "enc", cipher,
                "-pbkdf2",
                "-in", src_file,
                "-out", dst_file,
                "-pass", "stdin"
            ]

            # Pipe password to openssl
            pass_proc = subprocess.Popen(pass_cmd, stdout=subprocess.PIPE, text=True)
            encrypt_proc = subprocess.Popen(cmd, stdin=pass_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            pass_proc.stdout.close()
            
            out, err = encrypt_proc.communicate()
            code = encrypt_proc.returncode

            if code != 0:
                if os.path.exists(dst_file):
                    os.remove(dst_file)
                return f"❌ Błąd szyfrowania AES:\n{err or out}"

            result = (
                "✅ Dysk zaszyfrowany AES!\n"
                f"📁 Plik: {dst_file}\n"
                f"🔐 Szyfrowanie: {cipher.upper()}\n"
                f"📏 Rozmiar: {os.path.getsize(dst_file):,} bajtów"
            )

            return result

        except Exception as e:
            if os.path.exists(dst_file):
                os.remove(dst_file)
            return f"❌ Błąd szyfrowania AES: {str(e)}"

    def _decrypt_container(self, src_file: str, password: str, output_file: str = None, mount_point: str = None, keyfile: str = None) -> str:
        """Detect container type and dispatch to the correct decrypt handler.
        
        Supports .hc and .vc (VeraCrypt), .aes (OpenSSL), .encrypted.qcow2 (LUKS).
        Falls back to header inspection for unknown extensions.
        """
        # .hc is the standard VeraCrypt container extension
        if src_file.endswith(".hc") or src_file.endswith(".vc"):
            return self._decrypt_veracrypt(src_file, password, output_file, mount_point, keyfile)
        elif src_file.endswith(".aes"):
            return self._decrypt_aes(src_file, password, output_file, keyfile)
        elif src_file.endswith(".encrypted.qcow2"):
            return self._decrypt_luks(src_file, password, output_file, mount_point, keyfile)
        else:
            # Fallback: inspect file header bytes
            try:
                with open(src_file, "rb") as f:
                    header = f.read(1024)
                if b"LUKS" in header:
                    return self._decrypt_luks(src_file, password, output_file, mount_point, keyfile)
                # VeraCrypt containers have no plaintext magic - assume it if no other match
                return self._decrypt_veracrypt(src_file, password, output_file, mount_point, keyfile)
            except Exception as e:
                return f"❌ Błąd odczytu pliku: {e}"

    def _decrypt_luks(self, src_file: str, password: str, output_file: str = None, mount_point: str = None, keyfile: str = None) -> str:
        """Decrypt LUKS container"""
        ok, msg = _require_tool("qemu-img")
        if not ok:
            return msg

        if not output_file:
            output_file = src_file.replace(".encrypted.qcow2", ".decrypted.raw")

        # Get password/key
        secret_source = password
        secret_type = "password"
        
        if keyfile:
            if not os.path.exists(keyfile):
                return f"❌ Plik klucza nie istnieje: {keyfile}"
            secret_source = keyfile
            secret_type = "file"

        # Write secret to temp file
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".secret") as f:
            if secret_type == "password":
                f.write(secret_source)
            else:
                with open(secret_source, 'r') as kf:
                    f.write(kf.read())
            secret_file = f.name

        try:
            cmd = [
                "qemu-img", "convert",
                "-", "qcow2",
                "--object", f"secret,id=sec0,file={secret_file}",
                "-O", "raw",
                src_file, output_file
            ]
            code, out, err = _run(cmd)
        finally:
            os.unlink(secret_file)

        if code != 0:
            if os.path.exists(output_file):
                os.remove(output_file)
            return f"❌ Błąd deszyfrowania LUKS:\n{err or out}"

        result = (
            "✅ Dysk odszyfrowany LUKS!\n"
            f"📁 Plik: {output_file}\n"
            "🔓 Format: RAW (niezaszyfrowany)\n"
            f"📏 Rozmiar: {os.path.getsize(output_file):,} bajtów"
        )

        if mount_point:
            mount_result = self._mount_raw(output_file, mount_point)
            result += f"\n{mount_result}"

        return result

    def _decrypt_veracrypt(self, src_file: str, password: str, output_file: str = None, mount_point: str = None, keyfile: str = None) -> str:
        """Decrypt VeraCrypt container"""
        ok, msg = _require_tool("veracrypt")
        if not ok:
            return "❌ VeraCrypt nie jest dostępny"

        if not mount_point:
            return "❌ Do odszyfrowania VeraCrypt wymagany jest punkt montowania (--mount)"

        return self._mount_veracrypt(src_file, password, mount_point, keyfile)

    def _decrypt_aes(self, src_file: str, password: str, output_file: str = None, keyfile: str = None) -> str:
        """Decrypt AES container"""
        ok, msg = _require_tool("openssl")
        if not ok:
            return msg

        if not output_file:
            output_file = src_file.replace(".aes", ".decrypted")

        try:
            # Get password/key
            if keyfile:
                if not os.path.exists(keyfile):
                    return f"❌ Plik klucza nie istnieje: {keyfile}"
                pass_cmd = ["openssl", "enc", "-d", "-pbkdf2", "-in", keyfile]
            else:
                pass_cmd = ["echo", password]

            # Decrypt the file
            cmd = [
                "openssl", "enc", "-d",
                "-aes-256-cbc",
                "-pbkdf2",
                "-in", src_file,
                "-out", output_file,
                "-pass", "stdin"
            ]

            # Pipe password to openssl
            pass_proc = subprocess.Popen(pass_cmd, stdout=subprocess.PIPE, text=True)
            decrypt_proc = subprocess.Popen(cmd, stdin=pass_proc.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            pass_proc.stdout.close()
            
            out, err = decrypt_proc.communicate()
            code = decrypt_proc.returncode

            if code != 0:
                if os.path.exists(output_file):
                    os.remove(output_file)
                return f"❌ Błąd deszyfrowania AES:\n{err or out}"

            return (
                "✅ Plik odszyfrowany AES!\n"
                f"📁 Plik: {output_file}\n"
                "🔓 Format: RAW (niezaszyfrowany)\n"
                f"📏 Rozmiar: {os.path.getsize(output_file):,} bajtów"
            )

        except Exception as e:
            if os.path.exists(output_file):
                os.remove(output_file)
            return f"❌ Błąd deszyfrowania AES: {str(e)}"

    def _mount_encrypted(self, container_file: str, password: str, mount_point: str, encrypt_type: str) -> str:
        """Mount encrypted container"""
        if encrypt_type == "luks":
            # For LUKS, we'd need to use cryptsetup + mount
            ok, msg = _require_tool("cryptsetup")
            if not ok:
                return f"❌ cryptsetup nie jest dostępny: {msg}"
            
            # This is a simplified version - full implementation would be more complex
            return "⚠️  Montaż LUKS wymaga dodatkowej konfiguracji cryptsetup"
        
        return "❌ Montaż szyfrowanych kontenerów nie jest jeszcze w pełni zaimplementowany"

    def _mount_veracrypt(self, container_file: str, password: str, mount_point: str, keyfile: str = None) -> str:
        """Mount VeraCrypt container"""
        try:
            cmd = ["veracrypt", "--text", "--mount", container_file, mount_point]
            
            if password:
                cmd.extend(["--password", password])
            if keyfile:
                cmd.extend(["--keyfiles", keyfile])
            
            code, out, err = _run(cmd)
            
            if code == 0:
                return f"✅ Kontener VeraCrypt zamontowany w {mount_point}"
            else:
                return f"❌ Błąd montowania VeraCrypt: {err or out}"
                
        except Exception as e:
            return f"❌ Błąd montowania VeraCrypt: {str(e)}"

    def _mount_raw(self, raw_file: str, mount_point: str) -> str:
        """Mount raw disk image"""
        # This would need to detect filesystem and mount appropriately
        return "⚠️  Montowanie obrazów RAW wymaga detekcji systemu plików"

    def cmd_vdrive_info(self, args: List[str]) -> str:
        """
        vdrive info <plik>
        Pokazuje szczegółowe informacje o pliku, w tym informacje o szyfrowaniu.
        """
        if len(args) < 1:
            return "Użycie: vdrive info <plik>"

        file_path = self._abs(args[0])
        
        if not os.path.exists(file_path):
            return f"❌ Plik nie istnieje: {file_path}"

        info_lines = [f"📁 Plik: {file_path}"]
        info_lines.append(f"📏 Rozmiar: {os.path.getsize(file_path):,} bajtów")

        # Detect file type
        if file_path.endswith(".hc") or file_path.endswith(".vc"):
            info_lines.append("🔐 Typ: Kontener VeraCrypt (.hc)")
        elif file_path.endswith(".aes"):
            info_lines.append("🔐 Typ: Plik zaszyfrowany AES")
        elif file_path.endswith(".encrypted.qcow2"):
            info_lines.append("🔐 Typ: Dysk QCOW2 zaszyfrowany LUKS")
        else:
            # Try to detect from qemu-img
            ok, msg = _require_tool("qemu-img")
            if ok:
                code, out, err = _run(["qemu-img", "info", "--output=json", file_path])
                if code == 0:
                    try:
                        import json
                        data = json.loads(out)
                        if data.get("encrypt"):
                            info_lines.append(f"🔐 Szyfrowanie: {data['encrypt'].get('format', 'Nieznane')}")
                        info_lines.append(f"📋 Format: {data.get('format', 'Nieznany')}")
                        if "virtual-size" in data:
                            info_lines.append(f"💾 Rozmiar wirtualny: {data['virtual-size']:,} bajtów")
                    except:
                        pass

        return "\n".join(info_lines)

    def cmd_vhd_mount(self, args: List[str]) -> str:
        """
        vdrive vhd-mount <plik> <punkt_montowania> [--offset <bajty>]
        Montuje obraz dysku przez loop device.
        """
        if len(args) < 2:
            return "Użycie: vdrive vhd-mount <plik> <punkt_montowania> [--offset <bajty>]"

        path = self._abs(args[0])
        mp = self._abs(args[1])
        offset = None
        for i, a in enumerate(args):
            if a == "--offset" and i + 1 < len(args):
                offset = args[i + 1]

        ok, msg = self._require_file(path)
        if not ok:
            return msg

        if not _defender_ok(path):
            _vdrive_notify(self.terminal, f"Defender zablokował montowanie: {os.path.basename(path)}", kind="warn")
            return f"🛑 Defender oznaczył '{os.path.basename(path)}' jako niebezpieczny. Montowanie wstrzymane."

        # For non-raw formats, convert to raw temp first
        fmt = self._qemu_fmt(path)
        tmp_raw = None

        if fmt != "raw":
            ok2, msg2 = _require_tool("qemu-img")
            if not ok2:
                return msg2
            tmp_raw = path + ".mount.raw.tmp"
            code, out, err = _run(
                ["qemu-img", "convert", "-", fmt, "-O", "raw", path, tmp_raw])
            if code != 0:
                return f"❌ Konwersja do RAW nie powiodła się:\n{err}"
            mount_target = tmp_raw
        else:
            mount_target = path

        os.makedirs(mp, exist_ok=True)
        mount_opts = ["loop"]
        if offset:
            mount_opts.append(f"offset={offset}")

        code, out, err = _run(
            ["mount", "-o", ",".join(mount_opts), mount_target, mp])

        if code == 0:
            self._mounts.add(path, mp, "vhd-loop",
                             loop_dev=tmp_raw or "")
            _vdrive_notify(self.terminal, f"Dysk zamontowany: {os.path.basename(path)} → {mp}", kind="ok")
            return (
                "✅ Dysk zamontowany!\n"
                f"   Obraz : {path} (fmt: {fmt})\n"
                f"   Punkt : {mp}\n"
                + (f"   Offset: {offset}\n" if offset else "")
                + f"Odmontuj : vdrive vhd-umount {mp}"
            )

        if tmp_raw and os.path.exists(tmp_raw):
            os.remove(tmp_raw)
        return (
            f"⚠️  Montowanie nie powiodło się (brak uprawnień root?):\n{err}\n"
            "💡 Alternatywa: użyj vdrive vhd-extract (jeśli dostępne)"
        )

    def cmd_vhd_umount(self, args: List[str]) -> str:
        """
        vdrive vhd-umount <punkt_montowania>
        Odmontowuje wirtualny dysk.
        """
        if not args:
            return "Użycie: vdrive vhd-umount <punkt_montowania>"
        mp = self._abs(args[0])

        info = self._mounts.all().get(mp, {})
        code, out, err = _run(["umount", mp])
        if code == 0:
            self._mounts.remove(mp)
            # Clean up tmp raw if exists
            loop_dev = info.get("loop_dev", "")
            if loop_dev and loop_dev.endswith(".mount.raw.tmp") and os.path.exists(loop_dev):
                os.remove(loop_dev)
            _vdrive_notify(self.terminal, f"Dysk odmontowany: {mp}", kind="ok")
            return f"✅ Odmontowano: {mp}"
        return f"❌ Błąd odmontowania: {err}"

    def cmd_vhd_delete(self, args: List[str]) -> str:
        """
        vdrive vhd-delete <plik> [--force] [--wipe] [--passes N]
        Usuwa wirtualny dysk. Opcja --wipe nadpisuje plik przed usunięciem.
        """
        if not args:
            return "Użycie: vdrive vhd-delete <plik> [--force] [--wipe] [--passes N]"
        path = self._abs(args[0])
        force = "--force" in args
        wipe = "--wipe" in args
        
        passes = 1
        if "--passes" in args:
            try:
                idx = args.index("--passes")
                passes = int(args[idx + 1])
            except (ValueError, IndexError):
                pass

        ok, msg = self._require_file(path)
        if not ok:
            return msg

        if not force:
            size = os.path.getsize(path)
            wipe_msg = f" (BEZPIECZNE NADPISYWANIE - {passes} przebiegów)" if wipe else ""
            return (
                f"⚠️  Usuń '{os.path.basename(path)}' ({_size_human(size)}){wipe_msg}?\n"
                f"Potwierdź: vdrive vhd-delete {args[0]} --force {'--wipe' if wipe else ''}"
            )

        # Check if mounted
        mp = self._mounts.find_by_image(path)
        if mp:
            return f"❌ Dysk jest zamontowany w '{mp}'. Najpierw odmontuj: vdrive vhd-umount {mp}"

        if wipe:
            try:
                size = os.path.getsize(path)
                import secrets
                
                with open(path, "ba+", buffering=0) as f:
                    for p in range(1, passes + 1):
                        if RICH_AVAILABLE:
                            with Progress(
                                SpinnerColumn(),
                                TextColumn(f"[bold red]Wiping ({p}/{passes})[/bold red] {Path(path).name}"),
                                BarColumn(),
                                DownloadColumn(),
                                TaskProgressColumn(),
                                transient=True
                            ) as progress:
                                task = progress.add_task("Wiping...", total=size)
                                # DOD 5220.22-M: Pass 1: Zeros, Pass 2: Ones, Pass 3: Random
                                if p == 1: chunk_base = b'\x00'
                                elif p == 2: chunk_base = b'\xff'
                                else: chunk_base = None
                                
                                chunk_size = 1024 * 1024
                                if chunk_base:
                                    chunk = chunk_base * chunk_size
                                
                                f.seek(0)
                                written = 0
                                while written < size:
                                    to_write = min(chunk_size, size - written)
                                    if not chunk_base:
                                        f.write(secrets.token_bytes(to_write))
                                    else:
                                        f.write(chunk[:to_write])
                                    written += to_write
                                    progress.update(task, advance=to_write)
                        else:
                            f.seek(0)
                            f.write(b'\x00' * size)
                    f.flush()
                    os.fsync(f.fileno())
            except Exception as e:
                _vdrive_notify(self.terminal, f"Błąd bezpiecznego usuwania: {os.path.basename(path)}", kind="err")
                return f"❌ Błąd bezpiecznego usuwania: {e}"

            # Po nadpisaniu plik jest już nie do odzyskania - usuwamy trwale,
            # przenoszenie do kosza nie ma sensu (zawartość jest wyzerowana/random).
            os.remove(path)
            _vdrive_log(self.terminal, "WARN", f"vdrive: bezpieczne usunięcie (wipe x{passes}) {path}")
            _vdrive_notify(self.terminal, f"Dysk bezpiecznie usunięty: {os.path.basename(path)}", kind="warn", title="VDRIVE/SEC")
            return f"✅ Bezpiecznie usunięto (wipe x{passes}): {path}"

        # Bez --wipe: przenosimy do kosza EcoSystemu (trash.py) zamiast
        # trwale usuwać — zgodnie z konwencją reszty modułów (docs, command,
        # imgtools). Plik można odzyskać przez `trash restore`.
        ok_trash, dst_or_err = _trash_move(path)
        if ok_trash:
            _vdrive_notify(self.terminal, f"Dysk przeniesiony do kosza: {os.path.basename(path)}", kind="ok")
            return f"✅ Przeniesiono do kosza: {path}\n   Przywróć: trash restore {os.path.basename(dst_or_err)}"

        # Fallback - kosz niedostępny, usuń trwale jak poprzednio
        try:
            os.remove(path)
        except OSError as exc:
            return f"❌ Błąd usuwania: {exc}"
        _vdrive_notify(self.terminal, f"Dysk usunięty (bez kosza): {os.path.basename(path)}", kind="warn")
        return f"✅ Usunięto: {path}\n⚠️  Kosz niedostępny ({dst_or_err}) — usunięto trwale."

    # ------------------------------------------------------------------ #
    #  Mount overview                                                       #
    # ------------------------------------------------------------------ #

    def cmd_mounts(self, args: List[str]) -> str:
        """
        vdrive mounts
        Wyświetla wszystkie aktywne montowania.
        """
        mounts = self._mounts.all()
        if not mounts:
            return "ℹ️  Brak aktywnych montowań."
        lines = ["==== AKTYWNE MONTOWANIA ====\n"]
        for mp, info in mounts.items():
            lines.append(f"  Punkt   : {mp}")
            lines.append(f"  Obraz   : {info.get('image','?')}")
            lines.append(f"  Typ     : {info.get('kind','?')}")
            lines.append(f"  Zamontowano: {info.get('mounted_at','?')}")
            lines.append("")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  General vdrive list                                                 #
    # ------------------------------------------------------------------ #

    def cmd_list(self, args: List[str]) -> str:
        """
        vdrive list [katalog]
        Wyświetla pliki ISO i dysków wirtualnych w katalogu.
        """
        search_dir = self._abs(args[0]) if args else os.getcwd()
        if not os.path.isdir(search_dir):
            return f"❌ Katalog '{search_dir}' nie istnieje."

        exts = set(
            list(self.SUPPORTED_VHD_FORMATS.keys()) + ["iso"]
        )
        found = []
        try:
            for f in os.listdir(search_dir):
                ext = Path(f).suffix.lstrip(".").lower()
                if ext in exts:
                    full = os.path.join(search_dir, f)
                    size = os.path.getsize(full)
                    found.append((f, ext.upper(), size, full))
        except Exception as e:
            return f"❌ Błąd odczytu katalogu: {e}"

        if not found:
            return f"ℹ️  Brak plików ISO/VHD w '{search_dir}'."

        lines = [f"==== WIRTUALNE DYSKI/ISO: {search_dir} ====\n"]
        for name, fmt, size, full in sorted(found):
            lines.append(f"  {fmt:<6}  {_size_human(size):>10}   {name}")
        lines.append(f"\nRazem: {len(found)} plików")
        return "\n".join(lines)

    # ------------------------------------------------------------------ #
    #  Help                                                                 #
    # ------------------------------------------------------------------ #

    HELP = """
==== VIRTUAL DRIVE MANAGER ====

Zarządzanie obrazami ISO oraz wirtualnymi dyskami (VHD/VHDX/VMDK/QCOW2/VDI/RAW).

── ISO ────────────────────────────────────────────────────────
  vdrive iso-create <out.iso> <katalog> [--label X] [--joliet] [--rockridge]
  vdrive iso-info <plik.iso>            Info o ISO (PVD)
  vdrive iso-list <plik.iso> [--max N]  Zawartość ISO
  vdrive iso-extract <plik.iso> <dest>  Wypakuj ISO
  vdrive iso-mount <plik.iso> <punkt>   Zamontuj ISO
  vdrive iso-umount <punkt>             Odmontuj ISO
  vdrive iso-checksum <plik.iso> [--sha256] [--save]  Suma kontrolna

── WIRTUALNE DYSKI ────────────────────────────────────────────
  vdrive vhd-create <plik> <rozmiar> [--format vhd|vhdx|qcow2|vmdk|vdi|raw]
                    [--prealloc] [--backing <base>]
  vdrive vhd-info <plik>              Szczegółowe info
  vdrive vhd-convert <src> <dst> [--format fmt] [--compress]
  vdrive vhd-resize <plik> <rozmiar> [--shrink]
  vdrive vhd-compact <plik>           Kompaktuj (zmniejsz plik)
  vdrive vhd-clone <src> <dst> [--format fmt]
  vdrive vhd-merge <plik>             Scal z backing file
  vdrive vhd-check <plik> [--repair]  Sprawdź integralność
  vdrive vhd-encrypt <src> <dst.qcow2> <hasło>  Szyfrowanie LUKS
  vdrive vhd-mount <plik> <punkt> [--offset B]
  vdrive vhd-umount <punkt>
  vdrive vhd-delete <plik> [--force] [--wipe] [--passes N]

── SNAPSHOTY (qcow2/qcow) ────────────────────────────────────
  vdrive vhd-snap-create <plik.qcow2> <nazwa>
  vdrive vhd-snap-list <plik.qcow2>
  vdrive vhd-snap-restore <plik.qcow2> <nazwa>
  vdrive vhd-snap-delete <plik.qcow2> <nazwa>

── OGÓLNE ────────────────────────────────────────────────────
  vdrive list [katalog]    Lista ISO/VHD w katalogu
  vdrive mounts            Aktywne montowania
  vdrive help              Ta pomoc

Obsługiwane formaty: VHD (vpc), VHDX, QCOW2, QCOW, VMDK, VDI, RAW/IMG
Snapshoty: tylko QCOW2/QCOW
Szyfrowanie: LUKS (qcow2), VeraCrypt (.hc), AES-256 (OpenSSL)

Wymagane narzędzia:
  - qemu-img   (VHD/konwersje/snapshoty/szyfrowanie)
  - genisoimage (tworzenie ISO)
  - fuseiso    (montowanie ISO bez root)
  - isoinfo    (listowanie/ekstrakcja ISO)
"""


# ---------------------------------------------------------------------------
# Terminal CLI v2.0 Integration
# ---------------------------------------------------------------------------

def vdrive_command(args: List[str]) -> str:
    """Main vdrive command dispatcher"""
    if not args:
        return vdrive_manager.HELP
    
    subcommand = args[0]
    subargs = args[1:]
    
    # Map subcommands to methods
    command_map = {
        # ISO commands
        'iso-create': vdrive_manager.cmd_iso_create,
        'iso-info': vdrive_manager.cmd_iso_info,
        'iso-list': vdrive_manager.cmd_iso_list,
        'iso-extract': vdrive_manager.cmd_iso_extract,
        'iso-mount': vdrive_manager.cmd_iso_mount,
        'iso-umount': vdrive_manager.cmd_iso_umount,
        'iso-checksum': vdrive_manager.cmd_iso_checksum,
        
        # VHD commands
        'vhd-create': vdrive_manager.cmd_vhd_create,
        'vhd-info': vdrive_manager.cmd_vhd_info,
        'vhd-convert': vdrive_manager.cmd_vhd_convert,
        'vhd-resize': vdrive_manager.cmd_vhd_resize,
        'vhd-compact': vdrive_manager.cmd_vhd_compact,
        'vhd-clone': vdrive_manager.cmd_vhd_clone,
        'vhd-merge': vdrive_manager.cmd_vhd_merge,
        'vhd-check': vdrive_manager.cmd_vhd_check,
        'vhd-encrypt': vdrive_manager.cmd_vhd_encrypt,
        'vhd-mount': vdrive_manager.cmd_vhd_mount,
        'vhd-umount': vdrive_manager.cmd_vhd_umount,
        'vhd-delete': vdrive_manager.cmd_vhd_delete,
        
        # Snapshot commands
        'vhd-snap-create': vdrive_manager.cmd_vhd_snapshot_create,
        'vhd-snap-list': vdrive_manager.cmd_vhd_snapshot_list,
        'vhd-snap-restore': vdrive_manager.cmd_vhd_snapshot_restore,
        'vhd-snap-delete': vdrive_manager.cmd_vhd_snapshot_delete,
        
        # General commands
        'list': vdrive_manager.cmd_list,
        'mounts': vdrive_manager.cmd_mounts,
        'help': lambda args: vdrive_manager.HELP,
    }
    
    if subcommand in command_map:
        try:
            return command_map[subcommand](subargs)
        except Exception as e:
            return f"Error executing vdrive {subcommand}: {e}"
    else:
        return f"Unknown vdrive subcommand: {subcommand}\n{vdrive_manager.HELP}"

# Individual command functions for direct registration
def iso_create_command(args: List[str]) -> str:
    """Create ISO from directory"""
    return vdrive_manager.cmd_iso_create(args)

def iso_info_command(args: List[str]) -> str:
    """Show ISO information"""
    return vdrive_manager.cmd_iso_info(args)

def iso_list_command(args: List[str]) -> str:
    """List ISO contents"""
    return vdrive_manager.cmd_iso_list(args)

def iso_extract_command(args: List[str]) -> str:
    """Extract ISO contents"""
    return vdrive_manager.cmd_iso_extract(args)

def iso_mount_command(args: List[str]) -> str:
    """Mount ISO image"""
    return vdrive_manager.cmd_iso_mount(args)

def iso_umount_command(args: List[str]) -> str:
    """Unmount ISO image"""
    return vdrive_manager.cmd_iso_umount(args)

def iso_checksum_command(args: List[str]) -> str:
    """Calculate ISO checksum"""
    return vdrive_manager.cmd_iso_checksum(args)

def vhd_create_command(args: List[str]) -> str:
    """Create virtual disk"""
    return vdrive_manager.cmd_vhd_create(args)

def vhd_info_command(args: List[str]) -> str:
    """Show virtual disk information"""
    return vdrive_manager.cmd_vhd_info(args)

def vhd_convert_command(args: List[str]) -> str:
    """Convert virtual disk format"""
    return vdrive_manager.cmd_vhd_convert(args)

def vhd_resize_command(args: List[str]) -> str:
    """Resize virtual disk"""
    return vdrive_manager.cmd_vhd_resize(args)

def vhd_compact_command(args: List[str]) -> str:
    """Compact virtual disk"""
    return vdrive_manager.cmd_vhd_compact(args)

def vhd_clone_command(args: List[str]) -> str:
    """Clone virtual disk"""
    return vdrive_manager.cmd_vhd_clone(args)

def vhd_merge_command(args: List[str]) -> str:
    """Merge virtual disk with backing file"""
    return vdrive_manager.cmd_vhd_merge(args)

def vhd_check_command(args: List[str]) -> str:
    """Check virtual disk integrity"""
    return vdrive_manager.cmd_vhd_check(args)

def vhd_encrypt_command(args: List[str]) -> str:
    """Encrypt virtual disk"""
    return vdrive_manager.cmd_vhd_encrypt(args)

def vhd_mount_command(args: List[str]) -> str:
    """Mount virtual disk"""
    return vdrive_manager.cmd_vhd_mount(args)

def vhd_umount_command(args: List[str]) -> str:
    """Unmount virtual disk"""
    return vdrive_manager.cmd_vhd_umount(args)

def vhd_delete_command(args: List[str]) -> str:
    """Delete virtual disk"""
    return vdrive_manager.cmd_vhd_delete(args)

def vhd_snap_create_command(args: List[str]) -> str:
    """Create virtual disk snapshot"""
    return vdrive_manager.cmd_vhd_snapshot_create(args)

def vhd_snap_list_command(args: List[str]) -> str:
    """List virtual disk snapshots"""
    return vdrive_manager.cmd_vhd_snapshot_list(args)

def vhd_snap_restore_command(args: List[str]) -> str:
    """Restore virtual disk snapshot"""
    return vdrive_manager.cmd_vhd_snapshot_restore(args)

def vhd_snap_delete_command(args: List[str]) -> str:
    """Delete virtual disk snapshot"""
    return vdrive_manager.cmd_vhd_snapshot_delete(args)

def vdrive_list_command(args: List[str]) -> str:
    """List virtual drives in directory"""
    return vdrive_manager.cmd_list(args)

def vdrive_mounts_command(args: List[str]) -> str:
    """Show active mounts"""
    return vdrive_manager.cmd_mounts(args)

def vdrive_help_command(args: List[str]) -> str:
    """Show vdrive help"""
    return vdrive_manager.HELP

# Async command functions
async def async_iso_create_command(args: List[str]) -> str:
    """Async ISO creation"""
    return await async_vdrive_manager.cmd_iso_create_async(args)

async def async_vhd_create_command(args: List[str]) -> str:
    """Async VHD creation"""
    return await async_vdrive_manager.cmd_vhd_create_async(args)

async def async_vhd_convert_command(args: List[str]) -> str:
    """Async VHD conversion"""
    return await async_vdrive_manager.cmd_vhd_convert_async(args)

async def async_vhd_compact_command(args: List[str]) -> str:
    """Async VHD compaction"""
    return await async_vdrive_manager.cmd_vhd_compact_async(args)

async def async_vhd_check_command(args: List[str]) -> str:
    """Async VHD integrity check / repair"""
    return await async_vdrive_manager.cmd_vhd_check_async(args)

async def async_iso_checksum_command(args: List[str]) -> str:
    """Async ISO checksum"""
    return await async_vdrive_manager.cmd_iso_checksum_async(args)

async def async_vhd_delete_command(args: List[str]) -> str:
    """Async secure VHD delete"""
    return await async_vdrive_manager.cmd_vhd_delete_async(args)

# ══════════════════════════════════════════════════════════════════════════════
#  LEGACY MODULE INTERFACE (pozostawione dla zgodności / inspekcji API)
#  Uwaga: core/__init__.py wywołuje wyłącznie setup(terminal)/teardown(terminal)
#  zdefiniowane na końcu pliku. list_commands()/execute() to dawny interfejs
#  ModuleManagera dla modułów z /modules/ — nieużywany od przeniesienia do core,
#  zachowany jako alternatywne, programistyczne API dostępu do komend.
# ══════════════════════════════════════════════════════════════════════════════

def init(terminal) -> None:
    """Wywoływane przez setup() po rejestracji komend."""
    pass

def list_commands() -> Dict[str, Dict[str, str]]:
    """Zwraca mapę komend rejestrowanych automatycznie przez ModuleManager."""
    group = "Virtual Drives"
    return {
        "vdrive": {"category": group, "description": "Główna komenda zarządzania dyskami wirtualnymi"},
        "iso-create": {"category": group, "description": "Utwórz obraz ISO"},
        "iso-info": {"category": group, "description": "Pokaż informacje o ISO"},
        "iso-list": {"category": group, "description": "Lista zawartości ISO"},
        "iso-extract": {"category": group, "description": "Wypakuj pliki z ISO"},
        "iso-mount": {"category": group, "description": "Zamontuj ISO"},
        "iso-umount": {"category": group, "description": "Odmontuj ISO"},
        "iso-checksum": {"category": group, "description": "Sprawdź sumę kontrolną ISO"},
        "vhd-create": {"category": group, "description": "Utwórz dysk wirtualny"},
        "vhd-info": {"category": group, "description": "Pokaż informacje o dysku"},
        "vhd-convert": {"category": group, "description": "Konwertuj format dysku"},
        "vhd-resize": {"category": group, "description": "Zmień rozmiar dysku"},
        "vhd-compact": {"category": group, "description": "Kompaktuj dysk"},
        "vhd-clone": {"category": group, "description": "Klonuj dysk"},
        "vhd-merge": {"category": group, "description": "Scal dysk"},
        "vhd-check": {"category": group, "description": "Sprawdź integralność dysku"},
        "vhd-repair": {"category": group, "description": "Napraw uszkodzony dysk"},
        "vhd-encrypt": {"category": group, "description": "Szyfruj dysk"},
        "vhd-mount": {"category": group, "description": "Zamontuj dysk"},
        "vhd-umount": {"category": group, "description": "Odmontuj dysk"},
        "vhd-delete": {"category": group, "description": "Usuń dysk"},
        "vhd-snap-create": {"category": group, "description": "Utwórz migawkę"},
        "vhd-snap-list": {"category": group, "description": "Lista migawek"},
        "vhd-snap-restore": {"category": group, "description": "Przywróć migawkę"},
        "vhd-snap-delete": {"category": group, "description": "Usuń migawkę"},
        "vdrive-list": {"category": group, "description": "Lista dysków w katalogu"},
        "vdrive-mounts": {"category": group, "description": "Pokaż aktywne montowania"},
        "vdrive-help": {"category": group, "description": "Pomoc vdrive manager"},
    }

def execute(command: str, args: List[str]) -> Optional[str]:
    """Dispatcher wywoływany przez ModuleManager dla każdej komendy."""
    # Mapowanie komend na funkcje
    command_map = {
        "vdrive": vdrive_manager.cmd_vdrive_info,
        "iso-create": vdrive_manager.cmd_iso_create,
        "iso-info": vdrive_manager.cmd_iso_info,
        "iso-list": vdrive_manager.cmd_iso_list,
        "iso-extract": vdrive_manager.cmd_iso_extract,
        "iso-mount": vdrive_manager.cmd_iso_mount,
        "iso-umount": vdrive_manager.cmd_iso_umount,
        "iso-checksum": vdrive_manager.cmd_iso_checksum,
        "vhd-create": vdrive_manager.cmd_vhd_create,
        "vhd-info": vdrive_manager.cmd_vhd_info,
        "vhd-convert": vdrive_manager.cmd_vhd_convert,
        "vhd-resize": vdrive_manager.cmd_vhd_resize,
        "vhd-compact": vdrive_manager.cmd_vhd_compact,
        "vhd-clone": vdrive_manager.cmd_vhd_clone,
        "vhd-merge": vdrive_manager.cmd_vhd_merge,
        "vhd-check": vdrive_manager.cmd_vhd_check,
        "vhd-repair": lambda args: vdrive_manager.cmd_vhd_check(args + ["--repair"]),
        "vhd-encrypt": vdrive_manager.cmd_vhd_encrypt,
        "vhd-mount": vdrive_manager.cmd_vhd_mount,
        "vhd-umount": vdrive_manager.cmd_vhd_umount,
        "vhd-delete": vdrive_manager.cmd_vhd_delete,
        "vhd-snap-create": vdrive_manager.cmd_vhd_snapshot_create,
        "vhd-snap-list": vdrive_manager.cmd_vhd_snapshot_list,
        "vhd-snap-restore": vdrive_manager.cmd_vhd_snapshot_restore,
        "vhd-snap-delete": vdrive_manager.cmd_vhd_snapshot_delete,
        "vdrive-list": vdrive_manager.cmd_list,
        "vdrive-mounts": vdrive_manager.cmd_mounts,
        "vdrive-help": lambda args: vdrive_manager.HELP,
    }
    
    handler = command_map.get(command)
    if handler:
        return handler(args)
    else:
        return f"[vdrive_manager] Nieznana komenda: {command}"

# Global singleton instances (created after all class definitions)
vdrive_manager = VirtualDriveManager()
async_vdrive_manager = AsyncVirtualDriveManager()
async_vdrive_manager.set_manager(vdrive_manager)


# ─── CML command wrappers ─────────────────────────────────────────────────────
# Uwaga: _w, RST/BOLD/DIM/... i _pad importowane z core._shared (patrz import
# na początku pliku) — usunięto lokalne duplikaty po przeniesieniu modułu do
# core/. Dzięki temu vdrive dziedziczy automatycznie wykrywanie wsparcia ANSI
# (NO_COLOR/FORCE_COLOR) tak jak wszystkie inne moduły ekosystemu.

def _out(result):
    if result:
        _w(result + "\n")

def cmd_vdrive(args, terminal):
    """Główna komenda dysków wirtualnych (info / lista / montowania)."""
    if not args:
        cml_menu()
        return
    sub = args[0].lower()
    rest = args[1:]
    sub_map = {
        "info":    lambda: _out(vdrive_manager.cmd_vdrive_info(rest)),
        "list":    lambda: _out(vdrive_manager.cmd_list(rest)),
        "mounts":  lambda: _out(vdrive_manager.cmd_mounts(rest)),
    }
    fn = sub_map.get(sub)
    if fn:
        fn()
    else:
        _w(f"  {RED}Nieznana podkomenda: {sub}{RST}  "
           f"{DIM}Wpisz {RST}{YLW}vdrive{RST}{DIM} aby zobaczyć menu.{RST}\n")

def cmd_iso(args, terminal):
    """Komendy ISO: iso <create|info|list|extract|mount|umount|checksum> ..."""
    if not args:
        _w(f"  {DIM}Użycie: iso <create|info|list|extract|mount|umount|checksum> [opcje]{RST}\n")
        return
    sub = args[0].lower()
    rest = args[1:]
    iso_map = {
        "create":   vdrive_manager.cmd_iso_create,
        "info":     vdrive_manager.cmd_iso_info,
        "list":     vdrive_manager.cmd_iso_list,
        "extract":  vdrive_manager.cmd_iso_extract,
        "mount":    vdrive_manager.cmd_iso_mount,
        "umount":   vdrive_manager.cmd_iso_umount,
        "checksum": vdrive_manager.cmd_iso_checksum,
    }
    fn = iso_map.get(sub)
    if fn:
        _out(fn(rest))
    else:
        _w(f"  {RED}Nieznana podkomenda iso: {sub}{RST}\n")

def cmd_vhd(args, terminal):
    """Komendy VHD: vhd <create|info|convert|resize|compact|clone|merge|check|encrypt|mount|umount|delete|snap> ..."""
    if not args:
        _w(f"  {DIM}Użycie: vhd <create|info|convert|resize|...> [opcje]{RST}\n")
        return
    sub = args[0].lower()
    rest = args[1:]
    vhd_map = {
        "create":   vdrive_manager.cmd_vhd_create,
        "info":     vdrive_manager.cmd_vhd_info,
        "convert":  vdrive_manager.cmd_vhd_convert,
        "resize":   vdrive_manager.cmd_vhd_resize,
        "compact":  vdrive_manager.cmd_vhd_compact,
        "clone":    vdrive_manager.cmd_vhd_clone,
        "merge":    vdrive_manager.cmd_vhd_merge,
        "check":    vdrive_manager.cmd_vhd_check,
        "repair":   lambda args: vdrive_manager.cmd_vhd_check(args + ["--repair"]),
        "encrypt":  vdrive_manager.cmd_vhd_encrypt,
        "mount":    vdrive_manager.cmd_vhd_mount,
        "umount":   vdrive_manager.cmd_vhd_umount,
        "delete":   vdrive_manager.cmd_vhd_delete,
    }
    if sub == "snap":
        if not rest:
            _w(f"  {DIM}Użycie: vhd snap <create|list|restore|delete> [opcje]{RST}\n")
            return
        snap_sub = rest[0].lower()
        snap_map = {
            "create":  vdrive_manager.cmd_vhd_snapshot_create,
            "list":    vdrive_manager.cmd_vhd_snapshot_list,
            "restore": vdrive_manager.cmd_vhd_snapshot_restore,
            "delete":  vdrive_manager.cmd_vhd_snapshot_delete,
        }
        fn = snap_map.get(snap_sub)
        if fn:
            _out(fn(rest[1:]))
        else:
            _w(f"  {RED}Nieznana podkomenda vhd snap: {snap_sub}{RST}\n")
        return
    fn = vhd_map.get(sub)
    if fn:
        _out(fn(rest))
    else:
        _w(f"  {RED}Nieznana podkomenda vhd: {sub}{RST}\n")


# ─── CML_COMMANDS ─────────────────────────────────────────────────────────────

CML_COMMANDS = {
    "vdrive": cmd_vdrive,
    "iso":    cmd_iso,
    "vhd":    cmd_vhd,
}


# ─── cml_menu ─────────────────────────────────────────────────────────────────

def cml_menu():
    _w(f"\n{BOLD}{BCYN}  ╭──────────────────────────────────────────╮{RST}\n")
    _w(f"{BOLD}{BCYN}  │   💽  Moduł: VDrive Manager  v1.0.0     │{RST}\n")
    _w(f"{BOLD}{BCYN}  ╰──────────────────────────────────────────╯{RST}\n\n")

    sections = [
        ("ISO", [
            ("iso create <plik> <katalog>", "Utwórz obraz ISO"),
            ("iso info <plik>",             "Informacje o ISO"),
            ("iso list <plik>",             "Lista zawartości ISO"),
            ("iso extract <plik> <cel>",    "Wypakuj pliki z ISO"),
            ("iso mount <plik> <punkt>",    "Zamontuj ISO"),
            ("iso umount <punkt>",          "Odmontuj ISO"),
            ("iso checksum <plik>",         "Suma kontrolna ISO"),
        ]),
        ("VHD / Dyski wirtualne", [
            ("vhd create <plik> <rozmiar>", "Utwórz dysk wirtualny"),
            ("vhd info <plik>",             "Informacje o dysku"),
            ("vhd convert <src> <dst>",     "Konwertuj format dysku"),
            ("vhd resize <plik> <rozmiar>", "Zmień rozmiar dysku"),
            ("vhd compact <plik>",          "Kompaktuj dysk"),
            ("vhd clone <src> <dst>",       "Klonuj dysk"),
            ("vhd merge <src> <dst>",       "Scal dysk"),
            ("vhd check <plik>",            "Sprawdź integralność dysku"),
            ("vhd repair <plik>",           "Napraw uszkodzony dysk"),
            ("vhd encrypt <plik>",          "Szyfruj dysk"),
            ("vhd mount <plik> <punkt>",    "Zamontuj dysk"),
            ("vhd umount <punkt>",          "Odmontuj dysk"),
            ("vhd delete <plik> [--wipe]",  "Usuń dysk (opcjonalnie bezpiecznie)"),
        ]),
        ("Migawki (Snapshots)", [
            ("vhd snap create <plik>",      "Utwórz migawkę"),
            ("vhd snap list <plik>",        "Lista migawek"),
            ("vhd snap restore <plik>",     "Przywróć migawkę"),
            ("vhd snap delete <plik>",      "Usuń migawkę"),
        ]),
        ("Zarządzanie", [
            ("vdrive list",                 "Lista dysków w katalogu"),
            ("vdrive mounts",               "Pokaż aktywne montowania"),
            ("vdrive info",                 "Informacje o menadżerze"),
        ]),
    ]

    for section, cmds in sections:
        _w(f"  {BOLD}{WHT}{section}{RST}\n")
        for c, d in cmds:
            _w(f"    {YLW}{_pad(c, 34)}{RST} {DIM}{d}{RST}\n")
        _w("\n")


# ─── on_load ──────────────────────────────────────────────────────────────────

def on_load():
    pass


# ─── setup / teardown (wymagane przez core/__init__.py EcoSystem) ─────────────

def setup(terminal) -> None:
    """Rejestruje komendy vdrive w TerminalX EcoSystem i podłącza integrację."""
    # Referencja do terminala - potrzebna metodom cmd_* manager'a do wysyłania
    # notify/debugger bez przekazywania jej jako argumentu w każdym wywołaniu.
    vdrive_manager.terminal = terminal

    cat = terminal.t("cat_ecosystem")

    terminal.register_command(
        "vdrive",
        lambda args: cmd_vdrive(args, terminal),
        description=terminal.t("cmd_vdrive"),
        category=cat,
    )
    terminal.register_command(
        "iso",
        lambda args: cmd_iso(args, terminal),
        description=terminal.t("cmd_iso"),
        category=cat,
    )
    terminal.register_command(
        "vhd",
        lambda args: cmd_vhd(args, terminal),
        description=terminal.t("cmd_vhd"),
        category=cat,
    )

    # Rejestracja w _integration - inne moduly (monitor, docs, search) moga
    # odpytac stan dyskow wirtualnych bez bezposredniego importu core.vdrive.
    try:
        _integration.register("vdrive", {
            "get_mounts":   lambda: vdrive_manager._mounts.all(),
            "is_mounted":   lambda path: bool(vdrive_manager._mounts.find_by_image(
                                os.path.abspath(os.path.expanduser(path)))),
            "list_drives":  vdrive_manager.cmd_list,
            "mounts_text":  vdrive_manager.cmd_mounts,
            "qemu_info":    vdrive_manager._qemu_info,
        })
    except Exception:
        pass

    init(terminal)
    on_load()


def teardown(terminal) -> None:
    """Wyrejestrowuje komendy vdrive i odpina integrację."""
    terminal.commands.pop("vdrive", None)
    terminal.commands.pop("iso", None)
    terminal.commands.pop("vhd", None)
    try:
        _integration.unregister("vdrive")
    except Exception:
        pass
