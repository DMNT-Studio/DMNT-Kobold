"""Trick „Erinnern“: Erinnerungen per Strg+Alt+E oder Tray-Symbol → Erinnern.

Jede Erinnerung wird sofort atomar gespeichert. Nach einem Absturz oder
harten Beenden erscheint sie trotzdem pünktlich; was in der Zwischenzeit
fällig wurde, kommt beim nächsten Start sofort (mit „fällig war …“).

Die Sprechblase bleibt, bis man „Erledigt“ oder „In 10 min“ klickt.
Wegklicken zählt als erledigt.
"""
from __future__ import annotations

import time
import uuid
from datetime import datetime

from dmnt_kobold.modul import Modul
from dmnt_kobold.zeitangabe import zeit_parsen, zeit_text

PRIORITAET = 85
SPAETER_S = 600
KUERZEL = "Strg+Alt+E"


class Erinnern(Modul):
    anzeigename = "Erinnern"
    beschreibung = f"Erinnert dich pünktlich an Dinge. Neue Erinnerung: {KUERZEL} oder über das Tray-Symbol."

    def __init__(self, bus, motor, umgebung=None) -> None:
        super().__init__(bus, motor, umgebung)
        self._gezeigt: dict[str, int] = {}       # Erinnerungs-ID → Wunsch-ID
        self._karte = None
        self.kuerzel_frei = self.hotkey(KUERZEL, self.eingabe_oeffnen)

    # --- Daten ---------------------------------------------------------------
    def liste(self) -> list[dict]:
        return list(self.speicher.get("liste", []))

    def anlegen(self, text: str, faellig: float) -> dict:
        e = {"id": uuid.uuid4().hex[:12], "text": text.strip(), "faellig": float(faellig),
             "angelegt": time.time()}
        self.speicher["liste"] = self.liste() + [e]            # sofort auf der Platte
        return e

    def entfernen(self, eid: str) -> None:
        self.speicher["liste"] = [e for e in self.liste() if e["id"] != eid]
        wid = self._gezeigt.pop(eid, None)
        if wid is not None:
            self.zurueckziehen(wid)

    def verschieben(self, eid: str, faellig: float) -> None:
        neu = []
        for e in self.liste():
            if e["id"] == eid:
                e = dict(e, faellig=faellig)
            neu.append(e)
        self.speicher["liste"] = neu
        self._gezeigt.pop(eid, None)

    # --- Takt ------------------------------------------------------------------
    def jede_sekunde(self, jetzt: float | None = None) -> None:
        jetzt = time.time() if jetzt is None else jetzt
        for e in sorted(self.liste(), key=lambda x: x["faellig"]):
            if e["faellig"] <= jetzt and e["id"] not in self._gezeigt:
                self._zeigen(e, jetzt)

    def _zeigen(self, e: dict, jetzt: float) -> None:
        text = f"Erinnerung: {e['text']}"
        if jetzt - e["faellig"] > 120:
            text += f"\n(fällig war {zeit_text(datetime.fromtimestamp(e['faellig']))})"
        eid = e["id"]
        self._gezeigt[eid] = self.wunsch(
            unter=eid, animation="sprechen", text=text, knoepfe=("Erledigt", "In 10 min"),
            prioritaet=PRIORITAET, dauer_s=None, aufheben=True, ton="freuen",
            beim_knopf=lambda knopf, eid=eid: self._knopf(eid, knopf))

    def _knopf(self, eid: str, knopf: str) -> None:
        if knopf == "In 10 min":
            self.verschieben(eid, time.time() + SPAETER_S)
        else:
            self.entfernen(eid)

    def on_event(self, e) -> None:
        if e.name == "sprechblase.zu" and str(e.daten.get("quelle", "")).startswith(self.name + ":"):
            self.entfernen(e.daten["quelle"].split(":", 1)[1])

    # --- Oberfläche --------------------------------------------------------------
    def menue_eintraege(self):
        return [("Erinnern …", self.eingabe_oeffnen)]

    def eingabe_oeffnen(self) -> None:
        from .karte import ErinnernKarte  # Qt erst bei Bedarf

        if self._karte is not None:
            self._karte.raise_()
            self._karte.activateWindow()
            return
        self._karte = ErinnernKarte(self)
        self._karte.geschlossen.connect(self._karte_zu)
        pos = getattr(self.umgebung, "karten_punkt", None)
        self._karte.zeigen_bei(pos() if callable(pos) else None)

    def _karte_zu(self) -> None:
        self._karte = None

    def merken(self, text: str, wann: str) -> str | None:
        """Aus der Karte: liefert Fehlermeldung oder None."""
        if not text.strip():
            return "Woran denn?"
        ziel = zeit_parsen(wann)
        if ziel is None:
            return "Die Zeit verstehe ich nicht. Beispiele: 10 min, 14:30, morgen 9"
        self.anlegen(text, ziel.timestamp())
        self.wunsch(unter="ok", animation="freuen", text=f"Mach ich. {zeit_text(ziel)}.",
                    prioritaet=60, dauer_s=3.0)
        return None

    def beenden(self) -> None:
        if self._karte is not None:
            self._karte.close()
