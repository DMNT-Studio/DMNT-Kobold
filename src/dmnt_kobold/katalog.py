"""Katalog des Sockels: was es gibt – Ereignisse, Aktionen, Werte.

Einzige Quelle der Wahrheit fürs Verhalten. Der Sockel selbst kennt keine
konkreten Regeln; die liegen beim Avatar (``verhalten.json``) und werden von
``regeln.RegelPersoenlichkeit`` ausgewertet. Beobachter, Eigenleben und Motor
holen ihre Standardwerte von hier.

Reine Daten und Logik, kein Qt – nutzbar im Kobold, im Bau-Werkzeug und im
Avatar-Editor. ``python -m dmnt_kobold --katalog`` gibt alles als Markdown aus.

Format ``verhalten.json``::

    {"werte": {"einschlafen_nach_min": 8},          # nur Abweichungen vom Standard
     "regeln": [{"id": "minecraft", "aktiv": true,
                 "wenn": {"ereignis": "programm.aktiv", "programm": ["javaw.exe"],
                          "titel_enthaelt": "Minecraft"},     # oder Liste = „oder“
                 "dann": [{"aktion": "animation", "name": "freuen"},
                          {"aktion": "sprechen", "texte": ["Text A", "Text B"]}],
                 "prioritaet": 50, "abklingzeit_s": 600, "chance": 1.0, "dauer_s": 6}]}
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Iterable

SCHNELLTEST = os.environ.get("DMNT_KOBOLD_SCHNELLTEST") == "1"

LEISE_AB = 70                 # „Nicht stören“ und Stillsein lassen Wünsche ab hier durch
PRIORITAET_MAX = 99           # 100 = Nutzer-Eingriff (regelt das Overlay)
PRIORITAETEN = (
    ("100", "Nutzer-Eingriff (Ziehen, Rechtsklick, Einrichten) – nur der Sockel"),
    ("70–90", "wichtige Modul-Wünsche (Erinnerungen); kommen auch bei „Nicht stören“ durch"),
    ("30–60", "Persönlichkeit, Reaktionen (Regeln eines Avatars)"),
    ("0–20", "Eigenleben (läuft, wenn niemand etwas will)"),
)


# --- Bausteine ----------------------------------------------------------------------

@dataclass(frozen=True)
class Param:
    """Parameter einer Bedingung oder Aktion.

    typ: text, liste (eine Zeile je Eintrag), zahl, bool, auswahl, sowie Auswahl aus dem
    Avatar: animation, ton, zubehoer, innen (Variante des Innenlebens), regel (eine Regel-id),
    regeln (Liste von Regel-ids).
    Bei Bedingungen: ``feld`` = Ereignisdaten-Feld, ``vergleich`` = gleich, enthaelt,
    ab (Zahl ≥), eine_von (Liste), regel (Sprechblase dieser Regel), laeuft.
    Zahlen dürfen auf einen Wert verweisen: "$einschlafen_nach_min".
    """
    name: str
    typ: str
    beschreibung: str
    pflicht: bool = False
    feld: str = ""
    vergleich: str = "gleich"
    auswahl: tuple[str, ...] = ()
    standard: object = None


@dataclass(frozen=True)
class EreignisDef:
    name: str
    beschreibung: str
    bedingungen: tuple[Param, ...] = ()
    daten: tuple[str, ...] = ()              # was das Ereignis mitbringt
    platzhalter: tuple[tuple[str, str], ...] = ()   # {name} in Sprüchen
    muster: str = ""                         # ausgelöster Name, z. B. "leerlauf.<minuten>"


@dataclass(frozen=True)
class AktionDef:
    name: str
    beschreibung: str
    parameter: tuple[Param, ...] = ()
    wunsch: bool = True                      # erzeugt (mit) einen Wunsch an den Motor


@dataclass(frozen=True)
class WertDef:
    id: str
    beschreibung: str
    einheit: str
    standard: float
    min: float
    max: float
    bereich: str
    ganzzahl: bool = False
    schnelltest: float | None = None         # mit DMNT_KOBOLD_SCHNELLTEST=1

    @property
    def wirksamer_standard(self) -> float:
        wert = self.schnelltest if SCHNELLTEST and self.schnelltest is not None else self.standard
        return int(wert) if self.ganzzahl else float(wert)


def _programm(pflicht: bool = False) -> Param:
    return Param("programm", "liste", "Programmdateien, eine je Zeile (z. B. notepad.exe). "
                 "Groß/klein egal.", pflicht=pflicht, feld="name", vergleich="eine_von")


def _regel_quelle(text: str) -> Param:
    return Param("regel", "regel", text, feld="quelle", vergleich="regel")


TAGESZEITEN = ("morgens", "mittags", "abends", "nachts")

# --- Ereignisse: alles, was der Sockel heute wirklich auslöst -----------------------

EREIGNISSE: tuple[EreignisDef, ...] = (
    EreignisDef("maus.nah_am_avatar", "Der Mauszeiger kommt in die Nähe des Avatars.",
                daten=("entfernung",)),
    EreignisDef("maus.weg", "Der Mauszeiger entfernt sich wieder vom Avatar."),
    EreignisDef("maus.wackelt", "Jemand wackelt mit der Maus dicht am Avatar hin und her."),
    EreignisDef("maus.klick", "Kurzer Klick auf den Avatar (ohne Ziehen)."),
    EreignisDef("tastatur.tippt", "Eine Tipp-Sitzung beginnt (erkannt ohne Tastatur-Hook)."),
    EreignisDef("tastatur.schnell", "In der Sitzung wird einige Sekunden lang sehr schnell getippt "
                "(einmal je Sitzung)."),
    EreignisDef("tastatur.pause", "Eine Tipp-Sitzung endet, weil eine Weile nichts kam.",
                bedingungen=(Param("sitzung_ab_s", "zahl", "Nur wenn die Sitzung mindestens so lang war "
                                   "(Sekunden).", feld="sitzung_s", vergleich="ab"),),
                daten=("sitzung_s",),
                platzhalter=(("dauer", "Länge der Sitzung, z. B. „12 Minuten“"),)),
    EreignisDef("leerlauf", "Jede volle Minute ohne Eingabe (Maus und Tastatur).",
                bedingungen=(Param("ab_minuten", "zahl", "Nur ab so vielen Minuten Leerlauf.",
                                   feld="minuten", vergleich="ab"),),
                daten=("minuten",), platzhalter=(("minuten", "Minuten ohne Eingabe"),),
                muster="leerlauf.<minuten>"),
    EreignisDef("leerlauf.ende", "Nach einem Leerlauf (mindestens eine Minute) kommt wieder eine Eingabe.",
                daten=("minuten",), platzhalter=(("minuten", "so lange war Ruhe"),)),
    EreignisDef("programm.aktiv", "Ein anderes Programm kommt in den Vordergrund.",
                bedingungen=(_programm(),
                             Param("titel_enthaelt", "text", "Fenstertitel enthält diesen Text (Groß/klein "
                                   "egal). Der Titel wird nie gespeichert.", feld="titel", vergleich="enthaelt")),
                daten=("name", "titel", "vorher"),
                platzhalter=(("programm", "Name der Programmdatei"),)),
    EreignisDef("programm.gestartet", "Ein beobachtetes Programm läuft jetzt – egal, welches Fenster vorne "
                "ist. Beobachtet wird, was in solchen Regeln steht.",
                bedingungen=(_programm(pflicht=True),), daten=("name",),
                platzhalter=(("programm", "Name der Programmdatei"),)),
    EreignisDef("programm.beendet", "Ein beobachtetes Programm wurde beendet.",
                bedingungen=(_programm(pflicht=True),), daten=("name",),
                platzhalter=(("programm", "Name der Programmdatei"),)),
    EreignisDef("uhrzeit", "Jede Minute die aktuelle Uhrzeit.",
                bedingungen=(Param("uhrzeit", "text", "Genau diese Uhrzeit, z. B. 12:00.", feld="uhrzeit"),),
                daten=("uhrzeit",), muster="uhrzeit.<uhrzeit>"),
    EreignisDef("tageszeit", "Die Tageszeit wechselt (Grenzen siehe Werte).",
                bedingungen=(Param("tageszeit", "auswahl", "Nur bei dieser Tageszeit.", feld="tageszeit",
                                   auswahl=TAGESZEITEN),),
                daten=("tageszeit",), muster="tageszeit.<tageszeit>"),
    EreignisDef("audio.laeuft", "Seit einigen Sekunden läuft Ton (Musik, Video) – erkannt am Pegel, "
                "nicht am Inhalt."),
    EreignisDef("audio.still", "Der Ton ist wieder aus."),
    EreignisDef("avatar.gezogen", "Der Avatar wird mit der Maus gepackt."),
    EreignisDef("avatar.losgelassen", "Der Avatar wird losgelassen oder geworfen.", daten=("vx", "vy")),
    EreignisDef("avatar.gelandet", "Der Avatar landet nach einem Hüpfer, Fall oder Sprung.",
                bedingungen=(Param("art", "auswahl", "Nur nach einem Hüpfer (hupf), einem Nachhüpfer beim "
                                   "Nachfedern (nachhupf) oder nach einem Fall (fall).",
                                   feld="art", auswahl=("hupf", "fall", "nachhupf")),
                             Param("fallhoehe_px", "zahl", "Nur ab dieser Fallhöhe (Pixel vom höchsten Punkt bis "
                                   "zur Landung).", feld="fallhoehe_px", vergleich="ab")),
                daten=("art", "fallhoehe_px")),
    EreignisDef("avatar.einrichten_auf", "Die Einrichten-Bühne wird geöffnet."),
    EreignisDef("avatar.einrichten_zu", "Die Einrichten-Bühne wird geschlossen."),
    EreignisDef("avatar.umbenannt", "Der Nutzer gibt dem Avatar einen neuen Namen.", daten=("name",),
                platzhalter=(("name", "der neue Name"),)),
    EreignisDef("monitor.geaendert", "Bildschirme wurden an- oder abgesteckt oder umgestellt.",
                daten=("anzahl",)),
    EreignisDef("sprechblase.knopf", "In einer Sprechblase wurde ein Knopf gedrückt.",
                bedingungen=(Param("knopf", "text", "Beschriftung des Knopfs, z. B. Später.", feld="knopf"),
                             _regel_quelle("Nur Sprechblasen dieser Regel.")),
                daten=("knopf", "quelle", "wunsch_id")),
    EreignisDef("sprechblase.zu", "Eine Sprechblase wurde weggeklickt.",
                bedingungen=(_regel_quelle("Nur Sprechblasen dieser Regel."),), daten=("quelle", "wunsch_id")),
    EreignisDef("hotkey", "Ein Tastenkürzel eines Tricks wurde gedrückt.",
                bedingungen=(Param("trick", "text", "Name des Tricks, z. B. erinnern.", feld="trick"),),
                daten=("trick",), muster="hotkey.<trick>"),
)

#: Bedingungen, die bei jedem Ereignis gehen
ALLGEMEINE_BEDINGUNGEN: tuple[Param, ...] = (
    Param("regel_laeuft", "regel", "Nur wenn der Wunsch dieser Regel gerade besteht "
          "(z. B. „schläft gerade“).", vergleich="laeuft"),
)

# --- Aktionen: nur was der Motor heute kann -----------------------------------------

AKTIONEN: tuple[AktionDef, ...] = (
    AktionDef("animation", "Spielt eine Animation des Avatars. Fehlt sie, gilt der Rückfall (ruhe).",
              (Param("name", "animation", "Animation", pflicht=True),)),
    AktionDef("sprechen", "Sprechblase mit einem zufälligen Spruch aus der Liste. Ohne eigene Animation "
              "wird „sprechen“ gezeigt.",
              (Param("texte", "liste", "Sprüche, eine Zeile = ein Spruch. Platzhalter wie {dauer} je nach "
                     "Ereignis.", pflicht=True),
               Param("knoepfe", "liste", "Bis zu zwei Knöpfe, eine Zeile je Knopf (z. B. Mach ich, Später)."),
               Param("trotz_ruhe", "bool", "Spricht auch, wenn der Avatar gerade still ist.", standard=False))),
    AktionDef("ton", "Spielt einen Ton, wenn der Wunsch beginnt (statt des Sprech-Tons).",
              (Param("name", "ton", "Ton", pflicht=True),)),
    AktionDef("zubehoer", "Zubehör an- oder ausziehen. Bleibt, bis eine Regel es wieder ändert.",
              (Param("name", "zubehoer", "Zubehör", pflicht=True),
               Param("an", "bool", "anziehen (aus = ausziehen)", standard=True)), wunsch=False),
    AktionDef("gehen_zu", "Geht an eine Stelle des aktuellen Bildschirms und bleibt dort (Hüpfer hüpfen hin).",
              (Param("ziel", "auswahl", "Ziel", pflicht=True, auswahl=("links", "rechts", "mitte")),)),
    AktionDef("bleiben", "Hält an, bis eine andere Regel ihn zurückzieht (Dauer gilt dann nicht). Wird er "
              "verdrängt, wartet er. Solange er besteht, feuert die Regel nicht erneut.", wunsch=False),
    AktionDef("zurueckziehen", "Beendet die Wünsche anderer Regeln (und deren Stillsein).",
              (Param("regeln", "regeln", "Regeln, eine id je Zeile", pflicht=True),), wunsch=False),
    AktionDef("ruhig", f"Still werden: Sprüche anderer Regeln (Priorität unter {LEISE_AB}) entfallen ganz, "
              "bis diese Regel zurückgezogen wird.", wunsch=False),
    AktionDef("freuen_huepfend", "Drei Hüpfer auf der Stelle mit einer vollen Drehung (Animation „freuen“). "
              "Avatare, die nicht hüpfen, zeigen nur „freuen“.",
              (Param("dauer_s", "zahl", "So lange läuft der Wunsch (ohne Angabe: Dauer der Regel)."),)),
    AktionDef("innen", "Zeigt eine Variante des Innenlebens (Gegenstand im Körper), solange der Wunsch läuft. "
              "Fehlt die Variante, bleibt die Grundvariante.",
              (Param("variante", "innen", "Variante, z. B. froh (zu tnt@froh)", pflicht=True),)),
)

#: Felder einer Regel (außer wenn/dann) mit Standard und Grenzen
REGEL_FELDER: tuple[tuple[str, str, object], ...] = (
    ("id", "eindeutiger Name der Regel (Kleinbuchstaben, Ziffern, _)", None),
    ("aktiv", "an/aus", True),
    ("prioritaet", f"0–{PRIORITAET_MAX}; Persönlichkeit üblich 30–60", 50),
    ("abklingzeit_s", "frühestens wieder nach so vielen Sekunden (0 = immer)", 0),
    ("chance", "Wahrscheinlichkeit 0–1, dass die Regel feuert", 1.0),
    ("dauer_s", "so lange läuft der Wunsch (null = bis zurückgezogen)", 5.0),
    ("aufheben", "verdrängt → wartet und läuft danach weiter", False),
    ("gruppe", "Regeln einer Gruppe sind Alternativen: je Ereignis feuert nur die erste passende", ""),
)
ABKLINGZEIT_MAX = 7 * 24 * 3600
DAUER_MAX = 24 * 3600

# --- Werte: Zahlen, die das Verhalten prägen ------------------------------------------

WERTE: tuple[WertDef, ...] = (
    # Tippen (Beobachter)
    WertDef("tippen_start_takte", "So viele aktive 100-ms-Takte innerhalb von 2 s, dann beginnt eine "
            "Tipp-Sitzung.", "Takte", 3, 1, 20, "Tippen", ganzzahl=True),
    WertDef("tippen_pause_s", "So lange keine Eingabe, dann endet die Tipp-Sitzung (tastatur.pause).",
            "s", 5.0, 1, 60, "Tippen"),
    WertDef("schnell_takte", "Aktive Takte pro Sekunde, ab denen Tippen als schnell zählt (höchstens 10).",
            "Takte/s", 7, 1, 10, "Tippen", ganzzahl=True),
    WertDef("schnell_dauer_s", "So lange am Stück schnell, dann kommt tastatur.schnell.", "s", 3.0, 0.5, 30,
            "Tippen"),
    WertDef("lange_tippsitzung_s", "Ab dieser Länge gilt eine Tipp-Sitzung als lang (z. B. für den "
            "Pausen-Vorschlag).", "s", 60, 5, 7200, "Tippen", ganzzahl=True, schnelltest=10),
    # Maus
    WertDef("maus_nah_px", "Abstand zur Körpermitte, ab dem die Maus als nah gilt.", "px", 170, 30, 600,
            "Maus", ganzzahl=True),
    WertDef("maus_weg_px", "Abstand, ab dem die Maus wieder weg ist (größer als „nah“).", "px", 220, 40, 800,
            "Maus", ganzzahl=True),
    WertDef("wackeln_weg_px", "Mindestweg zwischen zwei Richtungswechseln beim Wackeln.", "px", 25, 5, 200,
            "Maus"),
    WertDef("wackeln_wechsel", "So viele Richtungswechsel …", "Wechsel", 4, 2, 12, "Maus", ganzzahl=True),
    WertDef("wackeln_fenster_s", "… innerhalb dieser Zeit sind ein Wackeln.", "s", 1.2, 0.3, 5, "Maus"),
    WertDef("wackeln_sperre_s", "Nach einem Wackeln so lange kein neues.", "s", 3.0, 0, 30, "Maus"),
    # Leerlauf
    WertDef("einschlafen_nach_min", "Nach so vielen Minuten ohne Eingabe schläft er ein.", "min", 5, 1, 240,
            "Leerlauf", ganzzahl=True, schnelltest=1),
    # Ton
    WertDef("audio_schwelle", "Pegel (0–1), ab dem Ton als hörbar gilt.", "", 0.015, 0.001, 0.5, "Ton"),
    WertDef("audio_start_s", "So lange Ton am Stück, dann kommt audio.laeuft.", "s", 6.0, 1, 60, "Ton"),
    WertDef("audio_luecke_s", "Kürzere Lücken beim Start zählen nicht als Ende.", "s", 1.5, 0.1, 10, "Ton"),
    WertDef("audio_ende_s", "So lange still, dann kommt audio.still.", "s", 6.0, 1, 120, "Ton"),
    # Tageszeit
    WertDef("morgens_ab", "Ab dieser Stunde ist es morgens.", "Uhr", 5, 0, 23, "Tageszeit", ganzzahl=True),
    WertDef("mittags_ab", "Ab dieser Stunde ist es mittags.", "Uhr", 11, 0, 23, "Tageszeit", ganzzahl=True),
    WertDef("abends_ab", "Ab dieser Stunde ist es abends.", "Uhr", 17, 0, 23, "Tageszeit", ganzzahl=True),
    WertDef("nachts_ab", "Ab dieser Stunde ist es nachts.", "Uhr", 22, 0, 23, "Tageszeit", ganzzahl=True),
    # Eigenleben
    WertDef("ruhe_min_s", "Ruhephase im Eigenleben: mindestens …", "s", 2.0, 0.5, 60, "Eigenleben"),
    WertDef("ruhe_max_s", "… höchstens.", "s", 6.0, 0.5, 120, "Eigenleben"),
    WertDef("laufen_min_s", "Herumlaufen: mindestens …", "s", 2.0, 0.5, 60, "Eigenleben"),
    WertDef("laufen_max_s", "… höchstens.", "s", 8.0, 0.5, 120, "Eigenleben"),
    WertDef("sitzen_min_s", "Hinsetzen: mindestens …", "s", 5.0, 0.5, 120, "Eigenleben"),
    WertDef("sitzen_max_s", "… höchstens.", "s", 15.0, 0.5, 600, "Eigenleben"),
    WertDef("chance_sitzen", "Wahrscheinlichkeit, sich nach einer Ruhephase hinzusetzen.", "", 0.12, 0, 1,
            "Eigenleben"),
    WertDef("chance_laufen", "Wahrscheinlichkeit, nach einer Ruhephase loszulaufen (Rest: weiter ruhen).",
            "", 0.63, 0, 1, "Eigenleben"),
    WertDef("blinzeln_min_s", "Blinzeln: frühestens alle …", "s", 3.0, 0.5, 60, "Eigenleben"),
    WertDef("blinzeln_max_s", "… spätestens alle.", "s", 7.0, 0.5, 120, "Eigenleben"),
    # Bewegung
    WertDef("laufgeschwindigkeit", "Tempo beim Herumlaufen.", "px/s", 60, 10, 300, "Bewegung"),
    WertDef("zieltempo", "Tempo, wenn er zu einem Ziel geht (gehen_zu).", "px/s", 140, 20, 600, "Bewegung"),
    # Hüpfen (nur Avatare mit bewegung.art = huepfen)
    WertDef("sprungweite_px", "So weit kommt er mit einem Hüpfer.", "px", 36, 0, 300, "Hüpfen"),
    WertDef("sprunghoehe_px", "So hoch hüpft er.", "px", 26, 4, 200, "Hüpfen"),
    WertDef("hupf_pause_min_s", "Pause zwischen zwei Hüpfern: mindestens …", "s", 0.8, 0, 10, "Hüpfen"),
    WertDef("hupf_pause_max_s", "… höchstens.", "s", 1.6, 0, 10, "Hüpfen"),
    WertDef("nachhuepfen", "Nachfedern nach einer Hüpf-Landung wie ein Ball: Jeder Nachhüpfer ist so viel "
            "mal so hoch wie der vorige (höchstens 4, Ende unter 3 px). 0 = aus.", "", 0.0, 0.0, 0.8, "Hüpfen"),
    # Motor
    WertDef("wunsch_verfaellt_s", "Nicht begonnene Wünsche verfallen nach dieser Zeit (keine veralteten "
            "Reaktionen).", "s", 10.0, 1, 120, "Motor"),
)

#: Kern-Vokabular der Animationen: Name → (wofür, wer nutzt sie)
KERN_ANIMATIONEN: dict[str, tuple[str, str]] = {
    "ruhe": ("Stehen ohne Anlass – Pflicht, Rückfall für alles", "Eigenleben"),
    "bewegen": ("Gehen (intern „laufen“)", "Eigenleben, gehen_zu"),
    "sitzen": ("Hinsetzen", "Eigenleben"),
    "schlafen": ("Schlafen", "Nicht stören"),
    "gezogen": ("Am Mauszeiger hängen", "Sockel (Ziehen)"),
    "fallen": ("Fallen", "Sockel (Physik)"),
    "springen": ("Sprung im Bogen", "Sockel (Einrichten)"),
    "schweben": ("Schweben", "Sockel (Einrichten)"),
    "sprechen": ("Reden (Standard bei Sprechblasen)", "Regeln mit „sprechen“"),
    "anschauen": ("Den Nutzer ansehen, Blick folgt der Maus", "Regeln"),
    "freuen": ("Freude", "Regeln"),
    "erschrecken": ("Erschrecken, Blick folgt der Maus", "Regeln"),
    "hocken": ("Vor dem Hüpfer zusammenziehen", "Sockel (Hüpfen)"),
    "absprung": ("Abspringen, gestreckt", "Sockel (Hüpfen)"),
    "flug": ("Im Bogen fliegen", "Sockel (Hüpfen)"),
    "landen": ("Aufkommen, kurz gestaucht", "Sockel (Hüpfen, nach jedem Fall)"),
    "drehen": ("Drehen auf der Stelle: vorne → ¾ → Seite → ¾ hinten → hinten", "freuen_huepfend, Regeln"),
}
#: Rückfall, wenn die Animation fehlt (sonst gilt RUECKFALL)
KERN_RUECKFALL: dict[str, str] = {
    "hocken": "ruhe, prozedural gestaucht",
    "absprung": "ruhe, prozedural gestreckt",
    "flug": "ruhe",
    "landen": "ruhe, prozedural gestaucht",
    "drehen": "Pseudo-Drehung: Breite folgt |cos|, Rückseite gespiegelt (ein Umlauf 700 ms)",
}
NAMEN = {"laufen": "bewegen"}          # intern → Kern-Vokabular
RUECKFALL = "ruhe"

# --- Nachschlagen ---------------------------------------------------------------------

EREIGNIS: dict[str, EreignisDef] = {e.name: e for e in EREIGNISSE}
AKTION: dict[str, AktionDef] = {a.name: a for a in AKTIONEN}
WERT: dict[str, WertDef] = {w.id: w for w in WERTE}
_MUSTER = {e.name: e.muster.split("<", 1)[1].rstrip(">") for e in EREIGNISSE if e.muster}


def zuordnen(name: str) -> tuple[EreignisDef, dict] | None:
    """Ausgelöster Name → (Katalog-Ereignis, Zusatzdaten aus dem Namen) oder None.
    Beispiele: "leerlauf.5" → leerlauf, "tageszeit.nachts" → tageszeit {tageszeit: nachts}."""
    e = EREIGNIS.get(name)
    if e is not None:
        return e, {}
    vorne, punkt, rest = name.partition(".")
    if punkt and vorne in _MUSTER and rest:
        feld = _MUSTER[vorne]
        if feld == "minuten" and not rest.isdigit():
            return None
        return EREIGNIS[vorne], {feld: int(rest) if feld == "minuten" else rest}
    return None


def standard(wert_id: str) -> float:
    return WERT[wert_id].wirksamer_standard


def rueckfall(animation: str, vorhanden: Iterable[str]) -> str:
    """Welche Animation wirklich gezeigt wird (Varianten „name~2“ zählen mit)."""
    name = NAMEN.get(animation, animation)
    basis = {v.split("~")[0].split("@")[0] for v in vorhanden}
    return name if name in basis else RUECKFALL


class Werte:
    """Werte eines Avatars: Standard aus dem Katalog, Abweichungen aus verhalten.json.
    Unbekannte Werte werden ignoriert, alles wird auf Min/Max begrenzt."""

    def __init__(self, abweichungen: dict | None = None) -> None:
        self.abweichungen = {k: v for k, v in (abweichungen or {}).items()
                             if k in WERT and isinstance(v, (int, float)) and not isinstance(v, bool)}

    def __getitem__(self, wert_id: str) -> float:
        d = WERT[wert_id]
        if SCHNELLTEST and d.schnelltest is not None:
            return d.wirksamer_standard
        wert = self.abweichungen.get(wert_id, d.standard)
        wert = min(max(wert, d.min), d.max)
        return int(round(wert)) if d.ganzzahl else float(wert)

    def get(self, wert_id: str, ersatz=None):
        """Abweichung, sonst ``ersatz`` (falls angegeben), sonst Standard."""
        if wert_id in self.abweichungen or ersatz is None:
            return self[wert_id]
        return ersatz


# --- Prüfen ---------------------------------------------------------------------------

ID_MUSTER = re.compile(r"^[a-z0-9_]+$")
_OBEN = {"werte", "regeln", "beschreibung"}
MIN_MAX = (("ruhe_min_s", "ruhe_max_s"), ("laufen_min_s", "laufen_max_s"), ("sitzen_min_s", "sitzen_max_s"),
           ("blinzeln_min_s", "blinzeln_max_s"), ("hupf_pause_min_s", "hupf_pause_max_s"))
_REGEL_SCHLUESSEL = {"id", "aktiv", "wenn", "dann", "prioritaet", "abklingzeit_s", "chance", "dauer_s",
                     "aufheben", "gruppe"}


def bedingungen(regel: dict) -> list[dict]:
    """„wenn“ als Liste (ein dict oder eine Liste von dicts = „oder“)."""
    wenn = regel.get("wenn")
    if isinstance(wenn, dict):
        return [wenn]
    return [b for b in wenn if isinstance(b, dict)] if isinstance(wenn, list) else []


def _zahl(x) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool)


def _param_pruefen(p: Param, wert, ort: str, regel_ids: set[str], fehler: list[str]) -> None:
    def falsch(was: str) -> None:
        fehler.append(f"{ort}, Feld „{p.name}“: {was}")

    if p.typ in ("liste", "regeln"):
        if not isinstance(wert, list) or not all(isinstance(x, str) for x in wert):
            falsch("erwartet eine Liste von Texten")
        elif p.typ == "regeln":
            for x in wert:
                if x not in regel_ids:
                    falsch(f"Regel „{x}“ gibt es nicht")
    elif p.typ == "zahl":
        if isinstance(wert, str) and wert.startswith("$"):
            if wert[1:] not in WERT:
                falsch(f"Wert „{wert[1:]}“ gibt es nicht")
        elif not _zahl(wert):
            falsch("erwartet eine Zahl oder $wert")
    elif p.typ == "bool":
        if not isinstance(wert, bool):
            falsch("erwartet true oder false")
    elif p.typ == "auswahl":
        if wert not in p.auswahl:
            falsch(f"„{wert}“ ist nicht erlaubt ({', '.join(p.auswahl)})")
    elif p.typ == "regel":
        if wert not in regel_ids:
            falsch(f"Regel „{wert}“ gibt es nicht")
    elif not isinstance(wert, str):
        falsch("erwartet einen Text")


def pruefen(verhalten, animationen: Iterable[str] | None = None,
            innen_varianten: Iterable[str] | None = None) -> tuple[list[str], list[str]]:
    """Prüft eine verhalten.json gegen den Katalog → (Fehler, Warnungen), deutsch,
    jeweils mit Regel-id und Feld. Fehler brechen den Bau ab, Warnungen nicht.
    ``innen_varianten``: Varianten des Innenlebens (z. B. {"froh"}), None = nicht prüfen."""
    fehler: list[str] = []
    warnungen: list[str] = []
    if not isinstance(verhalten, dict):
        return ["verhalten.json: erwartet ein Objekt mit „werte“ und „regeln“"], []
    for k in verhalten:
        if k not in _OBEN:
            fehler.append(f"verhalten.json: unbekannter Eintrag „{k}“")

    werte = verhalten.get("werte", {})
    if not isinstance(werte, dict):
        fehler.append("werte: erwartet ein Objekt")
        werte = {}
    for wid, wert in werte.items():
        d = WERT.get(wid)
        if d is None:
            fehler.append(f"Wert „{wid}“ gibt es nicht im Katalog")
        elif not _zahl(wert):
            fehler.append(f"Wert „{wid}“: erwartet eine Zahl")
        elif not d.min <= wert <= d.max:
            fehler.append(f"Wert „{wid}“ = {wert} liegt außerhalb {d.min:g}–{d.max:g} {d.einheit}".rstrip())
    for unten, oben in MIN_MAX:
        a, b = werte.get(unten, WERT[unten].standard), werte.get(oben, WERT[oben].standard)
        if _zahl(a) and _zahl(b) and a > b:
            fehler.append(f"Wert „{unten}“ = {a:g} ist größer als „{oben}“ = {b:g}")

    regeln = verhalten.get("regeln", [])
    if not isinstance(regeln, list):
        return fehler + ["regeln: erwartet eine Liste"], warnungen
    ids: list[str] = [r.get("id") for r in regeln if isinstance(r, dict) and isinstance(r.get("id"), str)]
    regel_ids = set(ids)
    vorhanden = set(animationen) if animationen is not None else None
    varianten = {v.lstrip("@") for v in innen_varianten} if innen_varianten is not None else None
    gesehen: set[str] = set()
    for nr, r in enumerate(regeln, 1):
        if not isinstance(r, dict):
            fehler.append(f"Regel Nr. {nr}: erwartet ein Objekt")
            continue
        rid = r.get("id")
        if not isinstance(rid, str) or not ID_MUSTER.match(rid):
            fehler.append(f"Regel Nr. {nr}, Feld „id“: fehlt oder ungültig (nur a–z, 0–9, _)")
            rid = f"Nr. {nr}"
        elif rid in gesehen:
            fehler.append(f"Regel „{rid}“, Feld „id“: doppelt vergeben")
        gesehen.add(rid)
        ort = f"Regel „{rid}“"
        for k in r:
            if k not in _REGEL_SCHLUESSEL:
                fehler.append(f"{ort}: unbekanntes Feld „{k}“")
        if "aktiv" in r and not isinstance(r["aktiv"], bool):
            fehler.append(f"{ort}, Feld „aktiv“: erwartet true oder false")
        if "aufheben" in r and not isinstance(r["aufheben"], bool):
            fehler.append(f"{ort}, Feld „aufheben“: erwartet true oder false")
        if "gruppe" in r and not isinstance(r["gruppe"], str):
            fehler.append(f"{ort}, Feld „gruppe“: erwartet einen Text")
        p = r.get("prioritaet", 50)
        if not isinstance(p, int) or isinstance(p, bool) or not 0 <= p <= PRIORITAET_MAX:
            fehler.append(f"{ort}, Feld „prioritaet“: {p} – erlaubt sind ganze Zahlen 0–{PRIORITAET_MAX}")
        a = r.get("abklingzeit_s", 0)
        if not _zahl(a) or not 0 <= a <= ABKLINGZEIT_MAX:
            fehler.append(f"{ort}, Feld „abklingzeit_s“: {a} – erlaubt 0–{ABKLINGZEIT_MAX} s")
        c = r.get("chance", 1.0)
        if not _zahl(c) or not 0 <= c <= 1:
            fehler.append(f"{ort}, Feld „chance“: {c} – erlaubt 0–1")
        d = r.get("dauer_s", 5.0)
        if d is not None and (not _zahl(d) or not 0 < d <= DAUER_MAX):
            fehler.append(f"{ort}, Feld „dauer_s“: {d} – erlaubt über 0 bis {DAUER_MAX} s oder null")

        # wenn
        wenn = r.get("wenn")
        liste = bedingungen(r)
        if not liste or (isinstance(wenn, list) and len(liste) != len(wenn)):
            fehler.append(f"{ort}, Feld „wenn“: fehlt (ein Ereignis oder eine Liste von Ereignissen)")
        for b in liste:
            name = b.get("ereignis")
            e = EREIGNIS.get(name) if isinstance(name, str) else None
            if e is None:
                fehler.append(f"{ort}, Feld „wenn.ereignis“: unbekanntes Ereignis „{name}“")
                continue
            erlaubt = {p.name: p for p in e.bedingungen + ALLGEMEINE_BEDINGUNGEN}
            for k, v in b.items():
                if k == "ereignis":
                    continue
                if k not in erlaubt:
                    fehler.append(f"{ort}, Feld „wenn.{k}“: gibt es bei „{name}“ nicht")
                else:
                    _param_pruefen(erlaubt[k], v, ort, regel_ids, fehler)
            for p in e.bedingungen:
                if p.pflicht and not b.get(p.name):
                    fehler.append(f"{ort}, Feld „wenn.{p.name}“: Pflicht bei „{name}“")

        # dann
        dann = r.get("dann")
        if not isinstance(dann, list) or not dann:
            fehler.append(f"{ort}, Feld „dann“: mindestens eine Aktion nötig")
            continue
        for akt in dann:
            art = akt.get("aktion") if isinstance(akt, dict) else None
            ad = AKTION.get(art) if isinstance(art, str) else None
            if ad is None:
                fehler.append(f"{ort}, Feld „dann.aktion“: unbekannte Aktion „{art}“")
                continue
            erlaubt = {p.name: p for p in ad.parameter}
            for k, v in akt.items():
                if k == "aktion":
                    continue
                if k not in erlaubt:
                    fehler.append(f"{ort}, Feld „{art}.{k}“: gibt es bei „{art}“ nicht")
                else:
                    _param_pruefen(erlaubt[k], v, ort, regel_ids, fehler)
            for p in ad.parameter:
                if p.pflicht and (p.name not in akt or akt[p.name] in ("", [], None)):
                    fehler.append(f"{ort}, Feld „{art}.{p.name}“: Pflicht")
            if art == "sprechen" and isinstance(akt.get("knoepfe"), list) and len(akt["knoepfe"]) > 2:
                fehler.append(f"{ort}, Feld „sprechen.knoepfe“: höchstens zwei Knöpfe")
            if art == "animation" and vorhanden is not None and isinstance(akt.get("name"), str):
                ziel = rueckfall(akt["name"], vorhanden)
                if ziel != NAMEN.get(akt["name"], akt["name"]):
                    warnungen.append(f"{ort}: Animation „{akt['name']}“ fehlt – Rückfall auf „{ziel}“")
            if art == "innen" and varianten is not None and isinstance(akt.get("variante"), str)                     and akt["variante"].lstrip("@") not in varianten:
                warnungen.append(f"{ort}: Innenleben-Variante „{akt['variante']}“ fehlt – es bleibt die "
                                 "Grundvariante")
    return fehler, warnungen


def beobachtete_programme(verhalten: dict | None) -> set[str]:
    """Programme, deren Start/Ende überwacht werden muss (aus den Regeln)."""
    ergebnis: set[str] = set()
    for r in (verhalten or {}).get("regeln", []):
        if not isinstance(r, dict) or not r.get("aktiv", True):
            continue
        for b in bedingungen(r):
            if b.get("ereignis") in ("programm.gestartet", "programm.beendet"):
                ergebnis |= {str(p).lower() for p in b.get("programm", [])}
    return ergebnis


def platzhalter(ereignis: str, daten: dict) -> dict[str, str]:
    """Werte für {platzhalter} in Sprüchen."""
    p: dict[str, str] = {}
    if ereignis == "tastatur.pause":
        minuten = max(1, round(float(daten.get("sitzung_s", 0)) / 60))
        p["dauer"] = f"{minuten} Minute" if minuten == 1 else f"{minuten} Minuten"
    if "minuten" in daten:
        p["minuten"] = str(daten["minuten"])
    if ereignis.startswith("programm.") and daten.get("name"):
        p["programm"] = str(daten["name"])
    if ereignis == "avatar.umbenannt" and daten.get("name"):
        p["name"] = str(daten["name"])
    return p


# --- Körper: Aussehen aus dem Bauplan (→ avatar.json) ---------------------------------
# Aussehen und Körper stehen im Bauplan, Temperament (wie weit, wie oft, wie schnell) in
# den Werten oben. Nichts doppelt: Tempo gibt es nur als Wert „laufgeschwindigkeit“.

BEWEGUNGSARTEN: dict[str, str] = {
    "gehen": "läuft mit der Animation „bewegen“",
    "gleiten": "gleitet ohne eigene Laufbilder (Platzhalter-Blob)",
    "huepfen": "hüpft schwerfällig: hocken → absprung → flug → landen → Pause",
}
HUEPF_STANDARD = {"hocken_ms": 260, "stauchen": {"breite": 1.18, "hoehe": 0.78},
                  "strecken": {"breite": 0.88, "hoehe": 1.16}}
ABSPRUNG_S = 0.08
LANDEN_S = 0.14
NACH_ABSPRUNG_S = 0.06       # Nachhüpfer: federt direkt ab, ohne Hocken
NACH_LANDEN_S = 0.10
NACH_TON_AB = 0.4            # Nachhüpfer unter diesem Höhenverhältnis landen still
DREHUNG_S = 0.7                 # ein Umlauf der Pseudo-Drehung
PARTIKEL_FORMEN = ("quadrat", "tropfen")
PARTIKEL_STANDARD = {"farbe": "#FFFFFF", "deckkraft": 0.6, "anzahl": [6, 10], "groesse_px": [3, 4],
                     "reichweite_px": 22, "dauer_ms": 380, "form": "quadrat"}
PARTIKEL_RAND = 28              # so viel Platz bekommt das Fenster für Partikel
TON_ABSTAND_S = 0.09            # Abstand zwischen Wiederholungen
TON_ENDUNGEN = (".wav", ".ogg")


def momente() -> list[str]:
    """Momente, zu denen Partikel und Körper-Töne kommen: die Kern-Animationen."""
    return list(KERN_ANIMATIONEN)


def _bereich(fehler: list[str], ort: str, wert, lo: float, hi: float, ganz: bool = False) -> None:
    if not _zahl(wert) or (ganz and int(wert) != wert):
        fehler.append(f"{ort}: erwartet eine {'ganze ' if ganz else ''}Zahl")
    elif not lo <= wert <= hi:
        fehler.append(f"{ort} = {wert:g} liegt außerhalb {lo:g}–{hi:g}")


def _paar(fehler: list[str], ort: str, wert, lo: float, hi: float, ganz: bool = False) -> None:
    if not (isinstance(wert, list) and len(wert) == 2):
        fehler.append(f"{ort}: erwartet [von, bis]")
        return
    for x in wert:
        _bereich(fehler, ort, x, lo, hi, ganz)
    if all(_zahl(x) for x in wert) and wert[0] > wert[1]:
        fehler.append(f"{ort}: „von“ ist größer als „bis“")


def koerper_pruefen(plan: dict, ordner=None) -> tuple[list[str], list[str]]:
    """Prüft die Körper-Blöcke eines Bauplans (bewegung, partikel, toene,
    koerper_deckkraft) → (Fehler, Warnungen), deutsch. ``ordner``: Quellordner, um
    Ton-Dateien zu finden (fehlende Datei = Warnung, der Ton entfällt)."""
    fehler: list[str] = []
    warnungen: list[str] = []
    bekannt = set(momente())

    b = plan.get("bewegung", {})
    if not isinstance(b, dict):
        fehler.append("bewegung: erwartet ein Objekt")
        b = {}
    if "tempo" in b:
        fehler.append("bewegung.tempo gibt es nicht mehr – die Laufgeschwindigkeit ist jetzt der Wert "
                      "„laufgeschwindigkeit“ in verhalten.json (Avatar-Editor → Verhalten → Werte). "
                      "Bitte „tempo“ aus dem Bauplan löschen.")
    for k in b:
        if k not in ("art", "tempo", "hocken_ms", "stauchen", "strecken"):
            fehler.append(f"bewegung: unbekannter Eintrag „{k}“")
    art = b.get("art", "gehen")
    if art not in BEWEGUNGSARTEN:
        fehler.append(f"bewegung.art: „{art}“ gibt es nicht ({', '.join(BEWEGUNGSARTEN)})")
    if "hocken_ms" in b:
        _bereich(fehler, "bewegung.hocken_ms", b["hocken_ms"], 0, 2000)
    for form in ("stauchen", "strecken"):
        if form not in b:
            continue
        f = b[form]
        if not isinstance(f, dict):
            fehler.append(f"bewegung.{form}: erwartet ein Objekt mit „breite“ und „hoehe“")
            continue
        for k, v in f.items():
            if k not in ("breite", "hoehe"):
                fehler.append(f"bewegung.{form}: unbekannter Eintrag „{k}“")
            else:
                _bereich(fehler, f"bewegung.{form}.{k}", v, 0.5, 1.6)

    if "koerper_deckkraft" in plan:
        _bereich(fehler, "koerper_deckkraft", plan["koerper_deckkraft"], 0.05, 1.0)

    partikel = plan.get("partikel", {})
    if not isinstance(partikel, dict):
        fehler.append("partikel: erwartet ein Objekt (Moment → Einstellungen)")
        partikel = {}
    for moment, d in partikel.items():
        ort = f"partikel.{moment}"
        if moment not in bekannt:
            fehler.append(f"{ort}: „{moment}“ ist kein Moment des Sockels (erlaubt: {', '.join(momente())})")
            continue
        if not isinstance(d, dict):
            fehler.append(f"{ort}: erwartet ein Objekt")
            continue
        for k, v in d.items():
            o = f"{ort}.{k}"
            if k == "farbe":
                if not (isinstance(v, str) and re.fullmatch(r"#[0-9A-Fa-f]{6}", v)):
                    fehler.append(f"{o}: erwartet eine Farbe wie #F2E36B")
            elif k == "deckkraft":
                _bereich(fehler, o, v, 0.05, 1.0)
            elif k == "anzahl":
                _paar(fehler, o, v, 1, 40, ganz=True)
            elif k == "groesse_px":
                _paar(fehler, o, v, 1, 16)
            elif k == "reichweite_px":
                _bereich(fehler, o, v, 2, PARTIKEL_RAND)
            elif k == "dauer_ms":
                _bereich(fehler, o, v, 50, 2000)
            elif k == "form":
                if v not in PARTIKEL_FORMEN:
                    fehler.append(f"{o}: „{v}“ gibt es nicht ({', '.join(PARTIKEL_FORMEN)})")
            else:
                fehler.append(f"{ort}: unbekannter Eintrag „{k}“")

    toene = plan.get("toene", {})
    if not isinstance(toene, dict):
        fehler.append("toene: erwartet ein Objekt (Name → Ton)")
        toene = {}
    for name, t in toene.items():
        ort = f"toene.{name}"
        if not isinstance(t, dict):
            fehler.append(f"{ort}: erwartet ein Objekt")
            continue
        if "segmente" in t:                         # synthetisierter Ton (frei benannt, für die Aktion „ton“)
            continue
        if name not in bekannt:
            fehler.append(f"{ort}: „{name}“ ist kein Moment des Sockels (erlaubt: {', '.join(momente())}). "
                          "Töne aus Dateien kommen automatisch zu ihrem Moment.")
            continue
        if "dateien" not in t:
            fehler.append(f"{ort}: „dateien“ fehlt")
        for k, v in t.items():
            o = f"{ort}.{k}"
            if k == "dateien":
                if not (isinstance(v, list) and v and all(isinstance(x, str) for x in v)):
                    fehler.append(f"{o}: erwartet eine Liste von Dateinamen")
                    continue
                for x in v:
                    if not x.lower().endswith(TON_ENDUNGEN):
                        fehler.append(f"{o}: „{x}“ – erlaubt sind {', '.join(TON_ENDUNGEN)}")
                    elif ordner is not None and not (ordner / x).is_file():
                        warnungen.append(f"{o}: Datei „{x}“ fehlt – wird übersprungen")
            elif k == "tonhoehe":
                _bereich(fehler, o, v, 0, 0.5)
            elif k == "wiederholen":
                _paar(fehler, o, v, 1, 5, ganz=True)
            else:
                fehler.append(f"{ort}: unbekannter Eintrag „{k}“")
    return fehler, warnungen


# --- Markdown ---------------------------------------------------------------------------

def _param_md(p: Param) -> str:
    teile = [f"`{p.name}`"]
    art = p.typ if not p.auswahl else " / ".join(p.auswahl)
    teile.append(f"({art}{', Pflicht' if p.pflicht else ''})")
    return " ".join(teile) + f" – {p.beschreibung}"


def als_markdown() -> str:
    z: list[str] = ["# DMNT-Kobold – Katalog des Sockels", "",
                    "Was ein Avatar in seiner `verhalten.json` benutzen kann. Erzeugt mit "
                    "`python -m dmnt_kobold --katalog`.", ""]
    z += ["## Ereignisse", "", "| Ereignis | Bedeutung | Bedingungen | Platzhalter |", "|---|---|---|---|"]
    for e in EREIGNISSE:
        name = f"`{e.name}`" + (f"<br>(ausgelöst als `{e.muster}`)" if e.muster else "")
        bed = "<br>".join(_param_md(p) for p in e.bedingungen) or "–"
        ph = "<br>".join(f"`{{{n}}}` {t}" for n, t in e.platzhalter) or "–"
        z.append(f"| {name} | {e.beschreibung} | {bed} | {ph} |")
    z += ["", "Bei jedem Ereignis zusätzlich: " + "; ".join(_param_md(p) for p in ALLGEMEINE_BEDINGUNGEN),
          "", "`wenn` darf auch eine Liste sein – dann genügt eine der Bedingungen („oder“).", ""]
    z += ["## Aktionen", "", "| Aktion | Bedeutung | Parameter |", "|---|---|---|"]
    for a in AKTIONEN:
        par = "<br>".join(_param_md(p) for p in a.parameter) or "–"
        z.append(f"| `{a.name}` | {a.beschreibung} | {par} |")
    z += ["", "## Felder einer Regel", "", "| Feld | Bedeutung | Standard |", "|---|---|---|"]
    for name, text, std in REGEL_FELDER:
        z.append(f"| `{name}` | {text} | {'–' if std is None else std} |")
    z += ["", "## Werte", "", "In `werte` stehen nur Abweichungen vom Standard.", ""]
    bereich = None
    for w in WERTE:
        if w.bereich != bereich:
            bereich = w.bereich
            z += ["", f"### {bereich}", "", "| Wert | Bedeutung | Standard | Bereich |", "|---|---|---|---|"]
        z.append(f"| `{w.id}` | {w.beschreibung} | {w.standard:g} {w.einheit} | {w.min:g}–{w.max:g} |")
    z += ["", "## Prioritäten", "", "| Priorität | Wer |", "|---|---|"]
    z += [f"| {p} | {t} |" for p, t in PRIORITAETEN]
    z += ["", "## Kern-Animationen", "", f"Fehlt eine Animation, gilt `{RUECKFALL}`. Varianten `name~2` werden "
          "zufällig gewählt.", "", "| Animation | Wofür | Genutzt von |", "|---|---|---|"]
    z += [f"| `{n}` | {w} | {wer} |" for n, (w, wer) in KERN_ANIMATIONEN.items()]
    z += ["", "Eigener Rückfall: " + "; ".join(f"`{n}` → {t}" for n, t in KERN_RUECKFALL.items()) + "."]
    z += ["", "## Körper (Bauplan → avatar.json)", "",
          "Aussehen gehört in den Bauplan, Temperament in die Werte. Partikel und Töne aus Dateien hängen "
          "an Momenten (= Kern-Animationen).", "",
          "| Block | Inhalt |", "|---|---|",
          "| `bewegung.art` | " + "; ".join(f"`{a}` {t}" for a, t in BEWEGUNGSARTEN.items()) + " |",
          "| `bewegung.hocken_ms`, `stauchen`, `strecken` | Hüpfen: Hockzeit, Form beim Stauchen/Strecken "
          "(`breite`, `hoehe` 0,5–1,6) |",
          "| `koerper_deckkraft` | Deckkraft des Körpers über dem Innenleben (0,05–1) |",
          "| `partikel.<moment>` | `farbe`, `deckkraft`, `anzahl` [von, bis], `groesse_px` [von, bis], "
          f"`reichweite_px` (bis {PARTIKEL_RAND}), `dauer_ms`, `form` ({' / '.join(PARTIKEL_FORMEN)}) |",
          "| `toene.<moment>` | `dateien` (.wav/.ogg), `tonhoehe` (Streuung ±), `wiederholen` [von, bis] |",
          "| Zubehör-Sitz `innen` | Gegenstand im Körper, Varianten je Stimmung (`tnt@froh`), Aktion `innen` |"]
    return "\n".join(z) + "\n"
