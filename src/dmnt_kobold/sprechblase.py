"""Sprechblase: der gemeinsame Ausgabekanal aller Module.

Weiße Karte mit Zipfel zum Avatar, Text 15 px, bis zu zwei Knöpfe
(Hauptknopf Salbeigrün, Nebenknopf weiß mit Rand). Klick auf die Karte
selbst schließt sie. Das Fenster stiehlt nie den Fokus.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from .menue import schriftart

RAND = 10          # Platz für den Schatten
ZIPFEL = 10        # Höhe des Zipfels
RADIUS = 16
MAX_TEXTBREITE = 260
ABSTAND_KOPF = 6

AKZENT = "#2F6F5E"
AKZENT_DUNKEL = "#265B4D"
TEXT = "#1D2320"


def _knopf_stil(haupt: bool) -> str:
    if haupt:
        return (f"QPushButton {{ background: {AKZENT}; color: #FFFFFF; border: none;"
                f" border-radius: 10px; padding: 0 16px; min-height: 40px; font-weight: 600; }}"
                f" QPushButton:hover {{ background: {AKZENT_DUNKEL}; }}")
    return ("QPushButton { background: #FFFFFF; color: #1D2320; border: 1px solid #C9CEC9;"
            " border-radius: 10px; padding: 0 16px; min-height: 40px; font-weight: 600; }"
            " QPushButton:hover { background: #E3EFEA; }")


class Sprechblase(QWidget):
    knopf_gedrueckt = Signal(int, str)
    weggeklickt = Signal(int)

    def __init__(self) -> None:
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
        self.setWindowTitle("DMNT-Kobold Sprechblase")
        self.wunsch_id: int | None = None
        self._zipfel_x = 40.0
        self._zipfel_unten = True

        self._layout = QVBoxLayout(self)
        self._layout.setSpacing(12)
        self._text = QLabel(self)
        self._text.setWordWrap(True)
        self._text.setStyleSheet(
            f"color: {TEXT}; font-family: '{schriftart()}'; font-size: 15px; background: transparent;")
        self._text.setMaximumWidth(MAX_TEXTBREITE)
        self._layout.addWidget(self._text)
        self._knopfzeile = QHBoxLayout()
        self._knopfzeile.setSpacing(8)
        self._layout.addLayout(self._knopfzeile)
        self._raender()

    # --- Inhalt ----------------------------------------------------------------
    def zeige(self, wunsch_id: int, text: str, knoepfe: tuple[str, ...]) -> None:
        self.wunsch_id = wunsch_id
        self._text.setText(text)
        while self._knopfzeile.count():
            w = self._knopfzeile.takeAt(0).widget()
            if w is not None:
                w.hide()
                w.setParent(None)
                w.deleteLater()
        if knoepfe:
            self._knopfzeile.addStretch(1)
        for i, beschriftung in enumerate(knoepfe):
            k = QPushButton(beschriftung, self)
            k.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            k.setCursor(Qt.CursorShape.PointingHandCursor)
            k.setStyleSheet(_knopf_stil(haupt=(i == 0)) + f" QPushButton {{ font-family: '{schriftart()}';"
                            " font-size: 14px; }")
            k.clicked.connect(lambda _=False, b=beschriftung: self._geklickt(b))
            self._knopfzeile.addWidget(k)
        # Textbreite festlegen, damit der Zeilenumbruch die Höhe richtig bestimmt
        self._text.ensurePolished()
        fm = QFontMetrics(self._text.font())
        breite = min(MAX_TEXTBREITE, fm.horizontalAdvance(text) + 4)
        knopf_breite = sum(self._knopfzeile.itemAt(i).sizeHint().width()
                           for i in range(self._knopfzeile.count())) + 8
        self._text.setFixedWidth(max(breite, min(knopf_breite, MAX_TEXTBREITE), 120))
        self._text.setFixedHeight(self._text.heightForWidth(self._text.width()))
        self._layout.activate()
        self.adjustSize()
        self.show()

    def verstecke(self) -> None:
        self.wunsch_id = None
        self.hide()

    def _geklickt(self, beschriftung: str) -> None:
        if self.wunsch_id is not None:
            self.knopf_gedrueckt.emit(self.wunsch_id, beschriftung)

    def mouseReleaseEvent(self, e) -> None:  # noqa: N802
        if e.button() == Qt.MouseButton.LeftButton and self.wunsch_id is not None:
            self.weggeklickt.emit(self.wunsch_id)

    # --- Lage --------------------------------------------------------------------
    def _raender(self) -> None:
        unten = RAND + 14 + (ZIPFEL if self._zipfel_unten else 0)
        oben = RAND + 14 + (0 if self._zipfel_unten else ZIPFEL)
        self._layout.setContentsMargins(RAND + 18, oben, RAND + 18, unten)

    def platzieren(self, anker_x: float, kopf_y: float, fuss_y: float,
                   bereich: tuple[float, float, float, float]) -> None:
        """Über den Kopf setzen; passt es oben nicht, unter den Fuss.
        ``bereich`` = (links, oben, rechts, unten) des Monitors (verfügbar)."""
        links, oben, rechts, unten = bereich
        w, h = self.width(), self.height()
        zipfel_unten = kopf_y - ABSTAND_KOPF - h >= oben
        if zipfel_unten != self._zipfel_unten:
            self._zipfel_unten = zipfel_unten
            self._raender()
            self.adjustSize()
            w, h = self.width(), self.height()
        y = kopf_y - ABSTAND_KOPF - h + RAND if zipfel_unten else fuss_y + ABSTAND_KOPF - RAND
        y = max(oben - RAND, min(y, unten - h + RAND))
        x = anker_x - w / 2
        x = max(links - RAND, min(x, rechts - w + RAND))
        self._zipfel_x = max(RAND + RADIUS + 8, min(anker_x - x, w - RAND - RADIUS - 8))
        neu = (round(x), round(y))
        if (self.x(), self.y()) != neu:
            self.move(*neu)
        self.update()

    # --- Zeichnen ------------------------------------------------------------------
    def _form(self) -> QPainterPath:
        w, h = self.width(), self.height()
        if self._zipfel_unten:
            karte = QRectF(RAND, RAND, w - 2 * RAND, h - 2 * RAND - ZIPFEL)
        else:
            karte = QRectF(RAND, RAND + ZIPFEL, w - 2 * RAND, h - 2 * RAND - ZIPFEL)
        pfad = QPainterPath()
        pfad.addRoundedRect(karte, RADIUS, RADIUS)
        z = QPainterPath()
        zx = self._zipfel_x
        if self._zipfel_unten:
            z.moveTo(zx - 9, karte.bottom() - 1)
            z.lineTo(zx, karte.bottom() + ZIPFEL)
            z.lineTo(zx + 9, karte.bottom() - 1)
        else:
            z.moveTo(zx - 9, karte.top() + 1)
            z.lineTo(zx, karte.top() - ZIPFEL)
            z.lineTo(zx + 9, karte.top() + 1)
        z.closeSubpath()
        return pfad.united(z).simplified()

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        form = self._form()
        # weicher Schatten aus mehreren Lagen
        for i, alpha in enumerate((10, 8, 6, 4)):
            p.save()
            p.translate(0, 2 + i * 0.6)
            p.setPen(QPen(QColor(20, 35, 30, alpha), 2 + i * 2.2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(form)
            p.restore()
        p.setPen(QPen(QColor("#E3E6E1"), 1))
        p.setBrush(QColor("#FFFFFF"))
        p.drawPath(form)
        p.end()

    def zipfelspitze(self) -> QPointF:
        """Für Tests: globale Position der Zipfelspitze."""
        y = self.height() - RAND if self._zipfel_unten else RAND
        return QPointF(self.x() + self._zipfel_x, self.y() + y)
