"""Beobachter: übersetzen, was am PC passiert, in abstrahierte Ereignisse.

Datenschutz: Es gibt keine globalen Hooks. Tippen wird erkannt, weil sich
der Zeitpunkt der letzten Eingabe ändert, während die Maus stillsteht und
keine Maustaste gedrückt ist. Welche Taste – das weiß das Programm nie.

Ereignisse:
  maus.nah_am_avatar (entfernung), maus.weg, maus.wackelt
  tastatur.tippt, tastatur.schnell, tastatur.pause (sitzung_s)
  leerlauf.<minuten> (minuten), leerlauf.ende (minuten)
  programm.aktiv (name, titel, vorher)   – Vordergrund; titel wird nie geloggt
  programm.gestartet / programm.beendet (name) – nur für beobachtete Programme
  uhrzeit.<hh:mm>, tageszeit.<morgens|mittags|abends|nachts>
  audio.laeuft, audio.still   – aus dem Lautstärkepegel, nicht aus dem Inhalt

Die Analyse-Klassen sind reine Logik (testbar), ``Beobachter`` pollt per QTimer.
Schwellen und Zeiten kommen aus dem Katalog (``katalog.Werte``) und können je
Avatar abweichen.
"""
from __future__ import annotations

import time
from collections import deque
from datetime import datetime

from . import katalog

# --- reine Logik -----------------------------------------------------------


def tageszeit(stunde: int, werte: katalog.Werte | None = None) -> str:
    w = werte or katalog.Werte()
    grenzen = sorted((w[f"{tz}_ab"], tz) for tz in katalog.TAGESZEITEN)
    ergebnis = grenzen[-1][1]                 # vor der ersten Grenze: die letzte (nachts)
    for ab, tz in grenzen:
        if stunde >= ab:
            ergebnis = tz
    return ergebnis


class TippAnalyse:
    """Bekommt alle 100 ms „Tastatur aktiv ja/nein“ und meldet Sitzungen."""

    def __init__(self, werte: katalog.Werte | None = None) -> None:
        w = werte or katalog.Werte()
        self.START_AKTIV = w["tippen_start_takte"]     # aktive Takte in 2 s → Tippen beginnt
        self.PAUSE_S = w["tippen_pause_s"]             # so lange still → Pause
        self.SCHNELL_AKTIV = w["schnell_takte"]        # aktive Takte pro Sekunde …
        self.SCHNELL_DAUER_S = w["schnell_dauer_s"]    # … so lange am Stück → schnell
        self._aktiv: deque[float] = deque()
        self.sitzung_start: float | None = None
        self.letzte_aktiv: float | None = None
        self._schnell_seit: float | None = None
        self._schnell_gemeldet = False

    @property
    def tippt(self) -> bool:
        return self.sitzung_start is not None

    def update(self, t: float, aktiv: bool) -> list[tuple[str, dict]]:
        ereignisse: list[tuple[str, dict]] = []
        if aktiv:
            self._aktiv.append(t)
            self.letzte_aktiv = t
        while self._aktiv and t - self._aktiv[0] > 2.0:
            self._aktiv.popleft()

        if self.sitzung_start is None:
            if len(self._aktiv) >= self.START_AKTIV:
                self.sitzung_start = self._aktiv[0]
                ereignisse.append(("tastatur.tippt", {}))
            return ereignisse

        if t - self.letzte_aktiv >= self.PAUSE_S:
            dauer = self.letzte_aktiv - self.sitzung_start
            ereignisse.append(("tastatur.pause", {"sitzung_s": round(dauer, 1)}))
            self.sitzung_start = None
            self._schnell_seit = None
            self._schnell_gemeldet = False
            self._aktiv.clear()
            return ereignisse

        pro_sekunde = sum(1 for z in self._aktiv if t - z <= 1.0)
        if pro_sekunde >= self.SCHNELL_AKTIV:
            if self._schnell_seit is None:
                self._schnell_seit = t
            elif not self._schnell_gemeldet and t - self._schnell_seit >= self.SCHNELL_DAUER_S:
                self._schnell_gemeldet = True
                ereignisse.append(("tastatur.schnell", {}))
        else:
            self._schnell_seit = None
        return ereignisse


