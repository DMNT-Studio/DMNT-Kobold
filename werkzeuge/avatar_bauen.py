"""Baut einen Avatar-Ordner aus Quellbildern.

Aufruf:  python werkzeuge/avatar_bauen.py quellen/<name> [--ziel <ordner>]
         python werkzeuge/avatar_bauen.py quellen/zubehoer   (Kopfhörer usw. für alle Avatare)
         python werkzeuge/avatar_bauen.py --vorlagen quellen/<name> [--innen <gegenstand>]
             vorhandener Avatar mit Auge: Einzelposen als Vorlage (vorlagen/<id>/)
             neuer Ordner: Hüpf-Avatar anlegen – leere Rahmen je Pose, Bauplan,
             Start-verhalten.json, LIESMICH (Bilder setzt man danach im Avatar-Editor ein)
Ergebnis: src/dmnt_kobold/avatare/<id>/ (oder --ziel) mit avatar.json, frames/, toene/, …

Bauplan-Eintrag eines Frames: [Quelle, Pose-Nr, Augen-Effekt] oder
[Quelle, Pose-Nr, Augen-Effekt, Hand-Variante] (z. B. "daumen_runter").

Zwei Arten auszurichten:
- mit Auge (DMNT 9000): Größe und Lage über das rote Auge (siehe unten)
- ``"ausrichtung": "rahmen"``: jedes Bild ist ein Rahmen ``rahmen_px`` groß, der Fußpunkt
  liegt unten in der Mitte. Andere Größen werden auf die Rahmenbreite skaliert. Für
  Avatare ohne Auge (Hüpfer wie Sulfi oder Kiesel). Optional je Quelle ``"hinten"``:
  eigene Rückwand (Innenleben liegt dann zwischen Rückwand und Körper).

Vektorgrafik (SVG) und Rig aus Teilen (z. B. Kiesel):
- Eine ``.svg`` wird mit ``QSvgRenderer`` (PySide6) gerendert – die viewBox ist die
  Leinwand (es wird nicht zugeschnitten), Standard 2× viewBox, im Rahmen-Modus genau
  ``rahmen_px``. Das gilt für Posen, Rückwände, Zubehör/Innenleben und die Herkunft.
- Rig: Eine Quelle zeichnet ``datei`` (der Körper) und darüber ``"teile"`` (Augen, Mund,
  Glanz …), alle mit derselben viewBox. Je Teil: ``x``/``y`` (Versatz, logische Pixel),
  ``breite``/``hoehe`` (Faktor um die Mitte des Teils), ``deckkraft``. ``"form"`` gilt für
  die ganze Pose samt Rückwand: ``breite``/``hoehe`` (Faktor um den Fußpunkt),
  ``neigung`` (Grad, Spitze nach vorn +, nach hinten −), ``x``/``y`` (Versatz).
  So steckt die Farbe nur in einer Körper-Datei und jede Pose ist eine Zeile im Bauplan.
- ``"portraet": {"pose": "<quelle>", "hoehe": 160}``: Porträt (und Tray-Icon) aus einer
  Pose samt Rückwand und Innenleben.

Das Programm selbst kennt nur fertige Frames. Dieses Werkzeug erledigt alles davor:
- Bildbögen in Einzelbilder zerlegen (leere Spalten trennen die Posen)
- schwarzen Hintergrund entfernen und die Außenkontur wieder schwarz nachziehen
- alle Posen über die Augengröße auf denselben Maßstab bringen
- Fußpunkt (unten) und Körpermitte (Auge) ausrichten
- Augen-Effekte rechnen (hell, dunkel, aus, grell, puls) für Ausdrücke
- Herkunfts-Bild zusammensetzen, Töne synthetisieren
- verhalten.json und Körper (bewegung, partikel, toene) gegen den Katalog prüfen
  (Fehler brechen ab, bevor etwas gelöscht wird)
- Töne aus Dateien übernehmen (.ogg wird zu .wav – mit soundfile oder ffmpeg)

Gerenderte Figuren (z. B. DMNT 9000 aus dem 3D-Modell, werkzeuge/figur3d/):
- ``"raster": true`` je Quelle: der Bogen besteht aus ``bilder`` gleich breiten Zellen
  (keine Suche nach leeren Spalten - Stein und Strahl gehören zur Pose). ``"fusspunkt": [x, y]``
  in Zellen-Pixeln ist der Anker (Boden unter der Figur), statt Augenmitte/Unterkante.
- ``"massstab": "fest"``: alle Bilder bekommen denselben Faktor (Referenzpose auf ``hoehe``),
  statt je Bild über die Augengröße - so wackelt eine 8-Bild-Bewegung nicht. Raster braucht "fest".

Was gebaut wird, steht in ``bauplan.json`` im Quellordner.
Benötigt (nur zum Bauen): Pillow, numpy, scipy.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "src"))
from dmnt_kobold import effekte, katalog  # noqa: E402
from dmnt_kobold.toene import schreibe_wav, synthese  # noqa: E402

# --- Hintergrund und Zerlegen ------------------------------------------------


def schwarz_entfernen(rgb: np.ndarray, toleranz: int = 26, kontur_px: int = 4) -> np.ndarray:
    """Schwarzer Hintergrund → transparent. Nur was vom Rand her erreichbar ist,
    damit schwarze Flächen im Körper bleiben. Die dabei verlorene schwarze
    Außenkontur wird um ``kontur_px`` wieder angesetzt."""
    dunkel = rgb.max(axis=2) <= toleranz
    beschriftet, _ = ndimage.label(dunkel)
    rand = np.unique(np.concatenate([beschriftet[0], beschriftet[-1], beschriftet[:, 0], beschriftet[:, -1]]))
    hintergrund = np.isin(beschriftet, rand[rand > 0])
    figur = ~hintergrund
    # winzige Inseln (Rauschen) entfernen
    inseln, n = ndimage.label(figur)
    if n:
        groessen = ndimage.sum(figur, inseln, range(1, n + 1))
        figur = np.isin(inseln, 1 + np.flatnonzero(groessen >= 400))
    mit_kontur = ndimage.binary_dilation(figur, iterations=kontur_px)
    rgba = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    rgba[..., :3] = np.where(figur[..., None], rgb, 0)
    alpha = mit_kontur.astype(np.float32)
    alpha = ndimage.gaussian_filter(alpha, 0.8)            # weiche Kante
    rgba[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    return rgba


def weiss_entfernen(rgb: np.ndarray, toleranz: int = 235, nur_groesstes: bool = True) -> np.ndarray:
    """Weißer Hintergrund → transparent (vom Rand her). Mit ``nur_groesstes``
    bleibt nur das größte zusammenhängende Teil (z. B. ohne Noten und Striche)."""
    hell = rgb.min(axis=2) >= toleranz
    beschriftet, _ = ndimage.label(hell)
    rand = np.unique(np.concatenate([beschriftet[0], beschriftet[-1], beschriftet[:, 0], beschriftet[:, -1]]))
    figur = ~np.isin(beschriftet, rand[rand > 0])
    if nur_groesstes:
        teile, n = ndimage.label(figur)
        groessen = ndimage.sum(figur, teile, range(1, n + 1))
        figur = ndimage.binary_fill_holes(teile == 1 + int(np.argmax(groessen))) & figur
    alpha = ndimage.gaussian_filter(figur.astype(np.float32), 0.7)
    rgba = np.zeros(rgb.shape[:2] + (4,), np.uint8)
    rgba[..., :3] = rgb
    rgba[..., 3] = np.clip(alpha * 255, 0, 255).astype(np.uint8)
    return rgba


def laden(pfad: Path, hintergrund: str | None, toleranz: int | None = None) -> np.ndarray:
    """``hintergrund``: None (Bild hat Transparenz), "schwarz" oder "weiss".
    Bei "weiss" auch für eingebrannte Karomuster: ``toleranz`` z. B. 220.
    SVG: gerendert in doppelter viewBox-Größe (Hintergrund gibt es dort nicht)."""
    if ist_svg(pfad):
        return rig_bild(pfad)
    im = Image.open(pfad)
    if hintergrund == "schwarz":
        return schwarz_entfernen(np.array(im.convert("RGB")))
    if hintergrund == "weiss":
        return weiss_entfernen(np.array(im.convert("RGB")), toleranz or 235)
    return np.array(im.convert("RGBA"))


def zubehoer_bauen(quelle: Path, ziel: Path, breite_px: int = 240) -> None:
    """Gemeinsames Zubehör (für alle Avatare): quellen/zubehoer/*.png → src/.../zubehoer/."""
    ziel.mkdir(parents=True, exist_ok=True)
    for datei in sorted(quelle.glob("*.png")):
        bild = zuschneiden(weiss_entfernen(np.array(Image.open(datei).convert("RGB"))))
        Image.fromarray(skalieren(bild, breite_px / bild.shape[1]), "RGBA").save(ziel / datei.name, optimize=True)
        print(f"  Zubehör: {datei.name}")


def zerlegen(rgba: np.ndarray, anzahl: int) -> list[np.ndarray]:
    """Teilt einen Bogen an leeren Spalten in ``anzahl`` Posen (größte Abschnitte)."""
    belegt = (rgba[..., 3] > 20).any(axis=0)
    abschnitte, start = [], None
    for x, b in enumerate(np.append(belegt, False)):
        if b and start is None:
            start = x
        elif not b and start is not None:
            abschnitte.append((start, x))
            start = None
    abschnitte = sorted(sorted(abschnitte, key=lambda a: a[1] - a[0], reverse=True)[:anzahl])
    if len(abschnitte) != anzahl:
        raise SystemExit(f"Erwartet {anzahl} Posen, gefunden {len(abschnitte)}")
    return [zuschneiden(rgba[:, a:b]) for a, b in abschnitte]


def zuschneiden(rgba: np.ndarray, rand: int = 2) -> np.ndarray:
    ys, xs = np.nonzero(rgba[..., 3] > 20)
    y0, y1 = max(ys.min() - rand, 0), min(ys.max() + rand + 1, rgba.shape[0])
    x0, x1 = max(xs.min() - rand, 0), min(xs.max() + rand + 1, rgba.shape[1])
    return rgba[y0:y1, x0:x1].copy()


def raster_zerlegen(rgba: np.ndarray, anzahl: int, fusspunkt=None) -> list[tuple[np.ndarray, tuple[float, float]]]:
    """Bogen aus ``anzahl`` gleich breiten Zellen → [(zugeschnittene Pose, Anker in deren Pixeln)].
    ``fusspunkt`` (x, y) in Zellen-Pixeln, Standard: unten in der Mitte."""
    h, w = rgba.shape[:2]
    if anzahl < 1 or w % anzahl:
        raise BauFehler(f"Raster: Breite {w} lässt sich nicht in {anzahl} gleiche Zellen teilen")
    zb = w // anzahl
    fx, fy = (float(fusspunkt[0]), float(fusspunkt[1])) if fusspunkt else (zb / 2, float(h))
    ergebnis = []
    for i in range(anzahl):
        zelle = rgba[:, i * zb:(i + 1) * zb]
        ys, xs = np.nonzero(zelle[..., 3] > 20)
        if not len(xs):
            raise BauFehler(f"Raster: Zelle {i + 1} von {anzahl} ist leer")
        y0, x0 = max(int(ys.min()) - 2, 0), max(int(xs.min()) - 2, 0)
        y1, x1 = min(int(ys.max()) + 3, h), min(int(xs.max()) + 3, zb)
        ergebnis.append((zelle[y0:y1, x0:x1].copy(), (fx - x0, fy - y0)))
    return ergebnis


# --- SVG und Rig ---------------------------------------------------------------------

_QT: list = []


def ist_svg(pfad: Path) -> bool:
    return pfad.suffix.lower() == ".svg"


def _qt_bereit() -> None:
    """QSvgRenderer/QPainter brauchen eine Qt-Anwendung (im Editor gibt es sie schon)."""
    from PySide6.QtGui import QGuiApplication

    if QGuiApplication.instance() is None and not _QT:
        import os

        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        _QT.append(QGuiApplication(["avatar_bauen"]))


def _svg(pfad: Path):
    from PySide6.QtSvg import QSvgRenderer

    _qt_bereit()
    if not pfad.is_file():
        raise BauFehler(f"Bild „{pfad.name}“ fehlt ({pfad})")
    r = QSvgRenderer(str(pfad))
    if not r.isValid():
        raise BauFehler(f"SVG „{pfad.name}“ lässt sich nicht lesen (kein gültiges SVG)")
    return r


def _als_array(img) -> np.ndarray:
    from PySide6.QtGui import QImage

    img = img.convertToFormat(QImage.Format.Format_RGBA8888)
    w, h = img.width(), img.height()
    roh = np.frombuffer(img.constBits(), np.uint8, count=img.sizeInBytes())
    return roh.reshape(h, img.bytesPerLine())[:, :w * 4].reshape(h, w, 4).copy()


_TEIL_MITTE: dict[Path, tuple[float, float]] = {}


def _teil_mitte(pfad: Path) -> tuple[float, float]:
    """Mitte der sichtbaren Fläche eines Teils (viewBox-Koordinaten) – um sie wird skaliert."""
    if pfad not in _TEIL_MITTE:
        r = _svg(pfad)
        vb = r.viewBoxF()
        bild = rig_bild(pfad, breite_px=round(vb.width() * 2))
        ys, xs = np.nonzero(bild[..., 3] > 10)
        if len(xs):
            _TEIL_MITTE[pfad] = (vb.x() + (xs.min() + xs.max()) / 4, vb.y() + (ys.min() + ys.max()) / 4)
        else:
            _TEIL_MITTE[pfad] = (vb.center().x(), vb.center().y())
    return _TEIL_MITTE[pfad]


def rig_bild(datei: Path, breite_px: int | None = None, form: dict | None = None,
             teile: list | tuple = (), ordner: Path | None = None) -> np.ndarray:
    """SVG (Körper) plus Teile darüber → RGBA. Leinwand = viewBox von ``datei`` in
    ``breite_px`` Breite (Standard 2×). ``form`` wirkt um den Fußpunkt (unten Mitte)."""
    import math

    from PySide6.QtCore import QRectF, Qt
    from PySide6.QtGui import QImage, QPainter, QTransform

    r = _svg(datei)
    vb = r.viewBoxF()
    k = breite_px / vb.width() if breite_px else 2.0
    w, h = max(1, round(vb.width() * k)), max(1, round(vb.height() * k))
    img = QImage(w, h, QImage.Format.Format_ARGB32_Premultiplied)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
    basis = QTransform().scale(k, k).translate(-vb.x(), -vb.y())
    if form:
        fx, fy = vb.center().x(), vb.bottom()
        t = QTransform()
        t.translate(fx + float(form.get("x", 0)), fy + float(form.get("y", 0)))
        t.shear(-math.tan(math.radians(float(form.get("neigung", 0)))), 0)
        t.scale(float(form.get("breite", 1)), float(form.get("hoehe", 1)))
        t.translate(-fx, -fy)
        basis = t * basis
    flaeche = QRectF(vb)
    p.setTransform(basis)
    r.render(p, flaeche)
    for teil in teile:
        pfad = (ordner or datei.parent) / teil["datei"]
        tr = _svg(pfad)
        cx, cy = _teil_mitte(pfad)
        t = QTransform()
        t.translate(cx + float(teil.get("x", 0)), cy + float(teil.get("y", 0)))
        t.scale(float(teil.get("breite", 1)), float(teil.get("hoehe", 1)))
        t.translate(-cx, -cy)
        p.setTransform(t * basis)
        p.setOpacity(float(teil.get("deckkraft", 1)))
        tr.render(p, QRectF(tr.viewBoxF()))
        p.setOpacity(1.0)
    p.end()
    return _als_array(img)


def _pil_bild(pfad: Path, breite_px: int | None = None) -> Image.Image:
    """Rasterbild oder SVG als PIL-Bild (SVG in ``breite_px`` Breite)."""
    if ist_svg(pfad):
        return Image.fromarray(rig_bild(pfad, breite_px), "RGBA")
    return Image.open(pfad)


# --- Auge ------------------------------------------------------------------------


def auge_finden(rgba: np.ndarray) -> tuple[float, float, float]:
    """Mitte und Radius des roten Auges (größter roter Fleck)."""
    r, g, b = (rgba[..., i].astype(int) for i in range(3))
    rot = (r > 140) & (g < 120) & (b < 100) & (r - g > 90) & (rgba[..., 3] > 200)
    marken, n = ndimage.label(rot)
    if not n:
        raise SystemExit("Kein rotes Auge gefunden")
    groessen = ndimage.sum(rot, marken, range(1, n + 1))
    groesster = marken == 1 + int(np.argmax(groessen))
    ys, xs = np.nonzero(groesster)
    return (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2, max(np.ptp(xs), np.ptp(ys)) / 2 + 1


def auge_effekt(rgba: np.ndarray, effekt: str) -> np.ndarray:
    if effekt == "normal":
        return rgba
    cx, cy, r = auge_finden(rgba)
    h, w = rgba.shape[:2]
    yy, xx = np.mgrid[0:h, 0:w]
    d = np.hypot(xx - cx, yy - cy)
    bild = rgba[..., :3].astype(np.float32)
    kern = np.clip((r * 1.08 - d) / 2.0, 0, 1)[..., None]      # weich bis zum Ring

    def glimmen(staerke: float, weite: float = 2.3) -> None:
        nonlocal bild
        ring = (d > r * 1.45) & (d < r * weite)
        abfall = np.clip(1 - (d - r * 1.45) / (r * (weite - 1.45)), 0, 1) ** 1.6
        dunkel = (bild.max(axis=2) < 70)[..., None]
        zusatz = np.zeros_like(bild)
        zusatz[..., 0] = 255 * staerke * abfall
        zusatz[..., 1] = 40 * staerke * abfall
        bild = np.where(ring[..., None] & dunkel, np.clip(bild + zusatz, 0, 255), bild)

    if effekt in ("hell", "puls", "grell"):
        faktor = {"hell": 1.28, "puls": 1.12, "grell": 1.45}[effekt]
        bild = bild * (1 - kern) + np.clip(bild * faktor + 12, 0, 255) * kern
        glimmen({"hell": 0.55, "puls": 0.3, "grell": 0.85}[effekt])
        if effekt == "grell":
            hot = np.clip(1 - d / (r * 0.45), 0, 1)[..., None] ** 1.5
            bild = bild * (1 - hot) + np.array([255, 235, 170], np.float32) * hot
    elif effekt in ("dunkel", "aus"):
        faktor = {"dunkel": 0.5, "aus": 0.2}[effekt]
        bild = bild * (1 - kern) + (bild * faktor) * kern
    else:
        raise SystemExit(f"Unbekannter Augen-Effekt {effekt}")
    aus = rgba.copy()
    aus[..., :3] = np.clip(bild, 0, 255).astype(np.uint8)
    return aus


def daumen_runter(rgba: np.ndarray) -> np.ndarray:
    """Spiegelt die Hand rechts vom Körper senkrecht: Daumen hoch → Daumen runter."""
    h, _ = rgba.shape[:2]
    cx, _, r = auge_finden(rgba)
    rgb = rgba[..., :3].astype(int)
    a = rgba[..., 3]
    grau = (a > 200) & (rgb.max(2) - rgb.min(2) < 30) & (rgb.max(2) > 85) & (rgb.max(2) < 225)
    grau[int(h * 0.62):] = False                  # Schuhe ausschließen
    grau[:, :int(cx + r * 1.5)] = False           # nur rechts vom Körper
    zu = ndimage.binary_closing(grau, iterations=int(r * 0.25) + 2)   # Finger zu einer Hand verbinden
    marken, n = ndimage.label(zu)
    if not n:
        raise SystemExit("Keine Hand für daumen_runter gefunden")
    groessen = ndimage.sum(zu, marken, range(1, n + 1))
    hand = ndimage.binary_fill_holes(marken == 1 + int(np.argmax(groessen)))
    hand = ndimage.binary_dilation(hand, iterations=int(r * 0.15) + 2) & (a > 20)
    ys, xs = np.nonzero(hand)
    y0, y1, x0, x1 = ys.min(), ys.max() + 1, xs.min(), xs.max() + 1
    stueck = rgba[y0:y1, x0:x1].copy()
    stueck[..., 3] = np.where(hand[y0:y1, x0:x1], stueck[..., 3], 0)
    aus = rgba.copy()
    aus[..., 3] = np.where(hand, 0, aus[..., 3])
    im = Image.fromarray(aus, "RGBA")
    im.alpha_composite(Image.fromarray(np.ascontiguousarray(stueck[::-1]), "RGBA"), (int(x0), int(y0)))
    return np.array(im)


HAND_VARIANTEN = {"daumen_runter": daumen_runter}


def kopf_finden(rgba: np.ndarray) -> tuple[float, float, float, float]:
    """Kopf für Zubehör: (Mitte x, Augen y, Kopfbreite, Oberkante y) in Pixeln.
    Kopf = helle Fläche um das Auge (beim DMNT 9000 die Raute)."""
    cx, cy, r = auge_finden(rgba)
    hell = (rgba[..., :3].min(axis=2) > 190) & (rgba[..., 3] > 200)
    y0, y1 = int(max(cy - 3.2 * r, 0)), int(cy + 0.5 * r)
    xs = np.nonzero(hell[y0:y1].any(axis=0))[0]
    links, rechts = (xs.min(), xs.max()) if len(xs) else (cx - 2 * r, cx + 2 * r)
    spalte = hell[:, int(cx)]
    oben = int(np.argmax(spalte)) if spalte.any() else int(cy - 3 * r)
    return (links + rechts) / 2, cy, float(rechts - links), float(oben)


def kopf_ohne_auge(rgba: np.ndarray) -> tuple[float, float, float, float]:
    """Für Posen ohne sichtbares Auge (Rückansicht): größte helle Fläche oben."""
    hell = (rgba[..., :3].min(axis=2) > 190) & (rgba[..., 3] > 200)
    h = rgba.shape[0]
    hell[int(h * 0.65):] = False
    marken, n = ndimage.label(hell)
    groessen = ndimage.sum(hell, marken, range(1, n + 1))
    kopf = marken == 1 + int(np.argmax(groessen))
    ys, xs = np.nonzero(kopf)
    oben, unten = ys.min(), ys.max()
    return (xs.min() + xs.max()) / 2, oben + (unten - oben) * 0.32, float(xs.max() - xs.min()), float(oben)


# --- Bauen -------------------------------------------------------------------------


def skalieren(rgba: np.ndarray, faktor: float) -> np.ndarray:
    im = Image.fromarray(rgba, "RGBA")
    neu = (max(1, round(im.width * faktor)), max(1, round(im.height * faktor)))
    return np.array(im.resize(neu, Image.LANCZOS))


def herkunft_bauen(quelle: Path, plan: dict, ziel: Path) -> str:
    seite = plan.get("groesse", 768)
    hg = _pil_bild(quelle / plan["hintergrund"], seite).convert("RGB")
    s = min(hg.width, hg.height)
    hg = hg.crop(((hg.width - s) // 2, (hg.height - s) // 2, (hg.width + s) // 2, (hg.height + s) // 2))
    hg = hg.resize((seite, seite), Image.LANCZOS).convert("RGBA")
    for ebene in plan.get("ebenen", []):
        b = round(seite * ebene["breite"])
        e = _pil_bild(quelle / ebene["datei"], b).convert("RGBA")
        e = e.resize((b, round(e.height * b / e.width)), Image.LANCZOS)
        x = round(seite * ebene["x"] - e.width / 2)
        y = round(seite * ebene["y"] - e.height / 2)
        hg.alpha_composite(e, (x, y))
    name = "herkunft.jpg"
    hg.convert("RGB").save(ziel / name, quality=88)
    return name


class BauFehler(SystemExit):
    """Bau abgebrochen – Meldung ist für Menschen (deutsch, mit Regel-id und Feld)."""


def zubehoer_laden(quelle: Path) -> dict:
    """zubehoer.json lesen. Namen und Plätze werden zur Kennung („Kopfhörer“ → „kopfhoerer“),
    damit selbst gebautes Zubehör zu den Regeln (Aktion „zubehoer“) und Platzhaltern passt."""
    datei = quelle / "zubehoer.json"
    if not datei.exists():
        return {}
    roh = json.loads(datei.read_text(encoding="utf-8"))
    plan = {}
    for name, z in roh.items():
        k = katalog.kennung(name) or name
        if k != name:
            print(f"  Hinweis: Zubehör „{name}“ heißt technisch „{k}“")
        if isinstance(z, dict) and z.get("gruppe"):
            z = dict(z, gruppe=katalog.kennung(z["gruppe"]) or z["gruppe"])
        plan[k] = z
    return plan


def innen_varianten(zplan: dict) -> set[str]:
    """Varianten des Innenlebens aus zubehoer.json (z. B. {"froh", "erschreckt"})."""
    return {v for z in zplan.values() if z.get("sitz") == "innen" for v in z.get("varianten", {})}


def koerper_pruefen(quelle: Path, plan: dict) -> None:
    """Körper-Blöcke des Bauplans prüfen. Fehler → BauFehler, Warnungen → Ausgabe."""
    fehler, warnungen = katalog.koerper_pruefen(plan, quelle)
    f2, w2 = effekte.plan_pruefen(plan, quelle, set(plan.get("animationen", {})) | set(katalog.KERN_ANIMATIONEN))
    fehler, warnungen = fehler + f2, warnungen + w2
    for w in warnungen:
        print(f"  Warnung: {w}")
    if fehler:
        raise BauFehler("Fehler im Bauplan – Bau abgebrochen:\n" + "\n".join(f"  - {f}" for f in fehler))


def verhalten_pruefen(quelle: Path, plan: dict, zplan: dict | None = None) -> dict | None:
    """verhalten.json gegen den Katalog prüfen. Fehler → BauFehler, Warnungen → Ausgabe."""
    datei = quelle / "verhalten.json"
    if not datei.exists():
        return None
    try:
        verhalten = json.loads(datei.read_text(encoding="utf-8"))
    except ValueError as e:
        raise BauFehler(f"Fehler in verhalten.json: kein gültiges JSON ({e})") from None
    fehler, warnungen = katalog.pruefen(verhalten, plan.get("animationen", {}).keys(),
                                        innen_varianten(zplan or {}))
    for w in warnungen:
        print(f"  Warnung: {w}")
    if fehler:
        raise BauFehler("Fehler in verhalten.json – Bau abgebrochen:\n" + "\n".join(f"  - {f}" for f in fehler))
    print(f"  Verhalten: {len(verhalten.get('regeln', []))} Regel(n), "
          f"{len(verhalten.get('werte', {}))} eigene(r) Wert(e)")
    return verhalten


# --- Rahmen-Ausrichtung (ohne Auge) -------------------------------------------------


def rahmen_bild(pfad: Path, q: dict, rahmen_b: int, ordner: Path | None = None,
                mit_teilen: bool = True) -> np.ndarray:
    """Bild einer Quelle im Rahmen-Modus: auf Rahmenbreite (× faktor) skaliert, ungeschnitten.
    SVG wird direkt in dieser Breite gerendert, mit ``form`` und (``mit_teilen``) den Teilen."""
    if ist_svg(pfad):
        return rig_bild(pfad, round(rahmen_b * float(q.get("faktor", 1.0))), q.get("form"),
                        q.get("teile", []) if mit_teilen else (), ordner)
    if q.get("teile") or q.get("form"):
        raise BauFehler(f"„teile“ und „form“ gehen nur mit SVG-Quellen ({pfad.name})")
    bild = laden(pfad, q.get("hintergrund"), q.get("toleranz"))
    f = rahmen_b / bild.shape[1] * float(q.get("faktor", 1.0))
    return bild if abs(f - 1) < 1e-6 else skalieren(bild, f)


def kopf_aus_umriss(rgba: np.ndarray) -> tuple[float, float, float, float]:
    """Ohne Auge: Mitte, „Augenhöhe“ (35 % von oben), Breite und Oberkante der Figur."""
    ys, xs = np.nonzero(rgba[..., 3] > 40)
    if not len(xs):
        h, w = rgba.shape[:2]
        return w / 2, h * 0.35, w * 0.6, 0.0
    oben, unten = ys.min(), ys.max()
    return (xs.min() + xs.max()) / 2, oben + (unten - oben) * 0.35, float(xs.max() - xs.min()), float(oben)


def rahmen_posen(quelle: Path, plan: dict) -> tuple[dict, dict, dict]:
    """→ (Posen je Quelle, Anker je Pose (Fußpunkt unten Mitte), Rückwände je Pose)."""
    rahmen_b = int(plan.get("rahmen_px", [256, 256])[0])
    skaliert: dict[str, list[np.ndarray]] = {}
    hinten: dict[tuple[str, int], np.ndarray] = {}
    for name, q in plan["quellen"].items():
        if q.get("bilder", 1) != 1:
            raise BauFehler(f"Quelle „{name}“: im Rahmen-Modus ein Bild je Datei")
        bild = rahmen_bild(quelle / q["datei"], q, rahmen_b, quelle)
        if not (bild[..., 3] > 20).any():
            print(f"  Warnung: Bild „{q['datei']}“ ist leer")
        skaliert[name] = [bild]
        if q.get("hinten"):
            if (quelle / q["hinten"]).exists():
                hinten[(name, 0)] = rahmen_bild(quelle / q["hinten"], q, rahmen_b, quelle, mit_teilen=False)
            else:
                print(f"  Warnung: Rückwand „{q['hinten']}“ fehlt – übersprungen")
    anker = {(name, 0): (liste[0].shape[1] / 2, liste[0].shape[0]) for name, liste in skaliert.items()}
    return skaliert, anker, hinten


# --- Töne aus Dateien -------------------------------------------------------------------


def ton_als_wav(quelle: Path, ziel: Path) -> None:
    """Ton-Datei → 16-bit-WAV (winsound spielt nur WAV). .ogg und andere Formate über
    soundfile oder ffmpeg."""
    import wave

    if quelle.suffix.lower() == ".wav":
        try:
            with wave.open(str(quelle), "rb") as w:
                if w.getsampwidth() == 2:
                    shutil.copy(quelle, ziel)
                    return
        except wave.Error:
            pass
    try:
        import soundfile  # noqa: PLC0415 – nur zum Bauen

        daten, rate = soundfile.read(str(quelle), dtype="int16")
        soundfile.write(str(ziel), daten, rate, subtype="PCM_16")
        return
    except ImportError:
        pass
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise BauFehler(f"Ton „{quelle.name}“: zum Umwandeln in WAV wird ffmpeg oder das Paket soundfile "
                        "gebraucht (pip install soundfile)")
    import subprocess

    ergebnis = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(quelle), "-ac", "1",
                               "-sample_fmt", "s16", str(ziel)], capture_output=True, text=True)
    if ergebnis.returncode != 0 or not ziel.exists():
        raise BauFehler(f"Ton „{quelle.name}“ ließ sich nicht umwandeln: {ergebnis.stderr.strip()[:200]}")


def effekte_bauen(quelle: Path, ziel: Path, plan: dict) -> dict:
    """Eigene Effekte (PNG-Folgen) nach ``effekte/<name>/`` kopieren → Eintrag für avatar.json."""
    eigene = {}
    for name, d in (plan.get("eigene") or {}).items():
        bilder = sorted((quelle / d["ordner"]).glob("*.png"))
        if not bilder:
            continue
        (ziel / "effekte" / name).mkdir(parents=True, exist_ok=True)
        rel = []
        for n, bild in enumerate(bilder):
            shutil.copy(bild, ziel / "effekte" / name / f"{n:02d}.png")
            rel.append(f"effekte/{name}/{n:02d}.png")
        eigene[name] = {"bilder": rel, "fps": d.get("fps", 8), "breite": d.get("breite", 40),
                        "hoehe_ueber_kopf": d.get("hoehe_ueber_kopf", 6)}
        print(f"  Effekt {name}: {len(rel)} Bild(er)")
    ergebnis: dict = {}
    if plan.get("zuordnung"):
        ergebnis["zuordnung"] = dict(plan["zuordnung"])
    if eigene:
        ergebnis["eigene"] = eigene
    return ergebnis


def bauen(quelle: Path, ziel: Path | None = None) -> Path:
    plan = json.loads((quelle / "bauplan.json").read_text(encoding="utf-8"))
    ziel = ziel or WURZEL / "src" / "dmnt_kobold" / "avatare" / plan["id"]
    s = plan.get("skalierung", 2)
    rahmen = plan.get("ausrichtung") == "rahmen"
    zplan_vorab = zubehoer_laden(quelle)
    koerper_pruefen(quelle, plan)                      # vor allem anderen: nichts kaputt bauen
    verhalten = verhalten_pruefen(quelle, plan, zplan_vorab)
    if rahmen:
        skaliert, anker, rueckwand = rahmen_posen(quelle, plan)
        ohne_auge = set(skaliert)
        posen = {}
    else:
        rueckwand = {}
        skaliert, anker, ohne_auge, posen = auge_posen(quelle, plan, s)

    def kopf(name: str, p: np.ndarray) -> tuple[float, float, float, float]:
        if rahmen:
            return kopf_aus_umriss(p)
        return kopf_ohne_auge(p) if name in ohne_auge else kopf_finden(p)

    # gemeinsame Leinwand: Anker = Fußpunkt
    links = rechts = oben = unten = 0.0
    for (name, i), (cx, fy) in anker.items():
        p = skaliert[name][i]
        links, rechts = max(links, cx), max(rechts, p.shape[1] - cx)
        oben = max(oben, fy)
        unten = max(unten, p.shape[0] - fy)          # nur bei Raster-Posen > 0
    unten_px = int(np.ceil(unten))
    unten_px += unten_px % s
    breite_px = int(np.ceil(2 * max(links, rechts))) + 4
    hoehe_px = int(np.ceil(oben)) + 4 + unten_px
    breite_px += breite_px % s
    hoehe_px += hoehe_px % s
    ax, ay = breite_px / 2, hoehe_px - 2 - unten_px
    return _bauen_rest(quelle, plan, ziel, s, rahmen, verhalten, skaliert, anker, ohne_auge, rueckwand, kopf,
                       breite_px, hoehe_px, ax, ay)


def auge_posen(quelle: Path, plan: dict, s: int):
    """Posen mit rotem Auge laden, über die Augengröße skalieren → (Posen, Anker, ohne Auge, roh)."""
    # 1) Posen laden
    posen: dict[str, list[np.ndarray]] = {}
    raster_anker: dict[str, list[tuple[float, float]]] = {}
    for name, q in plan["quellen"].items():
        bild = laden(quelle / q["datei"], q.get("hintergrund"), q.get("toleranz"))
        if q.get("raster"):
            if q.get("massstab") != "fest":
                raise BauFehler(f"Quelle „{name}“: „raster“ geht nur mit \"massstab\": \"fest\"")
            teile = raster_zerlegen(bild, q.get("bilder", 1), q.get("fusspunkt"))
            posen[name] = [p for p, _ in teile]
            raster_anker[name] = [a for _, a in teile]
        else:
            posen[name] = zerlegen(bild, q.get("bilder", 1))
        print(f"  {name}: {len(posen[name])} Pose(n)")

    # 2) Maßstab: Referenzpose auf Zielhöhe, alle anderen über die Augengröße
    ref_name, ref_i = plan["referenz"]
    ref = posen[ref_name][ref_i]
    _, _, ref_r = auge_finden(ref)
    faktor_pro_augenpixel = plan["hoehe"] * s / ref.shape[0] * ref_r
    ohne_auge = {n for n, q in plan["quellen"].items() if q.get("ohne_auge")}
    skaliert: dict[str, list[np.ndarray]] = {}
    for name, liste in posen.items():
        if name in ohne_auge:
            continue
        if plan["quellen"][name].get("massstab") == "fest":
            f = plan["hoehe"] * s / ref.shape[0] * plan["quellen"][name].get("faktor", 1.0)
            skaliert[name] = [skalieren(p, f) for p in liste]
            if name in raster_anker:
                raster_anker[name] = [(ax * f, ay * f) for ax, ay in raster_anker[name]]
            continue
        skaliert[name] = []
        for p in liste:
            _, _, r = auge_finden(p)
            f = plan["quellen"][name].get("faktor", 1.0)
            skaliert[name].append(skalieren(p, faktor_pro_augenpixel / r * f))
    # Quellen mit "massstab": "kopf" – Kopfbreite wie die Referenzpose (robuster,
    # wenn die Augengroesse zwischen den Bildern schwankt)
    ref_kopf = kopf_finden(skaliert[ref_name][ref_i])[2]
    for name, q in plan["quellen"].items():
        if q.get("massstab") == "kopf" and name not in ohne_auge:
            skaliert[name] = [skalieren(p, ref_kopf * q.get("faktor", 1.0) / kopf_finden(p)[2])
                              for p in posen[name]]
    # Posen ohne Auge: Kopfbreite relativ zu einer Pose mit Auge
    for name in ohne_auge:
        q = plan["quellen"][name]
        bezug_name, bezug_nr = q["kopfbreite_wie"]
        ziel_breite = kopf_finden(skaliert[bezug_name][bezug_nr])[2] * q.get("faktor", 1.0)
        skaliert[name] = [skalieren(p, ziel_breite / kopf_ohne_auge(p)[2]) for p in posen[name]]

    # 3) Anker = (Augen-x, Fuss-y)
    anker = {}
    for name, liste in skaliert.items():
        for i, p in enumerate(liste):
            if name in raster_anker:
                anker[(name, i)] = raster_anker[name][i]
                continue
            cx = auge_finden(p)[0] if name not in ohne_auge else kopf_ohne_auge(p)[0]
            anker[(name, i)] = (cx, p.shape[0])
    return skaliert, anker, ohne_auge, posen


def _bauen_rest(quelle, plan, ziel, s, rahmen, verhalten, skaliert, anker, ohne_auge, rueckwand, kopf,
                breite_px, hoehe_px, ax, ay) -> Path:
    if ziel.exists():
        shutil.rmtree(ziel)
    (ziel / "frames").mkdir(parents=True)

    # Kopf je Pose relativ zum Anker (logische Pixel) – Grundlage fürs Zubehör
    # Merkmale je Pose relativ zum Anker (logische Pixel): Kopf, Auge, vordere Hand
    kopf_rel: dict[str, dict] = {}
    for (name, i), (cx, fy) in anker.items():
        p = skaliert[name][i]
        kx, ky, kb, ko = kopf(name, p)
        dx, dy = round(ax - cx), round(ay - fy)
        m = {"kopf": ((kx + dx - ax) / s, (ky + dy - ay) / s, kb / s, (ko + dy - ay) / s),
             "auge": None, "hand": None}
        if name not in ohne_auge:
            ex, ey, er = auge_finden(p)
            m["auge"] = ((ex + dx - ax) / s, (ey + dy - ay) / s, er / s)
        h = None if rahmen else hand_finden(p)
        if h is not None:
            m["hand"] = ((h[0] + dx - ax) / s, (h[1] + dy - ay) / s)
        kopf_rel[f"{name}:{i}"] = m

    zubehoer_plan = zubehoer_laden(quelle)
    zubehoer_info = zubehoer_vorbereiten(quelle, zubehoer_plan, ziel)
    # Outfits: Zubehör, das gemeinsam an- und ausgezogen wird (outfits.json)
    outfits = json.loads((quelle / "outfits.json").read_text(encoding="utf-8")) \
        if (quelle / "outfits.json").exists() else {"aktiv": None, "outfits": {}}
    im_outfit = {katalog.kennung(t) or t for t in outfits.get("outfits", {}).get(outfits.get("aktiv") or "", [])}

    # 4) Animationen
    animationen = {}
    for anim, a in plan["animationen"].items():
        pfade, koepfe, posen_schluessel, hinten_pfade = [], [], [], []
        (ziel / "frames" / anim).mkdir()
        for i, eintrag in enumerate(a["bilder"]):
            pose, nr, effekt = eintrag[:3]
            posen_schluessel.append(f"{pose}:{nr}")
            p = skaliert[pose][nr]
            if len(eintrag) > 3:
                p = HAND_VARIANTEN[eintrag[3]](p)
            k = kopf(pose, p)                # vor dem Augen-Effekt (dunkles Auge wäre unauffindbar)
            if pose not in ohne_auge:
                p = auge_effekt(p, effekt)
            cx, fy = anker[(pose, nr)]
            dx, dy = round(ax - cx), round(ay - fy)
            leinwand = Image.new("RGBA", (breite_px, hoehe_px))
            leinwand.alpha_composite(Image.fromarray(p, "RGBA"), (dx, dy))
            rel = f"frames/{anim}/{i:02d}.png"
            leinwand.save(ziel / rel, optimize=True)
            pfade.append(rel)
            if (pose, nr) in rueckwand:
                wand = Image.new("RGBA", (breite_px, hoehe_px))
                wand.alpha_composite(Image.fromarray(rueckwand[(pose, nr)], "RGBA"), (dx, dy))
                hinten_rel = f"frames/{anim}/{i:02d}_hinten.png"
                wand.save(ziel / hinten_rel, optimize=True)
                hinten_pfade.append(hinten_rel)
            else:
                hinten_pfade.append(None)
            kx, ky, kb, ko = k[0] + dx, k[1] + dy, k[2], k[3] + dy
            koepfe.append([round(kx / s, 1), round(ky / s, 1), round(kb / s, 1), round(ko / s, 1)])
        animationen[anim] = {"fps": a["fps"], "schleife": a.get("schleife", True), "bilder": pfade,
                             "koepfe": koepfe, "posen": posen_schluessel}
        if any(hinten_pfade):
            animationen[anim]["hinten"] = hinten_pfade
        if zubehoer_info:
            animationen[anim]["zubehoer"] = {
                teil: [platzierung_liste(platzierung(info, zubehoer_plan[teil], schluessel, kopf_rel))
                       for schluessel in posen_schluessel]
                for teil, info in zubehoer_info.items()}
        print(f"  {anim}: {len(pfade)} Frame(s)")

    # 5) Körpermaß aus der Ruhepose (für die Physik)
    ruhe = np.array(Image.open(ziel / animationen["ruhe"]["bilder"][0]))
    ys, xs = np.nonzero(ruhe[..., 3] > 40)
    if len(xs):
        koerper_b = (xs.max() - xs.min()) / s
        koerper_h = (ay - ys.min()) / s
    else:                                     # leere Vorlage: Rahmen als Körper
        print("  Warnung: Pose „ruhe“ ist leer – Körpermaß = Rahmen")
        koerper_b, koerper_h = breite_px / s * 0.6, hoehe_px / s * 0.6

    # 6) Porträt (für den Einrichten-Modus, M4)
    portraet = None
    if "portraet" in plan:
        q = plan["portraet"]
        if q.get("pose"):
            bild = zuschneiden(pose_mit_innen(q["pose"], skaliert, rueckwand, anker, zubehoer_info,
                                              zubehoer_plan, kopf_rel, s, ziel))
        else:
            bild = zuschneiden(laden(quelle / q["datei"], q.get("hintergrund")))
        f = q.get("hoehe", 360) * s / bild.shape[0]
        Image.fromarray(skalieren(bild, f), "RGBA").save(ziel / "portraet.png", optimize=True)
        portraet = "portraet.png"

    # 7) Herkunft
    herkunft = herkunft_bauen(quelle, plan["herkunft"], ziel) if "herkunft" in plan else None

    # 8) Töne
    toene: dict[str, object] = {}
    if plan.get("toene"):
        (ziel / "toene").mkdir()
        for name, t in plan["toene"].items():
            if "segmente" in t:                  # synthetisiert
                segmente = [tuple(x) for x in t["segmente"]]
                pcm = synthese(segmente, 1.0, welle=t.get("welle", "sinus"))
                schreibe_wav(ziel / "toene" / f"{name}.wav", pcm)
                toene[name] = f"toene/{name}.wav"
                continue
            dateien = []                         # Körper-Ton aus Dateien (fehlende: Warnung beim Prüfen)
            for n, rel in enumerate(t.get("dateien", []), 1):
                if (quelle / rel).is_file():
                    ton_als_wav(quelle / rel, ziel / "toene" / f"{name}_{n}.wav")
                    dateien.append(f"toene/{name}_{n}.wav")
            if dateien:
                toene[name] = {"dateien": dateien, "tonhoehe": t.get("tonhoehe", 0.0),
                               "wiederholen": t.get("wiederholen", [1, 1])}
                for extra in ("chance", "abstand_s"):          # z. B. Pfeifen beim Loslaufen
                    if extra in t:
                        toene[name][extra] = t[extra]
                print(f"  Ton {name}: {len(dateien)} Datei(en)")

    # 8b) Effekte über dem Kopf: Zuordnung + eigene Bildfolgen
    effekte_json = effekte_bauen(quelle, ziel, plan.get("effekte") or {})

    # 9) Verhalten, Sonderlogik, Lizenz, avatar.json
    if verhalten is not None:
        (ziel / "verhalten.json").write_text(json.dumps(verhalten, ensure_ascii=False, indent=2) + "\n",
                                             encoding="utf-8")
    for datei in ("persoenlichkeit.py", "LIZENZ.txt"):
        if (quelle / datei).exists():
            shutil.copy(quelle / datei, ziel / datei)
    avatar = {
        "format": 1,
        "id": plan["id"],
        "name": plan["name"],
        "skalierung": s,
        "rahmen": [breite_px / s, hoehe_px / s],
        "anker": [ax / s, ay / s],
        "koerper": {"breite": round(float(koerper_b), 1), "hoehe": round(float(koerper_h), 1)},
        "blickrichtung": plan.get("blickrichtung", 1),
        "bewegung": plan.get("bewegung", {"art": "gehen"}),
        "herkunft": herkunft,
        "portraet": portraet,
        "animationen": animationen,
        "toene": toene,
        "outfits": outfits.get("outfits", {}),
        "outfit": outfits.get("aktiv"),
        "zubehoer": {teil: zubehoer_eintrag(teil, info, zubehoer_plan[teil], im_outfit)
                     for teil, info in zubehoer_info.items()},
    }
    for k in ("partikel", "koerper_deckkraft"):
        if k in plan:
            avatar[k] = plan[k]
    if effekte_json:
        avatar["effekte"] = effekte_json
    (ziel / "avatar.json").write_text(json.dumps(avatar, ensure_ascii=False, indent=2), encoding="utf-8")
    vorschau_schreiben(plan, skaliert, anker, ax, ay, breite_px, hoehe_px, s, kopf_rel, zubehoer_plan,
                       zubehoer_info)
    return ziel


def pose_mit_innen(name: str, skaliert, rueckwand, anker, zinfo, zplan, kopf_rel, s, ziel: Path) -> np.ndarray:
    """Eine Pose so, wie der Sockel sie zeigt: Rückwand, Innenleben (Grundvariante), Körper."""
    if name not in skaliert:
        raise BauFehler(f"portraet.pose: Quelle „{name}“ gibt es nicht")
    front = skaliert[name][0]
    im = Image.new("RGBA", (front.shape[1], front.shape[0]))
    if (name, 0) in rueckwand:
        im.alpha_composite(Image.fromarray(rueckwand[(name, 0)], "RGBA"))
    cx, fy = anker[(name, 0)]
    for teil, info in zinfo.items():
        if zplan[teil].get("sitz") != "innen":
            continue
        p = platzierung(info, zplan[teil], f"{name}:0", kopf_rel)
        if p.get("aus"):
            continue
        stueck = Image.open(ziel / info["bild"]).convert("RGBA")
        b = float(p["breite"]) * s
        h = b * stueck.height / stueck.width * float(p.get("hoehe", 100)) / 100
        stueck = stueck.resize((max(1, round(b)), max(1, round(h))), Image.LANCZOS)
        ebene = Image.new("RGBA", im.size)
        ebene.paste(stueck, (round(cx + float(p["x"]) * s - b / 2), round(fy + float(p["y"]) * s - h / 2)))
        im.alpha_composite(ebene)
    im.alpha_composite(Image.fromarray(front, "RGBA"))
    return np.array(im)


# --- Zubehör ------------------------------------------------------------------------
# zubehoer.json im Quellordner:
#   {"kopfhoerer": {"datei": "../zubehoer/kopfhoerer.png", "hintergrund": "weiss",
#                   "sitz": "ueber_kopf", "gruppe": "ohren", "immer": false,
#                   "posen": {"seite:0": {"x": 1.5, "y": -98, "breite": 74, "winkel": 0,
#                                          "hinten": false, "aus": false}}}}
# x/y = Mitte des Zubehörs relativ zum Fußpunkt (logische Pixel), breite in logischen
# Pixeln, winkel in Grad, hoehe in Prozent der natürlichen Höhe (Quetschen/Strecken). Posen ohne Eintrag bekommen eine Standard-Platzierung aus
# dem Kopf (``sitz``: "ueber_kopf" wie Kopfhörer, "auf_kopf" wie ein Hut).

ZUBEHOER_MAX_BREITE = 480


def _zubehoer_bild(pfad: Path, z: dict, ziel: Path, name: str) -> tuple[str, float] | None:
    """Bild freistellen, verkleinert in den Avatar-Ordner legen → (Pfad, Höhe/Breite)."""
    if not pfad.exists():
        return None
    bild = laden(pfad, z.get("hintergrund"), z.get("toleranz"))
    if (bild[..., 3] > 20).any() and not ist_svg(pfad):    # SVG: viewBox bleibt (Varianten deckungsgleich)
        bild = zuschneiden(bild)
    if bild.shape[1] > ZUBEHOER_MAX_BREITE:
        bild = skalieren(bild, ZUBEHOER_MAX_BREITE / bild.shape[1])
    (ziel / "zubehoer").mkdir(exist_ok=True)
    rel = f"zubehoer/{name}.png"
    Image.fromarray(bild, "RGBA").save(ziel / rel, optimize=True)
    return rel, bild.shape[0] / bild.shape[1]


def zubehoer_vorbereiten(quelle: Path, zplan: dict, ziel: Path) -> dict[str, dict]:
    """Bilder freistellen, verkleinert in den Avatar-Ordner legen.
    → {teil: {bild, verhaeltnis, varianten: {name: {bild, x, y}}}}"""
    info = {}
    for teil, z in zplan.items():
        haupt = _zubehoer_bild((quelle / z["datei"]).resolve(), z, ziel, teil)
        if haupt is None:
            print(f"  Zubehör {teil}: Bild fehlt ({z['datei']}) – übersprungen")
            continue
        info[teil] = {"bild": haupt[0], "verhaeltnis": haupt[1], "varianten": {}}
        for v, d in z.get("varianten", {}).items():          # Innenleben je Stimmung (tnt@froh)
            bild = _zubehoer_bild((quelle / d["datei"]).resolve(), z, ziel, f"{teil}@{v}")
            if bild is None:
                print(f"  Zubehör {teil}@{v}: Bild fehlt ({d['datei']}) – Grundvariante gilt")
                continue
            info[teil]["varianten"][v] = {"bild": bild[0], "x": float(d.get("x", 0)), "y": float(d.get("y", 0))}
        extra = f", Varianten: {', '.join(info[teil]['varianten'])}" if info[teil]["varianten"] else ""
        print(f"  Zubehör {teil}: {len(z.get('posen', {}))} Pose(n) eingestellt{extra}")
    return info


def zubehoer_eintrag(teil: str, info: dict, z: dict, im_outfit: set[str]) -> dict:
    """Eintrag in avatar.json. Innenleben (Sitz „innen“) gehört zum Körper: immer an."""
    eintrag = {"bild": info["bild"],
               "immer": bool(z.get("immer")) or teil in im_outfit or z.get("sitz") == "innen",
               "gruppe": z.get("gruppe", teil)}
    if z.get("sitz") == "innen":
        eintrag["sitz"] = "innen"
        eintrag["varianten"] = info.get("varianten", {})
    return eintrag


def hand_finden(rgba: np.ndarray) -> tuple[float, float] | None:
    """Vordere Hand (Handschuh): graue Fläche im mittleren Körperband, am weitesten
    in Blickrichtung (rechts). None, wenn nichts Passendes da ist."""
    r, g, b = (rgba[..., i].astype(int) for i in range(3))
    grau = ((np.abs(r - g) < 14) & (np.abs(g - b) < 14) & (r > 90) & (r < 190) & (rgba[..., 3] > 200))
    h = rgba.shape[0]
    grau[: int(h * 0.33)] = False
    grau[int(h * 0.74):] = False
    marken, n = ndimage.label(grau)
    if not n:
        return None
    groessen = ndimage.sum(grau, marken, range(1, n + 1))
    kandidaten = [i + 1 for i, g_ in enumerate(groessen) if g_ >= max(groessen) * 0.35]
    besten = None
    for k in kandidaten:
        ys, xs = np.nonzero(marken == k)
        mitte = (xs.mean(), ys.mean())
        if besten is None or mitte[0] > besten[0]:
            besten = mitte
    return besten


def standard_platzierung(info: dict, z: dict, merkmale: dict) -> dict:
    kx, _ky, kb, ko = merkmale["kopf"]
    sitz = z.get("sitz")
    if sitz == "innen":                       # mitten im Körper, gut ein Drittel so breit
        b = float(z["breite"]) if z.get("breite") else kb * 0.38
        return {"x": kx, "y": ko / 2, "breite": b, "winkel": 0.0, "hinten": False, "aus": False}
    if sitz == "am_auge" and merkmale.get("auge"):
        ex, ey, er = merkmale["auge"]
        b = er * 4.4
        return {"x": ex, "y": ey, "breite": b, "winkel": 0.0, "hinten": False, "aus": False}
    if sitz == "in_hand":
        hx, hy = merkmale.get("hand") or (kx + kb * 0.55, -kb * 0.9)
        hoehe = max(20.0, -hy / 0.92)           # vom Griff bis zum Boden
        b = hoehe / info["verhaeltnis"]
        return {"x": hx, "y": hy - hoehe * 0.06 + hoehe / 2, "breite": b, "winkel": 0.0,
                "hinten": True, "aus": False}
    if sitz == "auf_kopf":
        b = kb * 0.72
        h = b * info["verhaeltnis"]
        return {"x": kx, "y": ko - h / 2 + h * 0.12, "breite": b, "winkel": 0.0, "hinten": False, "aus": False}
    b = kb * 1.12
    h = b * info["verhaeltnis"]
    return {"x": kx, "y": ko - h * 0.3 + h / 2, "breite": b, "winkel": 0.0, "hinten": False, "aus": False}


def platzierung(info: dict, z: dict, schluessel: str, kopf_rel: dict) -> dict:
    p = standard_platzierung(info, z, kopf_rel[schluessel])
    p.update(z.get("posen", {}).get(schluessel, {}))
    return p


def platzierung_liste(p: dict) -> list:
    return [round(float(p["x"]), 1), round(float(p["y"]), 1), round(float(p["breite"]), 1),
            round(float(p.get("winkel", 0)), 1), int(bool(p.get("hinten"))), int(bool(p.get("aus"))),
            round(float(p.get("hoehe", 100)), 1)]


def vorschau_schreiben(plan, skaliert, anker, ax, ay, breite_px, hoehe_px, s, kopf_rel, zplan, zinfo) -> None:
    """Für den Avatar-Editor: jede Pose auf der gemeinsamen Leinwand + Daten (build/vorschau/<id>/)."""
    ordner = WURZEL / "build" / "vorschau" / plan["id"]
    if ordner.exists():
        shutil.rmtree(ordner)
    ordner.mkdir(parents=True)
    benutzt: dict[str, list[str]] = {}
    for anim, a in plan["animationen"].items():
        for e in a["bilder"]:
            liste = benutzt.setdefault(f"{e[0]}:{e[1]}", [])
            liste.append(anim)
    posen = {}
    for (name, i), (cx, fy) in anker.items():
        schluessel = f"{name}:{i}"
        dx, dy = round(ax - cx), round(ay - fy)
        leinwand = Image.new("RGBA", (breite_px, hoehe_px))
        leinwand.alpha_composite(Image.fromarray(skaliert[name][i], "RGBA"), (dx, dy))
        datei = f"{name}_{i}.png"
        leinwand.save(ordner / datei)
        posen[schluessel] = {
            "bild": datei, "quelle": name, "nr": i, "datei": plan["quellen"][name]["datei"],
            "bilder_in_datei": plan["quellen"][name].get("bilder", 1),
            "kopf": [round(v, 2) for v in kopf_rel[schluessel]["kopf"]],
            "auge": [round(v, 2) for v in kopf_rel[schluessel]["auge"]] if kopf_rel[schluessel]["auge"] else None,
            "hand": [round(v, 2) for v in kopf_rel[schluessel]["hand"]] if kopf_rel[schluessel]["hand"] else None,
            "benutzt": benutzt.get(schluessel, []),
            "zubehoer_standard": {t: standard_platzierung(zinfo[t], zplan[t], kopf_rel[schluessel])
                                  for t in zinfo},
        }
    daten = {"id": plan["id"], "skalierung": s, "leinwand": [breite_px / s, hoehe_px / s],
             "anker": [ax / s, ay / s], "posen": posen,
             "zubehoer": {t: {"bild": str((WURZEL / "src" / "dmnt_kobold" / "avatare" / plan["id"] / i["bild"])),
                              "verhaeltnis": i["verhaeltnis"]} for t, i in zinfo.items()}}
    (ordner / "posen.json").write_text(json.dumps(daten, ensure_ascii=False, indent=1), encoding="utf-8")


VORLAGEN_LIESMICH = """{name} – Bildvorlagen aller Posen
=====================================

Was ist das?
  Jede Pose, die der Kobold benutzt, als Einzelbild (Originalgröße, transparenter
  Hintergrund). _uebersicht.png zeigt, welche Pose in welcher Animation steckt.

Varianten machen (z. B. Kopfhörer):
  1. Pose nehmen, Variante erzeugen lassen. Pose, Blickrichtung und Ausschnitt
     möglichst gleich lassen – nur das Zubehör dazu.
  2. Hintergrund: transparent, einfarbig schwarz oder weiß.
  3. Gleicher Dateiname + Variante, z. B.  gehen_1_kopfhoerer.png
  4. Alle Bilder einer Variante zusammen an Claude geben.

Das Auge muss rot und sichtbar bleiben (danach richtet das Bau-Werkzeug
Größe und Position aus).

Bis die Varianten da sind, setzt der Kobold Platzhalter-Zubehör auf.
"""


def vorlagen_exportieren(quelle: Path) -> Path:
    """Exportiert jede verwendete Pose einzeln (Originalauflösung, transparenter
    Hintergrund) plus Übersicht – als Vorlage für Varianten (z. B. mit Kopfhörern)."""
    from PIL import ImageDraw, ImageFont

    plan = json.loads((quelle / "bauplan.json").read_text(encoding="utf-8"))
    ziel = WURZEL / "vorlagen" / plan["id"]
    if ziel.exists():
        shutil.rmtree(ziel)
    ziel.mkdir(parents=True)
    posen = {n: zerlegen(laden(quelle / q["datei"], q.get("hintergrund"), q.get("toleranz")),
                         q.get("bilder", 1))
             for n, q in plan["quellen"].items()}
    benutzt: dict[tuple, list[str]] = {}
    for anim, a in plan["animationen"].items():
        for eintrag in a["bilder"]:
            schluessel = (eintrag[0], eintrag[1], eintrag[3] if len(eintrag) > 3 else "")
            if anim not in benutzt.setdefault(schluessel, []):
                benutzt[schluessel].append(anim)
    namen = []
    for (pose, nr, hand), anims in benutzt.items():
        bild = posen[pose][nr]
        if hand:
            bild = HAND_VARIANTEN[hand](bild)
        name = f"{pose}_{nr + 1}{'_' + hand if hand else ''}.png"
        Image.fromarray(bild, "RGBA").save(ziel / name, optimize=True)
        namen.append((name, anims, bild))
    namen.sort(key=lambda n: n[0])
    # Übersicht
    zelle, kopf = 360, 96
    uebersicht = Image.new("RGB", (zelle * len(namen), zelle + kopf), (40, 44, 48))
    zeichnen = ImageDraw.Draw(uebersicht)
    try:
        schrift = ImageFont.truetype("DejaVuSans.ttf", 15)
    except OSError:
        schrift = ImageFont.load_default()
    for i, (name, anims, bild) in enumerate(namen):
        im = Image.fromarray(bild, "RGBA")
        im.thumbnail((zelle - 20, zelle - 20))
        uebersicht.paste(im, (i * zelle + (zelle - im.width) // 2, kopf + (zelle - im.height) // 2), im)
        zeichnen.text((i * zelle + 10, 8), name, fill=(240, 240, 240), font=schrift)
        for z in range(0, len(anims), 3):
            zeichnen.text((i * zelle + 10, 30 + z // 3 * 20), ", ".join(anims[z:z + 3]),
                          fill=(160, 200, 185), font=schrift)
    uebersicht.save(ziel / "_uebersicht.png")
    (ziel / "LIESMICH.txt").write_text(VORLAGEN_LIESMICH.format(name=plan["name"]), encoding="utf-8")
    print(f"  {len(namen)} Vorlagen → {ziel}")
    return ziel


def _option(args: list[str], name: str) -> str | None:
    if name not in args:
        return None
    i = args.index(name)
    if i + 1 >= len(args):
        raise SystemExit(f"{name} braucht einen Wert")
    wert = args[i + 1]
    del args[i:i + 2]
    return wert


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    ziel_ordner = _option(args, "--ziel")
    innen = _option(args, "--innen")
    if len(args) == 2 and args[0] == "--vorlagen":
        ordner = Path(args[1]).resolve()
        plan_datei = ordner / "bauplan.json"
        if not plan_datei.exists() or json.loads(plan_datei.read_text(encoding="utf-8")).get("ausrichtung") \
                == "rahmen":
            from vorlagen_huepfen import huepf_vorlagen   # neuer Hüpf-Avatar: leere Rahmen

            huepf_vorlagen(ordner, innen)
        else:
            vorlagen_exportieren(ordner)
        raise SystemExit(0)
    if len(args) != 1:
        raise SystemExit(__doc__)
    quelle = Path(args[0]).resolve()
    if quelle.name == "zubehoer":
        zubehoer_bauen(quelle, WURZEL / "src" / "dmnt_kobold" / "zubehoer")
    else:
        print(f"Fertig: {bauen(quelle, Path(ziel_ordner).resolve() if ziel_ordner else None)}")
