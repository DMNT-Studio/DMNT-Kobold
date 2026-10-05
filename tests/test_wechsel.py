"""Kobold ohne Neustart wechseln: Overlay tauscht den Avatar, Töne und Beobachter ziehen mit."""
from __future__ import annotations

from dmnt_kobold.physik import STEHT

from test_huepfen import _Uhr, fenster, probe_gebaut  # noqa: F401  (Fixtures)


def test_avatar_tauschen_im_overlay(fenster):
    from dmnt_kobold.avatar import avatar_laden

    f = fenster
    x0, y0 = f.position()
    d, a = avatar_laden("dmnt9000")
    assert a is not None
    f.avatar_tauschen(d, a.lauftempo, a.werte["zieltempo"], a.werte)
    assert f.darsteller is d and not f.huepft and f.size().width() == d.fenster_b
    assert f.koerper.hoehe == d.hoehe and f.position() == (x0, y0)       # Fußpunkt bleibt
    for _ in range(60):
        f._tick()
    d2, k = avatar_laden("kiesel")
    f.avatar_tauschen(d2, k.lauftempo, k.werte["zieltempo"], k.werte)
    assert f.huepft and f.werte["nachhuepfen"] == k.werte["nachhuepfen"]
    for _ in range(60):
        f._tick()


def test_buehnenhupf_landet_auf_der_stelle(fenster):
    f = fenster
    f._festgehalten = True
    x0, y0 = f.position()
    fertig = []
    f.buehnenhupf(hoehe=34, dauer=0.42, fertig=lambda: fertig.append(1))
    hoechster = y0
    for _ in range(40):
        f._tick()
        hoechster = min(hoechster, f.koerper.y)
    assert fertig == [1] and f.position() == (x0, y0) and f._festgehalten
    assert y0 - hoechster > 25 and f.koerper.zustand == STEHT


def test_toene_und_beobachter_ziehen_mit(tmp_path, qapp):
    from dmnt_kobold.avatar import avatar_laden
    from dmnt_kobold.toene import Toene

    _, k = avatar_laden("kiesel")
    t = Toene(tmp_path / "t", 0.0)
    assert not t.koerper_toene
    t.avatar_setzen(k.toene, k.koerper_toene)
    assert "landen" in t.koerper_toene
    t.avatar_setzen(None, None)
    assert not t.koerper_toene
