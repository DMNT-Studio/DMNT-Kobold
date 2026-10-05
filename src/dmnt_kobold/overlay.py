"""AvatarFenster: kleines, rahmenloses Overlay-Fenster in Avatar-Größe.

Das Fenster wandert mit dem Avatar. Transparente Bereiche sind durchklickbar
(zusätzlich Fenstermaske auf die Blob-Form).

Ablauf pro Takt:
  Verhaltensmotor (Wünsche/Eigenleben) → Ausgabe → Physik → Darstellung,
  Sprechblase, Töne. Nutzer-Eingriff (Ziehen, Menü) hat immer Vorrang.

Hüpfer (``bewegung.art = huepfen``) laufen nie: Jede Bewegung ist eine Kette aus
hocken → absprung → flug (echte Parabel) → landen → Pause. ``freuen_huepfend`` sind
drei Hüpfer auf der Stelle mit einer vollen Drehung. Partikel (Spritzer) und
Körper-Töne kommen zu ihren Momenten; ein Innenleben wackelt mit einer Feder nach.
Die Spritzer fliegen in einem eigenen, komplett durchklickbaren Fenster
(``PartikelFenster``) – die Maske des Avatars bleibt auf seiner Körperform.
Ohne Bewegung, Partikel und Wackeln fällt der Takt auf 100 ms (CPU in Ruhe).

Bedienung (Konzept #28): Linksklick gehört dem Avatar (``maus.klick`` an seine Regeln;
reagiert keine, macht der Sockel einen kleinen Hüpfer). Rechtsklick zeigt nur sein
Verhalten (Nicht stören, Auf diesem Monitor bleiben). Einrichten und Beenden liegen im Tray.
"""
from __future__ import annotations

import logging
import math
import os
import random
import time
from collections import deque

from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRect, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QPainter
from PySide6.QtWidgets import QWidget

from . import katalog, win32
from .avatar import Darsteller, Zustand
from .bus import EventBus
from .menue import Schalter, baue_menue
from .monitore import Monitor, lese_monitore, monitor_bei, monitor_unter_fuss
from .motor import Ausgabe, Verhaltensmotor
from .physik import FAELLT, GEDREHT, GELANDET, GERETTET, GEZOGEN, STEHT, Koerper
from .sprechblase import Sprechblase
from .toene import Toene

log = logging.getLogger(__name__)

AUGEN_ANTEIL = 0.58      # Augenhöhe als Anteil der Körperhöhe (für den Blick)
MASKEN_CACHE = 300

TAKT_SCHNELL_MS = 16     # Fallen, Ziehen, Stauchen
TAKT_MITTEL_MS = 33      # Laufen, Anschauen, Ausdrücke
TAKT_RUHE_MS = 100       # nichts passiert
ZIEH_SCHWELLE = 5        # px
WURF_FENSTER_S = 0.08    # letzte 80 ms Mausbewegung
STAUCH_DAUER = 0.12
TOPMOST_ALLE_S = 2.0
LAUFTEMPO = katalog.standard("laufgeschwindigkeit")
ZIELTEMPO = katalog.standard("zieltempo")
ZIEL_RAND = 24.0

BEWEGTE_ANIMATIONEN = {"laufen", "anschauen", "freuen", "erschrecken", "sprechen", "gezogen", "fallen",
                       "unzufrieden", "drehen"}
HUEPF_PHASEN = ("hocken", "absprung", "flug", "landen")
FREUDE_HUEPFER = 3
FREUDE_PAUSE_S = 0.1
FLUG_ENTSPANNEN_S = 0.16      # so lange bleibt er nach dem Absprung gestreckt
PARTIKEL_SCHWERKRAFT = 1400.0
INNEN_VERZOEGERUNG_S = 0.06   # Innenleben folgt dem Körper so viel später …
INNEN_FEDER = 900.0           # … mit einer leichten Feder
INNEN_DAEMPFUNG = 16.0
INNEN_MAX_PX = 6.0

PARTIKEL_RAND = 64           # so weit dürfen Spritzer über das Avatar-Fenster hinaus

