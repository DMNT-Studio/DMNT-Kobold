"""Reiter „Verhalten“ im Avatar-Editor: Werte, Regeln, Können.

Grundlage ist ``quellen/<id>/verhalten.json``, geprüft gegen den Katalog des Sockels
(``src/dmnt_kobold/katalog.py``). Gespeichert wird kurz nach jeder Änderung (nur
Abweichungen vom Standard bei den Werten), danach baut der Editor wie gewohnt neu;
„Kobold neu starten“ zeigt das Ergebnis.

Sonderlogik aus ``persoenlichkeit.py`` wird nur angezeigt (gelesen, nicht ausgeführt).
"""
from __future__ import annotations

import ast
import copy
import html
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMessageBox,
                               QPlainTextEdit, QPushButton, QScrollArea, QSlider, QSpinBox, QSplitter,
                               QTabWidget, QTextBrowser, QVBoxLayout, QWidget)

from dmnt_kobold import katalog, stil
from dmnt_kobold.toene import KLAENGE

GRAU = "#8A938E"
WARN = "#A0671A"
SPEICHERN_NACH_MS = 400


# --- Hilfen (ohne Fenster, testbar) -------------------------------------------------

def sonderlogik_lesen(datei: Path) -> list[tuple[str, str]] | None:
    """Sonderlogik aus persoenlichkeit.py lesen, ohne den Code auszuführen.
    None = keine Datei. Erwartet in der Klasse ``Persoenlichkeit``:
    ``SONDERLOGIK = [("Name", "Beschreibung"), ...]``."""
    if not datei.exists():
        return None
    try:
        baum = ast.parse(datei.read_text(encoding="utf-8"))
    except (OSError, SyntaxError, ValueError):
        return [("persoenlichkeit.py", "nicht lesbar (Syntaxfehler?)")]
    for knoten in baum.body:
        if not (isinstance(knoten, ast.ClassDef) and knoten.name == "Persoenlichkeit"):
            continue
        for z in knoten.body:
            ziele = z.targets if isinstance(z, ast.Assign) else [z.target] if isinstance(z, ast.AnnAssign) else []
            if any(isinstance(t, ast.Name) and t.id == "SONDERLOGIK" for t in ziele) and z.value is not None:
                try:
                    return [(str(n), str(b)) for n, b in ast.literal_eval(z.value)]
                except (ValueError, TypeError, SyntaxError):
                    break
        doc = ast.get_docstring(knoten) or ast.get_docstring(baum) or "ohne Beschreibung"
        return [("Persoenlichkeit", doc.strip().splitlines()[0])]
    return [("persoenlichkeit.py", "keine Klasse Persoenlichkeit gefunden")]


def _kurz(wert) -> str:
    if isinstance(wert, list):
        return ", ".join(str(x) for x in wert[:3]) + (" …" if len(wert) > 3 else "")
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    if isinstance(wert, str) and wert.startswith("$"):
        return f"Wert {wert[1:]}"
    return f"{wert:g}" if isinstance(wert, float) else str(wert)


KURZ_BEDINGUNG = {"titel_enthaelt": "Titel enthält „{}“", "sitzung_ab_s": "ab {} s", "ab_minuten": "ab {} min",
                  "regel_laeuft": "solange „{}“ läuft", "regel": "Blase von „{}“", "knopf": "Knopf „{}“"}


def kurz_wenn(regel: dict) -> str:
    teile = []
    for b in katalog.bedingungen(regel):
        e = katalog.EREIGNIS.get(b.get("ereignis"))
        if e is None:
            teile.append(f"?{b.get('ereignis')}")
            continue
        extra = [KURZ_BEDINGUNG.get(p.name, "{}").format(_kurz(b[p.name]))
                 for p in e.bedingungen + katalog.ALLGEMEINE_BEDINGUNGEN if b.get(p.name) not in (None, "", [])]
        teile.append(e.name + (f" ({'; '.join(extra)})" if extra else ""))
    return " oder ".join(teile) or "?"


def kurz_dann(regel: dict) -> str:
    teile = []
    for a in regel.get("dann", []):
        art = a.get("aktion")
        if art == "animation":
            teile.append(a.get("name", "?"))
        elif art == "sprechen":
            texte = a.get("texte") or [""]
            t = texte[0] if len(texte[0]) <= 30 else texte[0][:29] + "…"
            teile.append(f"„{t}“" + (f" (+{len(texte) - 1})" if len(texte) > 1 else ""))
        elif art == "ton":
            teile.append(f"Ton {a.get('name', '?')}")
        elif art == "zubehoer":
            teile.append(f"{a.get('name', '?')} {'an' if a.get('an', True) else 'aus'}")
        elif art == "gehen_zu":
            teile.append(f"geht {a.get('ziel', '?')}")
        elif art == "zurueckziehen":
            teile.append("beendet " + ", ".join(a.get("regeln", [])))
        else:
            teile.append(str(art))
    return ", ".join(teile) or "?"


def _schoen(x: float):
    return int(x) if float(x).is_integer() else round(float(x), 3)


def neue_id(basis: str, vorhanden: set[str]) -> str:
    basis = "".join(c for c in basis.lower() if c.isalnum() or c == "_") or "regel"
    rid, n = basis, 2
    while rid in vorhanden:
        rid, n = f"{basis}_{n}", n + 1
    return rid


