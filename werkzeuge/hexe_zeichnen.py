"""Hexe zeichnen: schwarze Katze mit grünen Augen, läuft auf allen vieren.

Erzeugt in quellen/hexe/:
  teile/*.svg     Posen (Körper samt Beinen und Schwanz) und Gesichtsteile (Augen, Mund)
  herkunft.svg    Hintergrund beim Einrichten: Dächer bei Vollmond
  toene/*.wav     miau, prrt, fauchen, schnurren, tapp (synthetisiert, warm und rau)
  zubehoer/       Fledermausflügel (nah/fern) als SVG
  zubehoer.json   nur, wenn noch keins da ist (Platzierung je Pose)
  bauplan.json    nur, wenn noch keiner da ist (Änderungen aus dem Editor bleiben erhalten)

Aufruf (lokal, im Repo):  python werkzeuge/hexe_zeichnen.py
Danach bauen:             python werkzeuge/avatar_bauen.py quellen/hexe

Alle Posen teilen sich die viewBox 0 0 120 90 (= logische Pixel), Fußpunkt unten Mitte.
Der Trick gegen „schwarz auf schwarz“: Jede Form wird erst etwas größer in RAND gezeichnet,
dann in Fellfarbe darüber. So bekommt nur die Außenkontur einen hellen Saum.
"""
from __future__ import annotations

import json
import math
import wave
from pathlib import Path

import numpy as np

WURZEL = Path(__file__).resolve().parents[1]
ZIEL = WURZEL / "quellen" / "hexe"

B, H = 120, 90
G = 90.0                      # Boden = Unterkante der viewBox

# --- Farben (hier ändern, dann Skript erneut laufen lassen und neu bauen) -------------
FELL = "#1C1B21"
FELL_FERN = "#121116"         # Beine auf der abgewandten Seite
RAND = "#5B5868"              # heller Saum, damit sie auf dunkler Taskleiste sichtbar bleibt
GLANZ = "#2B2A33"
OHR_INNEN = "#4B3541"
NASE = "#B8828F"
LINIE = "#6E6B7C"
SCHNURR = "#C4C7D0"
AUGE = "#86D45A"
AUGE_TIEF = "#5BA83C"
PUPILLE = "#0A0A0C"
MUND = "#4A2330"
ZUNGE = "#D98A9C"

RAND_W = 2.2
PFOTE_RY = 2.4
BODEN_Y = G - RAND_W / 2 - PFOTE_RY     # Mitte einer Pfote, die auf dem Boden steht
KOPF0 = (90.0, 38.0)                     # Kopfmitte, auf die die Gesichtsteile gezeichnet sind


def z(v: float) -> str:
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


# --- Formen ---------------------------------------------------------------------------

def ell(cx, cy, rx, ry, rot=0.0):
    return ("ell", cx, cy, rx, ry, rot)


def poly(*pts):
    return ("poly", pts)


def strich(pts, w):
    return ("strich", pts, w)


def kurve(d, w):
    return ("kurve", d, w)


def _el(s, farbe: str, extra: float) -> str:
    art = s[0]
    if art == "ell":
        _, cx, cy, rx, ry, rot = s
        t = f' transform="rotate({z(rot)} {z(cx)} {z(cy)})"' if rot else ""
        return (f'<ellipse cx="{z(cx)}" cy="{z(cy)}" rx="{z(rx + extra)}" ry="{z(ry + extra)}" '
                f'fill="{farbe}"{t}/>')
    if art == "poly":
        pts = " ".join(f"{z(x)},{z(y)}" for x, y in s[1])
        return (f'<polygon points="{pts}" fill="{farbe}" stroke="{farbe}" '
                f'stroke-width="{z(0.8 + 2 * extra)}" stroke-linejoin="round"/>')
    if art == "strich":
        pts = " ".join(f"{z(x)},{z(y)}" for x, y in s[1])
        return (f'<polyline points="{pts}" fill="none" stroke="{farbe}" stroke-width="{z(s[2] + 2 * extra)}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>')
    if art == "kurve":
        return (f'<path d="{s[1]}" fill="none" stroke="{farbe}" stroke-width="{z(s[2] + 2 * extra)}" '
                f'stroke-linecap="round" stroke-linejoin="round"/>')
    raise ValueError(art)


def gruppe(formen, farbe: str) -> str:
    rand = [_el(s, RAND, RAND_W / 2) for s in formen]
    fell = [_el(s, farbe, 0.0) for s in formen]
    return "\n  ".join(rand + fell)


def svg(inhalt: str) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {B} {H}" width="{B}" height="{H}">\n'
            f'  {inhalt}\n</svg>\n')


def pose_svg(fern, koerper, details, vorne=None) -> str:
    teile = []
    if fern:
        teile.append(f"<!-- Beine hinten (abgewandte Seite) -->\n  {gruppe(fern, FELL_FERN)}")
    teile.append(f"<!-- Körper: Fellfarbe {FELL}, Saum {RAND} -->\n  {gruppe(koerper, FELL)}")
    teile.append("<!-- Details -->\n  " + "\n  ".join(details))
    if vorne:
        teile.append(f"<!-- Vorderbein vorne, mit eigenem Saum -->\n  {gruppe(vorne, FELL)}")
    return svg("\n  ".join(teile))


