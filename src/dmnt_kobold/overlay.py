"""AvatarFenster: kleines, rahmenloses Overlay-Fenster in Avatar-Größe.

Das Fenster wandert mit dem Avatar. Transparente Bereiche sind durchklickbar:
Zusätzlich zur Transparenz wird eine Maske auf die Blob-Form gesetzt, damit
Klicks neben den Blob sicher im Fenster dahinter landen.
"""
from __future__ import annotations

import logging
import math
import os
import sys
import time
from collections import deque

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QWidget

from . import blob
from .eigenleben import LAUFEN, SITZEN, Eigenleben
from .menue import Schalter, baue_menue
from .monitore import Monitor, lese_monitore
from .physik import FAELLT, GEDREHT, GELANDET, GERETTET, GEZOGEN, STEHT, Koerper

log = logging.getLogger(__name__)

FENSTER_B = 150
FENSTER_H = 140
FUSS = QPointF(FENSTER_B / 2, FENSTER_H - 8)

TAKT_BEWEGT_MS = 16      # ~60 Hz
TAKT_RUHE_MS = 100       # 10 Hz
ZIEH_SCHWELLE = 5        # px
WURF_FENSTER_S = 0.08    # letzte 80 ms Mausbewegung
STAUCH_DAUER = 0.12
TOPMOST_ALLE_S = 2.0

MASKE_AKTIV = os.environ.get("DMNT_KOBOLD_OHNE_MASKE") != "1"


if sys.platform == "win32":
    import ctypes

    _user32 = ctypes.windll.user32
    _HWND_TOPMOST = ctypes.c_void_p(-1)
    _SWP = 0x0001 | 0x0002 | 0x0010 | 0x0200  # NOSIZE | NOMOVE | NOACTIVATE | NOOWNERZORDER

    def _ganz_nach_vorne(hwnd: int) -> None:
        _user32.SetWindowPos(ctypes.c_void_p(hwnd), _HWND_TOPMOST, 0, 0, 0, 0, _SWP)
else:
    def _ganz_nach_vorne(hwnd: int) -> None:
        pass


