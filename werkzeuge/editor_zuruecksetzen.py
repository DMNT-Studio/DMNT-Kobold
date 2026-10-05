"""Töne und Verhalten (Regeln + Werte) eines Avatars im Editor zurücksetzen.

Zur Auswahl stehen:
  • der Stand im Repo (zuletzt committet) – das, was Nutzer mit dem Setup bekommen
  • für das Verhalten zusätzlich das Standard-Verhalten des Sockels
  • frühere Fassungen aus dem Verlauf (``quellen/<id>/_alt/verlauf/``), neueste zuerst

Zurücksetzen speichert über ``Projekt._speichern`` – der Stand davor landet damit selbst im
Verlauf und lässt sich genauso wiederherstellen. Tondateien werden nie gelöscht.
"""
from __future__ import annotations

import copy
import json
import re
import subprocess
import html
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QDialogButtonBox, QLabel, QListWidget, QListWidgetItem,
                               QVBoxLayout)

from dmnt_kobold import stil
from dmnt_kobold.regeln import standard_verhalten

WURZEL = Path(__file__).resolve().parents[1]
BEREICHE = {"toene": ("bauplan", "Töne"), "verhalten": ("verhalten", "Verhalten (Regeln und Werte)")}
VERLAUF_ZEIGEN = 40
_ZEIT = re.compile(r"_(\d{8})_(\d{6})_(\d{3})$")


@dataclass
class Stand:
    name: str
    zeit: str
    daten: dict


# --- Daten (ohne Fenster, testbar) ---------------------------------------------------

def teil(bereich: str, datei_inhalt: dict) -> dict:
    """Den zurücksetzbaren Teil aus dem Inhalt einer Datei holen."""
    if bereich == "toene":
        return copy.deepcopy(datei_inhalt.get("toene") or {})
    return {"werte": copy.deepcopy(datei_inhalt.get("werte") or {}),
            "regeln": copy.deepcopy(datei_inhalt.get("regeln") or []),
            **{k: copy.deepcopy(v) for k, v in datei_inhalt.items() if k not in ("werte", "regeln")}}


def aktuell(projekt, bereich: str) -> dict:
    return teil(bereich, getattr(projekt, BEREICHE[bereich][0]))


