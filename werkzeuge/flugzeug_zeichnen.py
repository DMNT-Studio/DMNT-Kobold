"""Zeichnet den Avatar „Flugzeug" (Posen als SVG, Herkunft, Töne, Start-Bauplan).

Aufruf:  python werkzeuge/flugzeug_zeichnen.py
Danach:  python werkzeuge/avatar_bauen.py quellen/flugzeug
         (mit eigenem Körperbild zusätzlich: python werkzeuge/avatar_bauen.py quellen/flugzeug_lokal)

Aufbau: Ein Körper ohne Gesicht (Linien-Symbol), dazu blaue Arme und Beine mit weißen
Händen. Die Arme sind vorne auf den Körper aufgesetzt (hängen davor, stehen nicht ab),
die Beine kommen hinten unten aus dem Körper. Jede Pose ist eine fertige SVG-Datei.

Zwei Fassungen:
  quellen/flugzeug/        Platzhalter-Körper „Papierflieger" (eigene Form, MIT, im Repo)
  quellen/flugzeug_lokal/  nur wenn dort koerper.png oder koerper.svg liegt: derselbe Avatar
                           mit deinem eigenen Körperbild. Der Ordner ist in .gitignore und
                           kommt nie ins Repo, in ein Release oder die CI.
Andockpunkte (Schultern, Hüften) als Anteile der Körperfläche: andock.json im Lokal-Ordner
(wird beim ersten Lauf angelegt, danach nie überschrieben).

Was das Skript schreibt: teile/*.svg, herkunft.svg, toene/*.wav immer neu.
bauplan.json und verhalten.json nur, wenn es sie noch nicht gibt (Editor-Stand bleibt).
"""
from __future__ import annotations

import base64
import json
import math
import shutil
import wave
from pathlib import Path

import numpy as np

WURZEL = Path(__file__).resolve().parents[1]
ZIEL = WURZEL / "quellen" / "flugzeug"
LOKAL = WURZEL / "quellen" / "flugzeug_lokal"

# --- Maße (viewBox-Einheiten = logische Pixel bei faktor 1) -----------------------------
B, H = 110.0, 120.0
G = H                                    # Boden
BOX = (16.0, 36.0, 80.0, 52.0)           # Körperfläche x, y, Breite, Höhe (stehend)
OBERARM, UNTERARM = 12.0, 12.0
OBERSCHENKEL, UNTERSCHENKEL = 16.0, 16.0
HAND_R = 5.0
FUSS_RX, FUSS_RY = 7.5, 3.6
RAND_W = 1.6
KNOECHEL_Y = G - FUSS_RY - RAND_W        # Knöchel eines Fußes, der flach auf dem Boden steht

BLAU = "#2F7FD0"
BLAU_FERN = "#2768AD"                    # Arm und Bein auf der abgewandten Seite
RAND = "#1F5E9E"
HAND = "#FFFFFF"
LINIE = "#1D2320"                        # Körperlinien
SAUM = "#FFFFFF"                         # heller Saum, damit er auf dunkler Taskleiste sichtbar bleibt
GLIED_W = 6.0

ANDOCK_STANDARD = {
    "schulter_vorne": [0.58, 0.40],
    "schulter_hinten": [0.48, 0.36],
    "huefte_vorne": [0.33, 0.95],
    "huefte_hinten": [0.25, 0.92],
    "_hinweis": "Anteile der Körperfläche: 0,0 = oben links, 1,1 = unten rechts. Nase zeigt nach rechts.",
}