class AvatarFenster(QWidget):
    def __init__(self, schalter: Schalter, beim_beenden) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setFixedSize(FENSTER_B, FENSTER_H)
        self.setWindowTitle("DMNT-Kobold")

        self.schalter = schalter
        self.monitore: list[Monitor] = lese_monitore()
        self.koerper = Koerper(halbe_breite=blob.BREITE / 2 - 4, hoehe=blob.HOEHE)
        self.koerper.retten(self.monitore)
        self.eigenleben = Eigenleben()

        self.menue = baue_menue(schalter, beim_beenden, self)
        self.menue.aboutToHide.connect(self._menue_zu)
        self._menue_offen = False

        schalter.nicht_stoeren_geaendert.connect(self._nicht_stoeren)

        # Maus
        self._gedrueckt = False
        self._druck_pos = QPoint()
        self._griff = QPointF()
        self._spur: deque[tuple[float, float, float]] = deque(maxlen=64)

        # Darstellung
        self._stauch_t = -1.0
        self._lauf_phase = 0.0
        self._letzte_darstellung: tuple | None = None
        self._letzte_maske: tuple | None = None
        self._darst = (1.0, 1.0, 1, False, True)
        self._topmost_rest = 0.0

        self._uhr = QElapsedTimer()
        self._uhr.start()
        self._takt = QTimer(self)
        self._takt.setTimerType(Qt.TimerType.PreciseTimer)
        self._takt.timeout.connect(self._tick)
        self._takt.start(TAKT_RUHE_MS)

        self._platzieren()
        self._darstellung_aktualisieren(erzwingen=True)

    # --- öffentliche Steuerung ---------------------------------------------
    def zurueckholen(self) -> None:
        self.monitore = lese_monitore()
        self.koerper.retten(self.monitore)
        self.eigenleben.zuruecksetzen()
        self._platzieren()
        self.show()
        self._nach_vorne()
        log.info("Kobold zurückgeholt")

    def monitore_aktualisieren(self) -> None:
        self.monitore = lese_monitore()
        log.info("Monitore geändert: %s", [(m.name, m.geometrie, m.dpr) for m in self.monitore])
        if self.koerper.pruefe_monitore(self.monitore):
            log.info("Avatar außerhalb aller Monitore → Hauptmonitor")
            self.eigenleben.zuruecksetzen()
        self._platzieren()
        self._nach_vorne()

    # --- Takt ----------------------------------------------------------------
    def _tick(self) -> None:
        dt = min(self._uhr.restart() / 1000.0, 0.05)
        k = self.koerper

        if k.zustand == STEHT:
            self.eigenleben.tick(dt)
        laufen = (
            k.zustand == STEHT
            and self.eigenleben.zustand == LAUFEN
            and not self._gedrueckt
            and not self._menue_offen
            and not self.schalter.nicht_stoeren
        )
        k.richtung = self.eigenleben.richtung if laufen else k.richtung
        ereignisse = k.schritt(dt, self.monitore, laufen, self.schalter.monitor_bleiben)
        if GEDREHT in ereignisse:
            self.eigenleben.richtung = k.richtung
        if GELANDET in ereignisse:
            self._stauch_t = 0.0
            self.eigenleben.zuruecksetzen()
        if GERETTET in ereignisse:
            log.info("Avatar ins Nichts gefallen → Hauptmonitor")
            self.eigenleben.zuruecksetzen()

        if laufen:
            self._lauf_phase += dt
        if self._stauch_t >= 0:
            self._stauch_t += dt
            if self._stauch_t > STAUCH_DAUER:
                self._stauch_t = -1.0

        self._topmost_rest -= dt
        if self._topmost_rest <= 0:
            self._topmost_rest = TOPMOST_ALLE_S
            self._nach_vorne()

        self._platzieren()
        self._darstellung_aktualisieren()

        bewegt = laufen or k.in_bewegung or self._stauch_t >= 0 or self._gedrueckt
        soll = TAKT_BEWEGT_MS if bewegt else TAKT_RUHE_MS
        if self._takt.interval() != soll:
            self._takt.setInterval(soll)

    def _platzieren(self) -> None:
        x = round(self.koerper.x - FUSS.x())
        y = round(self.koerper.y - FUSS.y())
        if self.pos() != QPoint(x, y):
            self.move(x, y)

    def _nach_vorne(self) -> None:
        if self.isVisible():
            _ganz_nach_vorne(int(self.winId()))

    # --- Darstellung -------------------------------------------------------
    def _verformung(self) -> tuple[float, float]:
        k = self.koerper
        if k.zustand == GEZOGEN:
            return 0.93, 1.09
        if self._stauch_t >= 0:
            a = math.sin(math.pi * self._stauch_t / STAUCH_DAUER)
            return 1 + 0.14 * a, 1 - 0.16 * a
        if k.zustand == FAELLT:
            s = min(abs(k.vy) / 1800.0, 1.0) * 0.08
            return 1 - s * 0.6, 1 + s
        if self.eigenleben.zustand == SITZEN:
            return 1.06, 0.9
        if self.eigenleben.zustand == LAUFEN and not self.schalter.nicht_stoeren:
            w = math.sin(self._lauf_phase * 2 * math.pi * 2.2)
            return 1 - 0.015 * w, 1 + 0.03 * w
        return 1.0, 1.0

    def _darstellung_aktualisieren(self, erzwingen: bool = False) -> None:
        sx, sy = self._verformung()
        schatten = self.koerper.zustand == STEHT
        darst = (round(sx, 3), round(sy, 3), self.koerper.richtung,
                 self.eigenleben.augen_zu, schatten)
        if erzwingen or darst != self._letzte_darstellung:
            self._letzte_darstellung = darst
            self._darst = darst
            if MASKE_AKTIV:
                masken_schluessel = (round(sx, 2), round(sy, 2), darst[2], schatten)
                if erzwingen or masken_schluessel != self._letzte_maske:
                    self._letzte_maske = masken_schluessel
                    self.setMask(blob.maske(FUSS, sx, sy, darst[2], schatten))
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-API)
        sx, sy, richtung, augen_zu, schatten = self._darst
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        blob.zeichne(p, FUSS, sx, sy, richtung, augen_zu, schatten)
        p.end()

    # --- Maus ----------------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton:
            self._gedrueckt = True
            g = e.globalPosition()
            self._druck_pos = g.toPoint()
            self._griff = QPointF(g.x() - self.koerper.x, g.y() - self.koerper.y)
            self._spur.clear()
            self._spur.append((time.monotonic(), g.x(), g.y()))
        elif e.button() == Qt.MouseButton.RightButton:
            self._menue_offen = True
            self.menue.popup(e.globalPosition().toPoint())

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if not self._gedrueckt:
            return
        g = e.globalPosition()
        self._spur.append((time.monotonic(), g.x(), g.y()))
        k = self.koerper
        if k.zustand != GEZOGEN:
            if (g.toPoint() - self._druck_pos).manhattanLength() <= ZIEH_SCHWELLE:
                return
            k.greifen()
            self._stauch_t = -1.0
            self._takt.setInterval(TAKT_BEWEGT_MS)
        k.ziehen_nach(g.x() - self._griff.x(), g.y() - self._griff.y())
        self._platzieren()
        self._darstellung_aktualisieren()

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() != Qt.MouseButton.LeftButton or not self._gedrueckt:
            return
        self._gedrueckt = False
        k = self.koerper
        if k.zustand == GEZOGEN:
            vx, vy = self._wurfgeschwindigkeit()
            k.loslassen(vx, vy)
        else:
            k.huepfen()
        self._uhr.restart()
        self._takt.setInterval(TAKT_BEWEGT_MS)

    def _wurfgeschwindigkeit(self) -> tuple[float, float]:
        if len(self._spur) < 2:
            return 0.0, 0.0
        jetzt = time.monotonic()
        t1, x1, y1 = self._spur[-1]
        if jetzt - t1 > WURF_FENSTER_S:  # Maus stand vor dem Loslassen still
            return 0.0, 0.0
        t0, x0, y0 = t1, x1, y1
        for t, x, y in reversed(self._spur):
            if t1 - t > WURF_FENSTER_S:
                break
            t0, x0, y0 = t, x, y
        dauer = t1 - t0
        if dauer < 0.01:
            return 0.0, 0.0
        return (x1 - x0) / dauer, (y1 - y0) / dauer

    # --- Schalter / Menü -----------------------------------------------------
    def _nicht_stoeren(self, wert: bool) -> None:
        self.eigenleben.nicht_stoeren = wert
        self._darstellung_aktualisieren()

    def _menue_zu(self) -> None:
        self._menue_offen = False
