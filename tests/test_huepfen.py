"""Hüpf-Avatare: Katalog, Physik, Bau, Regeln, Töne, Darstellung, Overlay."""
import json
import random
import shutil
import sys
from pathlib import Path

import pytest

from dmnt_kobold import katalog
from dmnt_kobold.bus import Ereignis, EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.monitore import Monitor, Rechteck
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.physik import FAELLT, GEDREHT, GELANDET, STEHT, Koerper
from dmnt_kobold.regeln import RegelPersoenlichkeit

WURZEL = Path(__file__).resolve().parents[1]
PROBE = WURZEL / "tests" / "daten" / "huepf_probe"
DT = 1 / 60


def mon(name, x, y, w, h, *, frei=None, haupt=False):
    g = Rechteck(x, y, w, h)
    return Monitor(name, g, frei or g, 1.0, haupt)


def flug(k, monitore, max_s=5.0):
    ev = []
    for _ in range(int(max_s / DT)):
        ev += k.schritt(DT, monitore)
        if k.zustand == STEHT:
            break
    return ev


# --- Katalog -----------------------------------------------------------------------------

def test_katalog_kennt_huepfen():
    for a in ("freuen_huepfend", "innen"):
        assert a in katalog.AKTION
    for w in ("sprungweite_px", "sprunghoehe_px", "hupf_pause_min_s", "hupf_pause_max_s"):
        assert w in katalog.WERT
    for n in ("hocken", "absprung", "flug", "landen", "drehen"):
        assert n in katalog.KERN_ANIMATIONEN and n in katalog.KERN_RUECKFALL
    gelandet = {p.name for p in katalog.EREIGNIS["avatar.gelandet"].bedingungen}
    assert {"art", "fallhoehe_px"} <= gelandet
    md = katalog.als_markdown()
    for text in ("freuen_huepfend", "sprungweite_px", "`drehen`", "fallhoehe_px", "Körper", "partikel"):
        assert text in md


def test_min_nicht_ueber_max():
    fehler, _ = katalog.pruefen({"werte": {"hupf_pause_min_s": 2.0, "hupf_pause_max_s": 1.0}})
    assert any("hupf_pause_min_s" in f for f in fehler)
    assert katalog.pruefen({"werte": {"hupf_pause_min_s": 1.0, "hupf_pause_max_s": 1.0}}) == ([], [])


def test_gelandet_nach_fall_ab_200px():
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    v = {"regeln": [{"id": "tief", "wenn": {"ereignis": "avatar.gelandet", "art": "fall", "fallhoehe_px": 200},
                     "dann": [{"aktion": "animation", "name": "erschrecken"}]}]}
    assert katalog.pruefen(v) == ([], [])
    p = RegelPersoenlichkeit(bus, m, v)
    p.on_event(Ereignis("avatar.gelandet", {"art": "hupf", "fallhoehe_px": 26}, 0.0))
    p.on_event(Ereignis("avatar.gelandet", {"art": "fall", "fallhoehe_px": 120}, 1.0))
    assert m.wuensche() == []
    p.on_event(Ereignis("avatar.gelandet", {"art": "fall", "fallhoehe_px": 260}, 2.0))
    assert m.tick(0.1).animation == "erschrecken"


# --- Physik ------------------------------------------------------------------------------

def test_hupf_parabel_landet_exakt_auf_dem_boden():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    k = Koerper(500, 1040)
    k.richtung = 1
    weite, ev = k.hupf_weite(36, [m])
    assert weite == 36 and ev == []
    k.hupf_ab(weite, 26)
    oben = k.y
    for _ in range(200):
        e = k.schritt(DT, [m])
        oben = min(oben, k.y)
        if GELANDET in e:
            break
    assert k.zustand == STEHT and k.y == 1040
    assert 530 <= k.x <= 537                  # ~36 px weiter (Takt-Raster)
    assert 1040 - oben == pytest.approx(26, abs=3)
    art, hoehe = k.landung
    assert art == "hupf" and hoehe == pytest.approx(26, abs=3)


def test_weite_null_bleibt_auf_der_stelle():
    m = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(800, 1080)
    k.hupf_ab(0, 26)
    assert k.zustand == FAELLT
    flug(k, [m])
    assert k.x == 800 and k.y == 1080 and k.landung[0] == "hupf"


