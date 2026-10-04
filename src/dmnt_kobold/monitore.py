"""Monitor-Geometrie als einfache Rechtecke.

Alles hier ausser ``lese_monitore()`` ist reine Logik ohne Qt und damit testbar.

Hinweis zu gemischter Skalierung: Qt 6 behaelt bei jedem Bildschirm die linke
obere Ecke in nativen Pixeln und skaliert nur die Groesse. Bei 100 % + 150 %
entstehen dadurch logische Luecken oder Ueberlappungen zwischen Monitoren.
Deshalb werden Nachbarschaft und Bodenhoehe ueber nativen Koordinaten
verglichen (``nach_nativ_*`` / ``von_nativ_*``).
"""
from __future__ import annotations

from dataclasses import dataclass

TOLERANZ = 2.0


@dataclass(frozen=True)
class Rechteck:
    x: float
    y: float
    w: float
    h: float

    @property
    def links(self) -> float:
        return self.x

    @property
    def rechts(self) -> float:  # exklusiv
        return self.x + self.w

    @property
    def oben(self) -> float:
        return self.y

    @property
    def unten(self) -> float:  # exklusiv
        return self.y + self.h

    def enthaelt(self, px: float, py: float) -> bool:
        return self.links <= px < self.rechts and self.oben <= py < self.unten


@dataclass(frozen=True)
class Monitor:
    name: str
    geometrie: Rechteck
    verfuegbar: Rechteck
    dpr: float = 1.0
    haupt: bool = False

    # --- native Koordinaten (Qt 6: linke obere Ecke ist nativ) ---
    def nach_nativ_x(self, x: float) -> float:
        return self.geometrie.x + (x - self.geometrie.x) * self.dpr

    def nach_nativ_y(self, y: float) -> float:
        return self.geometrie.y + (y - self.geometrie.y) * self.dpr

    def von_nativ_y(self, y: float) -> float:
        return self.geometrie.y + (y - self.geometrie.y) / self.dpr

    @property
    def boden(self) -> float:
        return self.verfuegbar.unten

    def deckt_x(self, x: float) -> bool:
        return self.verfuegbar.links <= x < self.verfuegbar.rechts


def hauptmonitor(monitore: list[Monitor]) -> Monitor:
    for m in monitore:
        if m.haupt:
            return m
    return monitore[0]


def monitor_unter_fuss(monitore: list[Monitor], x: float, y: float) -> Monitor | None:
    """Monitor, auf dessen Boden der Fusspunkt gerade steht."""
    for m in monitore:
        if m.deckt_x(x) and abs(y - m.boden) <= TOLERANZ:
            return m
    return None


def monitor_bei(monitore: list[Monitor], x: float, y: float) -> Monitor | None:
    """Monitor, dessen Flaeche den Punkt enthaelt (ganzer Bildschirm)."""
    for m in monitore:
        if m.geometrie.enthaelt(x, y):
            return m
    return None


def boden_unter(monitore: list[Monitor], x: float, y: float) -> float | None:
    """Naechster Boden auf oder unter y bei Position x. None = nichts darunter.

    Steckt der Punkt in der Taskleiste (unter dem Boden, aber noch im
    Bildschirm), zaehlt der Boden dieses Monitors: der Avatar wird hochgesetzt.
    """
    kandidaten: list[float] = []
    for m in monitore:
        if not m.deckt_x(x):
            continue
        if m.boden >= y - TOLERANZ:
            kandidaten.append(m.boden)
        elif m.geometrie.oben <= y <= m.geometrie.unten + TOLERANZ:
            return m.boden
    return min(kandidaten) if kandidaten else None


def x_abgedeckt(monitore: list[Monitor], x: float) -> bool:
    return any(m.deckt_x(x) for m in monitore)


def auf_irgendeinem(monitore: list[Monitor], x: float, y: float) -> bool:
    """Liegt der Fusspunkt auf einem Monitor? (y-1, weil der Boden exklusiv ist)"""
    return any(m.geometrie.enthaelt(x, y - 1) for m in monitore)


def nachbar(monitore: list[Monitor], m: Monitor, seite: int, boden_nativ: float) -> Monitor | None:
    """Buendiger Nachbar auf Seite +1 (rechts) / -1 (links), der in Bodenhoehe
    begehbar ist (seine Flaeche reicht bis zur aktuellen Bodenhoehe herauf)."""
    kante = m.nach_nativ_x(m.verfuegbar.rechts if seite > 0 else m.verfuegbar.links)
    for n in monitore:
        if n is m:
            continue
        n_kante = n.nach_nativ_x(n.verfuegbar.links if seite > 0 else n.verfuegbar.rechts)
        tol = TOLERANZ * max(m.dpr, n.dpr)
        if abs(n_kante - kante) > tol:
            continue
        n_oben = n.nach_nativ_y(n.verfuegbar.oben)
        n_unten = n.nach_nativ_y(n.verfuegbar.unten)
        if n_oben < boden_nativ <= n_unten + tol:
            return n
    return None


def virtuelle_grenzen(monitore: list[Monitor]) -> Rechteck:
    links = min(m.geometrie.links for m in monitore)
    oben = min(m.geometrie.oben for m in monitore)
    rechts = max(m.geometrie.rechts for m in monitore)
    unten = max(m.geometrie.unten for m in monitore)
    return Rechteck(links, oben, rechts - links, unten - oben)


def lese_monitore() -> list[Monitor]:
    """Liest die aktuellen Bildschirme aus Qt (logische Koordinaten)."""
    from PySide6.QtGui import QGuiApplication

    primaer = QGuiApplication.primaryScreen()
    ergebnis: list[Monitor] = []
    for s in QGuiApplication.screens():
        g = s.geometry()
        a = s.availableGeometry()
        ergebnis.append(
            Monitor(
                name=s.name(),
                geometrie=Rechteck(g.x(), g.y(), g.width(), g.height()),
                verfuegbar=Rechteck(a.x(), a.y(), a.width(), a.height()),
                dpr=s.devicePixelRatio(),
                haupt=(s is primaer or s == primaer),
            )
        )
    return ergebnis
