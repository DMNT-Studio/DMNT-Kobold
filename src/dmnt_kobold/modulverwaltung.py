"""Modul-Lader („Tricks“) mit Herkunft und Prüfsumme.

Herkunft:
  offiziell  liegt im Programm (dmnt_kobold/tricks/<name>/modul.py)
  fremd      selbst beigebracht (Dokumente\\DMNT-Kobold\\module\\<name>\\modul.py)

Fremde Tricks sind Python-Code mit vollen Rechten. Sie laufen erst nach einer
ausdrücklichen Zustimmung. Die Zustimmung gilt für genau eine Prüfsumme über
alle Dateien des Ordners – ändert sich auch nur ein Byte, wird neu gefragt.
Vor der Zustimmung wird kein Code des Tricks ausgeführt (Name und
Beschreibung kommen dann aus der optionalen ``trick.json``).

Ein Fehler in einem Trick schaltet nur diesen Trick ab; der Avatar läuft weiter.
"""
from __future__ import annotations

import hashlib
import importlib.util
import inspect
import json
import logging
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .modul import Modul

log = logging.getLogger(__name__)

OFFIZIELL_ORDNER = Path(__file__).parent / "tricks"
STANDARD_AN = {"erinnern": True, "pausen": True}

AN, AUS, ZUSTIMMUNG, FEHLER = "an", "aus", "zustimmung", "fehler"


def pruefsumme(ordner: Path) -> str:
    h = hashlib.sha256()
    for datei in sorted(p for p in ordner.rglob("*") if p.is_file()):
        rel = datei.relative_to(ordner)
        if "__pycache__" in rel.parts or datei.suffix in (".pyc", ".pyo"):
            continue
        h.update(rel.as_posix().encode("utf-8") + b"\0")
        h.update(datei.read_bytes())
        h.update(b"\0")
    return h.hexdigest()


@dataclass
class Trick:
    name: str
    ordner: Path
    offiziell: bool
    anzeigename: str
    beschreibung: str = ""
    pruefsumme: str = ""
    status: str = AUS
    instanz: Modul | None = None

    @property
    def braucht_zustimmung(self) -> bool:
        return self.status == ZUSTIMMUNG


def _metadaten(ordner: Path) -> tuple[str, str]:
    try:
        daten = json.loads((ordner / "trick.json").read_text(encoding="utf-8"))
        return str(daten.get("anzeigename") or ordner.name), str(daten.get("beschreibung") or "")
    except (OSError, ValueError):
        return ordner.name, ""


