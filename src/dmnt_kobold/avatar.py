"""Avatare: Laden aus einem Ordner und Darstellung.

Ein Avatar ist ein Ordner (siehe Konzept, Abschnitt 4):
  avatar.json, frames/<animation>/*.png, toene/*.wav, herkunft.*, portraet.png,
  verhalten.json (Regeln und Werte, siehe katalog.py), persoenlichkeit.py (optional,
  Sonderlogik in Python), LIZENZ.txt

Verhalten: ``verhalten.json`` wird von ``regeln.RegelPersoenlichkeit`` ausgewertet.
Eine ``persoenlichkeit.py`` läuft zusätzlich (Klasse ``Persoenlichkeit``, ein ``Modul``
mit ``SONDERLOGIK = [(Name, Beschreibung), ...]`` für den Editor). Ein Avatar ohne
``persoenlichkeit.py`` ist „ohne Code“: es wird kein Code aus dem Avatar ausgeführt.

Darsteller zeichnen den Avatar in das Overlay-Fenster und liefern dessen Maske:
- ``SpriteDarsteller``: Frames aus dem Avatar-Ordner
- ``BlobDarsteller``: der gezeichnete Platzhalter (Rückfall, wenn kein Avatar lädt)

Rückfall-Regeln: Fehlt eine Animation, gilt ``ruhe``. Interne Namen werden auf
das Kern-Vokabular abgebildet (``laufen`` → ``bewegen``).

Zubehör (z. B. Kopfhörer): Hat der Avatar eigene Frames ``<animation>@<zubehör>``
(z. B. ``bewegen@kopfhoerer``), werden diese genommen. Sonst wird das gemeinsame
Zubehörbild anhand der Kopfdaten je Frame (``koepfe``) aufgesetzt (Platzhalter).

Innenleben: Zubehör mit Sitz ``innen`` liegt im Körper – gezeichnet zwischen Rückwand
(``hinten`` je Frame, optional) und Körper (mit ``koerper_deckkraft``). Varianten je
Stimmung (``tnt@froh``) haben eigenen Versatz; fehlt eine, gilt die Grundvariante.

Körper (Aussehen, aus dem Bauplan): ``bewegung`` (gehen, gleiten, huepfen + Form beim
Stauchen/Strecken), ``partikel`` und Körper-Töne je Moment – siehe katalog.py.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBitmap, QColor, QImage, QPainter, QPixmap, QRegion, QTransform

from . import blob, katalog
from .toene import KoerperTon

log = logging.getLogger(__name__)

PAKET = Path(__file__).resolve().parent
AVATAR_ORDNER = PAKET / "avatare"
ZUBEHOER_ORDNER = PAKET / "zubehoer"
STANDARD_AVATAR = "dmnt9000"

NAMEN = katalog.NAMEN                  # intern → Kern-Vokabular
RAND_SEITE = 14
RAND_OBEN = 44                         # Platz für zzz und Zubehör
RAND_UNTEN = 8


@dataclass
class Zustand:
    """Was gezeichnet werden soll (vom Overlay je Takt gefüllt)."""
    animation: str = "ruhe"
    t: float = 0.0
    sx: float = 1.0
    sy: float = 1.0
    richtung: int = 1
    augen: str = "offen"
    mund: str = "laecheln"
    blick: tuple[float, float] = (0.0, 0.0)
    zzz: bool = False
    schatten: bool = True
    zubehoer: frozenset[str] = field(default_factory=frozenset)
    drehung: float | None = None             # Winkel beim Drehen (Grad), nur mit Frames „drehen“
    innen: str | None = None                 # Variante des Innenlebens, z. B. "froh"
    innen_versatz: tuple[float, float] = (0.0, 0.0)   # Nachwackeln (logische Pixel)


def _zubehoer_laden() -> dict[str, QPixmap]:
    ergebnis = {}
    for datei in sorted(ZUBEHOER_ORDNER.glob("*.png")):
        pm = QPixmap(str(datei))
        if not pm.isNull():
            ergebnis[datei.stem] = pm
    return ergebnis


def _zubehoer_zeichnen(p: QPainter, bilder: dict[str, QPixmap], namen: frozenset[str],
                       kopf_mitte: QPointF, kopf_breite: float, kopf_oben: float) -> None:
    pm = bilder.get("kopfhoerer")
    if pm is not None and "kopfhoerer" in namen:
        b = kopf_breite * 1.12
        h = b * pm.height() / pm.width()
        ziel = QRectF(kopf_mitte.x() - b / 2, kopf_oben - h * 0.3, b, h)
        p.drawPixmap(ziel, pm, QRectF(pm.rect()))


def _maske_aus_bild(bild: QImage) -> QRegion:
    """Alles mit etwas Deckkraft ist klickbar (inkl. weicher Kanten): Deckkraft per
    Plus-Überlagerung vervierfachen, dann bei 50 % schneiden (≈ Original ≥ 12 %)."""
    verstaerkt = QImage(bild.size(), QImage.Format.Format_ARGB32_Premultiplied)
    verstaerkt.fill(Qt.GlobalColor.transparent)
    p = QPainter(verstaerkt)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    for _ in range(4):
        p.drawImage(0, 0, bild)
    p.end()
    maske = verstaerkt.createAlphaMask(Qt.ImageConversionFlag.ThresholdAlphaDither)
    return QRegion(QBitmap.fromImage(maske))


class Darsteller:
    name = "?"
    breite = 96.0          # Körperbreite für die Physik
    hoehe = 92.0
    fenster_b = 150
    fenster_h = 140
    fuss = QPointF(75, 132)
    blickrichtung = 1
    animiert_sich_selbst = False   # Frames bewegen sich selbst (kein Wippen nötig)
    bewegung: dict = {"art": "gleiten"}
    partikel: dict = {}
    innenleben = False

    def hat(self, animation: str) -> bool:
        """Hat der Avatar eigene Frames für diese Animation?"""
        return False

    def zeichnen(self, p: QPainter, z: Zustand) -> None:
        raise NotImplementedError

    def maske(self, z: Zustand) -> QRegion:
        bild = QImage(self.fenster_b, self.fenster_h, QImage.Format.Format_ARGB32_Premultiplied)
        bild.fill(Qt.GlobalColor.transparent)
        p = QPainter(bild)
        self.zeichnen(p, z)
        p.end()
        return _maske_aus_bild(bild)

    def masken_schluessel(self, z: Zustand) -> tuple:
        return (round(z.sx, 2), round(z.sy, 2), z.richtung, z.schatten, z.zzz, z.zubehoer)

    def varianten(self, animation: str) -> list[str]:
        """Namen aller Varianten einer Animation (``sprechen``, ``sprechen~2`` …).
        Das Overlay wählt bei jedem Beginn zufällig eine."""
        return [animation]


class BlobDarsteller(Darsteller):
    name = "Blob"

    def __init__(self) -> None:
        self.breite, self.hoehe = blob.BREITE, blob.HOEHE
        self.fenster_b, self.fenster_h = 150, 140
        self.fuss = QPointF(75, 132)
        self._zubehoer = _zubehoer_laden()

    def zeichnen(self, p: QPainter, z: Zustand) -> None:
        blob.zeichne(p, self.fuss, z.sx, z.sy, z.richtung, z.augen, z.mund, z.blick, z.zzz, z.schatten)
        if z.zubehoer:
            p.save()
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            oben = self.fuss.y() - blob.HOEHE * z.sy
            _zubehoer_zeichnen(p, self._zubehoer, z.zubehoer, QPointF(self.fuss.x(), 0),
                               blob.BREITE * 0.82 * z.sx, oben + 4)
            p.restore()

    def maske(self, z: Zustand) -> QRegion:
        if z.zubehoer:
            return super().maske(z)
        return blob.maske(self.fuss, z.sx, z.sy, z.richtung, z.schatten, z.zzz)


@dataclass
class Animation:
    fps: float
    schleife: bool
    bilder: list[QPixmap]
    koepfe: list[tuple[float, float, float, float]]
    # Zubehör-Platzierung je Frame: teil → [[x, y, breite, winkel, hinten, aus], ...]
    # (x/y = Mitte relativ zum Fußpunkt, logische Pixel)
    zubehoer: dict[str, list[list[float]]] = field(default_factory=dict)
    hinten: list[QPixmap | None] = field(default_factory=list)    # Rückwand je Frame (Innenleben)

    def index(self, t: float) -> int:
        n = len(self.bilder)
        i = int(t * self.fps)
        return i % n if self.schleife else min(i, n - 1)


class Avatar:
    """Inhalt eines Avatar-Ordners (ohne Persönlichkeit)."""

    def __init__(self, ordner: Path) -> None:
        self.ordner = ordner
        daten = json.loads((ordner / "avatar.json").read_text(encoding="utf-8"))
        if daten.get("format") != 1:
            raise ValueError(f"Unbekanntes Avatar-Format in {ordner}")
        self.id = daten["id"]
        self.name = daten["name"]
        self.skalierung = float(daten.get("skalierung", 1))
        self.rahmen = tuple(daten["rahmen"])
        self.anker = tuple(daten["anker"])
        self.koerper = daten["koerper"]
        self.blickrichtung = int(daten.get("blickrichtung", 1))
        self.bewegung = dict(daten.get("bewegung") or {"art": "gehen"})
        self.bewegung.pop("tempo", None)          # alt: Tempo ist jetzt der Wert „laufgeschwindigkeit“
        if self.bewegung.get("art") == "huepfen":
            for k, v in katalog.HUEPF_STANDARD.items():
                self.bewegung.setdefault(k, v)
        self.partikel = {m: {**katalog.PARTIKEL_STANDARD, **d} for m, d in daten.get("partikel", {}).items()
                         if m in katalog.KERN_ANIMATIONEN and isinstance(d, dict)}
        self.koerper_deckkraft = float(daten.get("koerper_deckkraft", 1.0))
        self.herkunft = ordner / daten["herkunft"] if daten.get("herkunft") else None
        self.portraet = ordner / daten["portraet"] if daten.get("portraet") else None
        self.toene = {n: ordner / rel for n, rel in daten.get("toene", {}).items()
                      if isinstance(rel, str) and (ordner / rel).exists()}
        self.koerper_toene = {n: KoerperTon.aus_json(ordner, t) for n, t in daten.get("toene", {}).items()
                              if isinstance(t, dict)}
        self.animationen: dict[str, Animation] = {}
        for name, a in daten["animationen"].items():
            bilder = []
            for rel in a["bilder"]:
                pm = QPixmap(str(ordner / rel))
                if pm.isNull():
                    raise ValueError(f"Frame fehlt oder defekt: {rel}")
                pm.setDevicePixelRatio(self.skalierung)
                bilder.append(pm)
            koepfe = [tuple(k) for k in a.get("koepfe", [])] or [(self.anker[0], 0, self.koerper["breite"], 0)]
            while len(koepfe) < len(bilder):
                koepfe.append(koepfe[-1])
            hinten: list[QPixmap | None] = []
            for rel in a.get("hinten", []):
                pm = QPixmap(str(ordner / rel)) if rel else QPixmap()
                if not pm.isNull():
                    pm.setDevicePixelRatio(self.skalierung)
                hinten.append(None if pm.isNull() else pm)
            self.animationen[name] = Animation(float(a["fps"]), bool(a.get("schleife", True)), bilder, koepfe,
                                               dict(a.get("zubehoer", {})), hinten)
        if "ruhe" not in self.animationen:
            raise ValueError("Pflicht-Animation 'ruhe' fehlt")
        self.persoenlichkeit_datei = ordner / "persoenlichkeit.py"
        self.verhalten: dict | None = None
        if (ordner / "verhalten.json").is_file():
            try:
                self.verhalten = json.loads((ordner / "verhalten.json").read_text(encoding="utf-8"))
            except (OSError, ValueError):
                log.exception("verhalten.json von %s unlesbar – nehme das Standard-Verhalten", self.id)
        # Avatar-eigenes Zubehör (Bild + Platzierung je Frame, im Editor eingestellt)
        self.zubehoer_bilder: dict[str, QPixmap] = {}
        self.zubehoer_immer: list[str] = []
        self.innen: dict[str, dict[str, tuple[QPixmap, float, float]]] = {}   # teil → variante → (bild, x, y)
        for teil, z in daten.get("zubehoer", {}).items():
            pm = QPixmap(str(ordner / z["bild"]))
            if pm.isNull():
                continue
            self.zubehoer_bilder[teil] = pm
            if z.get("sitz") == "innen":
                varianten = {}
                for v, d in z.get("varianten", {}).items():
                    vpm = QPixmap(str(ordner / d["bild"]))
                    if not vpm.isNull():
                        varianten[v] = (vpm, float(d.get("x", 0)), float(d.get("y", 0)))
                self.innen[teil] = varianten
            if z.get("immer") or z.get("sitz") == "innen":     # Innenleben gehört zum Körper
                self.zubehoer_immer.append(teil)

    @property
    def ohne_code(self) -> bool:
        """Kein Python im Avatar-Ordner: Verhalten nur aus verhalten.json."""
        return not self.persoenlichkeit_datei.exists()

    @property
    def werte(self) -> katalog.Werte:
        return katalog.Werte((self.verhalten or {}).get("werte"))

    @property
    def lauftempo(self) -> float:
        """Wert „laufgeschwindigkeit“ (Standard aus dem Katalog)."""
        return float(self.werte["laufgeschwindigkeit"])

    @property
    def innen_varianten(self) -> set[str]:
        return {v for varianten in self.innen.values() for v in varianten}

    def animation(self, name: str) -> Animation:
        name = NAMEN.get(name, name)
        return self.animationen.get(name) or self.animationen["ruhe"]


class SpriteDarsteller(Darsteller):
    animiert_sich_selbst = True

    def __init__(self, avatar: Avatar) -> None:
        self.avatar = avatar
        self.name = avatar.name
        self.breite = float(avatar.koerper["breite"])
        self.hoehe = float(avatar.koerper["hoehe"])
        rb, rh = avatar.rahmen
        self.fenster_b = int(math.ceil(rb + 2 * RAND_SEITE))
        self.fenster_h = int(math.ceil(rh + RAND_OBEN + RAND_UNTEN))
        self._links = (self.fenster_b - rb) / 2
        self.bewegung = avatar.bewegung
        self.partikel = avatar.partikel
        self.innenleben = bool(avatar.innen)
        rand = katalog.PARTIKEL_RAND if avatar.partikel else 0     # Platz für Spritzer
        self.fenster_b += 2 * rand
        self.fenster_h += rand
        self._links = (self.fenster_b - rb) / 2
        self.fuss = QPointF(self._links + avatar.anker[0], RAND_OBEN + avatar.anker[1])
        self.blickrichtung = avatar.blickrichtung
        self._zubehoer = _zubehoer_laden()

    def hat(self, animation: str) -> bool:
        return NAMEN.get(animation, animation) in self.avatar.animationen

    def _frame(self, z: Zustand) -> tuple[int, Animation, frozenset[str]]:
        """Frame-Index, Animation und das noch aufzusetzende Zubehör."""
        name = NAMEN.get(z.animation, z.animation)
        if name not in self.avatar.animationen:
            name = "ruhe"
        rest = set(z.zubehoer)
        for teil in sorted(z.zubehoer):
            variante = f"{name}@{teil}"
            if variante in self.avatar.animationen:
                name = variante
                rest.discard(teil)
                break
        a = self.avatar.animationen[name]
        if z.drehung is not None and name == "drehen" and len(a.bilder) > 1:
            phi = z.drehung % 360           # vorne → … → hinten, zweite Hälfte rückwärts (gespiegelt)
            halb = phi if phi <= 180 else 360 - phi
            return round(halb / 180 * (len(a.bilder) - 1)), a, frozenset(rest)
        return a.index(z.t), a, frozenset(rest)

    def zeichnen(self, p: QPainter, z: Zustand) -> None:
        i, a, zubehoer = self._frame(z)
        pm = a.bilder[i]
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        if z.schatten:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, int(255 * 0.18)))
            w = self.breite * 0.8 * z.sx
            p.drawEllipse(QRectF(self.fuss.x() - w / 2, self.fuss.y() - 5, w, 10))
        spiegeln = -1 if z.richtung != self.blickrichtung else 1
        t = QTransform()
        t.translate(self.fuss.x(), self.fuss.y())
        t.scale(z.sx * spiegeln, z.sy)
        t.translate(-self.avatar.anker[0], -self.avatar.anker[1])
        p.setTransform(t, True)
        eigene = {t for t in zubehoer if t in a.zubehoer and t in self.avatar.zubehoer_bilder}
        innen = {t for t in eigene if t in self.avatar.innen}
        aussen = eigene - innen
        if aussen:
            self._eigenes_zubehoer(p, a, i, aussen, vorne=False)
        if i < len(a.hinten) and a.hinten[i] is not None:      # Rückwand
            p.drawPixmap(QPointF(0, 0), a.hinten[i])
        if innen:
            self._innenleben(p, a, i, innen, z, z.sx * spiegeln, z.sy)
        if self.avatar.koerper_deckkraft < 1.0:
            p.setOpacity(self.avatar.koerper_deckkraft)
        p.drawPixmap(QPointF(0, 0), pm)
        p.setOpacity(1.0)
        if zubehoer:
            self._eigenes_zubehoer(p, a, i, aussen, vorne=True)
            rest = frozenset(zubehoer - eigene)
            if rest:
                kx, _ky, kb, ko = a.koepfe[i]
                _zubehoer_zeichnen(p, self._zubehoer, rest, QPointF(kx, 0), kb, ko)
        p.restore()
        if z.zzz:
            _zzz(p, QPointF(self.fuss.x() + self.breite * 0.25, RAND_OBEN - 2))

    def _eigenes_zubehoer(self, p: QPainter, a: Animation, i: int, teile: set[str], vorne: bool) -> None:
        """Zubehör mit eigener Platzierung zeichnen (im Frame-Koordinatensystem).
        ``vorne=False`` zeichnet nur, was hinter dem Körper liegt."""
        ax, ay = self.avatar.anker
        for teil in sorted(teile):
            werte = a.zubehoer[teil]
            x, y, b, winkel, hinten, aus, hoehe = (list(werte[min(i, len(werte) - 1)]) + [0, 0, 0, 100])[:7]
            if aus or bool(hinten) == vorne:
                continue
            pm = self.avatar.zubehoer_bilder[teil]
            h = b * pm.height() / pm.width() * (hoehe or 100) / 100
            p.save()
            p.translate(ax + x, ay + y)
            if winkel:
                p.rotate(winkel)
            p.drawPixmap(QRectF(-b / 2, -h / 2, b, h), pm, QRectF(pm.rect()))
            p.restore()

    def _innenleben(self, p: QPainter, a: Animation, i: int, teile: set[str], z: Zustand,
                    sx: float, sy: float) -> None:
        """Gegenstand im Körper: Variante (sonst Grundvariante), eigener Versatz und
        Nachwackeln. Macht Stauchen, Strecken und Drehen mit (gleiche Transformation)."""
        ax, ay = self.avatar.anker
        dx, dy = z.innen_versatz
        dx, dy = dx / (sx or 1), dy / (sy or 1)          # Wackeln in Bildschirm-Richtung
        for teil in sorted(teile):
            werte = a.zubehoer[teil]
            x, y, b, winkel, _hinten, aus, hoehe = (list(werte[min(i, len(werte) - 1)]) + [0, 0, 0, 100])[:7]
            if aus:
                continue
            pm = self.avatar.zubehoer_bilder[teil]
            variante = self.avatar.innen[teil].get(z.innen or "")
            if variante is not None:
                pm, vx, vy = variante
                x, y = x + vx, y + vy
            h = b * pm.height() / pm.width() * (hoehe or 100) / 100
            p.save()
            p.translate(ax + x + dx, ay + y + dy)
            if winkel:
                p.rotate(winkel)
            p.drawPixmap(QRectF(-b / 2, -h / 2, b, h), pm, QRectF(pm.rect()))
            p.restore()

    def varianten(self, animation: str) -> list[str]:
        name = NAMEN.get(animation, animation)
        namen = [n for n in self.avatar.animationen
                 if "@" not in n and (n == name or n.startswith(name + "~"))]
        return sorted(namen) or [animation]

    def masken_schluessel(self, z: Zustand) -> tuple:
        i, a, _ = self._frame(z)
        return (id(a), i, round(z.sx, 2), round(z.sy, 2), z.richtung, z.schatten, z.zzz, z.zubehoer,
                z.innen if self.innenleben else None)


def _zzz(p: QPainter, ort: QPointF) -> None:
    from PySide6.QtGui import QFont
    p.save()
    f = QFont("Segoe UI")
    f.setBold(True)
    farbe = QColor("#9AA39E")
    p.setPen(farbe)
    f.setPixelSize(12)
    p.setFont(f)
    p.drawText(ort + QPointF(0, 0), "z")
    f.setPixelSize(16)
    p.setFont(f)
    p.drawText(ort + QPointF(10, -14), "z")
    p.restore()


# --- Laden ---------------------------------------------------------------------


def avatar_laden(avatar_id: str = STANDARD_AVATAR, ordner: Path | None = None) -> tuple[Darsteller, Avatar | None]:
    """Lädt einen mitgelieferten (offiziellen) Avatar. Fremde Avatare brauchen ab M4
    eine Zustimmung. Bei jedem Fehler: Blob als Rückfall, der Kobold läuft weiter.
    ``ordner``: gebauter Avatar-Ordner außerhalb des Pakets (nur Entwickler, --avatar-pfad)."""
    ordner = ordner or AVATAR_ORDNER / avatar_id
    try:
        avatar = Avatar(ordner)
        log.info("Avatar geladen: %s (%d Animationen)", avatar.name, len(avatar.animationen))
        return SpriteDarsteller(avatar), avatar
    except Exception:  # noqa: BLE001
        log.exception("Avatar %s konnte nicht geladen werden – nehme den Blob", avatar_id)
        return BlobDarsteller(), None


def avatar_liste() -> list[tuple[str, str, Path | None]]:
    """Mitgelieferte Avatare: (id, Name, Porträt)."""
    liste = []
    for ordner in sorted(p for p in AVATAR_ORDNER.iterdir() if (p / "avatar.json").is_file()):
        try:
            daten = json.loads((ordner / "avatar.json").read_text(encoding="utf-8"))
            portraet = ordner / daten["portraet"] if daten.get("portraet") else None
            liste.append((daten["id"], daten["name"], portraet))
        except (OSError, ValueError, KeyError):
            log.warning("Avatar-Ordner %s unlesbar", ordner.name)
    return liste


def avatar_icon(avatar: Avatar | None):
    """Tray-/Fenster-Icon aus dem Porträt (oberes Quadrat = Kopf). None ohne Porträt."""
    from PySide6.QtGui import QIcon

    if avatar is None or avatar.portraet is None or not avatar.portraet.exists():
        return None
    pm = QPixmap(str(avatar.portraet))
    if pm.isNull():
        return None
    seite = min(pm.width(), pm.height())
    kopf = pm.copy((pm.width() - seite) // 2, 0, seite, seite)
    icon = QIcon()
    for g in (16, 24, 32, 48, 64, 128):
        icon.addPixmap(kopf.scaled(g, g, Qt.AspectRatioMode.KeepAspectRatio,
                                   Qt.TransformationMode.SmoothTransformation))
    return icon


def persoenlichkeiten_laden(avatar: Avatar | None, bus, motor, werte: katalog.Werte | None = None) -> list:
    """Verhalten eines Avatars: Regeln aus verhalten.json und – falls vorhanden – die
    Sonderlogik aus persoenlichkeit.py (läuft zusätzlich). Ohne beides: Standard-Reaktionen."""
    from .reaktionen import Reaktionen
    from .regeln import RegelPersoenlichkeit

    liste = []
    if avatar is not None and avatar.verhalten is not None:
        liste.append(RegelPersoenlichkeit(bus, motor, avatar.verhalten, name=avatar.id,
                                          werte=werte or avatar.werte))
    if avatar is not None and avatar.persoenlichkeit_datei.exists():
        try:
            spec = importlib.util.spec_from_file_location(
                f"dmnt_avatar_{avatar.id}", avatar.persoenlichkeit_datei)
            modul = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modul)  # type: ignore[union-attr]
            liste.append(modul.Persoenlichkeit(bus, motor))
        except Exception:  # noqa: BLE001
            log.exception("persoenlichkeit.py von %s fehlerhaft – nur die Regeln laufen", avatar.id)
    if not liste:
        liste.append(Reaktionen(bus, motor))
    return liste


def persoenlichkeit_laden(avatar: Avatar | None, bus, motor):
    """Wie ``persoenlichkeiten_laden``, liefert die erste (Regeln, sonst Sonderlogik)."""
    return persoenlichkeiten_laden(avatar, bus, motor)[0]


def beobachtete_programme(persoenlichkeiten: list) -> set[str]:
    ergebnis: set[str] = set()
    for p in persoenlichkeiten:
        ergebnis |= set(getattr(p, "BEOBACHTETE_PROGRAMME", set()))
    return ergebnis
