"""Kiesel: Eigenentwicklung als Vektor-Rig. Bau, Katalog, Innenleben, Verhalten."""
import json
import random
import shutil
import sys
from pathlib import Path

import pytest

from dmnt_kobold import katalog
from dmnt_kobold.bus import Ereignis, EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.regeln import RegelPersoenlichkeit

WURZEL = Path(__file__).resolve().parents[1]
QUELLE = WURZEL / "quellen" / "kiesel"
GEBAUT = WURZEL / "src" / "dmnt_kobold" / "avatare" / "kiesel"
VERHALTEN = json.loads((QUELLE / "verhalten.json").read_text(encoding="utf-8"))
VARIANTEN = ("froh", "erschreckt", "muede", "neugierig")


def _bauwerkzeug():
    pytest.importorskip("PIL")
    pytest.importorskip("scipy")
    sys.path.insert(0, str(WURZEL / "werkzeuge"))
    import avatar_bauen
    return avatar_bauen


@pytest.fixture(scope="module")
def kiesel_gebaut(tmp_path_factory, qapp):
    avatar_bauen = _bauwerkzeug()
    if shutil.which("ffmpeg") is None:
        try:
            import soundfile  # noqa: F401
        except ImportError:
            pytest.skip("ffmpeg oder soundfile fehlt (für die OGG-Töne)")
    import contextlib
    import io

    ziel = tmp_path_factory.mktemp("kiesel") / "kiesel"
    ausgabe = io.StringIO()
    with contextlib.redirect_stdout(ausgabe):
        avatar_bauen.bauen(QUELLE, ziel)
    return ziel, ausgabe.getvalue()


# --- Bau -------------------------------------------------------------------------------------

def test_kiesel_baut_ohne_warnung(kiesel_gebaut):
    ziel, ausgabe = kiesel_gebaut
    assert "Warnung" not in ausgabe, ausgabe
    d = json.loads((ziel / "avatar.json").read_text(encoding="utf-8"))
    assert d["bewegung"]["art"] == "huepfen"
    assert d["partikel"]["landen"]["form"] == "tropfen" and d["partikel"]["landen"]["farbe"] == "#8EC9E8"
    assert set(d["toene"]) == {"absprung", "landen", "sprechen", "erschrecken"}
    assert d["toene"]["sprechen"]["wiederholen"] == [1, 3]
    assert (ziel / d["herkunft"]).exists() and (ziel / d["portraet"]).exists()
    assert 80 <= d["koerper"]["breite"] <= 92 and 76 <= d["koerper"]["hoehe"] <= 86     # ca. 84 × 80
    assert {"ruhe", "hocken", "absprung", "flug", "landen", "drehen", "anschauen", "sprechen", "freuen",
            "erschrecken", "schlafen", "gezogen", "fallen"} <= set(d["animationen"])
    assert len(d["animationen"]["drehen"]["bilder"]) == 5
    assert all(d["animationen"][a].get("hinten") for a in d["animationen"])       # Rückwand je Frame


def test_gebauter_kiesel_im_paket_ist_aktuell(kiesel_gebaut):
    """Der mitgelieferte Kiesel entspricht den Quellen (sonst vergessen neu zu bauen)."""
    ziel, _ = kiesel_gebaut
    for datei in ("avatar.json", "verhalten.json"):
        assert (GEBAUT / datei).read_text(encoding="utf-8") == (ziel / datei).read_text(encoding="utf-8"), datei


def test_alle_regeln_validieren_gegen_den_katalog():
    plan = json.loads((QUELLE / "bauplan.json").read_text(encoding="utf-8"))
    fehler, warnungen = katalog.pruefen(VERHALTEN, plan["animationen"].keys(), set(VARIANTEN))
    assert fehler == [] and warnungen == []
    fehler, warnungen = katalog.koerper_pruefen(plan, QUELLE)
    assert fehler == [] and warnungen == []


