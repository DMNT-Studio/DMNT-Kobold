"""Avatar-Editor: Das Mausrad verstellt keine Auswahllisten und Zahlenfelder, es scrollt die Seite."""
import sys
from pathlib import Path

from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import QApplication, QComboBox, QDoubleSpinBox, QScrollArea, QVBoxLayout, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "werkzeuge"))
from avatar_editor import KeinMausrad  # noqa: E402


def _rad(widget, nach_unten=True):
    delta = -120 if nach_unten else 120
    ev = QWheelEvent(QPointF(5, 5), QPointF(widget.mapToGlobal(QPoint(5, 5))), QPoint(0, 0), QPoint(0, delta),
                     Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    QApplication.sendEvent(widget, ev)


def test_mausrad_veraendert_nichts_und_scrollt_die_seite(qapp):
    filt = KeinMausrad()
    qapp.installEventFilter(filt)
    try:
        bereich = QScrollArea()
        innen = QWidget()
        lay = QVBoxLayout(innen)
        combo = QComboBox()
        combo.addItems(["a", "b", "c"])
        zahl = QDoubleSpinBox()
        zahl.setValue(1.0)
        lay.addWidget(combo)
        lay.addWidget(zahl)
        innen.setMinimumHeight(3000)
        bereich.setWidget(innen)
        bereich.resize(300, 200)
        bereich.show()
        qapp.processEvents()
        _rad(combo)
        _rad(zahl)
        assert combo.currentIndex() == 0 and zahl.value() == 1.0
        assert bereich.verticalScrollBar().value() > 0
        bereich.close()
    finally:
        qapp.removeEventFilter(filt)
