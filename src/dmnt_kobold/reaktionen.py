"""Reaktionen des Platzhalter-Blobs (M2).

Das ist eine Persönlichkeit im Kleinen: Sie hört Ereignisse und äußert
Wünsche über dieselbe Modul-Schnittstelle wie spätere Tricks. In M3 wandert
dieses Verhalten in ``persoenlichkeit.py`` im Avatar-Ordner.

Zum schnellen Ausprobieren: Umgebungsvariable ``DMNT_KOBOLD_SCHNELLTEST=1``
verkürzt die Wartezeiten (Tipp-Sitzung 10 s statt 60 s, Leerlauf 1 statt 5 min).
"""
from __future__ import annotations

import os
import random

from .bus import Ereignis
from .modul import Modul

SCHNELLTEST = os.environ.get("DMNT_KOBOLD_SCHNELLTEST") == "1"

LANGE_SITZUNG_S = 10.0 if SCHNELLTEST else 60.0
SCHLAF_NACH_MIN = 1 if SCHNELLTEST else 5
PAUSE_ABSTAND_S = 30.0 if SCHNELLTEST else 15 * 60.0
PROGRAMM_ABSTAND_S = 20.0 if SCHNELLTEST else 10 * 60.0

NOTIZEN = {"notepad.exe"}
RUHIG_ZUSCHAUEN = {"starcitizen.exe"}
MINECRAFT = {"minecraft.exe", "minecraftlauncher.exe"}

MINECRAFT_SPRUECHE = (
    "Oh, Minecraft! Baust du mir auch ein Haus?",
    "Pass auf die Creeper auf.",
    "Ich nehme ein Zimmer mit Blick auf Lava.",
)


class Reaktionen(Modul):
    name = "reaktionen"
    anzeigename = "Reaktionen"

    def __init__(self, bus, motor, rng: random.Random | None = None) -> None:
        super().__init__(bus, motor)
        self.rng = rng or random.Random()
        self._letzte: dict[str, float] = {}
        self._programm: str | None = None
        self._ruhig = False
        self._schlaeft = False

    # --- Hilfen --------------------------------------------------------------
    def _darf(self, schluessel: str, jetzt: float, abstand_s: float) -> bool:
        letzte = self._letzte.get(schluessel)
        if letzte is not None and jetzt - letzte < abstand_s:
            return False
        self._letzte[schluessel] = jetzt
        return True

    def _sagen(self, text: str, **kw) -> int | None:
        """Sprechblase – außer der Avatar soll gerade ruhig sein."""
        if self._ruhig and kw.get("prioritaet", 50) < 70:
            return None
        kw.setdefault("animation", "sprechen")
        kw.setdefault("prioritaet", 50)
        kw.setdefault("dauer_s", 6.0)
        return self.wunsch(text=text, **kw)

    def _ist_minecraft(self, name: str, titel: str) -> bool:
        return name in MINECRAFT or (name in ("javaw.exe", "java.exe") and "minecraft" in titel.lower())

    # --- Ereignisse ------------------------------------------------------------
    def on_event(self, e: Ereignis) -> None:
        n, d, t = e.name, e.daten, e.zeit

        if n == "maus.nah_am_avatar":
            self.wunsch("maus", animation="anschauen", prioritaet=30, dauer_s=None, aufheben=True)
        elif n == "maus.weg":
            self.zurueckziehen(unter="maus")
        elif n == "maus.wackelt":
            if self._darf("wackeln", t, 8.0):
                self.wunsch("wackeln", animation="erschrecken", text="Hey! Nicht so wild!",
                            prioritaet=45, dauer_s=2.5, ton="erschrecken")
            else:
                self.wunsch("wackeln", animation="erschrecken", prioritaet=45, dauer_s=1.0,
                            ton="erschrecken")
        elif n == "maus.klick":
            self.wunsch("klick", animation="freuen", prioritaet=35, dauer_s=1.2)

        elif n == "tastatur.tippt":
            self.wunsch("tippen", animation="sitzen", prioritaet=15, dauer_s=None, aufheben=True)
        elif n == "tastatur.schnell":
            if self._darf("schnell", t, 20 * 60.0):
                self._sagen("Wow, du tippst ja schnell!", animation="erschrecken", ton="erschrecken",
                            prioritaet=40, dauer_s=4.0, unter="tippen")
        elif n == "tastatur.pause":
            self.zurueckziehen(unter="tippen")
            sitzung = float(d.get("sitzung_s", 0))
            if sitzung >= LANGE_SITZUNG_S and self._darf("pause", t, PAUSE_ABSTAND_S):
                minuten = max(1, round(sitzung / 60))
                dauer = f"{minuten} Minute" if minuten == 1 else f"{minuten} Minuten"
                self._sagen(f"Kurz durchatmen? Du hast {dauer} am Stück getippt.",
                            knoepfe=("Mach ich", "Später"), prioritaet=60, dauer_s=15.0,
                            aufheben=True, unter="pause")
            else:
                self.wunsch("blick", animation="anschauen", prioritaet=25, dauer_s=2.0)

        elif n.startswith("leerlauf.") and n != "leerlauf.ende":
            if int(d.get("minuten", 0)) >= SCHLAF_NACH_MIN and not self._schlaeft:
                self._schlaeft = True
                self.wunsch("schlaf", animation="schlafen", prioritaet=20, dauer_s=None, aufheben=True)
        elif n == "leerlauf.ende":
            if self._schlaeft:
                self._schlaeft = False
                self.zurueckziehen(unter="schlaf")
                self.wunsch("schlaf", animation="freuen", prioritaet=35, dauer_s=1.5, ton="aufwachen")

        elif n == "programm.aktiv":
            self._programm_gewechselt(str(d.get("name", "")), str(d.get("titel", "")), t)

        elif n == "tageszeit.nachts":
            if self._darf("nachts", t, 6 * 3600.0):
                self._sagen("Schon ziemlich spät …", prioritaet=40, dauer_s=5.0)

    def _programm_gewechselt(self, name: str, titel: str, t: float) -> None:
        # Verhalten des alten Programms beenden
        self.zurueckziehen(unter="programm")
        self._ruhig = False

        if name in RUHIG_ZUSCHAUEN:
            # Geht an den rechten Rand, setzt sich, schaut zu, sagt nichts.
            self._ruhig = True
            self.wunsch("programm", animation="sitzen", ziel="rand_rechts", prioritaet=50,
                        dauer_s=None, aufheben=True)
        elif self._ist_minecraft(name, titel):
            if self._darf("minecraft", t, PROGRAMM_ABSTAND_S):
                self._sagen(self.rng.choice(MINECRAFT_SPRUECHE), animation="freuen", ton="freuen",
                            prioritaet=50, dauer_s=6.0, unter="spruch")
        elif name in NOTIZEN:
            if self._darf("notizen", t, PROGRAMM_ABSTAND_S):
                self._sagen("Oh, du schreibst was auf?", knoepfe=("Ja",), animation="freuen",
                            ton="freuen", prioritaet=50, dauer_s=8.0, unter="spruch")
        self._programm = name