def test_nur_vektorgrafik_und_eigene_toene():
    bilder = [p for p in QUELLE.rglob("*") if p.is_file() and p.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif")]
    assert bilder == []                                         # alles SVG, keine Pixelgrafik
    assert sorted(p.name for p in (QUELLE / "toene").glob("*.ogg")) == \
        ["blubb.ogg", "kling.ogg", "platsch.ogg", "plopp.ogg"]
    assert "MIT" in (QUELLE / "LIZENZ.txt").read_text(encoding="utf-8")
    assert not (QUELLE / "persoenlichkeit.py").exists()        # ohne Code


# --- Rig ---------------------------------------------------------------------------------------

def test_rig_form_neigt_die_spitze_nach_hinten(qapp):
    import numpy as np
    avatar_bauen = _bauwerkzeug()

    def spitze_x(form):
        bild = avatar_bauen.rig_bild(QUELLE / "teile" / "koerper.svg", 224, form)
        ys, xs = np.nonzero(bild[..., 3] > 60)
        oben = ys.min()
        return xs[ys <= oben + 3].mean(), bild.shape

    gerade, groesse = spitze_x(None)
    geneigt, _ = spitze_x({"neigung": -6})
    assert groesse[:2] == (224, 224)                            # viewBox = Leinwand
    assert abs(gerade - 112) < 3 and geneigt < gerade - 8       # Spitze nach hinten (links)


def test_rig_teile_liegen_auf_dem_koerper(qapp):
    import numpy as np
    avatar_bauen = _bauwerkzeug()
    ohne = avatar_bauen.rig_bild(QUELLE / "teile" / "koerper.svg", 224)
    mit = avatar_bauen.rig_bild(QUELLE / "teile" / "koerper.svg", 224, None,
                                [{"datei": "teile/augen_offen.svg"}, {"datei": "teile/mund_strich.svg"}], QUELLE)
    augen = np.abs(mit.astype(int) - ohne.astype(int)).sum(axis=2) > 60
    ys, xs = np.nonzero(augen)
    assert 140 < ys.mean() < 190                                # Augen und Mund weit unten im Körper
    nach_rechts = avatar_bauen.rig_bild(QUELLE / "teile" / "koerper.svg", 224, None,
                                        [{"datei": "teile/augen_offen.svg", "x": 10}], QUELLE)
    ys2, xs2 = np.nonzero(np.abs(nach_rechts.astype(int) - ohne.astype(int)).sum(axis=2) > 60)
    assert xs2.mean() > xs[ys < 175].mean() + 15                # x in logischen Pixeln (×2)


# --- Innenleben ----------------------------------------------------------------------------------

def test_jede_innen_variante_existiert():
    z = json.loads((QUELLE / "zubehoer.json").read_text(encoding="utf-8"))["kiesel"]
    assert z["sitz"] == "innen" and set(z["varianten"]) == set(VARIANTEN)
    for v, d in z["varianten"].items():
        assert (QUELLE / d["datei"]).is_file(), v
    from dmnt_kobold.avatar import Avatar
    a = Avatar(GEBAUT)
    assert a.innen_varianten == set(VARIANTEN) and "kiesel" in a.zubehoer_immer


def test_unbekannte_variante_faellt_auf_kiesel_zurueck(qapp):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage, QPainter

    from dmnt_kobold.avatar import Zustand, avatar_laden

    d, a = avatar_laden("kiesel")
    assert a is not None and a.id == "kiesel"

    def bild(innen):
        im = QImage(d.fenster_b, d.fenster_h, QImage.Format.Format_ARGB32_Premultiplied)
        im.fill(Qt.GlobalColor.transparent)
        p = QPainter(im)
        d.zeichnen(p, Zustand(zubehoer=frozenset({"kiesel"}), innen=innen))
        p.end()
        return im

    grund = bild(None)
    assert bild("gibt_es_nicht") == grund
    assert bild("froh") != grund and bild("muede") != grund


# --- Verhalten -----------------------------------------------------------------------------------

def aufbau():
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    p = RegelPersoenlichkeit(bus, m, VERHALTEN, random.Random(3), name="verhalten")
    return m, p


def senden(p, ereignis, /, t=0.0, **daten):
    p.on_event(Ereignis(ereignis, daten, t))


def test_klick_freut_sich_huepfend_mit_frohem_kiesel():
    m, p = aufbau()
    senden(p, "maus.klick")
    w = m.aktiver_wunsch
    assert w.bewegung == "freuen_huepfend" and w.innen == "froh" and w.animation == "freuen"
    assert w.text in ("Juhu!", "Nochmal!", "Plopp-plopp!")


def test_leerlauf_schlaeft_mit_muedem_kiesel():
    m, p = aufbau()
    senden(p, "leerlauf.5", t=0)
    assert m.aktiver_wunsch is None                             # erst nach 6 Minuten
    senden(p, "leerlauf.6", t=60)
    w = m.aktiver_wunsch
    assert w.animation == "schlafen" and w.innen == "muede" and w.dauer_s is None
    senden(p, "leerlauf.ende", t=70)
    w = m.aktiver_wunsch
    assert w.animation == "erschrecken" and w.text == "Oh! Ich hab nur kurz geblinzelt."


def test_minecraft_mit_abklingzeit():
    m, p = aufbau()
    senden(p, "programm.aktiv", t=0, name="javaw.exe", titel="Minecraft 1.21.4")
    w = m.aktiver_wunsch
    assert w.animation == "freuen" and w.innen == "froh" and w.quelle == "verhalten:minecraft"
    m.zurueckziehen(w.id)
    senden(p, "programm.aktiv", t=600, name="javaw.exe", titel="Minecraft 1.21.4")
    assert m.aktiver_wunsch is None                             # 15 min Abklingzeit
    senden(p, "programm.aktiv", t=901, name="javaw.exe", titel="Minecraft 1.21.4")
    assert m.aktiver_wunsch is not None
    m2, p2 = aufbau()
    senden(p2, "programm.aktiv", t=0, name="javaw.exe", titel="Eclipse")
    assert m2.aktiver_wunsch is None


@pytest.mark.parametrize("art, hoehe, spricht", [("fall", 260, True), ("fall", 200, True), ("fall", 150, False),
                                                 ("hupf", 260, False)])
def test_platsch_nur_nach_hohem_fall(art, hoehe, spricht):
    m, p = aufbau()
    senden(p, "avatar.gelandet", art=art, fallhoehe_px=hoehe)
    w = m.aktiver_wunsch
    assert (w is not None and w.text == "Platsch! Alles heil.") == spricht


def test_wackeln_erschreckt_den_kiesel():
    m, p = aufbau()
    senden(p, "maus.wackelt")
    w = m.aktiver_wunsch
    assert w.animation == "erschrecken" and w.innen == "erschreckt" and w.text == "Huiii, mir ist schwindelig!"


def test_maus_nah_neugierig():
    m, p = aufbau()
    senden(p, "maus.nah_am_avatar")
    nah = [w for w in m.wuensche() if w.quelle == "verhalten:hallo_maus"]
    assert nah and nah[0].innen == "neugierig" and nah[0].animation == "anschauen"


def test_kiesel_ist_adoptierbar():
    from dmnt_kobold.avatar import avatar_liste
    assert ("kiesel", "Kiesel") in [(i, n) for i, n, _ in avatar_liste()]
