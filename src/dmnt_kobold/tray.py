"""Tray-Icon: alles, was das Programm betrifft (Konzept #28).

Menü: Einrichten, Einträge der Tricks (z. B. „Erinnern …“), Kobold zurückholen,
Nicht stören, Trennlinie, Beenden (rot). Doppelklick holt den Kobold zurück.
"""
from __future__ import annotations

from PySide6.QtGui import QAction
from PySide6.QtWidgets import QSystemTrayIcon

from . import blob
from .menue import Schalter, _BeendenEintrag, menue_rahmen, schalter_eintrag


def baue_tray_menue(schalter: Schalter, zurueckholen, beenden, beim_einrichten=None, eintraege=None):
    """``eintraege()`` liefert die Menüeinträge der Tricks [(Text, Funktion)] –
    sie werden bei jedem Öffnen frisch eingesetzt (unter „Einrichten“)."""
    menue = menue_rahmen()

    einrichten = QAction("Einrichten", menue)
    einrichten.setEnabled(beim_einrichten is not None)
    if beim_einrichten is not None:
        einrichten.triggered.connect(beim_einrichten)
    menue.addAction(einrichten)

    holen = QAction("Kobold zurückholen", menue)
    holen.triggered.connect(zurueckholen)
    menue.addAction(holen)
    schalter_eintrag(menue, "Nicht stören", schalter.nicht_stoeren, schalter.setze_nicht_stoeren,
                     schalter.nicht_stoeren_geaendert)
    menue.addSeparator()
    menue.addAction(_BeendenEintrag(menue, beenden))

    tricks: list[QAction] = []

    def tricks_einsetzen() -> None:
        for a in tricks:
            menue.removeAction(a)
            a.deleteLater()
        tricks.clear()
        liste = eintraege() if eintraege else []
        for text, funktion in liste:
            a = QAction(text, menue)
            a.triggered.connect(lambda _=False, f=funktion: f())
            menue.insertAction(holen, a)
            tricks.append(a)
        if liste:
            tricks.append(menue.insertSeparator(holen))

    menue.aboutToShow.connect(tricks_einsetzen)
    menue.tricks_einsetzen = tricks_einsetzen     # für Tests
    return menue


def baue_tray(schalter: Schalter, zurueckholen, beenden, icon=None, beim_einrichten=None,
              name: str = "DMNT-Kobold", eintraege=None) -> QSystemTrayIcon | None:
    if not QSystemTrayIcon.isSystemTrayAvailable():
        return None
    tray = QSystemTrayIcon(icon or blob.icon())
    tray.setToolTip(name)
    menue = baue_tray_menue(schalter, zurueckholen, beenden, beim_einrichten, eintraege)
    tray.setContextMenu(menue)
    tray._menue = menue  # Referenz halten
    tray.activated.connect(
        lambda grund: zurueckholen() if grund == QSystemTrayIcon.ActivationReason.DoubleClick else None
    )
    tray.show()
    return tray
