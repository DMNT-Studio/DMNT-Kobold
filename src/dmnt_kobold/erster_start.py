"""Erster Start: erst die Autostart-Frage, danach einmalig der Tray-Hinweis.

Einrichten und Beenden gibt es nur im Tray (Konzept #28), und Windows 11 versteckt
neue Tray-Icons im Überlaufmenü. Deshalb sagt der Avatar einmal, wo das Symbol ist.
Beides wird in den Einstellungen gemerkt (``autostart_gefragt``,
``hinweis_tray_gezeigt``) und erscheint danach nie wieder. Im Entwickler-Start
(``--avatar-pfad``) erscheint keins von beiden.
"""
from __future__ import annotations

from typing import Callable

AUTOSTART_TEXT = "Soll ich jedes Mal mit Windows starten?"
HINWEIS_TEXT = "Einrichten und Beenden findest du über mein Symbol unten rechts in der Taskleiste."
HINWEIS_KNOPF = "Alles klar"
HINWEIS_NACH_MS = 1_500          # Pause zwischen Autostart-Frage und Hinweis


class ErsterStart:
    def __init__(self, bus, motor, einstellungen, autostart_setzen: Callable[[bool], None],
                 verzoegern: Callable[[int, Callable[[], None]], None], entwickler: bool = False,
                 ohne_autostart: bool = False) -> None:
        self.entwickler = entwickler
        self.ohne_autostart = ohne_autostart     # Portable: keine Autostart-Frage, nur der Hinweis
        self.bus = bus
        self.motor = motor
        self.einstellungen = einstellungen
        self.autostart_setzen = autostart_setzen
        self.verzoegern = verzoegern
        self._hinweis_offen = False
        bus.abonnieren("sprechblase.zu", self._blase_zu, self)

    def starten(self, nach_ms: int) -> None:
        """Nach ``nach_ms`` die Autostart-Frage (oder, falls schon beantwortet, den Hinweis).
        Im Entwickler-Start nichts: echten Autostart nie anfassen."""
        if self.entwickler:
            return
        if not self.einstellungen.get("autostart_gefragt") and not self.ohne_autostart:
            self.verzoegern(nach_ms, self.autostart_fragen)
        else:
            self.verzoegern(nach_ms, self.hinweis_zeigen)

    # --- Autostart -------------------------------------------------------------
    def autostart_fragen(self) -> None:
        if self.einstellungen.get("autostart_gefragt"):
            self.hinweis_zeigen()
            return
        self.motor.wunsch(animation="sprechen", text=AUTOSTART_TEXT, knoepfe=("Ja", "Nein"),
                          prioritaet=60, dauer_s=None, aufheben=True, quelle="autostart",
                          beim_knopf=self._autostart_antwort)

    def _autostart_antwort(self, knopf: str) -> None:
        self._autostart_erledigt()
        if knopf == "Ja":
            self.autostart_setzen(True)

    def _autostart_erledigt(self) -> None:
        if self.einstellungen.get("autostart_gefragt"):
            return
        self.einstellungen["autostart_gefragt"] = True
        self.verzoegern(HINWEIS_NACH_MS, self.hinweis_zeigen)

    # --- Tray-Hinweis ------------------------------------------------------------
    def hinweis_zeigen(self) -> None:
        if self.einstellungen.get("hinweis_tray_gezeigt") or self._hinweis_offen:
            return
        self._hinweis_offen = True
        self.motor.wunsch(animation="sprechen", text=HINWEIS_TEXT, knoepfe=(HINWEIS_KNOPF,),
                          prioritaet=60, dauer_s=None, aufheben=True, quelle="tray_hinweis",
                          beim_knopf=lambda _k: self._hinweis_erledigt())

    def _hinweis_erledigt(self) -> None:
        self._hinweis_offen = False
        self.einstellungen["hinweis_tray_gezeigt"] = True

    def _blase_zu(self, e) -> None:          # weggeklickt zählt als beantwortet
        quelle = e.daten.get("quelle")
        if quelle == "autostart":
            self._autostart_erledigt()
        elif quelle == "tray_hinweis":
            self._hinweis_erledigt()