def test_an_der_wand_umdrehen():
    m = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(1920 - 45, 1080, halbe_breite=40)
    k.richtung = 1
    weite, ev = k.hupf_weite(36, [m])
    assert GEDREHT in ev and k.richtung == -1 and weite == 36
    k.hupf_ab(weite, 26)
    flug(k, [m])
    assert k.x < 1920 - 45


def test_auf_dem_monitor_bleiben_dreht_auch_mit_nachbar():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    b = mon("B", 1920, 0, 1920, 1080)
    k = Koerper(1920 - 45, 1080, halbe_breite=40)
    k.richtung = 1
    assert k.hupf_weite(36, [a, b])[1] == []                 # Nachbar: einfach weiter
    assert GEDREHT in k.hupf_weite(36, [a, b], auf_monitor_bleiben=True)[1]


def test_hupfer_ueber_tiefere_kante_endet_im_fallen():
    a = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    b = mon("B", 1920, 300, 1920, 1080)                     # Boden 1380, tiefer
    k = Koerper(1915, 1040, halbe_breite=20)
    k.richtung = 1
    weite, ev = k.hupf_weite(36, [a, b])
    assert ev == [] and weite == 36
    k.hupf_ab(weite, 26)
    ev = flug(k, [a, b])
    assert GELANDET in ev and k.y == 1380 and k.x > 1920
    art, hoehe = k.landung
    assert art == "fall" and hoehe > 300


# --- Bau ---------------------------------------------------------------------------------

@pytest.mark.parametrize("plan, erwartet", [
    ({"bewegung": {"art": "gehen", "tempo": 55}}, "laufgeschwindigkeit"),
    ({"bewegung": {"art": "rollen"}}, "bewegung.art"),
    ({"bewegung": {"art": "huepfen", "stauchen": {"breite": 3}}}, "bewegung.stauchen.breite"),
    ({"bewegung": {"art": "huepfen", "wackeln": 1}}, "unbekannter Eintrag „wackeln“"),
    ({"partikel": {"tanzen": {}}}, "kein Moment"),
    ({"partikel": {"landen": {"form": "stern"}}}, "partikel.landen.form"),
    ({"partikel": {"landen": {"reichweite_px": 99}}}, "partikel.landen.reichweite_px"),
    ({"partikel": {"landen": {"anzahl": [9, 3]}}}, "größer als „bis“"),
    ({"toene": {"schmatzen": {"dateien": ["a.wav"]}}}, "kein Moment"),
    ({"toene": {"landen": {"dateien": ["a.aiff"]}}}, ".wav, .ogg, .mp3"),
    ({"toene": {"landen": {"dateien": ["a.wav"], "tonhoehe": 2}}}, "toene.landen.tonhoehe"),
    ({"koerper_deckkraft": 0}, "koerper_deckkraft"),
])
def test_koerper_pruefen_meldet_deutsch(plan, erwartet):
    fehler, _ = katalog.koerper_pruefen(plan)
    assert any(erwartet in f for f in fehler), fehler


def test_synthetisierte_toene_bleiben_frei_benannt():
    plan = {"toene": {"aufwachen": {"segmente": [[500, 700, 0.1]]}}}
    assert katalog.koerper_pruefen(plan) == ([], [])


@pytest.fixture(scope="module")
def probe_gebaut(tmp_path_factory):
    pytest.importorskip("PIL")
    sys.path.insert(0, str(WURZEL / "werkzeuge"))
    import avatar_bauen

    ziel = tmp_path_factory.mktemp("probe") / "huepf_probe"
    avatar_bauen.bauen(PROBE, ziel)
    return ziel


def test_probe_baut_im_rahmen_modus(probe_gebaut):
    d = json.loads((probe_gebaut / "avatar.json").read_text(encoding="utf-8"))
    assert d["bewegung"]["art"] == "huepfen" and "tempo" not in d["bewegung"]
    assert d["partikel"]["landen"]["form"] == "quadrat"
    assert d["toene"]["landen"]["dateien"] == ["toene/landen_1.wav", "toene/landen_2.wav"]
    assert d["toene"]["sprechen"]["wiederholen"] == [1, 3]
    probe = d["zubehoer"]["probe"]
    assert probe["sitz"] == "innen" and probe["immer"] and "froh" in probe["varianten"]
    assert (probe_gebaut / probe["varianten"]["froh"]["bild"]).exists()
    assert 50 < d["koerper"]["breite"] < 70             # Kreis mit 116 px bei Skalierung 2


