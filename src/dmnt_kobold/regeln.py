"""Regel-Persönlichkeit: wertet die ``verhalten.json`` eines Avatars aus.

Ablauf je Ereignis (Regeln in Listen-Reihenfolge):
  Ereignis passt (eine der Bedingungen in „wenn“) → Regel aktiv → ihre Gruppe hat bei
  diesem Ereignis noch nicht gefeuert → ein „bleiben“-Wunsch der Regel läuft nicht
  schon → Abklingzeit vorbei → Chance gewürfelt → Aktionen ausführen.

Aus den Aktionen entsteht höchstens ein Wunsch an den Motor (Animation, Spruch, Ton,
Ziel, Hüpfen, Innenleben), Quelle ``<name>:<regel-id>``. Nebenher: Zubehör an/aus, andere Regeln
zurückziehen, still werden. Was der Katalog nicht kennt, wird ignoriert –
``katalog.pruefen`` meldet es schon beim Bauen.
"""
from __future__ import annotations

import json
import logging
import random
import re
from pathlib import Path

from . import katalog
from .bus import Ereignis
from .modul import Modul

log = logging.getLogger(__name__)

STANDARD_DATEI = Path(__file__).resolve().parent / "standard_verhalten.json"
SCHNELLTEST_TEILER = 30          # Abklingzeiten im Schnelltest (15 min → 30 s)
ZIELE = {"links": "rand_links", "rechts": "rand_rechts", "mitte": "mitte"}
_PLATZHALTER = re.compile(r"\{(\w+)\}")


def standard_verhalten() -> dict:
    """Verhalten ohne eigene verhalten.json (Platzhalter-Blob, Vorlage für neue Avatare)."""
    return json.loads(STANDARD_DATEI.read_text(encoding="utf-8"))


def fuellen(text: str, werte: dict[str, str]) -> str:
    return _PLATZHALTER.sub(lambda m: werte.get(m.group(1), m.group(0)), text)


