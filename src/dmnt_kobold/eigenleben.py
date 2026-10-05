"""Eigenleben: was der Avatar tut, wenn niemand etwas will (Priorität 0–20).
Wird vom Verhaltensmotor getickt und nur genutzt, solange kein Wunsch aktiv ist.

Zustände: ruhe, laufen, sitzen (selten), schlafen (nur bei „Nicht stören“), dazu
Blinzeln. Dauern und Wahrscheinlichkeiten kommen aus dem Katalog (Bereich
„Eigenleben“) und können je Avatar abweichen.
"""
from __future__ import annotations

import random

from . import katalog

RUHE = "ruhe"
LAUFEN = "laufen"
SITZEN = "sitzen"
SCHLAFEN = "schlafen"

BLINZEL_DAUER = 0.14


class Eigenleben:
    def __init__(self, rng: random.Random | None = None, werte: katalog.Werte | None = None):
        self.rng = rng or random.Random()
        self.werte = werte or katalog.Werte()
        self.zustand = RUHE
        self.rest = self._dauer("ruhe")
        self.richtung = 1
        self._nicht_stoeren = False
        self._blinzel_in = self._dauer("blinzeln")
        self._blinzel_rest = 0.0

    def _dauer(self, art: str) -> float:
        return self.rng.uniform(self.werte[f"{art}_min_s"], self.werte[f"{art}_max_s"])

    @property
    def nicht_stoeren(self) -> bool:
        return self._nicht_stoeren

    @nicht_stoeren.setter
    def nicht_stoeren(self, wert: bool) -> None:
        if wert == self._nicht_stoeren:
            return
        self._nicht_stoeren = wert
        if wert:
            self.zustand = SCHLAFEN
        else:
            self.zuruecksetzen()

    @property
    def blinzelt(self) -> bool:
        return self._blinzel_rest > 0

    def zuruecksetzen(self) -> None:
        self.zustand = SCHLAFEN if self._nicht_stoeren else RUHE
        self.rest = self._dauer("ruhe")

    def tick(self, dt: float) -> None:
        self._blinzel_in -= dt
        if self._blinzel_in <= 0:
            self._blinzel_rest = BLINZEL_DAUER
            self._blinzel_in = self._dauer("blinzeln")
        elif self._blinzel_rest > 0:
            self._blinzel_rest = max(0.0, self._blinzel_rest - dt)

        if self._nicht_stoeren:
            self.zustand = SCHLAFEN
            return
        self.rest -= dt
        if self.rest <= 0:
            self._naechster()

    def _naechster(self) -> None:
        if self.zustand != RUHE:
            self.zustand, self.rest = RUHE, self._dauer("ruhe")
            return
        r = self.rng.random()
        sitzen = self.werte["chance_sitzen"]
        if r < sitzen:
            self.zustand, self.rest = SITZEN, self._dauer("sitzen")
        elif r < sitzen + self.werte["chance_laufen"]:
            self.zustand, self.rest = LAUFEN, self._dauer("laufen")
            self.richtung = self.rng.choice((-1, 1))
        else:
            self.rest = self._dauer("ruhe")
