"""Platzhalter-Avatar „Blob", gezeichnet mit QPainter.

Lokale Koordinaten: Fusspunkt = (0, 0), Körper reicht bis y = -HOEHE.
Stauchen/Strecken und Spiegeln passieren als Transformation um den Fusspunkt.

Ausdrücke:
  augen: "offen" | "zu" | "froh" | "gross"
  mund:  "laecheln" | "offen" | "o" | "klein"
  blick: (dx, dy) Pupillenversatz in Pixeln (lokal, vor dem Spiegeln)
  zzz:   kleine „z“ über dem Kopf (schlafen)
"""
from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
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
ZZZ = QColor("#4A534E")

_KOERPER_PFAD: QPainterPath | None = None
_INNEN: QPainterPath | None = None


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


def _innen_ellipse() -> QPainterPath:
    """Heller Bereich, der von der Schattenseite ausgespart wird."""
    global _INNEN
    if _INNEN is None:
        _INNEN = QPainterPath()
        _INNEN.addEllipse(QRectF(-44, -88, 76, 82))
    return _INNEN


def transformation(fuss: QPointF, sx: float, sy: float, richtung: int) -> QTransform:
    t = QTransform()
    t.translate(fuss.x(), fuss.y())
    t.scale(sx * (1 if richtung >= 0 else -1), sy)
    return t


def schatten_rechteck(fuss: QPointF, sx: float) -> QRectF:
    w = BREITE * 0.86 * sx
    return QRectF(fuss.x() - w / 2, fuss.y() - 5, w, 10)


def zzz_rechteck(fuss: QPointF) -> QRectF:
    return QRectF(fuss.x() + 26, fuss.y() - HOEHE - 34, 34, 34)


def _augen(p: QPainter, augen: str, blick: tuple[float, float]) -> None:
    bx, by = blick
    for ax in (-13.0, 16.0):
        if augen in ("zu", "froh"):
            p.setPen(QPen(AUGE, 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.setBrush(Qt.BrushStyle.NoBrush)
            bogen = QPainterPath()
            if augen == "zu":
                bogen.moveTo(ax - 5, -52)
                bogen.quadTo(ax, -48, ax + 5, -52)
            else:
                bogen.moveTo(ax - 5, -50)
                bogen.quadTo(ax, -58, ax + 5, -50)
            p.drawPath(bogen)
            continue
        gross = augen == "gross"
        w, h = (12.0, 15.0) if gross else (9.0, 12.0)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(AUGE)
        p.drawEllipse(QRectF(ax - w / 2 + bx, -53 - h / 2 + by, w, h))
        p.setBrush(QColor("#FFFFFF"))
        g = 4.2 if gross else 3.4
        p.drawEllipse(QRectF(ax - 0.5 + bx * 1.2, -57 + by - (1 if gross else 0), g, g))


def _mund(p: QPainter, mund: str) -> None:
    if mund == "offen":
        p.setPen(QPen(AUGE, 1.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        p.setBrush(AUGE)
        m = QPainterPath()
        m.moveTo(-5, -42)
        m.quadTo(2, -30, 9, -42)
        m.closeSubpath()
        p.drawPath(m)
        return
    if mund == "o":
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(AUGE)
        p.drawEllipse(QRectF(-1, -42, 6, 7))
        return
    p.setPen(QPen(AUGE, 2.4, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
    p.setBrush(Qt.BrushStyle.NoBrush)
    m = QPainterPath()
    if mund == "klein":
        m.moveTo(0, -39)
        m.quadTo(2, -37.5, 5, -39)
    else:
        m.moveTo(-4, -41)
        m.quadTo(2, -35, 8, -41)
    p.drawPath(m)


def zeichne(p: QPainter, fuss: QPointF, sx: float = 1.0, sy: float = 1.0, richtung: int = 1,
            augen: str = "offen", mund: str = "laecheln", blick: tuple[float, float] = (0.0, 0.0),
            zzz: bool = False, schatten: bool = True) -> None:
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    if schatten:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, int(255 * 0.18)))
        p.drawEllipse(schatten_rechteck(fuss, sx))

    if zzz:
        f = QFont("Segoe UI")
        f.setBold(True)
        r = zzz_rechteck(fuss)
        farbe = QColor(ZZZ)
        farbe.setAlphaF(0.75)
        p.setPen(farbe)
        f.setPixelSize(12)
        p.setFont(f)
        p.drawText(QPointF(r.left() + 2, r.bottom() - 4), "z")
        f.setPixelSize(16)
        p.setFont(f)
        p.drawText(QPointF(r.left() + 13, r.top() + 18), "z")

    p.setTransform(transformation(fuss, sx, sy, richtung), True)
    koerper = koerper_pfad()

    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(KOERPER)
    p.drawPath(koerper)

    schatten_form = QPainterPath()
    schatten_form.addEllipse(QRectF(-8, -70, 74, 84))
    seite = QColor(SCHATTENSEITE)
    seite.setAlphaF(0.5)
    p.setBrush(seite)
    p.drawPath(koerper.intersected(schatten_form).subtracted(_innen_ellipse()))

    wange = QColor(WANGE)
    wange.setAlphaF(0.6)
    p.setBrush(wange)
    p.drawEllipse(QRectF(-31, -42, 13, 8))
    p.drawEllipse(QRectF(21, -42, 13, 8))

    _augen(p, augen, blick)
    _mund(p, mund)
    p.restore()


def maske(fuss: QPointF, sx: float, sy: float, richtung: int, schatten: bool = True,
          zzz: bool = False) -> QRegion:
    """Klickbarer Bereich: Körper (+3 px Rand für Kantenglättung), Schatten, zzz."""
    pfad = transformation(fuss, sx, sy, richtung).map(koerper_pfad())
    stroker = QPainterPathStroker()
    stroker.setWidth(6)
    pfad = pfad.united(stroker.createStroke(pfad))
    if schatten:
        s = QPainterPath()
        s.addEllipse(schatten_rechteck(fuss, sx).adjusted(-1, -1, 1, 1))
        pfad = pfad.united(s)
    region = QRegion(pfad.toFillPolygon().toPolygon())
    if zzz:
        region = region.united(QRegion(zzz_rechteck(fuss).toAlignedRect()))
    return region


def icon(groesse: int = 64) -> QIcon:
    ergebnis = QIcon()
    for g in (16, 24, 32, 48, groesse):
        pm = QPixmap(g, g)
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        faktor = g / (HOEHE + 8)
        fuss = QPointF(g / 2, g - 3 * faktor)
        zeichne(p, fuss, faktor, faktor, 1, schatten=False)
        p.end()
        ergebnis.addPixmap(pm)
    return ergebnis
