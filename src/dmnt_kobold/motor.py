"""Verhaltensmotor: sammelt Wünsche mit Priorität und entscheidet, was der
Avatar gerade tut. Module greifen nie direkt in die Animation ein.

Prioritäten (Richtwerte):
  100     Nutzer-Eingriff (Ziehen, Rechtsklick) – regelt das Overlay selbst
  70–90   wichtige Modul-Wünsche (Erinnerungen); kommen auch bei „Nicht stören“ durch
  30–60   Persönlichkeit, Reaktionen
  0–20    Eigenleben (läuft, wenn niemand etwas will)

Regeln:
- Es gewinnt die höchste Priorität. Bei Gleichstand bleibt der laufende Wunsch.
- Wird ein Wunsch verdrängt, verfällt er – außer ``aufheben=True``: dann
  wartet er und läuft später mit seiner Restzeit weiter.
- ``dauer_s=None`` heißt: bis zurückgezogen (z. B. „solange Programm X läuft“).
- Noch nicht begonnene Wünsche mit Dauer verfallen nach ``wunsch_verfaellt_s``
  (Katalog), damit keine veralteten Reaktionen nachgeholt werden.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Callable

from . import katalog
from .eigenleben import LAUFEN, SCHLAFEN, Eigenleben

log = logging.getLogger(__name__)

LEISE_AB = katalog.LEISE_AB     # „Nicht stören“ lässt nur Wünsche ab dieser Priorität durch
MAX_WARTEN_S = katalog.standard("wunsch_verfaellt_s")


@dataclass
class Wunsch:
    animation: str = "ruhe"
    text: str | None = None
    knoepfe: tuple[str, ...] = ()
    prioritaet: int = 50
    dauer_s: float | None = 5.0
    aufheben: bool = False
    ziel: str | float | None = None      # "rand_rechts", "rand_links", "mitte" oder x
    ton: str | None = None
    bewegung: str | None = None          # z. B. "freuen_huepfend" (Hüpfer auf der Stelle)
    innen: str | None = None             # Variante des Innenlebens, z. B. "froh"
    quelle: str = ""
    beim_knopf: Callable[[str], None] | None = None
    id: int = 0
    rest: float | None = None
    begonnen: bool = False
    gewartet: float = 0.0


@dataclass
class Ausgabe:
    animation: str
    laufen: bool
    richtung: int
    ziel: str | float | None
    sprechblase: tuple[int, str, tuple[str, ...]] | None
    toene: list[str] = field(default_factory=list)
    wunsch_id: int | None = None
    blinzelt: bool = False
    zubehoer: frozenset[str] = frozenset()
    bewegung: str | None = None
    innen: str | None = None


class Verhaltensmotor:
    def __init__(self, bus=None, eigenleben: Eigenleben | None = None) -> None:
        self.bus = bus
        self.eigenleben = eigenleben or Eigenleben()
        self.max_warten_s = self.eigenleben.werte["wunsch_verfaellt_s"]
        self._wuensche: list[Wunsch] = []
        self._aktiv: Wunsch | None = None
        self._naechste_id = 1
        self._nicht_stoeren = False
        self._toene: list[str] = []
        self._zubehoer: dict[str, set[str]] = {}   # Zubehör → Quellen, die es wollen

    # --- Zubehör (bleibt an, unabhängig von Wünschen) -------------------------
    def zubehoer_setzen(self, name: str, an: bool, quelle: str = "") -> None:
        """Mehrere Quellen können dasselbe Zubehör wollen; es bleibt an,
        solange mindestens eine es will."""
        quellen = self._zubehoer.setdefault(name, set())
        if an:
            quellen.add(quelle)
        else:
            quellen.discard(quelle)
            if not quellen:
                del self._zubehoer[name]

    @property
    def zubehoer(self) -> frozenset[str]:
        return frozenset(self._zubehoer)

    # --- Steuerung ---------------------------------------------------------
    @property
    def nicht_stoeren(self) -> bool:
        return self._nicht_stoeren

    @nicht_stoeren.setter
    def nicht_stoeren(self, wert: bool) -> None:
        self._nicht_stoeren = wert
        self.eigenleben.nicht_stoeren = wert
        self._waehlen()

    @property
    def aktiver_wunsch(self) -> Wunsch | None:
        return self._aktiv

    def wuensche(self) -> list[Wunsch]:
        return list(self._wuensche)

    @property
    def naechste_id(self) -> int:
        """Steigt mit jedem Wunsch – so sieht man, ob auf ein Ereignis jemand reagiert hat."""
        return self._naechste_id

    def wunsch(self, wunsch: Wunsch | None = None, **kw) -> int:
        w = wunsch or Wunsch(**kw)
        w.knoepfe = tuple(w.knoepfe)[:2]
        w.id = self._naechste_id
        self._naechste_id += 1
        w.rest = w.dauer_s
        self._wuensche.append(w)
        self._waehlen()
        return w.id

    def zurueckziehen(self, wunsch_id: int) -> None:
        self._wuensche = [w for w in self._wuensche if w.id != wunsch_id]
        self._nach_entfernen()

    def zurueckziehen_quelle(self, quelle: str) -> None:
        self._wuensche = [w for w in self._wuensche
                          if not (w.quelle == quelle or w.quelle.startswith(quelle + ":"))]
        for name in list(self._zubehoer):
            self._zubehoer[name] = {q for q in self._zubehoer[name]
                                    if not (q == quelle or q.startswith(quelle + ":"))}
            if not self._zubehoer[name]:
                del self._zubehoer[name]
        self._nach_entfernen()

    def knopf(self, wunsch_id: int, knopf: str) -> None:
        w = self._finden(wunsch_id)
        if w is None:
            return
        self.zurueckziehen(wunsch_id)
        if w.beim_knopf:
            try:
                w.beim_knopf(knopf)
            except Exception:  # noqa: BLE001
                log.exception("Knopf-Rückruf von %s fehlgeschlagen", w.quelle)
        if self.bus is not None:
            self.bus.senden("sprechblase.knopf", wunsch_id=wunsch_id, knopf=knopf, quelle=w.quelle)

    def sprechblase_geschlossen(self, wunsch_id: int) -> None:
        """Nutzer hat die Sprechblase weggeklickt."""
        w = self._finden(wunsch_id)
        if w is None:
            return
        self.zurueckziehen(wunsch_id)
        if self.bus is not None:
            self.bus.senden("sprechblase.zu", wunsch_id=wunsch_id, quelle=w.quelle)

    # --- Takt --------------------------------------------------------------
    def tick(self, dt: float) -> Ausgabe:
        self.eigenleben.tick(dt)

        for w in list(self._wuensche):
            if w is self._aktiv or w.begonnen or w.aufheben or w.dauer_s is None:
                continue
            w.gewartet += dt
            if w.gewartet > self.max_warten_s:
                self._wuensche.remove(w)

        w = self._aktiv
        if w is not None and w.rest is not None:
            w.rest -= dt
            if w.rest <= 0:
                self._wuensche.remove(w)
                self._aktiv = None
                self._waehlen()
                w = self._aktiv

        toene, self._toene = self._toene, []
        el = self.eigenleben
        if w is not None:
            blase = (w.id, w.text, w.knoepfe) if w.text else None
            return Ausgabe(w.animation, False, el.richtung, w.ziel, blase, toene, w.id, el.blinzelt,
                           self.zubehoer, w.bewegung, w.innen)
        anim = el.zustand
        return Ausgabe(anim, anim == LAUFEN, el.richtung, None, None, toene, None, el.blinzelt,
                       self.zubehoer)

    def verdraengt_eigenleben(self) -> bool:
        return self._aktiv is not None

    # --- intern ------------------------------------------------------------
    def _finden(self, wunsch_id: int) -> Wunsch | None:
        for w in self._wuensche:
            if w.id == wunsch_id:
                return w
        return None

    def _zulaessig(self, w: Wunsch) -> bool:
        return not self._nicht_stoeren or w.prioritaet >= LEISE_AB

    def _nach_entfernen(self) -> None:
        if self._aktiv is not None and self._aktiv not in self._wuensche:
            self._aktiv = None
        self._waehlen()

    def _waehlen(self) -> None:
        kandidaten = [w for w in self._wuensche if self._zulaessig(w)]
        bester = max(kandidaten, key=lambda w: (w.prioritaet, w is self._aktiv, w.id), default=None)
        if bester is self._aktiv:
            return
        alt = self._aktiv
        if alt is not None and alt in self._wuensche and not alt.aufheben and bester is not None:
            self._wuensche.remove(alt)  # verdrängt → verfällt
        self._aktiv = bester
        if bester is not None and not bester.begonnen:
            bester.begonnen = True
            if bester.ton:
                self._toene.append(bester.ton)
            elif bester.text:
                self._toene.append("sprechen")


__all__ = ["Ausgabe", "LEISE_AB", "SCHLAFEN", "Verhaltensmotor", "Wunsch"]