def umbenennen(verhalten: dict, alt: str, neu: str) -> None:
    """Regel umbenennen und alle Verweise (zurueckziehen, regel, regel_laeuft) mitziehen."""
    for r in verhalten.get("regeln", []):
        if r.get("id") == alt:
            r["id"] = neu
        for b in katalog.bedingungen(r):
            for k in ("regel", "regel_laeuft"):
                if b.get(k) == alt:
                    b[k] = neu
        for a in r.get("dann", []):
            if a.get("aktion") == "zurueckziehen":
                a["regeln"] = [neu if x == alt else x for x in a.get("regeln", [])]


# --- Eingabefelder --------------------------------------------------------------------

class ParamFeld(QWidget):
    """Eingabe für einen Katalog-Parameter. ``wert()`` liefert None für „nicht gesetzt“."""
    geaendert = Signal()

    def __init__(self, p: katalog.Param, wert, quellen: dict[str, list[str]]) -> None:
        super().__init__()
        self.p = p
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        t = p.typ
        if t in ("liste", "regeln"):
            w = QPlainTextEdit()
            w.setObjectName("eingabe")
            w.setFixedHeight(92 if p.name == "texte" else 58)
            w.setPlaceholderText("eine Regel-id je Zeile" if t == "regeln" else "eine Zeile je Eintrag")
            w.setPlainText("\n".join(str(x) for x in (wert or [])))
            w.textChanged.connect(self.geaendert)
        elif t == "bool":
            w = QCheckBox()
            w.setChecked(bool(p.standard) if wert is None else bool(wert))
            w.toggled.connect(self.geaendert)
        elif t == "zahl":
            w = QComboBox()
            w.setEditable(True)
            w.addItem("")
            for d in katalog.WERTE:
                w.addItem(f"Wert: {d.id}")
            text = "" if wert is None else f"Wert: {wert[1:]}" if isinstance(wert, str) and wert.startswith("$") \
                else (f"{wert:g}" if isinstance(wert, (int, float)) else str(wert))
            w.setEditText(text)
            w.lineEdit().setPlaceholderText("Zahl oder Wert aus der Liste")
            w.editTextChanged.connect(self.geaendert)
        elif t in ("auswahl", "animation", "ton", "zubehoer", "regel"):
            w = QComboBox()
            w.setEditable(t in ("animation", "ton", "zubehoer"))
            if not p.pflicht:
                w.addItem("")
            for o in (p.auswahl if t == "auswahl" else quellen.get(t, [])):
                w.addItem(o)
            if wert not in (None, "") and w.findText(str(wert)) < 0:
                w.addItem(str(wert))
            w.setCurrentText("" if wert is None else str(wert))
            w.currentTextChanged.connect(self.geaendert)
        else:
            w = QLineEdit(str(wert or ""))
            w.textEdited.connect(self.geaendert)
        w.setToolTip(p.beschreibung)
        self.w = w
        lay.addWidget(w)
        hinweis = QLabel(p.beschreibung)
        hinweis.setObjectName("neben")
        hinweis.setWordWrap(True)
        lay.addWidget(hinweis)

    def wert(self):
        t, w = self.p.typ, self.w
        if t in ("liste", "regeln"):
            return [x.strip() for x in w.toPlainText().splitlines() if x.strip()] or None
        if t == "bool":
            return w.isChecked()
        if t == "zahl":
            s = w.currentText().strip()
            if not s:
                return None
            if s.startswith("Wert:"):
                return "$" + s[5:].strip()
            if s.startswith("$"):
                return s
            try:
                return _schoen(float(s.replace(",", ".")))
            except ValueError:
                return s                         # die Prüfung meldet es
        if isinstance(w, QComboBox):
            return w.currentText().strip() or None
        return w.text().strip() or None


class Zeile(QFrame):
    """Eine Bedingung oder Aktion: Auswahl aus dem Katalog, Beschreibung, passende Felder."""
    geaendert = Signal()
    entfernen = Signal(object)
    schieben = Signal(object, int)

    def __init__(self, bedingung: bool, daten: dict, quellen: dict[str, list[str]], mit_pfeilen: bool) -> None:
        super().__init__()
        self.setObjectName("zeile")
        self.bedingung = bedingung
        self.schluessel = "ereignis" if bedingung else "aktion"
        self.daten = copy.deepcopy(daten)
        self.quellen = quellen
        lay = QVBoxLayout(self)
        oben = QHBoxLayout()
        oben.addWidget(QLabel("Ereignis" if bedingung else "Aktion"))
        self.wahl = QComboBox()
        for d in (katalog.EREIGNISSE if bedingung else katalog.AKTIONEN):
            self.wahl.addItem(d.name, d.name)
        aktuell = self.daten.get(self.schluessel)
        if self.wahl.findData(aktuell) < 0:
            self.wahl.addItem(f"{aktuell} (unbekannt)", aktuell)
        self.wahl.setCurrentIndex(self.wahl.findData(aktuell))
        self.wahl.currentIndexChanged.connect(self._art)
        oben.addWidget(self.wahl, 1)
        if mit_pfeilen:
            for text, r, tip in (("▲", -1, "nach oben"), ("▼", 1, "nach unten")):
                b = QPushButton(text)
                b.setObjectName("klein")
                b.setToolTip(tip)
                b.clicked.connect(lambda _=False, r=r: self.schieben.emit(self, r))
                oben.addWidget(b)
        weg = QPushButton("✕")
        weg.setObjectName("klein")
        weg.setToolTip("entfernen")
        weg.clicked.connect(lambda: self.entfernen.emit(self))
        oben.addWidget(weg)
        lay.addLayout(oben)
        self.beschreibung = QLabel()
        self.beschreibung.setObjectName("neben")
        self.beschreibung.setWordWrap(True)
        lay.addWidget(self.beschreibung)
        self.form = QFormLayout()
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop)
        lay.addLayout(self.form)
        self._felder_bauen()

    def _def(self):
        name = self.wahl.currentData()
        return (katalog.EREIGNIS if self.bedingung else katalog.AKTION).get(name)

    def _params(self) -> tuple[katalog.Param, ...]:
        d = self._def()
        if d is None:
            return ()
        return d.bedingungen + katalog.ALLGEMEINE_BEDINGUNGEN if self.bedingung else d.parameter

    def _art(self) -> None:
        erlaubt = {p.name for p in self._params()}
        self.daten = {self.schluessel: self.wahl.currentData(),
                      **{k: v for k, v in self.daten.items() if k in erlaubt}}
        self._felder_bauen()
        self.geaendert.emit()

    def _felder_bauen(self) -> None:
        while self.form.rowCount():
            self.form.removeRow(0)
        d = self._def()
        text = d.beschreibung if d else "Gibt es im Katalog nicht – bitte etwas anderes wählen."
        if d is not None and self.bedingung and d.platzhalter:
            text += "  Platzhalter in Sprüchen: " + ", ".join(f"{{{n}}} = {t}" for n, t in d.platzhalter)
        if d is not None and self.bedingung and d.muster:
            text += f"  (ausgelöst als {d.muster})"
        self.beschreibung.setText(text)
        for p in self._params():
            f = ParamFeld(p, self.daten.get(p.name), self.quellen)
            f.geaendert.connect(lambda p=p, f=f: self._feld(p, f))
            self.form.addRow(QLabel(p.name + (" *" if p.pflicht else "")), f)

    def _feld(self, p: katalog.Param, f: ParamFeld) -> None:
        v = f.wert()
        if v is None or (p.typ == "bool" and v is False and not p.standard):
            self.daten.pop(p.name, None)
        else:
            self.daten[p.name] = v
        self.geaendert.emit()


