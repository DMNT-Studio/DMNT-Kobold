"""Avatar-Töne. In M2 synthetisiert (kleine WAV-Dateien im Cache-Ordner);
ab M3 liefert der Avatar-Ordner eigene Töne (toene/<animation>.ogg).

Abspielen über winsound (Windows-Bordmittel, keine Zusatzpakete).
Die Lautstärke ist in die Dateien eingerechnet.
"""
from __future__ import annotations

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


def synthese(segmente: list[tuple[float, float, float]], lautstaerke: float) -> bytes:
    daten = bytearray()
    phase = 0.0
    for f0, f1, dauer in segmente:
        n = int(RATE * dauer)
        for i in range(n):
            anteil = i / n
            f = f0 + (f1 - f0) * anteil
            phase += 2 * math.pi * f / RATE
            huelle = min(1.0, i / (RATE * 0.004)) * math.exp(-3.2 * anteil)
            wert = (math.sin(phase) + 0.25 * math.sin(2 * phase)) / 1.25
            daten += struct.pack("<h", int(wert * huelle * lautstaerke * 32767))
        daten += b"\x00\x00" * int(RATE * 0.012)
    return bytes(daten)


def schreibe_wav(pfad: Path, pcm: bytes) -> None:
    tmp = pfad.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm)
    tmp.replace(pfad)


class Toene:
    def __init__(self, ordner: Path, lautstaerke: float = 0.35) -> None:
        self.ordner = ordner
        self.stumm = False
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
        except OSError:
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
