"""Avatar-Editor (Werkzeug für Avatar-Bauer, nicht für Nutzer).

Start:  .venv\\Scripts\\pythonw.exe werkzeuge\\avatar_editor.py   (oder Avatar-Editor.bat)

Drei Bereiche:
  Bilder       jede Pose des Avatars mit „wofür benutzt“; öffnen, bearbeiten, ersetzen,
               Größe feinjustieren, neue Bilder hinzufügen
  Animationen  welche Pose mit welchem Augen-Effekt in welcher Animation steckt;
               Bilder tauschen, umsortieren, Tempo, Vorschau
  Zubehör      Kopfhörer, Hüte & Co.: Bild, Sitz, „immer tragen“ und für jede Pose
               Position/Größe/Drehung per Maus (ziehen, Mausrad, Umschalt+Mausrad);
               Sitz „im Körper“ = Innenleben mit Varianten je Stimmung (tnt@froh)
  Verhalten    Werte, Regeln (Wenn … → Dann …) und was der Avatar kann – siehe
               editor_verhalten.py, geprüft gegen den Katalog des Sockels

Grundlage sind die Quellen (quellen/<id>/bauplan.json, zubehoer.json, verhalten.json, Bilder).
Nach jeder Änderung baut der Editor den Avatar neu (werkzeuge/avatar_bauen.py),
danach „Kobold neu starten“, um es live zu sehen.
"""
from __future__ import annotations

import copy
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

from PySide6.QtCore import (QEvent, QFileSystemWatcher, QObject, QPointF, QProcess, QRectF, QSize, Qt, QTimer,
                            Signal)
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QAbstractScrollArea, QAbstractSpinBox, QApplication, QCheckBox, QComboBox,
                               QDoubleSpinBox, QFileDialog, QFormLayout, QFrame, QGridLayout, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
                               QTabWidget, QToolBar, QVBoxLayout, QWidget)

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "src"))
from dmnt_kobold import stil  # noqa: E402
from dmnt_kobold.regeln import standard_verhalten  # noqa: E402
from editor_herkunft import HerkunftToeneTab  # noqa: E402
from editor_verhalten import VerhaltenTab  # noqa: E402

QUELLEN = WURZEL / "quellen"
VORSCHAU = WURZEL / "build" / "vorschau"
AVATARE = WURZEL / "src" / "dmnt_kobold" / "avatare"
EFFEKTE = ["normal", "puls", "hell", "grell", "dunkel", "aus"]
HAENDE = ["", "daumen_runter"]
BAU_PAUSE_MS = 1500


# --- Hilfen ----------------------------------------------------------------------

def hintergrund_erkennen(pfad: Path) -> str | None:
    """Transparent → None, sonst Farbe der Ecken: "schwarz" oder "weiss"."""
    from PIL import Image

    im = Image.open(pfad)
    if im.mode in ("RGBA", "LA", "P"):
        a = im.convert("RGBA")
        w, h = a.size
        ecken = [a.getpixel((x, y))[3] for x in (0, w - 1) for y in (0, h - 1)]
        if sum(e < 20 for e in ecken) >= 3:
            return None
    rgb = im.convert("RGB")
    w, h = rgb.size
    ecken = [sum(rgb.getpixel((x, y))) / 3 for x in (2, w - 3) for y in (2, h - 3)]
    mittel = sum(ecken) / 4
    if mittel < 50:
        return "schwarz"
    if mittel > 200:
        return "weiss"
    return None


def oeffnen(pfad: Path, bearbeiten: bool = False) -> None:
    if sys.platform == "win32":
        if bearbeiten:
            try:
                os.startfile(str(pfad), "edit")  # noqa: S606 – Standard-Bildbearbeitung (meist Paint)
                return
            except OSError:
                subprocess.Popen(["mspaint", str(pfad)])
                return
        os.startfile(str(pfad))  # noqa: S606
    else:
        subprocess.Popen(["xdg-open", str(pfad)])


def frisch(pfad) -> QPixmap:
    """Bild immer frisch von der Platte (QPixmap(pfad) nutzt Qts Bild-Cache –
    nach einem Neubau könnte sonst das alte Bild erscheinen)."""
    from PySide6.QtGui import QImage

    return QPixmap.fromImage(QImage(str(pfad)))


def pose_name(schluessel: str) -> str:
    q, nr = schluessel.split(":")
    return f"{q} · Bild {int(nr) + 1}"


# --- Datenmodell -----------------------------------------------------------------

VERLAUF_MAX = 300          # so viele alte Fassungen je JSON-Datei bleiben in _alt/verlauf/
_FEHLT = object()


def drei_wege(basis, mein, platte):
    """Dreiwege-Zusammenführung für JSON-Daten: Was ich seit ``basis`` geändert habe,
    kommt auf den Stand von der Platte – fremde Änderungen (anderer Editor, Claude)
    bleiben erhalten. Listen und Werte gelten als Ganzes."""
    if not (isinstance(basis, dict) and isinstance(mein, dict) and isinstance(platte, dict)):
        return platte if mein == basis else mein
    ergebnis = dict(platte)
    for k in set(basis) | set(mein):
        b = basis.get(k, _FEHLT)
        if k not in mein:                                  # von mir gelöscht
            if k in ergebnis and b is not _FEHLT and ergebnis[k] == b:
                del ergebnis[k]
            continue
        m = mein[k]
        if b is not _FEHLT and m == b:                     # von mir nicht angefasst
            continue
        if k in ergebnis and b is not _FEHLT:
            ergebnis[k] = drei_wege(b, m, ergebnis[k])
        else:
            ergebnis[k] = m
    return ergebnis


def ersetzen(tmp: Path, pfad: Path, text: str, versuche: int = 5) -> None:
    """Atomar ersetzen. Unter Windows schlägt das fehl, solange ein anderes Programm die
    Datei offen hält (Virenscanner, Indexer, ein Werkzeug) – dann kurz warten und nochmal,
    zuletzt direkt hineinschreiben. Die alte Fassung liegt da schon im Verlauf."""
    for i in range(versuche):
        try:
            os.replace(tmp, pfad)
            return
        except PermissionError:
            time.sleep(0.05 * (i + 1))
    pfad.write_text(text, encoding="utf-8")
    tmp.unlink(missing_ok=True)


