import json
import zipfile
from datetime import date, timedelta

import pytest

from dmnt_kobold.daten import Datenablage, Sicherung, Speicher, atomar_schreiben, json_laden


def test_speicher_schreibt_sofort_und_liest_neu(tmp_path):
    s = Speicher(tmp_path / "a.json")
    s["liste"] = [1, 2]
    assert json.loads((tmp_path / "a.json").read_text(encoding="utf-8")) == {"liste": [1, 2]}
    assert Speicher(tmp_path / "a.json").get("liste") == [1, 2]


def test_kaputte_datei_nimmt_bak(tmp_path):
    p = tmp_path / "a.json"
    s = Speicher(p)
    s["x"] = 1
    s["x"] = 2                      # jetzt gibt es a.json.bak mit x=1
    p.write_text("{kaputt", encoding="utf-8")
    assert json_laden(p) == {"x": 1}


def test_abbruch_beim_schreiben_laesst_alte_datei_heil(tmp_path, monkeypatch):
    p = tmp_path / "a.json"
    atomar_schreiben(p, b'{"x": 1}')

    import os

    def kaputt(*_a, **_k):
        raise OSError("Platte voll")
    monkeypatch.setattr(os, "replace", kaputt)
    with pytest.raises(OSError):
        atomar_schreiben(p, b'{"x": 2}')
    monkeypatch.undo()
    assert json_laden(p) == {"x": 1}
    assert not list(tmp_path.glob("*.tmp"))


def test_taegliche_sicherung_behaelt_sieben(tmp_path):
    ablage = Datenablage(tmp_path)
    ablage.speicher("einstellungen")["name"] = "Hugo"
    tag = [date(2026, 10, 1)]
    sich = Sicherung(ablage, heute=lambda: tag[0])
    for i in range(10):
        tag[0] = date(2026, 10, 1) + timedelta(days=i)
        assert sich.taeglich() is not None
        assert sich.taeglich() is None            # gleicher Tag: nichts Neues
    namen = sorted(p.name for p in ablage.sicherungen.glob("*.zip"))
    assert len(namen) == 7 and namen[0] == "2026-10-04.zip"
    with zipfile.ZipFile(ablage.sicherungen / namen[-1]) as z:
        assert "daten/einstellungen.json" in z.namelist()


def test_export_import_rundreise(tmp_path):
    ablage = Datenablage(tmp_path / "a")
    s = ablage.speicher("trick_erinnern")
    s["liste"] = [{"id": "1"}]
    sich = Sicherung(ablage)
    sich.exportieren(tmp_path / "export.zip")
    s["liste"] = []
    sich.importieren(tmp_path / "export.zip")
    assert s.get("liste") == [{"id": "1"}]          # gleiches Objekt, frisch geladen
    assert list(ablage.sicherungen.glob("vor-import-*.zip"))


def test_import_lehnt_fremde_zip_ab(tmp_path):
    ablage = Datenablage(tmp_path / "a")
    z = tmp_path / "boese.zip"
    with zipfile.ZipFile(z, "w") as f:
        f.writestr("dmnt-kobold-sicherung.json", "{}")
        f.writestr("../ausbruch.txt", "x")
    with pytest.raises(ValueError):
        Sicherung(ablage).importieren(z)
