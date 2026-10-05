"""Eingefrorene Referenz: Reaktionen und DMNT-9000-Persönlichkeit vor der Umstellung auf
verhalten.json (Stand 0.4.0). Nur für den Migrationstest – nicht ändern."""
from __future__ import annotations

import os
import random

from dmnt_kobold.bus import Ereignis
from dmnt_kobold.modul import Modul

SCHNELLTEST = os.environ.get("DMNT_KOBOLD_SCHNELLTEST") == "1"

LANGE_SITZUNG_S = 10.0 if SCHNELLTEST else 60.0
SCHLAF_NACH_MIN = 1 if SCHNELLTEST else 5
PAUSE_ABSTAND_S = 30.0 if SCHNELLTEST else 15 * 60.0
PROGRAMM_ABSTAND_S = 20.0 if SCHNELLTEST else 10 * 60.0

NOTIZEN = {"notepad.exe"}
RUHIG_ZUSCHAUEN = {"starcitizen.exe"}
MINECRAFT = {"minecraft.exe", "minecraftlauncher.exe"}


class Reaktionen(Modul):
    name = "reaktionen"
    anzeigename = "Reaktionen"

    #: Programme, deren Laufen (nicht nur Vordergrund) beobachtet wird
    BEOBACHTETE_PROGRAMME = RUHIG_ZUSCHAUEN

    # --- zum Überschreiben in der Persönlichkeit ------------------------------
    TEXTE: dict[str, object] = {
        "wackeln": "Hey! Nicht so wild!",
        "schnell": "Wow, du tippst ja schnell!",
        "pause": "Kurz durchatmen? Du hast {dauer} am Stück getippt.",
        "notizen": "Oh, du schreibst was auf?",
        "nachts": "Schon ziemlich spät …",
        "minecraft": (
            "Oh, Minecraft! Baust du mir auch ein Haus?",
            "Pass auf die Creeper auf.",
            "Ich nehme ein Zimmer mit Blick auf Lava.",
        ),
        "star_citizen": None,     # Satz beim Start, danach still
        "aufwachen": None,
        "spaeter": None,
        "musik": None,            # Satz, wenn er die Kopfhörer aufsetzt
    }
    ANIM_WACKELN = "erschrecken"
    ANIM_ENTTAEUSCHT = "anschauen"
    ANIM_ZUSCHAUEN = "sitzen"     # bei Programmen, denen er still zuschaut

    def __init__(self, bus, motor, rng: random.Random | None = None) -> None:
        super().__init__(bus, motor)
        self.rng = rng or random.Random()
        self._letzte: dict[str, float] = {}
        self._programm: str | None = None
        self._ruhig = False
        self._schlaeft = False

    # --- Hilfen --------------------------------------------------------------
    def text(self, schluessel: str) -> str | None:
        wert = self.TEXTE.get(schluessel, Reaktionen.TEXTE.get(schluessel))
        if isinstance(wert, (tuple, list)):
            return self.rng.choice(wert)
        return wert  # type: ignore[return-value]

    def _darf(self, schluessel: str, jetzt: float, abstand_s: float) -> bool:
        letzte = self._letzte.get(schluessel)
        if letzte is not None and jetzt - letzte < abstand_s:
            return False
        self._letzte[schluessel] = jetzt
        return True

    def _sagen(self, text: str | None, **kw) -> int | None:
        """Sprechblase – außer der Avatar soll gerade ruhig sein."""
        if not text or (self._ruhig and kw.get("prioritaet", 50) < 70):
            return None
        kw.setdefault("animation", "sprechen")
        kw.setdefault("prioritaet", 50)
        kw.setdefault("dauer_s", 6.0)
        return self.wunsch(text=text, **kw)

    def _ist_minecraft(self, name: str, titel: str) -> bool:
        return name in MINECRAFT or (name in ("javaw.exe", "java.exe") and "minecraft" in titel.lower())

    def _pause_knopf(self, knopf: str) -> None:
        if knopf == "Später":
            self.wunsch("pause", animation=self.ANIM_ENTTAEUSCHT, prioritaet=45, dauer_s=2.5,
                        text=self.text("spaeter"))

    # --- Ereignisse ------------------------------------------------------------
    def on_event(self, e: Ereignis) -> None:
        n, d, t = e.name, e.daten, e.zeit

        if n == "maus.nah_am_avatar":
            self.wunsch("maus", animation="anschauen", prioritaet=30, dauer_s=None, aufheben=True)
        elif n == "maus.weg":
            self.zurueckziehen(unter="maus")
        elif n == "maus.wackelt":
            if self._darf("wackeln", t, 8.0):
                self.wunsch("wackeln", animation=self.ANIM_WACKELN, text=self.text("wackeln"),
                            prioritaet=45, dauer_s=2.5, ton="erschrecken")
            else:
                self.wunsch("wackeln", animation=self.ANIM_WACKELN, prioritaet=45, dauer_s=1.2,
                            ton="erschrecken")
        elif n == "maus.klick":
            self.wunsch("klick", animation="freuen", prioritaet=35, dauer_s=1.2)

        elif n == "tastatur.tippt":
            self.wunsch("tippen", animation="sitzen", prioritaet=15, dauer_s=None, aufheben=True)
        elif n == "tastatur.schnell":
            if self._darf("schnell", t, 20 * 60.0):
                self._sagen(self.text("schnell"), animation="erschrecken", ton="erschrecken",
                            prioritaet=40, dauer_s=4.0, unter="tippen")
        elif n == "tastatur.pause":
            self.zurueckziehen(unter="tippen")
            sitzung = float(d.get("sitzung_s", 0))
            if sitzung >= LANGE_SITZUNG_S and self._darf("pause", t, PAUSE_ABSTAND_S):
                minuten = max(1, round(sitzung / 60))
                dauer = f"{minuten} Minute" if minuten == 1 else f"{minuten} Minuten"
                vorlage = self.text("pause") or ""
                self._sagen(vorlage.format(dauer=dauer), knoepfe=("Mach ich", "Später"),
                            prioritaet=60, dauer_s=15.0, aufheben=True, unter="pause",
                            beim_knopf=self._pause_knopf)
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
                self.wunsch("schlaf", animation="freuen", prioritaet=35, dauer_s=1.5, ton="aufwachen",
                            text=self.text("aufwachen"))

        elif n == "programm.aktiv":
            self._programm_gewechselt(str(d.get("name", "")), str(d.get("titel", "")), t)
        elif n == "programm.gestartet" and d.get("name") in RUHIG_ZUSCHAUEN:
            # Sagt höchstens einen Satz, geht an den rechten Rand, schaut still zu –
            # solange das Programm läuft, egal welches Fenster vorne ist.
            if self._darf("star_citizen", t, PROGRAMM_ABSTAND_S):
                self._sagen(self.text("star_citizen"), prioritaet=55, dauer_s=4.0, unter="zuschauen")
            self._ruhig = True
            self.wunsch("zuschauen", animation=self.ANIM_ZUSCHAUEN, ziel="rand_rechts", prioritaet=50,
                        dauer_s=None, aufheben=True)
        elif n == "programm.beendet" and d.get("name") in RUHIG_ZUSCHAUEN:
            self._ruhig = False
            self.zurueckziehen(unter="zuschauen")

        elif n == "audio.laeuft":
            self.zubehoer("kopfhoerer", True)
            if self._darf("musik", t, 30 * 60.0):
                self._sagen(self.text("musik"), animation="freuen", prioritaet=35, dauer_s=3.0)
            self.wunsch("musik", animation="freuen", prioritaet=32, dauer_s=1.5)
        elif n == "audio.still":
            self.zubehoer("kopfhoerer", False)

        elif n == "tageszeit.nachts":
            if self._darf("nachts", t, 6 * 3600.0):
                self._sagen(self.text("nachts"), prioritaet=40, dauer_s=5.0)

    def _programm_gewechselt(self, name: str, titel: str, t: float) -> None:
        if self._ist_minecraft(name, titel):
            if self._darf("minecraft", t, PROGRAMM_ABSTAND_S):
                self._sagen(self.text("minecraft"), animation="freuen", ton="freuen",
                            prioritaet=50, dauer_s=6.0, unter="spruch")
        elif name in NOTIZEN:
            if self._darf("notizen", t, PROGRAMM_ABSTAND_S):
                self._sagen(self.text("notizen"), knoepfe=("Ja",), animation="freuen",
                            ton="freuen", prioritaet=50, dauer_s=8.0, unter="spruch")
        self._programm = name


class Persoenlichkeit(Reaktionen):
    name = "dmnt9000"
    anzeigename = "DMNT 9000"

    TEXTE = {
        "wackeln": "Vorsicht. Meine Optik ist frisch kalibriert.",
        "schnell": "Beeindruckende Eingaberate.",
        "pause": "Wartungspause empfohlen: {dauer} Dauerbetrieb an der Tastatur.",
        "notizen": "Logbuch-Eintrag? Ich höre zu.",
        "nachts": "Nachtschicht im Asteroidenfeld? Denk an deinen Schlaf.",
        "minecraft": (
            "Bergbau ohne Schiff? Mutig.",
            "Erzvorkommen geortet. Viel Erfolg beim Schürfen.",
            "Ich empfehle Diamanten. Aus Gründen.",
        ),
        "star_citizen": "Schiffssysteme online. Ich halte mich im Hintergrund.",
        "aufwachen": "Systeme reaktiviert.",
        "spaeter": "Verstanden. Ich notiere: später.",
        "musik": "Audiosignal erkannt. Kopfhörer aktiv.",
    }
    ANIM_WACKELN = "unzufrieden"
    ANIM_ENTTAEUSCHT = "unzufrieden"
    ANIM_ZUSCHAUEN = "zuschauen"