def test_bau_bricht_bei_tempo_ab_bevor_etwas_geloescht_wird(tmp_path):
    pytest.importorskip("PIL")
    sys.path.insert(0, str(WURZEL / "werkzeuge"))
    import avatar_bauen

    quelle = tmp_path / "q"
    shutil.copytree(PROBE, quelle)
    plan = json.loads((quelle / "bauplan.json").read_text(encoding="utf-8"))
    plan["bewegung"]["tempo"] = 40
    (quelle / "bauplan.json").write_text(json.dumps(plan), encoding="utf-8")
    ziel = tmp_path / "ziel"
    ziel.mkdir()
    (ziel / "bleibt.txt").write_text("x")
    with pytest.raises(avatar_bauen.BauFehler, match="laufgeschwindigkeit"):
        avatar_bauen.bauen(quelle, ziel)
    assert (ziel / "bleibt.txt").exists()


def test_unbekannte_innen_variante_warnt_beim_bau():
    v = {"regeln": [{"id": "x", "wenn": {"ereignis": "maus.klick"},
                     "dann": [{"aktion": "innen", "variante": "wuetend"}]}]}
    fehler, warnungen = katalog.pruefen(v, ["ruhe"], {"froh"})
    assert fehler == [] and any("wuetend" in w and "Grundvariante" in w for w in warnungen)
    assert katalog.pruefen(v, ["ruhe"], {"wuetend"}) == ([], [])


def test_dmnt9000_ohne_bewegung_tempo(qapp):
    from dmnt_kobold.avatar import avatar_laden

    plan = json.loads((WURZEL / "quellen" / "dmnt9000" / "bauplan.json").read_text(encoding="utf-8"))
    assert "tempo" not in plan["bewegung"]
    assert katalog.koerper_pruefen(plan)[0] == []
    _, avatar = avatar_laden("dmnt9000")
    assert "tempo" not in avatar.bewegung and avatar.lauftempo == 55     # Wert aus verhalten.json


def test_vorlagen_legen_nur_rahmen_an_und_ueberschreiben_nichts(tmp_path):
    pytest.importorskip("PIL")
    sys.path.insert(0, str(WURZEL / "werkzeuge"))
    import avatar_bauen
    from vorlagen_huepfen import huepf_vorlagen

    ordner = tmp_path / "wuerfel"
    huepf_vorlagen(ordner, "tnt")
    plan = json.loads((ordner / "bauplan.json").read_text(encoding="utf-8"))
    for n in ("ruhe", "hocken", "absprung", "flug", "landen", "drehen", "freuen", "erschrecken", "schlafen",
              "sprechen"):
        assert n in plan["animationen"], n
    assert len(plan["animationen"]["drehen"]["bilder"]) == 5
    assert (ordner / "zubehoer" / "tnt@froh.png").exists() and (ordner / "LIESMICH.txt").exists()
    v = json.loads((ordner / "verhalten.json").read_text(encoding="utf-8"))
    klick = next(r for r in v["regeln"] if r["id"] == "klick")
    assert {"aktion": "freuen_huepfend"} in klick["dann"] and {"aktion": "innen", "variante": "froh"} in klick["dann"]
    wackeln = next(r for r in v["regeln"] if r["id"] == "wackeln")
    assert {"aktion": "innen", "variante": "erschreckt"} in wackeln["dann"]
    assert v["werte"]["sprungweite_px"] == 36
    avatar_bauen.bauen(ordner, tmp_path / "gebaut")                      # die leere Vorlage baut
    assert (tmp_path / "gebaut" / "avatar.json").exists()
    mein = (PROBE / "freuen.png").read_bytes()
    (ordner / "ruhe.png").write_bytes(mein)
    huepf_vorlagen(ordner, "tnt")
    assert (ordner / "ruhe.png").read_bytes() == mein                    # nichts überschrieben


# --- Regeln ------------------------------------------------------------------------------

def _regeln(dann, **regel):
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    p = RegelPersoenlichkeit(bus, m, {"regeln": [{"id": "r", "wenn": {"ereignis": "maus.klick"}, "dann": dann,
                                                  **regel}]}, random.Random(1))
    p.on_event(Ereignis("maus.klick", {}, 0.0))
    return m


