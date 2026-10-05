"""Trick „Pausen anmahnen“: Nach längerer Arbeit am Stück schlägt der Kobold
eine Pause vor.

Gezählt wird Zeit mit Eingaben. Fünf Minuten ohne Eingabe gelten als Pause
und setzen den Zähler zurück. Bei „Nicht stören“ wartet die Mahnung.
Der Zählerstand wird jede Minute gespeichert; war das Programm länger als
fünf Minuten aus, beginnt die Zählung neu.
"""
from __future__ import annotations

import time

from dmnt_kobold.modul import Modul

PAUSE_AB_MIN = 5
STANDARD_INTERVALL_MIN = 50
SPAETER_S = 600
PRIORITAET = 65          # unter „Nicht stören“-Schwelle → wartet bei Nicht stören


class Pausen(Modul):
    anzeigename = "Pausen anmahnen"
    beschreibung = f"Schlägt nach {STANDARD_INTERVALL_MIN} Minuten am Stück eine Pause vor."

    def __init__(self, bus, motor, umgebung=None) -> None:
        super().__init__(bus, motor, umgebung)
        self.leerlauf_min = 0
        self.mahnung: int | None = None
        stand = self.speicher.get("stand", {})
        if time.time() - stand.get("zeit", 0) < PAUSE_AB_MIN * 60:
            self.aktiv_s = float(stand.get("aktiv_s", 0))
        else:
            self.aktiv_s = 0.0
        self._seit_speichern = 0

    @property
    def intervall_s(self) -> float:
        return float(self.speicher.get("intervall_min", STANDARD_INTERVALL_MIN)) * 60

    def on_event(self, e) -> None:
        if e.name.startswith("leerlauf.") and e.name != "leerlauf.ende":
            self.leerlauf_min = int(e.daten.get("minuten", 0))
            if self.leerlauf_min >= PAUSE_AB_MIN:
                self._pause_gemacht()
        elif e.name == "leerlauf.ende":
            self.leerlauf_min = 0
        elif e.name == "sprechblase.zu" and e.daten.get("quelle") == f"{self.name}:mahnung":
            self.mahnung = None
            self.aktiv_s = self.intervall_s - SPAETER_S

    def jede_sekunde(self) -> None:
        if self.leerlauf_min == 0:
            self.aktiv_s += 1
        self._seit_speichern += 1
        if self._seit_speichern >= 60:
            self._speichern()
        if self.aktiv_s >= self.intervall_s and self.mahnung is None:
            minuten = int(self.aktiv_s // 60)
            self.mahnung = self.wunsch(
                unter="mahnung", animation="sprechen",
                text=f"Du bist seit {minuten} Minuten dran. Zeit für eine kurze Pause?",
                knoepfe=("Mach ich", "In 10 min"), prioritaet=PRIORITAET, dauer_s=None,
                aufheben=True, beim_knopf=self._knopf)

    def _knopf(self, knopf: str) -> None:
        self.mahnung = None
        if knopf == "Mach ich":
            self.aktiv_s = 0.0
        else:
            self.aktiv_s = self.intervall_s - SPAETER_S
        self._speichern()

    def _pause_gemacht(self) -> None:
        self.aktiv_s = 0.0
        if self.mahnung is not None:
            self.zurueckziehen(unter="mahnung")
            self.mahnung = None
        self._speichern()

    def _speichern(self) -> None:
        self._seit_speichern = 0
        self.speicher["stand"] = {"aktiv_s": round(self.aktiv_s), "zeit": time.time()}

    def beenden(self) -> None:
        self._speichern()
