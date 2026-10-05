"""Gemeinsamer Stil (Konzept Abschnitt 10): hell, ruhig, ein Akzent Salbeigrün."""
from __future__ import annotations

from PySide6.QtGui import QFontDatabase

GRUND = "#F3F4F1"
FLAECHE = "#FFFFFF"
TEXT = "#1D2320"
NEBENTEXT = "#4A534E"
AKZENT = "#2F6F5E"
AKZENT_HELL = "#E3EFEA"
FREMD_HELL = "#F7EBDD"
FREMD_TEXT = "#7A4810"
LINIE = "#DADDD8"
ROT = "#A13A2C"


def schriftart() -> str:
    return "Manrope" if "Manrope" in QFontDatabase.families() else "Segoe UI"


def bedien_stylesheet() -> str:
    """Für Karten und Kacheln: Knöpfe, Eingabefelder, Schalter, Regler."""
    s = schriftart()
    return f"""
    QWidget {{ font-family: "{s}"; color: {TEXT}; font-size: 14px; }}
    QLabel#titel {{ font-size: 17px; font-weight: 800; }}
    QLabel#neben {{ color: {NEBENTEXT}; font-size: 13px; }}
    QLabel#hinweis {{ color: {ROT}; font-size: 13px; }}
    QLabel#marke_offiziell {{ background: {AKZENT_HELL}; color: {AKZENT}; border-radius: 8px;
        padding: 2px 8px; font-size: 12px; font-weight: 600; }}
    QLabel#marke_fremd {{ background: {FREMD_HELL}; color: {FREMD_TEXT}; border-radius: 8px;
        padding: 2px 8px; font-size: 12px; font-weight: 600; }}
    QPushButton {{ min-height: 40px; padding: 0 16px; border-radius: 10px; font-weight: 600;
        background: {FLAECHE}; border: 1px solid {LINIE}; }}
    QPushButton:hover {{ background: {AKZENT_HELL}; }}
    QPushButton#haupt {{ background: {AKZENT}; color: white; border: none; }}
    QPushButton#haupt:hover {{ background: #285F51; }}
    QPushButton#klein {{ min-height: 28px; min-width: 28px; padding: 0 6px; border: none;
        background: transparent; color: {NEBENTEXT}; }}
    QPushButton#klein:hover {{ background: {AKZENT_HELL}; }}
    QLineEdit {{ min-height: 38px; padding: 0 10px; border: 1px solid {LINIE}; border-radius: 10px;
        background: {FLAECHE}; selection-background-color: {AKZENT}; }}
    QLineEdit:focus {{ border: 1.5px solid {AKZENT}; }}
    QCheckBox {{ spacing: 10px; min-height: 36px; }}
    QCheckBox::indicator {{ width: 38px; height: 22px; border-radius: 11px; background: #C9CEC9; }}
    QCheckBox::indicator:checked {{ background: {AKZENT}; }}
    QCheckBox::indicator:disabled {{ background: #E3E5E1; }}
    QSlider::groove:horizontal {{ height: 6px; border-radius: 3px; background: #D9DDD8; }}
    QSlider::sub-page:horizontal {{ border-radius: 3px; background: {AKZENT}; }}
    QSlider::handle:horizontal {{ width: 22px; height: 22px; margin: -8px 0; border-radius: 11px;
        background: {FLAECHE}; border: 2px solid {AKZENT}; }}
    QScrollArea {{ background: transparent; border: none; }}
    """
