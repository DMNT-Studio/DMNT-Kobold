"""Platzhalter-Avatar „Blob", gezeichnet mit QPainter.

Lokale Koordinaten: Fusspunkt = (0, 0), Körper reicht bis y = -HOEHE.
Stauchen/Strecken und Spiegeln passieren als Transformation um den Fusspunkt.
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QIcon,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QPixmap,
    QRegion,
    QTransform,
)

BREITE = 96.0
HOEHE = 92.0

KOERPER = QColor("#F2B66D")
SCHATTENSEITE = QColor("#E59E4D")
AUGE = QColor("#1D2320")
WANGE = QColor("#EE9A86")

_KOERPER_PFAD: QPainterPath | None = None


def koerper_pfad() -> QPainterPath:
    """Tropfen-/Bogenform, symmetrisch, Fuss bei y = 0."""
    global _KOERPER_PFAD
    if _KOERPER_PFAD is None:
        b = BREITE / 2
        p = QPainterPath()
        p.moveTo(-b, -2)
        p.cubicTo(-b - 4, -34, -38, -HOEHE, 0, -HOEHE)
        p.cubicTo(38, -HOEHE, b + 4, -34, b, -2)
        p.cubicTo(b - 10, 2, -b + 10, 2, -b, -2)
        p.closeSubpath()
        _KOERPER_PFAD = p
    return _KOERPER_PFAD


def transformation(fuss: QPointF, sx: float, sy: float, richtung: int) -> QTransform:
    t = QTransform()
    t.translate(fuss.x(), fuss.y())
    t.scale(sx * (1 if richtung >= 0 else -1), sy)
    return t


def schatten_rechteck(fuss: QPointF, sx: float) -> QRectF:
    w = BREITE * 0.86 * sx
    return QRectF(fuss.x() - w / 2, fuss.y() - 5, w, 10)


def zeichne(p: QPainter, fuss: QPointF, sx: float = 1.0, sy: float = 1.0,
            richtung: int = 1, augen_zu: bool = False, schatten: bool = True) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if schatten:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(255 * 0.18)))
        p.drawEllipse(schatten_rechteck(fuss, sx))

    p.setTransform(transformation(fuss, sx, sy, richtung), True)
    koerper = koerper_pfad()

    # Körper
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(KOERPER)
    p.drawPath(koerper)

    # Schattenseite (hinten-unten, 50 %)
    schatten_form = QPainterPath()
    schatten_form.addEllipse(QRectF(-8, -70, 74, 84))
    seite = QColor(SCHATTENSEITE)
    seite.setAlphaF(0.5)
    p.setBrush(seite)
    p.drawPath(koerper.intersected(schatten_form).subtracted(_innen_ellipse()))

    # Wangen (60 %)
    wange = QColor(WANGE)
    wange.setAlphaF(0.6)
    p.setBrush(wange)
    p.drawEllipse(QRectF(-31, -42, 13, 8))
    p.drawEllipse(QRectF(21, -42, 13, 8))

    # Augen (leicht in Blickrichtung versetzt)
    for ax in (-13.0, 16.0):
        if augen_zu:
            pen = QPen(AUGE, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            bogen = QPainterPath()
            bogen.moveTo(ax - 5, -52)
            bogen.quadTo(ax, -48, ax + 5, -52)
            p.drawPath(bogen)
        else:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(AUGE)
            p.drawEllipse(QRectF(ax - 4.5, -59, 9, 12))
            p.setBrush(QColor("#FFFFFF"))
            p.drawEllipse(QRectF(ax - 0.5, -57, 3.4, 3.4))

    # Lächeln
    pen = QPen(AUGE, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    p.setBrush(Qt.BrushStyle.NoBrush)
    mund = QPainterPath()
    mund.moveTo(-4, -41)
    mund.quadTo(2, -35, 8, -41)
    p.drawPath(mund)

    p.restore()


_INNEN: QPainterPath | None = None


def _innen_ellipse() -> QPainterPath:
    """Heller Bereich, der von der Schattenseite ausgespart wird."""
    global _INNEN
    if _INNEN is None:
        _INNEN = QPainterPath()
        _INNEN.addEllipse(QRectF(-44, -88, 76, 82))
    return _INNEN


def maske(fuss: QPointF, sx: float, sy: float, richtung: int, schatten: bool = True) -> QRegion:
    """Klickbarer Bereich: Körper (+3 px Rand für Kantenglättung) und Schatten."""
    pfad = transformation(fuss, sx, sy, richtung).map(koerper_pfad())
    stroker = QPainterPathStroker()
    stroker.setWidth(6)
    pfad = pfad.united(stroker.createStroke(pfad))
    if schatten:
        s = QPainterPath()
        s.addEllipse(schatten_rechteck(fuss, sx).adjusted(-1, -1, 1, 1))
        pfad = pfad.united(s)
    return QRegion(pfad.toFillPolygon().toPolygon())


def icon(groesse: int = 64) -> QIcon:
    ergebnis = QIcon()
    for g in (16, 24, 32, 48, groesse):
        pm = QPixmap(g, g)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        faktor = g / (HOEHE + 8)
        fuss = QPointF(g / 2, g - 3 * faktor)
        zeichne(p, fuss, faktor, faktor, 1, False, schatten=False)
        p.end()
        ergebnis.addPixmap(pm)
    return ergebnis