class RegelPersoenlichkeit(Modul):
    name = "verhalten"
    anzeigename = "Verhalten"

    def __init__(self, bus, motor, verhalten: dict | None = None, rng: random.Random | None = None, *,
                 name: str | None = None, werte: katalog.Werte | None = None) -> None:
        if name:
            self.name = name
        super().__init__(bus, motor)
        self.rng = rng or random.Random()
        verhalten = verhalten if verhalten is not None else standard_verhalten()
        self.werte = werte or katalog.Werte(verhalten.get("werte"))
        self.regeln: list[dict] = [r for r in verhalten.get("regeln", [])
                                   if isinstance(r, dict) and isinstance(r.get("id"), str)]
        self._programme = katalog.beobachtete_programme(verhalten)
        self._letzte: dict[str, float] = {}
        self._ruhig: set[str] = set()        # Regeln, die gerade „ruhig“ verlangen

    @property
    def BEOBACHTETE_PROGRAMME(self) -> set[str]:  # noqa: N802 – Schnittstelle wie bei Persönlichkeiten
        return self._programme

    def laeuft(self, regel_id: str) -> bool:
        quelle = f"{self.name}:{regel_id}"
        return any(w.quelle == quelle for w in self.motor.wuensche())

    # --- Auswertung ------------------------------------------------------------------
    def on_event(self, e: Ereignis) -> None:
        treffer = katalog.zuordnen(e.name)
        if treffer is None:
            return
        art, extra = treffer
        daten = {**extra, **e.daten}
        gefeuert: set[str] = set()
        for r in self.regeln:
            if not r.get("aktiv", True):
                continue
            gruppe = r.get("gruppe") or ""
            if gruppe and gruppe in gefeuert:
                continue
            if not any(self._passt(b, art, daten) for b in katalog.bedingungen(r)):
                continue
            rid = r["id"]
            if _hat(r, "bleiben") and self.laeuft(rid):
                continue
            abklingzeit = float(r.get("abklingzeit_s", 0) or 0)
            if katalog.SCHNELLTEST:
                abklingzeit /= SCHNELLTEST_TEILER
            letzte = self._letzte.get(rid)
            if abklingzeit > 0 and letzte is not None and e.zeit - letzte < abklingzeit:
                continue
            chance = float(r.get("chance", 1.0))
            if chance < 1.0 and self.rng.random() >= chance:
                continue
            self._letzte[rid] = e.zeit
            if gruppe:
                gefeuert.add(gruppe)
            self._ausfuehren(r, art.name, daten)

    def _zahl(self, wert) -> float:
        if isinstance(wert, str) and wert.startswith("$"):
            return float(self.werte[wert[1:]])
        return float(wert)

    def _passt(self, b: dict, art: katalog.EreignisDef, daten: dict) -> bool:
        if b.get("ereignis") != art.name:
            return False
        for p in art.bedingungen + katalog.ALLGEMEINE_BEDINGUNGEN:
            soll = b.get(p.name)
            if soll in (None, "", []):
                continue
            ist = daten.get(p.feld)
            if p.vergleich == "laeuft":
                ok = self.laeuft(str(soll))
            elif p.vergleich == "eine_von":
                ok = str(ist).lower() in {str(s).lower() for s in soll}
            elif p.vergleich == "enthaelt":
                ok = str(soll).lower() in str(ist or "").lower()
            elif p.vergleich == "ab":
                try:
                    ok = float(ist) >= self._zahl(soll)
                except (TypeError, ValueError, KeyError):
                    ok = False
            elif p.vergleich == "regel":
                ok = ist == f"{self.name}:{soll}"
            else:
                ok = str(ist).lower() == str(soll).lower()
            if not ok:
                return False
        return True

    def _ausfuehren(self, r: dict, ereignis: str, daten: dict) -> None:
        rid = r["id"]
        wunsch: dict = {}
        bleiben = trotz_ruhe = False
        eigene_dauer: float | None = None
        for a in r.get("dann", []):
            art = a.get("aktion")
            if art == "zurueckziehen":
                for ziel in a.get("regeln", []):
                    self.zurueckziehen(unter=ziel)
                    self._ruhig.discard(ziel)
            elif art == "zubehoer" and a.get("name"):
                self.zubehoer(katalog.kennung(a["name"]) or a["name"], bool(a.get("an", True)))
            elif art == "ruhig":
                self._ruhig.add(rid)
            elif art == "bleiben":
                bleiben = True
            elif art == "animation" and a.get("name"):
                wunsch["animation"] = a["name"]
            elif art == "sprechen" and a.get("texte"):
                texte = list(a["texte"])
                text = texte[0] if len(texte) == 1 else self.rng.choice(texte)
                wunsch["text"] = fuellen(text, katalog.platzhalter(ereignis, daten))
                wunsch["knoepfe"] = tuple(a.get("knoepfe", ()))[:2]
                trotz_ruhe = bool(a.get("trotz_ruhe", False))
            elif art == "ton" and a.get("name"):
                wunsch["ton"] = a["name"]
            elif art == "gehen_zu" and a.get("ziel") in ZIELE:
                wunsch["ziel"] = ZIELE[a["ziel"]]
            elif art == "freuen_huepfend":
                wunsch["bewegung"] = "freuen_huepfend"
                if a.get("dauer_s") is not None:
                    try:
                        eigene_dauer = self._zahl(a["dauer_s"])
                    except (TypeError, ValueError, KeyError):
                        pass
            elif art == "innen" and isinstance(a.get("variante"), str) and a["variante"].strip("@ "):
                wunsch["innen"] = a["variante"].strip("@ ")
            elif art == "effekt" and isinstance(a.get("name"), str) and a["name"]:
                wunsch["effekt"] = a["name"]
        if not wunsch:
            return
        prioritaet = int(r.get("prioritaet", 50))
        if ("text" in wunsch and not trotz_ruhe and prioritaet < katalog.LEISE_AB
                and self._ruhig - {rid}):
            return                                   # Avatar soll gerade still sein
        if "animation" not in wunsch:
            wunsch["animation"] = "sprechen" if "text" in wunsch else                 "freuen" if wunsch.get("bewegung") == "freuen_huepfend" else "ruhe"
        if bleiben:
            dauer, aufheben = None, True
        else:
            dauer = r.get("dauer_s", 5.0)
            dauer = None if dauer is None else float(dauer)
            if eigene_dauer is not None and eigene_dauer > 0:
                dauer = eigene_dauer
            aufheben = bool(r.get("aufheben", False))
        self.wunsch(rid, prioritaet=prioritaet, dauer_s=dauer, aufheben=aufheben, **wunsch)


def _hat(regel: dict, aktion: str) -> bool:
    return any(isinstance(a, dict) and a.get("aktion") == aktion for a in regel.get("dann", []))
