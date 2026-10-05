"""Reiter „Effekte“ im Avatar-Editor: was über dem Kopf schwebt.

Oben die Galerie (alle Effekte laufen als Vorschau), darunter die Zuordnung „Animation →
Effekt“ und die eigenen Effekte des Avatars (PNG-Bildfolgen). Gespeichert wird im Bauplan
unter ``effekte`` (``zuordnung``, ``eigene``); danach baut der Editor wie gewohnt neu.
In Regeln gibt es zusätzlich die Aktion „effekt“ (Reiter Verhalten).
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (QComboBox, QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from dmnt_kobold import effekte, katalog, stil

GRAU = "#8A938E"
BILDER = "Bilder (*.png)"


# --- Datenänderungen (ohne Fenster, testbar) ---------------------------------------

def _block(projekt) -> dict:
    return projekt.bauplan.setdefault("effekte", {})


def _aufraeumen(projekt) -> None:
    e = projekt.bauplan.get("effekte", {})
    for k in ("zuordnung", "eigene"):
        if k in e and not e[k]:
            del e[k]
    if not e:
        projekt.bauplan.pop("effekte", None)


def animationen(projekt) -> list[str]:
    """Kern-Animationen + die des Avatars (ohne Varianten ~n und Zubehör @x)."""
    eigene = {n.split("~")[0] for n in projekt.bauplan.get("animationen", {}) if "@" not in n}
    return list(katalog.KERN_ANIMATIONEN) + sorted(eigene - set(katalog.KERN_ANIMATIONEN))


def zuordnung_setzen(projekt, animation: str, name: str | None) -> None:
    """``None`` = Standard (Eintrag weg), ``""`` = bewusst kein Effekt, sonst Effekt-Name."""
    z = _block(projekt).setdefault("zuordnung", {})
    if name is None or name == effekte.STANDARD_ZUORDNUNG.get(animation, ""):
        z.pop(animation, None)
    else:
        z[animation] = name
    _aufraeumen(projekt)
    projekt.bauplan_speichern()


def eigene(projekt) -> dict:
    return dict((projekt.bauplan.get("effekte") or {}).get("eigene") or {})


def eigenen_hinzufuegen(projekt, name: str, dateien: list[Path]) -> str:
    """Bildfolge als eigenen Effekt übernehmen (Kopien nach ``effekte/<name>/``)."""
    name = name.strip().lower()
    if not re.fullmatch(effekte.NAME_MUSTER, name):
        raise ValueError("Namen bitte nur aus a–z, 0–9 und _")
    if name in effekte.EINGEBAUT or name in eigene(projekt):
        raise ValueError(f"„{name}“ gibt es schon")
    if not dateien:
        raise ValueError("Keine Bilder gewählt")
    ordner = projekt.ordner / "effekte" / name
    ordner.mkdir(parents=True, exist_ok=True)
    for n, datei in enumerate(dateien, 1):
        shutil.copy2(datei, ordner / f"{n:02d}.png")
    _block(projekt).setdefault("eigene", {})[name] = {"ordner": f"effekte/{name}", "fps": 8, "breite": 40}
    projekt.bauplan_speichern()
    return name


def eigenen_einstellen(projekt, name: str, **werte) -> None:
    d = _block(projekt).get("eigene", {}).get(name)
    if d is None:
        return
    for k, v in werte.items():
        if v is not None:
            d[k] = round(float(v), 1)
    projekt.bauplan_speichern()


def eigenen_entfernen(projekt, name: str) -> None:
    """Aus dem Bauplan nehmen (Bilder bleiben im Ordner), Zuordnungen darauf fallen weg."""
    e = _block(projekt)
    e.get("eigene", {}).pop(name, None)
    for anim, n in list(e.get("zuordnung", {}).items()):
        if n == name:
            del e["zuordnung"][anim]
    _aufraeumen(projekt)
    projekt.bauplan_speichern()


def vorschau_effekte(projekt) -> dict[str, effekte.EigenerEffekt]:
    """Eigene Effekte direkt aus den Quellen (ohne Bau) für die Vorschau."""
    ergebnis = {}
    for name, d in eigene(projekt).items():
        bilder = [QPixmap(str(p)) for p in sorted((projekt.ordner / d.get("ordner", "")).glob("*.png"))]
        bilder = [b for b in bilder if not b.isNull()]
        if bilder:
            ergebnis[name] = effekte.EigenerEffekt(bilder, float(d.get("fps", 8)), float(d.get("breite", 40)),
                                                   float(d.get("hoehe_ueber_kopf", 6)))
    return ergebnis


# --- Fenster -----------------------------------------------------------------------

class EffektVorschau(QWidget):
    """Ein Effekt über einem angedeuteten Kopf, läuft in Schleife."""

    def __init__(self, name: str, eigene_effekte: dict, parent=None) -> None:
        super().__init__(parent)
        self.name = name
        self.eigene = eigene_effekte
        self.t = 0.0
        self.setFixedSize(120, 146)
        self.setToolTip(effekte.EINGEBAUT.get(name, "eigener Effekt"))

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor("#FFFFFF"))
        p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 14, 14)
        kopf = QPointF(self.width() / 2, self.height() - 52)
        p.setBrush(QColor("#C9CEC9"))                       # angedeuteter Kopf
        p.drawEllipse(QRectF(kopf.x() - 22, kopf.y(), 44, 30))
        effekte.zeichnen(p, self.name, self.t, kopf, 44, 1, self.eigene)
        p.setPen(QColor(stil.NEBENTEXT))
        p.drawText(QRectF(0, self.height() - 20, self.width(), 18), Qt.AlignmentFlag.AlignCenter, self.name)
        p.end()


class EffekteTab(QWidget):
    def __init__(self, editor) -> None:
        super().__init__()
        self.editor = editor
        self._vorschauen: list[EffektVorschau] = []
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        info = QLabel("Effekte schweben über dem Kopf – unabhängig von der Animation, durchklickbar. "
                      "Hier legst du fest, welche Animation welchen Effekt zeigt. In Regeln gibt es dazu die "
                      "Aktion „effekt“ (Reiter Verhalten).")
        info.setWordWrap(True)
        kopf.addWidget(info, 1)
        zurueck = QPushButton("Effekte zurücksetzen …")
        zurueck.clicked.connect(self._zuruecksetzen)
        kopf.addWidget(zurueck, 0, Qt.AlignmentFlag.AlignTop)
        lay.addLayout(kopf)
        self.bereich = QScrollArea()
        self.bereich.setWidgetResizable(True)
        lay.addWidget(self.bereich, 1)
        self._takt = QTimer(self)
        self._takt.setInterval(33)
        self._takt.timeout.connect(self._weiter)

    @property
    def projekt(self):
        return self.editor.projekt

    def showEvent(self, e) -> None:  # noqa: N802
        self._takt.start()
        super().showEvent(e)

    def hideEvent(self, e) -> None:  # noqa: N802
        self._takt.stop()
        super().hideEvent(e)

    def _weiter(self) -> None:
        for v in self._vorschauen:
            v.t += 0.033
            v.update()

    @staticmethod
    def _karte(titel: str, text: str = "") -> tuple[QFrame, QVBoxLayout]:
        karte = QFrame()
        karte.setObjectName("karte")
        v = QVBoxLayout(karte)
        v.setContentsMargins(18, 16, 18, 16)
        t = QLabel(titel)
        t.setStyleSheet("font-weight: 800; font-size: 16px;")
        v.addWidget(t)
        if text:
            n = QLabel(text)
            n.setObjectName("neben")
            n.setWordWrap(True)
            v.addWidget(n)
        return karte, v

    def aufbauen(self) -> None:
        self._vorschau_effekte = vorschau_effekte(self.projekt)
        self._vorschauen = []
        innen = QWidget()
        lay = QVBoxLayout(innen)
        lay.setSpacing(16)
        lay.addWidget(self._galerie())
        lay.addWidget(self._zuordnung())
        lay.addWidget(self._eigene())
        lay.addStretch(1)
        self.bereich.setWidget(innen)

    def _galerie(self) -> QFrame:
        karte, v = self._karte("Alle Effekte", "Eingebaut und eigene dieses Avatars. Fahr mit der Maus "
                                               "drüber für eine Beschreibung.")
        reihe = QGridLayout()
        reihe.setSpacing(10)
        namen = list(effekte.EINGEBAUT) + sorted(self._vorschau_effekte)
        for i, name in enumerate(namen):
            vs = EffektVorschau(name, self._vorschau_effekte)
            self._vorschauen.append(vs)
            reihe.addWidget(vs, i // 6, i % 6)
        reihe.setColumnStretch(6, 1)
        v.addLayout(reihe)
        return karte

    def _zuordnung(self) -> QFrame:
        karte, v = self._karte("Effekt zur Animation", "Läuft, solange die Animation zu sehen ist. "
                                                       "Ein Effekt aus einer Regel hat Vorrang.")
        gitter = QGridLayout()
        gitter.setHorizontalSpacing(14)
        z = (self.projekt.bauplan.get("effekte") or {}).get("zuordnung") or {}
        auswahl = list(effekte.EINGEBAUT) + sorted(eigene(self.projekt))
        for zeile, anim in enumerate(animationen(self.projekt)):
            name = QLabel(anim)
            name.setStyleSheet("font-weight: 700;")
            name.setToolTip(katalog.KERN_ANIMATIONEN.get(anim, ("eigene Animation", ""))[0])
            gitter.addWidget(name, zeile, 0)
            box = QComboBox()
            standard = effekte.STANDARD_ZUORDNUNG.get(anim)
            box.addItem(f"Standard ({standard})" if standard else "kein Effekt", None)
            if standard:
                box.addItem("kein Effekt", "")
            for n in auswahl:
                box.addItem(n, n)
            gesetzt = z.get(anim)
            i = box.findData(gesetzt) if gesetzt is not None else 0
            box.setCurrentIndex(max(0, i))
            box.currentIndexChanged.connect(lambda _i, a=anim, b=box: self._setzen(a, b.currentData()))
            gitter.addWidget(box, zeile, 1)
            if gesetzt and gesetzt not in auswahl:
                warn = QLabel(f"„{gesetzt}“ gibt es nicht")
                warn.setStyleSheet(f"color: {stil.ROT};")
                gitter.addWidget(warn, zeile, 2)
        gitter.setColumnStretch(2, 1)
        v.addLayout(gitter)
        return karte

    def _eigene(self) -> QFrame:
        karte, v = self._karte("Eigene Effekte", "Eine Bildfolge aus PNG-Dateien (transparent), z. B. 4–8 Bilder. "
                                                 "Breite in Pixeln, Höhe = Abstand über dem Kopf.")
        gitter = QGridLayout()
        gitter.setHorizontalSpacing(12)
        for zeile, (name, d) in enumerate(sorted(eigene(self.projekt).items())):
            gitter.addWidget(QLabel(f"<b>{name}</b>"), zeile, 0)
            for spalte, (k, text, lo, hi, std) in enumerate((("fps", "Bilder/s", 1, 30, 8),
                                                              ("breite", "Breite", 8, 200, 40),
                                                              ("hoehe_ueber_kopf", "Höhe", -60, 80, 6)), 1):
                feld = QDoubleSpinBox()
                feld.setRange(lo, hi)
                feld.setDecimals(0)
                feld.setPrefix(f"{text}: ")
                feld.setValue(float(d.get(k, std)))
                feld.valueChanged.connect(lambda w, n=name, k=k: self._einstellen(n, k, w))
                gitter.addWidget(feld, zeile, spalte)
            weg = QPushButton("Entfernen")
            weg.setToolTip("Aus dem Avatar nehmen (die Bilder bleiben im Ordner)")
            weg.clicked.connect(lambda _=False, n=name: self._entfernen(n))
            gitter.addWidget(weg, zeile, 4)
        gitter.setColumnStretch(5, 1)
        v.addLayout(gitter)
        dazu = QPushButton("Eigenen Effekt hinzufügen …")
        dazu.setObjectName("haupt")
        dazu.clicked.connect(self._hinzufuegen)
        v.addWidget(dazu, 0, Qt.AlignmentFlag.AlignLeft)
        return karte

    # --- Aktionen ----------------------------------------------------------------------
    def _setzen(self, anim: str, name) -> None:
        zuordnung_setzen(self.projekt, anim, name)
        text = "Standard" if name is None else (name or "kein Effekt")
        self.editor.meldung(f"Effekt für {anim}: {text}")
        self.editor.geaendert()

    def _einstellen(self, name: str, k: str, wert: float) -> None:
        eigenen_einstellen(self.projekt, name, **{k: wert})
        self._vorschau_effekte.update(vorschau_effekte(self.projekt))
        for vs in self._vorschauen:
            vs.eigene = self._vorschau_effekte
        self.editor.geaendert()

    def _entfernen(self, name: str) -> None:
        eigenen_entfernen(self.projekt, name)
        self.editor.meldung(f"Effekt {name} entfernt (Bilder liegen weiter in effekte/{name}/).")
        self.aufbauen()
        self.editor.geaendert()

    def _hinzufuegen(self) -> None:
        dateien, _ = QFileDialog.getOpenFileNames(self, "Bilder für den Effekt (in Reihenfolge)",
                                                  str(Path.home() / "Downloads"), BILDER)
        if not dateien:
            return
        name, ok = QInputDialog.getText(self, "Eigener Effekt", "Name (a–z, 0–9, _):",
                                        text=Path(dateien[0]).stem.lower().split("_")[0])
        if not ok:
            return
        try:
            name = eigenen_hinzufuegen(self.projekt, name, sorted(Path(d) for d in dateien))
        except ValueError as e:
            self.editor.meldung(f"Effekt nicht übernommen: {e}")
            return
        self.editor.meldung(f"Effekt {name}: {len(dateien)} Bild(er) übernommen.")
        self.aufbauen()
        self.editor.geaendert()

    def _zuruecksetzen(self) -> None:
        from editor_zuruecksetzen import fragen_und_zuruecksetzen  # noqa: PLC0415

        stand = fragen_und_zuruecksetzen(self, self.projekt, "effekte")
        if stand is None:
            return
        self.editor.meldung(f"Effekte zurückgesetzt auf: {stand.name} {stand.zeit}".strip()
                            + ". Der vorige Stand liegt im Verlauf.")
        self.aufbauen()
        self.editor.geaendert()
