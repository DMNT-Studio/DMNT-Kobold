"""Avatar-Töne. Eingebaut synthetisiert (kleine WAV-Dateien im Cache-Ordner),
dazu eigene Töne des Avatars (toene/*.wav).

Körper-Töne (``avatar.json → toene.<moment>`` mit ``dateien``) kommen automatisch zu
ihrem Moment: je Auslösung eine zufällige Datei, Tonhöhe streut um ±``tonhoehe``
(per Resampling, im Cache abgelegt), ``wiederholen`` [von, bis] Mal mit 90 ms Abstand.

Abspielen über winsound (Windows-Bordmittel, keine Zusatzpakete).
Die Lautstärke ist in die Dateien eingerechnet.
"""
from __future__ import annotations

import array
import hashlib
import logging
import math
import random
import struct
import sys
import wave
from dataclasses import dataclass
from pathlib import Path

from . import katalog

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


def wav_lesen(pfad: Path) -> tuple[array.array, int]:
    """16-bit-WAV → (Mono-Samples, Abtastrate)."""
    with wave.open(str(pfad), "rb") as w:
        if w.getsampwidth() != 2:
            raise wave.Error(f"{pfad.name}: nur 16-bit-WAV")
        kanaele, rate = w.getnchannels(), w.getframerate()
        roh = w.readframes(w.getnframes())
    werte = array.array("h")
    werte.frombytes(roh)
    if sys.byteorder == "big":
        werte.byteswap()
    if kanaele > 1:
        werte = array.array("h", (sum(werte[i:i + kanaele]) // kanaele for i in range(0, len(werte), kanaele)))
    return werte, rate


def resampeln(werte: array.array, faktor: float, lautstaerke: float = 1.0) -> array.array:
    """Tonhöhe ändern: Faktor > 1 = höher (und kürzer). Lineare Interpolation."""
    n = len(werte)
    if n == 0:
        return array.array("h")
    neu_n = max(1, int(n / faktor))
    aus = array.array("h", bytes(2 * neu_n))
    for i in range(neu_n):
        pos = i * faktor
        j = int(pos)
        a = werte[min(j, n - 1)]
        b = werte[min(j + 1, n - 1)]
        aus[i] = max(-32768, min(32767, int((a + (b - a) * (pos - j)) * lautstaerke)))
    return aus


def schreibe_wav(pfad: Path, pcm: bytes, rate: int = RATE) -> None:
    tmp = pfad.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    tmp.replace(pfad)


@dataclass
class KoerperTon:
    """Ton eines Moments aus Dateien (siehe Modul-Doku)."""
    dateien: list[Path]
    tonhoehe: float = 0.0
    wiederholen: tuple[int, int] = (1, 1)

    @classmethod
    def aus_json(cls, ordner: Path, d: dict) -> "KoerperTon":
        w = d.get("wiederholen") or [1, 1]
        return cls([ordner / x for x in d.get("dateien", []) if (ordner / x).is_file()],
                   float(d.get("tonhoehe", 0.0)), (int(w[0]), int(w[1])))


TONHOEHE_STUFE = 0.01      # gerundet, damit der Cache klein bleibt
WIEDERHOLUNG_PLAETZE = 4   # rotierende Dateien: ein laufender Ton wird nicht überschrieben


class Toene:
    """Spielt Avatar-Töne. ``avatar_toene`` = Name → WAV-Datei des Avatars;
    fehlende Namen fallen auf die eingebauten Klänge zurück."""

    def __init__(self, ordner: Path, lautstaerke: float = 0.35,
                 avatar_toene: dict[str, Path] | None = None,
                 koerper_toene: dict[str, KoerperTon] | None = None, rng: random.Random | None = None) -> None:
        self.ordner = ordner
        self.stumm = False
        self.avatar_toene = dict(avatar_toene or {})
        self.koerper_toene = {n: t for n, t in (koerper_toene or {}).items() if t.dateien}
        self.rng = rng or random.Random()
        self._dateien: dict[str, Path] = {}
        self._quellen: dict[Path, tuple[array.array, int, str]] = {}
        self._platz = 0
        self.lautstaerke_setzen(lautstaerke)

    def avatar_setzen(self, avatar_toene: dict[str, Path] | None,
                      koerper_toene: dict[str, KoerperTon] | None) -> None:
        """Anderer Avatar: seine Töne übernehmen, eingebaute Klänge bleiben Rückfall."""
        self.avatar_toene = dict(avatar_toene or {})
        self.koerper_toene = {n: t for n, t in (koerper_toene or {}).items() if t.dateien}
        self._dateien = {}
        self._quellen = {}
        self.lautstaerke_setzen(self.lautstaerke)

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

    # --- Körper-Töne ---------------------------------------------------------------
    def tonhoehe(self, name: str) -> float:
        """Zufälliger Tonhöhen-Faktor für einen Körper-Ton (1.0 ± tonhoehe, gestuft)."""
        t = self.koerper_toene.get(name)
        streuung = t.tonhoehe if t else 0.0
        faktor = 1.0 + self.rng.uniform(-streuung, streuung)
        return round(round(faktor / TONHOEHE_STUFE) * TONHOEHE_STUFE, 2)

    def _quelle(self, pfad: Path) -> tuple[array.array, int, str]:
        if pfad not in self._quellen:
            werte, rate = wav_lesen(pfad)
            self._quellen[pfad] = (werte, rate, hashlib.md5(pfad.read_bytes()).hexdigest()[:10])
        return self._quellen[pfad]

    def koerper_datei(self, name: str, hoeher: float = 0.0) -> Path | None:
        """Eine Auslösung eines Körper-Tons als WAV: zufällige Datei(en), gestreute
        Tonhöhe, Wiederholungen. Einzelne Fassungen liegen im Cache."""
        t = self.koerper_toene.get(name)
        if t is None:
            return None
        self.ordner.mkdir(parents=True, exist_ok=True)
        stufe = round(self.lautstaerke * 100)
        von, bis = t.wiederholen
        anzahl = self.rng.randint(max(1, von), max(1, von, bis))
        teile: list[array.array] = []
        rate = RATE
        for _ in range(anzahl):
            werte, rate, kennung = self._quelle(self.rng.choice(t.dateien))
            faktor = self.tonhoehe(name)
            if hoeher:                           # z. B. Nachhüpfer: je Stufe etwas höher
                faktor = round(round(faktor * (1 + hoeher) / TONHOEHE_STUFE) * TONHOEHE_STUFE, 2)
            pfad = self.ordner / f"koerper_{kennung}_{stufe}_{round(faktor * 100)}.wav"
            if not pfad.exists():
                schreibe_wav(pfad, resampeln(werte, faktor, self.lautstaerke).tobytes(), rate)
            if anzahl == 1:
                return pfad
            teile.append(wav_lesen(pfad)[0])
        stille = array.array("h", bytes(2 * int(rate * katalog.TON_ABSTAND_S)))
        gesamt = array.array("h")
        for i, teil in enumerate(teile):
            if i:
                gesamt += stille
            gesamt += teil
        self._platz = (self._platz + 1) % WIEDERHOLUNG_PLAETZE
        pfad = self.ordner / f"koerper_folge_{self._platz}.wav"
        schreibe_wav(pfad, gesamt.tobytes(), rate)
        return pfad

    def moment(self, name: str) -> None:
        """Moment des Körpers: spielt nur, wenn der Avatar dafür einen Körper-Ton hat."""
        if name in self.koerper_toene:
            self.spielen(name)

    def spielen(self, name: str, hoeher: float = 0.0) -> None:
        if self.stumm or self.lautstaerke <= 0 or sys.platform != "win32":
            return
        pfad = None
        if name in self.koerper_toene:
            try:
                pfad = self.koerper_datei(name, hoeher)
            except (OSError, wave.Error, EOFError, struct.error):
                log.exception("Körper-Ton %s konnte nicht erzeugt werden", name)
        pfad = pfad or self._dateien.get(name)
        if pfad is None:
            return
        import winsound

        try:
            winsound.PlaySound(str(pfad), winsound.SND_FILENAME | winsound.SND_ASYNC
                               | winsound.SND_NODEFAULT)
        except RuntimeError:
            log.warning("Ton %s konnte nicht abgespielt werden", name)
