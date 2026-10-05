"""Update über das Internet: Versionen, API-Antwort, Prüfsumme, Hinweis, Portable."""
from __future__ import annotations

import copy
import dataclasses
import hashlib
import json
import sys
from pathlib import Path

import pytest

from dmnt_kobold import __version__, pfade, update
from dmnt_kobold.bus import EventBus
from dmnt_kobold.daten import Speicher
from dmnt_kobold.erster_start import ErsterStart
from dmnt_kobold.motor import Verhaltensmotor
from dmnt_kobold.update import Angebot, UpdateHinweis, release_auswerten, version_lesen

DATEN = Path(__file__).parent / "daten" / "update"
WURZEL = Path(__file__).parent.parent


def _json(name: str):
    return json.loads((DATEN / name).read_text(encoding="utf-8"))


# --- Version ----------------------------------------------------------------------

def test_version_eine_quelle():
    import tomllib
    with open(WURZEL / "pyproject.toml", "rb") as f:
        assert tomllib.load(f)["project"]["version"] == __version__


def test_versionen_vergleichen():
    v = version_lesen
    assert v("0.6.2") < v("0.7.0") < v("0.7.1") < v("0.10.0") < v("1.0.0")
    assert v("v0.7.0") == v("0.7.0")
    assert v("0.7.0-test.1") < v("0.7.0") and v("0.7.0-test.1") > v("0.6.9")
    assert v("0.7.0-test.2") > v("0.7.0-test.1") and v("0.7.0-test.10") > v("0.7.0-test.2")
    for kaputt in ("", "0.7", "x.y.z", "0.7.0.1", None, 7):
        assert v(kaputt) is None


# --- API-Antwort ------------------------------------------------------------------

def test_neuere_version_wird_angeboten():
    a = release_auswerten(_json("release_neu.json"), "0.7.0")
    assert a is not None and a.version == "0.7.1" and not a.vorab
    assert a.setup_url.endswith("/v0.7.1/DMNT-Kobold-Setup.exe")
    assert a.summen_url.endswith("/v0.7.1/SHA256SUMS.txt")
    assert a.seite_url == "https://github.com/DMNT-Studio/DMNT-Kobold/releases/tag/v0.7.1"


@pytest.mark.parametrize("aktuell", ["0.7.1", "0.8.0", "kaputt"])
def test_gleiche_aeltere_oder_kaputte_version_nichts(aktuell):
    assert release_auswerten(_json("release_neu.json"), aktuell) is None


def test_fehlendes_setup_nichts():
    r = _json("release_neu.json")
    r["assets"] = [x for x in r["assets"] if x["name"] != "DMNT-Kobold-Setup.exe"]
    assert release_auswerten(r, "0.7.0") is None


@pytest.mark.parametrize("url", [
    "https://evil.example/DMNT-Studio/DMNT-Kobold/releases/download/v0.7.1/DMNT-Kobold-Setup.exe",
    "http://github.com/DMNT-Studio/DMNT-Kobold/releases/download/v0.7.1/DMNT-Kobold-Setup.exe",
    "https://github.com/Fremd/DMNT-Kobold/releases/download/v0.7.1/DMNT-Kobold-Setup.exe",
    "https://github.com/DMNT-Studio/DMNT-Kobold/releases/download/v0.6.0/DMNT-Kobold-Setup.exe",
])
def test_fremde_download_adresse_abgelehnt(url):
    r = _json("release_neu.json")
    r["assets"][0]["browser_download_url"] = url
    assert release_auswerten(r, "0.7.0") is None


def test_kaputtes_json_nichts():
    assert update.json_auswerten(b"<html>Rate limit</html>", "0.7.0") is None
    assert update.json_auswerten(b'{"message": "Not Found"}', "0.7.0") is None


def test_vorab_nur_im_testkanal():
    liste = _json("releases_liste.json")
    stabil = release_auswerten(liste, "0.7.0", "stabil")
    assert stabil is not None and stabil.version == "0.7.1"           # Entwurf 0.9.0 zählt nie
    test = release_auswerten(liste, "0.7.0", "test")
    assert test is not None and test.version == "0.8.0-test.1" and test.vorab
    einzeln = copy.deepcopy(liste[0])
    assert release_auswerten(einzeln, "0.7.0", "stabil") is None


def test_weiterleitung_nur_zu_github():
    assert update.adresse_erlaubt("https://objects.githubusercontent.com/github-production-release-asset/x")
    assert update.adresse_erlaubt("https://release-assets.githubusercontent.com/x")
    assert not update.adresse_erlaubt("https://example.com/x")
    assert not update.adresse_erlaubt("http://objects.githubusercontent.com/x")


# --- Prüfsumme --------------------------------------------------------------------

def _summen(inhalt: bytes) -> str:
    h = hashlib.sha256(inhalt).hexdigest()
    return f"\ufeff{h}  DMNT-Kobold-Setup.exe\n{'0' * 64}  DMNT-Kobold-Portable.zip\n"


def test_pruefsumme_stimmt_installiert(tmp_path):
    setup = tmp_path / "DMNT-Kobold-Setup.exe"
    setup.write_bytes(b"echtes setup")
    gestartet, gemeldet = [], []
    ok = update.geladen_pruefen(setup, _summen(b"echtes setup"),
                                lambda p: gestartet.append(p) or True, gemeldet.append)
    assert ok and gestartet == [setup] and gemeldet == []


def test_pruefsumme_falsch_abbruch_und_geloescht(tmp_path):
    setup = tmp_path / "DMNT-Kobold-Setup.exe"
    setup.write_bytes(b"manipuliert")
    gestartet, gemeldet = [], []
    ok = update.geladen_pruefen(setup, _summen(b"echtes setup"), gestartet.append, gemeldet.append)
    assert not ok and gestartet == [] and not setup.exists()
    assert gemeldet == [update.TEXT_KAPUTT]


