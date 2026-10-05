"""Rennen – „ihre 5 Minuten“: aus dem Nichts losflitzen, Haken schlagen, springen."""
import random
from pathlib import Path

import pytest

from dmnt_kobold import katalog
from dmnt_kobold.bus import EventBus
from dmnt_kobold.eigenleben import RENNEN, Eigenleben
from dmnt_kobold.motor import Verhaltensmotor

WURZEL = Path(__file__).resolve().parents[1]
HEXE = WURZEL / "src" / "dmnt_kobold" / "avatare" / "hexe"


def _el(seed=1, **werte):
    return Eigenleben(random.Random(seed), katalog.Werte(werte))


def _bis_rennen(el, max_s=600.0):
    t = 0.0
    while el.zustand != RENNEN and t < max_s:
        el.tick(0.1)
        t += 0.1
    return el.zustand == RENNEN


def test_katalog_hat_renn_werte_und_animation():
    for wid in ("chance_rennen", "rennen_min_s", "rennen_max_s", "renntempo", "rennen_haken_s",
                "rennen_sprung_chance", "rennen_sprunghoehe_px"):
        assert katalog.WERT[wid].bereich == "Rennen"
    assert katalog.standard("chance_rennen") == 0.0                 # andere Avatare bleiben, wie sie sind
    assert "rennen" in katalog.KERN_ANIMATIONEN and "rennen" in katalog.momente()
    fehler, _ = katalog.pruefen({"werte": {"rennen_min_s": 9, "rennen_max_s": 2}, "regeln": []}, ["ruhe"])
    assert any("rennen_min_s" in f for f in fehler)


def test_standard_rennt_nie():
    el = _el()
    for _ in range(20000):
        el.tick(0.1)
        assert el.zustand != RENNEN


def test_ohne_rennen_gleicher_ablauf_wie_vorher():
    """chance_rennen 0 verbraucht keinen Zufall extra – bestehende Avatare verhalten sich gleich."""
    a, b = _el(7), _el(7, chance_rennen=0.0)
    for _ in range(3000):
        a.tick(0.1)
        b.tick(0.1)
        assert (a.zustand, a.richtung) == (b.zustand, b.richtung)


def test_rennt_mit_haken_und_endet():
    el = _el(chance_rennen=0.5, rennen_sprung_chance=0.0, rennen_haken_s=0.5, rennen_min_s=4, rennen_max_s=4)
    assert _bis_rennen(el)
    richtungen, t = [], 0.0
    while el.zustand == RENNEN:
        richtungen.append(el.richtung)
        el.tick(0.05)
        t += 0.05
    wechsel = sum(1 for x, y in zip(richtungen, richtungen[1:]) if x != y)
    assert 3 <= wechsel <= 20                                         # Zickzack
    assert 3.9 <= t <= 4.1 and el.zustand == "ruhe"


def test_springt_an_haken():
    el = _el(chance_rennen=0.5, rennen_sprung_chance=1.0, rennen_haken_s=0.5)
    assert _bis_rennen(el)
    for _ in range(40):
        el.tick(0.05)
    assert el.sprung_holen() and not el.sprung_holen()               # genau einmal


def test_motor_meldet_rennen():
    m = Verhaltensmotor(EventBus(), _el(chance_rennen=0.5))
    for _ in range(6000):
        a = m.tick(0.1)
        if a.rennen:
            break
    assert a.rennen and a.laufen and a.animation == RENNEN


@pytest.fixture
def hexe(qapp, monkeypatch, tmp_path):
    if not (HEXE / "avatar.json").exists():
        pytest.skip("Hexe nicht gebaut")
    from dmnt_kobold import overlay, win32
    from dmnt_kobold.avatar import avatar_laden
    from dmnt_kobold.menue import Schalter
    from dmnt_kobold.toene import Toene
    from test_huepfen import _Uhr

    monkeypatch.setattr(win32, "ganz_nach_vorne", lambda *_: None)
    d, a = avatar_laden(ordner=HEXE)
    werte = katalog.Werte({**a.werte.abweichungen, "rennen_sprung_chance": 1.0, "rennen_haken_s": 0.4})
    m = Verhaltensmotor(EventBus(), Eigenleben(random.Random(2), werte=werte))
    f = overlay.AvatarFenster(EventBus(), m, Schalter(), Toene(tmp_path / "t", 0.0), d, werte=werte)
    f._uhr = _Uhr()
    yield f
    f.close()


def test_hexe_flitzt_schnell_und_springt(hexe):
    f = hexe
    el = f.motor.eigenleben
    el.zustand, el.rest, el.richtung, el._haken_in = RENNEN, 30.0, 1, 0.4
    x0 = f.koerper.x
    tempo_max, geflogen, animationen = 0.0, False, set()
    for _ in range(120):                                              # knapp 2 s
        x_vor = f.koerper.x
        f._tick()
        tempo_max = max(tempo_max, abs(f.koerper.x - x_vor) / 0.016)
        geflogen |= f.koerper.zustand == "faellt" and f.koerper.hupf_flug
        animationen.add(f._animation)
    assert tempo_max > f.werte["laufgeschwindigkeit"] * 2              # deutlich schneller als Gehen
    assert geflogen                                                    # mindestens ein Sprung
    assert f.koerper.x != x0
    assert "fallen" not in animationen                                 # Sprung ist kein Sturz