class Projekt:
    """Quellen eines Avatars + die Vorschau des letzten Baus."""

    def __init__(self, ordner: Path) -> None:
        self.ordner = ordner
        self.laden()

    DATEIEN = {"bauplan": "bauplan.json", "zubehoer": "zubehoer.json", "outfits": "outfits.json",
               "verhalten": "verhalten.json"}
    LEER = {"bauplan": {}, "zubehoer": {}, "outfits": {"aktiv": None, "outfits": {}},
            "verhalten": {"werte": {}, "regeln": []}}

    def laden(self) -> None:
        self._basis: dict[str, dict] = {}
        self._geschrieben: dict[str, str] = {}
        for attr in self.DATEIEN:
            wert = self._platte(attr)
            setattr(self, attr, wert)
            self._basis[attr] = copy.deepcopy(wert)
        self.vorschau_laden()

    def _platte(self, attr: str) -> dict:
        pfad = self.ordner / self.DATEIEN[attr]
        if not pfad.exists():
            if attr == "verhalten":                 # ohne eigene Datei gilt das Standard-Verhalten
                std = standard_verhalten()
                std.pop("beschreibung", None)
                return std
            return copy.deepcopy(self.LEER[attr])
        return json.loads(pfad.read_text(encoding="utf-8"))

    def _speichern(self, attr: str) -> None:
        """Sicher speichern: alte Fassung in den Verlauf, fremde Änderungen zusammenführen,
        atomar schreiben. So geht nie etwas verloren – auch nicht bei zwei Editoren."""
        pfad = self.ordner / self.DATEIEN[attr]
        platte = self._platte(attr)
        mein = getattr(self, attr)
        neu = mein if platte == self._basis.get(attr) else drei_wege(self._basis.get(attr, {}), mein, platte)
        text = json.dumps(neu, indent=2, ensure_ascii=False) + "\n"
        if pfad.exists():
            alt_text = pfad.read_text(encoding="utf-8")
            if alt_text == text:
                self._basis[attr] = copy.deepcopy(neu)
                setattr(self, attr, neu)
                return
            verlauf = self.ordner / "_alt" / "verlauf"
            verlauf.mkdir(parents=True, exist_ok=True)
            (verlauf / f"{pfad.stem}_{time.strftime('%Y%m%d_%H%M%S')}_{int(time.time() * 1000) % 1000:03d}.json"
             ).write_text(alt_text, encoding="utf-8")
            alle = sorted(verlauf.glob(f"{pfad.stem}_*.json"))
            for weg in alle[:-VERLAUF_MAX]:
                weg.unlink(missing_ok=True)
        tmp = pfad.with_suffix(".json.tmp")
        tmp.write_text(text, encoding="utf-8")
        ersetzen(tmp, pfad, text)
        self._geschrieben[attr] = text
        self._basis[attr] = copy.deepcopy(neu)
        setattr(self, attr, neu)

    def von_aussen_geaendert(self, attr: str) -> bool:
        """Datei wurde extern geändert? Dann übernehmen (meine Änderungen sind immer
        schon gespeichert). Liefert True, wenn sich etwas geändert hat."""
        pfad = self.ordner / self.DATEIEN[attr]
        if not pfad.exists():
            return False
        text = pfad.read_text(encoding="utf-8")
        if text == self._geschrieben.get(attr):
            return False
        platte = json.loads(text)
        if platte == getattr(self, attr):
            return False
        neu = drei_wege(self._basis.get(attr, {}), getattr(self, attr), platte)
        setattr(self, attr, neu)
        self._basis[attr] = copy.deepcopy(platte)
        if neu != platte:
            self._speichern(attr)
        return True

    def vorschau_laden(self) -> None:
        p = VORSCHAU / self.id / "posen.json"
        self.vorschau = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {"posen": {}}

    @property
    def id(self) -> str:
        return self.bauplan["id"]

    def bauplan_speichern(self) -> None:
        self._speichern("bauplan")

    def outfits_speichern(self) -> None:
        self._speichern("outfits")

    def zubehoer_speichern(self) -> None:
        self._speichern("zubehoer")

    def verhalten_speichern(self) -> None:
        self._speichern("verhalten")

    # Posen
    def posen(self) -> list[str]:
        """Alle Posen-Schlüssel "quelle:nr" in Bauplan-Reihenfolge."""
        return [f"{q}:{i}" for q, d in self.bauplan["quellen"].items() for i in range(d.get("bilder", 1))]

    def benutzt(self, schluessel: str) -> list[str]:
        q, nr = schluessel.split(":")
        anims = []
        for name, a in self.bauplan["animationen"].items():
            n = sum(1 for e in a["bilder"] if e[0] == q and e[1] == int(nr))
            if n:
                anims.append(f"{name} ({n}×)" if n > 1 else name)
        return anims

    def vorschau_bild(self, schluessel: str) -> Path | None:
        v = self.vorschau["posen"].get(schluessel)
        return VORSCHAU / self.id / v["bild"] if v else None

    def quell_datei(self, schluessel: str) -> Path:
        q = schluessel.split(":")[0]
        return self.ordner / self.bauplan["quellen"][q]["datei"]

    def _sichern(self, datei: Path) -> None:
        if datei.exists():
            alt = self.ordner / "_alt"
            alt.mkdir(exist_ok=True)
            shutil.copy2(datei, alt / f"{datei.stem}_{time.strftime('%Y%m%d_%H%M%S')}{datei.suffix}")

    def ersetzen(self, schluessel: str, neu: Path) -> str:
        """Ersetzt eine Pose durch ein neues Bild. Bei Bildbögen (mehrere Posen in
        einer Datei) wird die Pose herausgelöst und bekommt eine eigene Datei."""
        from PIL import Image

        q, nr = schluessel.split(":")
        nr = int(nr)
        quelle = self.bauplan["quellen"][q]
        hg = hintergrund_erkennen(neu)
        if quelle.get("bilder", 1) == 1:
            ziel = self.ordner / Path(quelle["datei"]).with_suffix(".png").name
            self._sichern(self.ordner / quelle["datei"])
            Image.open(neu).save(ziel)
            quelle["datei"] = ziel.name
            for k in ("toleranz", "teile", "form"):     # Rig (SVG-Teile) gilt fürs neue Bild nicht
                quelle.pop(k, None)
            if hg:
                quelle["hintergrund"] = hg
            else:
                quelle.pop("hintergrund", None)
            self.bauplan_speichern()
            return schluessel
        # aus dem Bogen herauslösen
        name = f"{q}_{nr + 1}"
        while name in self.bauplan["quellen"]:
            name += "_neu"
        Image.open(neu).save(self.ordner / f"{name}.png")
        neue_quelle = {"datei": f"{name}.png", "bilder": 1}
        for k in ("massstab", "faktor"):
            if k in quelle:
                neue_quelle[k] = quelle[k]
        if hg:
            neue_quelle["hintergrund"] = hg
        self.bauplan["quellen"][name] = neue_quelle
        self.umbenennen(schluessel, f"{name}:0")
        return f"{name}:0"

    def umbenennen(self, alt: str, neu: str) -> None:
        """Alle Verweise auf eine Pose umhängen (Animationen, Referenz, Zubehör)."""
        aq, an = alt.split(":")
        nq, nn = neu.split(":")
        for a in self.bauplan["animationen"].values():
            for e in a["bilder"]:
                if e[0] == aq and e[1] == int(an):
                    e[0], e[1] = nq, int(nn)
        if self.bauplan.get("referenz") == [aq, int(an)]:
            self.bauplan["referenz"] = [nq, int(nn)]
        for z in self.zubehoer.values():
            if alt in z.get("posen", {}):
                z["posen"][neu] = z["posen"].pop(alt)
        self.bauplan_speichern()
        self.zubehoer_speichern()

    def hinzufuegen(self, datei: Path, name: str) -> str:
        from PIL import Image

        name = "".join(c for c in name.lower() if c.isalnum() or c == "_") or "bild"
        while name in self.bauplan["quellen"]:
            name += "_2"
        Image.open(datei).save(self.ordner / f"{name}.png")
        q = {"datei": f"{name}.png", "bilder": 1}
        hg = hintergrund_erkennen(datei)
        if hg:
            q["hintergrund"] = hg
        self.bauplan["quellen"][name] = q
        self.bauplan_speichern()
        return f"{name}:0"

    # Zubehör
    def platzierung(self, teil: str, schluessel: str) -> dict:
        std = self.vorschau["posen"].get(schluessel, {}).get("zubehoer_standard", {}).get(teil)
        p = dict(std or {"x": 0, "y": -100, "breite": 60, "winkel": 0, "hinten": False, "aus": False})
        p.update(self.zubehoer.get(teil, {}).get("posen", {}).get(schluessel, {}))
        return p

    def standard(self, teil: str, schluessel: str) -> dict | None:
        return self.vorschau["posen"].get(schluessel, {}).get("zubehoer_standard", {}).get(teil)

    @property
    def rahmen(self) -> bool:
        """Avatar ohne Auge (Rahmen-Ausrichtung, z. B. Hüpfer): keine Augen-Effekte."""
        return self.bauplan.get("ausrichtung") == "rahmen"

    def innen_varianten(self) -> list[str]:
        return sorted({v for z in self.zubehoer.values() if z.get("sitz") == "innen"
                       for v in z.get("varianten", {})})

    def zubehoer_bild(self, teil: str) -> Path | None:
        z = self.vorschau.get("zubehoer", {}).get(teil)
        if z and Path(z["bild"]).exists():
            return Path(z["bild"])
        quelle = self.zubehoer.get(teil, {}).get("datei")
        return (self.ordner / quelle).resolve() if quelle else None


# --- Bilder-Tab ------------------------------------------------------------------

class PoseKarte(QFrame):
    def __init__(self, editor: "Editor", schluessel: str) -> None:
        super().__init__()
        self.editor, self.schluessel = editor, schluessel
        pr = editor.projekt
        self.setObjectName("karte")
        self.setFixedWidth(272)
        lay = QVBoxLayout(self)
        lay.setSpacing(6)
        bild = QLabel()
        bild.setFixedSize(226, 210)
        bild.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bild.setStyleSheet("background: #E9ECE8; border-radius: 10px;")
        pfad = pr.vorschau_bild(schluessel)
        if pfad and pfad.exists():
            bild.setPixmap(frisch(pfad).scaled(216, 200, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))
        else:
            bild.setText("noch nicht gebaut")
        lay.addWidget(bild)
        titel = QLabel(pose_name(schluessel))
        titel.setStyleSheet("font-weight: 800; font-size: 15px;")
        lay.addWidget(titel)
        q = schluessel.split(":")[0]
        quelle = pr.bauplan["quellen"][q]
        datei = QLabel(f"Datei: {quelle['datei']}" + (f"  (Bogen mit {quelle['bilder']})"
                                                       if quelle.get("bilder", 1) > 1 else ""))
        datei.setObjectName("neben")
        datei.setWordWrap(True)
        lay.addWidget(datei)
        benutzt = pr.benutzt(schluessel)
        b = QLabel("Benutzt in: " + (", ".join(benutzt) if benutzt else "– (nicht benutzt)"))
        b.setWordWrap(True)
        b.setStyleSheet(f"color: {stil.AKZENT if benutzt else '#9AA39E'};")
        lay.addWidget(b)
        knoepfe = QHBoxLayout()
        for text, f in (("Öffnen", self._oeffnen), ("Bearbeiten", self._bearbeiten), ("Ersetzen", self._ersetzen)):
            k = QPushButton(text)
            k.setStyleSheet("min-height: 32px; padding: 0 6px;")
            k.clicked.connect(f)
            knoepfe.addWidget(k)
        lay.addLayout(knoepfe)
        groesse = QHBoxLayout()
        groesse.addWidget(QLabel("Größe"))
        spin = QDoubleSpinBox()
        spin.setRange(0.5, 1.6)
        spin.setSingleStep(0.02)
        spin.setValue(float(quelle.get("faktor", 1.0)))
        spin.setToolTip("Feinjustierung der Größe dieser Bilddatei (1,00 = automatisch)")
        spin.valueChanged.connect(self._faktor)
        groesse.addWidget(spin)
        groesse.addStretch(1)
        lay.addLayout(groesse)

    def _oeffnen(self) -> None:
        oeffnen(self.editor.projekt.quell_datei(self.schluessel))

    def _bearbeiten(self) -> None:
        oeffnen(self.editor.projekt.quell_datei(self.schluessel), bearbeiten=True)
        self.editor.meldung("Nach dem Speichern im Bildprogramm baut der Editor automatisch neu.")

    def _ersetzen(self) -> None:
        datei, _ = QFileDialog.getOpenFileName(self, f"Neues Bild für {pose_name(self.schluessel)}",
                                               str(Path.home() / "Downloads"), "Bilder (*.png *.jpg *.jpeg *.webp)")
        if not datei:
            return
        neu = self.editor.projekt.ersetzen(self.schluessel, Path(datei))
        self.editor.meldung(f"{pose_name(self.schluessel)} ersetzt → {pose_name(neu)}. Das alte Bild liegt in _alt/.")
        self.editor.geaendert(neu_aufbauen=True)

    def _faktor(self, wert: float) -> None:
        q = self.schluessel.split(":")[0]
        quelle = self.editor.projekt.bauplan["quellen"][q]
        if abs(wert - 1.0) < 1e-6:
            quelle.pop("faktor", None)
        else:
            quelle["faktor"] = round(wert, 3)
        self.editor.projekt.bauplan_speichern()
        self.editor.geaendert()


