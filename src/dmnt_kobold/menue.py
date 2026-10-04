"""Rechtsklick-Menü und die gemeinsamen Schalter (auch vom Tray genutzt)."""
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
    """Gemeinsame Umschalter für Menü und Tray (nicht gespeichert, kommt in M4)."""

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


def baue_menue(schalter: Schalter, beim_beenden, parent: QWidget | None = None) -> QMenu:
    menue = QMenu(parent)
    menue.setWindowFlags(menue.windowFlags() | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint)
    menue.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
    menue.setStyleSheet(stylesheet())
    menue.setToolTipsVisible(True)

    einrichten = QAction("Einrichten", menue)
    einrichten.setEnabled(False)
    einrichten.setToolTip("kommt in M4")
    menue.addAction(einrichten)

    ns = QAction("Nicht stören", menue, checkable=True)
    ns.setChecked(schalter.nicht_stoeren)
    ns.toggled.connect(schalter.setze_nicht_stoeren)
    schalter.nicht_stoeren_geaendert.connect(ns.setChecked)
    menue.addAction(ns)

    mb = QAction("Auf diesem Monitor bleiben", menue, checkable=True)
    mb.setChecked(schalter.monitor_bleiben)
    mb.toggled.connect(schalter.setze_monitor_bleiben)
    schalter.monitor_bleiben_geaendert.connect(mb.setChecked)
    menue.addAction(mb)

    menue.addSeparator()
    menue.addAction(_BeendenEintrag(menue, beim_beenden))
    return menue