MASKE_AKTIV = os.environ.get("DMNT_KOBOLD_OHNE_MASKE") != "1"


def _mischen(a: tuple[float, float], b: tuple[float, float], u: float) -> tuple[float, float]:
    u = max(0.0, min(1.0, u))
    return a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u


def huepf_form(phase: str, t: float, bewegung: dict, hocken_s: float) -> tuple[float, float]:
    """(Breite, Höhe) des Körpers in einer Hüpf-Phase – Stauchen und Strecken um den
    Fußpunkt, Form aus dem Bauplan (``stauchen``, ``strecken``)."""
    st = bewegung.get("stauchen", katalog.HUEPF_STANDARD["stauchen"])
    sr = bewegung.get("strecken", katalog.HUEPF_STANDARD["strecken"])
    gestaucht = (float(st.get("breite", 1)), float(st.get("hoehe", 1)))
    gestreckt = (float(sr.get("breite", 1)), float(sr.get("hoehe", 1)))
    if phase == "hocken":
        u = t / hocken_s if hocken_s > 0 else 1.0
        return _mischen((1.0, 1.0), gestaucht, u * u * (3 - 2 * u))
    if phase == "absprung":
        return _mischen(gestaucht, gestreckt, t / katalog.ABSPRUNG_S)
    if phase == "flug":
        return _mischen(gestreckt, (1.0, 1.0), t / FLUG_ENTSPANNEN_S)
    if phase == "landen":
        return _mischen((1.0, 1.0), gestaucht, math.sin(math.pi * min(1.0, t / katalog.LANDEN_S)))
    return 1.0, 1.0


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


class PartikelFenster(QWidget):
    """Zeichnet die Spritzer. Komplett durchklickbar (``WindowTransparentForInput`` →
    ``WS_EX_TRANSPARENT``) und nur sichtbar, solange Spritzer fliegen."""

    def __init__(self) -> None:
        super().__init__(None)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowDoesNotAcceptFocus
            | Qt.WindowType.NoDropShadowWindowHint
            | Qt.WindowType.WindowTransparentForInput
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setWindowTitle("DMNT-Kobold Spritzer")
        self.tropfen: list[tuple[QRectF, QColor, str]] = []

    def zeigen(self, bereich: QRect, tropfen: list[tuple[QRectF, QColor, str]]) -> None:
        """``bereich`` global, ``tropfen`` in Koordinaten relativ zu ``bereich``."""
        self.tropfen = tropfen
        if self.geometry() != bereich:
            self.setGeometry(bereich)
        if not self.isVisible():
            self.show()
            win32.ganz_nach_vorne(int(self.winId()))
        self.update()

    def verstecken(self) -> None:
        self.tropfen = []
        if self.isVisible():
            self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        for r, farbe, form in self.tropfen:
            p.setBrush(farbe)
            if form == "tropfen":
                p.drawEllipse(r)
            else:
                p.drawRect(r)
        p.end()


