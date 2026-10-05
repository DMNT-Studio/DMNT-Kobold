"""Bedienung am Avatar (Konzept #28): Klick gehört dem Avatar, Rechtsklick nur sein
Verhalten, Einrichten und Beenden im Tray, Tray-Hinweis beim ersten Start,
Spritzer durchklickbar."""
import random

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QAction
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QWidgetAction

from dmnt_kobold.bus import EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.erster_start import HINWEIS_KNOPF, HINWEIS_TEXT, ErsterStart
from dmnt_kobold.menue import Schalter, baue_menue
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.regeln import RegelPersoenlichkeit
from dmnt_kobold.tray import baue_tray_menue

from test_huepfen import _ticks, _Uhr, fenster, probe_gebaut  # noqa: F401 – Fixtures


def _texte(menue):
    return [a.text() if not isinstance(a, QWidgetAction) else "<Beenden>" for a in menue.actions()
            if not a.isSeparator() and a.isVisible()]


# --- Menüs ------------------------------------------------------------------------------

def test_rechtsklick_menue_nur_sein_verhalten(qapp):
    menue = baue_menue(Schalter())
    assert _texte(menue) == ["Nicht stören", "Auf diesem Monitor bleiben"]
    assert all(a.isCheckable() for a in menue.actions())
    assert not any(a.isSeparator() for a in menue.actions())


def test_rechtsklick_haekchen_folgen_dem_schalter(qapp):
    s = Schalter()
    menue = baue_menue(s)
    ns, mb = menue.actions()
    s.setze_nicht_stoeren(True)
    assert ns.isChecked() and not mb.isChecked()
    mb.trigger()
    assert s.monitor_bleiben


def test_tray_menue_einrichten_oben_beenden_unten(qapp):
    geklickt = []
    menue = baue_tray_menue(Schalter(), lambda: geklickt.append("holen"), lambda: geklickt.append("ende"),
                            beim_einrichten=lambda: geklickt.append("einrichten"),
                            eintraege=lambda: [("Erinnern …", lambda: geklickt.append("erinnern"))])
    menue.tricks_einsetzen()
    texte = _texte(menue)
    assert texte[0] == "Einrichten" and texte[-1] == "<Beenden>"
    assert texte == ["Einrichten", "Erinnern …", "Kobold zurückholen", "Nicht stören", "<Beenden>"]
    assert menue.actions()[-2].isSeparator()                    # Trennlinie vor Beenden
    menue.actions()[0].trigger()
    next(a for a in menue.actions() if a.text() == "Erinnern …").trigger()
    assert geklickt == ["einrichten", "erinnern"]
    menue.tricks_einsetzen()                                    # zweites Öffnen: nicht doppelt
    assert _texte(menue).count("Erinnern …") == 1


def test_tray_menue_ohne_tricks_ohne_doppelte_trennlinie(qapp):
    menue = baue_tray_menue(Schalter(), lambda: None, lambda: None, beim_einrichten=lambda: None)
    menue.tricks_einsetzen()
    assert _texte(menue) == ["Einrichten", "Kobold zurückholen", "Nicht stören", "<Beenden>"]
    assert sum(a.isSeparator() for a in menue.actions()) == 1


# --- Linksklick ---------------------------------------------------------------------------

def _klick_punkt(f) -> QPoint:
    """Ein Punkt in der Körperform (Maske), nicht im Durchklick-Bereich."""
    r = f.mask().boundingRect()
    return r.center()


def test_linksklick_geht_an_den_avatar_nie_ans_einrichten(fenster):
    f = fenster
    gesehen = []
    f.bus.abonnieren("*", lambda e: gesehen.append(e.name))
    QTest.mouseClick(f, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, _klick_punkt(f))
    assert "maus.klick" in gesehen
    assert "avatar.einrichten_auf" not in gesehen and not f.einrichten_aktiv
    assert not hasattr(f, "beim_einrichten")


def test_klick_ohne_regel_macht_rueckfall_hupfer(fenster):
    f = fenster
    f.motor.eigenleben.zustand, f.motor.eigenleben.rest = "ruhe", 30.0
    x0 = f.koerper.x
    f.klicken()
    phasen = _ticks(f, 1.5)
    assert phasen[:4] == ["", "hocken", "absprung", "flug"] or phasen[:3] == ["hocken", "absprung", "flug"]
    assert len(f.landungen) == 1 and f.landungen[0]["art"] == "hupf"
    assert f.koerper.x == x0                                    # auf der Stelle
    assert f.motor.wuensche() == []                             # kein Wunsch, nur der Sockel


def test_klick_mit_regel_kein_rueckfall(fenster):
    f = fenster
    f.motor.eigenleben.zustand, f.motor.eigenleben.rest = "ruhe", 30.0
    RegelPersoenlichkeit(f.bus, f.motor, {"regeln": [
        {"id": "klick", "wenn": {"ereignis": "maus.klick"},
         "dann": [{"aktion": "freuen_huepfend"}, {"aktion": "innen", "variante": "froh"}],
         "prioritaet": 35, "dauer_s": 2.8}]})
    f.klicken()
    assert not f._antippen
    _ticks(f, 3.5)
    assert len(f.landungen) == 3                                # die Regel: drei Freudenhüpfer