# --- Regel bearbeiten ----------------------------------------------------------------------

def _weg(w: QWidget | None) -> None:
    """Sofort aus dem Fenster nehmen (deleteLater allein lässt es bis zur nächsten Runde stehen)."""
    if w is not None:
        w.hide()
        w.setParent(None)
        w.deleteLater()


class RegelFormular(QWidget):
    geaendert = Signal()
    umbenannt = Signal(str, str)

    def __init__(self, tab: "VerhaltenTab") -> None:
        super().__init__()
        self.tab = tab
        self._laed = False
        self._regel: dict = {}
        lay = QVBoxLayout(self)

        kopf = QFormLayout()
        self.id = QLineEdit()
        self.id.setToolTip("Eindeutiger Name (a–z, 0–9, _). Verweise anderer Regeln werden mit umbenannt.")
        self.id.editingFinished.connect(self._id)
        kopf.addRow("Regel", self.id)
        self.gruppe = QLineEdit()
        self.gruppe.setPlaceholderText("leer = keine Gruppe")
        self.gruppe.setToolTip("Regeln einer Gruppe sind Alternativen: je Ereignis feuert nur die erste "
                               "passende (z. B. „mit Spruch“, sonst „ohne Spruch“).")
        self.gruppe.textEdited.connect(self._weiter)
        kopf.addRow("Gruppe", self.gruppe)
        lay.addLayout(kopf)

        lay.addWidget(self._titel("Wenn …", "Eine der Bedingungen genügt („oder“)."))
        self.bedingungen = QVBoxLayout()
        lay.addLayout(self.bedingungen)
        plus_b = QPushButton("+ oder …")
        plus_b.clicked.connect(self._plus_bedingung)
        lay.addWidget(plus_b, 0, Qt.AlignmentFlag.AlignLeft)

        lay.addWidget(self._titel("→ Dann …", "Aus Animation, Spruch, Ton und Ziel wird ein Wunsch an den Motor."))
        self.aktionen = QVBoxLayout()
        lay.addLayout(self.aktionen)
        plus_a = QPushButton("+ Aktion")
        plus_a.clicked.connect(self._plus_aktion)
        lay.addWidget(plus_a, 0, Qt.AlignmentFlag.AlignLeft)

        lay.addWidget(self._titel("Wie wichtig, wie lange, wie oft", ""))
        zahlen = QGridLayout()
        self.prioritaet = QSpinBox()
        self.prioritaet.setRange(0, katalog.PRIORITAET_MAX)
        self.prioritaet.valueChanged.connect(self._weiter)
        zahlen.addWidget(QLabel("Priorität"), 0, 0)
        zahlen.addWidget(self.prioritaet, 0, 1)
        p_hinweis = QLabel("Persönlichkeit: 30–60 · Eigenleben 0–20 · wichtig 70–90 (kommt auch bei „Nicht stören“)")
        p_hinweis.setObjectName("neben")
        zahlen.addWidget(p_hinweis, 0, 2)
        self.dauer = QDoubleSpinBox()
        self.dauer.setRange(0.1, katalog.DAUER_MAX)
        self.dauer.setDecimals(1)
        self.dauer.setSuffix(" s")
        self.dauer.valueChanged.connect(self._weiter)
        self.bis_zurueck = QCheckBox("bis zurückgezogen")
        self.bis_zurueck.toggled.connect(self._weiter)
        zahlen.addWidget(QLabel("Dauer"), 1, 0)
        zahlen.addWidget(self.dauer, 1, 1)
        zahlen.addWidget(self.bis_zurueck, 1, 2)
        self.abkling = QDoubleSpinBox()
        self.abkling.setRange(0, katalog.ABKLINGZEIT_MAX)
        self.abkling.setDecimals(0)
        self.abkling.setSuffix(" s")
        self.abkling.valueChanged.connect(self._weiter)
        self.abkling_text = QLabel()
        self.abkling_text.setObjectName("neben")
        zahlen.addWidget(QLabel("Abklingzeit"), 2, 0)
        zahlen.addWidget(self.abkling, 2, 1)
        zahlen.addWidget(self.abkling_text, 2, 2)
        self.chance = QDoubleSpinBox()
        self.chance.setRange(0, 1)
        self.chance.setSingleStep(0.05)
        self.chance.setDecimals(2)
        self.chance.valueChanged.connect(self._weiter)
        c_hinweis = QLabel("1 = immer, 0,25 = jedes vierte Mal (im Schnitt)")
        c_hinweis.setObjectName("neben")
        zahlen.addWidget(QLabel("Chance"), 3, 0)
        zahlen.addWidget(self.chance, 3, 1)
        zahlen.addWidget(c_hinweis, 3, 2)
        self.aufheben = QCheckBox("wartet, wenn verdrängt (und läuft danach weiter)")
        self.aufheben.toggled.connect(self._weiter)
        zahlen.addWidget(self.aufheben, 4, 1, 1, 2)
        zahlen.setColumnStretch(2, 1)
        lay.addLayout(zahlen)

        self.meldung = QLabel()
        self.meldung.setWordWrap(True)
        lay.addWidget(self.meldung)
        lay.addStretch(1)

    @staticmethod
    def _titel(text: str, neben: str) -> QWidget:
        w = QWidget()
        h = QHBoxLayout(w)
        h.setContentsMargins(0, 12, 0, 0)
        t = QLabel(text)
        t.setObjectName("titel")
        h.addWidget(t)
        if neben:
            n = QLabel(neben)
            n.setObjectName("neben")
            h.addWidget(n)
        h.addStretch(1)
        return w

    # --- laden / sammeln ---------------------------------------------------------------
    def laden(self, regel: dict | None) -> None:
        self._laed = True
        self.setEnabled(regel is not None)
        self._regel = copy.deepcopy(regel or {})
        r = self._regel
        self.id.setText(r.get("id", ""))
        self.gruppe.setText(r.get("gruppe", ""))
        self.prioritaet.setValue(int(r.get("prioritaet", 50)))
        dauer = r.get("dauer_s", 5.0)
        self.bis_zurueck.setChecked(dauer is None)
        self.dauer.setValue(float(dauer or 5.0))
        self.abkling.setValue(float(r.get("abklingzeit_s", 0)))
        self.chance.setValue(float(r.get("chance", 1.0)))
        self.aufheben.setChecked(bool(r.get("aufheben", False)))
        for box in (self.bedingungen, self.aktionen):
            while box.count():
                _weg(box.takeAt(0).widget())
        for b in katalog.bedingungen(r):
            self._zeile_dazu(True, b)
        for a in r.get("dann", []):
            self._zeile_dazu(False, a)
        self._laed = False
        self._anzeige()

    def _zeilen(self, box: QVBoxLayout) -> list[Zeile]:
        return [box.itemAt(i).widget() for i in range(box.count()) if isinstance(box.itemAt(i).widget(), Zeile)]

    def _zeile_dazu(self, bedingung: bool, daten: dict) -> None:
        z = Zeile(bedingung, daten, self.tab.quellen(), mit_pfeilen=not bedingung)
        z.geaendert.connect(self._weiter)
        z.entfernen.connect(self._entfernen)
        z.schieben.connect(self._schieben)
        (self.bedingungen if bedingung else self.aktionen).addWidget(z)

    def regel(self) -> dict:
        r: dict = {"id": self._regel.get("id", "")}
        if self._regel.get("aktiv") is False:
            r["aktiv"] = False
        bed = [z.daten for z in self._zeilen(self.bedingungen)]
        r["wenn"] = bed[0] if len(bed) == 1 else bed
        r["dann"] = [z.daten for z in self._zeilen(self.aktionen)]
        r["prioritaet"] = self.prioritaet.value()
        if not any(a.get("aktion") == "bleiben" for a in r["dann"]):
            r["dauer_s"] = None if self.bis_zurueck.isChecked() else _schoen(self.dauer.value())
        if self.aufheben.isChecked():
            r["aufheben"] = True
        if self.abkling.value() > 0:
            r["abklingzeit_s"] = _schoen(self.abkling.value())
        if self.chance.value() < 1:
            r["chance"] = _schoen(self.chance.value())
        if self.gruppe.text().strip():
            r["gruppe"] = self.gruppe.text().strip()
        return r

    # --- Änderungen ------------------------------------------------------------------------
    def _weiter(self, *_a) -> None:
        if self._laed:
            return
        self._regel = self.regel()
        self._anzeige()
        self.geaendert.emit()

    def _anzeige(self) -> None:
        bleiben = any(z.daten.get("aktion") == "bleiben" for z in self._zeilen(self.aktionen))
        self.dauer.setEnabled(not bleiben and not self.bis_zurueck.isChecked())
        self.bis_zurueck.setEnabled(not bleiben)
        if bleiben:
            self.bis_zurueck.setText("„bleiben“: bis zurückgezogen")
        else:
            self.bis_zurueck.setText("bis zurückgezogen")
        s = self.abkling.value()
        self.abkling_text.setText("feuert jedes Mal" if s == 0 else
                                  f"frühestens wieder nach {s / 60:g} min" if s >= 60 else
                                  f"frühestens wieder nach {s:g} s")

    def meldungen_zeigen(self, fehler: list[str], warnungen: list[str]) -> None:
        rid = self._regel.get("id", "")
        eigen = [f for f in fehler if f"Regel „{rid}“" in f]
        warn = [w for w in warnungen if f"Regel „{rid}“" in w]
        teile = [f"<span style='color:{stil.ROT}'>✗ {html.escape(f)}</span>" for f in eigen]
        teile += [f"<span style='color:{WARN}'>⚠ {html.escape(w)}</span>" for w in warn]
        self.meldung.setText("<br>".join(teile) if teile else
                             f"<span style='color:{stil.AKZENT}'>✓ Regel ist gültig</span>")

    def _id(self) -> None:
        if self._laed:
            return
        alt, neu = self._regel.get("id", ""), self.id.text().strip()
        if neu != alt:
            self.umbenannt.emit(alt, neu)

    def _plus_bedingung(self) -> None:
        self._zeile_dazu(True, {"ereignis": "maus.klick"})
        self._weiter()

    def _plus_aktion(self) -> None:
        self._zeile_dazu(False, {"aktion": "animation", "name": "freuen"})
        self._weiter()

    def _entfernen(self, z: Zeile) -> None:
        box = self.bedingungen if z.bedingung else self.aktionen
        if len(self._zeilen(box)) <= 1:
            self.tab.editor.meldung("Eine Regel braucht mindestens ein Ereignis und eine Aktion.")
            return
        box.removeWidget(z)
        _weg(z)
        self._weiter()

    def _schieben(self, z: Zeile, r: int) -> None:
        box = self.aktionen
        i = box.indexOf(z)
        j = i + r
        if 0 <= j < box.count():
            box.removeWidget(z)
            box.insertWidget(j, z)
            self._weiter()


