"""Reine Physik des Avatars: Schwerkraft, Boden, Laufen, Monitorkanten.

Keine Qt-Abhaengigkeit. Koordinaten sind logische Pixel, (x, y) ist der
Fusspunkt (Mitte unten) des Avatars.
"""
from __future__ import annotations

import math

from .monitore import (
    TOLERANZ,
    Monitor,
    auf_irgendeinem,
    boden_unter,
    hauptmonitor,
    monitor_bei,
    monitor_unter_fuss,
    nachbar,
    virtuelle_grenzen,
    x_abgedeckt,
)

SCHWERKRAFT = 2500.0      # px/s²
MAX_FALL = 1800.0         # px/s
LAUFTEMPO = 60.0          # px/s
MAX_WURF = 2200.0         # px/s, Deckel für Wurfgeschwindigkeit
HUEPFER = -520.0          # px/s, Anfangsgeschwindigkeit Hüpfer
ABPRALL = 0.5             # Anteil der Geschwindigkeit nach Abprall
RETTUNG_UNTER = 400.0     # px unter dem virtuellen Desktop → Rettung

# Zustände
STEHT = "steht"
FAELLT = "faellt"
GEZOGEN = "gezogen"

# Ereignisse aus schritt()
GELANDET = "gelandet"
GEDREHT = "gedreht"
GEWECHSELT = "monitor_gewechselt"
GERETTET = "gerettet"


