"""Erinnern und Pausen – über die Modulverwaltung geladen wie im Programm."""
import random
import time

from dmnt_kobold.bus import EventBus
from dmnt_kobold.daten import Datenablage
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.modulverwaltung import Modulverwaltung
from dmnt_kobold.motor import Verhaltensmotor


def start(pfad):
    bus = EventBus()
    motor = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    v = Modulverwaltung(bus, motor, Datenablage(pfad))
    v.alle_starten()
    return bus, motor, v


def test_erinnerung_ueberlebt_harten_neustart_und_kommt_puenktlich(tmp_path):
    _, _, v = start(tmp_path)
    jetzt = time.time()
    v.tricks["erinnern"].instanz.anlegen("Tee", jetzt + 60)
    # „harter Kill“: kein beenden(), alles weg – neuer Prozess liest von der Platte
    _, motor2, v2 = start(tmp_path)
    er = v2.tricks["erinnern"].instanz
    er.jede_sekunde(jetzt + 59)
    assert motor2.tick(0.1).sprechblase is None
    er.jede_sekunde(jetzt + 60)
    a = motor2.tick(0.1)
    assert a.sprechblase is not None and "Tee" in a.sprechblase[1]
    assert a.sprechblase[2] == ("Erledigt", "In 10 min")


def test_verpasste_erinnerung_kommt_nach_start_mit_hinweis(tmp_path):
    _, _, v = start(tmp_path)
    v.tricks["erinnern"].instanz.anlegen("Müll raus", time.time() - 3600)
    _, motor2, v2 = start(tmp_path)
    v2.tricks["erinnern"].instanz.jede_sekunde()
    assert "fällig war" in motor2.tick(0.1).sprechblase[1]


def test_erledigt_und_spaeter(tmp_path):
    _, motor, v = start(tmp_path)
    er = v.tricks["erinnern"].instanz
    e = er.anlegen("A", time.time() - 1)
    er.jede_sekunde()
    wid = motor.tick(0.1).sprechblase[0]
    motor.knopf(wid, "In 10 min")
    assert er.liste()[0]["faellig"] > time.time() + 500
    assert motor.tick(0.1).sprechblase is None
    er.verschieben(e["id"], time.time() - 1)
    er.jede_sekunde()
    motor.knopf(motor.tick(0.1).sprechblase[0], "Erledigt")
    assert er.liste() == []


def test_wegklicken_zaehlt_als_erledigt(tmp_path):
    _, motor, v = start(tmp_path)
    er = v.tricks["erinnern"].instanz
    er.anlegen("B", time.time() - 1)
    er.jede_sekunde()
    motor.sprechblase_geschlossen(motor.tick(0.1).sprechblase[0])
    assert er.liste() == []


def test_merken_aus_der_karte(tmp_path):
    _, _, v = start(tmp_path)
    er = v.tricks["erinnern"].instanz
    assert er.merken("", "10") == "Woran denn?"
    assert er.merken("Tee", "irgendwann") is not None
    assert er.merken("Tee", "10 min") is None
    assert len(er.liste()) == 1


def test_erinnerung_kommt_auch_bei_nicht_stoeren(tmp_path):
    _, motor, v = start(tmp_path)
    motor.nicht_stoeren = True
    er = v.tricks["erinnern"].instanz
    er.anlegen("C", time.time() - 1)
    er.jede_sekunde()
    assert motor.tick(0.1).sprechblase is not None


def test_pausen_mahnung_und_reset_durch_leerlauf(tmp_path):
    bus, motor, v = start(tmp_path)
    p = v.tricks["pausen"].instanz
    p.speicher["intervall_min"] = 1
    for _ in range(59):
        p.jede_sekunde()
    assert motor.tick(0.1).sprechblase is None
    p.jede_sekunde()
    a = motor.tick(0.1)
    assert a.sprechblase is not None and a.sprechblase[2] == ("Mach ich", "In 10 min")
    bus.senden("leerlauf.5", minuten=5)          # echte Pause gemacht
    assert motor.tick(0.1).sprechblase is None and p.aktiv_s == 0


def test_pausen_wartet_bei_nicht_stoeren(tmp_path):
    _, motor, v = start(tmp_path)
    p = v.tricks["pausen"].instanz
    p.speicher["intervall_min"] = 1
    motor.nicht_stoeren = True
    for _ in range(61):
        p.jede_sekunde()
    assert motor.tick(0.1).sprechblase is None
    motor.nicht_stoeren = False
    assert motor.tick(0.1).sprechblase is not None
