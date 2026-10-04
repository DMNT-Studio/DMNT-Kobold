"""Pfade für Nutzerdaten: %APPDATA%\\DMNT-Kobold\\ (Logs, Lockfile)."""
from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "DMNT-Kobold"


def datenordner() -> Path:
    basis = os.environ.get("APPDATA")
    if basis:
        ordner = Path(basis) / APP_NAME
    else:  # Entwicklung außerhalb von Windows
        ordner = Path.home() / ".local" / "share" / APP_NAME
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def logordner() -> Path:
    ordner = datenordner() / "logs"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


def lockdatei() -> Path:
    return datenordner() / "kobold.lock"
