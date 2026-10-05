"""Pfade für Nutzerdaten.

Alles liegt gesammelt in „Dokumente\\DMNT-Kobold\\“ (Stefans Vorgabe: sichtbar,
an einem Ort, leicht mitzunehmen). Der Dokumente-Ordner wird bei Windows
erfragt, damit ein umgeleiteter Ordner (z. B. OneDrive) stimmt.
Für Tests/Sonderfälle: Umgebungsvariable DMNT_KOBOLD_DATEN.

  daten/         Speicher der Tricks, einstellungen.json, zustand.json
  module/        selbst beigebrachte Tricks
  sicherungen/   tägliche ZIP-Sicherungen (7 Stück)
  logs/          kobold.log
  cache/         erzeugte Töne (darf gelöscht werden)
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "DMNT-Kobold"


def _dokumente() -> Path:
    if sys.platform == "win32":
        try:
            import ctypes
            from ctypes import wintypes

            class GUID(ctypes.Structure):
                _fields_ = [("d1", wintypes.DWORD), ("d2", wintypes.WORD), ("d3", wintypes.WORD),
                            ("d4", ctypes.c_ubyte * 8)]

            # FOLDERID_Documents {FDD39AD0-238F-46AF-ADB4-6C85480369C7}
            g = GUID(0xFDD39AD0, 0x238F, 0x46AF, (ctypes.c_ubyte * 8)(0xAD, 0xB4, 0x6C, 0x85, 0x48, 0x03, 0x69, 0xC7))
            zeiger = ctypes.c_wchar_p()
            if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(g), 0, None, ctypes.byref(zeiger)) == 0:
                pfad = Path(zeiger.value)
                ctypes.windll.ole32.CoTaskMemFree(zeiger)
                return pfad
        except (OSError, AttributeError):
            pass
    return Path.home() / "Documents"


PORTABLE_MARKE = "portable.txt"


def programmordner() -> Path | None:
    """Ordner der ausgelieferten EXE, im Entwickler-Start None."""
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else None


def installationsart() -> str:
    """``entwickler`` (aus dem Quellcode), ``portable`` (``portable.txt`` neben der EXE)
    oder ``installiert`` (über das Setup)."""
    ordner = programmordner()
    if ordner is None:
        return "entwickler"
    return "portable" if (ordner / PORTABLE_MARKE).exists() else "installiert"


def datenordner() -> Path:
    eigen = os.environ.get("DMNT_KOBOLD_DATEN")
    if eigen:
        ordner = Path(eigen)
    elif installationsart() == "portable":       # Daten wandern mit dem Ordner mit
        ordner = programmordner() / "daten"
    else:
        ordner = _dokumente() / APP_NAME
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def logordner() -> Path:
    ordner = datenordner() / "logs"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def lockdatei() -> Path:
    return datenordner() / "kobold.lock"
