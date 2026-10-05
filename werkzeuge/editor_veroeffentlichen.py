"""„Veröffentlichen“ im Avatar-Editor: Änderungen hochladen und als neue Version herausgeben.

Ablauf (stoppt beim ersten Fehler):
  1. Tests laufen lassen (pytest)
  2. Version erhöhen (pyproject.toml + __init__.py) und „Was ist neu“ in CHANGELOG.md
  3. Commit nur der angehakten Dateien
  4. Push nach GitHub (main)
  5. Tag v<version> pushen → GitHub Actions baut Setup, ZIP und Release,
     installierte Kobolde melden sich per Sprechblase.

Ohne „neue Version“ werden die Änderungen nur hochgeladen (Schritte 1, 3, 4).
Neue (noch nie hochgeladene) Dateien sind nicht vorausgewählt: Bilder und Töne gehen damit
öffentlich ins Netz und brauchen eine Lizenz, die das erlaubt.
"""
from __future__ import annotations

import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PySide6.QtCore import QProcess, QProcessEnvironment, Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QListWidget,
                               QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout)

from dmnt_kobold import stil

WURZEL = Path(__file__).resolve().parents[1]
ACTIONS_URL = "https://github.com/DMNT-Studio/DMNT-Kobold/actions"
MEDIEN = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".wav", ".ogg", ".mp3", ".flac", ".m4a", ".mp4"}
VERSIONSDATEIEN = ("pyproject.toml", "src/dmnt_kobold/__init__.py", "CHANGELOG.md")
ARTEN = (("patch", "Kleine Verbesserung / Fehlerbehebung"), ("minor", "Neue Funktion"),
         ("major", "Großer Schritt"))


# --- ohne Fenster, testbar ---------------------------------------------------------------

@dataclass
class Aenderung:
    pfad: str
    art: str            # geändert | neu | gelöscht | umbenannt
    vorauswahl: bool
    hinweis: str = ""


def _git(*args: str, wurzel: Path = WURZEL) -> str:
    erg = subprocess.run(["git", "-C", str(wurzel), *args], capture_output=True, check=True)
    return erg.stdout.decode("utf-8", "replace")


def aenderungen_lesen(status: str) -> list[Aenderung]:
    """Ausgabe von ``git status --porcelain=v1 -z -uall`` → Liste (bekannte zuerst, neue danach)."""
    teile = status.split("\0")
    ergebnis: list[Aenderung] = []
    i = 0
    while i < len(teile):
        eintrag = teile[i]
        i += 1
        if len(eintrag) < 4:
            continue
        xy, pfad = eintrag[:2], eintrag[3:]
        if "R" in xy:
            i += 1                                   # alter Name folgt als eigener Eintrag
            ergebnis.append(Aenderung(pfad, "umbenannt", True))
        elif xy == "??":
            hinweis = "neu – Lizenz geklärt?" if Path(pfad).suffix.lower() in MEDIEN else "neu"
            ergebnis.append(Aenderung(pfad, "neu", False, hinweis))
        elif "D" in xy:
            ergebnis.append(Aenderung(pfad, "gelöscht", True))
        else:
            ergebnis.append(Aenderung(pfad, "geändert", True))
    return sorted(ergebnis, key=lambda a: (a.art == "neu", a.pfad))


def aenderungen(wurzel: Path = WURZEL) -> list[Aenderung]:
    return aenderungen_lesen(_git("status", "--porcelain=v1", "-z", "-uall", wurzel=wurzel))


def version_lesen(wurzel: Path = WURZEL) -> str:
    m = re.search(r'^version = "([^"]+)"', (wurzel / "pyproject.toml").read_text(encoding="utf-8"), re.M)
    if not m:
        raise ValueError("Version in pyproject.toml nicht gefunden")
    return m.group(1)


def naechste_version(version: str, art: str) -> str:
    a, b, c = (int(x) for x in version.split("-")[0].split("."))
    if art == "major":
        return f"{a + 1}.0.0"
    if art == "minor":
        return f"{a}.{b + 1}.0"
    return f"{a}.{b}.{c + 1}"


def changelog_einfuegen(text: str, version: str, tag: date, punkte: list[str]) -> str:
    """Neuen Abschnitt vor den ersten ``## [`` setzen."""
    abschnitt = f"## [{version}] – {tag.isoformat()}\n\n" + "".join(f"- {p}\n" for p in punkte) + "\n"
    i = text.find("\n## [")
    if i < 0:
        return text.rstrip("\n") + "\n\n" + abschnitt
    return text[:i + 1] + abschnitt + text[i + 1:]