def test_klick_regel_in_abklingzeit_faellt_auf_hupfer_zurueck(fenster):
    f = fenster
    f.motor.eigenleben.zustand, f.motor.eigenleben.rest = "ruhe", 30.0
    RegelPersoenlichkeit(f.bus, f.motor, {"regeln": [
        {"id": "klick", "wenn": {"ereignis": "maus.klick"}, "dann": [{"aktion": "animation", "name": "freuen"}],
         "prioritaet": 35, "dauer_s": 0.5, "abklingzeit_s": 60}]})
    f.klicken()
    assert not f._antippen
    _ticks(f, 1.0)
    f.klicken()                                                 # Regel schweigt → Sockel hüpft
    assert f._antippen


def test_klick_auf_laeufer_kleiner_hupfer(qapp, tmp_path, monkeypatch):
    from dmnt_kobold import overlay, win32
    from dmnt_kobold.avatar import avatar_laden
    from dmnt_kobold.physik import FAELLT
    from dmnt_kobold.toene import Toene

    monkeypatch.setattr(win32, "ganz_nach_vorne", lambda *_: None)
    d, a = avatar_laden("dmnt9000")
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1), werte=a.werte))
    f = overlay.AvatarFenster(bus, m, Schalter(), Toene(tmp_path / "t", 0.0), d, werte=a.werte)
    try:
        f.koerper.zustand = "steht"
        f.klicken()
        assert f.koerper.zustand == FAELLT and f.koerper.vy < 0
    finally:
        f.close()


# --- Spritzer durchklickbar ------------------------------------------------------------------

def test_spritzer_im_eigenen_durchklickbaren_fenster(fenster):
    f = fenster
    el = f.motor.eigenleben
    el.zustand, el.rest, el.richtung = "laufen", 30.0, 1
    for _ in range(300):
        f._tick()
        if f._partikel:
            break
    assert f._partikel
    for _ in range(4):
        f._tick()
    pf = f.partikel_fenster
    assert pf.isVisible() and pf.tropfen
    assert pf.windowFlags() & Qt.WindowType.WindowTransparentForInput
    assert pf.testAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    # Die Maske des Avatars bleibt die Körperform – kein Spritzer liegt darin
    koerper = f.darsteller.maske(f._zustand)
    assert f.mask() == koerper
    links_oben = f.pos()
    for r, _farbe, _form in pf.tropfen:
        mitte = r.center().toPoint() + pf.pos() - links_oben
        if not koerper.boundingRect().contains(mitte):
            assert not f.mask().contains(mitte)
    _ticks(f, 1.0)
    el.zustand, el.rest = "ruhe", 30.0
    _ticks(f, 1.5)
    assert not f._partikel and not pf.isVisible()


# --- Erster Start ---------------------------------------------------------------------------

class _Verzoegern:
    def __init__(self):
        self.liste = []

    def __call__(self, _ms, f):
        self.liste.append(f)

    def alle(self):
        while self.liste:
            self.liste.pop(0)()


def _erster_start(einstellungen, entwickler=False):
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    v = _Verzoegern()
    gesetzt = []
    return ErsterStart(bus, m, einstellungen, gesetzt.append, v, entwickler=entwickler), m, v, gesetzt


def test_tray_hinweis_nach_autostart_frage_genau_einmal():
    einstellungen = {}
    es, m, v, gesetzt = _erster_start(einstellungen)
    es.starten(8000)
    v.alle()
    frage = m.aktiver_wunsch
    assert frage.quelle == "autostart" and frage.knoepfe == ("Ja", "Nein")
    m.knopf(frage.id, "Ja")
    assert gesetzt == [True] and einstellungen["autostart_gefragt"]
    assert m.aktiver_wunsch is None                             # Hinweis kommt erst nach einer Pause
    v.alle()
    hinweis = m.aktiver_wunsch
    assert hinweis.quelle == "tray_hinweis" and hinweis.text == HINWEIS_TEXT
    assert hinweis.knoepfe == (HINWEIS_KNOPF,)
    assert not einstellungen.get("hinweis_tray_gezeigt")
    m.knopf(hinweis.id, HINWEIS_KNOPF)
    assert einstellungen["hinweis_tray_gezeigt"] is True
    # nächster Start: weder Frage noch Hinweis
    es2, m2, v2, _ = _erster_start(einstellungen)
    es2.starten(8000)
    v2.alle()
    assert m2.wuensche() == []


def test_tray_hinweis_auch_fuer_bestehende_nutzer_und_wegklicken_zaehlt():
    einstellungen = {"autostart_gefragt": True}               # Stefans Stand: Frage schon beantwortet
    es, m, v, _ = _erster_start(einstellungen)
    es.starten(8000)
    v.alle()
    hinweis = m.aktiver_wunsch
    assert hinweis.quelle == "tray_hinweis"
    m.sprechblase_geschlossen(hinweis.id)
    assert einstellungen["hinweis_tray_gezeigt"] is True
    es.hinweis_zeigen()
    assert m.wuensche() == []


def test_autostart_weggeklickt_dann_hinweis():
    einstellungen = {}
    es, m, v, gesetzt = _erster_start(einstellungen)
    es.starten(8000)
    v.alle()
    m.sprechblase_geschlossen(m.aktiver_wunsch.id)
    assert einstellungen["autostart_gefragt"] and gesetzt == []
    v.alle()
    assert m.aktiver_wunsch.quelle == "tray_hinweis"


def test_entwickler_start_ohne_frage_und_hinweis():
    einstellungen = {}
    es, m, v, gesetzt = _erster_start(einstellungen, entwickler=True)
    es.starten(8000)
    v.alle()
    assert m.wuensche() == [] and einstellungen == {} and gesetzt == []
