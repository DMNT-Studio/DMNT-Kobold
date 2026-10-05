"""Einrichten-Modus (Konzept Abschnitt 10): kein Einstellungsfenster, sondern
eine Bühne um den Avatar.

Ablauf Öffnen (~1,4 s): Desktop dunkelt ab · Avatar schwebt zur Monitor-Mitte
(macht das Overlay) · runde Herkunft + Sockel erscheinen · Namensschild,
vier schwebende Kategorien und „Fertig“ blenden ein.
Ablauf Schließen (~1,5 s): Kacheln/Kategorien weg · Herkunft und Sockel blenden
aus · Avatar springt mit Stauchen zurück auf die Taskleiste.

Die Bühne ist ein Fenster über dem verfügbaren Bereich eines Monitors
(Taskleiste bleibt frei). Der Avatar bleibt sein eigenes Fenster und wird
für die Dauer zum „Besitzer-Fenster“ der Bühne, damit er immer davor steht.
"""
from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QPointF, QRect, QRectF, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import (QBrush, QColor, QDesktopServices, QLinearGradient, QPainter, QPainterPath,
                           QPen, QPixmap, QRadialGradient)
from PySide6.QtWidgets import (QFileDialog, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QLineEdit,
                               QPushButton, QSlider, QVBoxLayout, QWidget)

from . import stil
from .karten import Kippschalter, schatten_karte_malen

log = logging.getLogger(__name__)

# Zeiten (s)
T_DIMMEN = 0.35
T_SCHWEBEN = 1.0
T_BUEHNE = (0.65, 1.15)
T_TEILE = (1.0, 1.4)
T_ZU_TEILE = 0.2
T_ZU_BUEHNE = (0.15, 0.55)
T_ZU_DIMMEN = (0.3, 0.9)
T_SPRUNG_START = 0.35
T_SPRUNG = 0.85
T_MISCHEN = 0.9                # Herkunft des alten Kobolds verwischt in die des neuen
T_WECHSEL = 0.95               # so lange sind die Pfeile nach einem Wechsel gesperrt

ABDUNKELN = QColor(10, 30, 24)
ABDUNKELN_ALPHA = 128          # ca. 50 %

KACHEL_BREITE = 340
KAFFEE_URL = ""                # kommt in M5
REPO_URL = "https://github.com/DMNT-Studio/DMNT-Kobold"

# Kategorien: (Schlüssel, Text, Uhrzeit, Seite, Wipp-Frequenz, Phase)
KATEGORIEN = [
    ("tricks", "Tricks", 10, "links", 0.46, 0.0),
    ("lautstaerke", "Lautstärke", 8, "links", 0.57, 1.7),
    ("programme", "Programme", 2, "rechts", 0.51, 3.1),
    ("system", "System", 4, "rechts", 0.62, 4.4),
]


def _glatt(a: float, b: float, t: float) -> float:
    """0 vor a, 1 nach b, dazwischen weich."""
    if t <= a:
        return 0.0
    if t >= b:
        return 1.0
    x = (t - a) / (b - a)
    return x * x * (3 - 2 * x)


@dataclass
class Dienste:
    """Was die Bühne vom Rest des Programms braucht."""
    einstellungen: object                       # Speicher
    verwaltung: object                          # Modulverwaltung
    toene: object
    sicherung: object
    version: str
    avatar_name: str = "Kobold"
    herkunft: Path | None = None
    autostart_an: Callable[[], bool] = lambda: False
    autostart_setzen: Callable[[bool], bool] = lambda an: False
    zuletzt_programme: Callable[[], list[str]] = lambda: []
    avatare: Callable[[], list[tuple[str, str, Path | None]]] = lambda: []
    aktueller_avatar: str = ""
    nach_import: Callable[[], None] = lambda: None
    umbenannt: Callable[[str], None] = lambda name: None
    lautstaerke_geaendert: Callable[[float], None] = lambda w: None
    programme_geaendert: Callable[[], None] = lambda: None
    # Updates: Schalter „Nach Updates suchen“ (Programm-Einstellung, kein Verhalten)
    update_pruefen_an: Callable[[], bool] = lambda: True
    update_pruefen_setzen: Callable[[bool], bool] = lambda an: an
    neuigkeiten_url: str = "https://github.com/DMNT-Studio/DMNT-Kobold/releases"
    # Avatar sofort wechseln (Pfeile am Sockel, Adoptieren): startet Hüpfer und Überblenden,
    # liefert (Standardname, Herkunft) des neuen Avatars oder None, wenn er nicht ladbar ist.
    avatar_wechseln: Callable[[str], tuple[str, Path | None] | None] = lambda aid: None
    extra: dict = field(default_factory=dict)


def kobold_name(einstellungen, avatar_id: str, standard: str) -> str:
    """Name, den der Nutzer diesem Kobold gegeben hat – jeder Kobold behält seinen eigenen."""
    namen = einstellungen.get("namen") or {}
    return namen.get(avatar_id) or standard


def kobold_benennen(einstellungen, avatar_id: str, name: str) -> None:
    namen = dict(einstellungen.get("namen") or {})
    namen[avatar_id] = name
    einstellungen["namen"] = namen


# --- kleine Bausteine -----------------------------------------------------------