class RegelnBereich(QWidget):
    def __init__(self, tab: "VerhaltenTab") -> None:
        super().__init__()
        self.tab = tab
        lay = QHBoxLayout(self)
        split = QSplitter()
        lay.addWidget(split)

        links = QWidget()
        ll = QVBoxLayout(links)
        hinweis = QLabel("Von oben nach unten geprüft. Haken = aktiv.")
        hinweis.setObjectName("neben")
        ll.addWidget(hinweis)
        self.liste = QListWidget()
        self.liste.setWordWrap(True)
        self.liste.currentRowChanged.connect(lambda _: self.anzeigen())
        self.liste.itemChanged.connect(self._haken)
        ll.addWidget(self.liste, 1)
        knoepfe = QGridLayout()
        for i, (text, f) in enumerate((("Neu", self._neu), ("Duplizieren", self._duplizieren),
                                       ("Löschen", self._loeschen), ("▲ Hoch", lambda: self._schieben(-1)),
                                       ("▼ Runter", lambda: self._schieben(1)))):
            b = QPushButton(text)
            b.clicked.connect(f)
            knoepfe.addWidget(b, i // 3, i % 3)
        ll.addLayout(knoepfe)
        split.addWidget(links)

        self.formular = RegelFormular(tab)
        self.formular.geaendert.connect(self._formular)
        self.formular.umbenannt.connect(self._umbenennen)
        rolle = QScrollArea()
        rolle.setWidgetResizable(True)
        rolle.setWidget(self.formular)
        split.addWidget(rolle)
        split.setSizes([460, 900])

    @property
    def regeln(self) -> list[dict]:
        return self.tab.verhalten.setdefault("regeln", [])

    @staticmethod
    def _text(r: dict) -> str:
        return f"{r.get('id', '?')}\n    Wenn {kurz_wenn(r)}  →  {kurz_dann(r)}"

    def aufbauen(self, waehlen: str | None = None) -> None:
        aktuell = waehlen or self._aktuelle_id()
        self.liste.blockSignals(True)
        self.liste.clear()
        for r in self.regeln:
            it = QListWidgetItem(self._text(r))
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if r.get("aktiv", True) else Qt.CheckState.Unchecked)
            if not r.get("aktiv", True):
                it.setForeground(QColor(GRAU))
            self.liste.addItem(it)
        for name, beschreibung in self.tab.sonderlogik() or []:
            it = QListWidgetItem(f"Sonderlogik (Python): {name} – {beschreibung}")
            it.setFlags(Qt.ItemFlag.ItemIsEnabled)
            it.setForeground(QColor(GRAU))
            it.setToolTip("Steht in persoenlichkeit.py und läuft zusätzlich zu den Regeln. Nur lesen.")
            self.liste.addItem(it)
        ids = [r.get("id") for r in self.regeln]
        self.liste.setCurrentRow(ids.index(aktuell) if aktuell in ids else (0 if ids else -1))
        self.liste.blockSignals(False)
        self.anzeigen()

    def _aktuelle_id(self) -> str | None:
        i = self.liste.currentRow()
        return self.regeln[i].get("id") if 0 <= i < len(self.regeln) else None

    def anzeigen(self) -> None:
        i = self.liste.currentRow()
        self.formular.laden(self.regeln[i] if 0 <= i < len(self.regeln) else None)
        self.tab.pruefen()

    def _formular(self) -> None:
        i = self.liste.currentRow()
        if not 0 <= i < len(self.regeln):
            return
        self.regeln[i] = self.formular.regel()
        self.liste.blockSignals(True)
        self.liste.item(i).setText(self._text(self.regeln[i]))
        self.liste.blockSignals(False)
        self.tab.geaendert()

    def _haken(self, it: QListWidgetItem) -> None:
        i = self.liste.row(it)
        if not 0 <= i < len(self.regeln):
            return
        if it.checkState() == Qt.CheckState.Checked:
            self.regeln[i].pop("aktiv", None)
        else:
            self.regeln[i]["aktiv"] = False
        self.liste.blockSignals(True)
        it.setForeground(QColor(stil.TEXT if self.regeln[i].get("aktiv", True) else GRAU))
        self.liste.blockSignals(False)
        if i == self.liste.currentRow():
            self.formular.laden(self.regeln[i])
        self.tab.geaendert()

    def _umbenennen(self, alt: str, neu: str) -> None:
        ids = {r.get("id") for r in self.regeln}
        if not katalog.ID_MUSTER.match(neu) or neu in ids:
            self.tab.editor.meldung(f"„{neu}“ geht nicht: nur a–z, 0–9, _ und noch nicht vergeben.")
            self.formular.id.setText(alt)
            return
        umbenennen(self.tab.verhalten, alt, neu)
        self.tab.geaendert()
        self.aufbauen(waehlen=neu)

    def _neu(self) -> None:
        rid = neue_id("neue_regel", {r.get("id") for r in self.regeln})
        i = self.liste.currentRow() + 1 if self.liste.currentRow() >= 0 else len(self.regeln)
        self.regeln.insert(min(i, len(self.regeln)), {
            "id": rid, "wenn": {"ereignis": "maus.klick"},
            "dann": [{"aktion": "animation", "name": "freuen"}], "prioritaet": 40, "dauer_s": 2})
        self.tab.geaendert()
        self.aufbauen(waehlen=rid)

    def _duplizieren(self) -> None:
        i = self.liste.currentRow()
        if not 0 <= i < len(self.regeln):
            return
        kopie = copy.deepcopy(self.regeln[i])
        kopie["id"] = neue_id(kopie.get("id", "regel"), {r.get("id") for r in self.regeln})
        self.regeln.insert(i + 1, kopie)
        self.tab.geaendert()
        self.aufbauen(waehlen=kopie["id"])

    def _loeschen(self) -> None:
        i = self.liste.currentRow()
        if not 0 <= i < len(self.regeln):
            return
        rid = self.regeln[i].get("id")
        if QMessageBox.question(self, "Löschen", f"Regel „{rid}“ löschen?") != QMessageBox.StandardButton.Yes:
            return
        del self.regeln[i]
        self.tab.geaendert()
        rest = [r.get("id") for r in self.regeln]
        self.aufbauen(waehlen=rest[min(i, len(rest) - 1)] if rest else None)

    def _schieben(self, r: int) -> None:
        i = self.liste.currentRow()
        j = i + r
        if 0 <= i < len(self.regeln) and 0 <= j < len(self.regeln):
            self.regeln[i], self.regeln[j] = self.regeln[j], self.regeln[i]
            self.tab.geaendert()
            self.aufbauen(waehlen=self.regeln[j].get("id"))