class BilderTab(QWidget):
    def __init__(self, editor: "Editor") -> None:
        super().__init__()
        self.editor = editor
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        info = QLabel("Jedes Bild des Avatars. Klick auf „Bearbeiten“ öffnet die Quelldatei in deinem "
                      "Bildprogramm – speichern genügt, der Editor baut dann neu.")
        info.setWordWrap(True)
        kopf.addWidget(info, 1)
        neu = QPushButton("Neues Bild hinzufügen …")
        neu.clicked.connect(self._neu)
        kopf.addWidget(neu)
        lay.addLayout(kopf)
        self.bereich = QScrollArea()
        self.bereich.setWidgetResizable(True)
        lay.addWidget(self.bereich)

    def aufbauen(self) -> None:
        innen = QWidget()
        gitter = QGridLayout(innen)
        gitter.setSpacing(14)
        spalten = max(1, (self.bereich.viewport().width() - 20) // 286)
        posen = self.editor.projekt.posen()
        posen.sort(key=lambda s: (not self.editor.projekt.benutzt(s), self.editor.projekt.posen().index(s)))
        for i, s in enumerate(posen):
            gitter.addWidget(PoseKarte(self.editor, s), i // spalten, i % spalten, Qt.AlignmentFlag.AlignTop)
        gitter.setRowStretch(len(posen) // spalten + 1, 1)
        gitter.setColumnStretch(spalten, 1)
        self.bereich.setWidget(innen)

    def resizeEvent(self, e) -> None:  # noqa: N802
        super().resizeEvent(e)
        if not hasattr(self, "_neu_timer"):
            self._neu_timer = QTimer(self)
            self._neu_timer.setSingleShot(True)
            self._neu_timer.timeout.connect(self.aufbauen)
        self._neu_timer.start(150)

    def _neu(self) -> None:
        datei, _ = QFileDialog.getOpenFileName(self, "Neues Bild", str(Path.home() / "Downloads"),
                                               "Bilder (*.png *.jpg *.jpeg *.webp)")
        if not datei:
            return
        name, ok = QInputDialog.getText(self, "Name", "Kurzer Name für das Bild (z. B. winken):",
                                        text=Path(datei).stem[:20])
        if not ok:
            return
        s = self.editor.projekt.hinzufuegen(Path(datei), name)
        self.editor.meldung(f"{pose_name(s)} hinzugefügt. Unter „Animationen“ einer Bewegung zuordnen.")
        self.editor.geaendert(neu_aufbauen=True)


# --- Animationen-Tab -------------------------------------------------------------

class FrameKarte(QFrame):
    def __init__(self, tab: "AnimationenTab", index: int, eintrag: list) -> None:
        super().__init__()
        self.tab, self.index = tab, index
        pr = tab.editor.projekt
        self.setObjectName("karte")
        self.setFixedWidth(170)
        lay = QVBoxLayout(self)
        lay.setSpacing(4)
        lay.addWidget(QLabel(f"Bild {index + 1}"))
        bild = QLabel()
        bild.setFixedSize(150, 140)
        bild.setAlignment(Qt.AlignmentFlag.AlignCenter)
        bild.setStyleSheet("background: #E9ECE8; border-radius: 8px;")
        pfad = pr.vorschau_bild(f"{eintrag[0]}:{eintrag[1]}")
        if pfad and pfad.exists():
            bild.setPixmap(frisch(pfad).scaled(140, 130, Qt.AspectRatioMode.KeepAspectRatio,
                                                     Qt.TransformationMode.SmoothTransformation))
        lay.addWidget(bild)
        self.pose = QComboBox()
        for s in pr.posen():
            self.pose.addItem(pose_name(s), s)
        self.pose.setCurrentIndex(max(0, self.pose.findData(f"{eintrag[0]}:{eintrag[1]}")))
        self.pose.currentIndexChanged.connect(self._aendern)
        lay.addWidget(self.pose)
        self.effekt = QComboBox()
        self.effekt.addItems(EFFEKTE)
        self.effekt.setCurrentText(eintrag[2])
        self.effekt.setToolTip("Augen-Effekt")
        self.effekt.currentIndexChanged.connect(self._aendern)
        lay.addWidget(self.effekt)
        self.hand = QComboBox()
        self.hand.addItems(["Hand normal", "Daumen runter"])
        self.hand.setCurrentIndex(1 if len(eintrag) > 3 and eintrag[3] == "daumen_runter" else 0)
        self.hand.currentIndexChanged.connect(self._aendern)
        lay.addWidget(self.hand)
        if pr.rahmen:                      # ohne Auge und Hand: nur die Pose zählt
            self.effekt.hide()
            self.hand.hide()
        knoepfe = QHBoxLayout()
        for text, f, tip in (("◀", lambda: tab.verschieben(index, -1), "nach vorne"),
                             ("▶", lambda: tab.verschieben(index, 1), "nach hinten"),
                             ("✕", lambda: tab.entfernen(index), "entfernen")):
            k = QPushButton(text)
            k.setObjectName("klein")
            k.setToolTip(tip)
            k.clicked.connect(f)
            knoepfe.addWidget(k)
        lay.addLayout(knoepfe)

    def _aendern(self) -> None:
        q, nr = self.pose.currentData().split(":")
        e = [q, int(nr), self.effekt.currentText()]
        if self.hand.currentIndex() == 1:
            e.append("daumen_runter")
        self.tab.setzen(self.index, e)


class AnimationenTab(QWidget):
    def __init__(self, editor: "Editor") -> None:
        super().__init__()
        self.editor = editor
        lay = QHBoxLayout(self)
        links = QVBoxLayout()
        self.liste = QListWidget()
        self.liste.setFixedWidth(220)
        self.liste.currentTextChanged.connect(lambda _: self.anzeigen())
        links.addWidget(self.liste)
        neu = QPushButton("Neue Animation …")
        neu.clicked.connect(self._neu)
        links.addWidget(neu)
        weg = QPushButton("Animation löschen")
        weg.clicked.connect(self._loeschen)
        links.addWidget(weg)
        hinweis = QLabel("Varianten: „sprechen~2“ wird zufällig statt „sprechen“ gezeigt.")
        hinweis.setObjectName("neben")
        hinweis.setWordWrap(True)
        links.addWidget(hinweis)
        lay.addLayout(links)

        rechts = QVBoxLayout()
        kopf = QHBoxLayout()
        self.titel = QLabel()
        self.titel.setStyleSheet("font-size: 18px; font-weight: 800;")
        kopf.addWidget(self.titel)
        kopf.addStretch(1)
        kopf.addWidget(QLabel("Bilder pro Sekunde"))
        self.fps = QDoubleSpinBox()
        self.fps.setRange(0.2, 30)
        self.fps.setSingleStep(0.5)
        self.fps.valueChanged.connect(self._fps)
        kopf.addWidget(self.fps)
        self.schleife = QCheckBox("Schleife")
        self.schleife.toggled.connect(self._schleife)
        kopf.addWidget(self.schleife)
        rechts.addLayout(kopf)
        self.frames = QScrollArea()
        self.frames.setWidgetResizable(True)
        self.frames.setFixedHeight(380)
        rechts.addWidget(self.frames)
        unten = QHBoxLayout()
        plus = QPushButton("+ Bild anhängen")
        plus.clicked.connect(self._plus)
        unten.addWidget(plus)
        unten.addStretch(1)
        rechts.addLayout(unten)
        rechts.addWidget(QLabel("Vorschau (zuletzt gebaut):"))
        self.vorschau = QLabel()
        self.vorschau.setFixedSize(300, 280)
        self.vorschau.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.vorschau.setStyleSheet("background: #2B3A44; border-radius: 12px;")
        rechts.addWidget(self.vorschau)
        rechts.addStretch(1)
        lay.addLayout(rechts, 1)
        self._bilder: list[QPixmap] = []
        self._i = 0
        self._uhr = QTimer(self)
        self._uhr.timeout.connect(self._weiter)
        self._laed = False

    @property
    def name(self) -> str | None:
        it = self.liste.currentItem()
        return it.text() if it else None

    def aufbauen(self) -> None:
        aktuell = self.name
        self.liste.blockSignals(True)
        self.liste.clear()
        for n in self.editor.projekt.bauplan["animationen"]:
            self.liste.addItem(n)
        treffer = self.liste.findItems(aktuell or "ruhe", Qt.MatchFlag.MatchExactly)
        self.liste.setCurrentItem(treffer[0] if treffer else self.liste.item(0))
        self.liste.blockSignals(False)
        self.anzeigen()

    def anzeigen(self) -> None:
        n = self.name
        if not n:
            return
        a = self.editor.projekt.bauplan["animationen"][n]
        self._laed = True
        self.titel.setText(n)
        self.fps.setValue(float(a["fps"]))
        self.schleife.setChecked(bool(a.get("schleife", True)))
        self._laed = False
        innen = QWidget()
        h = QHBoxLayout(innen)
        for i, e in enumerate(a["bilder"]):
            h.addWidget(FrameKarte(self, i, e))
        h.addStretch(1)
        self.frames.setWidget(innen)
        # Vorschau aus den gebauten Frames
        ordner = AVATARE / self.editor.projekt.id / "frames" / n
        self._bilder = [frisch(p).scaled(280, 260, Qt.AspectRatioMode.KeepAspectRatio,
                                                Qt.TransformationMode.SmoothTransformation)
                        for p in sorted(ordner.glob("*.png"))]
        self._i = 0
        self._uhr.start(max(30, int(1000 / max(0.2, float(a["fps"])))))
        self._weiter()

    def _weiter(self) -> None:
        if self._bilder:
            self.vorschau.setPixmap(self._bilder[self._i % len(self._bilder)])
            self._i += 1

    def _a(self) -> dict:
        return self.editor.projekt.bauplan["animationen"][self.name]

    def _speichern(self, neu_anzeigen: bool = True) -> None:
        self.editor.projekt.bauplan_speichern()
        self.editor.geaendert()
        if neu_anzeigen:
            QTimer.singleShot(0, self.anzeigen)

    def setzen(self, i: int, e: list) -> None:
        self._a()["bilder"][i] = e
        self._speichern()

    def verschieben(self, i: int, r: int) -> None:
        b = self._a()["bilder"]
        j = i + r
        if 0 <= j < len(b):
            b[i], b[j] = b[j], b[i]
            self._speichern()

    def entfernen(self, i: int) -> None:
        b = self._a()["bilder"]
        if len(b) <= 1:
            self.editor.meldung("Eine Animation braucht mindestens ein Bild.")
            return
        del b[i]
        self._speichern()

    def _plus(self) -> None:
        b = self._a()["bilder"]
        b.append(copy.deepcopy(b[-1]))
        self._speichern()

    def _fps(self, wert: float) -> None:
        if not self._laed and self.name:
            self._a()["fps"] = round(wert, 2)
            self._speichern(neu_anzeigen=False)
            self._uhr.setInterval(max(30, int(1000 / wert)))

    def _schleife(self, an: bool) -> None:
        if not self._laed and self.name:
            if an:
                self._a().pop("schleife", None)
            else:
                self._a()["schleife"] = False
            self._speichern(neu_anzeigen=False)

    def _neu(self) -> None:
        name, ok = QInputDialog.getText(self, "Neue Animation",
                                        "Name (z. B. winken, tanzen, ruelpsen, sprechen~3):")
        name = name.strip().lower()
        if not ok or not name:
            return
        anims = self.editor.projekt.bauplan["animationen"]
        if name in anims:
            self.editor.meldung(f"„{name}“ gibt es schon.")
            return
        anims[name] = {"fps": 2, "bilder": [copy.deepcopy(anims["ruhe"]["bilder"][0])]}
        self.editor.projekt.bauplan_speichern()
        self.editor.geaendert()
        self.aufbauen()
        self.liste.setCurrentItem(self.liste.findItems(name, Qt.MatchFlag.MatchExactly)[0])

    def _loeschen(self) -> None:
        n = self.name
        if not n or n == "ruhe":
            self.editor.meldung("„ruhe“ ist Pflicht und kann nicht gelöscht werden.")
            return
        if QMessageBox.question(self, "Löschen", f"Animation „{n}“ löschen?") != QMessageBox.StandardButton.Yes:
            return
        del self.editor.projekt.bauplan["animationen"][n]
        self.editor.projekt.bauplan_speichern()
        self.editor.geaendert()
        self.aufbauen()


# --- Zubehör-Tab ---------------------------------------------------------------

class PlatzierungsAnsicht(QWidget):
    """Pose groß, Zubehör darüber. Ziehen = verschieben, Mausrad = Größe,
    Umschalt+Mausrad = drehen."""

    geaendert = Signal(dict)

    RAND_OBEN = 60     # logische Pixel über der Leinwand (Hüte!)

    def __init__(self) -> None:
        super().__init__()
        self.setMinimumSize(420, 420)
        self.setMouseTracking(True)
        self.pose: QPixmap | None = None
        self.leinwand = (145.0, 132.0)
        self.anker = (72.5, 131.0)
        self.teil_bild: QPixmap | None = None
        self.p: dict | None = None
        self.andere: list[tuple[QPixmap, dict]] = []
        self.kopf: list[float] | None = None
        self._zieh: tuple[QPointF, dict] | None = None

    def setzen(self, pose: QPixmap | None, leinwand, anker, teil_bild, p, andere, kopf) -> None:
        self.pose, self.leinwand, self.anker = pose, leinwand, anker
        self.teil_bild, self.p, self.andere, self.kopf = teil_bild, p, andere, kopf
        self.update()

    def _massstab(self) -> tuple[float, QPointF]:
        lb, lh = self.leinwand
        lh += self.RAND_OBEN
        z = min(self.width() / lb, self.height() / lh) * 0.95
        ox = (self.width() - lb * z) / 2
        oy = (self.height() - lh * z) / 2 + self.RAND_OBEN * z
        return z, QPointF(ox, oy)

    def _ins_bild(self, x: float, y: float) -> QPointF:
        z, o = self._massstab()
        return QPointF(o.x() + (self.anker[0] + x) * z, o.y() + (self.anker[1] + y) * z)

    def paintEvent(self, _e) -> None:  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.fillRect(self.rect(), QColor("#2B3A44"))
        z, o = self._massstab()
        lb, lh = self.leinwand
        p.setPen(QPen(QColor(255, 255, 255, 40), 1, Qt.PenStyle.DashLine))
        p.drawRect(QRectF(o.x(), o.y(), lb * z, lh * z))
        fuss = self._ins_bild(0, 0)
        p.drawLine(QPointF(fuss.x() - 20, fuss.y()), QPointF(fuss.x() + 20, fuss.y()))
        hinten = [(b, d) for b, d in self.andere if d.get("hinten")]
        vorne = [(b, d) for b, d in self.andere if not d.get("hinten")]
        aktiv_hinten = self.p is not None and self.p.get("hinten")
        for b, d in hinten:
            self._teil(p, b, d, z, 0.85)
        if aktiv_hinten and self.teil_bild:
            self._teil(p, self.teil_bild, self.p, z, 1.0)
        if self.pose and not self.pose.isNull():
            p.drawPixmap(QRectF(o.x(), o.y(), lb * z, lh * z), self.pose, QRectF(self.pose.rect()))
        for b, d in vorne:
            self._teil(p, b, d, z, 0.85)
        if self.p is not None and not aktiv_hinten and self.teil_bild:
            self._teil(p, self.teil_bild, self.p, z, 1.0)
        if self.kopf:
            kx, _ky, kb, ko = self.kopf
            a = self._ins_bild(kx - kb / 2, ko)
            p.setPen(QPen(QColor(120, 220, 180, 120), 1, Qt.PenStyle.DotLine))
            p.drawLine(a, QPointF(a.x() + kb * z, a.y()))
        if self.p is not None:
            p.setPen(QColor(230, 235, 232))
            p.drawText(10, 20, f"x {self.p['x']:.1f}   y {self.p['y']:.1f}   Breite {self.p['breite']:.1f}   Höhe {self.p.get('hoehe', 100):.0f} %"
                               f"   Drehung {self.p.get('winkel', 0):.0f}°"
                               + ("   (hinter dem Körper)" if self.p.get("hinten") else "")
                               + ("   AUSGEBLENDET" if self.p.get("aus") else ""))
            p.drawText(10, self.height() - 12, "Ziehen = verschieben · Mausrad = Größe · Strg+Mausrad = nur Breite"
                                               " · Alt+Mausrad = nur Höhe · Umschalt+Mausrad = drehen")
        p.end()

    def _teil(self, p: QPainter, bild: QPixmap, d: dict, z: float, deckkraft: float) -> None:
        if d.get("aus"):
            deckkraft *= 0.25
        mitte = self._ins_bild(d["x"], d["y"])
        b = d["breite"] * z
        h = b * bild.height() / bild.width() * d.get("hoehe", 100) / 100
        p.save()
        p.setOpacity(deckkraft)
        p.translate(mitte)
        p.rotate(d.get("winkel", 0))
        p.drawPixmap(QRectF(-b / 2, -h / 2, b, h), bild, QRectF(bild.rect()))
        p.restore()

    def mousePressEvent(self, e) -> None:  # noqa: N802
        if self.p is not None and e.button() == Qt.MouseButton.LeftButton:
            self._zieh = (e.position(), dict(self.p))

    def mouseMoveEvent(self, e) -> None:  # noqa: N802
        if self._zieh is None:
            return
        start, alt = self._zieh
        z, _ = self._massstab()
        d = e.position() - start
        self.p = dict(alt, x=round(alt["x"] + d.x() / z, 1), y=round(alt["y"] + d.y() / z, 1))
        self.update()

    def mouseReleaseEvent(self, _e) -> None:  # noqa: N802
        if self._zieh is not None:
            self._zieh = None
            self.geaendert.emit(dict(self.p))

    def wheelEvent(self, e) -> None:  # noqa: N802
        if self.p is None:
            return
        stufen = (e.angleDelta().y() or e.angleDelta().x()) / 120
        mod = e.modifiers()
        if mod & Qt.KeyboardModifier.ShiftModifier:
            self.p["winkel"] = round(self.p.get("winkel", 0) + 3 * stufen, 1)
        elif mod & Qt.KeyboardModifier.ControlModifier:      # nur Breite (seitlich quetschen)
            alt = self.p["breite"]
            neu = max(3.0, alt * (1.04 ** stufen))
            self.p["breite"] = round(neu, 1)
            self.p["hoehe"] = round(self.p.get("hoehe", 100) * alt / neu, 1)   # Höhe bleibt gleich
        elif mod & Qt.KeyboardModifier.AltModifier:          # nur Höhe (oben quetschen)
            self.p["hoehe"] = round(max(10.0, self.p.get("hoehe", 100) * (1.04 ** stufen)), 1)
        else:
            self.p["breite"] = round(max(5.0, self.p["breite"] * (1.04 ** stufen)), 1)
        self.update()
        self.geaendert.emit(dict(self.p))


class ZubehoerTab(QWidget):
    def __init__(self, editor: "Editor") -> None:
        super().__init__()
        self.editor = editor
        self._laed = False
        lay = QHBoxLayout(self)
        split = QSplitter()
        lay.addWidget(split)

        # links: Zubehör-Liste + Eigenschaften
        links = QWidget()
        ll = QVBoxLayout(links)
        ll.addWidget(QLabel("Zubehör"))
        self.teile = QListWidget()
        self.teile.currentTextChanged.connect(lambda _: self.teil_anzeigen())
        ll.addWidget(self.teile)
        k = QHBoxLayout()
        neu = QPushButton("Neu …")
        neu.clicked.connect(self._neu)
        weg = QPushButton("Entfernen")
        weg.clicked.connect(self._entfernen)
        k.addWidget(neu)
        k.addWidget(weg)
        ll.addLayout(k)
        form = QFormLayout()
        self.sitz = QComboBox()
        self.sitz.addItem("über dem Kopf (wie Kopfhörer)", "ueber_kopf")
        self.sitz.addItem("auf dem Kopf (wie ein Hut)", "auf_kopf")
        self.sitz.addItem("am Auge (wie ein Monokel)", "am_auge")
        self.sitz.addItem("in der Hand (wie ein Stock)", "in_hand")
        self.sitz.addItem("im Körper (Innenleben, z. B. TNT)", "innen")
        self.sitz.currentIndexChanged.connect(self._eigenschaften)
        form.addRow("Standard-Sitz", self.sitz)
        self.gruppe = QLineEdit()
        self.gruppe.setToolTip("Von allem auf demselben Platz trägt er nur eins (z. B. „hut“, „auge“, „hand“)")
        self.gruppe.editingFinished.connect(self._eigenschaften)
        form.addRow("Platz", self.gruppe)
        self.immer = QCheckBox("trägt er immer (einzeln)")
        self.immer.setToolTip("Dauerhaft auf (z. B. sein Hut). Kopfhörer kommen automatisch bei Musik.")
        self.immer.toggled.connect(self._eigenschaften)
        form.addRow("", self.immer)
        ll.addLayout(form)
        kb = QHBoxLayout()
        bild_neu = QPushButton("Bild ersetzen …")
        bild_neu.clicked.connect(self._bild_ersetzen)
        bild_auf = QPushButton("Bild öffnen")
        bild_auf.clicked.connect(lambda: self._teil_datei() and oeffnen(self._teil_datei(), bearbeiten=True))
        kb.addWidget(bild_neu)
        kb.addWidget(bild_auf)
        ll.addLayout(kb)

        # Innenleben: Varianten je Stimmung (tnt@froh), eigener Versatz
        self.innen_box = QWidget()
        ib = QVBoxLayout(self.innen_box)
        ib.setContentsMargins(0, 6, 0, 0)
        ib.addWidget(QLabel("Varianten (Innenleben je Stimmung)"))
        self.varianten = QListWidget()
        self.varianten.setMaximumHeight(110)
        self.varianten.currentTextChanged.connect(lambda _: self.variante_anzeigen())
        ib.addWidget(self.varianten)
        vk = QHBoxLayout()
        v_neu = QPushButton("Variante …")
        v_neu.setToolTip("Bild für eine Stimmung, z. B. froh → tnt@froh")
        v_neu.clicked.connect(self._variante_neu)
        v_weg = QPushButton("Entfernen")
        v_weg.clicked.connect(self._variante_entfernen)
        vk.addWidget(v_neu)
        vk.addWidget(v_weg)
        ib.addLayout(vk)
        vv = QHBoxLayout()
        self.v_felder = {}
        for achse in ("x", "y"):
            vv.addWidget(QLabel(f"Versatz {achse}"))
            f = QDoubleSpinBox()
            f.setRange(-100, 100)
            f.setSingleStep(0.5)
            f.setDecimals(1)
            f.valueChanged.connect(self._variante_versatz)
            self.v_felder[achse] = f
            vv.addWidget(f)
        ib.addLayout(vv)
        hinweis = QLabel("Regeln wählen die Variante mit der Aktion „innen“. Fehlt sie, gilt die Grundvariante.")
        hinweis.setObjectName("neben")
        hinweis.setWordWrap(True)
        ib.addWidget(hinweis)
        ll.addWidget(self.innen_box)

        # Outfits: mehrere Teile gemeinsam an/aus
        trenner = QFrame()
        trenner.setFrameShape(QFrame.Shape.HLine)
        ll.addWidget(trenner)
        ll.addWidget(QLabel("Outfits (zusammen an- und ausziehen)"))
        oz = QHBoxLayout()
        self.outfit_wahl = QComboBox()
        self.outfit_wahl.currentIndexChanged.connect(lambda _: self.outfit_anzeigen())
        oz.addWidget(self.outfit_wahl, 1)
        o_neu = QPushButton("Neu …")
        o_neu.clicked.connect(self._outfit_neu)
        o_weg = QPushButton("Löschen")
        o_weg.clicked.connect(self._outfit_loeschen)
        oz.addWidget(o_neu)
        oz.addWidget(o_weg)
        ll.addLayout(oz)
        self.outfit_teile = QListWidget()
        self.outfit_teile.setMaximumHeight(120)
        self.outfit_teile.itemChanged.connect(self._outfit_teil)
        ll.addWidget(self.outfit_teile)
        self.outfit_an = QPushButton()
        self.outfit_an.setObjectName("haupt")
        self.outfit_an.clicked.connect(self._outfit_umschalten)
        ll.addWidget(self.outfit_an)
        split.addWidget(links)

        # Mitte: Posen
        mitte = QWidget()
        ml = QVBoxLayout(mitte)
        ml.addWidget(QLabel("Bilder (Posen)"))
        self.posen = QListWidget()
        self.posen.setIconSize(QSize(64, 64))
        self.posen.currentRowChanged.connect(lambda _: self.pose_anzeigen())
        ml.addWidget(self.posen)
        split.addWidget(mitte)

        # rechts: Ansicht + Werte
        rechts = QWidget()
        rl = QVBoxLayout(rechts)
        self.ansicht = PlatzierungsAnsicht()
        self.ansicht.geaendert.connect(self._platzierung)
        rl.addWidget(self.ansicht, 1)
        werte = QHBoxLayout()
        self.felder = {}
        for name, lo, hi, schritt in (("x", -200, 200, 0.5), ("y", -300, 50, 0.5), ("breite", 3, 300, 1),
                                      ("hoehe", 10, 400, 5), ("winkel", -180, 180, 1)):
            werte.addWidget(QLabel({"hoehe": "höhe %"}.get(name, name)))
            f = QDoubleSpinBox()
            f.setRange(lo, hi)
            f.setSingleStep(schritt)
            f.setDecimals(1)
            f.valueChanged.connect(self._feld)
            self.felder[name] = f
            werte.addWidget(f)
        rl.addLayout(werte)
        schalter = QHBoxLayout()
        self.hinten = QCheckBox("hinter dem Körper")
        self.hinten.toggled.connect(self._feld)
        self.aus = QCheckBox("bei diesem Bild ausblenden")
        self.aus.toggled.connect(self._feld)
        self.alle_zeigen = QCheckBox("anderes Zubehör mit anzeigen")
        self.alle_zeigen.toggled.connect(lambda _: self.pose_anzeigen())
        schalter.addWidget(self.hinten)
        schalter.addWidget(self.aus)
        schalter.addStretch(1)
        schalter.addWidget(self.alle_zeigen)
        rl.addLayout(schalter)
        aktionen = QHBoxLayout()
        for text, f, tip in (
                ("Standard (Kopf)", self._standard, "Eigene Einstellung dieses Bildes verwerfen"),
                ("Wie Bild davor", self._wie_davor, "Einstellung des vorherigen Bildes übernehmen"),
                ("Auf alle Bilder übertragen", self._auf_alle,
                 "Diese Einstellung relativ zum Kopf auf alle Bilder übertragen")):
            b = QPushButton(text)
            b.setToolTip(tip)
            b.clicked.connect(f)
            aktionen.addWidget(b)
        rl.addLayout(aktionen)
        split.addWidget(rechts)
        split.setSizes([260, 230, 700])

    # --- Anzeige ---------------------------------------------------------------
    @property
    def teil(self) -> str | None:
        it = self.teile.currentItem()
        return it.text() if it else None

    @property
    def schluessel(self) -> str | None:
        it = self.posen.currentItem()
        return it.data(Qt.ItemDataRole.UserRole) if it else None

    def aufbauen(self) -> None:
        pr = self.editor.projekt
        teil, pose = self.teil, self.schluessel
        self.teile.blockSignals(True)
        self.teile.clear()
        for t in pr.zubehoer:
            self.teile.addItem(t)
        treffer = self.teile.findItems(teil or "", Qt.MatchFlag.MatchExactly)
        self.teile.setCurrentItem(treffer[0] if treffer else self.teile.item(0))
        self.teile.blockSignals(False)
        self.outfits_aufbauen()
        self.posen.blockSignals(True)
        self.posen.clear()
        for s in sorted(pr.posen(), key=lambda k: not pr.benutzt(k)):
            benutzt = pr.benutzt(s)
            it = QListWidgetItem(pose_name(s) + ("" if benutzt else "  (nicht benutzt)"))
            it.setData(Qt.ItemDataRole.UserRole, s)
            pfad = pr.vorschau_bild(s)
            if pfad and pfad.exists():
                it.setIcon(QIcon(frisch(pfad)))
            if not benutzt:
                it.setForeground(QColor("#9AA39E"))
            self.posen.addItem(it)
        zeile = next((i for i in range(self.posen.count())
                      if self.posen.item(i).data(Qt.ItemDataRole.UserRole) == pose), 0)
        self.posen.setCurrentRow(zeile)
        self.posen.blockSignals(False)
        self.teil_anzeigen()

    def teil_anzeigen(self) -> None:
        t = self.teil
        z = self.editor.projekt.zubehoer.get(t, {}) if t else {}
        self._laed = True
        self.sitz.setCurrentIndex(max(0, self.sitz.findData(z.get("sitz", "ueber_kopf"))))
        self.gruppe.setText(z.get("gruppe", t or ""))
        self.immer.setChecked(bool(z.get("immer")))
        self._laed = False
        self._bild_cache: dict[str, QPixmap] = {}
        self.varianten_aufbauen()
        self.pose_anzeigen()

    # --- Innenleben-Varianten ------------------------------------------------------
    def varianten_aufbauen(self) -> None:
        z = self.editor.projekt.zubehoer.get(self.teil or "", {})
        innen = z.get("sitz") == "innen"
        self.innen_box.setVisible(innen)
        aktuell = self.varianten.currentItem().text() if self.varianten.currentItem() else None
        self.varianten.blockSignals(True)
        self.varianten.clear()
        for v in z.get("varianten", {}):
            self.varianten.addItem(v)
        treffer = self.varianten.findItems(aktuell or "", Qt.MatchFlag.MatchExactly)
        if treffer:
            self.varianten.setCurrentItem(treffer[0])
        elif self.varianten.count():
            self.varianten.setCurrentRow(0)
        self.varianten.blockSignals(False)
        self.variante_anzeigen()

    def _variante(self) -> dict | None:
        it = self.varianten.currentItem()
        z = self.editor.projekt.zubehoer.get(self.teil or "", {})
        return z.get("varianten", {}).get(it.text()) if it else None

    def variante_anzeigen(self) -> None:
        v = self._variante()
        self._laed = True
        for achse, f in self.v_felder.items():
            f.setEnabled(v is not None)
            f.setValue(float(v.get(achse, 0)) if v else 0.0)
        self._laed = False

    def _variante_versatz(self) -> None:
        v = self._variante()
        if self._laed or v is None:
            return
        for achse, f in self.v_felder.items():
            v[achse] = round(f.value(), 1)
        self.editor.projekt.zubehoer_speichern()
        self.editor.geaendert()

    def _variante_neu(self) -> None:
        from PIL import Image

        t = self.teil
        if not t:
            return
        name, ok = QInputDialog.getText(self, "Neue Variante", f"Stimmung (z. B. froh, erschreckt) – wird zu {t}@…:")
        name = "".join(c for c in name.strip().lower().lstrip("@") if c.isalnum() or c == "_")
        if not ok or not name:
            return
        datei, _ = QFileDialog.getOpenFileName(self, f"Bild für {t}@{name}", str(Path.home() / "Downloads"),
                                               "Bilder (*.png *.jpg *.jpeg *.webp)")
        if not datei:
            return
        pr = self.editor.projekt
        (pr.ordner / "zubehoer").mkdir(exist_ok=True)
        ziel = pr.ordner / "zubehoer" / f"{t}@{name}.png"
        if ziel.exists():
            pr._sichern(ziel)  # noqa: SLF001
        Image.open(datei).save(ziel)
        pr.zubehoer[t].setdefault("varianten", {})[name] = {"datei": f"zubehoer/{t}@{name}.png", "x": 0, "y": 0}
        pr.zubehoer_speichern()
        self.editor.geaendert(neu_aufbauen=True)
        self.editor.meldung(f"Variante {t}@{name} angelegt. In Regeln: Aktion „innen“, Variante „{name}“.")

    def _variante_entfernen(self) -> None:
        it = self.varianten.currentItem()
        t = self.teil
        if not it or not t or QMessageBox.question(self, "Entfernen", f"Variante „{t}@{it.text()}“ entfernen?") \
                != QMessageBox.StandardButton.Yes:
            return
        self.editor.projekt.zubehoer[t].get("varianten", {}).pop(it.text(), None)
        self.editor.projekt.zubehoer_speichern()
        self.editor.geaendert(neu_aufbauen=True)

    def _bild(self, teil: str) -> QPixmap | None:
        if teil not in self._bild_cache:
            pfad = self.editor.projekt.zubehoer_bild(teil)
            self._bild_cache[teil] = frisch(pfad) if pfad and pfad.exists() else QPixmap()
        pm = self._bild_cache[teil]
        return pm if not pm.isNull() else None

    def pose_anzeigen(self) -> None:
        pr, t, s = self.editor.projekt, self.teil, self.schluessel
        if not s:
            return
        v = pr.vorschau
        pfad = pr.vorschau_bild(s)
        pose = frisch(pfad) if pfad and pfad.exists() else None
        p = pr.platzierung(t, s) if t else None
        if p is not None and pr.zubehoer.get(t, {}).get("sitz") == "innen":
            p["hinten"] = True             # Innenleben liegt im Körper: hinter dem (durchsichtigen) Bild
        andere = []
        if self.alle_zeigen.isChecked():
            for anderes in pr.zubehoer:
                if anderes != t and self._bild(anderes):
                    andere.append((self._bild(anderes), pr.platzierung(anderes, s)))
        kopf = v["posen"].get(s, {}).get("kopf")
        self.ansicht.setzen(pose, tuple(v.get("leinwand", (145, 132))), tuple(v.get("anker", (72.5, 131))),
                            self._bild(t) if t else None, p, andere, kopf)
        self._felder_setzen(p)

    def _felder_setzen(self, p: dict | None) -> None:
        self._laed = True
        for name, f in self.felder.items():
            f.setEnabled(p is not None)
            if p is not None:
                f.setValue(float(p.get(name, 100 if name == "hoehe" else 0)))
        self.hinten.setChecked(bool(p and p.get("hinten")))
        self.aus.setChecked(bool(p and p.get("aus")))
        self._laed = False

    # --- Ändern ----------------------------------------------------------------
    def _speichern_pose(self, s: str, p: dict) -> None:
        z = self.editor.projekt.zubehoer[self.teil]
        z.setdefault("posen", {})[s] = {k: (round(float(v), 1) if isinstance(v, float) else v)
                                        for k, v in p.items()}
        self.editor.projekt.zubehoer_speichern()
        self.editor.geaendert()

    def _platzierung(self, p: dict) -> None:
        if self.teil and self.schluessel:
            self._speichern_pose(self.schluessel, p)
            self._felder_setzen(p)

    def _feld(self) -> None:
        if self._laed or not (self.teil and self.schluessel):
            return
        p = self.editor.projekt.platzierung(self.teil, self.schluessel)
        for name, f in self.felder.items():
            p[name] = f.value()
        p["hinten"] = self.hinten.isChecked()
        p["aus"] = self.aus.isChecked()
        self._speichern_pose(self.schluessel, p)
        self.pose_anzeigen()

    def _standard(self) -> None:
        if self.teil and self.schluessel:
            self.editor.projekt.zubehoer[self.teil].get("posen", {}).pop(self.schluessel, None)
            self.editor.projekt.zubehoer_speichern()
            self.editor.geaendert()
            self.pose_anzeigen()

    def _wie_davor(self) -> None:
        r = self.posen.currentRow()
        if r <= 0 or not self.teil:
            return
        davor = self.posen.item(r - 1).data(Qt.ItemDataRole.UserRole)
        self._speichern_pose(self.schluessel, self._relativ(davor, self.schluessel))
        self.pose_anzeigen()

    def _relativ(self, von: str, nach: str) -> dict:
        """Platzierung von Pose ``von`` relativ zu deren Kopf auf Pose ``nach`` umrechnen."""
        pr, t = self.editor.projekt, self.teil
        quelle = pr.platzierung(t, von)
        sv, sn = pr.standard(t, von), pr.standard(t, nach)
        if not sv or not sn:
            return dict(quelle)
        kv = pr.vorschau["posen"][von]["kopf"][2] or 1
        kn = pr.vorschau["posen"][nach]["kopf"][2] or 1
        f = kn / kv
        return {"x": sn["x"] + (quelle["x"] - sv["x"]) * f, "y": sn["y"] + (quelle["y"] - sv["y"]) * f,
                "breite": sn["breite"] * quelle["breite"] / sv["breite"], "winkel": quelle.get("winkel", 0),
                "hoehe": quelle.get("hoehe", 100),
                "hinten": quelle.get("hinten", False), "aus": False}

    def _auf_alle(self) -> None:
        if not (self.teil and self.schluessel):
            return
        if QMessageBox.question(self, "Übertragen", "Diese Einstellung relativ zum Kopf auf ALLE Bilder "
                                "übertragen? Eigene Einstellungen der anderen Bilder werden überschrieben.") \
                != QMessageBox.StandardButton.Yes:
            return
        z = self.editor.projekt.zubehoer[self.teil]
        for s in self.editor.projekt.posen():
            if s != self.schluessel:
                z.setdefault("posen", {})[s] = {k: (round(v, 1) if isinstance(v, float) else v)
                                                for k, v in self._relativ(self.schluessel, s).items()}
        self.editor.projekt.zubehoer_speichern()
        self.editor.geaendert()
        self.editor.meldung("Auf alle Bilder übertragen. Einzelne Bilder kannst du danach noch nachstellen.")

    def _eigenschaften(self) -> None:
        if self._laed or not self.teil:
            return
        z = self.editor.projekt.zubehoer[self.teil]
        z["sitz"] = self.sitz.currentData()
        z["gruppe"] = self.gruppe.text().strip() or self.teil
        z["immer"] = self.immer.isChecked() or z["sitz"] == "innen"     # Innenleben gehört zum Körper
        self.varianten_aufbauen()
        if z["immer"]:   # aus einer Gruppe nur eins
            for anderes, w in self.editor.projekt.zubehoer.items():
                if anderes != self.teil and w.get("gruppe", anderes) == z["gruppe"]:
                    w["immer"] = False
        self.editor.projekt.zubehoer_speichern()
        self.editor.geaendert()

    # --- Outfits -----------------------------------------------------------------
    def outfits_aufbauen(self) -> None:
        o = self.editor.projekt.outfits
        alt = self.outfit_wahl.currentText() or o.get("aktiv") or ""
        self.outfit_wahl.blockSignals(True)
        self.outfit_wahl.clear()
        for name in o.get("outfits", {}):
            self.outfit_wahl.addItem(name)
        i = self.outfit_wahl.findText(alt)
        self.outfit_wahl.setCurrentIndex(i if i >= 0 else 0)
        self.outfit_wahl.blockSignals(False)
        self.outfit_anzeigen()

    def outfit_anzeigen(self) -> None:
        o = self.editor.projekt.outfits
        name = self.outfit_wahl.currentText()
        teile = set(o.get("outfits", {}).get(name, []))
        self.outfit_teile.blockSignals(True)
        self.outfit_teile.clear()
        for t in self.editor.projekt.zubehoer:
            it = QListWidgetItem(t)
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if t in teile else Qt.CheckState.Unchecked)
            self.outfit_teile.addItem(it)
        self.outfit_teile.blockSignals(False)
        self.outfit_teile.setEnabled(bool(name))
        an = bool(name) and o.get("aktiv") == name
        self.outfit_an.setEnabled(bool(name))
        self.outfit_an.setText(f"„{name}“ ausziehen" if an else (f"„{name}“ anziehen" if name else "kein Outfit"))

    def _outfit_teil(self, it: QListWidgetItem) -> None:
        o = self.editor.projekt.outfits
        name = self.outfit_wahl.currentText()
        if not name:
            return
        teile = [self.outfit_teile.item(i).text() for i in range(self.outfit_teile.count())
                 if self.outfit_teile.item(i).checkState() == Qt.CheckState.Checked]
        o.setdefault("outfits", {})[name] = teile
        self.editor.projekt.outfits_speichern()
        self.editor.geaendert()

    def _outfit_umschalten(self) -> None:
        o = self.editor.projekt.outfits
        name = self.outfit_wahl.currentText()
        o["aktiv"] = None if o.get("aktiv") == name else name
        self.editor.projekt.outfits_speichern()
        self.editor.geaendert()
        self.outfit_anzeigen()
        self.editor.meldung(f"Outfit „{name}“ " + ("angezogen." if o["aktiv"] else "ausgezogen.")
                            + " Nach dem Bau „Kobold neu starten“.")

    def _outfit_neu(self) -> None:
        name, ok = QInputDialog.getText(self, "Neues Outfit", "Name (z. B. gentleman, pirat, winter):")
        name = "".join(c for c in name.strip().lower() if c.isalnum() or c in "_-")
        if not ok or not name:
            return
        o = self.editor.projekt.outfits
        o.setdefault("outfits", {}).setdefault(name, [])
        self.editor.projekt.outfits_speichern()
        self.outfits_aufbauen()
        self.outfit_wahl.setCurrentText(name)

    def _outfit_loeschen(self) -> None:
        name = self.outfit_wahl.currentText()
        o = self.editor.projekt.outfits
        if not name or QMessageBox.question(self, "Löschen", f"Outfit „{name}“ löschen?") \
                != QMessageBox.StandardButton.Yes:
            return
        o.get("outfits", {}).pop(name, None)
        if o.get("aktiv") == name:
            o["aktiv"] = None
        self.editor.projekt.outfits_speichern()
        self.editor.geaendert()
        self.outfits_aufbauen()

    def _teil_datei(self) -> Path | None:
        t = self.teil
        if not t:
            return None
        d = self.editor.projekt.zubehoer[t].get("datei")
        return (self.editor.projekt.ordner / d).resolve() if d else None

    def _neu(self) -> None:
        from PIL import Image

        datei, _ = QFileDialog.getOpenFileName(self, "Bild für neues Zubehör", str(Path.home() / "Downloads"),
                                               "Bilder (*.png *.jpg *.jpeg *.webp)")
        if not datei:
            return
        name, ok = QInputDialog.getText(self, "Name", "Name (z. B. cowboyhut, brille, krone):",
                                        text=Path(datei).stem[:20].lower())
        name = "".join(c for c in name.lower() if c.isalnum() or c == "_")
        if not ok or not name:
            return
        pr = self.editor.projekt
        if name in pr.zubehoer:
            self.editor.meldung(f"„{name}“ gibt es schon.")
            return
        (pr.ordner / "zubehoer").mkdir(exist_ok=True)
        ziel = pr.ordner / "zubehoer" / f"{name}.png"
        Image.open(datei).save(ziel)
        sitz, gruppe = "ueber_kopf", name
        if any(w in name for w in ("hut", "muetze", "mütze", "kappe", "krone", "helm")):
            sitz, gruppe = "auf_kopf", "hut"
        elif any(w in name for w in ("monokel", "brille", "lupe")):
            sitz, gruppe = "am_auge", "auge"
        elif any(w in name for w in ("stock", "schirm", "stab", "schwert", "zepter")):
            sitz, gruppe = "in_hand", "hand"
        eintrag = {"datei": f"zubehoer/{name}.png", "sitz": sitz, "gruppe": gruppe, "immer": False, "posen": {}}
        hg = hintergrund_erkennen(ziel)
        if hg:
            eintrag["hintergrund"] = hg
        pr.zubehoer[name] = eintrag
        pr.zubehoer_speichern()
        self.editor.geaendert(neu_aufbauen=True)
        self.editor.meldung(f"Zubehör „{name}“ angelegt. Nach dem Bau erscheint es mit Standard-Sitz.")

    def _bild_ersetzen(self) -> None:
        from PIL import Image

        t = self.teil
        if not t:
            return
        datei, _ = QFileDialog.getOpenFileName(self, f"Neues Bild für {t}", str(Path.home() / "Downloads"),
                                               "Bilder (*.png *.jpg *.jpeg *.webp)")
        if not datei:
            return
        pr = self.editor.projekt
        alt = self._teil_datei()
        if alt and alt.exists():
            pr._sichern(alt)  # noqa: SLF001
        (pr.ordner / "zubehoer").mkdir(exist_ok=True)
        ziel = pr.ordner / "zubehoer" / f"{t}.png"
        Image.open(datei).save(ziel)
        pr.zubehoer[t]["datei"] = f"zubehoer/{t}.png"
        hg = hintergrund_erkennen(ziel)
        if hg:
            pr.zubehoer[t]["hintergrund"] = hg
        else:
            pr.zubehoer[t].pop("hintergrund", None)
        pr.zubehoer_speichern()
        self.editor.geaendert(neu_aufbauen=True)

    def _entfernen(self) -> None:
        t = self.teil
        if not t or QMessageBox.question(self, "Entfernen", f"Zubehör „{t}“ entfernen?") \
                != QMessageBox.StandardButton.Yes:
            return
        del self.editor.projekt.zubehoer[t]
        self.editor.projekt.zubehoer_speichern()
        self.editor.geaendert(neu_aufbauen=True)


# --- Hauptfenster ------------------------------------------------------------------

class Editor(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("DMNT-Kobold · Avatar-Editor")
        self.resize(1400, 900)
        self.setStyleSheet(stil.bedien_stylesheet() + f"""
            QMainWindow, QTabWidget::pane {{ background: {stil.GRUND}; }}
            QFrame#karte {{ background: white; border: 1px solid {stil.LINIE}; border-radius: 14px; }}
            QListWidget {{ background: white; border: 1px solid {stil.LINIE}; border-radius: 10px; }}
            QListWidget::item:selected {{ background: {stil.AKZENT_HELL}; color: {stil.TEXT}; }}
            QTabBar::tab {{ padding: 10px 22px; font-weight: 600; }}
            QTabBar::tab:selected {{ color: {stil.AKZENT}; border-bottom: 2px solid {stil.AKZENT}; }}
            QComboBox, QDoubleSpinBox, QSpinBox {{ min-height: 30px; }}
            QPlainTextEdit {{ background: #1F2A30; color: #D6E2DC; border-radius: 8px;
                              font-family: Consolas, monospace; font-size: 12px; }}
        """)
        self.avatare = sorted(p for p in QUELLEN.iterdir() if (p / "bauplan.json").exists())
        if not self.avatare:
            raise SystemExit("Keine Avatar-Quellen gefunden (quellen/<id>/bauplan.json)")
        self.projekt = Projekt(self.avatare[0])

        leiste = QToolBar()
        leiste.setMovable(False)
        self.addToolBar(leiste)
        self.wahl = QComboBox()
        for p in self.avatare:
            self.wahl.addItem(p.name, p)
        self.wahl.currentIndexChanged.connect(self._avatar_wechseln)
        leiste.addWidget(QLabel("  Avatar: "))
        leiste.addWidget(self.wahl)
        leiste.addSeparator()
        bauen = QAction("Neu bauen", self)
        bauen.triggered.connect(self.bauen)
        leiste.addAction(bauen)
        neustart = QAction("Kobold neu starten", self)
        neustart.triggered.connect(self.kobold_neu_starten)
        leiste.addAction(neustart)
        ordner = QAction("Quellordner öffnen", self)
        ordner.triggered.connect(lambda: oeffnen(self.projekt.ordner))
        leiste.addAction(ordner)
        leiste.addSeparator()
        self.auto = QCheckBox("automatisch bauen")
        self.auto.setChecked(True)
        leiste.addWidget(self.auto)
        self.status = QLabel()
        self.status.setStyleSheet("padding-left: 16px; font-weight: 600;")
        leiste.addWidget(self.status)

        self.tabs = QTabWidget()
        self.bilder = BilderTab(self)
        self.animationen = AnimationenTab(self)
        self.zubehoer = ZubehoerTab(self)
        self.verhalten = VerhaltenTab(self)
        self.herkunft = HerkunftToeneTab(self)
        self.tabs.addTab(self.bilder, "Bilder")
        self.tabs.addTab(self.animationen, "Animationen")
        self.tabs.addTab(self.zubehoer, "Zubehör")
        self.tabs.addTab(self.verhalten, "Verhalten")
        self.tabs.addTab(self.herkunft, "Herkunft && Töne")
        mitte = QWidget()
        ml = QVBoxLayout(mitte)
        ml.addWidget(self.tabs, 1)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setFixedHeight(110)
        ml.addWidget(self.log)
        self.setCentralWidget(mitte)

        self._prozess: QProcess | None = None
        self._nochmal = False
        self._nach_bau_aufbauen = False
        self._neustart_nach_bau = False
        self._puffer: list[str] = []
        self._bau_timer = QTimer(self)
        self._bau_timer.setSingleShot(True)
        self._bau_timer.timeout.connect(self.bauen)
        self._waechter = QFileSystemWatcher(self)
        self._waechter.fileChanged.connect(self._datei_geaendert)
        self._eigene_aenderung = 0.0

        self.alles_aufbauen()
        if not self.projekt.vorschau["posen"]:
            self.bauen()
        else:
            self._status("gebaut", True)

    # --- Ablauf ------------------------------------------------------------------
    def alles_aufbauen(self) -> None:
        self.projekt.vorschau_laden()
        self.bilder.aufbauen()
        self.animationen.aufbauen()
        self.zubehoer.aufbauen()
        self.verhalten.aufbauen()
        self.herkunft.aufbauen()
        self._beobachten()

    def _beobachten(self) -> None:
        if self._waechter.files():
            self._waechter.removePaths(self._waechter.files())
        dateien = {str(self.projekt.ordner / q["datei"]) for q in self.projekt.bauplan["quellen"].values()}
        dateien |= {str((self.projekt.ordner / z["datei"]).resolve()) for z in self.projekt.zubehoer.values()
                    if z.get("datei")}
        dateien |= {str((self.projekt.ordner / v["datei"]).resolve()) for z in self.projekt.zubehoer.values()
                    for v in z.get("varianten", {}).values() if v.get("datei")}
        dateien |= {str(self.projekt.ordner / d) for d in Projekt.DATEIEN.values()}
        self._waechter.addPaths([d for d in dateien if Path(d).exists()])

    def _datei_geaendert(self, pfad: str) -> None:
        QTimer.singleShot(300, self._beobachten)      # manche Programme ersetzen die Datei
        name = Path(pfad).name
        attr = next((a for a, d in Projekt.DATEIEN.items() if d == name), None)
        if attr is not None:
            QTimer.singleShot(250, lambda: self._json_von_aussen(attr))
            return
        self.meldung(f"Geändert: {name}")
        self.geaendert()

    def _json_von_aussen(self, attr: str) -> None:
        try:
            geaendert = self.projekt.von_aussen_geaendert(attr)
        except (OSError, ValueError):
            return                                   # Datei wird gerade geschrieben – nächstes Signal abwarten
        if geaendert:
            self.meldung(f"{Projekt.DATEIEN[attr]} wurde außerhalb geändert – übernommen.")
            self.bilder.aufbauen()
            self.animationen.aufbauen()
            self.zubehoer.aufbauen()
            self.verhalten.aufbauen()
            self.herkunft.aufbauen()
            self.geaendert()

    def _avatar_wechseln(self) -> None:
        if self.verhalten._timer.isActive():        # noqa: SLF001 – noch nicht gespeicherte Änderung
            self.verhalten.speichern_jetzt()
        self.projekt = Projekt(self.wahl.currentData())
        self.alles_aufbauen()

    def meldung(self, text: str) -> None:
        self.log.appendPlainText(f"{time.strftime('%H:%M:%S')}  {text}")
        self.statusBar().showMessage(text, 8000)

    def _status(self, text: str, ok: bool) -> None:
        self.status.setText(text)
        self.status.setStyleSheet(f"padding-left: 16px; font-weight: 600; color: {stil.AKZENT if ok else '#A0671A'};")

    def geaendert(self, neu_aufbauen: bool = False) -> None:
        self._status("Änderungen noch nicht gebaut", False)
        self._nach_bau_aufbauen = self._nach_bau_aufbauen or neu_aufbauen
        if self.auto.isChecked():
            self._bau_timer.start(BAU_PAUSE_MS)

    def bauen(self) -> None:
        if self._prozess is not None:
            self._nochmal = True
            return
        self._status("baut …", False)
        self._puffer = []
        self.meldung("Baue Avatar …")
        p = QProcess(self)
        p.setWorkingDirectory(str(WURZEL))
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        umgebung = p.processEnvironment()
        umgebung.insert("PYTHONIOENCODING", "utf-8")
        p.setProcessEnvironment(umgebung)
        p.readyReadStandardOutput.connect(lambda: self._ausgabe(p))
        p.finished.connect(lambda code, _s: self._fertig(code))
        python = Path(sys.executable)
        if python.name.lower() == "pythonw.exe":
            python = python.with_name("python.exe")
        p.start(str(python), [str(WURZEL / "werkzeuge" / "avatar_bauen.py"), str(self.projekt.ordner)])
        self._prozess = p

    def _ausgabe(self, p: QProcess) -> None:
        text = bytes(p.readAllStandardOutput()).decode("utf-8", "replace").strip()
        self._puffer += text.splitlines()
        for zeile in text.splitlines():
            if "Fehler" in zeile or "Error" in zeile or "Traceback" in zeile or "Fertig" in zeile \
                    or zeile.startswith(("  Zubehör", "SystemExit")) or "raise" in zeile:
                self.log.appendPlainText(zeile)

    def _fertig(self, code: int) -> None:
        self._prozess = None
        if code == 0:
            self._status("gebaut ✓ – „Kobold neu starten“ zum Ansehen", True)
            self.meldung("Bau fertig.")
            self.projekt.vorschau_laden()
            if self._nach_bau_aufbauen:
                self._nach_bau_aufbauen = False
                self.alles_aufbauen()
            else:
                self.bilder.aufbauen()
                self.animationen.anzeigen()
                self.zubehoer.aufbauen()
                self.verhalten.pruefen()
        else:
            self._status("Bau fehlgeschlagen – siehe Protokoll", False)
            self.log.appendPlainText("\n".join(self._puffer[-15:]))
            self.meldung("Bau fehlgeschlagen.")
        if self._nochmal:
            self._nochmal = False
            self.bauen()
        if self._neustart_nach_bau and self._prozess is None:
            self._neustart_nach_bau = False
            if code == 0:
                self.kobold_neu_starten()

    def closeEvent(self, e) -> None:  # noqa: N802
        if self.verhalten._timer.isActive():        # noqa: SLF001 – noch nicht gespeicherte Änderung
            self.verhalten.speichern_jetzt()
        super().closeEvent(e)

    def kobold_neu_starten(self) -> None:
        if self.verhalten._timer.isActive():        # noqa: SLF001
            self.verhalten.speichern_jetzt()
        if self._bau_timer.isActive() or self._prozess is not None:   # erst fertig bauen
            self._neustart_nach_bau = True
            if self._bau_timer.isActive():
                self._bau_timer.stop()
                self.bauen()
            self.meldung("Kobold startet neu, sobald der Bau fertig ist.")
            return
        if sys.platform != "win32":
            self.meldung("Neustart geht nur unter Windows.")
            return
        befehl = (
            "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
            "Where-Object { $_.CommandLine -like '*-m dmnt_kobold*' } | "
            "ForEach-Object { Stop-Process -Id $_.ProcessId -Force }; Start-Sleep -Milliseconds 800; "
            f"Start-Process '{WURZEL / '.venv' / 'Scripts' / 'pythonw.exe'}' -ArgumentList '-m','dmnt_kobold' "
            f"-WorkingDirectory '{WURZEL}'")
        subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", befehl],
                         creationflags=0x08000000)
        self.meldung("Kobold wird neu gestartet.")


def helles_design(app: QApplication) -> None:
    """Immer hell – auch wenn Windows auf dunkel steht (sonst mischen sich die Farben)."""
    from PySide6.QtGui import QPalette

    app.setStyle("Fusion")
    pal = QPalette()
    farben = {
        QPalette.ColorRole.Window: stil.GRUND, QPalette.ColorRole.WindowText: stil.TEXT,
        QPalette.ColorRole.Base: "#FFFFFF", QPalette.ColorRole.AlternateBase: "#F6F7F5",
        QPalette.ColorRole.Text: stil.TEXT, QPalette.ColorRole.Button: "#FFFFFF",
        QPalette.ColorRole.ButtonText: stil.TEXT, QPalette.ColorRole.Highlight: stil.AKZENT,
        QPalette.ColorRole.HighlightedText: "#FFFFFF", QPalette.ColorRole.ToolTipBase: "#FFFFFF",
        QPalette.ColorRole.ToolTipText: stil.TEXT, QPalette.ColorRole.PlaceholderText: "#8A938E",
    }
    for rolle, farbe in farben.items():
        pal.setColor(rolle, QColor(farbe))
    app.setPalette(pal)
    try:
        app.styleHints().setColorScheme(Qt.ColorScheme.Light)
    except AttributeError:
        pass


class KeinMausrad(QObject):
    """Mausrad verstellt keine Auswahllisten, Zahlenfelder und Regler – sonst ändert man beim
    Scrollen durch die Seite aus Versehen Werte. Das Rad scrollt stattdessen die Seite;
    verstellen geht nur per Klick oder Tippen."""

    def eventFilter(self, obj, event):  # noqa: N802 (Qt-API)
        if event.type() == QEvent.Type.Wheel and isinstance(obj, (QComboBox, QAbstractSpinBox, QSlider)):
            w = obj.parentWidget()
            while w is not None and not isinstance(w, QAbstractScrollArea):
                w = w.parentWidget()
            if w is not None:
                QApplication.sendEvent(w.viewport(), event)
            return True
        return super().eventFilter(obj, event)


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DMNT Avatar-Editor")
    helles_design(app)
    kein_mausrad = KeinMausrad(app)
    app.installEventFilter(kein_mausrad)
    from PySide6.QtCore import QLockFile

    (WURZEL / "build").mkdir(exist_ok=True)
    sperre = QLockFile(str(WURZEL / "build" / "avatar_editor.lock"))
    sperre.setStaleLockTime(0)
    if not sperre.tryLock(100):                 # zwei Editoren würden sich gegenseitig überschreiben
        QMessageBox.information(None, "Avatar-Editor", "Der Avatar-Editor ist schon offen.")
        return 0
    e = Editor()
    if "--tab" in sys.argv:              # z. B. --tab 2 öffnet „Zubehör“, --tab 3 „Verhalten“
        e.tabs.setCurrentIndex(int(sys.argv[sys.argv.index("--tab") + 1]))
    e.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