def test_pruefsumme_fehlt_abbruch(tmp_path):
    setup = tmp_path / "DMNT-Kobold-Setup.exe"
    setup.write_bytes(b"x")
    gestartet, gemeldet = [], []
    assert not update.geladen_pruefen(setup, "", gestartet.append, gemeldet.append)
    assert gestartet == [] and not setup.exists()


# --- Hinweis per Sprechblase --------------------------------------------------------

ANGEBOT = Angebot("0.7.1", "https://github.com/x", "https://github.com/y",
                  "https://github.com/DMNT-Studio/DMNT-Kobold/releases/tag/v0.7.1")


class Uhr:
    def __init__(self) -> None:
        self.t = 1_000_000.0

    def __call__(self) -> float:
        return self.t


def _hinweis(tmp_path, art="installiert", **kw):
    bus = EventBus()
    motor = Verhaltensmotor(bus)
    einst = Speicher(tmp_path / "einstellungen.json")
    uhr = Uhr()
    h = UpdateHinweis(motor, einst, art, "0.7.0", bus=bus, jetzt=uhr, **kw)
    return h, motor, einst, uhr, bus


def test_hinweis_mit_zwei_knoepfen(tmp_path):
    h, motor, *_ = _hinweis(tmp_path)
    assert h.melden(ANGEBOT)
    w = motor.aktiver_wunsch
    assert w.prioritaet == 70 and w.knoepfe == ("Aktualisieren", "Später")
    assert "0.7.1" in w.text


def test_aktualisieren_ruft_download(tmp_path):
    geklickt = []
    h, motor, *_ = _hinweis(tmp_path, aktualisieren=geklickt.append)
    h.melden(ANGEBOT)
    motor.knopf(motor.aktiver_wunsch.id, "Aktualisieren")
    assert geklickt == [ANGEBOT]


def test_spaeter_drei_tage_ruhe(tmp_path):
    h, motor, einst, uhr, _ = _hinweis(tmp_path)
    h.melden(ANGEBOT)
    motor.knopf(motor.aktiver_wunsch.id, "Später")
    assert einst["update_version"] == "0.7.1"
    uhr.t += 2 * 24 * 3600
    assert not h.melden(ANGEBOT)
    neuer = dataclasses.replace(ANGEBOT, version="0.7.2")
    assert h.melden(neuer)                      # andere Version kommt trotzdem
    motor.knopf(motor.aktiver_wunsch.id, "Später")
    uhr.t += 4 * 24 * 3600
    assert h.melden(ANGEBOT)                    # nach Ablauf wieder


def test_wegklicken_zaehlt_wie_spaeter(tmp_path):
    h, motor, einst, *_ = _hinweis(tmp_path)
    h.melden(ANGEBOT)
    motor.sprechblase_geschlossen(motor.aktiver_wunsch.id)
    assert einst["update_version"] == "0.7.1" and not h.melden(ANGEBOT)


def test_nicht_stoeren_und_einrichten_warten(tmp_path):
    offen = {"einrichten": True}
    h, motor, *_ = _hinweis(tmp_path, darf_jetzt=lambda: not offen["einrichten"])
    assert not h.melden(ANGEBOT) and h.wartend == ANGEBOT
    offen["einrichten"] = False
    motor.nicht_stoeren = True
    assert not h.nachholen()
    motor.nicht_stoeren = False
    assert h.nachholen() and h.wartend is None


def test_schalter_aus_und_entwickler_still(tmp_path):
    h, _motor, einst, *_ = _hinweis(tmp_path)
    einst["update_pruefen"] = False
    assert not h.melden(ANGEBOT)
    h2, *_ = _hinweis(tmp_path / "e", art="entwickler")
    assert not h2.melden(ANGEBOT)


def test_portable_knopf_herunterladen(tmp_path):
    geoeffnet = []
    h, motor, *_ = _hinweis(tmp_path, art="portable", herunterladen=geoeffnet.append)
    h.melden(ANGEBOT)
    assert motor.aktiver_wunsch.knoepfe == ("Herunterladen", "Später")
    motor.knopf(motor.aktiver_wunsch.id, "Herunterladen")
    assert geoeffnet == [ANGEBOT]


def test_nach_update_einmal_melden(tmp_path):
    h, motor, einst, *_ = _hinweis(tmp_path)
    assert not h.nach_update_melden()                # Erstinstallation: nur merken
    assert einst["letzte_version"] == "0.7.0"
    einst["letzte_version"] = "0.6.3"
    assert h.nach_update_melden()
    assert motor.aktiver_wunsch.text == "Ich bin jetzt Version 0.7.0."
    assert not h.nach_update_melden()                # nur einmal


# --- Portable ---------------------------------------------------------------------

def test_installationsart_und_portable_daten(tmp_path, monkeypatch):
    monkeypatch.delenv("DMNT_KOBOLD_DATEN", raising=False)
    assert pfade.installationsart() == "entwickler"
    exe = tmp_path / "DMNT-Kobold.exe"
    exe.write_bytes(b"")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(exe))
    assert pfade.installationsart() == "installiert"
    (tmp_path / "portable.txt").write_text("")
    assert pfade.installationsart() == "portable"
    assert pfade.datenordner() == tmp_path / "daten"


def test_portable_ohne_autostart_frage(tmp_path):
    bus = EventBus()
    motor = Verhaltensmotor(bus)
    einst = Speicher(tmp_path / "e.json")
    geplant = []
    es = ErsterStart(bus, motor, einst, lambda an: None, lambda ms, f: geplant.append(f),
                     ohne_autostart=True)
    es.starten(10)
    assert geplant == [es.hinweis_zeigen]