# --- Kopf -----------------------------------------------------------------------------

def _versatz(hx, hy):
    dx, dy = hx - KOPF0[0], hy - KOPF0[1]
    return lambda x, y: (x + dx, y + dy)


def kopf(hx, hy, ohren="normal"):
    p = _versatz(hx, hy)
    formen = [ell(*p(90, 38), 12.5, 12), ell(*p(91, 42.5), 13.5, 9.2)]
    if ohren == "flach":
        formen += [poly(p(79, 33), p(72.5, 24.5), p(86, 28.5)), poly(p(95, 27.5), p(105.5, 22), p(103.5, 32.5))]
    else:
        formen += [poly(p(79.5, 33), p(80.5, 18.5), p(88.5, 27.5)), poly(p(92, 27), p(100.5, 17), p(102.8, 32))]
    return formen


def kopf_details(hx, hy, ohren="normal"):
    p = _versatz(hx, hy)

    def pts(*ps):
        return " ".join(f"{z(x)},{z(y)}" for x, y in (p(*q) for q in ps))

    d = []
    if ohren == "flach":
        d.append(f'<polygon points="{pts((80, 31.5), (76, 26), (84.5, 28.6))}" fill="{OHR_INNEN}"/>')
        d.append(f'<polygon points="{pts((96.5, 28.3), (103, 24.5), (102, 30.8))}" fill="{OHR_INNEN}"/>')
    else:
        d.append(f'<polygon points="{pts((81.3, 30.5), (81.9, 22), (86.6, 27.6))}" fill="{OHR_INNEN}"/>')
        d.append(f'<polygon points="{pts((94, 27.6), (99.8, 20.6), (101.3, 30))}" fill="{OHR_INNEN}"/>')
    gx, gy = p(87, 30.5)
    d.append(f'<ellipse cx="{z(gx)}" cy="{z(gy)}" rx="5.5" ry="2" fill="{GLANZ}"/>')
    d.append(f'<polygon points="{pts((91.2, 43.2), (94, 43.2), (92.6, 45))}" fill="{NASE}" stroke="{NASE}" '
             f'stroke-width="0.6" stroke-linejoin="round"/>')
    mx, my = p(92.6, 45)
    d.append(f'<path d="M{z(mx)},{z(my)} q-1.2,1.6 -2.6,1 M{z(mx)},{z(my)} q1.2,1.6 2.6,1" fill="none" '
             f'stroke="{LINIE}" stroke-width="0.7" stroke-linecap="round"/>')
    haare = [((97.5, 44), (111, 41)), ((97.5, 45), (111.5, 45)), ((97, 46), (110, 49)),
             ((87.5, 44), (77, 41.5)), ((87.5, 45.2), (76.5, 45.5))]
    for a, b in haare:
        (x1, y1), (x2, y2) = p(*a), p(*b)
        d.append(f'<line x1="{z(x1)}" y1="{z(y1)}" x2="{z(x2)}" y2="{z(y2)}" stroke="{SCHNURR}" '
                 f'stroke-opacity="0.5" stroke-width="0.45" stroke-linecap="round"/>')
    return d


def glanz(cx, cy, rx, ry, rot=0.0):
    t = f' transform="rotate({z(rot)} {z(cx)} {z(cy)})"' if rot else ""
    return f'<ellipse cx="{z(cx)}" cy="{z(cy)}" rx="{z(rx)}" ry="{z(ry)}" fill="{GLANZ}"{t}/>'


# --- Beine ----------------------------------------------------------------------------

def vorderbein(gelenk, pfote, w=6.2, steif=False):
    (gx, gy), (px, py) = gelenk, pfote
    if steif:
        linie = strich([gelenk, (px, py - 1.5)], w)
    else:
        hub = max(0.0, BODEN_Y - py)
        knie = ((gx + px) / 2 + hub * 0.7, (gy + py) / 2)
        linie = strich([gelenk, knie, (px, py - 1.5)], w)
    return [linie, ell(px + 1, py, 4.3, PFOTE_RY)]


def hinterbein(huefte, pfote, w=6.2, steif=False):
    px, py = pfote
    if steif:
        linie = strich([huefte, (px, py - 1.5)], w)
    else:
        linie = strich([huefte, (px - 4, py - 10), (px, py - 1.5)], w)
    return [linie, ell(px + 1, py, 4.3, PFOTE_RY)]


# --- Posen ----------------------------------------------------------------------------

def schwanz_normal(dy=0.0, s=0.0):
    return kurve(f"M29,{z(55 + dy)} C17,{z(55 + dy)} 11,{z(44 + dy)} 13,{z(33 + dy)} "
                 f"S{z(20 + s)},{z(18 + dy)} {z(16 + s * 1.6)},{z(12 + dy)}", 5.4)


