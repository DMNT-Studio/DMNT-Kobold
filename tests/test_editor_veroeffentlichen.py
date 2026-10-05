"""Avatar-Editor: Veröffentlichen (Auswahl, Version, CHANGELOG, Befehlsfolge)."""
import shutil
import sys
from datetime import date
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "werkzeuge"))

from editor_veroeffentlichen import (VERSIONSDATEIEN, VeroeffentlichenDialog, aenderungen_lesen,  # noqa: E402
                                     changelog_einfuegen, naechste_version, punkte_lesen, schritte,
                                     version_lesen, version_schreiben)


def test_status_lesen_neue_nicht_vorausgewaehlt():
    status = "\0".join([" M src/a.py", "?? quellen/hexe/toene/miau.mp3", "?? notiz.txt", " D alt.wav",
                        "R  neu.py", "alt.py", ""])
    liste = aenderungen_lesen(status)
    art = {a.pfad: a for a in liste}
    assert art["src/a.py"].vorauswahl and art["alt.wav"].art == "gelöscht" and art["neu.py"].art == "umbenannt"
    assert "alt.py" not in art
    assert not art["quellen/hexe/toene/miau.mp3"].vorauswahl and "Lizenz" in art["quellen/hexe/toene/miau.mp3"].hinweis
    assert art["notiz.txt"].hinweis == "neu"
    assert [a.art for a in liste][-1] == "neu"                     # neue stehen unten


def test_naechste_version():
    assert naechste_version("0.7.0", "patch") == "0.7.1"
    assert naechste_version("0.7.3", "minor") == "0.8.0"
    assert naechste_version("0.9.2", "major") == "1.0.0"
    assert naechste_version("0.7.1-test.2", "patch") == "0.7.2"


def test_changelog_neuer_abschnitt_oben():
    alt = "# Änderungen\n\nText.\n\n## [0.7.0] – 2026-10-05\n\n- alt\n"
    neu = changelog_einfuegen(alt, "0.7.1", date(2026, 10, 6), ["Hexe flitzt", "Effekte"])
    assert neu.index("## [0.7.1] – 2026-10-06") < neu.index("## [0.7.0]")
    assert "- Hexe flitzt\n- Effekte\n" in neu and neu.startswith("# Änderungen")


def test_version_schreiben_alle_drei_dateien(tmp_path):
    for rel in VERSIONSDATEIEN:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(WURZEL / rel, tmp_path / rel)
    version_schreiben(tmp_path, "9.8.7", ["Probe"], date(2026, 1, 2))
    assert version_lesen(tmp_path) == "9.8.7"
    assert '__version__ = "9.8.7"' in (tmp_path / "src/dmnt_kobold/__init__.py").read_text(encoding="utf-8")
    assert "## [9.8.7] – 2026-01-02" in (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert not (tmp_path / "pyproject.toml").read_bytes().startswith(b"\xef\xbb\xbf")   # ohne BOM


def test_punkte_lesen():
    assert punkte_lesen("- eins\n\n• zwei\n  * drei  \n") == ["eins", "zwei", "drei"]


def test_schritte_mit_und_ohne_version():
    mit = schritte(["a.py"], "0.7.1", ["Neu"])
    titel = [t for t, _ in mit]
    assert titel == ["Tests", "Version setzen", "Dateien vormerken", "Commit", "Hochladen",
                     "Version markieren", "Version veröffentlichen"]
    commit = dict(mit)["Commit"]
    assert commit[:4] == ["git", "commit", "-m", "Version 0.7.1: Neu"]
    assert commit[commit.index("--") + 1:] == ["a.py", *VERSIONSDATEIEN]     # nur Ausgewähltes
    assert dict(mit)["Version veröffentlichen"] == ["git", "push", "origin", "v0.7.1"]
    ohne = [t for t, _ in schritte(["a.py"], None, ["Fix"])]
    assert ohne == ["Tests", "Dateien vormerken", "Commit", "Hochladen"]


def test_dialog_oeffnet_mit_repo(qapp):
    d = VeroeffentlichenDialog(None)
    assert d.version_alt == version_lesen()
    assert d.art.count() == 3 and not d.los.isEnabled()              # ohne „Was ist neu“ kein Start
    d.neu.setPlainText("Probe")
    assert d.los.isEnabled()
    d._laeuft = False
    d.close()
