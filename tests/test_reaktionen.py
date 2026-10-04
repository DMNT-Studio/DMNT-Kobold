import random

from dmnt_kobold.bus import EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.reaktionen import LANGE_SITZUNG_S, Reaktionen


def aufbau():
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    Reaktionen(bus, m, random.Random(1))
    return bus, m


def test_maus_nah_schaut_an_und_weg_hoert_auf():
    bus, m = aufbau()
    bus.senden("maus.nah_am_avatar", entfernung=80)
    assert m.tick(0.1).animation == "anschauen"
    bus.senden("maus.weg")
    assert m.tick(0.1).wunsch_id is None


def test_lange_tippsitzung_dann_pause_gibt_sprechblase_mit_knoepfen():
    bus, m = aufbau()
    bus.senden("tastatur.tippt")
    assert m.tick(0.1).animation == "sitzen"
    bus.senden("tastatur.pause", sitzung_s=LANGE_SITZUNG_S + 5)
    a = m.tick(0.1)
    assert a.sprechblase is not None
    assert "durchatmen" in a.sprechblase[1]
    assert a.sprechblase[2] == ("Mach ich", "Später")


def test_kurze_pause_nur_anschauen():
    bus, m = aufbau()
    bus.senden("tastatur.tippt")
    bus.senden("tastatur.pause", sitzung_s=3)
    a = m.tick(0.1)
    assert a.animation == "anschauen" and a.sprechblase is None


def test_star_citizen_rand_rechts_ruhig_und_zurueck():
    bus, m = aufbau()
    bus.senden("programm.aktiv", name="starcitizen.exe", titel="Star Citizen", vorher=None)
    a = m.tick(0.1)
    assert a.ziel == "rand_rechts" and a.animation == "sitzen"
    bus.senden("tastatur.pause", sitzung_s=LANGE_SITZUNG_S + 5)   # bleibt ruhig
    assert m.tick(0.1).sprechblase is None
    bus.senden("programm.aktiv", name="explorer.exe", titel="", vorher="starcitizen.exe")
    assert m.tick(0.1).ziel is None


def test_notepad_sprechblase():
    bus, m = aufbau()
    bus.senden("programm.aktiv", name="notepad.exe", titel="Unbenannt – Editor", vorher=None)
    a = m.tick(0.1)
    assert a.sprechblase is not None and a.sprechblase[2] == ("Ja",)
    assert "freuen" in a.toene


def test_minecraft_ueber_javaw_titel():
    bus, m = aufbau()
    bus.senden("programm.aktiv", name="javaw.exe", titel="Minecraft 1.21.4", vorher=None)
    assert m.tick(0.1).animation == "freuen"


def test_leerlauf_schlafen_und_aufwachen():
    bus, m = aufbau()
    from dmnt_kobold.reaktionen import SCHLAF_NACH_MIN
    bus.senden(f"leerlauf.{SCHLAF_NACH_MIN}", minuten=SCHLAF_NACH_MIN)
    assert m.tick(0.1).animation == "schlafen"
    bus.senden("leerlauf.ende", minuten=SCHLAF_NACH_MIN)
    a = m.tick(0.1)
    assert a.animation == "freuen" and "aufwachen" in a.toene


def test_wackeln_erschrickt():
    bus, m = aufbau()
    bus.senden("maus.nah_am_avatar", entfernung=50)
    bus.senden("maus.wackelt")
    a = m.tick(0.1)
    assert a.animation == "erschrecken" and a.sprechblase is not None
