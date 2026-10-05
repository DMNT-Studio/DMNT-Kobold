"""Avatare: Laden aus einem Ordner und Darstellung.

Ein Avatar ist ein Ordner (siehe Konzept, Abschnitt 4):
  avatar.json, frames/<animation>/*.png, toene/*.wav, herkunft.*, portraet.png,
  persoenlichkeit.py, LIZENZ.txt

Darsteller zeichnen den Avatar in das Overlay-Fenster und liefern dessen Maske:
- ``SpriteDarsteller``: Frames aus dem Avatar-Ordner
- ``BlobDarsteller``: der gezeichnete Platzhalter (Rückfall, wenn kein Avatar lädt)

Rückfall-Regeln: Fehlt eine Animation, gilt ``ruhe``. Interne Namen werden auf
das Kern-Vokabular abgebildet (``laufen`` → ``bewegen``).

Zubehör (z. B. Kopfhörer): Hat der Avatar eigene Frames ``<animation>@<zubehör>``
(z. B. ``bewegen@kopfhoerer``), werden diese genommen. Sonst wird das gemeinsame
Zubehörbild anhand der Kopfdaten je Frame (``koepfe``) aufgesetzt (Platzhalter).
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

from . import blob

log = logging.getLogger(__name__)

PAKET = Path(__file__).resolve().parent
AVATAR_ORDNER = PAKET / "avatare"
ZUBEHOER_ORDNER = PAKET / "zubehoer"
STANDARD_AVATAR = "dmnt9000"

NAMEN = {"laufen": "bewegen"}          # intern → Kern-Vokabular
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
        self.bewegung = daten.get("bewegung", {})
        self.herkunft = ordner / daten["herkunft"] if daten.get("herkunft") else None
        self.portraet = ordner / daten["portraet"] if daten.get("portraet") else None
        self.toene = {n: ordner / rel for n, rel in daten.get("toene", {}).items()
                      if (ordner / rel).exists()}
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
            self.animationen[name] = Animation(float(a["fps"]), bool(a.get("schleife", True)), bilder, koepfe)
        if "ruhe" not in self.animationen:
            raise ValueError("Pflicht-Animation 'ruhe' fehlt")
        self.persoenlichkeit_datei = ordner / "persoenlichkeit.py"

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
        self.fuss = QPointF(self._links + avatar.anker[0], RAND_OBEN + avatar.anker[1])
        self.blickrichtung = avatar.blickrichtung
        self._zubehoer = _zubehoer_laden()

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
        p.drawPixmap(QPointF(0, 0), pm)
        if zubehoer:
            kx, _ky, kb, ko = a.koepfe[i]
            _zubehoer_zeichnen(p, self._zubehoer, zubehoer, QPointF(kx, 0), kb, ko)
        p.restore()
        if z.zzz:
            _zzz(p, QPointF(self.fuss.x() + self.breite * 0.25, RAND_OBEN - 2))

    def masken_schluessel(self, z: Zustand) -> tuple:
        i, a, _ = self._frame(z)
        return (id(a), i, round(z.sx, 2), round(z.sy, 2), z.richtung, z.schatten, z.zzz, z.zubehoer)


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


def avatar_laden(avatar_id: str = STANDARD_AVATAR) -> tuple[Darsteller, Avatar | None]:
    """Lädt einen mitgelieferten (offiziellen) Avatar. Fremde Avatare brauchen ab M4
    eine Zustimmung. Bei jedem Fehler: Blob als Rückfall, der Kobold läuft weiter."""
    ordner = AVATAR_ORDNER / avatar_id
    try:
        avatar = Avatar(ordner)
        log.info("Avatar geladen: %s (%d Animationen)", avatar.name, len(avatar.animationen))
        return SpriteDarsteller(avatar), avatar
    except Exception:  # noqa: BLE001
        log.exception("Avatar %s konnte nicht geladen werden – nehme den Blob", avatar_id)
        return BlobDarsteller(), None


def persoenlichkeit_laden(avatar: Avatar | None, bus, motor):
    """Persönlichkeit aus dem Avatar-Ordner (Klasse ``Persoenlichkeit``), sonst Standard."""
    from .reaktionen import Reaktionen

    if avatar is not None and avatar.persoenlichkeit_datei.exists():
        try:
            spec = importlib.util.spec_from_file_location(
                f"dmnt_avatar_{avatar.id}", avatar.persoenlichkeit_datei)
            modul = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(modul)  # type: ignore[union-attr]
            return modul.Persoenlichkeit(bus, motor)
        except Exception:  # noqa: BLE001
            log.exception("Persönlichkeit von %s fehlerhaft – nehme die Standard-Reaktionen", avatar.id)
    return Reaktionen(bus, motor)