# --- Werte -------------------------------------------------------------------------------------

class WerteBereich(QScrollArea):
    SCHRITTE = 1000

    def __init__(self, tab: "VerhaltenTab") -> None:
        super().__init__()
        self.tab = tab
        self.setWidgetResizable(True)
        innen = QWidget()
        grid = QGridLayout(innen)
        grid.setHorizontalSpacing(16)
        hinweis = QLabel("Zahlen, die das Verhalten prägen. Gespeichert werden nur Abweichungen vom Standard – "
                         "sie gelten nur für diesen Avatar.")
        hinweis.setObjectName("neben")
        hinweis.setWordWrap(True)
        grid.addWidget(hinweis, 0, 0, 1, 5)
        self.zeilen: dict[str, tuple] = {}
        zeile, bereich = 1, None
        for d in katalog.WERTE:
            if d.bereich != bereich:
                bereich = d.bereich
                t = QLabel(bereich)
                t.setObjectName("titel")
                grid.addWidget(t, zeile, 0, 1, 5)
                zeile += 1
            name = QLabel()
            name.setWordWrap(True)
            name.setMinimumWidth(380)
            regler = QSlider(Qt.Orientation.Horizontal)
            regler.setRange(0, self.SCHRITTE)
            regler.setMinimumWidth(220)
            if d.ganzzahl:
                feld = QSpinBox()
                feld.setRange(int(d.min), int(d.max))
            else:
                feld = QDoubleSpinBox()
                feld.setRange(d.min, d.max)
                feld.setDecimals(3 if d.max <= 1 else 1)
                feld.setSingleStep(0.01 if d.max <= 1 else 0.5)
            if d.einheit:
                feld.setSuffix(f" {d.einheit}")
            feld.setMinimumWidth(130)
            standard = QLabel()
            standard.setStyleSheet(f"color: {GRAU};")
            knopf = QPushButton("Standard")
            knopf.setToolTip("Abweichung verwerfen")
            regler.valueChanged.connect(lambda pos, d=d: self._regler(d, pos))
            feld.valueChanged.connect(lambda wert, d=d: self._feld(d, wert))
            knopf.clicked.connect(lambda _=False, d=d: self._standard(d))
            for spalte, w in enumerate((name, regler, feld, standard, knopf)):
                grid.addWidget(w, zeile, spalte)
            self.zeilen[d.id] = (name, regler, feld, standard, knopf)
            zeile += 1
        grid.setRowStretch(zeile, 1)
        grid.setColumnStretch(0, 1)
        self.setWidget(innen)
        self._laed = False

    def standard(self, d: katalog.WertDef) -> float:
        if d.id == "laufgeschwindigkeit":            # ohne Angabe gilt das Tempo aus dem Bauplan
            return float(self.tab.editor.projekt.bauplan.get("bewegung", {}).get("tempo", d.standard))
        return d.standard

    @property
    def werte(self) -> dict:
        return self.tab.verhalten.setdefault("werte", {})

    def aufbauen(self) -> None:
        self._laed = True
        for d in katalog.WERTE:
            self._zeigen(d, self.werte.get(d.id, self.standard(d)))
        self._laed = False

    def _zeigen(self, d: katalog.WertDef, wert: float) -> None:
        name, regler, feld, standard, knopf = self.zeilen[d.id]
        for w in (regler, feld):
            w.blockSignals(True)
        feld.setValue(int(round(wert)) if d.ganzzahl else float(wert))
        regler.setValue(round((wert - d.min) / (d.max - d.min) * self.SCHRITTE) if d.max > d.min else 0)
        for w in (regler, feld):
            w.blockSignals(False)
        abweichend = d.id in self.werte
        farbe = stil.AKZENT if abweichend else stil.TEXT
        name.setText(f"<b style='color:{farbe}'>{d.id}</b>{' · geändert' if abweichend else ''}<br>"
                     f"<span style='color:{stil.NEBENTEXT}'>{html.escape(d.beschreibung)}</span>")
        std = self.standard(d)
        quelle = " (Bauplan)" if d.id == "laufgeschwindigkeit" and std != d.standard else ""
        standard.setText(f"Standard: {std:g} {d.einheit}{quelle}".strip())
        knopf.setEnabled(abweichend)

    def _regler(self, d: katalog.WertDef, pos: int) -> None:
        wert = d.min + (d.max - d.min) * pos / self.SCHRITTE
        self._setzen(d, round(wert) if d.ganzzahl else round(wert, 3))

    def _feld(self, d: katalog.WertDef, wert: float) -> None:
        self._setzen(d, wert)

    def _setzen(self, d: katalog.WertDef, wert: float) -> None:
        if self._laed:
            return
        if abs(float(wert) - self.standard(d)) < 1e-9:
            self.werte.pop(d.id, None)
        else:
            self.werte[d.id] = int(round(wert)) if d.ganzzahl else _schoen(wert)
        self._zeigen(d, wert)
        self.tab.geaendert()

    def _standard(self, d: katalog.WertDef) -> None:
        self.werte.pop(d.id, None)
        self._zeigen(d, self.standard(d))
        self.tab.geaendert()


