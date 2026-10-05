"""Avatar-Editor, Reiter „Herkunft & Töne“: Hintergrund und Töne setzen, Bauplan bleibt gültig."""
import shutil
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "werkzeuge"))

from avatar_editor import Projekt  # noqa: E402
from editor_herkunft import (HerkunftToeneTab, herkunft_entfernen, herkunft_setzen,  # noqa: E402
                             ton_einstellen, ton_entfernen, ton_hinzufuegen)

from dmnt_kobold import katalog  # noqa: E402


def _projekt(tmp_path, avatar="kiesel"):
    ordner = tmp_path / avatar
    shutil.copytree(WURZEL / "quellen" / avatar, ordner, ignore=shutil.ignore_patterns("_alt"))
    return Projekt(ordner)


def _gueltig(pr):
    fehler, _ = katalog.koerper_pruefen(pr.bauplan, pr.ordner)
    assert fehler == []


def test_herkunft_setzen_und_entfernen(tmp_path):
    pr = _projekt(tmp_path, "dmnt9000")
    assert pr.bauplan["herkunft"].get("ebenen")
    bild = tmp_path / "wiese.jpg"
    shutil.copy(WURZEL / "quellen" / "dmnt9000" / "herkunft_asteroiden.jpg", bild)
    name = herkunft_setzen(pr, bild)
    assert name == "herkunft.jpg" and (pr.ordner / name).exists()
    neu = Projekt(pr.ordner).bauplan["herkunft"]
    assert neu["hintergrund"] == "herkunft.jpg" and "ebenen" not in neu       # gespeichert, Ebenen weg
    assert any((pr.ordner / "_alt").iterdir())                                 # altes Bild gesichert
    herkunft_entfernen(pr)
    assert "herkunft" not in Projekt(pr.ordner).bauplan


def test_toene_hinzufuegen_einstellen_entfernen(tmp_path):
    pr = _projekt(tmp_path)
    ton = pr.ordner / "toene" / "plopp.ogg"
    neu = tmp_path / "plopp.ogg"
    shutil.copy(ton, neu)
    rel = ton_hinzufuegen(pr, "landen", neu)
    assert rel == "toene/plopp_2.ogg"                                          # gleicher Name → nicht überschrieben
    assert Projekt(pr.ordner).bauplan["toene"]["landen"]["dateien"] == ["toene/platsch.ogg", rel]
    ton_einstellen(pr, "landen", tonhoehe=0.9, wiederholen=(3, 2))
    t = pr.bauplan["toene"]["landen"]
    assert t["tonhoehe"] == 0.5 and t["wiederholen"] == [2, 3]
    _gueltig(pr)
    ton_hinzufuegen(pr, "erschrecken", neu)                                    # neuer Moment
    _gueltig(pr)
    for d in list(pr.bauplan["toene"]["landen"]["dateien"]):
        ton_entfernen(pr, "landen", d)
    assert "landen" not in Projekt(pr.ordner).bauplan["toene"]                # leerer Moment fällt weg
    _gueltig(pr)


def test_synthetischer_ton_wird_durch_datei_ersetzt(tmp_path):
    pr = _projekt(tmp_path, "dmnt9000")
    assert "segmente" in pr.bauplan["toene"]["sprechen"]
    neu = tmp_path / "pieps.wav"
    from dmnt_kobold.toene import schreibe_wav, synthese
    schreibe_wav(neu, synthese([(880, 880, 0.05)], 0.5))
    ton_hinzufuegen(pr, "sprechen", neu)
    t = pr.bauplan["toene"]["sprechen"]
    assert "segmente" not in t and t["dateien"] == ["toene/pieps.wav"]
    _gueltig(pr)


def test_reiter_baut_auf(tmp_path, qapp):
    pr = _projekt(tmp_path)

    class Editor:
        projekt = pr
        meldungen: list = []

        def meldung(self, t):
            self.meldungen.append(t)

        def geaendert(self, neu_aufbauen=False):
            pass

    tab = HerkunftToeneTab(Editor())
    tab.aufbauen()
    from PySide6.QtWidgets import QLabel
    namen = {w.text() for w in tab.bereich.widget().findChildren(QLabel)}
    assert {"Herkunft", "Töne des Körpers", "landen", "sprechen", "plopp.ogg"} <= namen
