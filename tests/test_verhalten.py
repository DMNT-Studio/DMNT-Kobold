"""Verhalten: Katalog, Prüfung, Regel-Auswertung, Werte, Migration von DMNT 9000."""
import copy
import json
import random
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from dmnt_kobold import katalog
from dmnt_kobold.beobachter import AudioAnalyse, TippAnalyse, WackelAnalyse, tageszeit
from dmnt_kobold.bus import Ereignis, EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.regeln import RegelPersoenlichkeit, standard_verhalten

WURZEL = Path(__file__).resolve().parents[1]
SRC = WURZEL / "src" / "dmnt_kobold"
DMNT = json.loads((WURZEL / "quellen" / "dmnt9000" / "verhalten.json").read_text(encoding="utf-8"))


def aufbau(verhalten, seed=7):
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    p = RegelPersoenlichkeit(bus, m, verhalten, random.Random(seed), name="test")
    return bus, m, p


def regel(rid="r", wenn=None, dann=None, **kw):
    return {"id": rid, "wenn": wenn or {"ereignis": "maus.klick"},
            "dann": dann or [{"aktion": "animation", "name": "freuen"}], **kw}


def senden(p, ereignis, /, t=0.0, **daten):
    p.on_event(Ereignis(ereignis, daten, t))


# --- Katalog ---------------------------------------------------------------------

def _ausgeloeste_namen() -> set[str]:
    """Alle Ereignisnamen, die der Sockel im Code auslöst (senden(...) und Analyse-Ergebnisse)."""
    namen = set()
    for datei in SRC.rglob("*.py"):
        text = datei.read_text(encoding="utf-8")
        for m in re.finditer(r'senden\(\s*(f?)"([^"]+)"', text):
            namen.add(m.group(2))
        for m in re.finditer(r'\((f?)"([a-z_]+\.[a-z_{}.:]+)", \{', text):
            namen.add(m.group(2))
    return namen


def test_jedes_ausgeloeste_ereignis_steht_im_katalog():
    namen = _ausgeloeste_namen()
    assert {"maus.wackelt", "tastatur.pause", "programm.aktiv", "leerlauf.ende"} <= namen
    beispiele = {"{minuten}": "5", "{minute}": "07:30", "{tz}": "nachts", "{quelle or 'unbekannt'}": "erinnern"}
    for name in namen:
        for platz, beispiel in beispiele.items():
            name = name.replace(platz, beispiel)
        assert katalog.zuordnen(name) is not None, f"{name} fehlt im Katalog"


def test_zuordnen_liest_daten_aus_dem_namen():
    e, extra = katalog.zuordnen("tageszeit.nachts")
    assert e.name == "tageszeit" and extra == {"tageszeit": "nachts"}
    assert katalog.zuordnen("leerlauf.12")[0].name == "leerlauf"
    assert katalog.zuordnen("leerlauf.ende")[0].name == "leerlauf.ende"
    assert katalog.zuordnen("uhrzeit.12:00")[1] == {"uhrzeit": "12:00"}
    assert katalog.zuordnen("gibt.es.nicht") is None


def test_katalog_als_markdown_enthaelt_alles():
    md = katalog.als_markdown()
    for e in katalog.EREIGNISSE:
        assert f"`{e.name}`" in md
    for a in katalog.AKTIONEN:
        assert f"`{a.name}`" in md
    for w in katalog.WERTE:
        assert f"`{w.id}`" in md


def test_aufruf_katalog_gibt_markdown_aus(capsys, monkeypatch):
    import runpy
    monkeypatch.setattr("sys.argv", ["dmnt_kobold", "--katalog"])
    with pytest.raises(SystemExit) as ende:
        runpy.run_module("dmnt_kobold", run_name="__main__")
    assert ende.value.code == 0
    assert "# DMNT-Kobold – Katalog des Sockels" in capsys.readouterr().out


def test_werte_standard_innerhalb_der_grenzen():
    for w in katalog.WERTE:
        assert w.min <= w.standard <= w.max, w.id


# --- Prüfen ------------------------------------------------------------------------

def test_standard_und_dmnt_sind_gueltig():
    assert katalog.pruefen(standard_verhalten())[0] == []
    plan = json.loads((WURZEL / "quellen" / "dmnt9000" / "bauplan.json").read_text(encoding="utf-8"))
    assert katalog.pruefen(DMNT, plan["animationen"]) == ([], [])


