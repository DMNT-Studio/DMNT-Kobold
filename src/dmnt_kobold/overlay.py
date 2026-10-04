"""AvatarFenster: kleines, rahmenloses Overlay-Fenster in Avatar-Größe.

Das Fenster wandert mit dem Avatar. Transparente Bereiche sind durchklickbar
(zusätzlich Fenstermaske auf die Blob-Form).

Ablauf pro Takt:
  Verhaltensmotor (Wünsche/Eigenleben) → Ausgabe → Physik → Darstellung,
  Sprechblase, Töne. Nutzer-Eingriff (Ziehen, Menü) hat immer Vorrang.
"""
from __future__ import annotations

import logging
import math
import os
import time
from collections import deque

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, Qt, QTimer
from PySide6.QtGui import QCursor, QPainter
from PySide6.QtWidgets import QWidget

from . import blob, win32
from .bus import EventBus
from .menue import Schalter, baue_menue
from .monitore import Monitor, lese_monitore, monitor_bei, monitor_unter_fuss
from .motor import Ausgabe, Verhaltensmotor
from .physik import FAELLT, GEDREHT, GELANDET, GERETTET, GEZOGEN, STEHT, Koerper
from .sprechblase import Sprechblase
from .toene import Toene

log = logging.getLogger(__name__)

FENSTER_B = 150
FENSTER_H = 140
FUSS = QPointF(FENSTER_B / 2, FENSTER_H - 8)
AUGEN_HOEHE = 53.0

TAKT_SCHNELL_MS = 16     # Fallen, Ziehen, Stauchen
TAKT_MITTEL_MS = 33      # Laufen, Anschauen, Ausdrücke
TAKT_RUHE_MS = 100       # nichts passiert
ZIEH_SCHWELLE = 5        # px
WURF_FENSTER_S = 0.08    # letzte 80 ms Mausbewegung
STAUCH_DAUER = 0.12
TOPMOST_ALLE_S = 2.0
LAUFTEMPO = 60.0
ZIELTEMPO = 140.0
ZIEL_RAND = 24.0

BEWEGTE_ANIMATIONEN = {"laufen", "anschauen", "freuen", "erschrecken", "sprechen", "gezogen", "fallen"}

MASKE_AKTIV = os.environ.get("DMNT_KOBOLD_OHNE_MASKE") != "1"


def ausdruck(animation: str, t: float, blinzelt: bool) -> tuple[float, float, str, str, bool]:
    """(sx, sy, augen, mund, zzz) für eine Animation zum Zeitpunkt t seit Beginn.
    Unbekannte Animationen fallen auf „ruhe“ zurück."""
    if animation == "laufen":
        w = math.sin(t * 2 * math.pi * 2.2)
        sx, sy, augen, mund, zzz = 1 - 0.015 * w, 1 + 0.03 * w, "offen", "laecheln", False
    elif animation == "sitzen":
        sx, sy, augen, mund, zzz = 1.06, 0.9, "offen", "laecheln", False
    elif animation == "schlafen":
        a = math.sin(t * 2 * math.pi * 0.4)
        sx, sy, augen, mund, zzz = 1.08 + 0.01 * a, 0.86 + 0.015 * a, "zu", "klein", True
    elif animation == "freuen":
        h = abs(math.sin(t * 2 * math.pi * 1.6))
        sx, sy, augen, mund, zzz = 1 + 0.05 * (1 - h), 0.95 + 0.08 * h, "froh", "offen", False
    elif animation == "erschrecken":
        k = max(0.0, 1 - t / 0.25)
        sx, sy, augen, mund, zzz = 0.95 - 0.04 * k, 1.05 + 0.08 * k, "gross", "o", False
    elif animation == "sprechen":
        offen = int(t * 7) % 2 == 0 and t < 1.6
        sx, sy, augen, mund, zzz = 1.0, 1.0, "offen", "offen" if offen else "laecheln", False
    elif animation == "gezogen":
        sx, sy, augen, mund, zzz = 0.93, 1.09, "gross", "o", False
    elif animation == "fallen":
        sx, sy, augen, mund, zzz = 0.96, 1.06, "gross", "o", False
    else:  # ruhe, anschauen und alles Unbekannte
        sx, sy, augen, mund, zzz = 1.0, 1.0, "offen", "laecheln", False
    if blinzelt and augen in ("offen", "gross"):
        augen = "zu"
    return sx, sy, augen, mund, zzz


