"""Eigenleben: was der Avatar tut, wenn niemand etwas will (Priorität 0–20).
Wird vom Verhaltensmotor getickt und nur genutzt, solange kein Wunsch aktiv ist.

Zustände: ruhe (2–6 s), laufen (2–8 s), sitzen (5–15 s, selten),
schlafen (nur bei „Nicht stören“). Blinzeln alle 3–7 s.
"""
from __future__ import annotations

import random

RUHE = "ruhe"
LAUFEN = "laufen"
SITZEN = "sitzen"
SCHLAFEN = "schlafen"

BLINZEL_DAUER = 0.14


class Eigenleben:
    def __init__(self, rng: random.Random | None = None):
        self.rng = rng or random.Random()
        self.zustand = RUHE
        self.rest = self.rng.uniform(2, 6)
        self.richtung = 1
        self._nicht_stoeren = False
        self._blinzel_in = self.rng.uniform(3, 7)
        self._blinzel_rest = 0.0

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
        self.rest = self.rng.uniform(2, 6)

    def tick(self, dt: float) -> None:
        self._blinzel_in -= dt
        if self._blinzel_in <= 0:
            self._blinzel_rest = BLINZEL_DAUER
            self._blinzel_in = self.rng.uniform(3, 7)
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
            self.zustand, self.rest = RUHE, self.rng.uniform(2, 6)
            return
        r = self.rng.random()
        if r < 0.12:
            self.zustand, self.rest = SITZEN, self.rng.uniform(5, 15)
        elif r < 0.75:
            self.zustand, self.rest = LAUFEN, self.rng.uniform(2, 8)
            self.richtung = self.rng.choice((-1, 1))
        else:
            self.rest = self.rng.uniform(2, 6)