def schwanz_froh(spitze=0.0):
    return kurve(f"M29,54 C21,50 20,32 22,18 Q{z(23 + spitze)},9 {z(31 + spitze)},{z(11 - spitze)}", 5.4)


def stehen(dy=0.0, schwanz=None, beine=None):
    b = beine or {"vn": (77, 0), "vf": (71, 0), "hn": (38, 0), "hf": (44, 0)}

    def fuss(k):
        return (b[k][0], BODEN_Y - b[k][1])

    fern = vorderbein((71, 64 + dy), fuss("vf")) + hinterbein((44, 64 + dy), fuss("hf"))
    koerper = [schwanz or schwanz_normal(dy)]
    koerper += hinterbein((40, 64 + dy), fuss("hn"))
    koerper += [ell(56, 60 + dy, 29, 13.5), ell(38, 61 + dy, 12.5, 12), ell(78, 58 + dy, 11, 12),
                ell(84, 48 + dy, 9, 10)]
    koerper += kopf(90, 38 + dy)
    koerper += vorderbein((76, 64 + dy), fuss("vn"))
    details = [glanz(55, 51 + dy, 14, 2.2)] + kopf_details(90, 38 + dy)
    return pose_svg(fern, koerper, details)


AMPL = 6.5


def bein_lauf(u: float) -> tuple[float, float]:
    """Phase 0..1 → (Versatz der Pfote, Anhebung). 62 % Stand, 38 % Schwung."""
    if u < 0.62:
        s = u / 0.62
        return AMPL * (1 - 2 * s), 0.0
    s = (u - 0.62) / 0.38
    e = (1 - math.cos(math.pi * s)) / 2
    return -AMPL + 2 * AMPL * e, 3.4 * math.sin(math.pi * s)


GEHEN_BILDER = 8


def gehen_dy(i: int) -> float:
    return round(0.6 * math.cos(4 * math.pi * i / GEHEN_BILDER), 1)


def gehen(i: int) -> str:
    t = i / GEHEN_BILDER
    beine = {}
    # Kreuzgang wie bei Katzen: hinten nah, vorne nah, hinten fern, vorne fern
    for name, basis, phase in (("hn", 38, 0.0), ("vn", 77, 0.25), ("hf", 44, 0.5), ("vf", 71, 0.75)):
        dx, hub = bein_lauf((t + phase) % 1)
        beine[name] = (basis + dx, hub)
    dy = gehen_dy(i)
    return stehen(dy, schwanz_normal(dy, 1.6 * math.sin(2 * math.pi * t)), beine)


SITZ_KOPF = (80, 31)


def sitzen(pfote_hoch=None, kopf_pos=SITZ_KOPF) -> str:
    fern = vorderbein((69, 66), (69, BODEN_Y))
    koerper = [kurve("M34,82 Q42,87 60,86.4 T86,85.5", 5.0),
               ell(48, 74.5, 17, 14.4), ell(62, 62, 12.5, 19, -18), ell(71, 58, 10, 13), ell(76, 44, 8.5, 9.5),
               ell(40, BODEN_Y - 0.3, 8.5, PFOTE_RY + 0.3)]
    koerper += kopf(*kopf_pos)
    if pfote_hoch:
        (px, py) = pfote_hoch
        vorne = [strich([(73, 64), (px - 5, (64 + py) / 2 + 3), (px - 1, py + 1)], 6.0), ell(px, py, 4, 3)]
    else:
        vorne = vorderbein((74, 66), (75, BODEN_Y))
    details = [glanz(47, 66, 8, 2.2, -25), glanz(60, 50, 3, 6, -18)] + kopf_details(*kopf_pos)
    return pose_svg(fern, koerper, details, vorne)


SCHLAF_KOPF = (80, 70)


def schlafen() -> str:
    koerper = [kurve("M30,82 Q40,86.6 66,86.2 T97,83", 5.0), ell(58, 76.5, 30, 12.4), ell(40, 74, 14, 13)]
    koerper += kopf(*SCHLAF_KOPF)
    details = [glanz(56, 68, 15, 2.2)] + kopf_details(*SCHLAF_KOPF)
    return pose_svg([], koerper, details)


STRECK_KOPF = (90, 36)


def strecken() -> str:
    fern = vorderbein((71, 60), (73, BODEN_Y - 1)) + hinterbein((45, 60), (46, BODEN_Y - 1))
    koerper = [kurve("M29,52 C19,56 15,67 18,80", 5.2),
               ell(56, 56, 30, 12), ell(38, 57, 11.5, 11), ell(78, 54, 11, 11.5), ell(84, 45, 9, 10)]
    koerper += kopf(*STRECK_KOPF)
    koerper += hinterbein((40, 60), (37, BODEN_Y)) + vorderbein((76, 60), (80, BODEN_Y))
    details = [glanz(55, 47.5, 14, 2.2)] + kopf_details(*STRECK_KOPF)
    return pose_svg(fern, koerper, details)


BUCKEL_KOPF = (91, 49)


