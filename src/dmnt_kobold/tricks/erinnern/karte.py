"""Eingabekarte für den Trick „Erinnern“."""
from __future__ import annotations

from datetime import datetime

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QLineEdit, QPushButton, QWidget

from dmnt_kobold.karten import Karte
from dmnt_kobold.zeitangabe import zeit_text

MAX_ANZEIGE = 5


class ErinnernKarte(Karte):
    def __init__(self, modul) -> None:
        super().__init__(360)
        self.modul = modul
        titel = QLabel("Woran soll ich dich erinnern?")
        titel.setObjectName("titel")
        self.inhalt.addWidget(titel)

        self.text = QLineEdit()
        self.text.setPlaceholderText("z. B. Wäsche aufhängen")
        self.inhalt.addWidget(self.text)

        self.wann = QLineEdit()
        self.wann.setPlaceholderText("Wann? 10 min · 14:30 · morgen 9")
        self.inhalt.addWidget(self.wann)

        self.hinweis = QLabel("")
        self.hinweis.setObjectName("hinweis")
        self.hinweis.setWordWrap(True)
        self.hinweis.hide()
        self.inhalt.addWidget(self.hinweis)

        knoepfe = QHBoxLayout()
        knoepfe.addStretch(1)
        abbrechen = QPushButton("Abbrechen")
        abbrechen.clicked.connect(self.close)
        merken = QPushButton("Merken")
        merken.setObjectName("haupt")
        merken.setDefault(True)
        merken.clicked.connect(self._merken)
        knoepfe.addWidget(abbrechen)
        knoepfe.addWidget(merken)
        self.inhalt.addLayout(knoepfe)

        self.liste = QWidget()
        self.liste_layout = QHBoxLayout()  # Platzhalter, wird in _liste_bauen ersetzt
        self.inhalt.addWidget(self.liste)
        self._liste_bauen()

        self.text.returnPressed.connect(self.wann.setFocus)
        self.wann.returnPressed.connect(self._merken)
        if not modul.kuerzel_frei:
            neben = QLabel("Hinweis: Strg+Alt+E ist von einem anderen Programm belegt.")
            neben.setObjectName("neben")
            neben.setWordWrap(True)
            self.inhalt.addWidget(neben)
        self.text.setFocus()

    def _liste_bauen(self) -> None:
        from PySide6.QtWidgets import QVBoxLayout

        alt = self.liste.layout()
        if alt is not None:
            while alt.count():
                w = alt.takeAt(0).widget()
                if w:
                    w.deleteLater()
            QWidget().setLayout(alt)       # altes Layout entsorgen
        lay = QVBoxLayout(self.liste)
        lay.setContentsMargins(0, 6, 0, 0)
        lay.setSpacing(2)
        eintraege = sorted(self.modul.liste(), key=lambda e: e["faellig"])
        if not eintraege:
            self.liste.hide()
            return
        kopf = QLabel(f"Geplant ({len(eintraege)})")
        kopf.setObjectName("neben")
        lay.addWidget(kopf)
        for e in eintraege[:MAX_ANZEIGE]:
            zeile = QWidget()
            h = QHBoxLayout(zeile)
            h.setContentsMargins(0, 0, 0, 0)
            wann = QLabel(zeit_text(datetime.fromtimestamp(e["faellig"])))
            wann.setObjectName("neben")
            wann.setFixedWidth(130)
            text = QLabel(e["text"])
            text.setTextFormat(Qt.TextFormat.PlainText)
            weg = QPushButton("×")
            weg.setObjectName("klein")
            weg.setToolTip("Löschen")
            weg.clicked.connect(lambda _=False, eid=e["id"]: self._loeschen(eid))
            h.addWidget(wann)
            h.addWidget(text, 1)
            h.addWidget(weg)
            lay.addWidget(zeile)
        self.liste.show()
        self.adjustSize()

    def _loeschen(self, eid: str) -> None:
        self.modul.entfernen(eid)
        self._liste_bauen()

    def _merken(self) -> None:
        fehler = self.modul.merken(self.text.text(), self.wann.text())
        if fehler:
            self.hinweis.setText(fehler)
            self.hinweis.show()
            self.adjustSize()
            return
        self.close()