def version_schreiben(wurzel: Path, version: str, punkte: list[str], tag: date | None = None) -> None:
    """pyproject.toml, __init__.py und CHANGELOG.md auf die neue Version setzen (UTF-8 ohne BOM)."""
    def ersetzen(rel: str, muster: str, neu: str) -> None:
        p = wurzel / rel
        t = p.read_text(encoding="utf-8")
        t2, n = re.subn(muster, neu, t, count=1, flags=re.M)
        if n != 1:
            raise ValueError(f"Version in {rel} nicht gefunden")
        p.write_bytes(t2.encode("utf-8"))

    ersetzen("pyproject.toml", r'^version = "[^"]+"', f'version = "{version}"')
    ersetzen("src/dmnt_kobold/__init__.py", r'^__version__ = "[^"]+"', f'__version__ = "{version}"')
    cl = wurzel / "CHANGELOG.md"
    alt = cl.read_text(encoding="utf-8") if cl.exists() else "# Änderungen\n"
    cl.write_bytes(changelog_einfuegen(alt, version, tag or date.today(), punkte).encode("utf-8"))


def punkte_lesen(text: str) -> list[str]:
    return [z.strip().lstrip("-•* ").strip() for z in text.splitlines() if z.strip().lstrip("-•* ").strip()]