@pytest.mark.parametrize("verhalten, erwartet", [
    ({"regeln": [regel("a", wenn={"ereignis": "maus.zwinkert"})]}, "Regel „a“, Feld „wenn.ereignis“"),
    ({"regeln": [regel("b", dann=[{"aktion": "tanzen"}])]}, "Regel „b“, Feld „dann.aktion“"),
    ({"regeln": [regel("c", prioritaet=150)]}, "Regel „c“, Feld „prioritaet“"),
    ({"regeln": [regel("d", chance=2)]}, "Regel „d“, Feld „chance“"),
    ({"regeln": [regel("e", wenn={"ereignis": "programm.gestartet"})]}, "Regel „e“, Feld „wenn.programm“: Pflicht"),
    ({"regeln": [regel("f", dann=[{"aktion": "sprechen"}])]}, "Regel „f“, Feld „sprechen.texte“: Pflicht"),
    ({"regeln": [regel("g", dann=[{"aktion": "zurueckziehen", "regeln": ["x"]}])]}, "Regel „x“ gibt es nicht"),
    ({"regeln": [regel("h", wenn={"ereignis": "leerlauf", "ab_minuten": "$gibtsnicht"})]}, "Regel „h“"),
    ({"regeln": [regel("i"), regel("i")]}, "Regel „i“, Feld „id“: doppelt"),
    ({"werte": {"einschlafen_nach_min": 999}}, "Wert „einschlafen_nach_min“ = 999 liegt außerhalb"),
    ({"werte": {"gibtsnicht": 1}}, "Wert „gibtsnicht“ gibt es nicht"),
])
def test_pruefen_meldet_fehler_mit_regel_und_feld(verhalten, erwartet):
    fehler, _ = katalog.pruefen(verhalten)
    assert any(erwartet in f for f in fehler), fehler


def test_fehlende_animation_ist_nur_warnung():
    fehler, warnungen = katalog.pruefen({"regeln": [regel("a", dann=[{"aktion": "animation", "name": "tanzen"}])]},
                                        ["ruhe", "freuen"])
    assert fehler == [] and warnungen == ["Regel „a“: Animation „tanzen“ fehlt – Rückfall auf „ruhe“"]
    assert katalog.pruefen({"regeln": [regel(dann=[{"aktion": "animation", "name": "laufen"}])]},
                           ["ruhe", "bewegen"])[1] == []


def test_bau_bricht_bei_fehler_ab_bevor_etwas_geloescht_wird(tmp_path):
    pytest.importorskip("PIL")
    pytest.importorskip("scipy")
    import sys
    sys.path.insert(0, str(WURZEL / "werkzeuge"))
    import avatar_bauen

    (tmp_path / "verhalten.json").write_text(json.dumps({"regeln": [regel("kaputt", prioritaet=-1)]}),
                                             encoding="utf-8")
    with pytest.raises(SystemExit) as fehler:
        avatar_bauen.verhalten_pruefen(tmp_path, {"animationen": {"ruhe": {}}})
    assert "Regel „kaputt“, Feld „prioritaet“" in str(fehler.value)


# --- Auswertung ----------------------------------------------------------------------

def test_bedingung_prioritaet_dauer():
    bus, m, p = aufbau({"regeln": [
        regel("mc", wenn={"ereignis": "programm.aktiv", "programm": ["JAVAW.exe"], "titel_enthaelt": "minecraft"},
              dann=[{"aktion": "animation", "name": "freuen"}], prioritaet=55, dauer_s=3)]})
    senden(p, "programm.aktiv", name="javaw.exe", titel="Eclipse")
    assert m.wuensche() == []
    senden(p, "programm.aktiv", name="javaw.exe", titel="Minecraft 1.21")
    w = m.wuensche()[0]
    assert (w.animation, w.prioritaet, w.dauer_s, w.quelle) == ("freuen", 55, 3.0, "test:mc")


def test_oder_bedingungen():
    _, m, p = aufbau({"regeln": [regel("r", wenn=[{"ereignis": "maus.klick"}, {"ereignis": "audio.laeuft"}])]})
    senden(p, "audio.laeuft")
    assert len(m.wuensche()) == 1


def test_abklingzeit():
    _, m, p = aufbau({"regeln": [regel(abklingzeit_s=10, dauer_s=1)]})
    senden(p, "maus.klick", t=0)
    senden(p, "maus.klick", t=5)
    assert len(m.wuensche()) == 1
    senden(p, "maus.klick", t=10.5)
    assert len(m.wuensche()) == 2


def test_chance_mit_festem_zufall():
    _, m, p = aufbau({"regeln": [regel(chance=0.5)]}, seed=3)
    for t in range(100):
        senden(p, "maus.klick", t=t)
    zufall = random.Random(3)
    erwartet = sum(zufall.random() < 0.5 for _ in range(100))
    assert len(m.wuensche()) == erwartet and 30 < erwartet < 70


