"""Avatar-Editor: Datenmodell (ohne Fenster)."""
import json
import shutil
import sys
from pathlib import Path

import pytest

pytest.importorskip("PIL")
WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "werkzeuge"))


@pytest.fixture
def projekt(tmp_path, qapp):
    import avatar_editor as ae

    ziel = tmp_path / "dmnt9000"
    shutil.copytree(WURZEL / "quellen" / "dmnt9000", ziel)
    return ae.Projekt(ziel)


def test_benutzt_und_posen(projekt):
    assert "seite:0" in projekt.posen()
    assert any(b.startswith("ruhe") for b in projekt.benutzt("seite:0"))


def test_ersetzen_im_bogen_loest_pose_heraus(projekt, tmp_path):
    from PIL import Image

    neu = tmp_path / "neu.png"
    Image.new("RGBA", (50, 80), (0, 0, 0, 0)).save(neu)
    projekt.zubehoer.setdefault("kopfhoerer", {}).setdefault("posen", {})["gehen4:1"] = {"x": 1}
    s = projekt.ersetzen("gehen4:1", neu)
    assert s == "gehen4_2:0"
    plan = json.loads((projekt.ordner / "bauplan.json").read_text(encoding="utf-8"))
    assert plan["quellen"]["gehen4_2"]["datei"] == "gehen4_2.png"
    assert ["gehen4_2", 0, "normal"] in plan["animationen"]["bewegen"]["bilder"]
    assert "gehen4_2:0" in projekt.zubehoer["kopfhoerer"]["posen"]


def test_ersetzen_einzelbild_sichert_altes(projekt, tmp_path):
    from PIL import Image

    neu = tmp_path / "neu.png"
    Image.new("RGB", (40, 40), (0, 0, 0)).save(neu)
    assert projekt.ersetzen("seite:0", neu) == "seite:0"
    assert list((projekt.ordner / "_alt").glob("seite_*.png"))
    assert projekt.bauplan["quellen"]["seite"]["hintergrund"] == "schwarz"


def test_drei_wege_behaelt_fremde_aenderungen():
    import avatar_editor as ae

    basis = {"zylinder": {"posen": {"a": {"x": 1}}}, "monokel": {"posen": {}}}
    mein = {"zylinder": {"posen": {"a": {"x": 1}, "b": {"x": 2}}}, "monokel": {"posen": {}}}
    platte = {"zylinder": {"posen": {"a": {"x": 5}}}, "monokel": {"posen": {"c": {"y": 3}}}, "neu": {}}
    e = ae.drei_wege(basis, mein, platte)
    assert e["zylinder"]["posen"] == {"a": {"x": 5}, "b": {"x": 2}}
    assert e["monokel"]["posen"] == {"c": {"y": 3}} and "neu" in e


def test_zwei_editoren_ueberschreiben_sich_nicht(projekt):
    import avatar_editor as ae

    zweiter = ae.Projekt(projekt.ordner)
    projekt.zubehoer["zylinder"]["posen"]["seite:0"] = {"x": 1.0}
    projekt.zubehoer_speichern()
    zweiter.zubehoer["zylinder"]["posen"]["front:0"] = {"x": 2.0}
    zweiter.zubehoer_speichern()                 # kennt seite:0 nicht – darf es aber nicht löschen
    dritter = ae.Projekt(projekt.ordner)
    assert set(dritter.zubehoer["zylinder"]["posen"]) >= {"seite:0", "front:0"}
    assert list((projekt.ordner / "_alt" / "verlauf").glob("zubehoer_*.json"))


def test_von_aussen_geaendert(projekt):
    import json

    z = json.loads((projekt.ordner / "zubehoer.json").read_text(encoding="utf-8"))
    z["zylinder"]["posen"]["fallen:0"] = {"winkel": -20}
    (projekt.ordner / "zubehoer.json").write_text(json.dumps(z), encoding="utf-8")
    assert projekt.von_aussen_geaendert("zubehoer")
    assert projekt.zubehoer["zylinder"]["posen"]["fallen:0"] == {"winkel": -20}


# --- Reiter „Verhalten“ ----------------------------------------------------------

def test_sonderlogik_wird_gelesen_nicht_ausgefuehrt(tmp_path):
    import editor_verhalten as ev

    datei = tmp_path / "persoenlichkeit.py"
    assert ev.sonderlogik_lesen(datei) is None
    datei.write_text('raise SystemExit("darf nie laufen")\n'
                     'class Persoenlichkeit:\n'
                     '    SONDERLOGIK = [("Wetter", "schaut aufs Wetter")]\n', encoding="utf-8")
    assert ev.sonderlogik_lesen(datei) == [("Wetter", "schaut aufs Wetter")]
    datei.write_text('class Persoenlichkeit:\n    """Zählt Klicks.\n\n    Mehr."""\n', encoding="utf-8")
    assert ev.sonderlogik_lesen(datei) == [("Persoenlichkeit", "Zählt Klicks.")]


def test_umbenennen_zieht_verweise_mit():
    import editor_verhalten as ev
    from dmnt_kobold.regeln import standard_verhalten

    v = standard_verhalten()
    ev.umbenennen(v, "einschlafen", "dösen")
    r = {x["id"]: x for x in v["regeln"]}
    assert "dösen" in r and r["aufwachen"]["wenn"]["regel_laeuft"] == "dösen"
    assert r["aufwachen"]["dann"][0]["regeln"] == ["dösen"]
    ev.umbenennen(v, "pause", "frage")
    assert r["spaeter"]["wenn"]["regel"] == "frage"
    assert ev.neue_id("frage", set(r) | {"frage"}) == "frage_2"


def test_kurzform_wenn_dann():
    import editor_verhalten as ev
    from dmnt_kobold.regeln import standard_verhalten

    r = {x["id"]: x for x in standard_verhalten()["regeln"]}
    assert ev.kurz_wenn(r["minecraft"]).startswith("programm.aktiv (minecraft.exe")
    assert " oder " in ev.kurz_wenn(r["minecraft"])
    assert ev.kurz_dann(r["aufwachen"]) == "beendet einschlafen, freuen, Ton aufwachen"


def test_projekt_verhalten_laden_und_speichern(projekt):
    assert any(r["id"] == "minecraft" for r in projekt.verhalten["regeln"])
    projekt.verhalten["werte"]["einschlafen_nach_min"] = 8
    projekt.verhalten_speichern()
    gespeichert = json.loads((projekt.ordner / "verhalten.json").read_text(encoding="utf-8"))
    assert gespeichert["werte"]["einschlafen_nach_min"] == 8


def test_projekt_ohne_verhalten_zeigt_standard(projekt):
    import avatar_editor as ae

    (projekt.ordner / "verhalten.json").unlink()
    neu = ae.Projekt(projekt.ordner)
    assert [r["id"] for r in neu.verhalten["regeln"]][:2] == ["maus_nah", "maus_weg"]
    assert not (projekt.ordner / "verhalten.json").exists()       # nur ansehen schreibt nichts