def z(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


# --- Geometrie ---------------------------------------------------------------------------

def drehen(p, mitte, winkel):
    a = math.radians(winkel)
    dx, dy = p[0] - mitte[0], p[1] - mitte[1]
    return (mitte[0] + dx * math.cos(a) - dy * math.sin(a), mitte[1] + dx * math.sin(a) + dy * math.cos(a))


def gelenk(a, t, l1, l2, seite):
    """Zweiteiliges Glied von a nach t: Lage des Gelenks (Knie/Ellbogen).
    seite -1: Gelenk zeigt (bei nach unten hängendem Glied) nach vorn, +1 nach hinten."""
    dx, dy = t[0] - a[0], t[1] - a[1]
    d = max(abs(l1 - l2) + 0.01, min(l1 + l2 - 0.01, math.hypot(dx, dy)))
    basis = math.atan2(dy, dx)
    w = math.acos(max(-1.0, min(1.0, (l1 * l1 + d * d - l2 * l2) / (2 * l1 * d))))
    g = basis + seite * w
    j = (a[0] + l1 * math.cos(g), a[1] + l1 * math.sin(g))
    ende_w = math.atan2(t[1] - j[1], t[0] - j[0])
    return j, (j[0] + l2 * math.cos(ende_w), j[1] + l2 * math.sin(ende_w))


def punkt(anteil):
    x0, y0, bw, bh = BOX
    return (x0 + anteil[0] * bw, y0 + anteil[1] * bh)


# --- Körper ------------------------------------------------------------------------------

def papierflieger() -> str:
    """Platzhalter-Körper: Papierflieger von der Seite, Nase rechts. Eigene Form."""
    nase, heck_o, falz, kiel = punkt((0.98, 0.50)), punkt((0.04, 0.08)), punkt((0.16, 0.50)), punkt((0.30, 0.95))

    def linien(farbe, w, deck=1.0):
        pts1 = " ".join(f"{z(x)},{z(y)}" for x, y in (nase, heck_o, falz))
        pts2 = " ".join(f"{z(x)},{z(y)}" for x, y in (nase, falz, kiel))
        attr = (f'fill="none" stroke="{farbe}" stroke-width="{z(w)}" stroke-linejoin="round" '
                f'stroke-linecap="round" stroke-opacity="{z(deck)}"')
        return f'<polygon points="{pts1}" {attr}/>\n    <polygon points="{pts2}" {attr}/>'

    return f"{linien(SAUM, 6.6, 0.9)}\n    {linien(LINIE, 3.6)}"


def lokales_bild() -> tuple[str, str] | None:
    """Eigenes Körperbild aus quellen/flugzeug_lokal/ als (Mime-Typ, Base64) oder None."""
    png = LOKAL / "koerper.png"
    if png.is_file():
        return "image/png", base64.b64encode(png.read_bytes()).decode("ascii")
    svg = LOKAL / "koerper.svg"
    if svg.is_file():                    # SVG in PNG wandeln (QtSvg zeichnet kein SVG in <image>)
        from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
        from PySide6.QtGui import QGuiApplication, QImage, QPainter
        from PySide6.QtSvg import QSvgRenderer

        if QGuiApplication.instance() is None:
            import os

            os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
            lokales_bild.app = QGuiApplication(["flugzeug"])
        r = QSvgRenderer(str(svg))
        vb = r.viewBoxF()
        k = 1200 / max(vb.width(), vb.height())
        img = QImage(round(vb.width() * k), round(vb.height() * k), QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r.render(p, QRectF(0, 0, img.width(), img.height()))
        p.end()
        daten = QByteArray()
        puffer = QBuffer(daten)
        puffer.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(puffer, "PNG")
        return "image/png", base64.b64encode(bytes(daten)).decode("ascii")
    return None


def bild_koerper(mime: str, b64: str) -> str:
    x0, y0, bw, bh = BOX
    return (f'<image x="{z(x0)}" y="{z(y0)}" width="{z(bw)}" height="{z(bh)}" '
            f'preserveAspectRatio="xMidYMid meet" xlink:href="data:{mime};base64,{b64}"/>')


# --- Glieder -----------------------------------------------------------------------------

def glied(pts, farbe) -> str:
    p = " ".join(f"{z(x)},{z(y)}" for x, y in pts)
    return (f'<polyline points="{p}" fill="none" stroke="{RAND}" stroke-width="{z(GLIED_W + 2 * RAND_W)}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>\n    '
            f'<polyline points="{p}" fill="none" stroke="{farbe}" stroke-width="{z(GLIED_W)}" '
            f'stroke-linecap="round" stroke-linejoin="round"/>')


def hand(p) -> str:
    return (f'<circle cx="{z(p[0])}" cy="{z(p[1])}" r="{z(HAND_R)}" fill="{HAND}" '
            f'stroke="{RAND}" stroke-width="{z(RAND_W)}"/>')


def fuss(knoechel, winkel, farbe) -> str:
    a = math.radians(winkel)
    cx, cy = knoechel[0] + 3 * math.cos(a), knoechel[1] + 3 * math.sin(a)
    return (f'<ellipse cx="{z(cx)}" cy="{z(cy)}" rx="{z(FUSS_RX)}" ry="{z(FUSS_RY)}" fill="{farbe}" '
            f'stroke="{RAND}" stroke-width="{z(RAND_W)}" transform="rotate({z(winkel)} {z(cx)} {z(cy)})"/>')


# --- Pose --------------------------------------------------------------------------------

class Pose:
    """Eine Pose. Oberkörper (Körper + Schultern + Hüften) wird um die Hüfte gekippt
    (``winkel``, + = Nase nach unten) und um ``dx``/``dy`` verschoben.
    Hände: Versatz zur Schulter im Körper-Rahmen. Füße: (x, y, winkel) in der Leinwand,
    Standard = flach unter der jeweiligen Hüfte."""

    def __init__(self, andock: dict, winkel=0.0, dx=0.0, dy=0.0,
                 hand_v=(3.0, 20.0), hand_h=(3.0, 20.0), fuss_v=None, fuss_h=None, fuss_dy=0.0):
        self.a = andock
        self.winkel, self.dx, self.dy = winkel, dx, dy
        self.hand_v, self.hand_h = hand_v, hand_h
        hv, hh = punkt(andock["huefte_vorne"]), punkt(andock["huefte_hinten"])
        self.fuss_v = fuss_v or (hv[0], KNOECHEL_Y + fuss_dy, 0.0)
        self.fuss_h = fuss_h or (hh[0], KNOECHEL_Y + fuss_dy, 0.0)

    def welt(self, p):
        mitte = punkt(self.a["huefte_vorne"])
        q = drehen(p, mitte, self.winkel)
        return (q[0] + self.dx, q[1] + self.dy)

    def svg(self, koerper: str) -> str:
        a = self.a
        teile = []

        def arm(schulter_anteil, rel, farbe):
            s_lokal = punkt(schulter_anteil)
            s = self.welt(s_lokal)
            t = self.welt((s_lokal[0] + rel[0], s_lokal[1] + rel[1]))
            ell, h = gelenk(s, t, OBERARM, UNTERARM, +1)
            return f"{glied([s, ell, h], farbe)}\n    {hand(h)}"

        def bein(huefte_anteil, f, farbe):
            hp = self.welt(punkt(huefte_anteil))
            knie, k = gelenk(hp, (f[0], f[1]), OBERSCHENKEL, UNTERSCHENKEL, -1)
            return f"{glied([hp, knie, k], farbe)}\n    {fuss(k, f[2], farbe)}"

        teile.append("<!-- hinten: Bein und Arm der abgewandten Seite -->\n    "
                     + bein(a["huefte_hinten"], self.fuss_h, BLAU_FERN))
        teile.append(arm(a["schulter_hinten"], self.hand_h, BLAU_FERN))
        mitte = punkt(a["huefte_vorne"])
        teile.append(f'<!-- Körper -->\n    <g transform="translate({z(self.dx)} {z(self.dy)}) '
                     f'rotate({z(self.winkel)} {z(mitte[0])} {z(mitte[1])})">\n    {koerper}\n    </g>')
        teile.append("<!-- vorne: Bein, dann der aufgesetzte Arm -->\n    "
                     + bein(a["huefte_vorne"], self.fuss_v, BLAU))
        teile.append(arm(a["schulter_vorne"], self.hand_v, BLAU))
        inhalt = "\n    ".join(teile)
        return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
                f'viewBox="0 0 {z(B)} {z(H)}" width="{z(B)}" height="{z(H)}">\n    {inhalt}\n</svg>\n')


GEHEN_BILDER = 8
SITZ_DY = 22.0


def posen(andock: dict) -> dict[str, Pose]:
    P = lambda **k: Pose(andock, **k)  # noqa: E731
    hv, hh = punkt(andock["huefte_vorne"]), punkt(andock["huefte_hinten"])
    p: dict[str, Pose] = {
        "stehen_a": P(),
        "stehen_b": P(dy=0.6, hand_v=(3.4, 19.6), hand_h=(2.6, 19.8)),
        "stehen_c": P(dy=1.2, hand_v=(3.8, 19.2), hand_h=(2.2, 19.6)),
        "zehen": P(dy=-3.0, fuss_v=(hv[0] - 1, KNOECHEL_Y - 3, -22), fuss_h=(hh[0] - 1, KNOECHEL_Y - 3, -22),
                   hand_v=(4, 19), hand_h=(2, 19)),
        "anschauen": P(winkel=-4, hand_v=(21, -9)),
        "sprechen_a": P(winkel=1, hand_v=(6, 18)),
        "sprechen_b": P(winkel=2, hand_v=(14, 6)),
        "sprechen_c": P(winkel=-1, hand_v=(16, -3)),
        "freuen_a": P(hand_v=(6, -20), hand_h=(-4, -20)),
        "freuen_b": P(dy=-6, fuss_dy=-6, hand_v=(9, -21), hand_h=(-1, -19)),
        "erschrecken_a": P(dx=-3, hand_v=(14, -14), hand_h=(-12, -14),
                           fuss_v=(hv[0] + 8, KNOECHEL_Y, 0), fuss_h=(hh[0] - 8, KNOECHEL_Y, 0)),
        "erschrecken_b": P(dx=-1.6, hand_v=(15, -15), hand_h=(-11, -15),
                           fuss_v=(hv[0] + 8, KNOECHEL_Y, 0), fuss_h=(hh[0] - 8, KNOECHEL_Y, 0)),
        "sitzen": P(winkel=-3, dy=SITZ_DY, hand_v=(8, 14), hand_h=(6, 14),
                    fuss_v=(hv[0] + 24, KNOECHEL_Y - 2, -70), fuss_h=(hh[0] + 22, KNOECHEL_Y - 2, -70)),
        "schlafen_a": P(winkel=10, dy=SITZ_DY, hand_v=(4, 16), hand_h=(3, 16),
                        fuss_v=(hv[0] + 24, KNOECHEL_Y - 2, -70), fuss_h=(hh[0] + 22, KNOECHEL_Y - 2, -70)),
        "schlafen_b": P(winkel=11, dy=SITZ_DY + 0.8, hand_v=(4, 16.5), hand_h=(3, 16.5),
                        fuss_v=(hv[0] + 24, KNOECHEL_Y - 2, -70), fuss_h=(hh[0] + 22, KNOECHEL_Y - 2, -70)),
        "gezogen": P(dy=-8, hand_v=(12, -15), hand_h=(-10, -15),
                     fuss_v=(hv[0] + 3, KNOECHEL_Y - 9, 25), fuss_h=(hh[0] - 2, KNOECHEL_Y - 10, 30)),
        "landen": P(dy=6, hand_v=(17, 2), hand_h=(-13, 2),
                    fuss_v=(hv[0] + 6, KNOECHEL_Y, 0), fuss_h=(hh[0] - 6, KNOECHEL_Y, 0)),
    }
    # Winken: vorderer Arm oben, Hand schwingt
    for i, x in enumerate((8, 12, 16, 12)):
        p[f"winken_{i + 1}"] = P(winkel=-3, hand_v=(x, -19 + (2 if x == 16 else 0)))
    # Fallen: Arme flattern wie Flügel (er glaubt, er kann fliegen)
    for i, (yv, yh) in enumerate(((-18, -14), (-8, -4), (4, 6), (-8, -4))):
        p[f"fallen_{i + 1}"] = P(dy=-8, hand_v=(16, yv), hand_h=(-12, yh),
                                 fuss_v=(hv[0] + 3, KNOECHEL_Y - 9, 25), fuss_h=(hh[0] - 2, KNOECHEL_Y - 10, 30))
    # Gehen: beschwingt, kippt im Schritttakt ±6°, wippt, Arme schwingen gegengleich
    for i in range(GEHEN_BILDER):
        ph = 2 * math.pi * i / GEHEN_BILDER
        s, c = math.sin(ph), math.cos(ph)
        heb_v, heb_h = 5 * max(0.0, c), 5 * max(0.0, -c)
        p[f"gehen_{i + 1}"] = P(
            winkel=6 * s, dy=-3 * abs(s),
            hand_v=(3 - 7 * s, 19.5 - 3 * max(0.0, -s)), hand_h=(3 + 7 * s, 19.5 - 3 * max(0.0, s)),
            fuss_v=(hv[0] + 10 * s, KNOECHEL_Y - heb_v, -4 * heb_v),
            fuss_h=(hh[0] - 10 * s, KNOECHEL_Y - heb_h, -4 * heb_h))
    return p


# --- Herkunft ----------------------------------------------------------------------------

def herkunft() -> str:
    striche = []
    for i in range(7):                    # Mittellinie der Piste in Perspektive
        t0, t1 = i / 7, (i + 0.5) / 7
        y0, y1 = 252 + t0 ** 1.6 * 148, 252 + t1 ** 1.6 * 148
        w0, w1 = 1.2 + 6 * t0, 1.2 + 6 * t1
        striche.append(f'<polygon points="{z(200 - w0 / 2)},{z(y0)} {z(200 + w0 / 2)},{z(y0)} '
                       f'{z(200 + w1 / 2)},{z(y1)} {z(200 - w1 / 2)},{z(y1)}" fill="#FFFFFF" fill-opacity="0.85"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 400 400" width="400" height="400">
  <defs>
    <linearGradient id="himmel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#9CC9EA"/>
      <stop offset="0.55" stop-color="#CFE5F2"/>
      <stop offset="1" stop-color="#FBE6C8"/>
    </linearGradient>
    <radialGradient id="sonne" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#FFF6DD" stop-opacity="1"/>
      <stop offset="0.35" stop-color="#FFE9B8" stop-opacity="0.8"/>
      <stop offset="1" stop-color="#FFE9B8" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="wiese" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#A9C98F"/>
      <stop offset="1" stop-color="#7FAF6A"/>
    </linearGradient>
  </defs>
  <rect width="400" height="400" fill="url(#himmel)"/>
  <circle cx="292" cy="196" r="92" fill="url(#sonne)"/>
  <circle cx="292" cy="196" r="20" fill="#FFF4D6"/>
  <ellipse cx="96" cy="88" rx="44" ry="11" fill="#FFFFFF" fill-opacity="0.7"/>
  <ellipse cx="126" cy="80" rx="28" ry="10" fill="#FFFFFF" fill-opacity="0.7"/>
  <ellipse cx="300" cy="120" rx="36" ry="8" fill="#FFFFFF" fill-opacity="0.55"/>
  <path d="M0,262 C70,236 140,248 205,240 C270,232 330,226 400,246 L400,400 L0,400 Z" fill="#B9D3A1"/>
  <path d="M0,282 C90,262 170,268 250,260 C320,254 360,256 400,262 L400,400 L0,400 Z" fill="url(#wiese)"/>
  <polygon points="192,252 208,252 290,400 110,400" fill="#9EA39F"/>
  <polygon points="192,252 208,252 290,400 110,400" fill="none" stroke="#FFFFFF" stroke-opacity="0.6" stroke-width="2"/>
  {chr(10).join('  ' + s for s in striche).lstrip()}
  <line x1="318" y1="300" x2="318" y2="254" stroke="#6A6E6B" stroke-width="2.4" stroke-linecap="round"/>
  <polygon points="318,256 346,260 344,268 318,266" fill="#E8894A"/>
  <polygon points="328,257.4 336,258.6 335,267.2 328,266.6" fill="#FFFFFF" fill-opacity="0.85"/>
</svg>
"""


# --- Töne --------------------------------------------------------------------------------

SR = 22050


def wav(ordner: Path, name: str, x: np.ndarray, pegel: float) -> None:
    x = x / (np.max(np.abs(x)) + 1e-9) * pegel
    daten = (np.clip(x, -1, 1) * 32767).astype("<i2")
    (ordner / "toene").mkdir(parents=True, exist_ok=True)
    with wave.open(str(ordner / "toene" / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(daten.tobytes())


def pfiff(noten, rnd, gleiten_s=0.03) -> np.ndarray:
    """Gepfiffene Melodie: [(Frequenz, Dauer s), …]. Weiches Gleiten zwischen den Tönen,
    leichtes Vibrato, ein Hauch Luft. Frequenz 0 = kurze Pause."""
    f, amp = [], []
    for freq, dauer in noten:
        n = int(SR * dauer)
        f.append(np.full(n, freq if freq else (f[-1][-1] if f else 1200.0)))
        t = np.arange(n) / SR
        if freq:
            a = np.minimum(1, t / 0.018) * np.minimum(1, (dauer - t) / 0.04)
            amp.append(0.25 + 0.75 * np.clip(a, 0, 1))
        else:
            amp.append(np.zeros(n))
    f = np.concatenate(f)
    amp = np.concatenate(amp)
    k = max(1, int(SR * gleiten_s))
    f = np.convolve(np.pad(f, (k, k), mode="edge"), np.ones(k) / k, mode="same")[k:-k]
    amp = np.convolve(np.pad(amp, (k, k), mode="edge"), np.ones(k) / k, mode="same")[k:-k]
    t = np.arange(len(f)) / SR
    f = f * (1 + 0.012 * np.sin(2 * np.pi * 5.5 * t))
    phase = 2 * np.pi * np.cumsum(f) / SR
    x = np.sin(phase) + 0.08 * np.sin(2 * phase)
    luft = rnd.standard_normal(len(x))
    luft = np.convolve(luft, np.ones(6) / 6, mode="same")
    x = x + 0.06 * luft
    n = len(x)
    huelle = np.minimum(1, t / 0.03) * np.minimum(1, (n / SR - t) / 0.08)
    return x * amp * huelle


C6, D6, E6, F6, G6, A6, H6, C7 = 1046.5, 1174.7, 1318.5, 1396.9, 1568.0, 1760.0, 1975.5, 2093.0


def toene(ordner: Path) -> None:
    rnd = np.random.default_rng(9)
    wav(ordner, "pfeifen_1", pfiff([(E6, .16), (G6, .16), (A6, .16), (G6, .14), (0, .05), (E6, .30)], rnd), 0.30)
    wav(ordner, "pfeifen_2", pfiff([(G6, .14), (E6, .14), (G6, .14), (C7, .34), (0, .05), (A6, .12), (G6, .26)],
                                   rnd), 0.30)
    wav(ordner, "pfeifen_3", pfiff([(C6, .14), (E6, .14), (G6, .22), (0, .06), (G6, .1), (A6, .1), (G6, .1),
                                    (E6, .28)], rnd), 0.30)
    wav(ordner, "duedel_1", pfiff([(G6, .07), (C7, .09)], rnd, 0.015), 0.32)
    wav(ordner, "duedel_2", pfiff([(A6, .07), (F6, .09)], rnd, 0.015), 0.32)
    wav(ordner, "juchz", pfiff([(G6, .08), (C7, .08), (0, .03), (E6, .06), (C7, .16)], rnd, 0.02), 0.34)
    n = int(SR * 0.22)
    f0 = np.linspace(2000, 900, n)
    t = np.arange(n) / SR
    wav(ordner, "huch", np.sin(2 * np.pi * np.cumsum(f0) / SR) * np.minimum(1, t / 0.01)
        * np.minimum(1, (0.22 - t) / 0.08), 0.34)
    n = int(SR * 0.06)
    f0 = np.linspace(170, 80, n)
    t = np.arange(n) / SR
    wav(ordner, "tapp", np.sin(2 * np.pi * np.cumsum(f0) / SR) * np.minimum(1, t / 0.004)
        * np.minimum(1, (0.06 - t) / 0.04), 0.35)


# --- Bauplan und Verhalten --------------------------------------------------------------

def bauplan(avatar_id: str, name: str) -> dict:
    def anim(fps, namen, schleife=True):
        a = {"fps": fps, "bilder": [[n, 0, "normal"] for n in namen]}
        if not schleife:
            a["schleife"] = False
        return a

    alle = [*posen(ANDOCK_STANDARD).keys()]
    a, b, c = "stehen_a", "stehen_b", "stehen_c"
    ruhe = [a, a, b, b, c, c, c, b, b, a, a, a, b, b, c, c, b, b, a, a, "zehen", "zehen", a, a]
    t = lambda *d: [f"toene/{x}.wav" for x in d]  # noqa: E731
    return {
        "id": avatar_id,
        "name": name,
        "skalierung": 2,
        "ausrichtung": "rahmen",
        "rahmen_px": [int(B * 2), int(H * 2)],
        "blickrichtung": 1,
        "bewegung": {"art": "gehen"},
        "toene": {
            "bewegen": {"dateien": t("pfeifen_1", "pfeifen_2", "pfeifen_3"), "tonhoehe": 0.04,
                        "chance": 0.5, "abstand_s": 25},
            "sprechen": {"dateien": t("duedel_1", "duedel_2"), "tonhoehe": 0.1, "wiederholen": [1, 2]},
            "freuen": {"dateien": t("juchz"), "tonhoehe": 0.05},
            "erschrecken": {"dateien": t("huch"), "tonhoehe": 0.05},
            "landen": {"dateien": t("tapp"), "tonhoehe": 0.1},
        },
        "portraet": {"pose": "stehen_a", "hoehe": 160},
        "quellen": {n: {"datei": f"teile/{n}.svg", "faktor": 1.0} for n in alle},
        "referenz": ["stehen_a", 0],
        "animationen": {
            "ruhe": anim(4, ruhe),
            "bewegen": anim(9, [f"gehen_{i + 1}" for i in range(GEHEN_BILDER)]),
            "sitzen": anim(1, ["sitzen"]),
            "schlafen": anim(0.8, ["schlafen_a", "schlafen_b"]),
            "gezogen": anim(2, ["gezogen"]),
            "fallen": anim(10, ["fallen_1", "fallen_2", "fallen_3", "fallen_4"]),
            "springen": anim(2, ["gezogen"]),
            "schweben": anim(1, ["gezogen"]),
            "landen": anim(4, ["landen"], schleife=False),
            "anschauen": anim(2, ["anschauen"]),
            "sprechen": anim(6, ["sprechen_a", "sprechen_b", "sprechen_c", "sprechen_b"]),
            "freuen": anim(5, ["freuen_a", "freuen_b"]),
            "winken": anim(6, ["winken_1", "winken_2", "winken_3", "winken_4"]),
            "erschrecken": anim(12, ["erschrecken_a", "erschrecken_b"] * 2 + ["erschrecken_a"], schleife=False),
        },
        "herkunft": {"hintergrund": "herkunft.svg", "groesse": 768},
        "effekte": {"zuordnung": {"bewegen": "noten", "freuen": "herzchen", "erschrecken": "ausrufezeichen"}},
    }


def regel(id_, wenn, dann, **rest) -> dict:
    return {"id": id_, "wenn": wenn, "dann": dann, **rest}


def anim(name):
    return {"aktion": "animation", "name": name}


def sag(*texte, **rest):
    return {"aktion": "sprechen", "texte": list(texte), **rest}


def verhalten() -> dict:
    return {
        "beschreibung": "Flugzeug - freundlicher Helfer ohne Gesicht. Schlendert pfeifend über die "
                        "Taskleiste, winkt gern und hält sich für einen Flieger. Ohne Code.",
        "werte": {"laufgeschwindigkeit": 50, "einschlafen_nach_min": 8},
        "regeln": [
            regel("hallo_maus", {"ereignis": "maus.nah_am_avatar"}, [anim("anschauen"), {"aktion": "bleiben"}],
                  prioritaet=30),
            regel("hallo_winken", {"ereignis": "maus.nah_am_avatar"},
                  [anim("winken"), sag("Kann ich helfen?", "Bereit zum Einsteigen?", "Alles im grünen Bereich?")],
                  prioritaet=31, dauer_s=3, chance=0.3, abklingzeit_s=45),
            regel("maus_weg", {"ereignis": "maus.weg"},
                  [{"aktion": "zurueckziehen", "regeln": ["hallo_maus", "hallo_winken"]}]),
            regel("klick", {"ereignis": "maus.klick"},
                  [anim("freuen"), sag("Zu Diensten!", "Startklar!", "Immer gern.", "Wohin soll's gehen?")],
                  prioritaet=35, dauer_s=2.5, gruppe="klick"),
            regel("wackeln", {"ereignis": "maus.wackelt"},
                  [anim("erschrecken"), sag("Huch, Turbulenzen!", "Bitte anschnallen!", trotz_ruhe=True)],
                  prioritaet=45, dauer_s=2, abklingzeit_s=8, gruppe="wackeln"),
            regel("wackeln_kurz", {"ereignis": "maus.wackelt"}, [anim("erschrecken")],
                  prioritaet=45, dauer_s=1.2, gruppe="wackeln"),
            regel("tipp_pause", {"ereignis": "tastatur.pause", "sitzung_ab_s": "$lange_tippsitzung_s"},
                  [sag("Zeit für eine kurze Zwischenlandung?", knoepfe=["Ok", "Gleich"])],
                  prioritaet=60, dauer_s=15, aufheben=True, abklingzeit_s=900, gruppe="pause"),
            regel("pause_ok", {"ereignis": "sprechblase.knopf", "knopf": "Ok", "regel": "tipp_pause"},
                  [anim("freuen"), sag("Gute Landung!")], prioritaet=45, dauer_s=2.5),
            regel("pause_gleich", {"ereignis": "sprechblase.knopf", "knopf": "Gleich", "regel": "tipp_pause"},
                  [anim("winken"), sag("Ich halte die Parkposition frei.")], prioritaet=45, dauer_s=3),
            regel("leerlauf", {"ereignis": "leerlauf", "ab_minuten": "$einschlafen_nach_min"},
                  [anim("schlafen"), {"aktion": "bleiben"}], prioritaet=20),
            regel("aufwachen", {"ereignis": "leerlauf.ende", "regel_laeuft": "leerlauf"},
                  [{"aktion": "zurueckziehen", "regeln": ["leerlauf"]}, anim("freuen"),
                   sag("Wieder an Bord? Schön!", "Triebwerke laufen wieder.")],
                  prioritaet=35, dauer_s=4),
            regel("landung_hoch", {"ereignis": "avatar.gelandet", "art": "fall", "fallhoehe_px": 200},
                  [anim("landen"), sag("Holprige Landung. Alles heil!")], prioritaet=40, dauer_s=2.5),
            regel("musik", {"ereignis": "audio.laeuft"}, [anim("freuen"), {"aktion": "effekt", "name": "noten"}],
                  prioritaet=32, dauer_s=4, chance=0.4, abklingzeit_s=120),
            regel("morgens", {"ereignis": "tageszeit", "tageszeit": "morgens"},
                  [anim("winken"), sag("Guten Morgen! Der Tag ist startklar.")],
                  prioritaet=40, dauer_s=5, abklingzeit_s=21600),
            regel("star_citizen", {"ereignis": "programm.gestartet", "programm": ["starcitizen.exe"]},
                  [{"aktion": "gehen_zu", "ziel": "rechts"}, anim("sitzen"), {"aktion": "bleiben"}],
                  prioritaet=40),
            regel("star_citizen_spruch", {"ereignis": "programm.gestartet", "programm": ["starcitizen.exe"]},
                  [sag("Ich halte dir die Startbahn frei.")], prioritaet=41, dauer_s=4),
            regel("star_citizen_ende", {"ereignis": "programm.beendet", "programm": ["starcitizen.exe"]},
                  [{"aktion": "zurueckziehen", "regeln": ["star_citizen"]}]),
        ],
    }


LIZENZ = """Flugzeug - Avatar fuer DMNT-Kobold

Copyright (c) 2026 Stefan Rohrbach

Figur, Grafik (teile/*.svg mit dem Platzhalter-Koerper "Papierflieger", herkunft.svg),
Toene (toene/*.wav, erzeugt mit werkzeuge/flugzeug_zeichnen.py), bauplan.json und verhalten.json:
  Eigenentwicklung fuer DMNT-Kobold. Frei erfunden, ohne fremde Vorlage.
  Lizenz: MIT (wie das Projekt).
Ein eigenes Koerperbild in quellen/flugzeug_lokal/ ist NICHT Teil dieser Lizenz und
bleibt lokal (siehe .gitignore).

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

LIESMICH = """Flugzeug - freundlicher Helfer ohne Gesicht
=============================================

Eigener Avatar (MIT, Stefan Rohrbach), komplett als Vektorgrafik und "ohne Code":
alles, was er tut, steht in verhalten.json. Blaue Arme und Beine, weisse Haende. Die Arme
sind vorne auf den Koerper aufgesetzt, die Beine kommen hinten unten heraus. Er schlendert
wackelnd ueber die Taskleiste, ueber ihm schweben Noten, und beim Loslaufen pfeift er
manchmal (hoechstens alle 25 s) ein kurzes Liedchen.

Erzeugt mit:  python werkzeuge/flugzeug_zeichnen.py
  schreibt teile/, herkunft.svg und toene/ neu. bauplan.json und verhalten.json nur,
  wenn es sie noch nicht gibt - Aenderungen aus dem Avatar-Editor bleiben erhalten.
Bauen:        python werkzeuge/avatar_bauen.py quellen/flugzeug

Eigenes Koerperbild (bleibt lokal, nie im Repo)
  1. Bild als quellen/flugzeug_lokal/koerper.png (transparent, Nase nach rechts) ablegen.
  2. python werkzeuge/flugzeug_zeichnen.py
  3. Passen Schultern/Huefte nicht: quellen/flugzeug_lokal/andock.json anpassen, Schritt 2.
  4. python werkzeuge/avatar_bauen.py quellen/flugzeug_lokal
  Der Ordner flugzeug_lokal ist in .gitignore und wird nie gepackt.
"""


# --- Los ---------------------------------------------------------------------------------

def schreiben(ordner: Path, avatar_id: str, name: str, koerper: str, andock: dict) -> int:
    teile = ordner / "teile"
    if teile.exists():
        shutil.rmtree(teile)
    teile.mkdir(parents=True)
    alle = posen(andock)
    for n, pose in alle.items():
        (teile / f"{n}.svg").write_text(pose.svg(koerper), encoding="utf-8")
    (ordner / "herkunft.svg").write_text(herkunft(), encoding="utf-8")
    toene(ordner)
    for datei, inhalt in (("bauplan.json", bauplan(avatar_id, name)), ("verhalten.json", verhalten())):
        pfad = ordner / datei
        if pfad.exists():
            print(f"  {avatar_id}/{datei} gibt es schon - unverändert gelassen")
        else:
            pfad.write_text(json.dumps(inhalt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(f"  {avatar_id}/{datei} angelegt")
    return len(alle)


def main() -> None:
    ZIEL.mkdir(parents=True, exist_ok=True)
    n = schreiben(ZIEL, "flugzeug", "Papierflieger", papierflieger(), ANDOCK_STANDARD)
    (ZIEL / "LIZENZ.txt").write_text(LIZENZ, encoding="utf-8")
    (ZIEL / "LIESMICH.txt").write_text(LIESMICH, encoding="utf-8")
    print(f"{n} Posen, Herkunft und Töne in {ZIEL}")

    bild = lokales_bild()
    if bild is None:
        print("Kein eigenes Körperbild (quellen/flugzeug_lokal/koerper.png) - nur der Platzhalter.")
        return
    datei = LOKAL / "andock.json"
    if not datei.exists():
        datei.write_text(json.dumps(ANDOCK_STANDARD, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("  flugzeug_lokal/andock.json angelegt (Schultern/Hüften, bei Bedarf anpassen)")
    andock = {**ANDOCK_STANDARD, **json.loads(datei.read_text(encoding="utf-8"))}
    n = schreiben(LOKAL, "flugzeug_lokal", "Flugzeug", bild_koerper(*bild), andock)
    print(f"{n} Posen mit eigenem Körper in {LOKAL} (bleibt lokal)")


if __name__ == "__main__":
    main()
