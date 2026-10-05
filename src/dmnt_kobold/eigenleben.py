"""Eigenleben: was der Avatar tut, wenn niemand etwas will (Priorität 0–20).
Wird vom Verhaltensmotor getickt und nur genutzt, solange kein Wunsch aktiv ist.

Zustände: ruhe, laufen, sitzen (selten), rennen („ihre 5 Minuten“: aus dem Nichts
losflitzen, Haken schlagen, springen), schlafen (nur bei „Nicht stören“), dazu
Blinzeln. Dauern und Wahrscheinlichkeiten kommen aus dem Katalog (Bereiche
„Eigenleben“ und „Rennen“) und können je Avatar abweichen.
"""
from __future__ import annotations

import random

from . import katalog

RUHE = "ruhe"
LAUFEN = "laufen"
SITZEN = "sitzen"
RENNEN = "rennen"
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
        self._haken_in = 0.0
        self._sprung = False

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
            self._sprung = False
        else:
            self.zuruecksetzen()

    @property
    def blinzelt(self) -> bool:
        return self._blinzel_rest > 0

    @property
    def rennt(self) -> bool:
        return self.zustand == RENNEN

    def sprung_holen(self) -> bool:
        """True genau einmal, wenn beim Flitzen ein Sprung fällig ist (das Overlay springt dann)."""
        faellig, self._sprung = self._sprung and self.zustand == RENNEN, False
        return faellig

    def zuruecksetzen(self) -> None:
        self.zustand = SCHLAFEN if self._nicht_stoeren else RUHE
        self.rest = self._dauer("ruhe")
        self._sprung = False

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
        if self.zustand == RENNEN:
            self._haken_in -= dt
            if self._haken_in <= 0:
                self._haken()
        self.rest -= dt
        if self.rest <= 0:
            self._naechster()

    def _haken_abstand(self) -> float:
        return self.werte["rennen_haken_s"] * self.rng.uniform(0.5, 1.5)

    def _haken(self) -> None:
        """Zickzack: umdrehen – oder an dieser Stelle hochspringen."""
        if self.rng.random() < self.werte["rennen_sprung_chance"]:
            self._sprung = True
        else:
            self.richtung = -self.richtung
        self._haken_in = self._haken_abstand()

    def _naechster(self) -> None:
        if self.zustand != RUHE:
            self.zustand, self.rest = RUHE, self._dauer("ruhe")
            self._sprung = False
            return
        r = self.rng.random()
        rennen = self.werte["chance_rennen"]
        if r < rennen:                                # „ihre 5 Minuten“
            self.zustand, self.rest = RENNEN, self._dauer("rennen")
            self.richtung = self.rng.choice((-1, 1))
            self._haken_in = self._haken_abstand()
            return
        r = (r - rennen) / (1 - rennen) if rennen < 1 else 1.0
        sitzen = self.werte["chance_sitzen"]
        if r < sitzen:
            self.zustand, self.rest = SITZEN, self._dauer("sitzen")
        elif r < sitzen + self.werte["chance_laufen"]:
            self.zustand, self.rest = LAUFEN, self._dauer("laufen")
            self.richtung = self.rng.choice((-1, 1))
        else:
            self.rest = self._dauer("ruhe")