def test_freuen_huepfend_erzeugt_wunsch():
    m = _regeln([{"aktion": "freuen_huepfend", "dauer_s": 3}], dauer_s=1)
    (w,) = m.wuensche()
    assert w.bewegung == "freuen_huepfend" and w.animation == "freuen" and w.dauer_s == 3
    a = m.tick(0.1)
    assert a.bewegung == "freuen_huepfend" and a.animation == "freuen"
    m2 = _regeln([{"aktion": "freuen_huepfend"}, {"aktion": "animation", "name": "erschrecken"}], dauer_s=2)
    (w2,) = m2.wuensche()
    assert w2.animation == "erschrecken" and w2.dauer_s == 2


def test_innen_erzeugt_variante():
    m = _regeln([{"aktion": "animation", "name": "freuen"}, {"aktion": "innen", "variante": "@froh"}], dauer_s=1)
    a = m.tick(0.1)
    assert a.innen == "froh"
    for _ in range(12):
        a = m.tick(0.1)
    assert a.innen is None                         # Wunsch vorbei → Grundvariante


# --- Töne --------------------------------------------------------------------------------

def test_tonhoehe_streut_im_bereich(tmp_path):
    from dmnt_kobold.toene import KoerperTon, Toene, resampeln, wav_lesen

    t = Toene(tmp_path / "cache", 0.5, koerper_toene={
        "landen": KoerperTon.aus_json(PROBE, {"dateien": ["toene/landen_1.wav", "toene/landen_2.wav"],
                                              "tonhoehe": 0.08}),
        "sprechen": KoerperTon.aus_json(PROBE, {"dateien": ["toene/pieps.wav"], "tonhoehe": 0.15,
                                                "wiederholen": [1, 3]})}, rng=random.Random(7))
    faktoren = [t.tonhoehe("landen") for _ in range(300)]
    assert all(0.92 - 1e-9 <= f <= 1.08 + 1e-9 for f in faktoren)
    assert min(faktoren) < 0.95 and max(faktoren) > 1.05            # streut wirklich
    assert len(set(faktoren)) <= 17                                  # gestuft → kleiner Cache
    assert t.tonhoehe("gibtsnicht") == 1.0
    pfad = t.koerper_datei("landen")
    assert pfad.exists() and pfad.parent == tmp_path / "cache"
    laengen = {len(wav_lesen(t.koerper_datei("sprechen"))[0]) for _ in range(30)}
    assert len(laengen) > 1                                          # 1–3 Wiederholungen
    werte, _ = wav_lesen(PROBE / "toene" / "pieps.wav")
    assert len(resampeln(werte, 1.25)) == int(len(werte) / 1.25)


# --- Darstellung und Overlay ---------------------------------------------------------------

def _deckung(darsteller, z):
    from PySide6.QtGui import QImage, QPainter

    img = QImage(darsteller.fenster_b, darsteller.fenster_h, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    darsteller.zeichnen(p, z)
    p.end()
    return img


def test_innenleben_variante_und_rueckfall(qapp, probe_gebaut):
    from dmnt_kobold.avatar import Zustand, avatar_laden

    d, a = avatar_laden(ordner=probe_gebaut)
    assert d.innenleben and a.innen_varianten == {"froh"} and "probe" in a.zubehoer_immer
    assert d.fenster_b > a.rahmen[0] + 2 * katalog.PARTIKEL_RAND          # Platz für Spritzer
    immer = frozenset(a.zubehoer_immer)
    grund = _deckung(d, Zustand(zubehoer=immer, schatten=False))
    froh = _deckung(d, Zustand(zubehoer=immer, schatten=False, innen="froh"))
    unbekannt = _deckung(d, Zustand(zubehoer=immer, schatten=False, innen="wuetend"))
    assert grund != froh and grund == unbekannt
    mitte = (int(d.fuss.x()), int(d.fuss.y() - d.hoehe / 2))
    assert grund.pixelColor(*mitte).red() > grund.pixelColor(*mitte).blue() + 15   # rotes Quadrat scheint durch


class _Uhr:
    def restart(self):
        return 16


@pytest.fixture
def fenster(qapp, probe_gebaut, monkeypatch, tmp_path):
    from dmnt_kobold import overlay, win32
    from dmnt_kobold.avatar import avatar_laden
    from dmnt_kobold.menue import Schalter
    from dmnt_kobold.toene import Toene

    monkeypatch.setattr(win32, "ganz_nach_vorne", lambda *_: None)
    d, a = avatar_laden(ordner=probe_gebaut)
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(3), werte=a.werte))
    f = overlay.AvatarFenster(bus, m, Schalter(), Toene(tmp_path / "t", 0.0), d, werte=a.werte)
    f._uhr = _Uhr()
    for teil in a.zubehoer_immer:
        m.zubehoer_setzen(teil, True, "avatar")
    f.landungen = []
    bus.abonnieren("avatar.gelandet", lambda e: f.landungen.append(dict(e.daten)))
    yield f
    f.close()


