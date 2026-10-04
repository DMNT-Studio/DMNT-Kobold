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

    # --- Nutzer-Eingriff ---------------------------------------------------
    @property
    def in_bewegung(self) -> bool:
        return self.zustand in (FAELLT, GEZOGEN)

    def greifen(self) -> None:
        self.zustand = GEZOGEN
        self.vx = self.vy = 0.0

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

    def retten(self, monitore: list[Monitor]) -> None:
        m = hauptmonitor(monitore)
        self.x = m.verfuegbar.links + m.verfuegbar.w / 2
        self.y = m.boden
        self.vx = self.vy = 0.0
        self.zustand = STEHT

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
            return [GELANDET]
        if self.y > grenzen.unten + RETTUNG_UNTER:
            self.retten(monitore)
            return [GERETTET]
        return []

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
        self.x += r * LAUFTEMPO * dt
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
            self.vx = r * LAUFTEMPO
            self.vy = 0.0
            self.zustand = FAELLT
            ereignisse.append(GEWECHSELT)
        return ereignisse