def test_aktiv_false_bleibt_aus():
    _, m, p = aufbau({"regeln": [regel(aktiv=False)]})
    senden(p, "maus.klick")
    assert m.wuensche() == []


def test_gruppe_feuert_nur_die_erste_passende():
    _, m, p = aufbau({"regeln": [
        regel("lang", dann=[{"aktion": "animation", "name": "freuen"}], abklingzeit_s=8, gruppe="g"),
        regel("kurz", dann=[{"aktion": "animation", "name": "erschrecken"}], gruppe="g")]})
    senden(p, "maus.klick", t=0)
    senden(p, "maus.klick", t=1)
    assert [w.animation for w in m.wuensche()] == ["freuen", "erschrecken"]


def test_bleiben_zurueckziehen_und_regel_laeuft():
    _, m, p = aufbau({"regeln": [
        regel("schlaf", wenn={"ereignis": "leerlauf", "ab_minuten": "$einschlafen_nach_min"},
              dann=[{"aktion": "animation", "name": "schlafen"}, {"aktion": "bleiben"}]),
        regel("wach", wenn={"ereignis": "leerlauf.ende", "regel_laeuft": "schlaf"},
              dann=[{"aktion": "zurueckziehen", "regeln": ["schlaf"]}, {"aktion": "animation", "name": "freuen"}])]})
    senden(p, "leerlauf.4", minuten=4)
    assert m.wuensche() == []
    senden(p, "leerlauf.5", minuten=5)
    senden(p, "leerlauf.6", minuten=6)                  # schläft schon → kein zweiter Wunsch
    assert [(w.animation, w.dauer_s, w.aufheben) for w in m.wuensche()] == [("schlafen", None, True)]
    senden(p, "leerlauf.ende", minuten=6)
    assert [w.animation for w in m.wuensche()] == ["freuen"]
    senden(p, "leerlauf.ende", minuten=1)               # schlief nicht → nichts
    assert len(m.wuensche()) == 1


def test_ruhig_unterdrueckt_sprueche_ausser_trotz_ruhe():
    _, m, p = aufbau({"regeln": [
        regel("still", wenn={"ereignis": "audio.laeuft"}, dann=[{"aktion": "ruhig"}]),
        regel("spruch", dann=[{"aktion": "sprechen", "texte": ["Hallo"]}]),
        regel("trotzdem", wenn={"ereignis": "maus.wackelt"},
              dann=[{"aktion": "sprechen", "texte": ["Hey"], "trotz_ruhe": True}]),
        regel("laut", wenn={"ereignis": "audio.still"}, dann=[{"aktion": "zurueckziehen", "regeln": ["still"]}])]})
    senden(p, "audio.laeuft")
    senden(p, "maus.klick")
    senden(p, "maus.wackelt")
    assert [w.text for w in m.wuensche()] == ["Hey"]
    senden(p, "audio.still")
    senden(p, "maus.klick", t=1)
    assert [w.text for w in m.wuensche()] == ["Hey", "Hallo"]


def test_sprechen_platzhalter_knoepfe_und_zubehoer():
    bus, m, p = aufbau({"regeln": [
        regel("pause", wenn={"ereignis": "tastatur.pause"},
              dann=[{"aktion": "sprechen", "texte": ["{dauer} getippt, {unbekannt}"], "knoepfe": ["Ja", "Nein"]}]),
        regel("auf", wenn={"ereignis": "audio.laeuft"}, dann=[{"aktion": "zubehoer", "name": "hut"}]),
        regel("ziel", dann=[{"aktion": "gehen_zu", "ziel": "links"}])]})
    senden(p, "tastatur.pause", sitzung_s=61)
    w = m.wuensche()[0]
    assert (w.animation, w.text, w.knoepfe) == ("sprechen", "1 Minute getippt, {unbekannt}", ("Ja", "Nein"))
    senden(p, "audio.laeuft")
    assert m.zubehoer == {"hut"}
    senden(p, "maus.klick")
    assert m.wuensche()[-1].ziel == "rand_links"


def test_knopf_der_regel_loest_folgeregel_aus():
    bus, m, p = aufbau({"regeln": [
        regel("frage", dann=[{"aktion": "sprechen", "texte": ["Pause?"], "knoepfe": ["Später"]}]),
        regel("antwort", wenn={"ereignis": "sprechblase.knopf", "knopf": "Später", "regel": "frage"},
              dann=[{"aktion": "animation", "name": "unzufrieden"}])]})
    bus.senden("maus.klick")
    wid = m.tick(0.1).sprechblase[0]
    m.knopf(wid, "Später")
    assert m.tick(0.1).animation == "unzufrieden"


