"""Mit Windows starten: Eintrag unter HKCU\\...\\Run (nur für diesen Nutzer,
keine Adminrechte)."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

log = logging.getLogger(__name__)

SCHLUESSEL = r"Software\Microsoft\Windows\CurrentVersion\Run"
WERT = "DMNT-Kobold"


def befehl() -> str:
    """Startbefehl: die EXE (ausgeliefert) oder pythonw -m dmnt_kobold (Entwicklung)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = Path(sys.executable)
    pythonw = exe.with_name("pythonw.exe")
    if pythonw.exists():
        exe = pythonw
    return f'"{exe}" -m dmnt_kobold'


def ist_an() -> bool:
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCHLUESSEL) as k:
            winreg.QueryValueEx(k, WERT)
            return True
    except OSError:
        return False


def setzen(an: bool) -> bool:
    """Liefert den tatsächlichen Zustand danach."""
    if sys.platform != "win32":
        return False
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SCHLUESSEL, 0, winreg.KEY_SET_VALUE) as k:
            if an:
                winreg.SetValueEx(k, WERT, 0, winreg.REG_SZ, befehl())
            else:
                try:
                    winreg.DeleteValue(k, WERT)
                except FileNotFoundError:
                    pass
    except OSError:
        log.exception("Autostart konnte nicht gesetzt werden")
    zustand = ist_an()
    log.info("Autostart %s", "an" if zustand else "aus")
    return zustand
