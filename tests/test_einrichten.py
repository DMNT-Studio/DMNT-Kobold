import random
import time

from PySide6.QtCore import QRect

from dmnt_kobold.bus import EventBus
from dmnt_kobold.daten import Datenablage, Sicherung
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.modulverwaltung import Modulverwaltung
from dmnt_kobold.motor import Verhaltensmotor


class FakeToene:
    lautstaerke = 0.35

    def spielen(self, _name):
        pass

    def lautstaerke_setzen(self, w):
        self.lautstaerke = w


def buehne(tmp_path, qapp):
    from dmnt_kobold.einrichten import Dienste, Einrichten

    bus = EventBus()
    motor = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    ablage = Datenablage(tmp_path)
    v = Modulverwaltung(bus, motor, ablage)
    v.alle_starten()
    d = Dienste(einstellungen=ablage.speicher("einstellungen"), verwaltung=v, toene=FakeToene(),
                sicherung=Sicherung(ablage), version="0.4.0", avatar_name="DMNT 9000",
                zuletzt_programme=lambda: ["starcitizen.exe", "notepad.exe"])
    b = Einrichten(QRect(0, 0, 1920, 1032), d)
    return b, d


def test_alle_kacheln_oeffnen_und_schliessen(tmp_path, qapp):
    b, d = buehne(tmp_path, qapp)
    b.show()
    b._t0 -= 2.0                      # Aufbau übersprungen
    b._tick()
    assert all(k.isVisible() for k in b.kategorien.values())
    for s in ("tricks", "lautstaerke", "programme", "system"):
        b.kategorie_umschalten(s)
    assert b.offen == {"links": "lautstaerke", "rechts": "system"}
    b.kategorie_umschalten("system")            # zweiter Klick schließt
    assert b.offen["rechts"] is None
    b.kategorie_umschalten("programme")
    b._programm_setzen("starcitizen.exe", True)
    assert d.einstellungen["programme"] == {"starcitizen.exe": {"ignorieren": True}}
    b._lautstaerke(70)
    assert d.einstellungen["lautstaerke"] == 0.7


def test_umbenennen_wird_gespeichert(tmp_path, qapp):
    b, d = buehne(tmp_path, qapp)
    b.schild._bearbeiten()
    b.schild.feld.setText("  Hal  ")
    b.schild._fertig()
    assert d.einstellungen["name"] == "Hal"


def test_schliessen_laeuft_durch(tmp_path, qapp):
    b, _ = buehne(tmp_path, qapp)
    signale = []
    b.zu_beginnt.connect(lambda: signale.append("sprung"))
    b.geschlossen.connect(lambda: signale.append("zu"))
    b.show()
    b.schliessen()
    b._zu_t0 -= 5.0
    b._tick()
    assert signale == ["sprung", "zu"]


def test_trick_ausschalten_ueber_kachel(tmp_path, qapp):
    b, d = buehne(tmp_path, qapp)
    b.kategorie_umschalten("tricks")
    b._trick_schalten("pausen", False)
    assert d.verwaltung.tricks["pausen"].instanz is None
