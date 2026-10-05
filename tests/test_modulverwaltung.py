import random

from dmnt_kobold.bus import EventBus
from dmnt_kobold.daten import Datenablage
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.modulverwaltung import AN, AUS, FEHLER, ZUSTIMMUNG, Modulverwaltung, pruefsumme
from dmnt_kobold.motor import Verhaltensmotor

FREMD = '''
from dmnt_kobold.modul import Modul

class Test(Modul):
    anzeigename = "Testtrick"
    def on_event(self, e):
        if e.name == "kaputt":
            raise RuntimeError("bumm")
        if e.name == "hallo":
            self.speicher["gehoert"] = True
'''


def aufbau(tmp_path):
    bus = EventBus()
    motor = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    ablage = Datenablage(tmp_path / "daten")
    return bus, motor, ablage, Modulverwaltung(bus, motor, ablage)


def fremder_trick(tmp_path, name="test"):
    q = tmp_path / "quelle" / name
    q.mkdir(parents=True)
    (q / "modul.py").write_text(FREMD, encoding="utf-8")
    (q / "trick.json").write_text('{"anzeigename": "Testtrick"}', encoding="utf-8")
    return q


def test_offizielle_tricks_laufen_standardmaessig(tmp_path):
    _, _, _, v = aufbau(tmp_path)
    v.alle_starten()
    assert v.tricks["erinnern"].status == AN and v.tricks["erinnern"].offiziell
    assert v.tricks["pausen"].status == AN


def test_fremder_trick_braucht_zustimmung_und_laeuft_dann(tmp_path):
    bus, _, ablage, v = aufbau(tmp_path)
    v.alle_starten()
    t = v.beibringen(fremder_trick(tmp_path))
    assert t.status == ZUSTIMMUNG and t.instanz is None and not t.offiziell
    v.schalten("test", True)
    assert v.tricks["test"].status == ZUSTIMMUNG           # ohne Zustimmung läuft nichts
    v.zustimmen("test")
    assert v.tricks["test"].status == AN
    bus.senden("hallo")
    assert ablage.speicher("trick_test").get("gehoert") is True


def test_geaenderter_trick_braucht_neue_zustimmung(tmp_path):
    bus, motor, ablage, v = aufbau(tmp_path)
    v.alle_starten()
    v.beibringen(fremder_trick(tmp_path))
    v.zustimmen("test")
    v.alle_beenden()
    (ablage.module / "test" / "modul.py").write_text(FREMD + "\n# geändert\n", encoding="utf-8")
    v2 = Modulverwaltung(bus, motor, ablage)
    v2.alle_starten()
    assert v2.tricks["test"].status == ZUSTIMMUNG


def test_fehler_schaltet_nur_den_trick_ab(tmp_path):
    bus, _, _, v = aufbau(tmp_path)
    v.alle_starten()
    v.beibringen(fremder_trick(tmp_path))
    v.zustimmen("test")
    bus.senden("kaputt")
    assert v.tricks["test"].status == FEHLER
    assert v.tricks["erinnern"].status == AN
    bus.senden("kaputt")                                    # zweites Mal: niemand hört mehr zu


def test_ausschalten_bleibt_gespeichert(tmp_path):
    bus, motor, ablage, v = aufbau(tmp_path)
    v.alle_starten()
    assert v.schalten("pausen", False) == AUS
    v2 = Modulverwaltung(bus, motor, ablage)
    v2.alle_starten()
    assert v2.tricks["pausen"].status == AUS


def test_pruefsumme_ignoriert_cache(tmp_path):
    q = fremder_trick(tmp_path)
    vorher = pruefsumme(q)
    (q / "__pycache__").mkdir()
    (q / "__pycache__" / "x.pyc").write_bytes(b"123")
    assert pruefsumme(q) == vorher
