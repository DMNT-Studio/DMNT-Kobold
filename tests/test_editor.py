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
