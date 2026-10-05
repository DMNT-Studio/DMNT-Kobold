"""Avatar-Editor: Töne und Verhalten zurücksetzen (Repo-Stand, Standard, Verlauf)."""
import json
import shutil
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "werkzeuge"))

from avatar_editor import Projekt  # noqa: E402
from editor_herkunft import ton_entfernen  # noqa: E402
from editor_zuruecksetzen import (ZuruecksetzenDialog, aktuell, repo_stand, staende,  # noqa: E402
                                  unterschied, verlauf_staende, zuruecksetzen, zusammenfassung)


def _projekt(tmp_path, avatar="kiesel"):
    ordner = tmp_path / avatar
    shutil.copytree(WURZEL / "quellen" / avatar, ordner, ignore=shutil.ignore_patterns("_alt"))
    return Projekt(ordner)


def test_toene_aus_verlauf_zurueck(tmp_path):
    pr = _projekt(tmp_path)
    vorher = aktuell(pr, "toene")
    moment = next(iter(vorher))
    for d in list(vorher[moment].get("dateien", [])) or [None]:     # wie im Editor, Datei für Datei
        ton_entfernen(pr, moment, d)
    assert moment not in aktuell(pr, "toene")
    liste = staende(pr, "toene")
    assert liste and liste[0].name == "Verlauf"                      # neueste Fassung zuerst
    original = next(s for s in liste if s.daten == vorher)           # der Stand vor allen Änderungen
    liste[0] = original
    assert "kommt zurück: " + moment in unterschied("toene", aktuell(pr, "toene"), liste[0].daten)
    zuruecksetzen(pr, "toene", liste[0])
    assert Projekt(pr.ordner).bauplan["toene"] == vorher           # gespeichert
    # der kaputte Stand liegt jetzt selbst im Verlauf
    assert any(moment not in s.daten for s in verlauf_staende(pr, "toene"))


def test_toene_zuruecksetzen_laesst_rest_des_bauplans(tmp_path):
    pr = _projekt(tmp_path)
    pr.bauplan["skalierung"] = 3
    pr.bauplan["toene"] = {}
    pr.bauplan_speichern()
    zuruecksetzen(pr, "toene", verlauf_staende(pr, "toene")[0])
    neu = Projekt(pr.ordner).bauplan
    assert neu["skalierung"] == 3 and neu["toene"]


def test_verhalten_zurueck_auf_standard_und_verlauf(tmp_path):
    pr = _projekt(tmp_path)
    vorher = aktuell(pr, "verhalten")
    pr.verhalten["regeln"] = []
    pr.verhalten["werte"] = {"laufgeschwindigkeit": 99}
    pr.verhalten_speichern()
    namen = [s.name for s in staende(pr, "verhalten")]
    assert "Standard-Verhalten des Sockels" in namen and "Verlauf" in namen
    alt = next(s for s in staende(pr, "verhalten") if s.name == "Verlauf")
    assert alt.daten == vorher
    zuruecksetzen(pr, "verhalten", alt)
    gespeichert = json.loads((pr.ordner / "verhalten.json").read_text(encoding="utf-8"))
    assert gespeichert["regeln"] == vorher["regeln"] and gespeichert["werte"] == vorher["werte"]


def test_aktueller_stand_wird_nicht_angeboten(tmp_path):
    pr = _projekt(tmp_path)
    jetzt = aktuell(pr, "toene")
    assert all(s.daten != jetzt for s in staende(pr, "toene"))


def test_repo_stand_nur_im_repo(tmp_path):
    assert repo_stand(_projekt(tmp_path), "toene") is None           # Kopie liegt außerhalb des Repos
    echt = Projekt(WURZEL / "quellen" / "kiesel")                    # nur lesen
    s = repo_stand(echt, "toene")
    assert s is not None and s.daten and s.zeit


def test_zusammenfassung_lesbar():
    assert zusammenfassung("toene", {}) == "keine Töne"
    t = zusammenfassung("toene", {"landen": {"dateien": ["toene/platsch.ogg"]}, "sprechen": {"segmente": []}})
    assert "landen: platsch.ogg" in t and "sprechen (eingebaut)" in t
    assert zusammenfassung("verhalten", {"regeln": [{"id": "a"}], "werte": {}}).startswith("1 Regeln")


def test_dialog_zeigt_staende(tmp_path, qapp):
    pr = _projekt(tmp_path)
    pr.bauplan["toene"] = {}
    pr.bauplan_speichern()
    d = ZuruecksetzenDialog(None, pr, "toene")
    assert d.liste.count() >= 1 and d.ok.isEnabled() and d.gewaehlt is not None
    assert "kommt zurück" in d.vorschau.text()