def buckel() -> str:
    fern = vorderbein((70, 60), (70, BODEN_Y), steif=True) + hinterbein((46, 60), (47, BODEN_Y), steif=True)
    koerper = [kurve("M31,46 C24,38 23,24 27,13", 9.0),
               ell(57, 51, 26, 15.5), ell(41, 56, 10, 10), ell(74, 56, 10, 11), ell(82, 53, 8, 9)]
    for x in (40, 46, 52, 58, 64, 70):
        oben = 51 - 15.5 * math.sqrt(max(0.0, 1 - ((x - 57) / 26) ** 2))
        koerper.append(poly((x - 2.6, oben + 2.2), (x - 0.4, oben - 3.6), (x + 2.4, oben + 2.2)))
    koerper += kopf(*BUCKEL_KOPF, ohren="flach")
    koerper += hinterbein((40, 60), (37, BODEN_Y), steif=True) + vorderbein((76, 60), (78, BODEN_Y), steif=True)
    details = kopf_details(*BUCKEL_KOPF, ohren="flach")
    return pose_svg(fern, koerper, details)


PUTZ_KOPF_1 = (81, 35)
PUTZ_KOPF_2 = (81, 36)


# --- Gesichtsteile (gezeichnet auf KOPF0, verschoben per Bauplan) -------------------

AUGEN = ((85.0, 37.5, 3.4, 3.9), (95.6, 37.0, 2.9, 3.6))


def augen(art: str) -> str:
    d = []
    for x, y, rx, ry in AUGEN:
        if art in ("offen", "rund", "halb"):
            d.append(f'<ellipse cx="{z(x)}" cy="{z(y)}" rx="{z(rx)}" ry="{z(ry)}" fill="{AUGE}" '
                     f'stroke="{PUPILLE}" stroke-width="0.5"/>')
            d.append(f'<ellipse cx="{z(x)}" cy="{z(y + ry * 0.45)}" rx="{z(rx * 0.75)}" ry="{z(ry * 0.4)}" '
                     f'fill="{AUGE_TIEF}" fill-opacity="0.6"/>')
            if art == "rund":
                d.append(f'<ellipse cx="{z(x + 0.3)}" cy="{z(y + 0.2)}" rx="{z(rx * 0.62)}" ry="{z(ry * 0.7)}" '
                         f'fill="{PUPILLE}"/>')
            else:
                d.append(f'<ellipse cx="{z(x + 0.3)}" cy="{z(y)}" rx="0.95" ry="{z(ry * 0.82)}" fill="{PUPILLE}"/>')
            d.append(f'<circle cx="{z(x - 1.1)}" cy="{z(y - 1.4)}" r="0.85" fill="#FFFFFF"/>')
            if art == "halb":
                l, r, o = x - rx - 0.6, x + rx + 0.6, y - ry - 0.6
                d.append(f'<path d="M{z(l)},{z(o)} H{z(r)} V{z(y - 0.2)} Q{z(x)},{z(y + 0.9)} {z(l)},{z(y - 0.2)} Z" '
                         f'fill="{FELL}"/>')
                d.append(f'<path d="M{z(x - rx)},{z(y - 0.1)} Q{z(x)},{z(y + 0.9)} {z(x + rx)},{z(y - 0.1)}" '
                         f'fill="none" stroke="{LINIE}" stroke-width="0.8" stroke-linecap="round"/>')
        elif art == "zu":
            d.append(f'<path d="M{z(x - rx)},{z(y + 0.4)} Q{z(x)},{z(y + 2.6)} {z(x + rx)},{z(y + 0.4)}" '
                     f'fill="none" stroke="{LINIE}" stroke-width="1.1" stroke-linecap="round"/>')
        elif art == "froh":
            d.append(f'<path d="M{z(x - rx + 0.2)},{z(y + 1.2)} Q{z(x)},{z(y - 2.4)} {z(x + rx - 0.2)},{z(y + 1.2)}" '
                     f'fill="none" stroke="{AUGE}" stroke-width="1.3" stroke-linecap="round"/>')
    return svg("\n  ".join(d))


def mund(art: str) -> str:
    if art == "auf":
        return svg(f'<ellipse cx="92.6" cy="47.2" rx="1.9" ry="1.5" fill="{MUND}"/>')
    if art == "fauchen":
        return svg(f'<ellipse cx="92.6" cy="47.8" rx="3.1" ry="2.5" fill="{MUND}"/>\n  '
                   f'<polygon points="90.9,45.7 91.5,47.6 92.1,45.7" fill="#F4F2EC"/>\n  '
                   f'<polygon points="93.1,45.7 93.7,47.6 94.3,45.7" fill="#F4F2EC"/>')
    if art == "zunge":
        return svg(f'<ellipse cx="93" cy="47.3" rx="1.5" ry="1.1" fill="{ZUNGE}"/>')
    raise ValueError(art)


# --- Herkunft -------------------------------------------------------------------------

