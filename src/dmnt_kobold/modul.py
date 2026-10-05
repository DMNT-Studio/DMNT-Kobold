"""Basisklasse für Module („Tricks") und Persönlichkeiten.

Ein Modul hört Ereignisse (``on_event``) und äußert Wünsche (``wunsch``).
Es greift nie direkt in Animation oder Fenster ein. Wirft ein Modul einen
Fehler, wird es deaktiviert und seine Wünsche verschwinden – der Avatar
läuft weiter.

Für Modulautoren stehen bereit:
  on_event(e)         jedes Ereignis vom Bus (e.name, e.daten)
  jede_sekunde()      Takt einmal pro Sekunde
  wunsch(...)         Wunsch an den Verhaltensmotor (siehe motor.Wunsch)
  zurueckziehen(...)  Wünsche zurücknehmen
  zubehoer(name, an)  Zubehör an/aus (z. B. "kopfhoerer")
  self.speicher       dict, das sich bei jeder Änderung sofort sicher speichert
  hotkey(kombi, f)    globales Tastenkürzel, z. B. "Strg+Alt+E" (ohne Tastatur-Hook)
  menue_eintraege()   Einträge fürs Tray-Menü: [(Text, Funktion), ...]
  beenden()           wird beim Abschalten aufgerufen
"""
from __future__ import annotations

import logging
from typing import Callable

from .bus import Ereignis, EventBus
from .motor import Verhaltensmotor

log = logging.getLogger(__name__)


class Modul:
    name = "modul"
    anzeigename = "Modul"
    beschreibung = ""

    def __init__(self, bus: EventBus, motor: Verhaltensmotor, umgebung=None) -> None:
        self.bus = bus
        self.motor = motor
        self.umgebung = umgebung
        self.aktiv = True
        self._hotkeys: list[int] = []
        if umgebung is not None:
            self.speicher = umgebung.speicher(self.name)
        else:
            self.speicher = {}          # Tests / ohne Datenablage: nur im Speicher
        bus.abonnieren("*", self._empfangen, self)

    # --- für Modulautoren --------------------------------------------------
    def on_event(self, ereignis: Ereignis) -> None:
        """Wird für jedes Ereignis aufgerufen. Überschreiben."""

    def jede_sekunde(self) -> None:
        """Takt einmal pro Sekunde. Überschreiben."""

    def menue_eintraege(self) -> list[tuple[str, Callable[[], None]]]:
        return []

    def beenden(self) -> None:
        """Aufräumen beim Abschalten. Überschreiben, super() aufrufen."""

    def wunsch(self, unter: str = "", **kw) -> int:
        """Wunsch an den Verhaltensmotor. ``unter`` gruppiert Wünsche, die
        später gemeinsam zurückgezogen werden (``zurueckziehen(unter=...)``)."""
        kw["quelle"] = f"{self.name}:{unter}" if unter else self.name
        return self.motor.wunsch(**kw)

    def zurueckziehen(self, wunsch_id: int | None = None, *, unter: str = "") -> None:
        if wunsch_id is not None:
            self.motor.zurueckziehen(wunsch_id)
        else:
            self.motor.zurueckziehen_quelle(f"{self.name}:{unter}" if unter else self.name)

    def zubehoer(self, name: str, an: bool = True) -> None:
        """Zubehör an/aus (z. B. "kopfhoerer"). Bleibt, bis das Modul es abnimmt."""
        self.motor.zubehoer_setzen(name, an, self.name)

    def hotkey(self, kombination: str, rueckruf: Callable[[], None]) -> bool:
        """Globales Tastenkürzel (RegisterHotKey, kein Tastatur-Hook).
        Liefert False, wenn es schon ein anderes Programm belegt."""
        hk = getattr(self.umgebung, "hotkeys", None)
        if hk is None:
            return False
        kennung = hk.registrieren(kombination, self._sicher(rueckruf), self.name)
        if kennung is None:
            return False
        self._hotkeys.append(kennung)
        return True

    # --- intern ------------------------------------------------------------
    def _sicher(self, f: Callable[[], None]) -> Callable[[], None]:
        def aufruf() -> None:
            if not self.aktiv:
                return
            try:
                f()
            except Exception:  # noqa: BLE001
                log.exception("Fehler in Modul %s", self.name)
                self.bei_fehler()
        return aufruf

    def _empfangen(self, e: Ereignis) -> None:
        if self.aktiv:
            self.on_event(e)

    def _takt(self) -> None:
        if self.aktiv:
            self._sicher(self.jede_sekunde)()

    def abschalten(self) -> None:
        """Vom Sockel aufgerufen: Modul sauber abmelden."""
        if not self.aktiv:
            return
        self.aktiv = False
        try:
            self.beenden()
        except Exception:  # noqa: BLE001
            log.exception("beenden() von %s fehlgeschlagen", self.name)
        self._abmelden()

    def _abmelden(self) -> None:
        self.motor.zurueckziehen_quelle(self.name)
        self.bus.abbestellen(self)
        hk = getattr(self.umgebung, "hotkeys", None)
        if hk is not None:
            for k in self._hotkeys:
                hk.freigeben(k)
        self._hotkeys.clear()

    def bei_fehler(self) -> None:
        self.aktiv = False
        self._abmelden()
        log.warning("Modul %s nach Fehler deaktiviert", self.name)
        melden = getattr(self.umgebung, "modul_fehler", None)
        if callable(melden):
            melden(self)