class AvatarFenster(QWidget):
    def __init__(self, bus: EventBus, motor: Verhaltensmotor, schalter: Schalter,
                 toene: Toene, darsteller: Darsteller, lauftempo: float = LAUFTEMPO,
                 zieltempo: float = ZIELTEMPO, werte: katalog.Werte | None = None) -> None:
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
        self.darsteller = darsteller
        self.fuss = darsteller.fuss
        self.lauftempo = lauftempo
        self.zieltempo = zieltempo
        self.werte = werte or katalog.Werte()
        self.huepft = darsteller.bewegung.get("art") == "huepfen"
        self.hocken_s = float(darsteller.bewegung.get("hocken_ms", katalog.HUEPF_STANDARD["hocken_ms"])) / 1000
        self.setFixedSize(darsteller.fenster_b, darsteller.fenster_h)
        self.setWindowTitle("DMNT-Kobold")

        self.bus = bus
        self.motor = motor
        self.schalter = schalter
        self.toene = toene
        self.monitore: list[Monitor] = lese_monitore()
        self.koerper = Koerper(halbe_breite=darsteller.breite / 2 - 4, hoehe=darsteller.hoehe)
        self.koerper.retten(self.monitore)

        self.blase = Sprechblase()
        self.blase.knopf_gedrueckt.connect(self.motor.knopf)
        self.blase.weggeklickt.connect(self.motor.sprechblase_geschlossen)
        self._blase_id: int | None = None

        # Einrichten: öffnet app.py über das Tray; solange es offen ist, führt es den Avatar
        self.einrichten_aktiv = False
        self._fuehrung: dict | None = None   # Schweben/Springen statt Physik
        self._festgehalten = False

        self.menue = baue_menue(schalter, self)    # nur sein Verhalten (#28)
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
        self._variante = "ruhe"
        self._stauch_t = -1.0
        self._blick = (0.0, 0.0)
        self._letzte_darstellung: tuple | None = None
        self._letzte_maske: tuple | None = None
        self._masken: dict[tuple, object] = {}
        self._zustand = Zustand()
        self._topmost_rest = 0.0

        # Hüpfen, Drehen, Partikel, Innenleben
        self._rng = random.Random()
        self._phase = ""                     # "", hocken, absprung, flug, landen, pause
        self._phase_t = 0.0
        self._pause_s = 0.0
        self._hupf_weite = 0.0
        self._freude: dict | None = None     # {"wid", "rest", "phi"} – freuen_huepfend
        self._drehung: float | None = None
        self._partikel: list[dict] = []
        self.partikel_fenster = PartikelFenster()
        self._antippen = False               # Rückfall-Hüpfer nach einem Klick ohne Regel
        self._innen_variante: str | None = None
        self._innen_pos: list[float] | None = None
        self._innen_v = [0.0, 0.0]
        self._innen_spur: deque[tuple[float, float, float]] = deque(maxlen=32)
        self._innen_versatz = (0.0, 0.0)
        self._zeit = 0.0

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
        return self.koerper.x, self.koerper.y - self.darsteller.hoehe / 2

    # --- Takt ----------------------------------------------------------------
    def _tick(self) -> None:
        dt = min(self._uhr.restart() / 1000.0, 0.05)
        k = self.koerper
        a = self.motor.tick(dt)
        self._ausgabe = a
        for ton in a.toene:
            self.toene.spielen(ton)

        laufen = False
        self._zeit += dt
        if self._fuehrung is not None:
            ereignisse = self._fuehrung_schritt(dt)
        elif self._festgehalten:
            ereignisse = []
        elif self.huepft:
            ereignisse = self._huepfen(dt, a)
        else:
            # Bewegungsentscheidung (Nutzer-Eingriff hat Vorrang)
            frei = k.zustand == STEHT and not self._gedrueckt and not self._menue_offen
            k.tempo = self.lauftempo
            if frei and a.ziel is not None:
                ziel_x = self._ziel_x(a.ziel)
                if ziel_x is not None and abs(ziel_x - k.x) > 4:
                    laufen = True
                    k.richtung = 1 if ziel_x > k.x else -1
                    k.tempo = self.zieltempo
            elif frei and a.laufen and not self.schalter.nicht_stoeren:
                laufen = True
                k.richtung = a.richtung
            ereignisse = k.schritt(dt, self.monitore, laufen, self.schalter.monitor_bleiben)
        if GEDREHT in ereignisse:
            self.motor.eigenleben.richtung = k.richtung
        if GELANDET in ereignisse:
            if not self.huepft:
                self._stauch_t = 0.0
            self._moment("landen")
            art, hoehe = k.landung
            self.bus.senden("avatar.gelandet", art=art, fallhoehe_px=round(hoehe))
        if GERETTET in ereignisse:
            log.info("Avatar ins Nichts gefallen → Hauptmonitor")

        # welche Animation ist sichtbar?
        if k.zustand == GEZOGEN:
            animation = "gezogen"
        elif k.zustand == FAELLT and not (self.huepft and k.hupf_flug):
            animation = "fallen"
        elif self._fuehrung is not None:
            animation = "schweben" if self._fuehrung["art"] == "schweben" else "springen"
        elif laufen:
            animation = "laufen"
        elif self.huepft and (self._phase in HUEPF_PHASEN or k.zustand == FAELLT):
            animation = a.animation if self._freude is not None else (self._phase or "fallen")
        elif self.huepft and self._phase == "pause" and self._freude is None and self._will_huepfen(a):
            animation = "ruhe"                 # zwischen zwei Hüpfern einer Kette
        else:
            animation = a.animation
        if self.huepft and animation == "laufen":
            animation = "ruhe"                 # Hüpfer laufen nie
        if animation != self._animation:
            self._animation = animation
            self._animation_t = 0.0
            self._variante = random.choice(self.darsteller.varianten(animation))
            if animation not in ("landen", "laufen"):       # landen kommt mit der Landung
                self._moment(animation, ton=animation != "sprechen")
        else:
            self._animation_t += dt

        # Drehen: freuen_huepfend (eine Drehung über drei Hüpfer) oder Animation „drehen“
        if self._freude is not None:
            self._drehung = self._freude["phi"] if 0 < self._freude["phi"] < 360 else None
        elif animation == "drehen":
            self._drehung = (self._animation_t / katalog.DREHUNG_S * 360) % 360
        else:
            self._drehung = None
        self._innen_schritt(dt, a)
        self._partikel_schritt(dt)

        # Blick zum Mauszeiger beim Anschauen, Avatar dreht sich mit
        self._blick = (0.0, 0.0)
        if animation in ("anschauen", "erschrecken") and k.zustand == STEHT:
            c = QCursor.pos()
            dx, dy = c.x() - k.x, c.y() - (k.y - self.darsteller.hoehe * AUGEN_ANTEIL)
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

        if k.in_bewegung or self._stauch_t >= 0 or self._gedrueckt or self._fuehrung is not None \
                or self._phase in HUEPF_PHASEN or self._partikel or self._innen_wackelt() \
                or self._drehung is not None:
            soll = TAKT_SCHNELL_MS
        elif animation in BEWEGTE_ANIMATIONEN or self._phase == "pause":
            soll = TAKT_MITTEL_MS
        else:
            soll = TAKT_RUHE_MS
        if self._takt.interval() != soll:
            self._takt.setInterval(soll)

    # --- Hüpfen ----------------------------------------------------------------
    def _will_huepfen(self, a: Ausgabe) -> bool:
        if self._antippen or (self._freude is not None and self._freude["rest"] > 0):
            return True
        if a.ziel is not None:
            ziel_x = self._ziel_x(a.ziel)
            return ziel_x is not None and abs(ziel_x - self.koerper.x) > 4
        return bool(a.laufen) and not self.schalter.nicht_stoeren

    def _naechster_hupfer(self, a: Ausgabe) -> float | None:
        """Weite des nächsten Hüpfers (setzt die Richtung) oder None = stehen bleiben."""
        k = self.koerper
        if self._freude is not None:
            return 0.0 if self._freude["rest"] > 0 else None
        if self._antippen:                     # Klick ohne Regel: ein Hüpfer auf der Stelle
            self._antippen = False
            return 0.0
        weite = float(self.werte["sprungweite_px"])
        if a.ziel is not None:
            ziel_x = self._ziel_x(a.ziel)
            if ziel_x is None or abs(ziel_x - k.x) <= 4:
                return None
            k.richtung = 1 if ziel_x > k.x else -1
            return min(weite, abs(ziel_x - k.x))
        if a.laufen and not self.schalter.nicht_stoeren:
            k.richtung = a.richtung
            return weite
        return None

    def _huepfen(self, dt: float, a: Ausgabe) -> list[str]:
        """Ablauf eines Hüpfers: hocken → absprung → flug → landen → pause."""
        k = self.koerper
        # freuen_huepfend: neuer Wunsch → drei Hüpfer; Wunsch vorbei → nach der Landung aufhören
        if a.bewegung == "freuen_huepfend" and a.wunsch_id is not None:
            if self._freude is None or self._freude["wid"] != a.wunsch_id:
                self._freude = {"wid": a.wunsch_id, "rest": FREUDE_HUEPFER, "phi": 0.0}
                if self._phase == "pause":
                    self._phase = ""
        elif self._freude is not None and self._phase in ("", "pause"):
            self._freude = None

        if k.zustand == GEZOGEN:
            self._phase, self._freude, self._antippen = "", None, False
            return []
        if self._gedrueckt and self._phase in ("", "hocken", "pause"):   # Maus drückt: stillhalten
            self._phase = ""
            return k.schritt(dt, self.monitore)
        if k.zustand == FAELLT and not k.hupf_flug:          # geworfen oder heruntergefallen
            self._phase = ""
            ereignisse = k.schritt(dt, self.monitore)
            if GELANDET in ereignisse:
                self._phase, self._phase_t = "landen", 0.0
            return ereignisse

        self._phase_t += dt
        phase = self._phase
        ereignisse: list[str] = []
        if phase in ("", "pause"):
            frei = k.zustand == STEHT and not self._menue_offen
            fertig = phase == "" or self._phase_t >= self._pause_s
            if frei and fertig:
                weite = self._naechster_hupfer(a)
                if weite is not None:
                    self._hupf_weite = weite
                    self._phase, self._phase_t = "hocken", 0.0
                elif phase == "pause":
                    self._phase = ""
            ereignisse = k.schritt(dt, self.monitore)
        elif phase == "hocken":
            if self._phase_t >= self.hocken_s:
                weite, ereignisse = k.hupf_weite(self._hupf_weite, self.monitore, self.schalter.monitor_bleiben)
                k.hupf_ab(weite, float(self.werte["sprunghoehe_px"]))
                self._phase, self._phase_t = "absprung", 0.0
                if self._freude is not None:
                    self._freude["rest"] -= 1
            else:
                ereignisse = k.schritt(dt, self.monitore)
        elif phase in ("absprung", "flug"):
            if phase == "absprung" and self._phase_t >= katalog.ABSPRUNG_S:
                self._phase = "flug"
            ereignisse = k.schritt(dt, self.monitore)
            if self._freude is not None:      # eine volle Drehung, verteilt auf die Flüge
                schritt = 360 / (FREUDE_HUEPFER * k.flugzeit(float(self.werte["sprunghoehe_px"])))
                bis = 360 * (FREUDE_HUEPFER - self._freude["rest"]) / FREUDE_HUEPFER
                self._freude["phi"] = min(bis, self._freude["phi"] + schritt * dt)
            if GELANDET in ereignisse:
                self._phase, self._phase_t = "landen", 0.0
                if self._freude is not None:
                    self._freude["phi"] = 360 * (FREUDE_HUEPFER - self._freude["rest"]) / FREUDE_HUEPFER
            elif k.zustand == STEHT:          # Flug abgebrochen (z. B. Monitor weg)
                self._phase = ""
        elif phase == "landen":
            if self._phase_t >= katalog.LANDEN_S:
                self._phase, self._phase_t = "pause", 0.0
                if self._freude is not None:
                    self._pause_s = FREUDE_PAUSE_S
                else:
                    self._pause_s = self._rng.uniform(float(self.werte["hupf_pause_min_s"]),
                                                      float(self.werte["hupf_pause_max_s"]))
            ereignisse = k.schritt(dt, self.monitore)
        return ereignisse

    # --- Momente: Partikel und Körper-Töne --------------------------------------
    def _moment(self, name: str, ton: bool = True) -> None:
        if ton:
            if name == "landen":
                self.toene.spielen("landen")
            else:
                self.toene.moment(name)
        d = self.darsteller.partikel.get(name)
        if not d:
            return
        k = self.koerper
        unten = name in ("landen", "hocken", "absprung")
        y0 = k.y if unten else k.y - self.darsteller.hoehe * 0.5
        dauer = max(0.05, float(d["dauer_ms"]) / 1000)
        weite = float(d["reichweite_px"])
        farbe = QColor(d["farbe"])
        for _ in range(self._rng.randint(int(d["anzahl"][0]), int(d["anzahl"][1]))):
            seite = self._rng.choice((-1, 1))
            self._partikel.append({
                "x": k.x + seite * self._rng.uniform(0.1, 0.4) * self.darsteller.breite / 2, "y": y0 - 1,
                "vx": seite * self._rng.uniform(0.45, 1.0) * weite / (dauer * 0.8),
                "vy": -self._rng.uniform(150, 230), "t": 0.0, "dauer": dauer, "boden": k.y,
                "g": self._rng.uniform(float(d["groesse_px"][0]), float(d["groesse_px"][1])),
                "farbe": farbe, "deckkraft": float(d["deckkraft"]), "form": d.get("form", "quadrat")})

    def _partikel_schritt(self, dt: float) -> None:
        if not self._partikel:
            self.partikel_fenster.verstecken()
            return
        for t in self._partikel:
            t["t"] += dt
            t["vy"] += PARTIKEL_SCHWERKRAFT * dt
            t["x"] += t["vx"] * dt
            t["y"] += t["vy"] * dt
            if t["y"] >= t["boden"]:            # auf dem Boden liegen bleiben
                t["y"], t["vy"], t["vx"] = t["boden"], 0.0, t["vx"] * 0.6
        self._partikel = [t for t in self._partikel if t["t"] < t["dauer"]]
        if not self._partikel:
            self.partikel_fenster.verstecken()
            return
        bereich = self.partikel_bereich()
        self.partikel_fenster.zeigen(bereich, self._partikel_in(bereich.left(), bereich.top()))

    def partikel_bereich(self) -> QRect:
        """Globaler Bereich des Spritzer-Fensters: Avatar-Fenster plus Rand."""
        x = round(self.koerper.x - self.fuss.x())
        y = round(self.koerper.y - self.fuss.y())
        return QRect(x - PARTIKEL_RAND, y - PARTIKEL_RAND, self.width() + 2 * PARTIKEL_RAND,
                     self.height() + 2 * PARTIKEL_RAND)

    def _partikel_in(self, ox: float, oy: float) -> list[tuple[QRectF, QColor, str]]:
        ergebnis = []
        for t in self._partikel:
            g = t["g"]
            h = g * 1.3 if t["form"] == "tropfen" else g
            farbe = QColor(t["farbe"])
            farbe.setAlphaF(max(0.0, t["deckkraft"] * (1 - t["t"] / t["dauer"])))
            ergebnis.append((QRectF(t["x"] - ox - g / 2, t["y"] - oy - h, g, h), farbe, t["form"]))
        return ergebnis

    # --- Innenleben: Variante und Nachwackeln ----------------------------------------
    def _innen_wackelt(self) -> bool:
        return self._innen_versatz != (0.0, 0.0) or abs(self._innen_v[0]) + abs(self._innen_v[1]) > 1.0

    def _innen_schritt(self, dt: float, a: Ausgabe) -> None:
        if not self.darsteller.innenleben:
            return
        variante = a.innen
        if variante != self._innen_variante:
            self._innen_variante = variante
            self._innen_v[1] -= 70.0          # Wechsel: kleiner Hopser im Körper
        k = self.koerper
        mitte = (k.x, k.y - self.darsteller.hoehe * self._zustand.sy / 2)
        self._innen_spur.append((self._zeit, *mitte))
        if self._innen_pos is None:
            self._innen_pos = list(mitte)
        ziel = mitte
        for zeit, x, y in self._innen_spur:     # Stand vor 60 ms
            if zeit <= self._zeit - INNEN_VERZOEGERUNG_S:
                ziel = (x, y)
        for i in (0, 1):
            beschl = INNEN_FEDER * (ziel[i] - self._innen_pos[i]) - INNEN_DAEMPFUNG * self._innen_v[i]
            self._innen_v[i] += beschl * dt
            self._innen_pos[i] += self._innen_v[i] * dt
            versatz = self._innen_pos[i] - mitte[i]
            if abs(versatz) > INNEN_MAX_PX:
                self._innen_pos[i] = mitte[i] + math.copysign(INNEN_MAX_PX, versatz)
        dx = round((self._innen_pos[0] - mitte[0]) * 2) / 2
        dy = round((self._innen_pos[1] - mitte[1]) * 2) / 2
        if abs(dx) < 0.5 and abs(dy) < 0.5 and abs(self._innen_v[0]) + abs(self._innen_v[1]) < 1.0:
            dx = dy = 0.0
            self._innen_v = [0.0, 0.0]
            self._innen_pos = list(mitte)
        self._innen_versatz = (dx, dy)

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
        x = round(self.koerper.x - self.fuss.x())
        y = round(self.koerper.y - self.fuss.y())
        if self.pos() != QPoint(x, y):
            self.move(x, y)

    def _nach_vorne(self) -> None:
        if self.isVisible():
            win32.ganz_nach_vorne(int(self.winId()))
            if self.blase.isVisible():
                win32.ganz_nach_vorne(int(self.blase.winId()))

    # --- Einrichten: geführte Bewegung ------------------------------------------
    def position(self) -> tuple[float, float]:
        return self.koerper.x, self.koerper.y

    def schweben_nach(self, x: float, y: float, dauer: float = 1.0, fertig=None) -> None:
        """Schwebt (Physik aus) zum Fußpunkt (x, y) und bleibt dort, bis ``loslassen_nach``."""
        self._fuehrung_starten("schweben", x, y, dauer, fertig)

    def springen_nach(self, x: float, y: float, dauer: float = 0.85, fertig=None) -> None:
        """Sprung im Bogen zum Fußpunkt (x, y), dort landen (Stauchen), Physik wieder an."""
        self._fuehrung_starten("springen", x, y, dauer, fertig)
        self.toene.spielen("huepfen")

    def _fuehrung_starten(self, art: str, x: float, y: float, dauer: float, fertig) -> None:
        k = self.koerper
        k.zustand = STEHT
        k.vx = k.vy = 0.0
        if abs(x - k.x) > 4:
            k.richtung = 1 if x > k.x else -1
        self._gedrueckt = False
        self._stauch_t = -1.0
        self._phase, self._freude = "", None
        self._fuehrung = {"art": art, "von": (k.x, k.y), "nach": (x, y), "t": 0.0,
                          "dauer": max(0.05, dauer), "fertig": fertig}
        self._takt.setInterval(TAKT_SCHNELL_MS)

    def _fuehrung_schritt(self, dt: float) -> list[str]:
        f = self._fuehrung
        k = self.koerper
        f["t"] += dt
        s = min(1.0, f["t"] / f["dauer"])
        (x0, y0), (x1, y1) = f["von"], f["nach"]
        if f["art"] == "schweben":
            e = s * s * (3 - 2 * s)
            k.x = x0 + (x1 - x0) * e
            k.y = y0 + (y1 - y0) * e - math.sin(math.pi * s) * 24
        else:
            hoehe = 70 + 0.12 * abs(y1 - y0)
            k.x = x0 + (x1 - x0) * s
            k.y = y0 + (y1 - y0) * s * s - hoehe * 4 * s * (1 - s) * (1 - 0.35 * s)
        k.vx = k.vy = 0.0
        if s < 1.0:
            return []
        self._fuehrung = None
        fertig = f["fertig"]
        if f["art"] == "springen":
            self._festgehalten = False
            k.zustand = STEHT
            if self.huepft:
                self._phase, self._phase_t = "landen", 0.0
            else:
                self._stauch_t = 0.0
            self._moment("landen")
            self.bus.senden("avatar.gelandet", art="hupf", fallhoehe_px=round(70 + 0.12 * abs(y1 - y0)))
            k.pruefe_monitore(self.monitore)    # Monitor inzwischen weg → Hauptmonitor
        else:
            self._festgehalten = True
        if fertig:
            fertig()
        return []

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
        kopf = k.y - self.darsteller.hoehe * self._zustand.sy
        if self._zustand.zubehoer:
            kopf -= 12
        self.blase.platzieren(k.x, kopf, k.y, bereich)

    # --- Darstellung -------------------------------------------------------
    def _darstellung_aktualisieren(self, erzwingen: bool = False) -> None:
        a = self._ausgabe
        blinzelt = a.blinzelt if a else False
        sx, sy, augen, mund, zzz = ausdruck(self._animation, self._animation_t, blinzelt)
        sprite = self.darsteller.animiert_sich_selbst
        if sprite and self._animation == "laufen":
            sx, sy = 1.0, 1.0                  # die Frames laufen selbst
        if self.huepft and self._phase in HUEPF_PHASEN:
            sx, sy = huepf_form(self._phase, self._phase_t, self.darsteller.bewegung, self.hocken_s)
        elif self._stauch_t >= 0:
            s = math.sin(math.pi * self._stauch_t / STAUCH_DAUER)
            sx, sy = 1 + 0.14 * s, 1 - 0.16 * s
        elif self.koerper.zustand == FAELLT:
            s = min(abs(self.koerper.vy) / 1800.0, 1.0) * 0.08
            sx, sy = 1 - s * 0.6, 1 + s
        richtung = self.koerper.richtung
        animation, drehung = self._variante, None
        if self._drehung is not None:
            phi = self._drehung
            if self.darsteller.hat("drehen"):            # Frames vorne → … → hinten
                animation, drehung = "drehen", phi
                if phi > 180:
                    richtung = -richtung
            else:                                        # Pseudo-Drehung
                c = math.cos(math.radians(phi))
                sx *= max(0.06, abs(c))
                if c < 0:
                    richtung = -richtung
        if sprite:                             # grob runden → wenige Masken im Cache
            sx, sy = round(sx * 50) / 50, round(sy * 50) / 50
        z = Zustand(
            animation=animation, t=self._animation_t, sx=sx, sy=sy,
            richtung=richtung, augen=augen, mund=mund,
            blick=(round(self._blick[0], 1), round(self._blick[1], 1)), zzz=zzz,
            schatten=self.koerper.zustand == STEHT and self._fuehrung is None,
            zubehoer=a.zubehoer if a else frozenset(), drehung=drehung,
            innen=self._innen_variante, innen_versatz=self._innen_versatz,
        )
        schluessel = self.darsteller.masken_schluessel(z)
        darst = (schluessel, z.augen, z.mund, z.blick, round(z.sx, 3), round(z.sy, 3), z.innen_versatz)
        if erzwingen or darst != self._letzte_darstellung:
            self._letzte_darstellung = darst
            self._zustand = z
            if MASKE_AKTIV and (erzwingen or schluessel != self._letzte_maske):
                self._letzte_maske = schluessel
                maske = self._masken.get(schluessel)
                if maske is None:
                    if len(self._masken) > MASKEN_CACHE:
                        self._masken.clear()
                    maske = self._masken[schluessel] = self.darsteller.maske(z)
                self.setMask(maske)
            self.update()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        self.darsteller.zeichnen(p, self._zustand)
        p.end()

    # --- Maus ----------------------------------------------------------------
    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self.einrichten_aktiv:
            return
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
            self.klicken()
        self._uhr.restart()
        self._takt.setInterval(TAKT_SCHNELL_MS)

    def klicken(self) -> None:
        """Linksklick gehört dem Avatar und öffnet nie das Einrichten (#28). ``maus.klick``
        geht an seine Regeln; Läufer machen dazu wie seit M1 einen kleinen Hüpfer.
        Hüpfer hüpfen nur, wenn keine Regel reagiert hat (Rückfall im Sockel)."""
        vorher = self.motor.naechste_id
        self.bus.senden("maus.klick")
        if not self.huepft:
            self.koerper.huepfen()
            self.toene.spielen("huepfen")
        elif self.motor.naechste_id == vorher:     # niemand hat sich etwas gewünscht
            self._antippen = True
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
