"""Updates über das Internet: neue Version bei GitHub finden, laden, prüfen, installieren.

Konzept #20: kein stilles Update. Der Kobold sagt per Sprechblase Bescheid, der Nutzer
klickt „Aktualisieren“. Dann wird das Setup geladen, die Prüfsumme kontrolliert, der
Zustand gesichert und das Setup still gestartet. Das Setup startet den neuen Kobold.

Datenschutz: Die einzige Verbindung ist ``GET`` auf die GitHub-API dieses Repos (und
beim Aktualisieren der Download von dort). Es wird nichts mitgeschickt außer
``User-Agent: DMNT-Kobold/<version>``. Abschaltbar unter Einrichten → System.

Installationsarten (``pfade.installationsart``):
  installiert  Ein-Klick-Update über das Setup
  portable     Knopf „Herunterladen“ öffnet nur die Release-Seite
  entwickler   keine Prüfung (Start aus dem Quellcode)

Testkanal: ``DMNT_KOBOLD_UPDATE_KANAL=test`` berücksichtigt auch Vorab-Versionen
(Tags mit Bindestrich, z. B. ``v0.7.1-test.1``).
"""
from __future__ import annotations

import functools
import hashlib
import json
import logging
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import urlparse

log = logging.getLogger(__name__)

REPO = "DMNT-Studio/DMNT-Kobold"
API_NEUESTE = f"https://api.github.com/repos/{REPO}/releases/latest"
API_ALLE = f"https://api.github.com/repos/{REPO}/releases?per_page=20"
SEITE_NEUESTE = f"https://github.com/{REPO}/releases/latest"
SETUP_NAME = "DMNT-Kobold-Setup.exe"
PORTABLE_NAME = "DMNT-Kobold-Portable.zip"
SUMMEN_NAME = "SHA256SUMS.txt"
# Downloads nur von GitHub: die Adresse aus der API und die Weiterleitungen auf den Datenspeicher
ERLAUBTE_HOSTS = frozenset({"github.com", "objects.githubusercontent.com",
                            "release-assets.githubusercontent.com"})

ERSTE_PRUEFUNG_MS = 60_000
INTERVALL_MS = 24 * 60 * 60_000
NOCHMAL_MS = 10 * 60_000             # Hinweis passte gerade nicht (Nicht stören, Einrichten)
SPAETER_S = 3 * 24 * 60 * 60
PRIORITAET = 70

KNOPF_AKTUALISIEREN = "Aktualisieren"
KNOPF_HERUNTERLADEN = "Herunterladen"
KNOPF_SPAETER = "Später"
TEXT_NEU = "Es gibt eine neue Version von mir: {version}."
TEXT_LADEN = "Ich hole mir die neue Version. Einen Moment …"
TEXT_KAPUTT = "Das Update ist kaputt angekommen. Ich versuche es morgen nochmal."
TEXT_FEHLER = "Ich konnte das Update gerade nicht laden. Ich versuche es morgen nochmal."
TEXT_START_FEHLER = "Das Update ließ sich nicht starten. Ich versuche es morgen nochmal."
TEXT_FERTIG = "Ich bin jetzt Version {version}."


# --- Versionen ----------------------------------------------------------------

_MUSTER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.\-]+))?$")


@functools.total_ordering
@dataclass(frozen=True)
class Version:
    haupt: tuple[int, int, int]
    vorab: tuple[str, ...] = ()          # leer = fertige Version

    @property
    def ist_vorab(self) -> bool:
        return bool(self.vorab)

    def _schluessel(self):
        # Fertige Version > jede Vorab-Version derselben Nummer (SemVer)
        teile = tuple((0, int(t), "") if t.isdigit() else (1, 0, t) for t in self.vorab)
        return self.haupt, 0 if self.vorab else 1, teile

    def __lt__(self, other: "Version") -> bool:
        return self._schluessel() < other._schluessel()

    def __str__(self) -> str:
        text = ".".join(map(str, self.haupt))
        return f"{text}-{'.'.join(self.vorab)}" if self.vorab else text


def version_lesen(text: object) -> Version | None:
    if not isinstance(text, str):
        return None
    m = _MUSTER.match(text.strip())
    if not m:
        return None
    vorab = tuple(m.group(4).split(".")) if m.group(4) else ()
    return Version((int(m.group(1)), int(m.group(2)), int(m.group(3))), vorab)


# --- Antwort der GitHub-API ---------------------------------------------------