def _git(*args: str) -> str | None:
    try:
        erg = subprocess.run(["git", "-C", str(WURZEL), *args], capture_output=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return erg.stdout.decode("utf-8", "replace") if erg.returncode == 0 else None


def repo_stand(projekt, bereich: str) -> Stand | None:
    """Stand der Datei im letzten Commit, None wenn der Avatar nicht im Repo ist (z. B. Sulfi)."""
    datei = projekt.ordner / datei_name(bereich)
    try:
        rel = datei.resolve().relative_to(WURZEL).as_posix()
    except ValueError:
        return None
    text = _git("show", f"HEAD:{rel}")
    if text is None:
        return None
    try:
        inhalt = json.loads(text)
    except ValueError:
        return None
    zeit = (_git("log", "-1", "--format=%cd", "--date=format:%d.%m.%Y %H:%M", "--", rel) or "").strip()
    return Stand("Stand im Repo (zuletzt committet)", zeit, teil(bereich, inhalt))


def datei_name(bereich: str) -> str:
    return "bauplan.json" if bereich == "toene" else "verhalten.json"


def verlauf_staende(projekt, bereich: str) -> list[Stand]:
    """Frühere Fassungen aus dem Verlauf, neueste zuerst, ohne Doppelte."""
    stamm = Path(datei_name(bereich)).stem
    ordner = projekt.ordner / "_alt" / "verlauf"
    if not ordner.is_dir():
        return []
    ergebnis: list[Stand] = []
    gesehen: list[dict] = []
    for pfad in sorted(ordner.glob(f"{stamm}_*.json"), reverse=True):
        m = _ZEIT.search(pfad.stem)
        if not m:
            continue
        try:
            daten = teil(bereich, json.loads(pfad.read_text(encoding="utf-8")))
        except (OSError, ValueError):
            continue
        if daten in gesehen:
            continue
        gesehen.append(daten)
        zeit = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S").strftime("%d.%m.%Y %H:%M:%S")
        ergebnis.append(Stand("Verlauf", zeit, daten))
        if len(ergebnis) >= VERLAUF_ZEIGEN:
            break
    return ergebnis


def staende(projekt, bereich: str) -> list[Stand]:
    """Alle Stände zur Auswahl, ohne den, der gerade gilt."""
    jetzt = aktuell(projekt, bereich)
    liste: list[Stand] = []
    repo = repo_stand(projekt, bereich)
    if repo is not None:
        liste.append(repo)
    if bereich == "verhalten":
        std = standard_verhalten()
        std.pop("beschreibung", None)
        liste.append(Stand("Standard-Verhalten des Sockels", "", teil(bereich, std)))
    liste += verlauf_staende(projekt, bereich)
    eindeutig: list[Stand] = []
    for s in liste:
        if s.daten != jetzt and all(s.daten != e.daten for e in eindeutig):
            eindeutig.append(s)
    return eindeutig


def zuruecksetzen(projekt, bereich: str, stand: Stand) -> None:
    """Stand übernehmen und speichern (der bisherige Stand geht in den Verlauf)."""
    if bereich == "toene":
        if stand.daten:
            projekt.bauplan["toene"] = copy.deepcopy(stand.daten)
        else:
            projekt.bauplan.pop("toene", None)
        projekt.bauplan_speichern()
    else:
        projekt.verhalten = copy.deepcopy(stand.daten)
        projekt.verhalten_speichern()


def zusammenfassung(bereich: str, daten: dict) -> str:
    if bereich == "toene":
        if not daten:
            return "keine Töne"
        teile = []
        for moment, t in daten.items():
            if "segmente" in t:
                teile.append(f"{moment} (eingebaut)")
            else:
                namen = [Path(d).name for d in t.get("dateien", [])]
                teile.append(f"{moment}: " + ", ".join(namen))
        return "\n".join(teile)
    regeln = daten.get("regeln", [])
    werte = daten.get("werte", {})
    text = f"{len(regeln)} Regeln, {len(werte)} geänderte Werte"
    if regeln:
        text += "\n" + ", ".join(r.get("id", "?") for r in regeln)
    return text


def unterschied(bereich: str, jetzt: dict, stand: dict) -> str:
    """Kurz, was sich beim Zurücksetzen ändert."""
    if bereich == "toene":
        a, b = set(jetzt), set(stand)
        geaendert = sorted(m for m in a & b if jetzt[m] != stand[m])
    else:
        ja = {r.get("id"): r for r in jetzt.get("regeln", [])}
        st = {r.get("id"): r for r in stand.get("regeln", [])}
        a, b = set(ja), set(st)
        geaendert = sorted(i for i in a & b if ja[i] != st[i])
    teile = []
    if b - a:
        teile.append("kommt zurück: " + ", ".join(sorted(map(str, b - a))))
    if a - b:
        teile.append("fällt weg: " + ", ".join(sorted(map(str, a - b))))
    if geaendert:
        teile.append("ändert sich: " + ", ".join(map(str, geaendert)))
    if bereich == "verhalten" and jetzt.get("werte") != stand.get("werte"):
        teile.append("Werte ändern sich")
    return "\n".join(teile) or "nur kleine Unterschiede (Reihenfolge, Einstellungen)"


# --- Fenster -----------------------------------------------------------------------

class ZuruecksetzenDialog(QDialog):
    def __init__(self, parent, projekt, bereich: str) -> None:
        super().__init__(parent)
        self.bereich = bereich
        self.jetzt = aktuell(projekt, bereich)
        self.liste_staende = staende(projekt, bereich)
        name = BEREICHE[bereich][1]
        self.setWindowTitle(f"{name} zurücksetzen – {projekt.id}")
        self.resize(720, 560)
        lay = QVBoxLayout(self)
        was = "sollen die Töne" if bereich == "toene" else "soll das Verhalten (Regeln und Werte)"
        erkl = QLabel(f"Auf welchen Stand {was} von „{projekt.id}“ zurück? Der jetzige Stand "
                      "kommt dabei in den Verlauf und lässt sich hier genauso wiederherstellen. "
                      "Dateien werden nicht gelöscht.")
        erkl.setWordWrap(True)
        lay.addWidget(erkl)
        self.liste = QListWidget()
        for s in self.liste_staende:
            it = QListWidgetItem(f"{s.name}" + (f"  ·  {s.zeit}" if s.zeit else ""))
            self.liste.addItem(it)
        self.liste.currentRowChanged.connect(self._zeigen)
        lay.addWidget(self.liste, 1)
        self.vorschau = QLabel()
        self.vorschau.setWordWrap(True)
        self.vorschau.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.vorschau.setStyleSheet(f"background: white; color: {stil.TEXT}; border: 1px solid {stil.LINIE};"
                                    " border-radius: 10px; padding: 10px;")
        self.vorschau.setMinimumHeight(150)
        self.vorschau.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self.vorschau, 1)
        knoepfe = QDialogButtonBox()
        self.ok = knoepfe.addButton("Zurücksetzen", QDialogButtonBox.ButtonRole.AcceptRole)
        self.ok.setObjectName("haupt")
        knoepfe.addButton("Abbrechen", QDialogButtonBox.ButtonRole.RejectRole)
        knoepfe.accepted.connect(self.accept)
        knoepfe.rejected.connect(self.reject)
        lay.addWidget(knoepfe)
        if self.liste_staende:
            self.liste.setCurrentRow(0)
        else:
            self.vorschau.setText("Es gibt keinen anderen Stand als den jetzigen.")
            self.ok.setEnabled(False)

    def _zeigen(self, i: int) -> None:
        if not 0 <= i < len(self.liste_staende):
            return
        s = self.liste_staende[i]
        self.vorschau.setText(f"<b>Beim Zurücksetzen</b><br>{_html(unterschied(self.bereich, self.jetzt, s.daten))}"
                              f"<br><br><b>Dieser Stand</b><br>{_html(zusammenfassung(self.bereich, s.daten))}")

    @property
    def gewaehlt(self) -> Stand | None:
        i = self.liste.currentRow()
        return self.liste_staende[i] if 0 <= i < len(self.liste_staende) else None


def _html(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def fragen_und_zuruecksetzen(parent, projekt, bereich: str) -> Stand | None:
    """Dialog zeigen; liefert den übernommenen Stand oder None."""
    d = ZuruecksetzenDialog(parent, projekt, bereich)
    if d.exec() != QDialog.DialogCode.Accepted or d.gewaehlt is None:
        return None
    zuruecksetzen(projekt, bereich, d.gewaehlt)
    return d.gewaehlt
