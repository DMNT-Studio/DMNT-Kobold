"""Datenhaltung: Nutzerdaten gehen nie verloren.

- ``atomar_schreiben``: erst in eine Temp-Datei im selben Ordner, ``fsync``,
  dann ``os.replace``. Die vorige Fassung bleibt als ``.bak`` liegen.
  Ein harter Kill mitten im Schreiben hinterlässt also immer eine heile Datei.
- ``Speicher``: ein JSON-Dokument pro Modul (``daten/<name>.json``), wie ein
  dict benutzbar. Jede Änderung wird sofort atomar geschrieben.
- ``Sicherung``: tägliche ZIP-Sicherung aller Nutzerdaten, die letzten 7
  bleiben. Dazu Export/Import als ZIP (vor jedem Import wird gesichert).

Ordner unter Dokumente\\DMNT-Kobold\\ (siehe pfade.py):
  daten/          Speicher der Module, einstellungen.json, zustand.json
  module/         selbst beigebrachte (fremde) Tricks
  sicherungen/    JAHR-MM-TT.zip (7 Stück)
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import tempfile
import zipfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator

log = logging.getLogger(__name__)

ANZAHL_SICHERUNGEN = 7
GESICHERTE_ORDNER = ("daten", "module")


# --- atomares Schreiben -----------------------------------------------------

def atomar_schreiben(pfad: Path, inhalt: bytes) -> None:
    pfad.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=pfad.name + ".", suffix=".tmp", dir=pfad.parent)
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(inhalt)
            f.flush()
            os.fsync(f.fileno())
        if pfad.exists():
            try:
                shutil.copy2(pfad, pfad.with_name(pfad.name + ".bak"))
            except OSError:
                log.warning("Konnte .bak von %s nicht anlegen", pfad.name)
        os.replace(tmp, pfad)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def json_schreiben(pfad: Path, daten: Any) -> None:
    atomar_schreiben(pfad, json.dumps(daten, ensure_ascii=False, indent=1).encode("utf-8"))


def json_laden(pfad: Path, standard: Any = None) -> Any:
    """Liest ``pfad``; ist die Datei kaputt oder fehlt, die ``.bak``."""
    for kandidat in (pfad, pfad.with_name(pfad.name + ".bak")):
        try:
            return json.loads(kandidat.read_text(encoding="utf-8"))
        except FileNotFoundError:
            continue
        except (OSError, ValueError):
            log.warning("%s unlesbar, versuche Ersatz", kandidat.name)
    return standard


# --- Speicher-API -----------------------------------------------------------

class Speicher:
    """Ein dict, das sich bei jeder Änderung sofort atomar auf die Platte schreibt.

    >>> s = Speicher(ordner / "erinnern.json")
    >>> s["liste"] = [...]        # geschrieben
    >>> s.get("liste", [])

    Verschachtelte Objekte, die direkt verändert werden (``s["liste"].append``),
    bemerkt der Speicher nicht – danach ``s.speichern()`` aufrufen oder neu zuweisen.
    """

    def __init__(self, pfad: Path) -> None:
        self.pfad = pfad
        geladen = json_laden(pfad, {})
        self._daten: dict[str, Any] = geladen if isinstance(geladen, dict) else {}

    def speichern(self) -> None:
        json_schreiben(self.pfad, self._daten)

    def __getitem__(self, schluessel: str) -> Any:
        return self._daten[schluessel]

    def __setitem__(self, schluessel: str, wert: Any) -> None:
        self._daten[schluessel] = wert
        self.speichern()

    def __delitem__(self, schluessel: str) -> None:
        del self._daten[schluessel]
        self.speichern()

    def __contains__(self, schluessel: object) -> bool:
        return schluessel in self._daten

    def __iter__(self) -> Iterator[str]:
        return iter(self._daten)

    def get(self, schluessel: str, standard: Any = None) -> Any:
        return self._daten.get(schluessel, standard)

    def setdefault(self, schluessel: str, standard: Any) -> Any:
        if schluessel not in self._daten:
            self[schluessel] = standard
        return self._daten[schluessel]

    def aktualisieren(self, **werte: Any) -> None:
        self._daten.update(werte)
        self.speichern()

    def als_dict(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._daten))


class Datenablage:
    """Wurzel der Nutzerdaten. Liefert Speicher je Name (zwischengespeichert)."""

    def __init__(self, wurzel: Path) -> None:
        self.wurzel = wurzel
        self.daten = wurzel / "daten"
        self.module = wurzel / "module"
        self.sicherungen = wurzel / "sicherungen"
        for o in (self.daten, self.module, self.sicherungen):
            o.mkdir(parents=True, exist_ok=True)
        self._speicher: dict[str, Speicher] = {}

    def speicher(self, name: str) -> Speicher:
        if name not in self._speicher:
            self._speicher[name] = Speicher(self.daten / f"{name}.json")
        return self._speicher[name]

    def neu_laden(self) -> None:
        """Nach einem Import: alle Speicher frisch von der Platte lesen."""
        for name, s in self._speicher.items():
            neu = Speicher(s.pfad)
            s._daten = neu._daten  # noqa: SLF001 – Objekte bleiben gültig (Module halten sie)


# --- Sicherung, Export, Import ----------------------------------------------

def _zip_schreiben(wurzel: Path, ziel: Path) -> None:
    ziel.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".zip.tmp", dir=ziel.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(tmp, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("dmnt-kobold-sicherung.json",
                       json.dumps({"erstellt": datetime.now().isoformat(timespec="seconds")}))
            for teil in GESICHERTE_ORDNER:
                ordner = wurzel / teil
                if not ordner.exists():
                    continue
                for datei in sorted(ordner.rglob("*")):
                    if datei.is_file() and "__pycache__" not in datei.parts \
                            and not datei.name.endswith((".tmp", ".bak")):
                        z.write(datei, datei.relative_to(wurzel).as_posix())
        os.replace(tmp, ziel)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


class Sicherung:
    def __init__(self, ablage: Datenablage, heute=date.today) -> None:
        self.ablage = ablage
        self._heute = heute

    def taeglich(self) -> Path | None:
        """Legt die Sicherung von heute an, falls sie fehlt. Räumt alte weg."""
        ziel = self.ablage.sicherungen / f"{self._heute().isoformat()}.zip"
        if ziel.exists():
            return None
        _zip_schreiben(self.ablage.wurzel, ziel)
        self._aufraeumen()
        log.info("Tägliche Sicherung %s", ziel.name)
        return ziel

    def _aufraeumen(self) -> None:
        alle = sorted(self.ablage.sicherungen.glob("????-??-??.zip"))
        for alt in alle[:-ANZAHL_SICHERUNGEN]:
            try:
                alt.unlink()
            except OSError:
                log.warning("Alte Sicherung %s nicht löschbar", alt.name)

    def exportieren(self, ziel: Path) -> None:
        _zip_schreiben(self.ablage.wurzel, ziel)

    def importieren(self, quelle: Path) -> None:
        """Ersetzt daten/ und module/ durch den Inhalt der ZIP. Vorher wird der
        aktuelle Stand als ``vor-import-<zeit>.zip`` gesichert."""
        with zipfile.ZipFile(quelle) as z:
            namen = z.namelist()
            if "dmnt-kobold-sicherung.json" not in namen:
                raise ValueError("Keine DMNT-Kobold-Sicherung")
            for n in namen:
                teile = Path(n).parts
                if n.startswith("/") or ".." in teile or (teile and teile[0] not in
                                                           GESICHERTE_ORDNER + ("dmnt-kobold-sicherung.json",)):
                    raise ValueError(f"Unerwarteter Eintrag in der Sicherung: {n}")
            stempel = datetime.now().strftime("%Y-%m-%d_%H%M%S")
            _zip_schreiben(self.ablage.wurzel, self.ablage.sicherungen / f"vor-import-{stempel}.zip")
            entpackt = Path(tempfile.mkdtemp(dir=self.ablage.wurzel, prefix="import."))
            try:
                z.extractall(entpackt)
                for teil in GESICHERTE_ORDNER:
                    alt = self.ablage.wurzel / teil
                    neu = entpackt / teil
                    if not neu.exists():
                        neu.mkdir()
                    weg = self.ablage.wurzel / f".{teil}.alt"
                    shutil.rmtree(weg, ignore_errors=True)
                    if alt.exists():
                        os.replace(alt, weg)
                    os.replace(neu, alt)
                    shutil.rmtree(weg, ignore_errors=True)
            finally:
                shutil.rmtree(entpackt, ignore_errors=True)
        self.ablage.neu_laden()
        log.info("Import aus %s", quelle.name)
