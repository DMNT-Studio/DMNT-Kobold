"""Rechtsklick-Menü (nur sein Verhalten) und die gemeinsamen Schalter (auch vom Tray genutzt)."""
from __future__ import annotations

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QAction, QFontDatabase
from PySide6.QtWidgets import QLabel, QMenu, QWidget, QWidgetAction

AKZENT_HELL = "#E3EFEA"
TEXT = "#1D2320"
NEBENTEXT = "#4A534E"
ROT = "#A13A2C"


def schriftart() -> str:
    return "Manrope" if "Manrope" in QFontDatabase.families() else "Segoe UI"


def stylesheet() -> str:
    return f"""
    QMenu {{
        background: #FFFFFF;
        border: 1px solid #DADDD8;
        border-radius: 12px;
        padding: 6px;
        font-family: "{schriftart()}";
        font-size: 14px;
        font-weight: 600;
        color: {TEXT};
    }}
    QMenu::item {{
        min-height: 40px;
        padding: 0px 18px 0px 12px;
        border-radius: 8px;
    }}
    QMenu::item:selected {{ background: {AKZENT_HELL}; }}
    QMenu::item:disabled {{ color: #A3AAA6; }}
    QMenu::item:disabled:selected {{ background: transparent; }}
    QMenu::separator {{ height: 1px; background: #E6E8E4; margin: 6px 8px; }}
    QMenu::indicator {{ width: 16px; height: 16px; margin-left: 6px; }}
    QMenu::indicator:non-exclusive:unchecked {{
        border: 1.5px solid #9AA39E; border-radius: 4px; background: #FFFFFF;
    }}
    QMenu::indicator:non-exclusive:checked {{
        border: 1.5px solid #2F6F5E; border-radius: 4px; background: #2F6F5E;
    }}
    QLabel#beenden {{
        color: {ROT};
        min-height: 40px;
        padding: 0px 18px 0px 34px;
        border-radius: 8px;
        font-family: "{schriftart()}";
        font-size: 14px;
        font-weight: 600;
    }}
    QLabel#beenden:hover {{ background: {AKZENT_HELL}; }}
    """


class Schalter(QObject):
    """Gemeinsame Umschalter für Menü und Tray (app.py speichert sie in den Einstellungen)."""

    nicht_stoeren_geaendert = Signal(bool)
    monitor_bleiben_geaendert = Signal(bool)

    def __init__(self) -> None:
        super().__init__()
        self._nicht_stoeren = False
        self._monitor_bleiben = False

    @property
    def nicht_stoeren(self) -> bool:
        return self._nicht_stoeren

    def setze_nicht_stoeren(self, wert: bool) -> None:
        if wert != self._nicht_stoeren:
            self._nicht_stoeren = wert
            self.nicht_stoeren_geaendert.emit(wert)

    @property
    def monitor_bleiben(self) -> bool:
        return self._monitor_bleiben

    def setze_monitor_bleiben(self, wert: bool) -> None:
        if wert != self._monitor_bleiben:
            self._monitor_bleiben = wert
            self.monitor_bleiben_geaendert.emit(wert)


class _BeendenEintrag(QWidgetAction):
    """Roter Menüeintrag (Stylesheets können einzelne QActions nicht färben)."""

    def __init__(self, menue: QMenu, beim_beenden) -> None:
        super().__init__(menue)
        self._menue = menue
        self._beim_beenden = beim_beenden

    def createWidget(self, parent: QWidget) -> QWidget:  # noqa: N802 (Qt-API)
        label = QLabel("Beenden", parent)
        label.setObjectName("beenden")
        label.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        label.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        label.mouseReleaseEvent = lambda _e: (self._menue.close(), self._beim_beenden())
        return label


def menue_rahmen(parent: QWidget | None = None) -> QMenu:
    """Leeres Menü im Kobold-Stil (rahmenlos, runde Ecken)."""
    menue = QMenu(parent)
    menue.setWindowFlags(menue.windowFlags() | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
    menue.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menue.setStyleSheet(stylesheet())
    menue.setToolTipsVisible(True)
    return menue


def schalter_eintrag(menue: QMenu, text: str, wert: bool, setzen, geaendert) -> QAction:
    """Umschaltbarer Eintrag mit Häkchen, der dem Schalter folgt."""
    a = QAction(text, menue, checkable=True)
    a.setChecked(wert)
    a.toggled.connect(setzen)
    geaendert.connect(a.setChecked)
    menue.addAction(a)
    return a


def baue_menue(schalter: Schalter, parent: QWidget | None = None) -> QMenu:
    """Rechtsklick am Avatar: nur sein Verhalten (Konzept #28). Einrichten, Tricks
    und Beenden betreffen das Programm und liegen im Tray."""
    menue = menue_rahmen(parent)
    schalter_eintrag(menue, "Nicht stören", schalter.nicht_stoeren, schalter.setze_nicht_stoeren,
                     schalter.nicht_stoeren_geaendert)
    schalter_eintrag(menue, "Auf diesem Monitor bleiben", schalter.monitor_bleiben,
                     schalter.setze_monitor_bleiben, schalter.monitor_bleiben_geaendert)
    return menue