def _ticks(f, sekunden, animationen=None):
    phasen = []
    for _ in range(int(sekunden / 0.016)):
        f._tick()
        if not phasen or phasen[-1] != f._phase:
            phasen.append(f._phase)
        if animationen is not None:
            animationen.add(f._animation)
    return phasen


def test_hueper_kette_statt_laufen(fenster):
    f = fenster
    el = f.motor.eigenleben
    x0 = f.koerper.x
    el.zustand, el.rest, el.richtung = "laufen", 30.0, 1
    animationen = set()
    phasen = _ticks(f, 3.0, animationen)
    assert phasen[:5] == ["hocken", "absprung", "flug", "landen", "pause"]
    assert {"hocken", "absprung", "flug", "landen"} <= animationen
    assert not animationen & {"laufen", "bewegen", "fallen"}          # Hüpfer laufen nie, Flug ist kein Fall
    assert f.koerper.x > x0 + 30                                          # mindestens ein Hüpfer weit
    assert f.landungen and f.landungen[0]["art"] == "hupf"


def test_landung_macht_spritzer_die_wieder_verschwinden(fenster):
    f = fenster
    el = f.motor.eigenleben
    el.zustand, el.rest, el.richtung = "laufen", 30.0, 1
    gesehen = False
    for _ in range(200):
        f._tick()
        if f._partikel:
            gesehen = True
            assert 6 <= len(f._partikel) <= 10
            break
    assert gesehen
    el.zustand, el.rest = "ruhe", 30.0
    _ticks(f, 1.0)
    assert f._partikel == [] and not f.partikel_fenster.isVisible()


def test_freuen_huepfend_drei_hupfer_mit_drehung(fenster):
    f = fenster
    f.motor.eigenleben.zustand, f.motor.eigenleben.rest = "ruhe", 30.0
    x0 = f.koerper.x
    f.motor.wunsch(animation="freuen", bewegung="freuen_huepfend", innen="froh", prioritaet=40, dauer_s=4)
    winkel = []
    for _ in range(int(3.5 / 0.016)):
        f._tick()
        if f._drehung is not None:
            winkel.append(f._drehung)
    assert len(f.landungen) == 3 and all(l["art"] == "hupf" for l in f.landungen)
    assert f.koerper.x == x0                                              # auf der Stelle
    assert winkel and max(winkel) > 300 and f._drehung is None            # volle Drehung, danach vorne
    assert f._innen_variante == "froh"
    assert f._zustand.richtung == f.koerper.richtung


def test_innenleben_wackelt_nach_und_kommt_zur_ruhe(fenster):
    f = fenster
    f.motor.eigenleben.zustand, f.motor.eigenleben.rest = "ruhe", 30.0
    f.motor.wunsch(animation="freuen", innen="froh", prioritaet=40, dauer_s=0.5)
    versatz = []
    for _ in range(40):
        f._tick()
        versatz.append(f._innen_versatz)
    assert any(v != (0.0, 0.0) for v in versatz)                          # Wechsel → Hopser
    _ticks(f, 2.0)
    assert f._innen_versatz == (0.0, 0.0) and not f._innen_wackelt()
    assert f._takt.interval() == 100                                      # in Ruhe: langsamer Takt


def test_editor_kennt_rahmen_und_innenleben(tmp_path, qapp):
    pytest.importorskip("PIL")
    sys.path.insert(0, str(WURZEL / "werkzeuge"))
    import avatar_editor as ae
    from editor_verhalten import kurz_dann

    ziel = tmp_path / "huepf_probe"
    shutil.copytree(PROBE, ziel)
    pr = ae.Projekt(ziel)
    assert pr.rahmen and pr.innen_varianten() == ["froh"]
    assert not ae.Projekt(WURZEL / "quellen" / "dmnt9000").rahmen
    assert kurz_dann({"dann": [{"aktion": "freuen_huepfend"}, {"aktion": "innen", "variante": "froh"}]}) \
        == "hüpft vor Freude, innen @froh"