# --- Können ---------------------------------------------------------------------------------------

class KoennenBereich(QTextBrowser):
    def __init__(self, tab: "VerhaltenTab") -> None:
        super().__init__()
        self.tab = tab
        self.setOpenLinks(False)

    def aufbauen(self) -> None:
        vorhanden = self.tab.animationen()
        basis: dict[str, int] = {}
        for n in vorhanden:
            if "@" not in n:
                b = n.split("~")[0]
                basis[b] = basis.get(b, 0) + 1
        genutzt: dict[str, list[str]] = {}
        for r in self.tab.verhalten.get("regeln", []):
            for a in r.get("dann", []):
                if a.get("aktion") == "animation" and a.get("name"):
                    genutzt.setdefault(katalog.NAMEN.get(a["name"], a["name"]), []).append(r.get("id", "?"))
            if any(a.get("aktion") == "sprechen" for a in r.get("dann", [])) and \
                    not any(a.get("aktion") == "animation" for a in r.get("dann", [])):
                genutzt.setdefault("sprechen", []).append(r.get("id", "?"))
        e = html.escape
        z = [f"<style>td, th {{ padding: 4px 10px; vertical-align: top; }} th {{ text-align: left; "
             f"color: {stil.NEBENTEXT}; }} h3 {{ margin-top: 18px; }}</style>"]
        z.append("<h3>Animationen – Kern-Vokabular</h3><table><tr><th>Animation</th><th>Wofür</th>"
                 "<th>Genutzt von</th><th>Stand</th></tr>")
        namen = list(katalog.KERN_ANIMATIONEN) + sorted(set(genutzt) - set(katalog.KERN_ANIMATIONEN))
        for n in namen:
            wofuer, wer = katalog.KERN_ANIMATIONEN.get(n, ("eigene", ""))
            regeln = genutzt.get(n, [])
            if regeln:
                wer = ", ".join(x for x in [wer if not wer.startswith("Regeln") else "",
                                            "Regeln: " + ", ".join(regeln)] if x)
            if n in basis:
                stand = f"<span style='color:{stil.AKZENT}'>✓ vorhanden" + \
                        (f" ({basis[n]} Varianten)" if basis[n] > 1 else "") + "</span>"
            elif n == katalog.RUECKFALL:
                stand = f"<span style='color:{stil.ROT}'>✗ fehlt – Pflicht!</span>"
            else:
                stand = f"<span style='color:{WARN}'>fehlt → Rückfall auf „{katalog.RUECKFALL}“</span>"
            z.append(f"<tr><td><b>{e(n)}</b></td><td>{e(wofuer)}</td><td>{e(wer)}</td><td>{stand}</td></tr>")
        z.append("</table>")
        eigene = sorted(set(basis) - set(namen))
        if eigene:
            z.append("<p>Weitere Animationen des Avatars (nur über Regeln erreichbar): " +
                     ", ".join(f"<b>{e(n)}</b>" for n in eigene) + "</p>")
        fehler, warnungen = self.tab.pruefung
        if fehler or warnungen:
            z.append("<h3>Prüfung</h3><ul>")
            z += [f"<li style='color:{stil.ROT}'>{e(f)}</li>" for f in fehler]
            z += [f"<li style='color:{WARN}'>{e(w)}</li>" for w in warnungen]
            z.append("</ul>")
        z.append("<h3>Ereignisse des Sockels</h3><table><tr><th>Ereignis</th><th>Bedeutung</th>"
                 "<th>Bedingungen</th></tr>")
        for ev in katalog.EREIGNISSE:
            bed = "<br>".join(f"<b>{e(p.name)}</b>: {e(p.beschreibung)}" for p in ev.bedingungen) or "–"
            z.append(f"<tr><td><b>{e(ev.name)}</b></td><td>{e(ev.beschreibung)}</td><td>{bed}</td></tr>")
        z.append("</table><h3>Aktionen</h3><table><tr><th>Aktion</th><th>Bedeutung</th></tr>")
        for a in katalog.AKTIONEN:
            z.append(f"<tr><td><b>{e(a.name)}</b></td><td>{e(a.beschreibung)}</td></tr>")
        z.append("</table><h3>Prioritäten</h3><table>")
        z += [f"<tr><td><b>{e(p)}</b></td><td>{e(t)}</td></tr>" for p, t in katalog.PRIORITAETEN]
        z.append("</table>")
        pos = self.verticalScrollBar().value()
        self.setHtml("".join(z))
        self.verticalScrollBar().setValue(pos)


