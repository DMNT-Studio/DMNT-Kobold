"""Nachhüpfen: Hüpf-Avatare federn nach einer Landung wie ein Ball nach (Wert ``nachhuepfen``)."""
from __future__ import annotations

import math

import pytest

from dmnt_kobold import katalog
from dmnt_kobold.bus import Ereignis, EventBus
from dmnt_kobold.monitore import Monitor, Rechteck
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.physik import NACHHUPF_MAX, STEHT, Koerper, nachhupf
from dmnt_kobold.regeln import RegelPersoenlichkeit

from test_huepfen import _Uhr, fenster, probe_gebaut  # noqa: F401  (Fixtures)

DT = 1 / 60


def mon(name, x, y, w, h, *, haupt=False):
    g = Rechteck(x, y, w, h)
    return Monitor(name, g, g, 1.0, haupt)


# --- Katalog --------------------------------------------------------------------------------

def test_katalog_wert_und_ereignis():
    d = katalog.WERT["nachhuepfen"]
    assert (d.standard, d.min, d.max) == (0.0, 0.0, 0.8)
    gelandet = next(e for e in katalog.EREIGNISSE if e.name == "avatar.gelandet")
    art = next(p for p in gelandet.bedingungen if p.name == "art")
    assert "nachhupf" in art.auswahl


def test_validierung_zu_gross():
    fehler, _ = katalog.pruefen({"werte": {"nachhuepfen": 0.9}})
    assert any("nachhuepfen" in f for f in fehler)
    assert katalog.pruefen({"werte": {"nachhuepfen": 0.45}}) == ([], [])


def test_standard_aus():
    assert katalog.Werte()["nachhuepfen"] == 0.0


# --- Physik ---------------------------------------------------------------------------------

def _folge(hoehe, weite, faktor):
    folge, schon = [], 0
    while (n := nachhupf(hoehe, weite, faktor, schon)) is not None:
        hoehe, weite = n
        folge.append(n)
        schon += 1
    return folge


def test_hoehenfolge_kiesel():
    folge = _folge(22, 30, 0.45)
    assert [round(h, 1) for h, _ in folge] == [9.9, 4.5]
    assert folge[0][1] == pytest.approx(30 * math.sqrt(0.45))
    assert folge[1][1] == pytest.approx(30 * 0.45)


def test_faktor_null_und_hoechstens_vier():
    assert nachhupf(22, 30, 0.0, 0) is None
    assert len(_folge(200, 30, 0.8)) == NACHHUPF_MAX


def test_nachhupfer_landet_exakt_auf_dem_boden():
    m = [mon("A", 0, 0, 1920, 1080, haupt=True)]
    k = Koerper(x=800, y=1080)
    h, w = nachhupf(22, 30, 0.45, 0)
    k.hupf_ab(w, h)
    for _ in range(300):
        k.schritt(DT, m)
        if k.zustand == STEHT:
            break
    assert k.zustand == STEHT and k.y == 1080 and k.landung[0] == "hupf"


# --- Regeln ---------------------------------------------------------------------------------

def test_regel_mit_art_hupf_feuert_nicht_bei_nachhupfer():
    import random

    from dmnt_kobold.eigenleben import Eigenleben

    v = {"regeln": [{"id": "plopp", "wenn": {"ereignis": "avatar.gelandet", "art": "hupf"},
                     "dann": [{"aktion": "animation", "name": "erschrecken"}]}]}
    assert katalog.pruefen(v) == ([], [])
    assert katalog.pruefen({"regeln": [{"id": "n", "wenn": {"ereignis": "avatar.gelandet", "art": "nachhupf"},
                                        "dann": [{"aktion": "animation", "name": "freuen"}]}]}) == ([], [])
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    p = RegelPersoenlichkeit(bus, m, v)
    p.on_event(Ereignis("avatar.gelandet", {"art": "nachhupf", "fallhoehe_px": 10}, 0.0))
    assert m.wuensche() == []
    p.on_event(Ereignis("avatar.gelandet", {"art": "hupf", "fallhoehe_px": 22}, 1.0))
    assert m.tick(0.1).animation == "erschrecken"


# --- Overlay --------------------------------------------------------------------------------

def _ruhe(f):
    f.motor.eigenleben.zustand, f.motor.eigenleben.rest = "ruhe", 60.0


def _ticks(f, sekunden):
    phasen = []
    for _ in range(int(sekunden / 0.016)):
        f._tick()
        if not phasen or phasen[-1] != f._phase:
            phasen.append(f._phase)
    return phasen


def test_eigenleben_hupfer_federt_zweimal_nach(fenster):
    f = fenster
    f.werte = katalog.Werte({"nachhuepfen": 0.45, "sprunghoehe_px": 22, "hupf_pause_min_s": 5,
                             "hupf_pause_max_s": 5})
    el = f.motor.eigenleben
    el.zustand, el.rest, el.richtung = "laufen", 30.0, 1
    phasen = _ticks(f, 2.0)
    arten = [l["art"] for l in f.landungen]
    assert arten == ["hupf", "nachhupf", "nachhupf"]
    assert "hocken" not in phasen[phasen.index("landen"):phasen.index("pause")]   # direkt abgefedert
    assert f.koerper.y == 1080 or f.koerper.zustand == STEHT


def test_faktor_null_kein_nachfedern(fenster):
    f = fenster
    f.werte = katalog.Werte({"hupf_pause_min_s": 5, "hupf_pause_max_s": 5})
    el = f.motor.eigenleben
    el.zustand, el.rest, el.richtung = "laufen", 30.0, 1
    _ticks(f, 1.5)
    assert [l["art"] for l in f.landungen] == ["hupf"]


def test_freuen_huepfend_federt_nur_nach_dem_letzten(fenster):
    f = fenster
    f.werte = katalog.Werte({"nachhuepfen": 0.45})
    _ruhe(f)
    x0 = f.koerper.x
    f.motor.wunsch(animation="freuen", bewegung="freuen_huepfend", prioritaet=40, dauer_s=4)
    _ticks(f, 4.0)
    arten = [l["art"] for l in f.landungen]
    assert arten[:3] == ["hupf", "hupf", "hupf"] and arten[3:] and set(arten[3:]) == {"nachhupf"}
    assert f.koerper.x == x0                                               # senkrecht nachgefedert


def test_ziehen_bricht_nachfedern_ab(fenster):
    from dmnt_kobold.physik import GEZOGEN
    f = fenster
    f.werte = katalog.Werte({"nachhuepfen": 0.7, "hupf_pause_min_s": 5, "hupf_pause_max_s": 5})
    el = f.motor.eigenleben
    el.zustand, el.rest, el.richtung = "laufen", 30.0, 1
    for _ in range(400):
        f._tick()
        if f._nach is not None:
            break
    assert f._nach is not None
    f.koerper.greifen()
    f._tick()
    assert f.koerper.zustand == GEZOGEN and f._nach is None and f._phase == ""


def test_kleine_nachhupfer_ohne_spritzer(fenster):
    f = fenster
    f._partikel = []
    f.darsteller.partikel["landen"] = dict(katalog.PARTIKEL_STANDARD, anzahl=[6, 6])
    f._moment("landen", staerke=0.2)
    assert f._partikel == []
    f._moment("landen", staerke=0.5)
    assert len(f._partikel) == 3
