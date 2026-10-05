"""Bausteine für eigene Oberflächen von Tricks: schwebende Karte, Kippschalter.

Eine ``Karte`` ist ein rahmenloses, immer obenliegendes Fenster mit weißer,
abgerundeter Fläche und weichem Schatten (Stil wie die Sprechblase).
"""
from __future__ import annotations

from PySide6.QtCore import QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath
from PySide6.QtWidgets import QAbstractButton, QVBoxLayout, QWidget

from . import stil

SCHATTEN = 14
RADIUS = 18


def schatten_karte_malen(p: QPainter, flaeche: QRectF, radius: float = RADIUS,
                         schatten: int = SCHATTEN, farbe: str = stil.FLAECHE) -> None:
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    for i in range(schatten, 0, -2):
        a = int(26 * (1 - i / schatten) ** 2) + 2
        p.setBrush(QColor(20, 35, 30, a))
        p.drawRoundedRect(flaeche.adjusted(-i * 0.6, -i * 0.3, i * 0.6, i), radius + i * 0.6, radius + i * 0.6)
    p.setBrush(QColor(farbe))
    p.drawRoundedRect(flaeche, radius, radius)


class Karte(QWidget):
    """Schwebende Karte. Inhalt in ``self.inhalt`` (QVBoxLayout) einhängen."""

    geschlossen = Signal()

    def __init__(self, breite: int = 360, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool
                            | Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.NoDropShadowWindowHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(stil.bedien_stylesheet())
        self.setFixedWidth(breite + 2 * SCHATTEN)
        self.inhalt = QVBoxLayout(self)
        self.inhalt.setContentsMargins(SCHATTEN + 20, SCHATTEN + 18, SCHATTEN + 20, SCHATTEN + 20)
        self.inhalt.setSpacing(10)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        r = QRectF(self.rect()).adjusted(SCHATTEN, SCHATTEN * 0.6, -SCHATTEN, -SCHATTEN)
        schatten_karte_malen(p, r)
        p.end()

    def zeigen_bei(self, punkt: QPoint | None = None) -> None:
        """Zeigt die Karte zentriert über ``punkt`` (oder Bildschirmmitte), im Bild gehalten."""
        self.adjustSize()
        screen = QGuiApplication.screenAt(punkt) if punkt else QGuiApplication.primaryScreen()
        screen = screen or QGuiApplication.primaryScreen()
        v = screen.availableGeometry()
        if punkt is None:
            punkt = v.center() + QPoint(0, self.height() // 2)
        x = punkt.x() - self.width() // 2
        y = punkt.y() - self.height()
        x = max(v.left(), min(x, v.right() - self.width()))
        y = max(v.top(), min(y, v.bottom() - self.height()))
        self.move(x, y)
        self.show()
        self.raise_()
        self.activateWindow()

    def keyPressEvent(self, e) -> None:  # noqa: N802
        if e.key() == Qt.Key.Key_Escape:
            self.close()
        else:
            super().keyPressEvent(e)

    def closeEvent(self, e) -> None:  # noqa: N802
        self.geschlossen.emit()
        super().closeEvent(e)


class Kippschalter(QAbstractButton):
    """An/Aus-Schalter (44 × 26) im Stil der Kacheln."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedSize(QSize(44, 26))

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(44, 26)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        an = self.isChecked()
        farbe = QColor(stil.AKZENT if an else "#C9CEC9")
        if not self.isEnabled():
            farbe = QColor("#E3E5E1")
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(farbe)
        r = QRectF(1, 1, 42, 24)
        pfad = QPainterPath()
        pfad.addRoundedRect(r, 12, 12)
        p.drawPath(pfad)
        p.setBrush(QColor("white"))
        x = 21 if an else 3
        p.drawEllipse(QRectF(x, 3, 20, 20))
        p.end()
