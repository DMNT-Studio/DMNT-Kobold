"""Netz-Teil des Updates (Qt): prüfen, Setup laden, installieren.

Alles läuft asynchron über ``QNetworkAccessManager`` – die Animation wird nie
blockiert. Fehler (offline, Rate-Limit, Zeitüberschreitung) bleiben still und
landen nur im Log. Weiterleitungen werden nur zu GitHub-Adressen gefolgt.
"""
from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QObject, QProcess, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from . import update
from .update import Angebot, UpdateHinweis

log = logging.getLogger(__name__)

SETUP_ARGUMENTE = ["/SILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/CLOSEAPPLICATIONS"]
API_TIMEOUT_MS = 30_000
DOWNLOAD_TIMEOUT_MS = 10 * 60_000


def update_ordner() -> Path:
    ordner = Path(tempfile.gettempdir()) / "DMNT-Kobold-Update"
    ordner.mkdir(parents=True, exist_ok=True)
    return ordner


class UpdateDienst(QObject):
    def __init__(self, hinweis: UpdateHinweis, version: str,
                 vor_installation: Callable[[], None], beenden: Callable[[], None],
                 nach_fehlstart: Callable[[], None] = lambda: None, parent=None) -> None:
        super().__init__(parent)
        self.hinweis = hinweis
        self.version = version
        self.vor_installation = vor_installation
        self.beenden = beenden
        self.nach_fehlstart = nach_fehlstart
        self.netz = QNetworkAccessManager(self)
        self._laeuft = False
        self._info_wunsch: int | None = None
        hinweis.aktualisieren = self.aktualisieren
        hinweis.herunterladen = self.seite_oeffnen

        self.takt = QTimer(self)
        self.takt.timeout.connect(self.pruefen)
        self.nachhol_takt = QTimer(self)
        self.nachhol_takt.setInterval(update.NOCHMAL_MS)
        self.nachhol_takt.timeout.connect(self._nachholen)

    # --- Zeitplan ---------------------------------------------------------------
    def starten(self) -> None:
        if self.hinweis.art == "entwickler":
            log.info("Update-Prüfung aus (Entwickler-Start)")
            return
        QTimer.singleShot(update.ERSTE_PRUEFUNG_MS, self.pruefen)
        self.takt.start(update.INTERVALL_MS)

    def _nachholen(self) -> None:
        if self.hinweis.wartend is None or self.hinweis.nachholen():
            self.nachhol_takt.stop()

    # --- Netz ---------------------------------------------------------------------
    def _anfrage(self, url: str, timeout_ms: int) -> QNetworkRequest:
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"User-Agent", f"DMNT-Kobold/{self.version}".encode())
        req.setRawHeader(b"Accept", b"application/vnd.github+json")
        req.setAttribute(QNetworkRequest.Attribute.RedirectPolicyAttribute,
                         QNetworkRequest.RedirectPolicy.UserVerifiedRedirectPolicy)
        req.setTransferTimeout(timeout_ms)
        return req

    def _holen(self, url: str, timeout_ms: int) -> QNetworkReply:
        antwort = self.netz.get(self._anfrage(url, timeout_ms))

        def weiter(ziel: QUrl, a=antwort) -> None:
            if update.adresse_erlaubt(ziel.toString()):
                a.redirectAllowed.emit()
            else:
                log.warning("Update: Weiterleitung zu %s abgelehnt", ziel.host())
                a.abort()
        antwort.redirected.connect(weiter)
        return antwort

    def pruefen(self) -> None:
        if not self.hinweis.an or self._laeuft:
            return
        kanal = update.kanal()
        url = update.API_ALLE if kanal == "test" else update.API_NEUESTE
        antwort = self._holen(url, API_TIMEOUT_MS)

        def fertig() -> None:
            antwort.deleteLater()
            if antwort.error() != QNetworkReply.NetworkError.NoError:
                log.info("Update-Prüfung fehlgeschlagen: %s", antwort.errorString())
                return
            angebot = update.json_auswerten(bytes(antwort.readAll().data()), self.version, kanal)
            if angebot is None:
                log.info("Update-Prüfung: aktuell (%s)", self.version)
                return
            if not self.hinweis.melden(angebot) and self.hinweis.wartend is not None:
                self.nachhol_takt.start()
        antwort.finished.connect(fertig)

    # --- Knöpfe -------------------------------------------------------------------
    def seite_oeffnen(self, angebot: Angebot) -> None:
        QDesktopServices.openUrl(QUrl(angebot.seite_url))

    def aktualisieren(self, angebot: Angebot) -> None:
        if self._laeuft:
            return
        self._laeuft = True
        self._info_wunsch = self.hinweis.sagen(update.TEXT_LADEN, dauer_s=None)
        ordner = update_ordner()
        setup = ordner / update.SETUP_NAME
        try:
            setup.unlink(missing_ok=True)
        except OSError:
            pass

        summen = self._holen(angebot.summen_url, API_TIMEOUT_MS)

        def summen_da() -> None:
            summen.deleteLater()
            if summen.error() != QNetworkReply.NetworkError.NoError:
                self._fehler(f"Prüfsummen: {summen.errorString()}")
                return
            text = bytes(summen.readAll().data()).decode("utf-8", "replace")
            self._setup_laden(angebot, setup, text)
        summen.finished.connect(summen_da)

    def _setup_laden(self, angebot: Angebot, setup: Path, summen_text: str) -> None:
        try:
            datei = open(setup, "wb")  # noqa: SIM115 – bleibt offen bis „finished“
        except OSError as e:
            self._fehler(f"Datei: {e}")
            return
        antwort = self._holen(angebot.setup_url, DOWNLOAD_TIMEOUT_MS)
        antwort.readyRead.connect(lambda: datei.write(bytes(antwort.readAll().data())))

        def fertig() -> None:
            datei.write(bytes(antwort.readAll().data()))
            datei.close()
            antwort.deleteLater()
            if antwort.error() != QNetworkReply.NetworkError.NoError:
                setup.unlink(missing_ok=True)
                self._fehler(f"Setup: {antwort.errorString()}")
                return
            self._info_weg()
            ok = update.geladen_pruefen(setup, summen_text, self._installieren, self.hinweis.sagen)
            if not ok:
                self._laeuft = False
        antwort.finished.connect(fertig)

    def _installieren(self, setup: Path) -> bool:
        log.info("Update: starte %s", setup)
        self.vor_installation()
        ok, _pid = QProcess.startDetached(str(setup), SETUP_ARGUMENTE)
        if not ok:
            log.error("Update: Setup ließ sich nicht starten")
            self.nach_fehlstart()
            return False
        QTimer.singleShot(300, self.beenden)
        return True

    def _info_weg(self) -> None:
        if self._info_wunsch is not None:
            self.hinweis.motor.zurueckziehen(self._info_wunsch)
            self._info_wunsch = None

    def _fehler(self, grund: str) -> None:
        log.info("Update fehlgeschlagen: %s", grund)
        self._info_weg()
        self._laeuft = False
        self.hinweis.sagen(update.TEXT_FEHLER)
