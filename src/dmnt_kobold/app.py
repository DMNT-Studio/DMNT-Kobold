"""Einstieg: QApplication, Einzelinstanz, Logging, Verdrahtung."""
from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler

from PySide6.QtCore import QLockFile, Qt, QTimer
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QApplication

from . import __version__, blob, pfade

log = logging.getLogger("dmnt_kobold")


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


def main() -> int:
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
    log.info("Start DMNT-Kobold %s", __version__)

    # Erst nach QApplication importieren (Qt-Widgets)
    from .avatar import avatar_laden, persoenlichkeit_laden
    from .beobachter import Beobachter
    from .bus import EventBus
    from .menue import Schalter
    from .motor import Verhaltensmotor
    from .overlay import AvatarFenster
    from .toene import Toene
    from .tray import baue_tray

    app.setWindowIcon(blob.icon())
    schalter = Schalter()
    bus = EventBus()
    motor = Verhaltensmotor(bus)
    darsteller, avatar = avatar_laden()
    toene = Toene(pfade.datenordner() / "cache" / "toene",
                  avatar_toene=avatar.toene if avatar else None)
    lauftempo = float(avatar.bewegung.get("tempo", 60)) if avatar else 60.0

    def beenden() -> None:
        log.info("Beenden über Menü")
        app.quit()

    fenster = AvatarFenster(bus, motor, schalter, toene, beenden, darsteller, lauftempo)
    persoenlichkeit = persoenlichkeit_laden(avatar, bus, motor)  # noqa: F841 – lebt über den Bus
    log.info("Persönlichkeit: %s", type(persoenlichkeit).__name__)
    beobachter = Beobachter(bus, fenster.kopf_mitte, os.getpid(), parent=app,  # noqa: F841
                            beobachtete_programme=getattr(persoenlichkeit, "BEOBACHTETE_PROGRAMME", set()))
    tray = baue_tray(schalter, fenster.zurueckholen, beenden)
    if tray is None:
        log.warning("Kein Infobereich verfügbar – Tray-Icon fehlt")

    # Monitor-Änderungen gebündelt und verzögert auswerten: Windows meldet beim
    # Abstecken mehrere Signale, und screenRemoved kommt, bevor die Liste stimmt.
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
    log.info("Ende (Code %s)", code)
    sperre.unlock()
    return code