def _icon_malen(p: QPainter, art: str, r: QRectF, farbe: QColor) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(QPen(farbe, 1.8, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    p.setBrush(Qt.BrushStyle.NoBrush)
    c = r.center()
    s = r.width() / 2
    if art == "tricks":          # Funkeln
        pfad = QPainterPath()
        for i in range(4):
            w = math.pi / 2 * i
            pfad.moveTo(c)
            pfad.lineTo(c + QPointF(math.cos(w) * s, math.sin(w) * s))
        p.drawPath(pfad)
        p.drawEllipse(c, s * 0.28, s * 0.28)
    elif art == "lautstaerke":   # Lautsprecher
        pfad = QPainterPath()
        pfad.moveTo(c + QPointF(-s * 0.9, -s * 0.3))
        pfad.lineTo(c + QPointF(-s * 0.45, -s * 0.3))
        pfad.lineTo(c + QPointF(0, -s * 0.75))
        pfad.lineTo(c + QPointF(0, s * 0.75))
        pfad.lineTo(c + QPointF(-s * 0.45, s * 0.3))
        pfad.lineTo(c + QPointF(-s * 0.9, s * 0.3))
        pfad.closeSubpath()
        p.drawPath(pfad)
        p.drawArc(QRectF(c.x() - s * 0.35, c.y() - s * 0.5, s, s), -50 * 16, 100 * 16)
        p.drawArc(QRectF(c.x() - s * 0.6, c.y() - s * 0.85, s * 1.6, s * 1.7), -50 * 16, 100 * 16)
    elif art == "programme":     # Fenster
        p.drawRoundedRect(QRectF(c.x() - s * 0.9, c.y() - s * 0.75, s * 1.8, s * 1.5), 3, 3)
        p.drawLine(c + QPointF(-s * 0.9, -s * 0.3), c + QPointF(s * 0.9, -s * 0.3))
    else:                        # System: Zahnrad (vereinfacht)
        p.drawEllipse(c, s * 0.38, s * 0.38)
        for i in range(8):
            w = math.pi / 4 * i
            p.drawLine(c + QPointF(math.cos(w) * s * 0.62, math.sin(w) * s * 0.62),
                       c + QPointF(math.cos(w) * s * 0.92, math.sin(w) * s * 0.92))
    p.restore()


class KategorieKnopf(QPushButton):
    """Schwebende Pille mit Linien-Icon."""

    def __init__(self, schluessel: str, text: str, parent: QWidget) -> None:
        super().__init__(text, parent)
        self.schluessel = schluessel
        self.offen = False
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(172, 52))
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(6, 4, -6, -8)
        hover = self.underMouse()
        farbe = stil.AKZENT if self.offen else stil.FLAECHE
        schatten_karte_malen(p, r, radius=r.height() / 2, schatten=8,
                             farbe=farbe if not (hover and not self.offen) else stil.AKZENT_HELL)
        icon_farbe = QColor("white" if self.offen else stil.AKZENT)
        _icon_malen(p, self.schluessel, QRectF(r.left() + 16, r.center().y() - 9, 18, 18), icon_farbe)
        p.setPen(QColor("white" if self.offen else stil.TEXT))
        f = self.font()
        f.setFamily(stil.schriftart())
        f.setPixelSize(15)
        f.setWeight(f.Weight.DemiBold)
        p.setFont(f)
        p.drawText(r.adjusted(46, 0, -10, 0), Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                   self.text())
        p.end()


class PfeilKnopf(QPushButton):
    """Runder Milchglas-Knopf mit Linien-Pfeil neben dem Sockel: anderen Kobold holen."""

    GROESSE = 46

    def __init__(self, richtung: int, parent: QWidget) -> None:
        super().__init__(parent)
        self.richtung = richtung
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(self.GROESSE, self.GROESSE + 6))
        self.setToolTip("Nächster Kobold" if richtung > 0 else "Vorheriger Kobold")
        self.setStyleSheet("QPushButton { background: transparent; border: none; }")

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(4, 2, self.GROESSE - 8, self.GROESSE - 8)
        hover = self.underMouse() and self.isEnabled()
        schatten_karte_malen(p, r, radius=r.height() / 2, schatten=8,
                             farbe=stil.AKZENT_HELL if hover else stil.FLAECHE)
        farbe = QColor(stil.AKZENT)
        if not self.isEnabled():
            farbe.setAlpha(90)
        p.setPen(QPen(farbe, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        c = r.center()
        d = 5.0 * self.richtung
        pfad = QPainterPath()
        pfad.moveTo(c + QPointF(-d * 0.6, -8))
        pfad.lineTo(c + QPointF(d * 0.9, 0))
        pfad.lineTo(c + QPointF(-d * 0.6, 8))
        p.drawPath(pfad)
        p.end()


class Kachel(QWidget):
    """Weiße Karte mit Titel, Inhalt austauschbar."""

    RAND = 14

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedWidth(KACHEL_BREITE + 2 * self.RAND)
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(self.RAND + 20, self.RAND + 16, self.RAND + 20, self.RAND + 20)
        self.lay.setSpacing(10)

    def leeren(self) -> None:
        _layout_leeren(self.lay)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        schatten_karte_malen(p, QRectF(self.rect()).adjusted(self.RAND, self.RAND * 0.6, -self.RAND, -self.RAND),
                             radius=20)
        p.end()


def _layout_leeren(lay) -> None:
    """Inhalt sofort entfernen: verstecken und abhängen, damit nichts Altes bis zur nächsten
    Runde der Ereignisschleife sichtbar bleibt oder in die Größe einfließt."""
    while lay.count():
        item = lay.takeAt(0)
        w = item.widget()
        if w is not None:
            w.hide()
            w.setParent(None)
            w.deleteLater()
        elif item.layout() is not None:
            _layout_leeren(item.layout())
            item.layout().deleteLater()


def _label(text: str, art: str = "", wrap: bool = True) -> QLabel:
    lab = QLabel(text)
    if art:
        lab.setObjectName(art)
    lab.setWordWrap(wrap)
    lab.setTextFormat(Qt.TextFormat.PlainText)
    return lab


def _zeile(*widgets, stretch_index: int = 0) -> QHBoxLayout:
    h = QHBoxLayout()
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(10)
    for i, w in enumerate(widgets):
        if isinstance(w, QWidget):
            h.addWidget(w, 1 if i == stretch_index else 0)
        else:
            h.addLayout(w, 1 if i == stretch_index else 0)
    return h


# --- Namensschild ---------------------------------------------------------------

class Namensschild(QWidget):
    def __init__(self, name: str, beim_umbenennen: Callable[[str], None], parent: QWidget) -> None:
        super().__init__(parent)
        self._beim_umbenennen = beim_umbenennen
        self.setFixedHeight(64)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(30, 12, 22, 18)
        lay.setSpacing(8)
        self.label = QLabel(name)
        self.label.setStyleSheet(f"font-family: '{stil.schriftart()}'; font-size: 19px; font-weight: 800;"
                                 f" color: {stil.TEXT};")
        self.feld = QLineEdit(name)
        self.feld.setMaxLength(24)
        self.feld.hide()
        self.feld.returnPressed.connect(self._fertig)
        self.feld.editingFinished.connect(self._fertig)
        self.stift = QPushButton("✎")
        self.stift.setObjectName("klein")
        self.stift.setToolTip("Umbenennen")
        self.stift.clicked.connect(self._bearbeiten)
        lay.addWidget(self.label)
        lay.addWidget(self.feld)
        lay.addWidget(self.stift)
        self._anpassen()

    def name_setzen(self, name: str) -> None:
        """Anderer Kobold: sein Name aufs Schild (offenes Umbenennen wird verworfen)."""
        self.feld.hide()
        self.label.setText(name)
        self.label.show()
        self.stift.show()
        self._anpassen()

    def _anpassen(self) -> None:
        self.adjustSize()
        self.setFixedWidth(max(180, self.sizeHint().width()))

    def _bearbeiten(self) -> None:
        self.label.hide()
        self.stift.hide()
        self.feld.setText(self.label.text())
        self.feld.setFixedWidth(220)
        self.feld.show()
        self.window().activateWindow()
        self.feld.setFocus()
        self.feld.selectAll()
        self._anpassen()
        self.parent().teile_platzieren()

    def _fertig(self) -> None:
        if self.feld.isHidden():
            return
        name = " ".join(self.feld.text().split()) or self.label.text()
        self.feld.hide()
        self.label.setText(name)
        self.label.show()
        self.stift.show()
        self._anpassen()
        self.parent().teile_platzieren()
        self._beim_umbenennen(name)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(8, 4, -8, -10)
        schatten_karte_malen(p, r, radius=r.height() / 2, schatten=8)
        p.end()


# --- die Bühne ------------------------------------------------------------------

class Einrichten(QWidget):
    """Bühne. ``ort`` = verfügbarer Bereich des Monitors (logische Pixel)."""

    geschlossen = Signal()          # Ablauf komplett beendet
    zu_beginnt = Signal()           # Avatar soll zurückspringen

    def __init__(self, ort: QRect, dienste: Dienste) -> None:
        super().__init__(None)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("DMNT-Kobold Einrichten")
        self.setStyleSheet(stil.bedien_stylesheet())
        self.setGeometry(ort)
        self.d = dienste

        # Maße
        b, h = ort.width(), ort.height()
        self.radius = max(120, min(175, int(h * 0.17), int(b * 0.12)))
        self.mitte = QPointF(b / 2, h / 2 - h * 0.03)
        self.fuss_y = self.mitte.y() + self.radius * 0.58          # Avatar steht hier (Sockel-Oberseite)

        self._herkunft = QPixmap(str(dienste.herkunft)) if dienste.herkunft else QPixmap()
        self._herkunft_alt: QPixmap | None = None     # beim Wechsel: verwischt ins neue Bild
        self._misch_t0: float | None = None
        self._wechsel_bis = 0.0
        self._adopt_liste = False                     # rechte Kachel zeigt gerade die Kobold-Liste
        self._t0 = time.monotonic()
        self._zu_t0: float | None = None
        self._sprung_gesendet = False

        # Teile
        name = kobold_name(dienste.einstellungen, dienste.aktueller_avatar, dienste.avatar_name)
        self.schild = Namensschild(name, self._umbenennen, self)
        self.pfeile = [PfeilKnopf(-1, self), PfeilKnopf(1, self)]
        for pf in self.pfeile:
            pf.clicked.connect(lambda _=False, r=pf.richtung: self.wechseln(r))
        self._mit_pfeilen = len(dienste.avatare()) > 1
        self.kategorien: dict[str, KategorieKnopf] = {}
        for schluessel, text, *_ in KATEGORIEN:
            k = KategorieKnopf(schluessel, text, self)
            k.clicked.connect(lambda _=False, s=schluessel: self.kategorie_umschalten(s))
            self.kategorien[schluessel] = k
        self.fertig_knopf = QPushButton("Fertig", self)
        self.fertig_knopf.setObjectName("haupt")
        self.fertig_knopf.setFixedSize(QSize(150, 44))
        self.fertig_knopf.clicked.connect(lambda: self.schliessen("Fertig"))
        self.kacheln = {"links": Kachel(self), "rechts": Kachel(self)}
        self.offen: dict[str, str | None] = {"links": None, "rechts": None}
        for k in self.kacheln.values():
            k.hide()

        self._effekte: list[QGraphicsOpacityEffect] = []
        for pf in self.pfeile:
            pf.hide()
        teile = [self.schild, self.fertig_knopf, *self.kategorien.values()]
        if self._mit_pfeilen:                       # nur ein Kobold da: keine Pfeile
            teile += self.pfeile
        for w in teile:
            eff = QGraphicsOpacityEffect(w)
            eff.setOpacity(0.0)
            w.setGraphicsEffect(eff)
            self._effekte.append(eff)
            w.hide()
        self.teile_platzieren()

        self._takt = QTimer(self)
        self._takt.timeout.connect(self._tick)
        self._takt.start(16)

    # --- Ablauf ------------------------------------------------------------------
    def jetzt(self) -> float:
        return time.monotonic() - self._t0

    def avatar_ziel(self) -> QPointF:
        """Fußpunkt des Avatars auf dem Sockel (globale logische Koordinaten)."""
        return QPointF(self.x() + self.mitte.x(), self.y() + self.fuss_y)

    def _tick(self) -> None:
        t = self.jetzt()
        if self._zu_t0 is None:
            sichtbar = _glatt(*T_TEILE, t)
        else:
            tz = time.monotonic() - self._zu_t0
            sichtbar = 1.0 - _glatt(0.0, T_ZU_TEILE, tz)
            if not self._sprung_gesendet and tz >= T_SPRUNG_START:
                self._sprung_gesendet = True
                self.zu_beginnt.emit()
            if tz >= max(T_ZU_DIMMEN[1], T_SPRUNG_START + T_SPRUNG) + 0.05:
                self._takt.stop()
                self.close()
                return
        for eff in self._effekte:
            eff.setOpacity(sichtbar)
            w = eff.parent()
            if sichtbar > 0.01 and not w.isVisible():
                w.show()
            elif sichtbar <= 0.01 and w.isVisible():
                w.hide()
        if self._zu_t0 is not None and sichtbar < 0.5:
            for k in self.kacheln.values():
                k.hide()
        self._wippen(t)
        self.update()
        # nach dem Aufbau reicht ein ruhigerer Takt fürs Wippen
        soll = 33 if (self._zu_t0 is None and t > T_TEILE[1] + 0.1) else 16
        if self._takt.interval() != soll:
            self._takt.setInterval(soll)

    def schliessen(self, grund: str = "Fertig") -> None:
        if self._zu_t0 is not None:
            return
        log.info("Einrichten schließen (%s)", grund)
        self._zu_t0 = time.monotonic()
        self._takt.setInterval(16)
        for k in self.kategorien.values():
            k.offen = False

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.schliessen("Esc")
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e) -> None:  # noqa: N802
        self._takt.stop()
        self.geschlossen.emit()
        super().closeEvent(e)

    # --- Malen -------------------------------------------------------------------
    def _phasen(self) -> tuple[float, float]:
        t = self.jetzt()
        dimm = _glatt(0, T_DIMMEN, t)
        buehne = _glatt(*T_BUEHNE, t)
        if self._zu_t0 is not None:
            tz = time.monotonic() - self._zu_t0
            buehne *= 1 - _glatt(*T_ZU_BUEHNE, tz)
            dimm *= 1 - _glatt(*T_ZU_DIMMEN, tz)
        return dimm, buehne

    def paintEvent(self, _e) -> None:  # noqa: N802
        dimm, buehne = self._phasen()
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        farbe = QColor(ABDUNKELN)
        farbe.setAlpha(max(1, int(ABDUNKELN_ALPHA * dimm)))   # nie ganz 0: Klicks bleiben auf der Bühne
        p.fillRect(self.rect(), farbe)
        if buehne > 0.005:
            self._herkunft_malen(p, buehne)
            self._sockel_malen(p, buehne)
        p.end()

    def _herkunft_malen(self, p: QPainter, a: float) -> None:
        r = self.radius * (0.86 + 0.14 * a)
        c = self.mitte
        kreis = QRectF(c.x() - r, c.y() - r, 2 * r, 2 * r)
        p.save()
        p.setOpacity(a)
        # weicher Schein hinter dem Kreis
        schein = QRadialGradient(c, r * 1.25)
        schein.setColorAt(0.75, QColor(255, 255, 255, 60))
        schein.setColorAt(1.0, QColor(255, 255, 255, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(schein))
        p.drawEllipse(c, r * 1.25, r * 1.25)
        pfad = QPainterPath()
        pfad.addEllipse(kreis)
        p.setClipPath(pfad)
        misch = self._mischung()
        if self._herkunft_alt is not None and misch < 1.0:
            # Verwischen: der alte Hintergrund wird unscharf und blasst aus, der neue
            # kommt unscharf herein und wird in der zweiten Hälfte scharf.
            scharf_alt = max(0.0, 1.0 - 2 * misch)
            scharf_neu = max(0.0, 2 * misch - 1.0)
            zoom_alt, zoom_neu = 1.0 + 0.1 * misch, 1.1 - 0.1 * misch
            self._herkunft_fuellen(p, self._weich_alt, kreis, a * (1 - misch), zoom_alt)
            self._herkunft_fuellen(p, self._herkunft_alt, kreis, a * scharf_alt, zoom_alt)
            self._herkunft_fuellen(p, self._weich_neu, kreis, a * misch, zoom_neu)
            self._herkunft_fuellen(p, self._herkunft, kreis, a * scharf_neu, zoom_neu)
        else:
            self._herkunft_fuellen(p, self._herkunft, kreis, a, 1.0)
        p.setClipping(False)
        p.setPen(QPen(QColor(255, 255, 255, 200), 3))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(kreis)
        p.restore()

    @staticmethod
    def _weich(pm: QPixmap) -> QPixmap:
        """Unscharfe Fassung (klein rechnen, weich wieder hoch) – leer bleibt leer."""
        if pm.isNull():
            return pm
        klein = pm.scaled(max(1, pm.width() // 14), max(1, pm.height() // 14),
                          Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
        return klein.scaled(pm.width() // 2, pm.height() // 2, Qt.AspectRatioMode.IgnoreAspectRatio,
                            Qt.TransformationMode.SmoothTransformation)

    def herkunft_wechseln(self, pfad: Path | None) -> None:
        """Neuer Kobold: sein Hintergrund verwischt aus dem alten heraus (``T_MISCHEN``)."""
        neu = QPixmap(str(pfad)) if pfad else QPixmap()
        self._herkunft_alt, self._herkunft = self._herkunft, neu
        self._weich_alt, self._weich_neu = self._weich(self._herkunft_alt), self._weich(neu)
        self._misch_t0 = time.monotonic()
        self.update()

    def _mischung(self) -> float:
        """0 → nur alter Hintergrund, 1 → nur neuer (Wechsel abgeschlossen)."""
        if self._misch_t0 is None:
            return 1.0
        u = _glatt(0.0, T_MISCHEN, time.monotonic() - self._misch_t0)
        if u >= 1.0:
            self._misch_t0, self._herkunft_alt = None, None
        return u

    def _herkunft_fuellen(self, p: QPainter, pm: QPixmap, kreis: QRectF, deckkraft: float,
                          zoom: float) -> None:
        if deckkraft <= 0.003:
            return
        p.save()
        p.setOpacity(deckkraft)
        if not pm.isNull():
            s = max(kreis.width() / pm.width(), kreis.height() / pm.height()) * zoom
            ziel = QRectF(0, 0, pm.width() * s, pm.height() * s)
            ziel.moveCenter(kreis.center())
            p.drawPixmap(ziel, pm, QRectF(pm.rect()))
        else:
            g = QLinearGradient(kreis.topLeft(), kreis.bottomRight())
            g.setColorAt(0, QColor(stil.AKZENT_HELL))
            g.setColorAt(1, QColor(stil.AKZENT))
            p.fillRect(kreis, QBrush(g))
        p.restore()

    def _sockel_malen(self, p: QPainter, a: float) -> None:
        breite = self.radius * 1.15
        hoehe = breite * 0.2
        c = QPointF(self.mitte.x(), self.fuss_y + hoehe * 0.15)
        p.save()
        p.setOpacity(a)
        p.setPen(Qt.PenStyle.NoPen)
        # Schatten
        p.setBrush(QColor(0, 0, 0, 60))
        p.drawEllipse(QRectF(c.x() - breite / 2 - 6, c.y() + hoehe * 0.35, breite + 12, hoehe * 0.9))
        # Seitenwand
        g = QLinearGradient(c.x() - breite / 2, 0, c.x() + breite / 2, 0)
        g.setColorAt(0, QColor("#C9CEC9"))
        g.setColorAt(0.5, QColor("#E9EBE7"))
        g.setColorAt(1, QColor("#BFC5BF"))
        p.setBrush(QBrush(g))
        wand = QPainterPath()
        wand.addRoundedRect(QRectF(c.x() - breite / 2, c.y() - hoehe / 2 + hoehe * 0.35, breite, hoehe * 0.75),
                            hoehe / 2, hoehe / 2)
        p.drawPath(wand)
        # Oberseite
        p.setBrush(QColor(stil.GRUND))
        p.drawEllipse(QRectF(c.x() - breite / 2, c.y() - hoehe / 2, breite, hoehe))
        p.setPen(QPen(QColor(255, 255, 255, 220), 1.5))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(c.x() - breite / 2 + 1, c.y() - hoehe / 2 + 1, breite - 2, hoehe - 2))
        p.restore()

    # --- Anordnung ---------------------------------------------------------------
    def _kategorie_punkt(self, uhr: int) -> QPointF:
        w = math.radians(uhr * 30)
        r = self.radius + 18
        return QPointF(self.mitte.x() + math.sin(w) * r, self.mitte.y() - math.cos(w) * r)

    def teile_platzieren(self) -> None:
        c, r = self.mitte, self.radius
        s = self.schild
        s.move(int(c.x() - s.width() / 2), int(c.y() - r - s.height() - 14))
        f = self.fertig_knopf
        f.move(int(c.x() - f.width() / 2), int(self.fuss_y + r * 0.5))
        # Pfeile sitzen an den Enden des Sockels – nah genug, dass sie nie mit den
        # Kategorien bei 4 und 8 Uhr kollidieren, auch bei kleinem Kreis
        breite = self.radius * 1.15
        mitte_sockel = self.fuss_y + breite * 0.2 * 0.35
        for pf in self.pfeile:
            kreis_mitte_x = 4 + (PfeilKnopf.GROESSE - 8) / 2
            x = c.x() + pf.richtung * (breite / 2 + 4) - kreis_mitte_x
            pf.move(int(x), int(mitte_sockel - 2 - (PfeilKnopf.GROESSE - 8) / 2))
        self._wippen(self.jetzt())
        self._kacheln_platzieren()

    def _wippen(self, t: float) -> None:
        for schluessel, _text, uhr, seite, freq, phase in KATEGORIEN:
            k = self.kategorien[schluessel]
            pt = self._kategorie_punkt(uhr)
            dy = math.sin(t * 2 * math.pi * freq + phase) * 4
            x = pt.x() - (k.width() - 24 if seite == "links" else 24)
            k.move(int(x), int(pt.y() - k.height() / 2 + dy))

    def _kacheln_platzieren(self) -> None:
        for seite, kachel in self.kacheln.items():
            lay = kachel.layout()
            lay.invalidate()
            lay.activate()
            # Höhe für die feste Breite (umbrechende Texte), aber nie kleiner als der Inhalt
            # verlangt – sonst wird die Kachel nach einem Inhaltswechsel zur flachen Pille.
            h = kachel.sizeHint().height()
            if lay.hasHeightForWidth():
                h = max(h, lay.totalHeightForWidth(kachel.width()))
            kachel.resize(kachel.width(), h)
            if seite == "links":
                rechts = min(k.x() for k in self.kategorien.values() if k in self._seite("links")) - 8
                x = max(8, rechts - kachel.width())
            else:
                links = max(k.x() + k.width() for k in self.kategorien.values() if k in self._seite("rechts")) + 8
                x = min(self.width() - kachel.width() - 8, links)
            y = int(max(8, min(self.mitte.y() - h / 2, self.height() - h - 8)))
            kachel.move(int(x), y)

    def _seite(self, seite: str) -> list[KategorieKnopf]:
        return [self.kategorien[s] for s, _t, _u, si, *_ in KATEGORIEN if si == seite]

    # --- Kategorien und Kacheln --------------------------------------------------
    def kategorie_umschalten(self, schluessel: str) -> None:
        log.info("Kategorie %s", schluessel)
        seite = next(si for s, _t, _u, si, *_ in KATEGORIEN if s == schluessel)
        kachel = self.kacheln[seite]
        if self.offen[seite] == schluessel:           # zweiter Klick schließt
            self.offen[seite] = None
            self.kategorien[schluessel].offen = False
            kachel.hide()
        else:
            if self.offen[seite]:
                self.kategorien[self.offen[seite]].offen = False
            self.offen[seite] = schluessel
            self.kategorien[schluessel].offen = True
            self.kachel_bauen(schluessel)
            kachel.show()
            kachel.raise_()
        for k in self.kategorien.values():
            k.update()
        self._kacheln_platzieren()

    def kachel_bauen(self, schluessel: str) -> None:
        seite = next(si for s, _t, _u, si, *_ in KATEGORIEN if s == schluessel)
        kachel = self.kacheln[seite]
        kachel.leeren()
        if seite == "rechts":
            self._adopt_liste = False
        titel = next(t for s, t, *_ in KATEGORIEN if s == schluessel)
        kachel.lay.addWidget(_label(titel, "titel"))
        getattr(self, f"_kachel_{schluessel}")(kachel.lay)
        self._kachel_gewechselt(kachel)

    def _kachel_gewechselt(self, kachel: Kachel) -> None:
        """Nach neuem Inhalt Größe anpassen. Neue Kinder einer sichtbaren Kachel zeigt Qt erst
        in der nächsten Runde der Ereignisschleife – vorher zählen sie nicht zur Höhe. Darum
        jetzt sichtbar machen (außer bewusst versteckte) und danach noch einmal messen."""
        if kachel.isVisible():
            for w in kachel.findChildren(QWidget):
                if not w.isVisible() and not w.testAttribute(Qt.WidgetAttribute.WA_WState_ExplicitShowHide):
                    w.show()
        kachel.adjustSize()
        self._kacheln_platzieren()
        QTimer.singleShot(0, self._kacheln_platzieren)

    def _neu_bauen(self, schluessel: str) -> None:
        if schluessel in self.offen.values():
            self.kachel_bauen(schluessel)

    # Tricks
    def _kachel_tricks(self, lay: QVBoxLayout) -> None:
        from .modulverwaltung import FEHLER, ZUSTIMMUNG

        v = self.d.verwaltung
        v.finden()
        if not v.tricks:
            lay.addWidget(_label("Noch keine Tricks da.", "neben"))
        for t in v.tricks.values():
            kopf_links = QVBoxLayout()
            kopf_links.setSpacing(2)
            name_zeile = QHBoxLayout()
            name_zeile.setSpacing(8)
            n = _label(t.anzeigename, wrap=False)
            n.setStyleSheet("font-weight: 700;")
            name_zeile.addWidget(n)
            marke = QLabel("Offiziell" if t.offiziell else
                           ("Fremd · Zustimmung nötig" if t.status == ZUSTIMMUNG else "Fremd"))
            marke.setObjectName("marke_offiziell" if t.offiziell else "marke_fremd")
            name_zeile.addWidget(marke)
            name_zeile.addStretch(1)
            kopf_links.addLayout(name_zeile)
            if t.beschreibung:
                kopf_links.addWidget(_label(t.beschreibung, "neben"))
            if t.status == FEHLER:
                kopf_links.addWidget(_label("Nach einem Fehler abgeschaltet. Schalter = neu versuchen.",
                                            "hinweis"))
            schalter = Kippschalter()
            schalter.setChecked(t.instanz is not None)
            schalter.toggled.connect(lambda an, name=t.name: self._trick_schalten(name, an))
            lay.addLayout(_zeile(kopf_links, schalter))
        beibringen = QPushButton("Neuen Trick beibringen")
        beibringen.clicked.connect(self._trick_beibringen)
        lay.addSpacing(4)
        lay.addWidget(beibringen)
        self._tricks_hinweis = _label("", "hinweis")
        self._tricks_hinweis.hide()
        lay.addWidget(self._tricks_hinweis)

    def _trick_schalten(self, name: str, an: bool) -> None:
        from .modulverwaltung import ZUSTIMMUNG

        v = self.d.verwaltung
        t = v.tricks.get(name)
        if t is None:
            return
        if an and not v.zugestimmt(t):
            self._zustimmung_fragen(name)
            return
        status = v.schalten(name, an)
        if an and status == ZUSTIMMUNG:
            self._zustimmung_fragen(name)
            return
        self._neu_bauen("tricks")

    def _zustimmung_fragen(self, name: str) -> None:
        t = self.d.verwaltung.tricks[name]
        kachel = self.kacheln["links"]
        kachel.leeren()
        kachel.lay.addWidget(_label("Zustimmung nötig", "titel"))
        kachel.lay.addWidget(_label(
            f"„{t.anzeigename}“ ist kein offizieller Trick. Er läuft mit vollen Rechten auf "
            "deinem PC – er könnte Dateien lesen oder verändern. Stimm nur zu, wenn du der "
            "Quelle vertraust. Ändert sich der Trick später, frage ich erneut."))
        ja = QPushButton("Zustimmen und einschalten")
        ja.setObjectName("haupt")
        ja.clicked.connect(lambda: (self.d.verwaltung.zustimmen(name), self._neu_bauen("tricks")))
        nein = QPushButton("Abbrechen")
        nein.clicked.connect(lambda: self._neu_bauen("tricks"))
        kachel.lay.addLayout(_zeile(nein, ja, stretch_index=-1))
        self._kachel_gewechselt(kachel)

    def _trick_beibringen(self) -> None:
        ordner = QFileDialog.getExistingDirectory(self, "Ordner mit dem Trick (modul.py) wählen")
        if not ordner:
            return
        try:
            t = self.d.verwaltung.beibringen(Path(ordner))
        except (ValueError, OSError) as fehler:
            self._neu_bauen("tricks")
            self._tricks_hinweis.setText(str(fehler))
            self._tricks_hinweis.show()
            return
        self._zustimmung_fragen(t.name)

    # Lautstärke
    def _kachel_lautstaerke(self, lay: QVBoxLayout) -> None:
        wert = round(float(self.d.einstellungen.get("lautstaerke", self.d.toene.lautstaerke)) * 100)
        regler = QSlider(Qt.Orientation.Horizontal)
        regler.setRange(0, 100)
        regler.setValue(wert)
        regler.setMinimumHeight(32)
        anzeige = QLabel(f"{wert} %")
        anzeige.setFixedWidth(52)
        anzeige.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        regler.valueChanged.connect(lambda v: anzeige.setText(f"{v} %"))
        regler.sliderReleased.connect(lambda: self._lautstaerke(regler.value()))
        regler.valueChanged.connect(lambda v: None if regler.isSliderDown() else self._lautstaerke(v))
        lay.addLayout(_zeile(regler, anzeige))
        lay.addWidget(_label("Was er von sich gibt, entscheidet er selbst.", "neben"))

    def _lautstaerke(self, wert: int) -> None:
        w = wert / 100
        self.d.einstellungen["lautstaerke"] = w
        self.d.lautstaerke_geaendert(w)
        self.d.toene.spielen("freuen")

    # Programme
    def _kachel_programme(self, lay: QVBoxLayout) -> None:
        lay.addWidget(_label("Bei diesen Programmen achtet er nicht auf Tippen und Maus.", "neben"))
        programme: dict = dict(self.d.einstellungen.get("programme", {}))
        if not programme:
            lay.addWidget(_label("Noch keine Programme eingetragen.", "neben"))
        for exe in sorted(programme):
            name = _label(exe, wrap=False)
            schalter = Kippschalter()
            schalter.setToolTip("Eingaben hier ignorieren")
            schalter.setChecked(bool(programme[exe].get("ignorieren", True)))
            schalter.toggled.connect(lambda an, e=exe: self._programm_setzen(e, an))
            weg = QPushButton("×")
            weg.setObjectName("klein")
            weg.setToolTip("Entfernen")
            weg.clicked.connect(lambda _=False, e=exe: self._programm_entfernen(e))
            lay.addLayout(_zeile(name, schalter, weg))
        vorschlaege = [p for p in self.d.zuletzt_programme() if p not in programme][:4]
        if vorschlaege:
            lay.addWidget(_label("Zuletzt benutzt – antippen zum Hinzufügen:", "neben"))
            zeile = QHBoxLayout()
            zeile.setSpacing(6)
            for p in vorschlaege:
                k = QPushButton(p.removesuffix(".exe"))
                k.setToolTip(p)
                k.setStyleSheet("min-height: 30px; padding: 0 10px; font-weight: 600;")
                k.clicked.connect(lambda _=False, e=p: self._programm_setzen(e, True))
                zeile.addWidget(k)
            zeile.addStretch(1)
            lay.addLayout(zeile)
        hinzu = QPushButton("Programm hinzufügen")
        hinzu.clicked.connect(self._programm_waehlen)
        lay.addWidget(hinzu)

    def _programm_setzen(self, exe: str, an: bool) -> None:
        programme = dict(self.d.einstellungen.get("programme", {}))
        programme[exe.lower()] = {"ignorieren": an}
        self.d.einstellungen["programme"] = programme
        self.d.programme_geaendert()
        self._neu_bauen("programme")

    def _programm_entfernen(self, exe: str) -> None:
        programme = dict(self.d.einstellungen.get("programme", {}))
        programme.pop(exe, None)
        self.d.einstellungen["programme"] = programme
        self.d.programme_geaendert()
        self._neu_bauen("programme")

    def _programm_waehlen(self) -> None:
        datei, _ = QFileDialog.getOpenFileName(self, "Programm wählen", "C:/Program Files",
                                               "Programme (*.exe)")
        if datei:
            self._programm_setzen(Path(datei).name, True)

    # System
    def _kachel_system(self, lay: QVBoxLayout) -> None:
        schalter = Kippschalter()
        schalter.setChecked(self.d.autostart_an())
        schalter.toggled.connect(lambda an: schalter.setChecked(self.d.autostart_setzen(an)))
        lay.addLayout(_zeile(_label("Mit Windows starten", wrap=False), schalter))
        updates = Kippschalter()
        updates.setChecked(self.d.update_pruefen_an())
        updates.toggled.connect(lambda an: updates.setChecked(self.d.update_pruefen_setzen(an)))
        self.update_schalter = updates
        lay.addLayout(_zeile(_label("Nach Updates suchen", wrap=False), updates))

        sichern = QPushButton("Daten sichern")
        sichern.clicked.connect(self._daten_sichern)
        laden = QPushButton("Daten laden")
        laden.clicked.connect(self._daten_laden_fragen)
        lay.addLayout(_zeile(sichern, laden, stretch_index=-1))
        self._system_hinweis = _label("", "neben")
        self._system_hinweis.hide()
        lay.addWidget(self._system_hinweis)

        andere = [a for a in self.d.avatare() if a[0] != self.d.aktueller_avatar]
        adoptieren = QPushButton("Anderen Kobold adoptieren")
        if not andere:
            adoptieren.setEnabled(False)
            adoptieren.setToolTip("Noch kein anderer Kobold da")
        adoptieren.clicked.connect(self._adoptieren_zeigen)
        lay.addWidget(adoptieren)

        lay.addSpacing(6)
        ueber = _label(f"DMNT-Kobold {self.d.version} · MIT-Lizenz", "neben", wrap=False)
        lay.addWidget(ueber)
        links = QHBoxLayout()
        repo = QPushButton("Quellcode")
        repo.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(REPO_URL)))
        links.addWidget(repo)
        neu = QPushButton("Was ist neu")
        neu.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(self.d.neuigkeiten_url)))
        links.addWidget(neu)
        links.addStretch(1)
        lay.addLayout(links)
        if KAFFEE_URL:                          # eigene Zeile, damit die Kachel schmal bleibt
            kaffee = QPushButton("Kauf mir nen Kaffee")
            kaffee.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(KAFFEE_URL)))
            lay.addLayout(_zeile(kaffee, stretch_index=-1))

    def _system_meldung(self, text: str) -> None:
        self._system_hinweis.setText(text)
        self._system_hinweis.show()
        self.kacheln["rechts"].adjustSize()
        self._kacheln_platzieren()

    def _daten_sichern(self) -> None:
        vorschlag = str(Path.home() / "Documents" / f"DMNT-Kobold-Sicherung-{date.today().isoformat()}.zip")
        datei, _ = QFileDialog.getSaveFileName(self, "Daten sichern", vorschlag, "Sicherung (*.zip)")
        if not datei:
            return
        try:
            self.d.sicherung.exportieren(Path(datei))
            self._system_meldung(f"Gesichert: {Path(datei).name}")
        except OSError as fehler:
            self._system_meldung(f"Sichern fehlgeschlagen: {fehler}")

    def _daten_laden_fragen(self) -> None:
        datei, _ = QFileDialog.getOpenFileName(self, "Sicherung laden", str(Path.home() / "Documents"),
                                               "Sicherung (*.zip)")
        if not datei:
            return
        kachel = self.kacheln["rechts"]
        kachel.leeren()
        self._adopt_liste = False
        kachel.lay.addWidget(_label("Daten laden?", "titel"))
        kachel.lay.addWidget(_label(
            f"Alle Erinnerungen, Tricks und Einstellungen werden durch „{Path(datei).name}“ ersetzt. "
            "Der jetzige Stand wird vorher automatisch gesichert."))
        ja = QPushButton("Laden")
        ja.setObjectName("haupt")
        ja.clicked.connect(lambda: self._daten_laden(Path(datei)))
        nein = QPushButton("Abbrechen")
        nein.clicked.connect(lambda: self._neu_bauen("system"))
        kachel.lay.addLayout(_zeile(nein, ja, stretch_index=-1))
        self._kachel_gewechselt(kachel)

    def _daten_laden(self, datei: Path) -> None:
        try:
            self.d.sicherung.importieren(datei)
            self.d.nach_import()
            self._neu_bauen("system")
            self._system_meldung("Geladen.")
        except (ValueError, OSError) as fehler:
            self._neu_bauen("system")
            self._system_meldung(f"Laden fehlgeschlagen: {fehler}")

    def _adoptieren_zeigen(self) -> None:
        kachel = self.kacheln["rechts"]
        kachel.leeren()
        self._adopt_liste = True
        kachel.lay.addWidget(_label("Anderen Kobold adoptieren", "titel"))
        for aid, name, portraet in self.d.avatare():
            bild = QLabel()
            if portraet and Path(portraet).exists():
                bild.setPixmap(QPixmap(str(portraet)).scaledToHeight(
                    56, Qt.TransformationMode.SmoothTransformation))
            bild.setFixedWidth(64)
            knopf = QPushButton("Wohnt hier" if aid == self.d.aktueller_avatar else "Adoptieren")
            knopf.setEnabled(aid != self.d.aktueller_avatar)
            knopf.setFixedWidth(118)                 # alle Knöpfe gleich breit, bündig
            knopf.clicked.connect(lambda _=False, a=aid: self._adoptieren(a))
            kachel.lay.addLayout(_zeile(bild, _label(name, wrap=False), knopf, stretch_index=1))
        zurueck = QPushButton("Zurück")
        zurueck.clicked.connect(lambda: self._neu_bauen("system"))
        kachel.lay.addWidget(zurueck)
        self._kachel_gewechselt(kachel)

    def _adoptieren(self, aid: str) -> None:
        self.avatar_wechseln_zu(aid)         # die Liste zeigt danach „Wohnt hier“ beim neuen

    # --- Kobold wechseln (Pfeile am Sockel) --------------------------------------
    def wechseln(self, richtung: int) -> None:
        """Vorheriger (-1) oder nächster (+1) Kobold, ringsum."""
        ids = [a[0] for a in self.d.avatare()]
        if len(ids) < 2:
            return
        i = ids.index(self.d.aktueller_avatar) if self.d.aktueller_avatar in ids else -1
        self.avatar_wechseln_zu(ids[(i + richtung) % len(ids)])

    def avatar_wechseln_zu(self, aid: str) -> bool:
        """Sofort wechseln: Avatar hüpft und blendet über, Hintergrund verwischt, Schild
        zeigt den Namen des neuen Kobolds. Während eines Wechsels gesperrt."""
        if aid == self.d.aktueller_avatar or self._zu_t0 is not None or time.monotonic() < self._wechsel_bis:
            return False
        ergebnis = self.d.avatar_wechseln(aid)
        if ergebnis is None:
            log.warning("Kein Wechsel zu %s (lädt nicht oder ein Wechsel läuft noch)", aid)
            return False
        standardname, herkunft = ergebnis
        self._wechsel_bis = time.monotonic() + T_WECHSEL
        self.d.aktueller_avatar, self.d.avatar_name, self.d.herkunft = aid, standardname, herkunft
        self.herkunft_wechseln(herkunft)
        self.schild.name_setzen(kobold_name(self.d.einstellungen, aid, standardname))
        self.teile_platzieren()
        if self._adopt_liste and self.offen["rechts"] == "system":   # „Wohnt hier“ wandert mit
            self._adoptieren_zeigen()
        elif self.offen["rechts"] == "system":
            self._neu_bauen("system")
        log.info("Kobold gewechselt: %s", aid)
        return True

    def _umbenennen(self, name: str) -> None:
        kobold_benennen(self.d.einstellungen, self.d.aktueller_avatar, name)
        self.d.umbenannt(name)

    def mousePressEvent(self, e) -> None:  # noqa: N802
        # Klick daneben: offene Kacheln zu
        for seite, schluessel in list(self.offen.items()):
            if schluessel and not self.kacheln[seite].geometry().contains(e.position().toPoint()):
                self.kategorie_umschalten(schluessel)
        super().mousePressEvent(e)
