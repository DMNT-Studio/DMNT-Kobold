"""DMNT 9000 3D: Raster-Bögen mit festem Maßstab und Fußpunkt, gebauter Avatar."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "werkzeuge"))
import avatar_bauen as ab  # noqa: E402

GEBAUT = WURZEL / "src" / "dmnt_kobold" / "avatare" / "dmnt9000_3d"


def _figur(w: int, h: int, x: int) -> np.ndarray:
    """Weißer Körper mit rotem Auge, Füße 10 px über dem Zellenboden."""
    a = np.zeros((h, w, 4), np.uint8)
    a[20:h - 10, x - 20:x + 20] = (240, 240, 240, 255)
    yy, xx = np.mgrid[0:h, 0:w]
    a[(xx - x) ** 2 + (yy - 40) ** 2 < 64] = (220, 30, 30, 255)
    return a


def test_raster_anker_folgt_der_figur():
    bogen = np.concatenate([_figur(100, 120, 50), _figur(100, 120, 60)], axis=1)
    (_, (ax0, ay0)), (_, (ax1, ay1)) = ab.raster_zerlegen(bogen, 2, (50, 110))
    assert round(ax0 - ax1) == 10            # Figur 10 px weiter rechts → Anker 10 px weiter links in der Pose
    assert ay0 == ay1


def test_raster_braucht_gleiche_zellen():
    with pytest.raises(ab.BauFehler):
        ab.raster_zerlegen(np.zeros((10, 101, 4), np.uint8), 2)


def test_raster_ohne_festen_massstab_bricht_ab(tmp_path):
    Image.fromarray(np.concatenate([_figur(100, 120, 50)] * 2, axis=1), "RGBA").save(tmp_path / "a.png")
    plan = {"hoehe": 50, "referenz": ["a", 0],
            "quellen": {"a": {"datei": "a.png", "bilder": 2, "raster": True}}}
    with pytest.raises(ab.BauFehler):
        ab.auge_posen(tmp_path, plan, 2)


def test_fester_massstab_gleich_fuer_alle_bilder(tmp_path):
    Image.fromarray(np.concatenate([_figur(100, 120, 50), _figur(100, 120, 60)], axis=1), "RGBA").save(tmp_path / "a.png")
    plan = {"hoehe": 50, "referenz": ["a", 0],
            "quellen": {"a": {"datei": "a.png", "bilder": 2, "raster": True, "massstab": "fest", "fusspunkt": [50, 110]}}}
    skaliert, anker, _, _ = ab.auge_posen(tmp_path, plan, 2)
    p0, p1 = skaliert["a"]
    assert p0.shape == p1.shape                       # gleicher Faktor, keine Augen-Schwankung
    assert p0.shape[0] == 100                         # Referenz auf hoehe × skalierung
    f = 100 / 94
    assert anker[("a", 0)][0] - anker[("a", 1)][0] == pytest.approx(10 * f, abs=0.6)


@pytest.mark.skipif(not (GEBAUT / "avatar.json").exists(), reason="dmnt9000_3d noch nicht gebaut")
def test_gebauter_avatar_hat_8_bilder_je_bewegung():
    a = json.loads((GEBAUT / "avatar.json").read_text(encoding="utf-8"))
    for name in ("ruhe", "ruhe~2", "bewegen", "bewegen~2", "freuen", "unzufrieden", "fallen", "schlafen"):
        assert len(a["animationen"][name]["bilder"]) == 8, name
    groessen = {Image.open(GEBAUT / b).size for anim in a["animationen"].values() for b in anim["bilder"]}
    assert len(groessen) == 1                         # gemeinsame Leinwand
