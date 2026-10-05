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
    from dmnt_kobold.einrichten import kobold_name
    assert kobold_name(d.einstellungen, d.aktueller_avatar, "DMNT 9000") == "Hal"


def test_pfeile_wechseln_ringsum_mit_eigenem_namen(tmp_path, qapp):
    """Pfeile am Sockel: sofort wechseln, ringsum; jeder Kobold behält seinen Namen,
    der Hintergrund verwischt, während eines Wechsels sind die Pfeile gesperrt."""
    import time

    from dmnt_kobold import einrichten
    from dmnt_kobold.einrichten import kobold_benennen

    b, d = buehne(tmp_path, qapp)
    gewechselt = []
    d.avatare = lambda: [("dmnt9000", "DMNT 9000", None), ("kiesel", "Kiesel", None), ("sulfi", "Sulfi", None)]
    d.aktueller_avatar = "kiesel"
    d.avatar_wechseln = lambda aid: (gewechselt.append(aid), (aid.title(), None))[1]
    kobold_benennen(d.einstellungen, "sulfi", "Würfelchen")
    b2 = einrichten.Einrichten(b.geometry(), d)
    b2.show()
    b2._t0 -= 2.0
    b2._tick()
    assert all(p.isVisible() for p in b2.pfeile)
    links, rechts = b2.pfeile
    assert links.x() < b2.mitte.x() < rechts.x()
    rechts.click()
    assert gewechselt == ["sulfi"] and b2.schild.label.text() == "Würfelchen"
    assert b2._herkunft_alt is not None and b2._mischung() < 1.0          # Hintergrund verwischt
    rechts.click()                                                         # gesperrt während des Wechsels
    assert gewechselt == ["sulfi"]
    b2._wechsel_bis = time.monotonic() - 1
    rechts.click()                                                         # ringsum: nach Sulfi kommt DMNT 9000
    assert gewechselt == ["sulfi", "dmnt9000"] and b2.schild.label.text() == "Dmnt9000"
    b2._wechsel_bis = time.monotonic() - 1
    links.click()
    assert gewechselt[-1] == "sulfi"


def test_keine_pfeile_bei_nur_einem_kobold(tmp_path, qapp):
    b, _ = buehne(tmp_path, qapp)
    b.show()
    b._t0 -= 2.0
    b._tick()
    assert not any(p.isVisible() for p in b.pfeile)


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


def test_adoptieren_kachel_hat_volle_hoehe(tmp_path, qapp):
    """Nach dem Inhaltswechsel (System → Adoptieren) wird die Kachel nicht zur flachen Pille."""
    b, d = buehne(tmp_path, qapp)
    d.avatare = lambda: [("dmnt9000", "DMNT 9000", None), ("kiesel", "Kiesel", None), ("sulfi", "Sulfi", None)]
    d.aktueller_avatar = "kiesel"
    b.show()
    b._t0 -= 2.0
    b._tick()
    b.kategorie_umschalten("system")
    qapp.processEvents()
    b._adoptieren_zeigen()
    k = b.kacheln["rechts"]
    assert k.height() >= k.sizeHint().height() > 200          # sofort, ohne Ereignisschleife
    texte = [w.text() for w in k.findChildren(type(b.fertig_knopf)) if w.isVisible()]
    assert texte.count("Adoptieren") == 2 and "Wohnt hier" in texte and "Zurück" in texte
    assert not any(w.text() == "System" for w in k.findChildren(type(k.findChild(type(b.schild.label))))
                   if w.isVisible())                         # alter Inhalt ist sofort weg
    qapp.processEvents()
    assert k.height() >= k.sizeHint().height()