def test_beobachtete_programme_aus_den_regeln():
    _, _, p = aufbau(DMNT)
    assert p.BEOBACHTETE_PROGRAMME == {"starcitizen.exe"}


# --- Werte ----------------------------------------------------------------------------

def test_werte_standard_abweichung_grenzen():
    w = katalog.Werte({"einschlafen_nach_min": 8, "maus_nah_px": 99999, "gibtsnicht": 3, "chance_sitzen": True})
    assert w["einschlafen_nach_min"] == 8
    assert w["maus_nah_px"] == katalog.WERT["maus_nah_px"].max
    assert w["tippen_pause_s"] == 5.0 and w["chance_sitzen"] == 0.12
    assert katalog.Werte().get("laufgeschwindigkeit", 55) == 55
    assert katalog.Werte({"laufgeschwindigkeit": 45}).get("laufgeschwindigkeit", 55) == 45


def test_einschlafzeit_aus_den_werten():
    v = copy.deepcopy(DMNT)
    v["werte"]["einschlafen_nach_min"] = 8
    _, m, p = aufbau(v)
    senden(p, "leerlauf.5", minuten=5)
    assert m.wuensche() == []
    senden(p, "leerlauf.8", minuten=8)
    assert m.wuensche()[0].animation == "schlafen"


def test_beobachter_und_eigenleben_nehmen_die_werte():
    w = katalog.Werte({"tippen_pause_s": 2, "wackeln_wechsel": 2, "audio_start_s": 1, "nachts_ab": 20,
                       "ruhe_min_s": 30, "ruhe_max_s": 30, "wunsch_verfaellt_s": 3})
    assert TippAnalyse(w).PAUSE_S == 2 and WackelAnalyse(w).WECHSEL == 2 and AudioAnalyse(w).START_S == 1
    assert tageszeit(21, w) == "nachts" and tageszeit(21) == "abends"
    el = Eigenleben(random.Random(1), werte=w)
    assert el.rest == 30
    assert Verhaltensmotor(None, el).max_warten_s == 3


# --- Laden: Regeln + optionale Sonderlogik ---------------------------------------------

def _avatar(tmp_path, verhalten=None, code=None):
    datei = tmp_path / "persoenlichkeit.py"
    if code:
        datei.write_text(code, encoding="utf-8")
    return SimpleNamespace(id="probe", verhalten=verhalten, persoenlichkeit_datei=datei,
                           werte=katalog.Werte((verhalten or {}).get("werte")))


SONDERLOGIK = '''
from dmnt_kobold.modul import Modul

class Persoenlichkeit(Modul):
    name = "probe_sonder"
    SONDERLOGIK = [("Klick-Zähler", "zählt Klicks")]
    BEOBACHTETE_PROGRAMME = {"spiel.exe"}

    def on_event(self, e):
        if e.name == "maus.klick":
            self.wunsch(animation="winken", prioritaet=30)
'''


def test_sonderlogik_laeuft_zusaetzlich(tmp_path):
    from dmnt_kobold.avatar import beobachtete_programme, persoenlichkeiten_laden

    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    liste = persoenlichkeiten_laden(_avatar(tmp_path, DMNT, SONDERLOGIK), bus, m)
    assert [type(p).__name__ for p in liste] == ["RegelPersoenlichkeit", "Persoenlichkeit"]
    assert beobachtete_programme(liste) == {"starcitizen.exe", "spiel.exe"}
    bus.senden("maus.klick")
    assert sorted(w.animation for w in m.wuensche()) == ["freuen", "winken"]


def test_ohne_alles_gilt_der_standard(tmp_path):
    from dmnt_kobold.avatar import persoenlichkeiten_laden
    from dmnt_kobold.reaktionen import Reaktionen

    liste = persoenlichkeiten_laden(_avatar(tmp_path), EventBus(), Verhaltensmotor())
    assert len(liste) == 1 and isinstance(liste[0], Reaktionen)


def test_gebauter_dmnt9000_ist_ohne_code():
    gebaut = SRC / "avatare" / "dmnt9000"
    assert (gebaut / "verhalten.json").exists() and not (gebaut / "persoenlichkeit.py").exists()
    assert json.loads((gebaut / "verhalten.json").read_text(encoding="utf-8")) == DMNT


# --- Migration: neue Regeln erzeugen dieselben Wünsche wie der alte Code ----------------