def herkunft() -> str:
    rnd = np.random.default_rng(7)
    sterne = []
    for _ in range(38):
        x, y = rnd.uniform(10, 502), rnd.uniform(10, 330)
        if (x - 330) ** 2 + (y - 170) ** 2 < 110 ** 2:
            continue
        r = rnd.uniform(0.7, 1.9)
        sterne.append(f'<circle cx="{z(x)}" cy="{z(y)}" r="{z(r)}" fill="#F4EED6" '
                      f'fill-opacity="{z(rnd.uniform(0.35, 0.9))}"/>')
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512" width="512" height="512">
  <defs>
    <linearGradient id="himmel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#171B33"/>
      <stop offset="0.65" stop-color="#363B68"/>
      <stop offset="1" stop-color="#5B5583"/>
    </linearGradient>
    <radialGradient id="schein" cx="0.5" cy="0.5" r="0.5">
      <stop offset="0" stop-color="#F4EED6" stop-opacity="0.45"/>
      <stop offset="1" stop-color="#F4EED6" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="512" height="512" fill="url(#himmel)"/>
  {chr(10).join('  ' + s for s in sterne).strip()}
  <circle cx="330" cy="170" r="160" fill="url(#schein)"/>
  <circle cx="330" cy="170" r="74" fill="#F2ECD3"/>
  <circle cx="306" cy="148" r="13" fill="#E3DBBE"/>
  <circle cx="352" cy="196" r="17" fill="#E3DBBE"/>
  <circle cx="356" cy="140" r="7" fill="#E3DBBE"/>
  <circle cx="300" cy="200" r="6" fill="#E3DBBE"/>
  <!-- Dächer -->
  <path d="M0,420 L70,360 L140,420 L140,512 L0,512 Z" fill="#1A1C2B"/>
  <path d="M110,440 L215,350 L320,440 L320,512 L110,512 Z" fill="#141622"/>
  <rect x="250" y="360" width="22" height="48" fill="#141622"/>
  <path d="M290,455 L400,380 L512,455 L512,512 L290,512 Z" fill="#1A1C2B"/>
  <rect x="198" y="440" width="34" height="30" rx="3" fill="#F0C86A" fill-opacity="0.85"/>
  <rect x="214" y="440" width="2" height="30" fill="#141622"/>
  <rect x="198" y="454" width="34" height="2" fill="#141622"/>
  <rect x="420" y="470" width="26" height="22" rx="3" fill="#F0C86A" fill-opacity="0.55"/>
