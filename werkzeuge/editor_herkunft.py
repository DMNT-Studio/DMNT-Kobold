"""Reiter „Herkunft & Töne“ im Avatar-Editor.

Herkunft: das runde Hintergrundbild hinter dem Sockel im Einrichten. Ein neues Bild wird in
den Quellordner kopiert (altes nach _alt/), Ebenen (z. B. ein Schiff über dem Weltraum)
werden dabei entfernt, weil sie zum alten Bild gehörten.

Töne: je Moment des Sockels (landen, absprung, sprechen …) eine oder mehrere Dateien
(.wav, .ogg, .mp3, .flac, .m4a), Tonhöhen-Streuung und Wiederholungen. Eingebaute, synthetisierte Töne aus dem
Bauplan werden angezeigt und lassen sich durch Dateien ersetzen. „Anhören“ spielt die Datei
direkt (ohne Bau). Jede Änderung speichert den Bauplan; der Editor baut dann wie gewohnt neu.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QImage, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QDoubleSpinBox, QFileDialog, QFrame, QGridLayout, QHBoxLayout, QLabel,
                               QPushButton, QScrollArea, QSpinBox, QVBoxLayout, QWidget)

from dmnt_kobold import katalog, stil

BILDER = "Bilder (*.png *.jpg *.jpeg *.webp *.svg)"
TOENE = "Töne (*.wav *.ogg *.mp3 *.flac *.m4a)"
GRAU = "#8A938E"
AVATARE = Path(__file__).resolve().parents[1] / "src" / "dmnt_kobold" / "avatare"


def _frisch(pfad: Path) -> QPixmap:
    """Immer frisch von der Platte (ohne Qts Bild-Cache)."""
    return QPixmap.fromImage(QImage(str(pfad)))


# --- Datenänderungen (ohne Fenster, testbar) ---------------------------------------

def herkunft_setzen(projekt, datei: Path) -> str:
    """Neues Herkunftsbild übernehmen → Dateiname im Quellordner."""
    ziel = projekt.ordner / f"herkunft{datei.suffix.lower()}"
    alt = projekt.bauplan.get("herkunft", {}).get("hintergrund")
    if alt:
        projekt._sichern(projekt.ordner / alt)          # noqa: SLF001
    if datei.resolve() != ziel.resolve():
        if ziel.exists():
            projekt._sichern(ziel)                      # noqa: SLF001
        shutil.copy2(datei, ziel)
    h = projekt.bauplan.setdefault("herkunft", {})
    h["hintergrund"] = ziel.name
    h.setdefault("groesse", 768)
    h.pop("ebenen", None)
    projekt.bauplan_speichern()
    return ziel.name


def herkunft_entfernen(projekt) -> None:
    alt = projekt.bauplan.get("herkunft", {}).get("hintergrund")
    if alt:
        projekt._sichern(projekt.ordner / alt)          # noqa: SLF001
    projekt.bauplan.pop("herkunft", None)
    projekt.bauplan_speichern()


def ton_hinzufuegen(projekt, moment: str, datei: Path) -> str:
    """Tondatei für einen Moment übernehmen (nach toene/). Ein eingebauter, synthetisierter
    Ton dieses Moments wird dadurch ersetzt."""
    ordner = projekt.ordner / "toene"
    ordner.mkdir(exist_ok=True)
    name = datei.name
    ziel = ordner / name
    if ziel.exists() and ziel.resolve() != datei.resolve():
        stamm, nr = datei.stem, 2
        while ziel.exists():
            ziel = ordner / f"{stamm}_{nr}{datei.suffix.lower()}"
            nr += 1
    if ziel.resolve() != datei.resolve():
        shutil.copy2(datei, ziel)
    toene = projekt.bauplan.setdefault("toene", {})
    t = toene.get(moment)
    if t is None or "segmente" in t:
        t = toene[moment] = {"dateien": [], "tonhoehe": 0.08}
    rel = f"toene/{ziel.name}"
    if rel not in t["dateien"]:
        t["dateien"].append(rel)
    projekt.bauplan_speichern()
    return rel


def ton_entfernen(projekt, moment: str, rel: str) -> None:
    """Datei aus dem Moment nehmen (sie bleibt im Ordner). Letzte Datei → Moment ohne Ton."""
    toene = projekt.bauplan.get("toene", {})
    t = toene.get(moment)
    if t is None:
        return
    if "segmente" in t:
        del toene[moment]
    else:
        t["dateien"] = [d for d in t.get("dateien", []) if d != rel]
        if not t["dateien"]:
            del toene[moment]
    if not toene:
        projekt.bauplan.pop("toene", None)
    projekt.bauplan_speichern()


def ton_einstellen(projekt, moment: str, tonhoehe: float | None = None,
                   wiederholen: tuple[int, int] | None = None) -> None:
    t = projekt.bauplan.get("toene", {}).get(moment)
    if t is None or "segmente" in t:
        return
    if tonhoehe is not None:
        t["tonhoehe"] = round(max(0.0, min(0.5, tonhoehe)), 3)
    if wiederholen is not None:
        von, bis = max(1, min(5, wiederholen[0])), max(1, min(5, wiederholen[1]))
        if (von, bis) == (1, 1):
            t.pop("wiederholen", None)
        else:
            t["wiederholen"] = [min(von, bis), max(von, bis)]
    projekt.bauplan_speichern()


# --- Fenster -----------------------------------------------------------------------

def _rund(pm: QPixmap, d: int) -> QPixmap:
    """Bild als runder Ausschnitt, wie im Einrichten."""
    aus = QPixmap(d, d)
    aus.fill(Qt.GlobalColor.transparent)
    if pm.isNull():
        return aus
    s = max(d / pm.width(), d / pm.height())
    b = pm.scaled(round(pm.width() * s), round(pm.height() * s), Qt.AspectRatioMode.IgnoreAspectRatio,
                  Qt.TransformationMode.SmoothTransformation)
    p = QPainter(aus)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    pfad = QPainterPath()
    pfad.addEllipse(0, 0, d, d)
    p.setClipPath(pfad)
    p.drawPixmap((d - b.width()) // 2, (d - b.height()) // 2, b)
    p.end()
    return aus


class HerkunftToeneTab(QWidget):
    def __init__(self, editor) -> None:
        super().__init__()
        self.editor = editor
        self._player = None
        lay = QVBoxLayout(self)
        info = QLabel("Hintergrund im Einrichten und die Töne des Körpers. Änderungen werden sofort "
                      "gespeichert, danach baut der Editor neu – „Kobold neu starten“ zeigt das Ergebnis.")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.bereich = QScrollArea()
        self.bereich.setWidgetResizable(True)
        lay.addWidget(self.bereich)

    @property
    def projekt(self):
        return self.editor.projekt

    def aufbauen(self) -> None:
        innen = QWidget()
        lay = QVBoxLayout(innen)
        lay.setSpacing(16)
        lay.addWidget(self._herkunft_karte())
        lay.addWidget(self._toene_karte())
        lay.addStretch(1)
        self.bereich.setWidget(innen)

    # Herkunft ------------------------------------------------------------------------
    def _herkunft_karte(self) -> QFrame:
        karte = QFrame()
        karte.setObjectName("karte")
        h = QHBoxLayout(karte)
        h.setContentsMargins(18, 16, 18, 16)
        h.setSpacing(18)
        plan = self.projekt.bauplan.get("herkunft") or {}
        datei = plan.get("hintergrund")
        bild = QLabel()
        bild.setFixedSize(180, 180)
        bild.setAlignment(Qt.AlignmentFlag.AlignCenter)
        vorschau = self._herkunft_vorschau()
        if vorschau is not None and not vorschau.isNull():
            bild.setPixmap(_rund(vorschau, 176))
        else:
            bild.setText("kein Bild\n(grüner Verlauf)")
            bild.setStyleSheet(f"background: {stil.AKZENT_HELL}; border-radius: 88px; color: {GRAU};")
        h.addWidget(bild)
        rechts = QVBoxLayout()
        titel = QLabel("Herkunft")
        titel.setStyleSheet("font-weight: 800; font-size: 16px;")
        rechts.addWidget(titel)
        text = f"Datei: {datei}" if datei else "Kein eigenes Bild – im Einrichten erscheint ein grüner Verlauf."
        if plan.get("ebenen"):
            text += f"\nDarüber {len(plan['ebenen'])} Ebene(n): " + ", ".join(e["datei"] for e in plan["ebenen"])
        t = QLabel(text)
        t.setObjectName("neben")
        t.setWordWrap(True)
        rechts.addWidget(t)
        hinweis = QLabel("Ein quadratisches oder breites Bild, mindestens 768 px. Es wird rund ausgeschnitten "
                         "(Mitte zählt). PNG, JPG, WEBP oder SVG.")
        hinweis.setWordWrap(True)
        hinweis.setStyleSheet(f"color: {GRAU};")
        rechts.addWidget(hinweis)
        knoepfe = QHBoxLayout()
        waehlen = QPushButton("Bild wählen …")
        waehlen.setObjectName("haupt")
        waehlen.clicked.connect(self._herkunft_waehlen)
        knoepfe.addWidget(waehlen)
        if datei:
            oeffnen_k = QPushButton("Öffnen")
            oeffnen_k.clicked.connect(lambda: self._oeffnen(self.projekt.ordner / datei))
            knoepfe.addWidget(oeffnen_k)
            weg = QPushButton("Entfernen")
            weg.clicked.connect(self._herkunft_entfernen)
            knoepfe.addWidget(weg)
        knoepfe.addStretch(1)
        rechts.addLayout(knoepfe)
        rechts.addStretch(1)
        h.addLayout(rechts, 1)
        return karte

    def _herkunft_vorschau(self) -> QPixmap | None:
        """Bevorzugt das gebaute Bild (mit Ebenen), sonst die Quelle."""
        gebaut = AVATARE / self.projekt.id / "herkunft.jpg"
        datei = (self.projekt.bauplan.get("herkunft") or {}).get("hintergrund")
        if not datei:
            return None
        quelle = self.projekt.ordner / datei
        if gebaut.exists() and quelle.exists() and gebaut.stat().st_mtime >= quelle.stat().st_mtime:
            return _frisch(gebaut)
        return _frisch(quelle)

    def _herkunft_waehlen(self) -> None:
        datei, _ = QFileDialog.getOpenFileName(self, "Herkunft – Hintergrundbild", str(Path.home() / "Downloads"),
                                               BILDER)
        if not datei:
            return
        hatte_ebenen = bool((self.projekt.bauplan.get("herkunft") or {}).get("ebenen"))
        name = herkunft_setzen(self.projekt, Path(datei))
        self.editor.meldung(f"Herkunft: {name} übernommen" + (" (alte Ebenen entfernt)" if hatte_ebenen else "")
                            + ". Das alte Bild liegt in _alt/.")
        self.aufbauen()
        self.editor.geaendert()

    def _herkunft_entfernen(self) -> None:
        herkunft_entfernen(self.projekt)
        self.editor.meldung("Herkunft entfernt (Bild liegt in _alt/). Im Einrichten erscheint ein Verlauf.")
        self.aufbauen()
        self.editor.geaendert()

    # Töne ------------------------------------------------------------------------------
    def _toene_karte(self) -> QFrame:
        karte = QFrame()
        karte.setObjectName("karte")
        v = QVBoxLayout(karte)
        v.setContentsMargins(18, 16, 18, 16)
        kopf = QHBoxLayout()
        titel = QLabel("Töne des Körpers")
        titel.setStyleSheet("font-weight: 800; font-size: 16px;")
        kopf.addWidget(titel)
        kopf.addStretch(1)
        zurueck = QPushButton("Töne zurücksetzen …")
        zurueck.setToolTip("Auf den Stand im Repo oder eine frühere Fassung aus dem Verlauf zurück")
        zurueck.clicked.connect(self._toene_zuruecksetzen)
        kopf.addWidget(zurueck)
        v.addLayout(kopf)
        erkl = QLabel("Zu jedem Moment kann ein Ton kommen. Mehrere Dateien = jedes Mal eine zufällige. "
                      "Streuung = Tonhöhe schwankt um ± so viel (0,08 = 8 %). Wiederholen = 1 bis n Mal hintereinander "
                      "(z. B. Piepsen beim Sprechen). Laut oder leise regelt nur der Nutzer.")
        erkl.setObjectName("neben")
        erkl.setWordWrap(True)
        v.addWidget(erkl)
        gitter = QGridLayout()
        gitter.setHorizontalSpacing(14)
        gitter.setVerticalSpacing(10)
        for spalte, kopf in enumerate(("Moment", "Dateien", "Streuung", "Wiederholen", "")):
            k = QLabel(kopf)
            k.setStyleSheet(f"font-weight: 700; color: {GRAU};")
            gitter.addWidget(k, 0, spalte)
        toene = self.projekt.bauplan.get("toene", {})
        alle = list(katalog.momente()) + sorted(n for n in toene if n not in katalog.momente())
        momente = [m for m in alle if m in toene] + [m for m in alle if m not in toene]   # belegte zuerst
        for zeile, moment in enumerate(momente, 1):
            self._ton_zeile(gitter, zeile, moment, toene.get(moment))
        gitter.setColumnStretch(1, 1)
        v.addLayout(gitter)
        return karte

    def _ton_zeile(self, gitter: QGridLayout, zeile: int, moment: str, t: dict | None) -> None:
        name = QLabel(moment)
        name.setStyleSheet("font-weight: 700;")
        beschreibung = katalog.KERN_ANIMATIONEN.get(moment, ("eigener Ton für Regeln (Aktion „ton“)", ""))[0]
        name.setToolTip(beschreibung)
        links = QVBoxLayout()
        links.setSpacing(0)
        links.addWidget(name)
        b = QLabel(beschreibung)
        b.setStyleSheet(f"color: {GRAU}; font-size: 12px;")
        b.setWordWrap(True)
        b.setMaximumWidth(230)
        links.addWidget(b)
        gitter.addLayout(links, zeile, 0, Qt.AlignmentFlag.AlignTop)

        dateien = QHBoxLayout()
        dateien.setSpacing(6)
        if t is not None and "segmente" in t:
            s = QLabel("eingebauter Ton (synthetisch)")
            s.setStyleSheet(f"color: {GRAU};")
            dateien.addWidget(s)
            if moment in katalog.momente():
                ersetzen = QPushButton("Durch Datei ersetzen …")
                ersetzen.clicked.connect(lambda _=False, m=moment: self._ton_waehlen(m))
                dateien.addWidget(ersetzen)
        else:
            for rel in (t or {}).get("dateien", []):
                dateien.addWidget(self._datei_chip(moment, rel))
            dazu = QPushButton("+ Datei" if t else "Ton hinzufügen …")
            dazu.setStyleSheet("min-height: 30px; padding: 0 10px;")
            dazu.clicked.connect(lambda _=False, m=moment: self._ton_waehlen(m))
            dateien.addWidget(dazu)
        dateien.addStretch(1)
        gitter.addLayout(dateien, zeile, 1, Qt.AlignmentFlag.AlignTop)

        if t is not None and "segmente" not in t:
            streu = QDoubleSpinBox()
            streu.setRange(0.0, 0.5)
            streu.setSingleStep(0.01)
            streu.setDecimals(2)
            streu.setValue(float(t.get("tonhoehe", 0.0)))
            streu.valueChanged.connect(lambda w, m=moment: self._einstellen(m, tonhoehe=w))
            gitter.addWidget(streu, zeile, 2, Qt.AlignmentFlag.AlignTop)
            wdh = QHBoxLayout()
            von, bis = (t.get("wiederholen") or [1, 1])
            sv, sb = QSpinBox(), QSpinBox()
            for sp, w in ((sv, von), (sb, bis)):
                sp.setRange(1, 5)
                sp.setValue(int(w))
            sv.valueChanged.connect(lambda _w, m=moment, a=sv, b2=sb: self._einstellen(m, wiederholen=(a.value(), b2.value())))
            sb.valueChanged.connect(lambda _w, m=moment, a=sv, b2=sb: self._einstellen(m, wiederholen=(a.value(), b2.value())))
            wdh.addWidget(sv)
            wdh.addWidget(QLabel("bis"))
            wdh.addWidget(sb)
            gitter.addLayout(wdh, zeile, 3, Qt.AlignmentFlag.AlignTop)

    def _datei_chip(self, moment: str, rel: str) -> QFrame:
        chip = QFrame()
        vorhanden = (self.projekt.ordner / rel).is_file()
        chip.setStyleSheet(f"QFrame {{ background: {stil.AKZENT_HELL if vorhanden else '#F7E3DF'};"
                           " border-radius: 14px; }}")
        h = QHBoxLayout(chip)
        h.setContentsMargins(10, 2, 4, 2)
        h.setSpacing(4)
        name = QLabel(Path(rel).name + ("" if vorhanden else "  (fehlt)"))
        if not vorhanden:
            name.setStyleSheet(f"color: {stil.ROT};")
        h.addWidget(name)
        if vorhanden:
            hoeren = QPushButton("▶")
            hoeren.setObjectName("klein")
            hoeren.setToolTip("Anhören")
            hoeren.clicked.connect(lambda: self._abspielen(self.projekt.ordner / rel))
            h.addWidget(hoeren)
        weg = QPushButton("×")
        weg.setObjectName("klein")
        weg.setToolTip("Aus diesem Moment entfernen (Datei bleibt im Ordner)")
        weg.clicked.connect(lambda: self._ton_entfernen(moment, rel))
        h.addWidget(weg)
        return chip

    def _ton_waehlen(self, moment: str) -> None:
        dateien, _ = QFileDialog.getOpenFileNames(self, f"Ton für „{moment}“", str(Path.home() / "Downloads"), TOENE)
        if not dateien:
            return
        for d in dateien:
            ton_hinzufuegen(self.projekt, moment, Path(d))
        self.editor.meldung(f"Ton für {moment}: {len(dateien)} Datei(en) übernommen.")
        self.aufbauen()
        self.editor.geaendert()

    def _ton_entfernen(self, moment: str, rel: str) -> None:
        ton_entfernen(self.projekt, moment, rel)
        self.editor.meldung(f"{Path(rel).name} aus {moment} entfernt (Datei bleibt in toene/).")
        self.aufbauen()
        self.editor.geaendert()

    def _toene_zuruecksetzen(self) -> None:
        from editor_zuruecksetzen import fragen_und_zuruecksetzen  # noqa: PLC0415

        stand = fragen_und_zuruecksetzen(self, self.projekt, "toene")
        if stand is None:
            return
        self.editor.meldung(f"Töne zurückgesetzt auf: {stand.name} {stand.zeit}".strip()
                            + ". Der vorige Stand liegt im Verlauf.")
        self.aufbauen()
        self.editor.geaendert()

    def _einstellen(self, moment: str, **kw) -> None:
        ton_einstellen(self.projekt, moment, **kw)
        self.editor.geaendert()

    def _abspielen(self, pfad: Path) -> None:
        try:
            from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer  # noqa: PLC0415
        except ImportError:
            self._oeffnen(pfad)
            return
        if self._player is None:
            self._player = QMediaPlayer(self)
            self._ausgabe = QAudioOutput(self)
            self._ausgabe.setVolume(0.6)
            self._player.setAudioOutput(self._ausgabe)
        self._player.stop()
        self._player.setSource(QUrl.fromLocalFile(str(pfad)))
        self._player.play()

    @staticmethod
    def _oeffnen(pfad: Path) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(pfad)))