@dataclass(frozen=True)
class Angebot:
    version: str
    setup_url: str
    summen_url: str
    seite_url: str
    vorab: bool = False


def adresse_erlaubt(url: object, tag: str | None = None, name: str | None = None) -> bool:
    """Nur https auf GitHub. Mit ``tag``/``name``: genau die Release-Datei dieses Repos."""
    if not isinstance(url, str):
        return False
    try:
        teile = urlparse(url)
    except ValueError:
        return False
    if teile.scheme != "https" or teile.hostname not in ERLAUBTE_HOSTS:
        return False
    if tag is not None and name is not None:
        return teile.hostname == "github.com" and teile.path == f"/{REPO}/releases/download/{tag}/{name}"
    return True


def _asset(release: dict, name: str) -> str | None:
    for a in release.get("assets") or []:
        if isinstance(a, dict) and a.get("name") == name:
            url = a.get("browser_download_url")
            if adresse_erlaubt(url, release.get("tag_name"), name):
                return url
            log.warning("Update: unerwartete Download-Adresse für %s abgelehnt", name)
            return None
    return None


def release_auswerten(daten: object, aktuell: str, kanal: str = "stabil") -> Angebot | None:
    """Liefert ein Angebot, wenn die Antwort eine neuere, vollständige Version enthält.
    ``daten`` ist bei ``kanal="stabil"`` ein Release (``/releases/latest``), im Testkanal
    die Liste (``/releases``)."""
    jetzt = version_lesen(aktuell)
    if jetzt is None:
        return None
    if isinstance(daten, list):
        kandidaten = [r for r in daten if isinstance(r, dict)]
    elif isinstance(daten, dict):
        kandidaten = [daten]
    else:
        return None
    beste: tuple[Version, dict] | None = None
    for r in kandidaten:
        if r.get("draft"):
            continue
        v = version_lesen(r.get("tag_name"))
        if v is None:
            continue
        if (v.ist_vorab or r.get("prerelease")) and kanal != "test":
            continue
        if beste is None or v > beste[0]:
            beste = (v, r)
    if beste is None or not beste[0] > jetzt:
        return None
    v, r = beste
    setup = _asset(r, SETUP_NAME)
    summen = _asset(r, SUMMEN_NAME)
    if setup is None or summen is None:
        log.info("Update %s ohne Setup oder Prüfsummen – übersprungen", v)
        return None
    seite = r.get("html_url")
    if not (isinstance(seite, str) and seite.startswith(f"https://github.com/{REPO}/")):
        seite = SEITE_NEUESTE
    return Angebot(str(v), setup, summen, seite, v.ist_vorab)


def json_auswerten(text: bytes | str, aktuell: str, kanal: str = "stabil") -> Angebot | None:
    try:
        daten = json.loads(text)
    except (ValueError, TypeError):
        log.info("Update: Antwort ist kein JSON")
        return None
    return release_auswerten(daten, aktuell, kanal)


# --- Prüfsumme ------------------------------------------------------------------

def summen_lesen(text: str) -> dict[str, str]:
    """``SHA256SUMS.txt``: Zeilen ``<hash>  <name>`` (auch ``*<name>``)."""
    summen: dict[str, str] = {}
    for zeile in text.lstrip("\ufeff").splitlines():
        teile = zeile.strip().split(None, 1)
        if len(teile) == 2 and re.fullmatch(r"[0-9a-fA-F]{64}", teile[0]):
            summen[teile[1].lstrip("*").strip()] = teile[0].lower()
    return summen


