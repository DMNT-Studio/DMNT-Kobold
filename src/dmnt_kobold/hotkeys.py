"""Globale Tastenkürzel per RegisterHotKey – Windows meldet nur „Kürzel X
gedrückt“ (WM_HOTKEY). Kein Tastatur-Hook, keine anderen Tasten.

Kombinationen als Text: "Strg+Alt+E", "Strg+Umschalt+F9", "Win+K".
Jede Auslösung geht zusätzlich als ``hotkey.<modul>`` auf den Bus.
"""
from __future__ import annotations

import ctypes
import logging
import sys
from typing import Callable

log = logging.getLogger(__name__)

WM_HOTKEY = 0x0312
MOD = {"alt": 0x1, "strg": 0x2, "ctrl": 0x2, "umschalt": 0x4, "shift": 0x4, "win": 0x8}
MOD_NOREPEAT = 0x4000
SONDERTASTEN = {
    "leer": 0x20, "space": 0x20, "eingabe": 0x0D, "enter": 0x0D, "pos1": 0x24, "ende": 0x23,
    "einfg": 0x2D, "entf": 0x2E, "bildauf": 0x21, "bildab": 0x22, "pause": 0x13,
}


def zerlegen(kombination: str) -> tuple[int, int]:
    """'Strg+Alt+E' → (Modifier-Bits, virtueller Tastencode). ValueError bei Unsinn."""
    teile = [t.strip().lower() for t in kombination.split("+") if t.strip()]
    if not teile:
        raise ValueError("leere Kombination")
    mods = 0
    for t in teile[:-1]:
        if t not in MOD:
            raise ValueError(f"unbekannte Zusatztaste: {t}")
        mods |= MOD[t]
    taste = teile[-1]
    if len(taste) == 1 and (taste.isascii() and taste.isalnum()):
        vk = ord(taste.upper())
    elif taste.startswith("f") and taste[1:].isdigit() and 1 <= int(taste[1:]) <= 24:
        vk = 0x70 + int(taste[1:]) - 1
    elif taste in SONDERTASTEN:
        vk = SONDERTASTEN[taste]
    else:
        raise ValueError(f"unbekannte Taste: {taste}")
    if mods == 0 and not (0x70 <= vk <= 0x87):
        raise ValueError("ohne Zusatztaste nur F-Tasten erlaubt")
    return mods, vk


class Hotkeys:
    """Verwaltet registrierte Kürzel. Unter Windows hängt sich ein
    Native-Event-Filter in Qt und fängt WM_HOTKEY ab."""

    def __init__(self, bus=None) -> None:
        self.bus = bus
        self._naechste = 0xB000
        self._eintraege: dict[int, tuple[str, Callable[[], None], str]] = {}
        self._filter = None
        if sys.platform == "win32":
            self._user32 = ctypes.windll.user32
            self._filter_installieren()

    def _filter_installieren(self) -> None:
        from PySide6.QtCore import QAbstractNativeEventFilter, QCoreApplication
        from ctypes import wintypes

        aussen = self

        class _Filter(QAbstractNativeEventFilter):
            def nativeEventFilter(self, typ, nachricht):  # noqa: N802 (Qt-API)
                if typ == b"windows_generic_MSG" or typ == "windows_generic_MSG":
                    msg = wintypes.MSG.from_address(int(nachricht))
                    if msg.message == WM_HOTKEY:
                        aussen.ausloesen(int(msg.wParam))
                        return True, 0
                return False, 0

        self._filter = _Filter()
        QCoreApplication.instance().installNativeEventFilter(self._filter)

    def registrieren(self, kombination: str, rueckruf: Callable[[], None], quelle: str = "") -> int | None:
        try:
            mods, vk = zerlegen(kombination)
        except ValueError as fehler:
            log.warning("Kürzel %r ungültig: %s", kombination, fehler)
            return None
        kennung = self._naechste
        self._naechste += 1
        if sys.platform == "win32":
            if not self._user32.RegisterHotKey(None, kennung, mods | MOD_NOREPEAT, vk):
                log.warning("Kürzel %s ist schon belegt", kombination)
                return None
        self._eintraege[kennung] = (kombination, rueckruf, quelle)
        log.info("Kürzel %s für %s", kombination, quelle or "?")
        return kennung

    def freigeben(self, kennung: int) -> None:
        if self._eintraege.pop(kennung, None) is not None and sys.platform == "win32":
            self._user32.UnregisterHotKey(None, kennung)

    def alle_freigeben(self) -> None:
        for k in list(self._eintraege):
            self.freigeben(k)

    def belegt(self) -> list[tuple[str, str]]:
        return [(k, q) for k, _, q in self._eintraege.values()]

    def ausloesen(self, kennung: int) -> None:
        eintrag = self._eintraege.get(kennung)
        if eintrag is None:
            return
        _, rueckruf, quelle = eintrag
        if self.bus is not None:
            self.bus.senden(f"hotkey.{quelle or 'unbekannt'}")
        rueckruf()