class Koerper:
    def __init__(self, x: float = 0.0, y: float = 0.0, halbe_breite: float = 40.0, hoehe: float = 92.0):
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.zustand = STEHT
        self.richtung = 1
        self.halbe_breite = halbe_breite
        self.hoehe = hoehe
        self.tempo = LAUFTEMPO
        self.hupf_flug = False                     # gerade in der Luft wegen eines Hüpfers
        self.landung: tuple[str, float] = ("fall", 0.0)   # (hupf | fall, Fallhöhe) der letzten Landung
        self._start_y: float | None = None         # Boden beim Absprung
        self._oben_y: float | None = None          # höchster Punkt im Fall/Flug

    # --- Nutzer-Eingriff ---------------------------------------------------
    @property
    def in_bewegung(self) -> bool:
        return self.zustand in (FAELLT, GEZOGEN)

    def greifen(self) -> None:
        self.zustand = GEZOGEN
        self.vx = self.vy = 0.0
        self._flug_ende()

    def ziehen_nach(self, x: float, y: float) -> None:
        self.x, self.y = x, y

    def loslassen(self, vx: float, vy: float) -> None:
        betrag = math.hypot(vx, vy)
        if betrag > MAX_WURF:
            vx, vy = vx / betrag * MAX_WURF, vy / betrag * MAX_WURF
        self.vx, self.vy = vx, vy
        self.zustand = FAELLT

    def huepfen(self) -> None:
        if self.zustand == STEHT:
            self.vy = HUEPFER
            self.vx = 0.0
            self.zustand = FAELLT

    # --- Hüpfen (Bewegungsart „huepfen“) ----------------------------------------
    def hupf_weite(self, weite: float, monitore: list[Monitor], auf_monitor_bleiben: bool = False) -> tuple[float, list[str]]:
        """Weite des nächsten Hüpfers in Blickrichtung. Stößt er an eine Kante ohne
        Nachbarn (oder soll auf dem Monitor bleiben), dreht er um; passt der Hüpfer
        auch so nicht, wird er kürzer. → (Weite, Ereignisse)"""
        m = monitor_unter_fuss(monitore, self.x, self.y)
        if m is None or weite <= 0:
            return max(0.0, weite), []
        boden_nativ = m.nach_nativ_y(m.boden)
        ereignisse: list[str] = []

        def frei(r: int) -> float:
            """So weit geht es in Richtung r (unbegrenzt, wenn dort ein Nachbar ist)."""
            if not auf_monitor_bleiben and nachbar(monitore, m, r, boden_nativ) is not None:
                return math.inf
            if r > 0:
                return m.verfuegbar.rechts - self.halbe_breite - self.x
            return self.x - (m.verfuegbar.links + self.halbe_breite)

        if frei(self.richtung) < weite:
            if frei(-self.richtung) > frei(self.richtung):
                self.richtung = -self.richtung
                ereignisse.append(GEDREHT)
            weite = max(0.0, min(weite, frei(self.richtung)))
        return weite, ereignisse

    def hupf_ab(self, weite: float, hoehe: float) -> None:
        """Absprung: echte Parabel mit der Schwerkraft. Startgeschwindigkeit aus
        Weite und Höhe; die Landung übernimmt das Fallen (exakt auf dem Boden)."""
        if self.zustand != STEHT:
            return
        hoehe = max(1.0, hoehe)
        self.vy = -math.sqrt(2 * SCHWERKRAFT * hoehe)
        flugzeit = 2 * -self.vy / SCHWERKRAFT
        self.vx = self.richtung * max(0.0, weite) / flugzeit
        self.zustand = FAELLT
        self.hupf_flug = True
        self._start_y = self.y

    @staticmethod
    def flugzeit(hoehe: float) -> float:
        return 2 * math.sqrt(2 * max(1.0, hoehe) / SCHWERKRAFT)

    def retten(self, monitore: list[Monitor]) -> None:
        m = hauptmonitor(monitore)
        self.x = m.verfuegbar.links + m.verfuegbar.w / 2
        self.y = m.boden
        self.vx = self.vy = 0.0
        self.zustand = STEHT
        self._flug_ende()

    def pruefe_monitore(self, monitore: list[Monitor]) -> bool:
        """Nach Monitor-Änderung: außerhalb aller Monitore → Hauptmonitor.
        Gibt True zurück, wenn gerettet wurde."""
        if self.zustand == GEZOGEN:
            return False
        if not auf_irgendeinem(monitore, self.x, self.y):
            self.retten(monitore)
            return True
        return False

    def _im_bild(self, monitore: list[Monitor], x: float, y: float) -> bool:
        """Liegt die Körpermitte (halbe Höhe über dem Fuss) auf einem Monitor?"""
        py = y - self.hoehe / 2
        return any(m.geometrie.enthaelt(x, py) for m in monitore)

    # --- Takt --------------------------------------------------------------
    def schritt(self, dt: float, monitore: list[Monitor], laufen: bool = False,
                auf_monitor_bleiben: bool = False) -> list[str]:
        if not monitore or self.zustand == GEZOGEN:
            return []
        if self.zustand == FAELLT:
            return self._fallen(dt, monitore)
        return self._stehen(dt, monitore, laufen, auf_monitor_bleiben)

    def _fallen(self, dt: float, monitore: list[Monitor]) -> list[str]:
        grenzen = virtuelle_grenzen(monitore)
        y_alt = self.y
        self._oben_y = y_alt if self._oben_y is None else min(self._oben_y, y_alt)
        self.vy = min(self.vy + SCHWERKRAFT * dt, MAX_FALL)

        x_neu = self.x + self.vx * dt
        y_neu = self.y + self.vy * dt

        # Seitenwände: Rand des sichtbaren Bereichs (Vereinigung aller Monitore)
        if self.vx != 0.0:
            vorne = x_neu + math.copysign(self.halbe_breite, self.vx)
            wand = not x_abgedeckt(monitore, vorne) or not x_abgedeckt(monitore, x_neu)
            if not wand and self._im_bild(monitore, self.x, self.y):
                wand = not self._im_bild(monitore, vorne, self.y)
            if wand:
                self.vx = -self.vx * ABPRALL
                x_neu = self.x
        # Decke: nach oben aus dem sichtbaren Bereich → anhalten
        if self.vy < 0 and self._im_bild(monitore, self.x, self.y) \
                and not self._im_bild(monitore, x_neu, y_neu):
            self.vy = 0.0
            y_neu = self.y
        self.x, self.y = x_neu, y_neu

        decke = grenzen.oben + self.hoehe
        if self.y < decke:
            self.y = decke
            self.vy = max(self.vy, 0.0)

        boden = boden_unter(monitore, self.x, y_alt)
        if boden is not None and self.y >= boden:
            self.y = boden
            self.vx = self.vy = 0.0
            self.zustand = STEHT
            gleich = self._start_y is not None and abs(boden - self._start_y) <= TOLERANZ + 1
            self.landung = ("hupf" if self.hupf_flug and gleich else "fall",
                            round(max(0.0, boden - min(self._oben_y, y_alt)), 1))
            self._flug_ende()
            return [GELANDET]
        if self.y > grenzen.unten + RETTUNG_UNTER:
            self.retten(monitore)
            return [GERETTET]
        return []

    def _flug_ende(self) -> None:
        self.hupf_flug = False
        self._start_y = self._oben_y = None

    def _stehen(self, dt: float, monitore: list[Monitor], laufen: bool,
                auf_monitor_bleiben: bool) -> list[str]:
        m = monitor_unter_fuss(monitore, self.x, self.y)
        if m is None:
            # Boden hat sich verschoben (Taskleiste, Auflösung).
            b = monitor_bei(monitore, self.x, self.y - 1)
            if b is not None and b.deckt_x(self.x) and self.y > b.boden:
                self.y = b.boden  # Boden ist hochgewandert → hochsetzen
                return []
            self.zustand = FAELLT
            self.vx = self.vy = 0.0
            return []

        self.y = m.boden
        if not laufen:
            return []

        ereignisse: list[str] = []
        r = self.richtung
        self.x += r * self.tempo * dt
        kante = m.verfuegbar.rechts if r > 0 else m.verfuegbar.links
        boden_nativ = m.nach_nativ_y(m.boden)
        n = None if auf_monitor_bleiben else nachbar(monitore, m, r, boden_nativ)

        if n is None:
            if r > 0 and self.x + self.halbe_breite > kante:
                self.x = kante - self.halbe_breite
                self.richtung = -1
                ereignisse.append(GEDREHT)
            elif r < 0 and self.x - self.halbe_breite < kante:
                self.x = kante + self.halbe_breite
                self.richtung = 1
                ereignisse.append(GEDREHT)
            return ereignisse

        ueber = (self.x - kante) if r > 0 else (kante - self.x)
        if ueber < 0:
            return ereignisse  # Mitte noch nicht über der Kante

        n_kante = n.verfuegbar.links if r > 0 else n.verfuegbar.rechts
        self.x = n_kante + r * max(ueber, 0.5)
        y_neu = n.von_nativ_y(boden_nativ)
        if abs(n.boden - y_neu) <= TOLERANZ:
            self.y = n.boden
            ereignisse.append(GEWECHSELT)
        else:
            # Nachbar-Boden liegt tiefer → herunterfallen
            self.y = y_neu
            self.vx = r * self.tempo
            self.vy = 0.0
            self.zustand = FAELLT
            ereignisse.append(GEWECHSELT)
        return ereignisse
