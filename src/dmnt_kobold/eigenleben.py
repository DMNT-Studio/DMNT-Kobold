"""Einfaches Eigenleben (Platzhalter). Wird in M2 durch Event-Bus und
Verhaltensmotor ersetzt.

Zustände: ruhe (2–6 s), laufen (2–8 s), sitzen (5–15 s, selten).
Blinzeln alle 3–7 s.
"""
from __future__ import annotations

import random

RUHE = "ruhe"
LAUFEN = "laufen"
SITZEN = "sitzen"

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
        self._nicht_stoeren = wert
        if wert:
            self.zustand = SITZEN
        else:
            self.zuruecksetzen()

    @property
    def augen_zu(self) -> bool:
        return self.zustand == SITZEN or self._blinzel_rest > 0

    def zuruecksetzen(self) -> None:
        self.zustand = SITZEN if self._nicht_stoeren else RUHE
        self.rest = self.rng.uniform(2, 6)

    def tick(self, dt: float) -> None:
        self._blinzel_in -= dt
        if self._blinzel_in <= 0:
            self._blinzel_rest = BLINZEL_DAUER
            self._blinzel_in = self.rng.uniform(3, 7)
        elif self._blinzel_rest > 0:
            self._blinzel_rest = max(0.0, self._blinzel_rest - dt)

        if self._nicht_stoeren:
            self.zustand = SITZEN
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

    def naechster_wechsel_in(self) -> float:
        """Sekunden bis zum nächsten sichtbaren Ereignis (für den Ruhetakt)."""
        return min(self.rest, self._blinzel_in, self._blinzel_rest or 99.0)
