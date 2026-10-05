"""Baut einen Avatar-Ordner aus Quellbildern.

Aufruf:  python werkzeuge/avatar_bauen.py quellen/<name>
         python werkzeuge/avatar_bauen.py quellen/zubehoer   (Kopfhörer usw. für alle Avatare)
         python werkzeuge/avatar_bauen.py --vorlagen quellen/<name>   (Einzelposen als Vorlage)
Ergebnis: src/dmnt_kobold/avatare/<id>/ mit avatar.json, frames/, toene/, Herkunft, Porträt.

Bauplan-Eintrag eines Frames: [Quelle, Pose-Nr, Augen-Effekt] oder
[Quelle, Pose-Nr, Augen-Effekt, Hand-Variante] (z. B. "daumen_runter").

Das Programm selbst kennt nur fertige Frames. Dieses Werkzeug erledigt alles davor:
- Bildbögen in Einzelbilder zerlegen (leere Spalten trennen die Posen)
- schwarzen Hintergrund entfernen und die Außenkontur wieder schwarz nachziehen
- alle Posen über die Augengröße auf denselben Maßstab bringen
- Fußpunkt (unten) und Körpermitte (Auge) ausrichten
- Augen-Effekte rechnen (hell, dunkel, aus, grell, puls) für Ausdrücke
- Herkunfts-Bild zusammensetzen, Töne synthetisieren

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
    Bei "weiss" auch für eingebrannte Karomuster: ``toleranz`` z. B. 220."""
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
    hg = Image.open(quelle / plan["hintergrund"]).convert("RGB")
    seite = plan.get("groesse", 768)
    s = min(hg.width, hg.height)
    hg = hg.crop(((hg.width - s) // 2, (hg.height - s) // 2, (hg.width + s) // 2, (hg.height + s) // 2))
    hg = hg.resize((seite, seite), Image.LANCZOS).convert("RGBA")
    for ebene in plan.get("ebenen", []):
        e = Image.open(quelle / ebene["datei"]).convert("RGBA")
        b = round(seite * ebene["breite"])
        e = e.resize((b, round(e.height * b / e.width)), Image.LANCZOS)
        x = round(seite * ebene["x"] - e.width / 2)
        y = round(seite * ebene["y"] - e.height / 2)
        hg.alpha_composite(e, (x, y))
    name = "herkunft.jpg"
    hg.convert("RGB").save(ziel / name, quality=88)
    return name


def bauen(quelle: Path) -> Path:
    plan = json.loads((quelle / "bauplan.json").read_text(encoding="utf-8"))
    ziel = WURZEL / "src" / "dmnt_kobold" / "avatare" / plan["id"]
    s = plan.get("skalierung", 2)

    # 1) Posen laden
    posen: dict[str, list[np.ndarray]] = {}
    for name, q in plan["quellen"].items():
        posen[name] = zerlegen(laden(quelle / q["datei"], q.get("hintergrund"), q.get("toleranz")),
                               q.get("bilder", 1))
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
        skaliert[name] = []
        for p in liste:
            _, _, r = auge_finden(p)
            skaliert[name].append(skalieren(p, faktor_pro_augenpixel / r))
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

    def kopf(name: str, p: np.ndarray) -> tuple[float, float, float, float]:
        return kopf_ohne_auge(p) if name in ohne_auge else kopf_finden(p)

    # 3) gemeinsame Leinwand: Anker = (Augen-x, Fuss-y)
    anker = {}
    links = rechts = oben = 0.0
    for name, liste in skaliert.items():
        for i, p in enumerate(liste):
            cx = auge_finden(p)[0] if name not in ohne_auge else kopf_ohne_auge(p)[0]
            fy = p.shape[0]
            anker[(name, i)] = (cx, fy)
            links, rechts = max(links, cx), max(rechts, p.shape[1] - cx)
            oben = max(oben, fy)
    breite_px = int(np.ceil(2 * max(links, rechts))) + 4
    hoehe_px = int(np.ceil(oben)) + 4
    breite_px += breite_px % s
    hoehe_px += hoehe_px % s
    ax, ay = breite_px / 2, hoehe_px - 2

    if ziel.exists():
        shutil.rmtree(ziel)
    (ziel / "frames").mkdir(parents=True)

    # 4) Animationen
    animationen = {}
    for anim, a in plan["animationen"].items():
        pfade, koepfe = [], []
        (ziel / "frames" / anim).mkdir()
        for i, eintrag in enumerate(a["bilder"]):
            pose, nr, effekt = eintrag[:3]
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
            kx, ky, kb, ko = k[0] + dx, k[1] + dy, k[2], k[3] + dy
            koepfe.append([round(kx / s, 1), round(ky / s, 1), round(kb / s, 1), round(ko / s, 1)])
        animationen[anim] = {"fps": a["fps"], "schleife": a.get("schleife", True), "bilder": pfade,
                             "koepfe": koepfe}
        print(f"  {anim}: {len(pfade)} Frame(s)")

    # 5) Körpermaß aus der Ruhepose (für die Physik)
    ruhe = np.array(Image.open(ziel / animationen["ruhe"]["bilder"][0]))
    ys, xs = np.nonzero(ruhe[..., 3] > 40)
    koerper_b = (xs.max() - xs.min()) / s
    koerper_h = (ay - ys.min()) / s

    # 6) Porträt (für den Einrichten-Modus, M4)
    portraet = None
    if "portraet" in plan:
        q = plan["portraet"]
        bild = zuschneiden(laden(quelle / q["datei"], q.get("hintergrund")))
        f = q.get("hoehe", 360) * s / bild.shape[0]
        Image.fromarray(skalieren(bild, f), "RGBA").save(ziel / "portraet.png", optimize=True)
        portraet = "portraet.png"

    # 7) Herkunft
    herkunft = herkunft_bauen(quelle, plan["herkunft"], ziel) if "herkunft" in plan else None

    # 8) Töne
    toene = {}
    if plan.get("toene"):
        (ziel / "toene").mkdir()
        for name, t in plan["toene"].items():
            segmente = [tuple(x) for x in t["segmente"]]
            pcm = synthese(segmente, 1.0, welle=t.get("welle", "sinus"))
            schreibe_wav(ziel / "toene" / f"{name}.wav", pcm)
            toene[name] = f"toene/{name}.wav"

    # 9) Persönlichkeit, Lizenz, avatar.json
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
        "bewegung": plan.get("bewegung", {"art": "gehen", "tempo": 60}),
        "herkunft": herkunft,
        "portraet": portraet,
        "animationen": animationen,
        "toene": toene,
    }
    (ziel / "avatar.json").write_text(json.dumps(avatar, ensure_ascii=False, indent=2), encoding="utf-8")
    return ziel


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


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--vorlagen":
        vorlagen_exportieren(Path(sys.argv[2]).resolve())
        raise SystemExit(0)
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    quelle = Path(sys.argv[1]).resolve()
    if quelle.name == "zubehoer":
        zubehoer_bauen(quelle, WURZEL / "src" / "dmnt_kobold" / "zubehoer")
    else:
        print(f"Fertig: {bauen(quelle)}")