def sha256(pfad: Path) -> str:
    h = hashlib.sha256()
    with open(pfad, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def geladen_pruefen(setup: Path, summen_text: str, installieren: Callable[[Path], bool],
                    melden: Callable[[str], None]) -> bool:
    """Prüfsumme kontrollieren. Stimmt sie, ``installieren``; sonst Datei löschen und melden."""
    erwartet = summen_lesen(summen_text).get(SETUP_NAME)
    try:
        ok = erwartet is not None and sha256(setup) == erwartet
    except OSError:
        ok = False
    if not ok:
        log.warning("Update: Prüfsumme stimmt nicht – abgebrochen")
        try:
            setup.unlink()
        except OSError:
            pass
        melden(TEXT_KAPUTT)
        return False
    if not installieren(setup):
        melden(TEXT_START_FEHLER)
        return False
    return True


def kanal() -> str:
    return "test" if os.environ.get("DMNT_KOBOLD_UPDATE_KANAL", "").lower() == "test" else "stabil"


# --- Hinweis per Sprechblase (ohne Netz, testbar) ---------------------------------

class UpdateHinweis:
    """Entscheidet, wann der Kobold von einer neuen Version erzählt, und merkt sich „Später“.

    Einstellungen: ``update_pruefen`` (Standard an), ``update_version`` und
    ``update_ignoriert_bis`` (für „Später“), ``letzte_version`` (Meldung nach dem Update).
    """

    def __init__(self, motor, einstellungen, art: str, version: str, *,
                 bus=None, jetzt: Callable[[], float] = time.time,
                 darf_jetzt: Callable[[], bool] = lambda: True,
                 aktualisieren: Callable[[Angebot], None] = lambda a: None,
                 herunterladen: Callable[[Angebot], None] = lambda a: None) -> None:
        self.motor = motor
        self.einstellungen = einstellungen
        self.art = art
        self.version = version
        self.jetzt = jetzt
        self.darf_jetzt = darf_jetzt
        self.aktualisieren = aktualisieren
        self.herunterladen = herunterladen
        self.wartend: Angebot | None = None
        self._offen: tuple[int, Angebot] | None = None
        if bus is not None:
            bus.abonnieren("sprechblase.zu", self._blase_zu, self)

    @property
    def an(self) -> bool:
        return self.art != "entwickler" and bool(self.einstellungen.get("update_pruefen", True))

    def ignoriert(self, angebot: Angebot) -> bool:
        return (self.einstellungen.get("update_version") == angebot.version
                and float(self.einstellungen.get("update_ignoriert_bis", 0) or 0) > self.jetzt())

    def melden(self, angebot: Angebot) -> bool:
        """True, wenn die Sprechblase jetzt erscheint. Passt es gerade nicht (Nicht stören,
        Einrichten), bleibt das Angebot in ``wartend`` für ``nachholen``."""
        if not self.an or self.ignoriert(angebot):
            return False
        if self._offen is not None:
            return False
        if self.motor.nicht_stoeren or not self.darf_jetzt():
            self.wartend = angebot
            return False
        self.wartend = None
        knopf = KNOPF_HERUNTERLADEN if self.art == "portable" else KNOPF_AKTUALISIEREN
        wid = self.motor.wunsch(animation="sprechen", text=TEXT_NEU.format(version=angebot.version),
                                knoepfe=(knopf, KNOPF_SPAETER), prioritaet=PRIORITAET, dauer_s=None,
                                aufheben=True, quelle="update",
                                beim_knopf=lambda k, a=angebot: self._knopf(k, a))
        self._offen = (wid, angebot)
        log.info("Update %s angeboten", angebot.version)
        return True

    def nachholen(self) -> bool:
        return self.melden(self.wartend) if self.wartend is not None else False

    def _knopf(self, knopf: str, angebot: Angebot) -> None:
        self._offen = None
        if knopf == KNOPF_AKTUALISIEREN:
            self.aktualisieren(angebot)
        elif knopf == KNOPF_HERUNTERLADEN:
            self.herunterladen(angebot)
        else:
            self.spaeter(angebot)

    def spaeter(self, angebot: Angebot) -> None:
        self.einstellungen.aktualisieren(update_version=angebot.version,
                                         update_ignoriert_bis=self.jetzt() + SPAETER_S)

    def _blase_zu(self, e) -> None:          # weggeklickt zählt wie „Später“
        if e.daten.get("quelle") == "update" and self._offen is not None:
            _wid, angebot = self._offen
            self._offen = None
            self.spaeter(angebot)

    def sagen(self, text: str, dauer_s: float | None = 8.0) -> int:
        return self.motor.wunsch(animation="sprechen", text=text, prioritaet=PRIORITAET,
                                 dauer_s=dauer_s, aufheben=True, quelle="update:info")

    def nach_update_melden(self) -> bool:
        """Einmal nach einem Update: „Ich bin jetzt Version …“. Bei einer Erstinstallation
        wird die Version nur gemerkt."""
        letzte = self.einstellungen.get("letzte_version")
        if letzte == self.version:
            return False
        self.einstellungen["letzte_version"] = self.version
        alt, neu = version_lesen(letzte), version_lesen(self.version)
        if alt is None or neu is None or not neu > alt:
            return False
        self.sagen(TEXT_FERTIG.format(version=self.version))
        return True
