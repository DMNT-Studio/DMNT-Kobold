"""Effekt-Ebene: was über dem Kopf schwebt (z z Z Z, Noten, Sterne, Dampf …).

Zwei Ebenen: der Avatar (eigenes Fenster, Maske = Körperform) und die Effekte
(``EffektFenster``, komplett durchklickbar). Ein Effekt hängt am Kopf des aktuellen
Frames, läuft in seiner eigenen Schleife und ist unabhängig von der Körper-Animation.

Woher ein Effekt kommt:
  • Zuordnung zur sichtbaren Animation (Bauplan ``effekte.zuordnung``, sonst
    ``STANDARD_ZUORDNUNG``, z. B. schlafen → zzz)
  • Regel-Aktion „effekt“ (solange der Wunsch läuft – hat Vorrang)

Eingebaute Effekte werden gezeichnet (kein Bild nötig). Eigene Effekte eines Avatars sind
Bildfolgen (PNG) in ``effekte/<name>/``, im Editor angelegt.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRect, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen, QPixmap, QPolygonF
from PySide6.QtWidgets import QWidget

#: Eingebaute Effekte: Name → Beschreibung
EINGEBAUT: dict[str, str] = {
    "zzz": "z z Z Z steigt auf (Schlafen)",
    "noten": "Noten schweben hoch (Musik, gute Laune)",
    "sterne": "Sterne kreisen um den Kopf (schwindelig)",
    "dampf": "Dampfwolken steigen auf (Wut)",
    "herzchen": "Herzchen steigen auf",
    "fragezeichen": "Fragezeichen über dem Kopf",
    "ausrufezeichen": "Ausrufezeichen springt hoch (Schreck)",
}
#: Gilt für jeden Avatar, solange sein Bauplan nichts anderes sagt ("" = kein Effekt)
STANDARD_ZUORDNUNG: dict[str, str] = {"schlafen": "zzz"}

FENSTER_B, FENSTER_H = 220, 180          # Effekt-Fenster, Kopf sitzt unten in der Mitte
KOPF_X, KOPF_Y = FENSTER_B / 2, FENSTER_H - 30
NAME_MUSTER = r"[a-z0-9_]+"

GRAPHIT = QColor("#4A534E")
AKZENT = QColor("#2F6F5E")
GOLD = QColor("#E8B931")
ROSA = QColor("#D9546A")
DAMPF = QColor("#8A938E")


@dataclass
class EigenerEffekt:
    """Bildfolge aus dem Avatar-Ordner."""
    bilder: list[QPixmap]
    fps: float = 8.0
    breite: float = 40.0                 # logische Pixel
    hoehe_ueber_kopf: float = 6.0        # Abstand Unterkante → Kopf
    extra: dict = field(default_factory=dict)


def zuordnung(eigene: dict[str, str] | None) -> dict[str, str]:
    """Standard + Bauplan des Avatars ("" im Bauplan schaltet einen Standard ab)."""
    z = dict(STANDARD_ZUORDNUNG)
    z.update({k: v for k, v in (eigene or {}).items() if isinstance(v, str)})
    return {k: v for k, v in z.items() if v}


def bekannt(name: str, eigene: dict | None = None) -> bool:
    return name in EINGEBAUT or name in (eigene or {})


# --- Zeichnen (Ursprung = Mitte der Kopfoberkante, y nach oben negativ) -------------------

def _huelle(u: float) -> float:
    """Ein- und Ausblenden über einen Durchlauf (0 → 1 → 0)."""
    return max(0.0, min(1.0, u * 5.0, (1.0 - u) * 3.0))


def _text(p: QPainter, text: str, x: float, y: float, px: float, farbe: QColor, alpha: float,
          winkel: float = 0.0, familie: str = "Segoe UI") -> None:
    if alpha <= 0.01 or px < 1:
        return
    f = QFont(familie)
    f.setBold(True)
    f.setPixelSize(max(1, round(px)))
    p.save()
    p.translate(x, y)
    if winkel:
        p.rotate(winkel)
    c = QColor(farbe)
    c.setAlphaF(max(0.0, min(1.0, alpha)) * farbe.alphaF())
    p.setPen(c)
    p.setFont(f)
    p.drawText(QRectF(-px, -px, 2 * px, 2 * px), Qt.AlignmentFlag.AlignCenter, text)
    p.restore()


def _stern(p: QPainter, x: float, y: float, r: float, alpha: float, drehung: float) -> None:
    punkte = []
    for i in range(10):
        w = math.radians(drehung + i * 36 - 90)
        rr = r if i % 2 == 0 else r * 0.45
        punkte.append(QPointF(x + math.cos(w) * rr, y + math.sin(w) * rr))
    fuell, rand = QColor(GOLD), QColor("#B8891A")
    fuell.setAlphaF(alpha)
    rand.setAlphaF(alpha)
    p.setPen(QPen(rand, max(0.8, r * 0.12)))
    p.setBrush(fuell)
    p.drawPolygon(QPolygonF(punkte))


def _herz(p: QPainter, x: float, y: float, g: float, alpha: float) -> None:
    pfad = QPainterPath()
    pfad.moveTo(x, y + g * 0.35)
    pfad.cubicTo(x - g * 0.9, y - g * 0.25, x - g * 0.35, y - g * 0.95, x, y - g * 0.4)
    pfad.cubicTo(x + g * 0.35, y - g * 0.95, x + g * 0.9, y - g * 0.25, x, y + g * 0.35)
    c = QColor(ROSA)
    c.setAlphaF(alpha)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(c)
    p.drawPath(pfad)


def _zzz(p: QPainter, t: float, s: float, r: int) -> None:
    periode = 2.4
    for k in range(3):
        u = ((t + k * periode / 3) % periode) / periode
        x = r * (12 + 36 * u + math.sin(u * 6.0) * 3) * s
        _text(p, "Z" if u > 0.5 else "z", x, (-6 - 74 * u) * s, (10 + 12 * u) * s, GRAPHIT, _huelle(u))


def _noten(p: QPainter, t: float, s: float, r: int) -> None:
    periode = 2.2
    for k, zeichen in enumerate(("♪", "♫", "♪")):
        u = ((t + k * periode / 3) % periode) / periode
        x = r * (-16 + k * 16 + math.sin(u * 2 * math.pi + k) * 7) * s
        _text(p, zeichen, x, (-8 - 66 * u) * s, 17 * s, AKZENT, _huelle(u),
              winkel=math.sin(u * 5 + k) * 12, familie="Segoe UI Symbol")


def _sterne(p: QPainter, t: float, s: float, _r: int) -> None:
    n = 4
    sterne = []
    for k in range(n):
        w = t * 2.6 + k * 2 * math.pi / n
        vorne = math.sin(w)
        sterne.append((vorne, math.cos(w) * 30 * s, (-8 + vorne * 8) * s, (5 + vorne) * s, w))
    for vorne, x, y, g, w in sorted(sterne):            # hintere zuerst, blasser
        _stern(p, x, y, g, 0.45 + 0.55 * (vorne + 1) / 2, math.degrees(w) * 0.6)


def _dampf(p: QPainter, t: float, s: float, _r: int) -> None:
    p.setPen(Qt.PenStyle.NoPen)
    for seite in (-1, 1):
        for k in range(3):
            u = (t / 1.6 + k / 3 + (0.15 if seite > 0 else 0)) % 1.0
            x = seite * (16 + 16 * u) * s
            y = (-2 - 44 * u) * s
            rad = (4 + 10 * u) * s
            c = QColor(DAMPF)
            c.setAlphaF(0.75 * (1 - u) * min(1.0, u * 6))
            p.setBrush(c)
            p.drawEllipse(QPointF(x, y), rad, rad * 0.85)


def _herzchen(p: QPainter, t: float, s: float, r: int) -> None:
    periode = 2.6
    for k in range(2):
        u = ((t + k * periode / 2) % periode) / periode
        seite = r if k == 0 else -r
        x = seite * (10 + 18 * u + math.sin(u * 7) * 4) * s
        _herz(p, x, (-6 - 66 * u) * s, (9 + 5 * u) * s, _huelle(u))


def _fragezeichen(p: QPainter, t: float, s: float, r: int) -> None:
    _text(p, "?", r * 4 * s, (-28 + math.sin(t * 3) * 3) * s, 26 * s, AKZENT, min(1.0, t * 5),
          winkel=math.sin(t * 2) * 10)


def _ausrufezeichen(p: QPainter, t: float, s: float, r: int) -> None:
    u = min(1.0, t / 0.25)
    gross = 1 + 2.2 * (u - 1) ** 3 + 1.2 * (u - 1) ** 2 if u < 1 else 1.0     # „Pop“ mit Überschwinger
    wackeln = math.sin(t * 40) * 2 * max(0.0, 1 - t / 0.6)
    _text(p, "!", r * 2 * s + wackeln, (-30 - 6 * (1 - u)) * s, 28 * s * max(0.05, gross), QColor("#A13A2C"),
          min(1.0, t * 8))


ZEICHNER = {"zzz": _zzz, "noten": _noten, "sterne": _sterne, "dampf": _dampf, "herzchen": _herzchen,
            "fragezeichen": _fragezeichen, "ausrufezeichen": _ausrufezeichen}


def zeichnen(p: QPainter, name: str, t: float, kopf: QPointF, kopf_breite: float, richtung: int = 1,
             eigene: dict[str, EigenerEffekt] | None = None) -> bool:
    """Effekt ``name`` zum Zeitpunkt ``t`` über dem Kopf zeichnen. False = unbekannt."""
    s = max(0.7, min(1.4, kopf_breite / 44.0))
    r = 1 if richtung >= 0 else -1
    eigener = (eigene or {}).get(name)
    if eigener is None and name not in ZEICHNER:
        return False
    p.save()
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    p.translate(kopf)
    if eigener is not None and eigener.bilder:
        pm = eigener.bilder[int(t * eigener.fps) % len(eigener.bilder)]
        b = eigener.breite
        h = b * pm.height() / max(1, pm.width())
        p.drawPixmap(QRectF(-b / 2, -eigener.hoehe_ueber_kopf - h, b, h), pm, QRectF(pm.rect()))
    else:
        ZEICHNER[name](p, t, s, r)
    p.restore()
    return True


# --- Bauplan und avatar.json -----------------------------------------------------------------

def plan_pruefen(plan: dict, ordner=None, animationen=None) -> tuple[list[str], list[str]]:
    """Prüft ``effekte`` im Bauplan → (Fehler, Warnungen)."""
    import re
    from pathlib import Path

    fehler: list[str] = []
    warnungen: list[str] = []
    e = plan.get("effekte", {})
    if not e:
        return fehler, warnungen
    if not isinstance(e, dict):
        return ["effekte: erwartet ein Objekt mit „zuordnung“ und „eigene“"], warnungen
    for k in e:
        if k not in ("zuordnung", "eigene"):
            fehler.append(f"effekte: unbekannter Eintrag „{k}“")
    eigene = e.get("eigene", {})
    if not isinstance(eigene, dict):
        fehler.append("effekte.eigene: erwartet ein Objekt (Name → Einstellungen)")
        eigene = {}
    for name, d in eigene.items():
        ort = f"effekte.eigene.{name}"
        if not re.fullmatch(NAME_MUSTER, name):
            fehler.append(f"{ort}: Namen bitte nur aus a–z, 0–9 und _")
        elif name in EINGEBAUT:
            fehler.append(f"{ort}: „{name}“ ist schon ein eingebauter Effekt – bitte anders nennen")
        if not isinstance(d, dict) or not isinstance(d.get("ordner"), str):
            fehler.append(f"{ort}: „ordner“ fehlt")
            continue
        for k, (lo, hi) in (("fps", (1, 30)), ("breite", (8, 200)), ("hoehe_ueber_kopf", (-60, 80))):
            v = d.get(k)
            if v is not None and (not isinstance(v, (int, float)) or isinstance(v, bool) or not lo <= v <= hi):
                fehler.append(f"{ort}.{k}: erwartet eine Zahl von {lo} bis {hi}")
        if ordner is not None and not sorted((Path(ordner) / d["ordner"]).glob("*.png")):
            warnungen.append(f"{ort}: keine PNG-Bilder in {d['ordner']} – der Effekt entfällt")
    z = e.get("zuordnung", {})
    if not isinstance(z, dict):
        fehler.append("effekte.zuordnung: erwartet ein Objekt (Animation → Effekt)")
        z = {}
    for anim, name in z.items():
        if not isinstance(name, str):
            fehler.append(f"effekte.zuordnung.{anim}: erwartet einen Effekt-Namen")
        elif name and not bekannt(name, eigene):
            fehler.append(f"effekte.zuordnung.{anim}: Effekt „{name}“ gibt es nicht "
                          f"(eingebaut: {', '.join(EINGEBAUT)})")
        if animationen is not None and anim not in animationen:
            warnungen.append(f"effekte.zuordnung.{anim}: Animation „{anim}“ hat der Avatar nicht")
    return fehler, warnungen


def eigene_laden(ordner, daten: dict) -> dict[str, EigenerEffekt]:
    """``effekte.eigene`` aus avatar.json → Bildfolgen."""
    ergebnis: dict[str, EigenerEffekt] = {}
    for name, d in ((daten.get("effekte") or {}).get("eigene") or {}).items():
        bilder = [QPixmap(str(ordner / rel)) for rel in d.get("bilder", [])]
        bilder = [b for b in bilder if not b.isNull()]
        if bilder:
            ergebnis[name] = EigenerEffekt(bilder, float(d.get("fps", 8)), float(d.get("breite", 40)),
                                           float(d.get("hoehe_ueber_kopf", 6)))
    return ergebnis


# --- Fenster ---------------------------------------------------------------------------------

class EffektFenster(QWidget):
    """Zweite Ebene über dem Avatar. Komplett durchklickbar (``WindowTransparentForInput``)
    und nur sichtbar, solange ein Effekt läuft."""

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
        self.setWindowTitle("DMNT-Kobold Effekte")
        self.setFixedSize(FENSTER_B, FENSTER_H)
        self.name: str | None = None
        self.t = 0.0
        self.kopf_breite = 44.0
        self.richtung = 1
        self.eigene: dict[str, EigenerEffekt] = {}

    @staticmethod
    def bereich(kopf_global: QPointF) -> QRect:
        return QRect(round(kopf_global.x() - KOPF_X), round(kopf_global.y() - KOPF_Y), FENSTER_B, FENSTER_H)

    def zeigen(self, name: str, t: float, kopf_global: QPointF, kopf_breite: float, richtung: int,
               eigene: dict[str, EigenerEffekt]) -> None:
        self.name, self.t, self.kopf_breite, self.richtung, self.eigene = name, t, kopf_breite, richtung, eigene
        ort = self.bereich(kopf_global)
        if self.pos() != ort.topLeft():
            self.move(ort.topLeft())
        if not self.isVisible():
            from . import win32
            self.show()
            win32.ganz_nach_vorne(int(self.winId()))
        self.update()

    def verstecken(self) -> None:
        self.name = None
        if self.isVisible():
            self.hide()

    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt-API)
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Source)
        p.fillRect(self.rect(), Qt.GlobalColor.transparent)
        p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
        if self.name:
            zeichnen(p, self.name, self.t, QPointF(KOPF_X, KOPF_Y), self.kopf_breite, self.richtung, self.eigene)
        p.end()