def schritte(dateien: list[str], version: str | None, punkte: list[str]) -> list[tuple[str, list[str]]]:
    """Die Befehle in Reihenfolge: (Titel, argv). ``version`` None = nur hochladen."""
    titel = punkte[0] if punkte else "Änderungen"
    nachricht = (f"Version {version}: " if version else "") + titel
    liste: list[tuple[str, list[str]]] = [
        ("Tests", [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider"])]
    if version:
        liste.append(("Version setzen", ["@version"]))         # erledigt das Programm selbst
    zu_adden = list(dateien) + (list(VERSIONSDATEIEN) if version else [])
    if zu_adden:
        liste.append(("Dateien vormerken", ["git", "add", "-A", "--", *zu_adden]))
    # nur die angehakten Dateien – was sonst schon vorgemerkt ist, bleibt außen vor
    liste += [("Commit", ["git", "commit", "-m", nachricht, "--", *zu_adden]),
              ("Hochladen", ["git", "push", "origin", "HEAD:main"])]
    if version:
        liste += [("Version markieren", ["git", "tag", "-a", f"v{version}", "-m", f"DMNT-Kobold {version}"]),
                  ("Version veröffentlichen", ["git", "push", "origin", f"v{version}"])]
    return liste


# --- Fenster --------------------------------------------------------------------------------

class VeroeffentlichenDialog(QDialog):
    def __init__(self, parent=None, wurzel: Path = WURZEL) -> None:
        super().__init__(parent)
        self.wurzel = wurzel
        self.setWindowTitle("Veröffentlichen")
        self.resize(800, 740)
        self.version_alt = version_lesen(wurzel)
        self.aenderungen: list[Aenderung] = []
        self._liste: list[tuple[str, list[str]]] = []
        self._i = 0
        self._proz: QProcess | None = None
        self._laeuft = False
        self._neue_version: str | None = None
        self._punkte: list[str] = []

        lay = QVBoxLayout(self)
        erkl = QLabel("Angehakte Dateien gehen nach GitHub. Mit „neue Version“ baut GitHub danach automatisch "
                      "Setup und Release, und installierte Kobolde melden sich per Sprechblase. Neue Dateien "
                      "sind nicht vorausgewählt – Bilder und Töne nur anhaken, wenn ihre Lizenz das erlaubt.")
        erkl.setWordWrap(True)
        lay.addWidget(erkl)

        self.liste = QListWidget()
        self.liste.itemChanged.connect(lambda _it: self._bereit())
        lay.addWidget(self.liste, 2)
        knoepfe = QHBoxLayout()
        for text, wert in (("Alle neuen anhaken", True), ("Keine neuen", False)):
            b = QPushButton(text)
            b.clicked.connect(lambda _=False, w=wert: self._neue_setzen(w))
            knoepfe.addWidget(b)
        knoepfe.addStretch(1)
        self.anzahl = QLabel()
        knoepfe.addWidget(self.anzahl)
        lay.addLayout(knoepfe)

        zeile = QHBoxLayout()
        self.mit_version = QCheckBox("Als neue Version veröffentlichen")
        self.mit_version.setChecked(True)
        self.mit_version.toggled.connect(self._version_anzeigen)
        zeile.addWidget(self.mit_version)
        self.art = QComboBox()
        for schluessel, text in ARTEN:
            self.art.addItem(f"{text}: {naechste_version(self.version_alt, schluessel)}", schluessel)
        zeile.addWidget(self.art, 1)
        lay.addLayout(zeile)
        jetzt = QLabel(f"Jetzt: {self.version_alt}")
        jetzt.setObjectName("neben")
        lay.addWidget(jetzt)

        lay.addWidget(QLabel("Was ist neu? (eine Zeile je Punkt – steht im Release und in CHANGELOG.md)"))
        self.neu = QPlainTextEdit()
        self.neu.setPlaceholderText("Hexe hat jetzt ihre 5 Minuten: flitzt los, schlägt Haken, springt")
        self.neu.setFixedHeight(90)
        self.neu.textChanged.connect(self._bereit)
        lay.addWidget(self.neu)

        self.protokoll = QPlainTextEdit()
        self.protokoll.setReadOnly(True)
        self.protokoll.setStyleSheet(f"background: white; color: {stil.TEXT}; font-family: Consolas, monospace;"
                                     " font-size: 12px;")
        lay.addWidget(self.protokoll, 1)

        unten = QHBoxLayout()
        self.ansehen = QPushButton("Fortschritt auf GitHub ansehen")
        self.ansehen.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(ACTIONS_URL)))
        self.ansehen.hide()
        unten.addWidget(self.ansehen)
        unten.addStretch(1)
        self.los = QPushButton("Veröffentlichen")
        self.los.setObjectName("haupt")
        self.los.clicked.connect(self.starten)
        unten.addWidget(self.los)
        self.zu = QPushButton("Schließen")
        self.zu.clicked.connect(self.reject)
        unten.addWidget(self.zu)
        lay.addLayout(unten)

        self._laden()

    # --- Auswahl ----------------------------------------------------------------------
    def _laden(self) -> None:
        self.liste.blockSignals(True)
        self.liste.clear()
        try:
            self.aenderungen = aenderungen(self.wurzel)
        except (OSError, subprocess.CalledProcessError) as e:
            self.aenderungen = []
            self._log(f"git nicht erreichbar: {e}")
        for a in self.aenderungen:
            zusatz = f"   ({a.hinweis})" if a.art == "neu" and a.hinweis else ""
            it = QListWidgetItem(f"{a.art:<10} {a.pfad}{zusatz}")
            it.setFlags(it.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            it.setCheckState(Qt.CheckState.Checked if a.vorauswahl else Qt.CheckState.Unchecked)
            self.liste.addItem(it)
        self.liste.blockSignals(False)
        if not self.aenderungen:
            self._log("Keine geänderten Dateien – mit „neue Version“ lässt sich trotzdem ein Release anstoßen.")
        self._version_anzeigen()

    def _neue_setzen(self, an: bool) -> None:
        for i, a in enumerate(self.aenderungen):
            if a.art == "neu":
                self.liste.item(i).setCheckState(Qt.CheckState.Checked if an else Qt.CheckState.Unchecked)

    def gewaehlt(self) -> list[str]:
        return [a.pfad for i, a in enumerate(self.aenderungen)
                if self.liste.item(i).checkState() == Qt.CheckState.Checked]

    def _version_anzeigen(self) -> None:
        self.art.setEnabled(self.mit_version.isChecked() and not self._laeuft)
        self._bereit()

    def _bereit(self) -> None:
        n = len(self.gewaehlt())
        self.anzahl.setText(f"{n} von {len(self.aenderungen)} Dateien ausgewählt")
        ok = bool(punkte_lesen(self.neu.toPlainText())) and (n > 0 or self.mit_version.isChecked())
        self.los.setEnabled(ok and not self._laeuft)

    def _bedienbar(self, an: bool) -> None:
        for w in (self.liste, self.mit_version, self.neu):
            w.setEnabled(an)
        self._version_anzeigen()

    # --- Ablauf -------------------------------------------------------------------------
    def starten(self) -> None:
        self._punkte = punkte_lesen(self.neu.toPlainText())
        self._neue_version = (naechste_version(self.version_alt, self.art.currentData())
                              if self.mit_version.isChecked() else None)
        dateien = self.gewaehlt()
        self._liste = schritte(dateien, self._neue_version, self._punkte)
        self._i = 0
        self._laeuft = True
        self._bedienbar(False)
        self.protokoll.clear()
        ziel = f"Version {self._neue_version}" if self._neue_version else "nur hochladen"
        self._log(f"Veröffentlichen ({ziel}), {len(dateien)} Dateien")
        self._naechster()

    def _log(self, text: str) -> None:
        self.protokoll.appendPlainText(text)

    def _naechster(self) -> None:
        if self._i >= len(self._liste):
            self._fertig()
            return
        titel, argv = self._liste[self._i]
        self._log(f"\n▶ {titel}")
        if argv == ["@version"]:
            try:
                version_schreiben(self.wurzel, self._neue_version, self._punkte)
            except (OSError, ValueError) as e:
                self._fehler(f"Version setzen: {e}")
                return
            self._log(f"  {self.version_alt} → {self._neue_version}, CHANGELOG ergänzt")
            self._i += 1
            self._naechster()
            return
        p = QProcess(self)
        p.setWorkingDirectory(str(self.wurzel))
        umgebung = QProcessEnvironment.systemEnvironment()
        umgebung.insert("QT_QPA_PLATFORM", "offscreen")
        umgebung.insert("PYTHONIOENCODING", "utf-8")
        p.setProcessEnvironment(umgebung)
        p.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        p.readyReadStandardOutput.connect(lambda: self._ausgabe(p))
        p.finished.connect(lambda code, _s: self._beendet(code))
        p.errorOccurred.connect(lambda _e: self._beendet(-1) if self._proz is p else None)
        self._proz = p
        p.start(argv[0], argv[1:])

    def _ausgabe(self, p: QProcess) -> None:
        text = bytes(p.readAllStandardOutput().data()).decode("utf-8", "replace").rstrip()
        zeilen = text.splitlines()
        if self._liste[self._i][0] == "Tests":          # nur das Wesentliche, keine Punkte-Zeilen
            zeilen = [z for z in zeilen if z.strip() and not set(z.strip()) <= set(".[]%0123456789 sF")][-30:]
        if zeilen:
            self._log("\n".join("  " + z for z in zeilen))

    def _beendet(self, code: int) -> None:
        if self._proz is None:
            return
        self._proz = None
        if code != 0:
            self._fehler(f"{self._liste[self._i][0]} fehlgeschlagen (Code {code})")
            return
        self._i += 1
        self._naechster()

    def _fehler(self, text: str) -> None:
        erledigt = [t for t, _ in self._liste[:self._i]]
        self._log(f"\n✗ {text}")
        if "Commit" not in erledigt and "Version setzen" in erledigt:
            # Version zurücknehmen – es wurde noch nichts committet und nichts hochgeladen
            subprocess.run(["git", "-C", str(self.wurzel), "reset", "-q", "--", *VERSIONSDATEIEN],
                           capture_output=True)
            subprocess.run(["git", "-C", str(self.wurzel), "checkout", "--", *VERSIONSDATEIEN],
                           capture_output=True)
            self._log("  Version und CHANGELOG zurückgesetzt – es wurde nichts hochgeladen.")
        elif "Commit" in erledigt:
            self._log("  Der Commit liegt lokal. Internetverbindung prüfen und Claude Bescheid sagen "
                      "(oder im Repo-Ordner: git push origin main --follow-tags).")
        else:
            self._log("  Es wurde nichts verändert und nichts hochgeladen.")
        self._laeuft = False
        self._bedienbar(True)

    def _fertig(self) -> None:
        self._laeuft = False
        if self._neue_version:
            self._log(f"\n✓ Version {self._neue_version} ist unterwegs. GitHub baut jetzt Setup und Release "
                      "(ca. 5 Minuten). Installierte Kobolde melden sich innerhalb eines Tages.")
        else:
            self._log("\n✓ Hochgeladen.")
        self.ansehen.show()
        self.zu.setText("Fertig")

    def reject(self) -> None:                          # während des Ablaufs nicht schließen
        if self._laeuft:
            self._log("  Bitte warten, bis der Ablauf fertig ist.")
            return
        super().reject()


def oeffnen(parent=None) -> None:
    VeroeffentlichenDialog(parent).exec()