class WackelAnalyse:
    """Mehrere schnelle Richtungswechsel der Maus in kurzer Zeit = Wackeln."""

    def __init__(self, werte: katalog.Werte | None = None) -> None:
        w = werte or katalog.Werte()
        self.MIN_WEG = w["wackeln_weg_px"]
        self.WECHSEL = w["wackeln_wechsel"]
        self.FENSTER_S = w["wackeln_fenster_s"]
        self.PAUSE_S = w["wackeln_sperre_s"]
        self._wechsel: deque[float] = deque()
        self._letztes_x: float | None = None
        self._umkehr_x: float | None = None
        self._richtung = 0
        self._sperre_bis = 0.0

    def zuruecksetzen(self) -> None:
        self._wechsel.clear()
        self._letztes_x = self._umkehr_x = None
        self._richtung = 0

    def update(self, t: float, x: float) -> bool:
        if self._letztes_x is None:
            self._letztes_x = self._umkehr_x = x
            return False
        dx = x - self._letztes_x
        self._letztes_x = x
        if dx == 0:
            return False
        r = 1 if dx > 0 else -1
        if r != self._richtung:
            if self._richtung != 0 and abs(x - dx - self._umkehr_x) >= self.MIN_WEG:
                self._wechsel.append(t)
            self._umkehr_x = x - dx
            self._richtung = r
        while self._wechsel and t - self._wechsel[0] > self.FENSTER_S:
            self._wechsel.popleft()
        if len(self._wechsel) >= self.WECHSEL and t >= self._sperre_bis:
            self._wechsel.clear()
            self._sperre_bis = t + self.PAUSE_S
            return True
        return False