</svg>
"""


# --- Töne -----------------------------------------------------------------------------
# Warm und rau statt schrill: tiefe Grundtöne und Formanten, ein kehliger Unterton,
# leises Knarzen (unregelmäßige Pulse) und zum Schluss ein Tiefpass gegen spitze Höhen.

SR = 22050


def wav(name: str, x: np.ndarray, pegel: float = 0.6) -> None:
    x = x / (np.max(np.abs(x)) + 1e-9) * pegel
    daten = (np.clip(x, -1, 1) * 32767).astype("<i2")
    (ZIEL / "toene").mkdir(parents=True, exist_ok=True)
    with wave.open(str(ZIEL / "toene" / f"{name}.wav"), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(daten.tobytes())


def huelle(n: int, an_s: float, ab_s: float) -> np.ndarray:
    t = np.arange(n) / SR
    dauer = n / SR
    return np.minimum(1, t / an_s) * np.minimum(1, (dauer - t) / ab_s)


def _glatt(rnd, n: int, schritte: int) -> np.ndarray:
    """Langsames Zufallsrauschen (-1..1) für Schwankungen der Stimme."""
    punkte = rnd.uniform(-1, 1, schritte + 2)
    return np.interp(np.linspace(0, schritte + 1, n), np.arange(schritte + 2), punkte)


def _knarz(rnd, n: int, takt: float, tiefe: float) -> np.ndarray:
    """Weiche, leicht unregelmäßige Pulse – das „Kratzige“ in der Stimme."""
    f = takt * (1 + 0.25 * _glatt(rnd, n, 12))
    puls = (0.5 + 0.5 * np.sin(2 * np.pi * np.cumsum(f) / SR)) ** 3
    return 1 - tiefe + tiefe * puls


def _tiefpass(x: np.ndarray, grenze: float, ordnung: int = 4) -> np.ndarray:
    from scipy import signal

    b, a = signal.butter(ordnung, grenze, btype="low", fs=SR)
    return signal.lfilter(b, a, x)


def _hauch(rnd, n: int, unten: float, oben: float) -> np.ndarray:
    from scipy import signal

    b, a = signal.butter(2, [unten, oben], btype="band", fs=SR)
    h = signal.lfilter(b, a, rnd.standard_normal(n))
    return h / (np.max(np.abs(h)) + 1e-9)


def miau(dauer, f_tief, f_hoch, f_ende, rnd) -> np.ndarray:
    n = int(SR * dauer)
    t = np.linspace(0, 1, n)
    f0 = np.interp(t, [0, 0.2, 0.55, 1], [f_tief, f_hoch, f_hoch * 0.95, f_ende])
    f0 = f0 * (1 + 0.025 * _glatt(rnd, n, int(dauer * 40)))           # Zittern
    formant = np.interp(t, [0, 0.3, 0.7, 1], [1500, 1050, 800, 560])  # „i“ → „a“ → „u“, tief
    phase = 2 * np.pi * np.cumsum(f0) / SR
    x = np.zeros(n)
    for k in range(1, 13):
        w = 0.3 / k + 1.2 * np.exp(-((k * f0 - formant) / 420) ** 2) / math.sqrt(k)
        x += w * np.sin(k * phase)
    x += 0.35 * np.sin(phase / 2)                                     # kehliger Unterton
    x = x / np.max(np.abs(x)) * _knarz(rnd, n, 34, 0.35)
    x += 0.14 * _hauch(rnd, n, 300, 2400)
    return _tiefpass(x, 3000) * huelle(n, 0.05, 0.14)


def toene() -> None:
    from scipy import signal

    rnd = np.random.default_rng(3)
    wav("miau_1", miau(0.46, 330, 520, 360, rnd), 0.55)
    wav("miau_2", miau(0.38, 380, 560, 410, rnd), 0.55)
    wav("miau_3", miau(0.55, 300, 480, 320, rnd), 0.55)
    for i, (f1, f2) in enumerate(((220, 290), (250, 320)), 1):
        n = int(SR * 0.3)
        f0 = np.linspace(f1, f2, n)
        phase = 2 * np.pi * np.cumsum(f0) / SR
        x = sum(np.sin(k * phase) / k for k in range(1, 9)) + 0.4 * np.sin(phase / 2)
        x = x * _knarz(rnd, n, 25, 0.75) + 0.1 * _hauch(rnd, n, 200, 1500)
        wav(f"prrt_{i}", _tiefpass(x, 1800) * huelle(n, 0.03, 0.08), 0.5)
    n = int(SR * 0.6)
    b, a = signal.butter(2, [1000, 4000], btype="band", fs=SR)
    x = signal.lfilter(b, a, rnd.standard_normal(n)) * _knarz(rnd, n, 18, 0.3)
    wav("fauchen", _tiefpass(x, 4500, 2) * huelle(n, 0.05, 0.22), 0.38)
    n = int(SR * 1.4)
    t = np.arange(n) / SR
    b, a = signal.butter(3, 380, btype="low", fs=SR)
    x = signal.lfilter(b, a, rnd.standard_normal(n)) * (np.abs(np.sin(np.pi * 24 * t)) ** 3)
    x += 0.3 * np.sin(2 * np.pi * 48 * t) * (np.abs(np.sin(np.pi * 24 * t)) ** 3)
    wav("schnurren", x * huelle(n, 0.2, 0.4), 0.45)
    n = int(SR * 0.07)
    f0 = np.linspace(150, 70, n)
    wav("tapp", np.sin(2 * np.pi * np.cumsum(f0) / SR) * huelle(n, 0.004, 0.05), 0.35)


# --- Zubehör: Fledermausflügel (nach Stefans Skizze) ---------------------------------
# Schwarze Haut, lila Knochen und Kanten. Zwei Bilder: der nahe Flügel liegt vor dem
# Körper, der ferne (dunkler, etwas kleiner) dahinter. Getragen ab abends (Regeln).

FLUEGEL = "#141218"
FLUEGEL_FERN = "#0C0B0F"
FLUEGEL_LILA = "#9B52C9"
FLUEGEL_LILA_FERN = "#5E3478"
FB, FH = 100, 70
ANSATZ = (91, 49)        # Stelle im Flügelbild, die am Rücken sitzt (rechte Kante)


def fluegel(fern: bool = False) -> str:
    fl = FLUEGEL_FERN if fern else FLUEGEL
    li = FLUEGEL_LILA_FERN if fern else FLUEGEL_LILA
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {FB} {FH}" width="{FB}" height="{FH}">\n'
            f'  <path d="M94,30 L18,3 Q24,20 2,24 Q22,36 10,46 Q40,52 66,68 L88,68 Z" fill="{fl}" '
            f'stroke="#3A2C46" stroke-width="0.9" stroke-linejoin="round"/>\n'
            f'  <path d="M92,32 L2,24 M92,33 L10,46 M91,36 L66,68" fill="none" stroke="{li}" '
            f'stroke-width="1.6" stroke-linecap="round"/>\n'
            f'  <path d="M18,3 L94,30 L88,68" fill="none" stroke="{li}" stroke-width="2.6" '
            f'stroke-linecap="round" stroke-linejoin="round"/>\n'
            f'</svg>\n')


def _faktor() -> float:
    """Größe der Posen aus dem Bauplan („faktor“ je Quelle, z. B. im Editor auf 1,6 gestellt)."""
    plan = ZIEL / "bauplan.json"
    if not plan.exists():
        return 1.0
    quellen = json.loads(plan.read_text(encoding="utf-8")).get("quellen", {})
    return float(next(iter(quellen.values()), {}).get("faktor", 1.0))


def _platz(sx, sy, breite, winkel=0.0, hinten=False) -> dict:
    """Ansatz des Flügels auf die Schulter (sx, sy) legen → Mitte relativ zum Fußpunkt.
    Eingaben in viewBox-Einheiten, Ergebnis in logischen Pixeln (× Faktor)."""
    f = _faktor()
    k = breite / FB
    mx, my = FB / 2 - ANSATZ[0], FH / 2 - ANSATZ[1]
    return {"x": round((sx + mx * k - B / 2) * f, 1), "y": round((sy + my * k - G) * f, 1),
            "breite": round(breite * f, 1), "winkel": round(winkel, 1), "hinten": hinten, "aus": False}


def fluegel_posen(fern: bool) -> dict:
    posen = {}

    def setze(namen, sx, sy, b=44.0, w=0.0):
        for n in namen:
            if fern:
                posen[f"{n}:0"] = _platz(sx + 5, sy - 2, b * 0.9, w + 7, True)
            else:
                posen[f"{n}:0"] = _platz(sx, sy, b, w)

    setze(["stehen_a", "stehen_b", "stehen_c", "stehen_zu", "anschauen", "sprechen_auf",
           "freuen_a", "freuen_b"], 71, 50)
    for i in range(GEHEN_BILDER):
        setze([f"gehen_{i + 1}"], 71, 50 + gehen_dy(i), w=6 * math.sin(2 * math.pi * i / GEHEN_BILDER))
    setze(["sitzen", "sitzen_halb", "sitzen_zu", "putzen_1", "putzen_2"], 58, 50, w=14)
    setze(["schlafen_a", "schlafen_b"], 60, 66, b=34, w=-6)
    setze(["strecken", "strecken_halb"], 71, 46, w=-8)
    setze(["landen"], 70.6, 53, b=46)
    setze(["buckel"], 66, 40, w=8)
    setze(["buckel_1"], 67.2, 40, w=8)
    setze(["buckel_2"], 64.8, 40, w=8)
    return posen


def zubehoer_plan() -> dict:
    return {
        "fluegel": {"datei": "zubehoer/fluegel.svg", "sitz": "ueber_kopf", "gruppe": "fluegel",
                    "immer": False, "posen": fluegel_posen(False)},
        "fluegel_fern": {"datei": "zubehoer/fluegel_fern.svg", "sitz": "ueber_kopf", "gruppe": "fluegel_fern",
                         "immer": False, "posen": fluegel_posen(True)},
    }


# --- Bauplan --------------------------------------------------------------------------

def _off(pos):
    return (round(pos[0] - KOPF0[0], 1), round(pos[1] - KOPF0[1], 1))


def quelle(datei, augen_art, off, mund_art=None, form=None):
    teile = [{"datei": f"teile/augen_{augen_art}.svg", "x": off[0], "y": off[1]}]
    if mund_art:
        teile.append({"datei": f"teile/mund_{mund_art}.svg", "x": off[0], "y": off[1]})
    q = {"datei": f"teile/{datei}.svg", "teile": teile}
    if form:
        q["form"] = form
    return q


def bauplan() -> dict:
    sitz, schlaf, streck, buck = _off(SITZ_KOPF), _off(SCHLAF_KOPF), _off(STRECK_KOPF), _off(BUCKEL_KOPF)
    q = {
        "stehen_a": quelle("stehen_a", "offen", (0, 0)),
        "stehen_b": quelle("stehen_b", "offen", (0, 0)),
        "stehen_c": quelle("stehen_c", "offen", (0, 0)),
        "stehen_zu": quelle("stehen_b", "zu", (0, 0)),
    }
    for i in range(GEHEN_BILDER):
        q[f"gehen_{i + 1}"] = quelle(f"gehen_{i + 1}", "offen", (0, gehen_dy(i)))
    q |= {
        "sitzen": quelle("sitzen", "offen", sitz),
        "sitzen_halb": quelle("sitzen", "halb", sitz),
        "sitzen_zu": quelle("sitzen", "zu", sitz),
        "schlafen_a": quelle("schlafen", "zu", schlaf),
        "schlafen_b": quelle("schlafen", "zu", schlaf, form={"hoehe": 1.03}),
        "strecken": quelle("strecken", "rund", streck),
        "strecken_halb": quelle("strecken", "halb", streck),
        "landen": quelle("stehen_b", "zu", (0, 0), form={"breite": 1.06, "hoehe": 0.88}),
        "anschauen": quelle("stehen_b", "rund", (0, 0)),
        "sprechen_auf": quelle("stehen_b", "offen", (0, 0), "auf"),
        "buckel_1": quelle("buckel", "rund", buck, "fauchen", form={"x": 1.2}),
        "buckel_2": quelle("buckel", "rund", buck, "fauchen", form={"x": -1.2}),
        "buckel": quelle("buckel", "rund", buck),
        "freuen_a": quelle("freuen_a", "froh", (0, 0)),
        "freuen_b": quelle("freuen_b", "froh", (0, 0)),
        "putzen_1": quelle("putzen_1", "zu", _off(PUTZ_KOPF_1), "zunge"),
        "putzen_2": quelle("putzen_2", "zu", _off(PUTZ_KOPF_2)),
    }

    def anim(fps, namen, schleife=True):
        a = {"fps": fps, "bilder": [[n, 0, "normal"] for n in namen]}
        if not schleife:
            a["schleife"] = False
        return a

    a, b, c = "stehen_a", "stehen_b", "stehen_c"
    ruhe = [a, a, b, b, c, c, c, b, b, a, a, a, a, b, b, c, c, "stehen_zu", c, b, b, a, a, a]
    sitz_folge = ["sitzen"] * 7 + ["sitzen_halb", "sitzen_halb"] + ["sitzen"] * 5 + ["sitzen_zu"]
    return {
        "id": "hexe",
        "name": "Hexe",
        "skalierung": 2,
        "ausrichtung": "rahmen",
        "rahmen_px": [B * 2, H * 2],
        "blickrichtung": 1,
        "bewegung": {"art": "gehen"},
        "toene": {
            "sprechen": {"dateien": ["toene/miau_1.wav", "toene/miau_2.wav", "toene/miau_3.wav"],
                         "tonhoehe": 0.06},
            "freuen": {"dateien": ["toene/prrt_1.wav", "toene/prrt_2.wav"], "tonhoehe": 0.05},
            "erschrecken": {"dateien": ["toene/fauchen.wav"], "tonhoehe": 0.05},
            "landen": {"dateien": ["toene/tapp.wav"], "tonhoehe": 0.1},
            "schlafen": {"dateien": ["toene/schnurren.wav"], "tonhoehe": 0.03},
        },
        "portraet": {"pose": "sitzen", "hoehe": 160},
        "quellen": q,
        "referenz": ["stehen_b", 0],
        "animationen": {
            "ruhe": anim(4, ruhe),
            "bewegen": anim(14, [f"gehen_{i + 1}" for i in range(GEHEN_BILDER)]),
            "sitzen": anim(2, sitz_folge),
            "schlafen": anim(0.8, ["schlafen_a", "schlafen_b"]),
            "gezogen": anim(2, ["strecken"]),
            "fallen": anim(2, ["strecken"]),
            "springen": anim(2, ["strecken"]),
            "schweben": anim(1, ["strecken_halb"]),
            "landen": anim(4, ["landen"], schleife=False),
            "anschauen": anim(2, ["anschauen"]),
            "sprechen": anim(8, [b, "sprechen_auf", "sprechen_auf", b]),
            "freuen": anim(3, ["freuen_a", "freuen_b"]),
            "erschrecken": anim(12, ["buckel_1", "buckel_2", "buckel_1", "buckel_2", "buckel_1", "buckel"],
                                schleife=False),
            "putzen": anim(3, ["putzen_1", "putzen_2"]),
        },
        "herkunft": {"hintergrund": "herkunft.svg", "groesse": 768},
    }


# --- Los ------------------------------------------------------------------------------

def main() -> None:
    teile = ZIEL / "teile"
    teile.mkdir(parents=True, exist_ok=True)
    dateien = {
        "stehen_a": stehen(schwanz=schwanz_normal(0, 0)),
        "stehen_b": stehen(schwanz=schwanz_normal(0, 1.5)),
        "stehen_c": stehen(schwanz=schwanz_normal(0, 3.0)),
        "sitzen": sitzen(),
        "schlafen": schlafen(),
        "strecken": strecken(),
        "buckel": buckel(),
        "freuen_a": stehen(schwanz=schwanz_froh(0)),
        "freuen_b": stehen(schwanz=schwanz_froh(1.2)),
        "putzen_1": sitzen(pfote_hoch=(85, 44.5), kopf_pos=PUTZ_KOPF_1),
        "putzen_2": sitzen(pfote_hoch=(84, 48), kopf_pos=PUTZ_KOPF_2),
    }
    for i in range(GEHEN_BILDER):
        dateien[f"gehen_{i + 1}"] = gehen(i)
    for art in ("offen", "rund", "halb", "zu", "froh"):
        dateien[f"augen_{art}"] = augen(art)
    for art in ("auf", "fauchen", "zunge"):
        dateien[f"mund_{art}"] = mund(art)
    for name, inhalt in dateien.items():
        (teile / f"{name}.svg").write_text(inhalt, encoding="utf-8")
    (ZIEL / "herkunft.svg").write_text(herkunft(), encoding="utf-8")
    (ZIEL / "zubehoer").mkdir(exist_ok=True)
    (ZIEL / "zubehoer" / "fluegel.svg").write_text(fluegel(), encoding="utf-8")
    (ZIEL / "zubehoer" / "fluegel_fern.svg").write_text(fluegel(fern=True), encoding="utf-8")
    zplan = ZIEL / "zubehoer.json"
    if zplan.exists():
        print("zubehoer.json gibt es schon – unverändert gelassen")
    else:
        zplan.write_text(json.dumps(zubehoer_plan(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("zubehoer.json angelegt")
    toene()
    plan = ZIEL / "bauplan.json"
    if plan.exists():
        print("bauplan.json gibt es schon – unverändert gelassen")
    else:
        plan.write_text(json.dumps(bauplan(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("bauplan.json angelegt")
    print(f"{len(dateien)} SVG-Teile, Herkunft und Töne in {ZIEL}")


if __name__ == "__main__":
    main()
