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
