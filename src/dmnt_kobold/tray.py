"""Tray-Icon als Notausgang: Kobold zurückholen, Nicht stören, Beenden."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from . import blob
from .menue import Schalter, stylesheet


def baue_tray(schalter: Schalter, zurueckholen, beenden) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(blob.icon())
    tray.setToolTip("DMNT-Kobold")

    menue = QMenu()
    menue.setWindowFlags(menue.windowFlags() | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
    menue.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menue.setStyleSheet(stylesheet())

    holen = QAction("Kobold zurückholen", menue)
    holen.triggered.connect(zurueckholen)
    menue.addAction(holen)

    ns = QAction("Nicht stören", menue, checkable=True)
    ns.setChecked(schalter.nicht_stoeren)
    ns.toggled.connect(schalter.setze_nicht_stoeren)
    schalter.nicht_stoeren_geaendert.connect(ns.setChecked)
    menue.addAction(ns)

    menue.addSeparator()
    ende = QAction("Beenden", menue)
    ende.triggered.connect(beenden)
    menue.addAction(ende)

    tray.setContextMenu(menue)
    tray._menue = menue  # Referenz halten
    tray.activated.connect(
        lambda grund: zurueckholen() if grund == QSystemTrayIcon.ActivationReason.DoubleClick else None
    )
    tray.show()
    return tray
