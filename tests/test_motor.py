import random

from dmnt_kobold.bus import EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.modul import Modul
from dmnt_kobold.motor import MAX_WARTEN_S, Verhaltensmotor, Wunsch


def motor():
    return Verhaltensmotor(EventBus(), Eigenleben(random.Random(1)))


# --- Bus -------------------------------------------------------------------------

def test_bus_muster():
    bus = EventBus()
    gesehen = []
    bus.abonnieren("maus.*", lambda e: gesehen.append(("praefix", e.name)))
    bus.abonnieren("maus.klick", lambda e: gesehen.append(("genau", e.name)))
    bus.abonnieren("*", lambda e: gesehen.append(("alles", e.name)))
    bus.senden("maus.klick")
    bus.senden("tastatur.tippt")
    assert gesehen == [("praefix", "maus.klick"), ("genau", "maus.klick"), ("alles", "maus.klick"),
                       ("alles", "tastatur.tippt")]


def test_fehlerhaftes_modul_wird_deaktiviert_und_rest_laeuft():
    bus = EventBus()
    m = motor()

    class Kaputt(Modul):
        name = "kaputt"

        def on_event(self, e):
            self.wunsch(animation="freuen", dauer_s=None)
            raise RuntimeError("absichtlich")

    k = Kaputt(bus, m)
    andere = []
    bus.abonnieren("*", lambda e: andere.append(e.name))
    bus.senden("x")
    bus.senden("y")
    assert k.aktiv is False
    assert m.wuensche() == []          # Wünsche des Moduls sind weg
    assert andere == ["x", "y"]        # andere Abonnenten laufen weiter


# --- Motor -----------------------------------------------------------------------

def test_ohne_wunsch_eigenleben():
    m = motor()
    a = m.tick(0.1)
    assert a.wunsch_id is None
    assert a.animation in ("ruhe", "laufen", "sitzen")


def test_hoehere_prioritaet_gewinnt_und_verdraengter_verfaellt():
    m = motor()
    a_id = m.wunsch(animation="sitzen", prioritaet=30, dauer_s=10)
    b_id = m.wunsch(animation="freuen", prioritaet=50, dauer_s=1)
    assert m.tick(0.1).wunsch_id == b_id
    for _ in range(12):
        m.tick(0.1)
    assert m.tick(0.1).wunsch_id is None   # a ist verfallen
    assert all(w.id != a_id for w in m.wuensche())


def test_aufheben_kommt_mit_restzeit_zurueck():
    m = motor()
    a_id = m.wunsch(animation="sitzen", prioritaet=30, dauer_s=2, aufheben=True)
    for _ in range(5):
        m.tick(0.1)                          # 0,5 s verbraucht
    m.wunsch(animation="freuen", prioritaet=50, dauer_s=1)
    for _ in range(11):
        m.tick(0.1)
    a = m.tick(0.1)
    assert a.wunsch_id == a_id
    rest = next(w.rest for w in m.wuensche() if w.id == a_id)
    assert 1.3 < rest < 1.5


def test_gleichstand_behaelt_laufenden():
    m = motor()
    a_id = m.wunsch(animation="sitzen", prioritaet=40, dauer_s=5)
    m.wunsch(animation="freuen", prioritaet=40, dauer_s=5)
    assert m.tick(0.1).wunsch_id == a_id


def test_wartender_wunsch_verfaellt():
    m = motor()
    m.wunsch(animation="sitzen", prioritaet=60, dauer_s=None, aufheben=True)
    m.wunsch(animation="freuen", prioritaet=30, dauer_s=2)
    for _ in range(int(MAX_WARTEN_S / 0.5) + 2):
        m.tick(0.5)
    assert [w.animation for w in m.wuensche()] == ["sitzen"]


def test_zurueckziehen_nach_quelle():
    m = motor()
    m.wunsch(animation="sitzen", prioritaet=50, dauer_s=None, quelle="reaktionen:programm")
    m.wunsch(animation="freuen", prioritaet=40, dauer_s=None, quelle="reaktionen:maus")
    m.zurueckziehen_quelle("reaktionen:programm")
    assert m.tick(0.1).animation == "freuen"
    m.zurueckziehen_quelle("reaktionen")
    assert m.wuensche() == []


def test_sprechblase_und_knopf():
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    gedrueckt, gesendet = [], []
    bus.abonnieren("sprechblase.knopf", lambda e: gesendet.append(e.daten["knopf"]))
    wid = m.wunsch(text="Pause?", knoepfe=["Ja", "Nein", "Vielleicht"], prioritaet=60,
                   dauer_s=None, beim_knopf=gedrueckt.append)
    a = m.tick(0.1)
    assert a.sprechblase == (wid, "Pause?", ("Ja", "Nein"))   # höchstens zwei Knöpfe
    assert "sprechen" in a.toene                                # Ton beim Beginn
    m.knopf(wid, "Ja")
    assert gedrueckt == ["Ja"] and gesendet == ["Ja"]
    assert m.tick(0.1).sprechblase is None


def test_nicht_stoeren_laesst_nur_wichtiges_durch():
    m = motor()
    m.nicht_stoeren = True
    m.wunsch(animation="freuen", text="Hallo", prioritaet=50, dauer_s=5)
    a = m.tick(0.1)
    assert a.sprechblase is None and a.animation == "schlafen"
    wid = m.wunsch(text="Termin!", prioritaet=80, dauer_s=5)
    assert m.tick(0.1).wunsch_id == wid


def test_ton_nur_einmal_beim_start():
    m = motor()
    m.wunsch(animation="erschrecken", ton="erschrecken", prioritaet=40, dauer_s=2)
    assert m.tick(0.1).toene == ["erschrecken"]
    assert m.tick(0.1).toene == []


def test_eigenleben_laufen_meldet_laufen():
    el = Eigenleben(random.Random(3))
    m = Verhaltensmotor(None, el)
    el.zustand, el.rest = "laufen", 5
    a = m.tick(0.1)
    assert a.animation == "laufen" and a.laufen is True
    m.wunsch(animation="anschauen", prioritaet=30, dauer_s=None)
    a = m.tick(0.1)
    assert a.animation == "anschauen" and a.laufen is False