ABLAUF = [
    (0, "maus.nah_am_avatar", {"entfernung": 80}),
    (1, "maus.wackelt", {}),
    (3, "maus.wackelt", {}),
    (12, "maus.wackelt", {}),
    (13, "maus.weg", {}),
    (14, "maus.klick", {}),
    (20, "tastatur.tippt", {}),
    (25, "tastatur.schnell", {}),
    (30, "tastatur.pause", {"sitzung_s": 3}),
    (40, "tastatur.tippt", {}),
    (200, "tastatur.pause", {"sitzung_s": 160}),
    (201, "KNOPF", {"knopf": "Später"}),
    (210, "tastatur.tippt", {}),
    (300, "tastatur.pause", {"sitzung_s": 90}),
    (400, "leerlauf.1", {"minuten": 1}),
    (700, "leerlauf.5", {"minuten": 5}),
    (760, "leerlauf.6", {"minuten": 6}),
    (800, "leerlauf.ende", {"minuten": 6}),
    (801, "leerlauf.ende", {"minuten": 1}),
    (900, "programm.aktiv", {"name": "javaw.exe", "titel": "Minecraft 1.21.4", "vorher": None}),
    (950, "programm.aktiv", {"name": "minecraftlauncher.exe", "titel": "", "vorher": "javaw.exe"}),
    (960, "programm.aktiv", {"name": "notepad.exe", "titel": "Unbenannt – Editor", "vorher": None}),
    (1000, "programm.gestartet", {"name": "starcitizen.exe"}),
    (1020, "tageszeit.nachts", {}),
    (1030, "maus.wackelt", {}),
    (1040, "audio.laeuft", {}),
    (1045, "programm.aktiv", {"name": "notepad.exe", "titel": "", "vorher": "x"}),
    (1100, "programm.beendet", {"name": "starcitizen.exe"}),
    (1200, "audio.still", {}),
    (1300, "tageszeit.nachts", {}),
    (1400, "tageszeit.morgens", {}),
    (1500, "uhrzeit.12:00", {}),
    (1600, "programm.aktiv", {"name": "minecraft.exe", "titel": "", "vorher": None}),
    (1700, "maus.klick", {}),
]


def _schnappschuss(m: Verhaltensmotor, a) -> tuple:
    wuensche = tuple(sorted((w.animation, w.text or "", w.knoepfe, w.prioritaet, w.dauer_s, w.aufheben,
                             str(w.ziel), w.ton or "") for w in m.wuensche()))
    return wuensche, a.animation, a.sprechblase[1:] if a.sprechblase else None, a.ziel, tuple(a.toene), \
        tuple(sorted(m.zubehoer))


def _ablauf(fabrik) -> list[tuple]:
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    p = fabrik(bus, m)
    protokoll, jetzt = [], 0.0
    for t, name, daten in ABLAUF:
        while jetzt < t:
            schritt = min(0.5, t - jetzt)
            m.tick(schritt)
            jetzt += schritt
        if name == "KNOPF":
            a = m.tick(0.0)
            if a.sprechblase:
                m.knopf(a.sprechblase[0], daten["knopf"])
        else:
            p.on_event(Ereignis(name, daten, float(t)))
        protokoll.append((t, name, _schnappschuss(m, m.tick(0.01))))
        jetzt += 0.01
    return protokoll


@pytest.mark.parametrize("art", ["dmnt9000", "standard"])
def test_migration_gleiche_wuensche_wie_vorher(art):
    import alt_reaktionen
    from dmnt_kobold.reaktionen import Reaktionen

    if art == "dmnt9000":
        alt = _ablauf(lambda b, m: alt_reaktionen.Persoenlichkeit(b, m, random.Random(5)))
        # Seit den Roboter-Tönen heißen DMNTs Ton-Aktionen „alarm“/„freude“ statt „erschrecken“/„freuen“
        # (eigene Namen, damit sie nicht automatisch zu jeder Freuen-Animation kommen). Bei Musik spielt
        # er seit dem Editor-Stand die eigene Animation „musik“ statt „freuen“. Sonst gleich.
        regeln = json.loads(json.dumps(DMNT).replace('"name": "alarm"', '"name": "erschrecken"')
                            .replace('"name": "freude"', '"name": "freuen"')
                            .replace('"name": "musik"', '"name": "freuen"'))
        neu = _ablauf(lambda b, m: RegelPersoenlichkeit(b, m, regeln, random.Random(5), name="dmnt9000"))
    else:
        alt = _ablauf(lambda b, m: alt_reaktionen.Reaktionen(b, m, random.Random(5)))
        neu = _ablauf(lambda b, m: Reaktionen(b, m, random.Random(5)))
    for vorher, nachher in zip(alt, neu):
        assert vorher == nachher
    assert any(s[2][2] for s in neu), "Ablauf ohne Sprechblase – Test prüft zu wenig"