class AvatarFenster(QWidget):
    def __init__(self, bus: EventBus, motor: Verhaltensmotor, schalter: Schalter,
                 toene: Toene, beim_beenden) -> None:
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

        self.bus = bus
        self.motor = motor
        self.schalter = schalter
        self.toene = toene
        self.monitore: list[Monitor] = lese_monitore()
        self.koerper = Koerper(halbe_breite=blob.BREITE / 2 - 4, hoehe=blob.HOEHE)
        self.koerper.retten(self.monitore)

        self.blase = Sprechblase()
        self.blase.knopf_gedrueckt.connect(self.motor.knopf)
        self.blase.weggeklickt.connect(self.motor.sprechblase_geschlossen)
        self._blase_id: int | None = None

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
        self._ausgabe: Ausgabe | None = None
        self._animation = "ruhe"
        self._animation_t = 0.0
        self._stauch_t = -1.0
        self._blick = (0.0, 0.0)
        self._letzte_darstellung: tuple | None = None
        self._letzte_maske: tuple | None = None
        self._darst: tuple = (1.0, 1.0, 1, "offen", "laecheln", (0.0, 0.0), False, True)
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
        self.motor.eigenleben.zuruecksetzen()
        self._platzieren()
        self.show()
        self._nach_vorne()
        log.info("Kobold zurückgeholt")

    def monitore_aktualisieren(self) -> None:
        self.monitore = lese_monitore()
        log.info("Monitore geändert: %s", [(m.name, m.geometrie, m.dpr) for m in self.monitore])
        if self.koerper.pruefe_monitore(self.monitore):
            log.info("Avatar außerhalb aller Monitore → Hauptmonitor")
            self.motor.eigenleben.zuruecksetzen()
        self._platzieren()
        self._nach_vorne()
        self.bus.senden("monitor.geaendert", anzahl=len(self.monitore))

    def kopf_mitte(self) -> tuple[float, float] | None:
        """Für den Maus-Beobachter: Körpermitte, None während des Ziehens."""
        if self.koerper.zustand == GEZOGEN:
            return None
        return self.koerper.x, self.koerper.y - blob.HOEHE / 2

    # --- Takt ----------------------------------------------------------------
    def _tick(self) -> None:
        dt = min(self._uhr.restart() / 1000.0, 0.05)
        k = self.koerper
        a = self.motor.tick(dt)
        self._ausgabe = a
        for ton in a.toene:
            self.toene.spielen(ton)

        # Bewegungsentscheidung (Nutzer-Eingriff hat Vorrang)
        frei = k.zustand == STEHT and not self._gedrueckt and not self._menue_offen
        laufen = False
        k.tempo = LAUFTEMPO
        if frei and a.ziel is not None:
            ziel_x = self._ziel_x(a.ziel)
            if ziel_x is not None and abs(ziel_x - k.x) > 4:
                laufen = True
                k.richtung = 1 if ziel_x > k.x else -1
                k.tempo = ZIELTEMPO
        elif frei and a.laufen and not self.schalter.nicht_stoeren:
            laufen = True
            k.richtung = a.richtung

        ereignisse = k.schritt(dt, self.monitore, laufen, self.schalter.monitor_bleiben)
        if GEDREHT in ereignisse:
            self.motor.eigenleben.richtung = k.richtung
        if GELANDET in ereignisse:
            self._stauch_t = 0.0
            self.toene.spielen("landen")
            self.bus.senden("avatar.gelandet")
        if GERETTET in ereignisse:
            log.info("Avatar ins Nichts gefallen → Hauptmonitor")

        # welche Animation ist sichtbar?
        if k.zustand == GEZOGEN:
            animation = "gezogen"
        elif k.zustand == FAELLT:
            animation = "fallen"
        elif laufen:
            animation = "laufen"
        else:
            animation = a.animation
        if animation != self._animation:
            self._animation = animation
            self._animation_t = 0.0
        else:
            self._animation_t += dt

        # Blick zum Mauszeiger beim Anschauen, Avatar dreht sich mit
        self._blick = (0.0, 0.0)
        if animation in ("anschauen", "erschrecken") and k.zustand == STEHT:
            c = QCursor.pos()
            dx, dy = c.x() - k.x, c.y() - (k.y - AUGEN_HOEHE)
            if abs(dx) > 30:
                k.richtung = 1 if dx > 0 else -1
            laenge = math.hypot(dx, dy) or 1.0
            self._blick = (abs(dx) / laenge * 2.6, dy / laenge * 2.2)

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
        self._sprechblase(a)

        if k.in_bewegung or self._stauch_t >= 0 or self._gedrueckt:
            soll = TAKT_SCHNELL_MS
        elif animation in BEWEGTE_ANIMATIONEN:
            soll = TAKT_MITTEL_MS
        else:
            soll = TAKT_RUHE_MS
        if self._takt.interval() != soll:
            self._takt.setInterval(soll)

    def _monitor(self) -> Monitor | None:
        k = self.koerper
        return monitor_unter_fuss(self.monitore, k.x, k.y) or monitor_bei(self.monitore, k.x, k.y - 1)

    def _ziel_x(self, ziel: str | float) -> float | None:
        m = self._monitor()
        if m is None:
            return None
        links = m.verfuegbar.links + self.koerper.halbe_breite + ZIEL_RAND
        rechts = m.verfuegbar.rechts - self.koerper.halbe_breite - ZIEL_RAND
        if ziel == "rand_rechts":
            return rechts
        if ziel == "rand_links":
            return links
        if ziel == "mitte":
            return (links + rechts) / 2
        if isinstance(ziel, (int, float)):
            return max(links, min(float(ziel), rechts))
        return None

    def _platzieren(self) -> None:
        x = round(self.koerper.x - FUSS.x())
        y = round(self.koerper.y - FUSS.y())
        if self.pos() != QPoint(x, y):
            self.move(x, y)

    def _nach_vorne(self) -> None:
        if self.isVisible():
            win32.ganz_nach_vorne(int(self.winId()))
            if self.blase.isVisible():
                win32.ganz_nach_vorne(int(self.blase.winId()))

    # --- Sprechblase ---------------------------------------------------------
    def _sprechblase(self, a: Ausgabe) -> None:
        if a.sprechblase is None:
            if self._blase_id is not None:
                self._blase_id = None
                self.blase.verstecke()
            return
        wid, text, knoepfe = a.sprechblase
        if wid != self._blase_id:
            self._blase_id = wid
            self.blase.zeige(wid, text, knoepfe)
            self._nach_vorne()
        k = self.koerper
        m = self._monitor()
        if m is not None:
            v = m.verfuegbar
            bereich = (v.links, v.oben, v.rechts, v.unten)
        else:
            bereich = (k.x - 2000, k.y - 2000, k.x + 2000, k.y + 2000)
        sy = self._darst[1]
        self.blase.platzieren(k.x, k.y - blob.HOEHE * sy, k.y, bereich)

    # --- Darstellung -------------------------------------------------------
    def _darstellung_aktualisieren(self, erzwingen: bool = False) -> None:
        a = self._ausgabe
        blinzelt = a.blinzelt if a else False
        sx, sy, augen, mund, zzz = ausdruck(self._animation, self._animation_t, blinzelt)
        if self._stauch_t >= 0:
            s = math.sin(math.pi * self._stauch_t / STAUCH_DAUER)
            sx, sy = 1 + 0.14 * s, 1 - 0.16 * s
        elif self.koerper.zustand == FAELLT:
            s = min(abs(self.koerper.vy) / 1800.0, 1.0) * 0.08
            sx, sy = 1 - s * 0.6, 1 + s
        schatten = self.koerper.zustand == STEHT
        blick = (round(self._blick[0], 1), round(self._blick[1], 1))
        darst = (round(sx, 3), round(sy, 3), self.koerper.richtung, augen, mund, blick, zzz, schatten)
        if erzwingen or darst != self._letzte_darstellung:
            self._letzte_darstellung = darst
            self._darst = darst
            if MASKE_AKTIV:
                schluessel = (round(sx, 2), round(sy, 2), darst[2], schatten, zzz)
                if erzwingen or schluessel != self._letzte_maske:
                    self._letzte_maske = schluessel
                    self.setMask(blob.maske(FUSS, sx, sy, darst[2], schatten, zzz))
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-API)
        sx, sy, richtung, augen, mund, blick, zzz, schatten = self._darst
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        blob.zeichne(p, FUSS, sx, sy, richtung, augen, mund, blick, zzz, schatten)
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
            self._takt.setInterval(TAKT_SCHNELL_MS)
            self.bus.senden("avatar.gezogen")
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
            self.bus.senden("avatar.losgelassen", vx=round(vx), vy=round(vy))
        else:
            k.huepfen()
            self.toene.spielen("huepfen")
            self.bus.senden("maus.klick")
        self._uhr.restart()
        self._takt.setInterval(TAKT_SCHNELL_MS)

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
        self.motor.nicht_stoeren = wert
        self.toene.stumm = wert
        self._darstellung_aktualisieren()

    def _menue_zu(self) -> None:
        self._menue_offen = False
