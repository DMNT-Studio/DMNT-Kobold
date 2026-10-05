"""Effekt-Ebene: zzz, Noten, Sterne … über dem Kopf – eigenes, durchklickbares Fenster."""
import random
import shutil
import sys
from pathlib import Path

import pytest
from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QImage, QPainter

from dmnt_kobold import effekte, katalog
from dmnt_kobold.bus import EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.regeln import RegelPersoenlichkeit

WURZEL = Path(__file__).resolve().parents[1]
HEXE = WURZEL / "src" / "dmnt_kobold" / "avatare" / "hexe"
sys.path.insert(0, str(WURZEL / "werkzeuge"))


def _gemalt(name, t=0.6, eigene=None) -> int:
    """Wie viele Pixel ein Effekt deckt (0 = nichts gezeichnet)."""
    bild = QImage(220, 180, QImage.Format.Format_ARGB32_Premultiplied)
    bild.fill(Qt.GlobalColor.transparent)
    p = QPainter(bild)
    ok = effekte.zeichnen(p, name, t, QPointF(110, 150), 44, 1, eigene)
    p.end()
    if not ok:
        return -1
    return sum(1 for y in range(0, 180, 2) for x in range(0, 220, 2) if bild.pixelColor(x, y).alpha() > 40)


@pytest.mark.parametrize("name", list(effekte.EINGEBAUT))
def test_jeder_eingebaute_effekt_zeichnet_ueber_dem_kopf(qapp, name):
    assert _gemalt(name) > 3


def test_unbekannter_effekt_zeichnet_nichts(qapp):
    assert _gemalt("gibtsnicht") == -1


def test_eigener_effekt_aus_bildern(qapp):
    from PySide6.QtGui import QPixmap
    pm = QPixmap(20, 20)
    pm.fill(QColor("#FF0000"))
    eigen = {"funken": effekte.EigenerEffekt([pm, pm], 8, 30)}
    assert _gemalt("funken", eigene=eigen) > 20


def test_zuordnung_standard_und_abschalten():
    assert effekte.zuordnung(None) == {"schlafen": "zzz"}
    assert effekte.zuordnung({"schlafen": ""}) == {}
    assert effekte.zuordnung({"erschrecken": "ausrufezeichen"})["schlafen"] == "zzz"


def test_plan_pruefen():
    f, _ = effekte.plan_pruefen({"effekte": {"zuordnung": {"freuen": "regenbogen"}}})
    assert any("regenbogen" in x for x in f)
    f, _ = effekte.plan_pruefen({"effekte": {"eigene": {"zzz": {"ordner": "x"}}}})
    assert any("eingebaut" in x for x in f)
    f, w = effekte.plan_pruefen({"effekte": {"zuordnung": {"freuen": "sterne"}}})
    assert f == [] and w == []


def test_regel_aktion_effekt_geht_an_den_motor():
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    regeln = {"regeln": [{"id": "dreh", "wenn": {"ereignis": "maus.wackelt"},
                          "dann": [{"aktion": "effekt", "name": "sterne"}], "prioritaet": 50, "dauer_s": 3}]}
    RegelPersoenlichkeit(bus, m, regeln, random.Random(1), name="test")     # meldet sich selbst am Bus an
    bus.senden("maus.wackelt")
    a = m.tick(0.01)
    assert a.effekt == "sterne"
    assert katalog.pruefen(regeln, ["ruhe"])[0] == []


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
    m = Verhaltensmotor(EventBus(), Eigenleben(random.Random(2), werte=a.werte))
    f = overlay.AvatarFenster(EventBus(), m, Schalter(), Toene(tmp_path / "t", 0.0), d, werte=a.werte)
    f._uhr = _Uhr()
    yield f
    f.close()


def test_hexe_schlaeft_mit_zzz_in_eigener_ebene(hexe):
    f = hexe
    f.motor.nicht_stoeren = True                     # Eigenleben schläft
    for _ in range(5):
        f._tick()
    ef = f.effekt_fenster
    assert f._animation == "schlafen" and ef.isVisible() and ef.name == "zzz"
    assert ef.windowFlags() & Qt.WindowType.WindowTransparentForInput      # durchklickbar
    assert not f._zustand.zzz                         # nicht mehr im Avatar-Fenster
    kopf, _b = f.darsteller.kopf(f._zustand)
    unten = ef.pos().y() + effekte.KOPF_Y
    assert abs(unten - (f.pos().y() + kopf.y())) <= 1    # sitzt auf dem Kopf
    f.motor.nicht_stoeren = False
    for _ in range(3):
        f._tick()
    assert not ef.isVisible()


def test_hexe_effekt_aus_regel_und_zuordnung(hexe):
    f = hexe
    f.darsteller.effekte_zuordnung = {"erschrecken": "ausrufezeichen"}     # wie in Hexes Bauplan
    f.motor.wunsch(animation="ruhe", effekt="sterne", prioritaet=50, dauer_s=2)
    f._tick()
    assert f.effekt_fenster.name == "sterne"
    f.motor.zurueckziehen(f.motor.aktiver_wunsch.id)
    f.motor.wunsch(animation="erschrecken", prioritaet=50, dauer_s=2)
    f._tick()
    assert f.effekt_fenster.name == "ausrufezeichen"          # Hexes Bauplan: erschrecken → !


def test_editor_eigener_effekt_und_zuordnung(tmp_path, qapp):
    from avatar_editor import Projekt
    from editor_effekte import EffekteTab, eigenen_entfernen, eigenen_hinzufuegen, zuordnung_setzen

    ordner = tmp_path / "kiesel"
    shutil.copytree(WURZEL / "quellen" / "kiesel", ordner, ignore=shutil.ignore_patterns("_alt"))
    pr = Projekt(ordner)
    bild = tmp_path / "f1.png"
    img = QImage(16, 16, QImage.Format.Format_ARGB32)
    img.fill(QColor("#FFAA00"))
    img.save(str(bild))
    name = eigenen_hinzufuegen(pr, "Funken", [bild, bild])
    assert name == "funken" and len(list((ordner / "effekte" / "funken").glob("*.png"))) == 2
    with pytest.raises(ValueError):
        eigenen_hinzufuegen(pr, "zzz", [bild])
    zuordnung_setzen(pr, "freuen", "funken")
    zuordnung_setzen(pr, "schlafen", "")
    gespeichert = Projekt(ordner).bauplan["effekte"]
    assert gespeichert["zuordnung"] == {"freuen": "funken", "schlafen": ""}
    assert effekte.plan_pruefen(Projekt(ordner).bauplan, ordner)[0] == []
    eigenen_entfernen(pr, "funken")
    assert Projekt(ordner).bauplan["effekte"] == {"zuordnung": {"schlafen": ""}}
    zuordnung_setzen(pr, "schlafen", None)
    assert "effekte" not in Projekt(ordner).bauplan                     # zurück auf Standard

    class Editor:
        projekt = pr
        meldung = staticmethod(lambda t: None)
        geaendert = staticmethod(lambda: None)
    tab = EffekteTab(Editor())
    tab.aufbauen()
    assert len(tab._vorschauen) == len(effekte.EINGEBAUT)