# --- Reiter ----------------------------------------------------------------------------------------

class VerhaltenTab(QWidget):
    def __init__(self, editor) -> None:
        super().__init__()
        self.editor = editor
        self.pruefung: tuple[list[str], list[str]] = ([], [])
        self.setStyleSheet(f"""
            QPlainTextEdit#eingabe {{ background: white; color: {stil.TEXT}; border: 1px solid {stil.LINIE};
                border-radius: 10px; font-family: "{stil.schriftart()}"; font-size: 14px; padding: 4px; }}
            QFrame#zeile {{ background: white; border: 1px solid {stil.LINIE}; border-radius: 12px; }}
            QTextBrowser {{ background: white; border: 1px solid {stil.LINIE}; border-radius: 12px; padding: 8px; }}
            QListWidget::item {{ padding: 6px 4px; }}
        """)
        lay = QVBoxLayout(self)
        kopf = QHBoxLayout()
        self.code = QLabel()
        kopf.addWidget(self.code)
        self.status = QLabel()
        self.status.setWordWrap(True)
        kopf.addWidget(self.status, 1)
        lay.addLayout(kopf)
        self.unter = QTabWidget()
        self.werte = WerteBereich(self)
        self.regeln = RegelnBereich(self)
        self.koennen = KoennenBereich(self)
        self.unter.addTab(self.werte, "Werte")
        self.unter.addTab(self.regeln, "Regeln")
        self.unter.addTab(self.koennen, "Können")
        self.unter.setCurrentIndex(1)
        lay.addWidget(self.unter, 1)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self.speichern_jetzt)

    # --- Daten ---------------------------------------------------------------------------
    @property
    def verhalten(self) -> dict:
        return self.editor.projekt.verhalten

    def animationen(self) -> list[str]:
        return list(self.editor.projekt.bauplan.get("animationen", {}))

    def sonderlogik(self) -> list[tuple[str, str]] | None:
        return sonderlogik_lesen(self.editor.projekt.ordner / "persoenlichkeit.py")

    def quellen(self) -> dict[str, list[str]]:
        pr = self.editor.projekt
        anims = sorted({n.split("~")[0] for n in self.animationen() if "@" not in n} | {"ruhe"})
        return {"animation": anims,
                "ton": sorted(set(pr.bauplan.get("toene", {})) | set(KLAENGE)),
                "zubehoer": sorted(set(pr.zubehoer) | {"kopfhoerer"}),
                "regel": [r.get("id", "") for r in self.verhalten.get("regeln", [])]}

    # --- Ablauf ---------------------------------------------------------------------------
    def aufbauen(self) -> None:
        self.werte.aufbauen()
        self.regeln.aufbauen()
        self.pruefen()

    def geaendert(self) -> None:
        self._timer.start(SPEICHERN_NACH_MS)
        self.pruefen()

    def speichern_jetzt(self) -> None:
        self._timer.stop()
        pr = self.editor.projekt
        vorher = pr.verhalten
        neu_angelegt = not (pr.ordner / "verhalten.json").exists()
        pr.verhalten_speichern()
        if neu_angelegt:
            self.editor._beobachten()          # noqa: SLF001 – neue Datei mit beobachten
        if pr.verhalten is not vorher:          # fremde Änderung wurde eingemischt
            self.aufbauen()
        self.editor.geaendert()

    def pruefen(self) -> None:
        self.pruefung = katalog.pruefen(self.verhalten, self.animationen())
        fehler, warnungen = self.pruefung
        sonder = self.sonderlogik()
        if sonder is None:
            self.code.setText("ohne Code")
            self.code.setObjectName("marke_offiziell")
            self.code.setToolTip("Kein Python im Avatar: alles Verhalten steht in verhalten.json.")
        else:
            self.code.setText("mit Sonderlogik (Python)")
            self.code.setObjectName("marke_fremd")
            self.code.setToolTip("persoenlichkeit.py läuft zusätzlich zu den Regeln.")
        self.code.style().unpolish(self.code)      # Objektname neu auswerten
        self.code.style().polish(self.code)
        n = len(self.verhalten.get("regeln", []))
        if fehler:
            text = (f"<span style='color:{stil.ROT}'><b>{len(fehler)} Fehler – der Bau bricht ab:</b> "
                    f"{html.escape(fehler[0])}{' …' if len(fehler) > 1 else ''}</span>")
        elif warnungen:
            text = (f"<span style='color:{WARN}'>{n} Regeln · {len(warnungen)} Warnung(en): "
                    f"{html.escape(warnungen[0])}</span>")
        else:
            text = f"<span style='color:{stil.AKZENT}'>{n} Regeln · geprüft ✓</span>"
        self.status.setText(text)
        self.regeln.formular.meldungen_zeigen(fehler, warnungen)
        self.koennen.aufbauen()
