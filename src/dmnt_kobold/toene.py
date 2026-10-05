"""Avatar-Töne. In M2 synthetisiert (kleine WAV-Dateien im Cache-Ordner);
ab M3 liefert der Avatar-Ordner eigene Töne (toene/<animation>.ogg).

Abspielen über winsound (Windows-Bordmittel, keine Zusatzpakete).
Die Lautstärke ist in die Dateien eingerechnet.
"""
from __future__ import annotations

import hashlib
import logging
import math
import struct
import sys
import wave
from pathlib import Path

log = logging.getLogger(__name__)

RATE = 22050

# Name → Liste von (Startfrequenz, Endfrequenz, Dauer s)
KLAENGE: dict[str, list[tuple[float, float, float]]] = {
    "landen": [(520, 240, 0.07)],
    "sprechen": [(880, 900, 0.045), (1320, 1300, 0.055)],
    "erschrecken": [(360, 780, 0.14)],
    "freuen": [(660, 660, 0.06), (880, 880, 0.06), (1175, 1190, 0.10)],
    "aufwachen": [(500, 700, 0.08), (700, 620, 0.08)],
    "huepfen": [(420, 720, 0.06)],
}


def _welle(phase: float, welle: str) -> float:
    if welle == "rechteck":   # weich gerundetes Rechteck (Computer-Piepsen)
        return math.tanh(4 * math.sin(phase)) * 0.75
    if welle == "dreieck":
        return 2 / math.pi * math.asin(math.sin(phase))
    return (math.sin(phase) + 0.25 * math.sin(2 * phase)) / 1.25


def synthese(segmente: list[tuple[float, float, float]], lautstaerke: float,
             welle: str = "sinus") -> bytes:
    """Segmente = (Startfrequenz, Endfrequenz, Dauer s). Frequenz 0 = Pause."""
    daten = bytearray()
    phase = 0.0
    for f0, f1, dauer in segmente:
        n = int(RATE * dauer)
        for i in range(n):
            anteil = i / n
            f = f0 + (f1 - f0) * anteil
            if f <= 0:
                daten += b"\x00\x00"
                continue
            phase += 2 * math.pi * f / RATE
            huelle = min(1.0, i / (RATE * 0.004)) * math.exp(-3.2 * anteil)
            wert = _welle(phase, welle)
            daten += struct.pack("<h", int(wert * huelle * lautstaerke * 32767))
        daten += b"\x00\x00" * int(RATE * 0.012)
    return bytes(daten)


def lautstaerke_anpassen(quelle: Path, ziel: Path, lautstaerke: float) -> None:
    """Kopie einer 16-bit-WAV mit eingerechneter Lautstärke."""
    with wave.open(str(quelle), "rb") as w:
        param = w.getparams()
        roh = w.readframes(w.getnframes())
    werte = struct.unpack(f"<{len(roh) // 2}h", roh)
    neu = struct.pack(f"<{len(werte)}h", *(max(-32768, min(32767, int(v * lautstaerke))) for v in werte))
    tmp = ziel.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setparams(param)
        w.writeframes(neu)
    tmp.replace(ziel)


def schreibe_wav(pfad: Path, pcm: bytes) -> None:
    tmp = pfad.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    tmp.replace(pfad)


class Toene:
    """Spielt Avatar-Töne. ``avatar_toene`` = Name → WAV-Datei des Avatars;
    fehlende Namen fallen auf die eingebauten Klänge zurück."""

    def __init__(self, ordner: Path, lautstaerke: float = 0.35,
                 avatar_toene: dict[str, Path] | None = None) -> None:
        self.ordner = ordner
        self.stumm = False
        self.avatar_toene = dict(avatar_toene or {})
        self._dateien: dict[str, Path] = {}
        self.lautstaerke_setzen(lautstaerke)

    def lautstaerke_setzen(self, lautstaerke: float) -> None:
        self.lautstaerke = max(0.0, min(1.0, lautstaerke))
        stufe = round(self.lautstaerke * 100)
        try:
            self.ordner.mkdir(parents=True, exist_ok=True)
            for name, segmente in KLAENGE.items():
                pfad = self.ordner / f"{name}_{stufe}.wav"
                if not pfad.exists():
                    schreibe_wav(pfad, synthese(segmente, self.lautstaerke))
                self._dateien[name] = pfad
            for name, quelle in self.avatar_toene.items():
                kennung = hashlib.md5(quelle.read_bytes()).hexdigest()[:10]
                pfad = self.ordner / f"avatar_{kennung}_{stufe}.wav"
                if not pfad.exists():
                    lautstaerke_anpassen(quelle, pfad, self.lautstaerke)
                self._dateien[name] = pfad
        except (OSError, wave.Error, struct.error):
            log.exception("Töne konnten nicht erzeugt werden")

    def spielen(self, name: str) -> None:
        if self.stumm or self.lautstaerke <= 0 or sys.platform != "win32":
            return
        pfad = self._dateien.get(name)
        if pfad is None:
            return
        import winsound

        try:
            winsound.PlaySound(str(pfad), winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_NODEFAULT)
        except RuntimeError:
            log.warning("Ton %s konnte nicht abgespielt werden", name)
