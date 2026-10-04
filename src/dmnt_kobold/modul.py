"""Basisklasse für Module („Tricks") und Persönlichkeiten.

Ein Modul hört Ereignisse (``on_event``) und äußert Wünsche (``wunsch``).
Es greift nie direkt in Animation oder Fenster ein. Wirft ein Modul einen
Fehler, wird es deaktiviert und seine Wünsche verschwinden – der Avatar
läuft weiter.
"""
from __future__ import annotations

import logging

from .bus import Ereignis, EventBus
from .motor import Verhaltensmotor

log = logging.getLogger(__name__)


class Modul:
    name = "modul"
    anzeigename = "Modul"

    def __init__(self, bus: EventBus, motor: Verhaltensmotor) -> None:
        self.bus = bus
        self.motor = motor
        self.aktiv = True
        bus.abonnieren("*", self._empfangen, self)

    # --- für Modulautoren --------------------------------------------------
    def on_event(self, ereignis: Ereignis) -> None:
        """Wird für jedes Ereignis aufgerufen. Überschreiben."""

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

    # --- intern ------------------------------------------------------------
    def _empfangen(self, e: Ereignis) -> None:
        if self.aktiv:
            self.on_event(e)

    def bei_fehler(self) -> None:
        self.aktiv = False
        self.motor.zurueckziehen_quelle(self.name)
        self.bus.abbestellen(self)
        log.warning("Modul %s nach Fehler deaktiviert", self.name)
