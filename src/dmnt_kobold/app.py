"""Einstieg: QApplication, Einzelinstanz, Logging, Datenhaltung, Verdrahtung.

Entwickler-Start: ``python -m dmnt_kobold --avatar-pfad <gebauter Avatar-Ordner>``
startet einen Avatar außerhalb des Pakets (z. B. die Prüf-Figur). Er wird nicht als
Avatar gespeichert, hat eigene Daten (build/kobold_entwickler, läuft also neben dem
normalen Kobold), und ein Klick öffnet nicht das Einrichten (das geht per Rechtsklick).
"""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

from PySide6.QtCore import QLockFile, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import __version__, blob, pfade

log = logging.getLogger("dmnt_kobold")

ZUSTAND_ALLE_MS = 60_000
SICHERUNG_PRUEFEN_MS = 30 * 60_000
AUTOSTART_FRAGE_NACH_MS = 8_000
SYSTEM_PROGRAMME = {"explorer.exe", "searchhost.exe", "shellexperiencehost.exe", "startmenuexperiencehost.exe",
                    "applicationframehost.exe", "lockapp.exe", "textinputhost.exe", "python.exe",
                    "pythonw.exe", "claude.exe"}


def _logging_einrichten() -> None:
    handler = RotatingFileHandler(
        pfade.logordner() / "kobold.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    wurzel = logging.getLogger()
    wurzel.setLevel(logging.INFO)
    wurzel.addHandler(handler)

    def ausnahme(typ, wert, tb):
        logging.getLogger("dmnt_kobold").critical("Unbehandelter Fehler", exc_info=(typ, wert, tb))
        sys.__excepthook__(typ, wert, tb)

    sys.excepthook = ausnahme


def _avatar_pfad() -> Path | None:
    if "--avatar-pfad" not in sys.argv:
        return None
    i = sys.argv.index("--avatar-pfad")
    if i + 1 >= len(sys.argv):
        raise SystemExit("--avatar-pfad braucht einen Ordner (gebauter Avatar mit avatar.json)")
    ordner = Path(sys.argv[i + 1]).resolve()
    if not (ordner / "avatar.json").is_file():
        raise SystemExit(f"Kein gebauter Avatar in {ordner} (avatar.json fehlt)")
    if not os.environ.get("DMNT_KOBOLD_DATEN"):     # eigene Daten → läuft neben dem echten Kobold
        os.environ["DMNT_KOBOLD_DATEN"] = str(Path.cwd() / "build" / "kobold_entwickler")
    return ordner


def main() -> int:
    avatar_pfad = _avatar_pfad()
    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv)
    app.setApplicationName("DMNT-Kobold")
    app.setQuitOnLastWindowClosed(False)

    sperre = QLockFile(str(pfade.lockdatei()))
    sperre.setStaleLockTime(0)
    if not sperre.tryLock(100):
        return 0  # läuft schon → still beenden

    _logging_einrichten()
    log.info("Start DMNT-Kobold %s, Daten in %s", __version__, pfade.datenordner())

    # Erst nach QApplication importieren (Qt-Widgets)
    from . import autostart, win32
    from .avatar import (STANDARD_AVATAR, avatar_icon, avatar_laden, avatar_liste, beobachtete_programme,
                         persoenlichkeiten_laden)
    from .beobachter import Beobachter
    from .bus import EventBus
    from .daten import Datenablage, Sicherung
    from .eigenleben import Eigenleben
    from .katalog import Werte
    from .einrichten import Dienste, Einrichten
    from .hotkeys import Hotkeys
    from .menue import Schalter
    from .modulverwaltung import Modulverwaltung
    from .motor import Verhaltensmotor
    from .overlay import AvatarFenster
    from .toene import Toene
    from .tray import baue_tray

    # --- Daten ---------------------------------------------------------------
    ablage = Datenablage(pfade.datenordner())
    einstellungen = ablage.speicher("einstellungen")
    zustand = ablage.speicher("zustand")
    sicherung = Sicherung(ablage)
    try:
        sicherung.taeglich()
    except OSError:
        log.exception("Tägliche Sicherung fehlgeschlagen")

    # --- Sockel ----------------------------------------------------------------
    schalter = Schalter()
    schalter.setze_nicht_stoeren(bool(einstellungen.get("nicht_stoeren", False)))
    schalter.setze_monitor_bleiben(bool(einstellungen.get("monitor_bleiben", False)))
    schalter.nicht_stoeren_geaendert.connect(lambda w: einstellungen.__setitem__("nicht_stoeren", w))
    schalter.monitor_bleiben_geaendert.connect(lambda w: einstellungen.__setitem__("monitor_bleiben", w))

    bus = EventBus()
    avatar_id = einstellungen.get("avatar", STANDARD_AVATAR)
    darsteller, avatar = avatar_laden(avatar_id, avatar_pfad)
    if avatar is None and (avatar_id != STANDARD_AVATAR or avatar_pfad is not None):
        darsteller, avatar = avatar_laden(STANDARD_AVATAR)
    if avatar_pfad is not None:
        log.info("Entwickler-Start mit Avatar aus %s", avatar_pfad)
    werte = avatar.werte if avatar else Werte()          # Verhalten gehört zum Avatar
    motor = Verhaltensmotor(bus, Eigenleben(werte=werte))
    icon = avatar_icon(avatar) or blob.icon()
    app.setWindowIcon(icon)
    toene = Toene(pfade.datenordner() / "cache" / "toene",
                  lautstaerke=float(einstellungen.get("lautstaerke", 0.35)),
                  avatar_toene=avatar.toene if avatar else None,
                  koerper_toene=avatar.koerper_toene if avatar else None)
    lauftempo = avatar.lauftempo if avatar else werte["laufgeschwindigkeit"]
    name = lambda: einstellungen.get("name") or (avatar.name if avatar else "DMNT-Kobold")  # noqa: E731

    def beenden() -> None:
        log.info("Beenden über Menü")
        app.quit()

    fenster = AvatarFenster(bus, motor, schalter, toene, beenden, darsteller, lauftempo, werte["zieltempo"],
                            werte=werte)
    fenster.klick_oeffnet_einrichten = avatar_pfad is None
    for teil in (avatar.zubehoer_immer if avatar else []):     # z. B. ein Hut, den er immer trägt
        motor.zubehoer_setzen(teil, True, "avatar")
    if schalter.nicht_stoeren:
        motor.nicht_stoeren = True
        toene.stumm = True

    # Position vom letzten Mal (danach regelt die Physik den Boden)
    pos = zustand.get("position")
    if isinstance(pos, dict) and "x" in pos:
        k = fenster.koerper
        k.x, k.y = float(pos["x"]), float(pos.get("y", k.y))
        k.pruefe_monitore(fenster.monitore)

    persoenlichkeiten = persoenlichkeiten_laden(avatar, bus, motor, werte)
    log.info("Verhalten: %s%s", ", ".join(type(p).__name__ for p in persoenlichkeiten),
             " (ohne Code)" if avatar is not None and avatar.ohne_code else "")
    beobachter = Beobachter(bus, fenster.kopf_mitte, os.getpid(), parent=app,
                            beobachtete_programme=beobachtete_programme(persoenlichkeiten), werte=werte)

    def programme_uebernehmen() -> None:
        beobachter.ignorierte_programme = {exe for exe, w in einstellungen.get("programme", {}).items()
                                           if w.get("ignorieren", True)}
    programme_uebernehmen()

    # --- Tricks ------------------------------------------------------------------
    hotkeys = Hotkeys(bus)
    verwaltung = Modulverwaltung(bus, motor, ablage, hotkeys)

    def karten_punkt() -> QPoint:
        x, y = fenster.position()
        return QPoint(int(x), int(y - darsteller.hoehe - 16))
    verwaltung.karten_punkt = karten_punkt
    verwaltung.alle_starten()
    fenster.menue_eintraege = verwaltung.menue_eintraege
    sekunde = QTimer(app)
    sekunde.timeout.connect(verwaltung.takt)
    sekunde.start(1000)

    # --- Einrichten ----------------------------------------------------------------
    tray = None
    buehne_ref: dict = {}

    def umbenannt(neu: str) -> None:
        if tray is not None:
            tray.setToolTip(neu)
        bus.senden("avatar.umbenannt", name=neu)

    def nach_import() -> None:
        verwaltung.alle_beenden()
        verwaltung.alle_starten()
        toene.lautstaerke_setzen(float(einstellungen.get("lautstaerke", toene.lautstaerke)))
        programme_uebernehmen()
        schalter.setze_nicht_stoeren(bool(einstellungen.get("nicht_stoeren", False)))
        schalter.setze_monitor_bleiben(bool(einstellungen.get("monitor_bleiben", False)))
        umbenannt(name())

    def dienste() -> Dienste:
        return Dienste(
            einstellungen=einstellungen, verwaltung=verwaltung, toene=toene, sicherung=sicherung,
            version=__version__, avatar_name=avatar.name if avatar else "DMNT-Kobold",
            herkunft=avatar.herkunft if avatar else None,
            autostart_an=autostart.ist_an, autostart_setzen=autostart.setzen,
            zuletzt_programme=lambda: [p for p in beobachter.zuletzt if p not in SYSTEM_PROGRAMME],
            avatare=avatar_liste, aktueller_avatar=avatar.id if avatar else "",
            nach_import=nach_import, umbenannt=umbenannt,
            lautstaerke_geaendert=toene.lautstaerke_setzen,
            programme_geaendert=programme_uebernehmen,
        )

    def einrichten_oeffnen() -> None:
        if fenster.einrichten_aktiv:
            buehne = buehne_ref.get("buehne")
            if buehne is not None:
                buehne.activateWindow()
            return
        x, y = fenster.position()
        screen = QGuiApplication.screenAt(QPoint(int(x), int(y) - 10)) or QGuiApplication.primaryScreen()
        ort: QRect = screen.availableGeometry()
        fenster.einrichten_aktiv = True
        wid = motor.wunsch(animation="ruhe", prioritaet=100, dauer_s=None, quelle="einrichten")
        buehne = Einrichten(ort, dienste())
        buehne_ref["buehne"] = buehne
        buehne.show()
        buehne.raise_()
        buehne.activateWindow()
        win32.besitzer_setzen(int(fenster.winId()), int(buehne.winId()))
        win32.ganz_nach_vorne(int(fenster.winId()))
        ziel = buehne.avatar_ziel()
        fenster.schweben_nach(ziel.x(), ziel.y(), 1.0)
        bus.senden("avatar.einrichten_auf")
        log.info("Einrichten auf")

        def zurueck() -> None:
            fenster.springen_nach(x, y, 0.85)

        def zu() -> None:
            win32.besitzer_setzen(int(fenster.winId()), None)
            motor.zurueckziehen(wid)
            if fenster._fuehrung is None:            # noqa: SLF001 – Sprung schon fertig/abgebrochen
                fenster._festgehalten = False        # noqa: SLF001
            fenster.einrichten_aktiv = False
            buehne_ref.pop("buehne", None)
            win32.ganz_nach_vorne(int(fenster.winId()))
            bus.senden("avatar.einrichten_zu")
            log.info("Einrichten zu")

        buehne.zu_beginnt.connect(zurueck)
        buehne.geschlossen.connect(zu)

    fenster.beim_einrichten = einrichten_oeffnen

    tray = baue_tray(schalter, fenster.zurueckholen, beenden, icon=icon,
                     beim_einrichten=einrichten_oeffnen, name=name())
    if tray is None:
        log.warning("Kein Infobereich verfügbar – Tray-Icon fehlt")

    # --- Zustand sichern ---------------------------------------------------------
    def zustand_sichern() -> None:
        if fenster.einrichten_aktiv:
            return
        x, y = fenster.position()
        try:
            zustand["position"] = {"x": round(x, 1), "y": round(y, 1)}
        except OSError:
            log.exception("Zustand nicht gespeichert")

    zustand_timer = QTimer(app)
    zustand_timer.timeout.connect(zustand_sichern)
    zustand_timer.start(ZUSTAND_ALLE_MS)

    def sicherung_pruefen() -> None:
        try:
            sicherung.taeglich()
        except OSError:
            log.exception("Tägliche Sicherung fehlgeschlagen")

    sicherung_timer = QTimer(app)
    sicherung_timer.timeout.connect(sicherung_pruefen)
    sicherung_timer.start(SICHERUNG_PRUEFEN_MS)

    # --- Autostart beim ersten Start abfragen ---------------------------------------
    def autostart_fragen() -> None:
        if einstellungen.get("autostart_gefragt"):
            return

        def antwort(knopf: str) -> None:
            einstellungen["autostart_gefragt"] = True
            if knopf == "Ja":
                autostart.setzen(True)

        motor.wunsch(animation="sprechen", text="Soll ich jedes Mal mit Windows starten?",
                     knoepfe=("Ja", "Nein"), prioritaet=60, dauer_s=None, aufheben=True,
                     quelle="autostart", beim_knopf=antwort)

    def autostart_zu(e) -> None:
        if e.daten.get("quelle") == "autostart":
            einstellungen["autostart_gefragt"] = True
    bus.abonnieren("sprechblase.zu", autostart_zu)
    if avatar_pfad is None:                  # Entwickler-Start: echten Autostart nie anfassen
        QTimer.singleShot(AUTOSTART_FRAGE_NACH_MS, autostart_fragen)

    # --- Monitore -------------------------------------------------------------------
    # Änderungen gebündelt und verzögert auswerten: Windows meldet beim Abstecken
    # mehrere Signale, und screenRemoved kommt, bevor die Liste stimmt.
    entprellen = QTimer()
    entprellen.setSingleShot(True)
    entprellen.setInterval(300)
    entprellen.timeout.connect(fenster.monitore_aktualisieren)
    geaendert = lambda *_: entprellen.start()  # noqa: E731

    def bildschirm_verbinden(screen) -> None:
        screen.geometryChanged.connect(geaendert)
        screen.availableGeometryChanged.connect(geaendert)
        screen.logicalDotsPerInchChanged.connect(geaendert)

    for s in app.screens():
        bildschirm_verbinden(s)
    app.screenAdded.connect(lambda s: (bildschirm_verbinden(s), geaendert()))
    app.screenRemoved.connect(geaendert)
    app.primaryScreenChanged.connect(geaendert)

    fenster.show()
    code = app.exec()
    zustand_sichern()
    verwaltung.alle_beenden()
    hotkeys.alle_freigeben()
    log.info("Ende (Code %s)", code)
    sperre.unlock()
    return code