class Modulverwaltung:
    """Zugleich die „Umgebung“, die Module bekommen (speicher, hotkeys, modul_fehler)."""

    def __init__(self, bus, motor, ablage, hotkeys=None, offiziell_ordner: Path = OFFIZIELL_ORDNER,
                 bei_aenderung: Callable[[], None] | None = None) -> None:
        self.bus = bus
        self.motor = motor
        self.ablage = ablage
        self.hotkeys = hotkeys
        self.offiziell_ordner = offiziell_ordner
        self.fremd_ordner = ablage.module
        self.einstellungen = ablage.speicher("einstellungen")
        self.bei_aenderung = bei_aenderung
        self.tricks: dict[str, Trick] = {}

    # --- Umgebung für Module ---------------------------------------------------
    def speicher(self, name: str):
        return self.ablage.speicher(f"trick_{name}")

    def modul_fehler(self, modul: Modul) -> None:
        t = self.tricks.get(modul.name)
        if t is not None and t.instanz is modul:
            t.status = FEHLER
            t.instanz = None
            self._geaendert()

    # --- Finden und Laden ----------------------------------------------------
    def finden(self) -> list[Trick]:
        gefunden: dict[str, Trick] = {}
        for offiziell, wurzel in ((True, self.offiziell_ordner), (False, self.fremd_ordner)):
            if not wurzel.exists():
                continue
            for ordner in sorted(p for p in wurzel.iterdir() if (p / "modul.py").is_file()):
                name = ordner.name
                if name in gefunden:
                    log.warning("Trick %s doppelt – fremde Fassung ignoriert", name)
                    continue
                anzeige, beschr = _metadaten(ordner)
                alt = self.tricks.get(name)
                t = Trick(name, ordner, offiziell, anzeige, beschr, pruefsumme(ordner))
                if alt is not None and alt.instanz is not None and alt.pruefsumme == t.pruefsumme:
                    t.status, t.instanz = alt.status, alt.instanz
                    t.anzeigename, t.beschreibung = alt.anzeigename, alt.beschreibung
                gefunden[name] = t
        self.tricks = gefunden
        return list(gefunden.values())

    def gewuenscht(self, name: str) -> bool:
        return bool(self.einstellungen.get("tricks", {}).get(name, STANDARD_AN.get(name, False)))

    def zugestimmt(self, t: Trick) -> bool:
        return t.offiziell or self.einstellungen.get("zustimmungen", {}).get(t.name) == t.pruefsumme

    def alle_starten(self) -> None:
        self.finden()
        for t in self.tricks.values():
            if t.instanz is None:
                self._starten_wenn_erlaubt(t)
        self._geaendert()

    def _starten_wenn_erlaubt(self, t: Trick) -> None:
        if not self.gewuenscht(t.name):
            t.status = AUS
        elif not self.zugestimmt(t):
            t.status = ZUSTIMMUNG
        else:
            self._laden(t)

    def _laden(self, t: Trick) -> None:
        try:
            modname = f"dmnt_kobold_trick_{t.name}"
            spec = importlib.util.spec_from_file_location(modname, t.ordner / "modul.py",
                                                          submodule_search_locations=[str(t.ordner)])
            pymod = importlib.util.module_from_spec(spec)
            sys.modules[modname] = pymod
            spec.loader.exec_module(pymod)
            klassen = [k for _, k in inspect.getmembers(pymod, inspect.isclass)
                       if issubclass(k, Modul) and k is not Modul and k.__module__ == modname]
            if not klassen:
                raise TypeError("modul.py enthält keine Klasse, die von Modul erbt")
            klasse = klassen[0]
            klasse.name = t.name
            t.anzeigename = getattr(klasse, "anzeigename", None) or t.anzeigename
            if getattr(klasse, "beschreibung", ""):
                t.beschreibung = klasse.beschreibung
            t.instanz = klasse(self.bus, self.motor, self)
            t.status = AN if t.instanz.aktiv else FEHLER
            log.info("Trick %s gestartet (%s)", t.name, "offiziell" if t.offiziell else "fremd")
        except Exception:  # noqa: BLE001
            log.exception("Trick %s konnte nicht geladen werden", t.name)
            t.instanz = None
            t.status = FEHLER

    # --- Bedienung (Einrichten → Tricks) --------------------------------------
    def schalten(self, name: str, an: bool) -> str:
        t = self.tricks[name]
        tricks = dict(self.einstellungen.get("tricks", {}))
        tricks[name] = an
        self.einstellungen["tricks"] = tricks
        if an:
            if t.instanz is None:
                self._starten_wenn_erlaubt(t)
        else:
            if t.instanz is not None:
                t.instanz.abschalten()
                t.instanz = None
            t.status = AUS
        self._geaendert()
        return t.status

    def zustimmen(self, name: str) -> str:
        t = self.tricks[name]
        t.pruefsumme = pruefsumme(t.ordner)        # frisch – nicht dem Stand von vorhin trauen
        z = dict(self.einstellungen.get("zustimmungen", {}))
        z[name] = t.pruefsumme
        self.einstellungen["zustimmungen"] = z
        return self.schalten(name, True)

    def beibringen(self, quelle: Path) -> Trick:
        """Kopiert einen Trick-Ordner nach module/. Er braucht danach eine Zustimmung."""
        quelle = Path(quelle)
        if not (quelle / "modul.py").is_file():
            raise ValueError("Im Ordner fehlt modul.py")
        name = "".join(c for c in quelle.name.lower() if c.isalnum() or c in "_-") or "trick"
        if name in self.tricks:
            raise ValueError(f"Einen Trick „{name}“ gibt es schon")
        ziel = self.fremd_ordner / name
        shutil.copytree(quelle, ziel, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        self.finden()
        t = self.tricks[name]
        t.status = ZUSTIMMUNG
        self._geaendert()
        return t

    # --- Takt, Menü, Ende -----------------------------------------------------
    def takt(self) -> None:
        for t in list(self.tricks.values()):
            if t.instanz is not None:
                t.instanz._takt()  # noqa: SLF001

    def menue_eintraege(self) -> list[tuple[str, Callable[[], None]]]:
        eintraege = []
        for t in self.tricks.values():
            if t.instanz is not None and t.instanz.aktiv:
                try:
                    eintraege += [(text, t.instanz._sicher(f))  # noqa: SLF001
                                  for text, f in t.instanz.menue_eintraege()]
                except Exception:  # noqa: BLE001
                    log.exception("menue_eintraege von %s", t.name)
        return eintraege

    def alle_beenden(self) -> None:
        for t in self.tricks.values():
            if t.instanz is not None:
                t.instanz.abschalten()
                t.instanz = None

    def _geaendert(self) -> None:
        if self.bei_aenderung:
            self.bei_aenderung()