class LeerlaufAnalyse:
    """Meldet jede volle Minute ohne Eingabe und das Ende des Leerlaufs."""

    def __init__(self) -> None:
        self.gemeldet = 0

    def update(self, leerlauf_s: float) -> list[tuple[str, dict]]:
        minuten = int(leerlauf_s // 60)
        if minuten > self.gemeldet:
            self.gemeldet = minuten
            return [(f"leerlauf.{minuten}", {"minuten": minuten})]
        if leerlauf_s < 2.0 and self.gemeldet > 0:
            m, self.gemeldet = self.gemeldet, 0
            return [("leerlauf.ende", {"minuten": m})]
        return []


class AudioAnalyse:
    """Pegel 0..1 alle 100 ms → „läuft“ nach einigen Sekunden Ton, „still“ nach Pause.
    Kurze Lücken (Liedwechsel, leise Stellen) zählen nicht als Ende."""

    def __init__(self, werte: katalog.Werte | None = None) -> None:
        w = werte or katalog.Werte()
        self.SCHWELLE = w["audio_schwelle"]
        self.START_S = w["audio_start_s"]
        self.LUECKE_S = w["audio_luecke_s"]
        self.ENDE_S = w["audio_ende_s"]
        self.laeuft = False
        self._seit: float | None = None
        self._laut: float | None = None

    def update(self, t: float, pegel: float) -> list[tuple[str, dict]]:
        if pegel >= self.SCHWELLE:
            self._laut = t
            if self._seit is None:
                self._seit = t
        if self._laut is None:
            return []
        if not self.laeuft:
            if t - self._laut > self.LUECKE_S:
                self._seit = None
            elif self._seit is not None and t - self._seit >= self.START_S:
                self.laeuft = True
                return [("audio.laeuft", {})]
        elif t - self._laut > self.ENDE_S:
            self.laeuft = False
            self._seit = None
            return [("audio.still", {})]
        return []


# --- Polling (Qt) -----------------------------------------------------------

NAH_PX = katalog.standard("maus_nah_px")
WEG_PX = katalog.standard("maus_weg_px")


class Beobachter:
    """Pollt alle 100 ms. ``avatar_mitte()`` liefert (x, y) logisch oder None
    (während der Avatar gezogen wird)."""

    def __init__(self, bus, avatar_mitte, eigene_pid: int, parent=None,
                 beobachtete_programme: set[str] | None = None, werte: katalog.Werte | None = None) -> None:
        from PySide6.QtCore import QTimer

        from . import win32

        self.bus = bus
        self.avatar_mitte = avatar_mitte
        self.eigene_pid = eigene_pid
        self.win = win32
        self.werte = werte or katalog.Werte()
        self.nah_px = self.werte["maus_nah_px"]
        self.weg_px = max(self.werte["maus_weg_px"], self.nah_px)
        self.tipp = TippAnalyse(self.werte)
        self.wackel = WackelAnalyse(self.werte)
        self.leerlauf = LeerlaufAnalyse()
        self.audio = AudioAnalyse(self.werte)
        self._pegel = win32.Pegelmesser()
        self._nah = False
        self._letzte_eingabe = win32.letzte_eingabe_ms()
        self._letzte_maus: tuple[int, int] | None = None
        self._programm: str | None = None
        self._programm_takt = 0
        self.beobachtete_programme = {n.lower() for n in (beobachtete_programme or set())}
        self._laufend: set[str] = set()
        self._prozess_takt = 0
        self._minute = ""
        self._tageszeit = ""
        self.ignorierte_programme: set[str] = set()      # Einrichten → Programme
        self.zuletzt: deque[str] = deque(maxlen=10)      # nur Prozessnamen, nur im Speicher

        self._timer = QTimer(parent)
        self._timer.timeout.connect(self._takt)
        self._timer.start(100)
        # Wackeln braucht feinere Abtastung: 30 Hz, aber nur solange die Maus nah ist
        self._wackel_timer = QTimer(parent)
        self._wackel_timer.timeout.connect(self._wackel_takt)

    def _ignoriert(self) -> bool:
        return self._programm is not None and self._programm in self.ignorierte_programme

    def _senden(self, liste: list[tuple[str, dict]]) -> None:
        for name, daten in liste:
            self.bus.senden(name, **daten)

    def _wackel_takt(self) -> None:
        from PySide6.QtGui import QCursor

        if self._ignoriert():
            return
        if self._nah and self.wackel.update(time.monotonic(), QCursor.pos().x()):
            self.bus.senden("maus.wackelt")

    def _takt(self) -> None:
        from PySide6.QtGui import QCursor

        t = time.monotonic()
        pos = QCursor.pos()
        maus = (pos.x(), pos.y())

        # Maus am Avatar
        mitte = self.avatar_mitte()
        if mitte is not None:
            d = ((maus[0] - mitte[0]) ** 2 + (maus[1] - mitte[1]) ** 2) ** 0.5
            if not self._nah and d < self.nah_px:
                self._nah = True
                self.wackel.zuruecksetzen()
                self._wackel_timer.start(33)
                self.bus.senden("maus.nah_am_avatar", entfernung=round(d))
            elif self._nah and d > self.weg_px:
                self._nah = False
                self._wackel_timer.stop()
                self.bus.senden("maus.weg")

        # Tastatur (nur „aktiv ja/nein“) und Leerlauf
        if self.win.IST_WINDOWS:
            eingabe = self.win.letzte_eingabe_ms()
            neu = eingabe != self._letzte_eingabe
            self._letzte_eingabe = eingabe
            tastatur = (neu and maus == self._letzte_maus and not self.win.maustaste_gedrueckt()
                        and not self._ignoriert())
            self._senden(self.tipp.update(t, tastatur))
            self._senden(self.leerlauf.update(self.win.leerlauf_s()))
            self._senden(self.audio.update(t, self._pegel.pegel(0.1)))
        self._letzte_maus = maus

        # Programm im Vordergrund (2× pro Sekunde)
        self._programm_takt = (self._programm_takt + 1) % 5
        if self._programm_takt == 0:
            fg = self.win.vordergrund_programm()
            if fg is not None and fg[2] != self.eigene_pid and fg[0] and fg[0] != self._programm:
                vorher, self._programm = self._programm, fg[0]
                if fg[0] in self.zuletzt:
                    self.zuletzt.remove(fg[0])
                self.zuletzt.appendleft(fg[0])
                self.bus.senden("programm.aktiv", name=fg[0], titel=fg[1], vorher=vorher)

        # Beobachtete Programme laufen? (alle 5 s, unabhängig vom Vordergrund)
        self._prozess_takt = (self._prozess_takt + 1) % 50
        if self._prozess_takt == 1 and self.beobachtete_programme:
            jetzt_laufend = self.win.laufende_programme() & self.beobachtete_programme
            for name in sorted(jetzt_laufend - self._laufend):
                self.bus.senden("programm.gestartet", name=name)
            for name in sorted(self._laufend - jetzt_laufend):
                self.bus.senden("programm.beendet", name=name)
            self._laufend = jetzt_laufend

        # Uhrzeit / Tageszeit
        jetzt = datetime.now()
        minute = jetzt.strftime("%H:%M")
        if minute != self._minute:
            self._minute = minute
            self.bus.senden(f"uhrzeit.{minute}")
            tz = tageszeit(jetzt.hour, self.werte)
            if tz != self._tageszeit:
                self._tageszeit = tz
                self.bus.senden(f"tageszeit.{tz}")
