"""Kiesels Töne synthetisieren → quellen/kiesel/toene/*.ogg (eigene Klänge, MIT).

Aufruf:  python werkzeuge/toene_kiesel.py

- plopp    Hüpfen: Sinus 520 → 260 Hz, 90 ms, leise
- platsch  Landen: Rauschen durch einen Bandpass um 1,2 kHz, Hüllkurve 60 ms (feucht, kurz)
- blubb    Sprechen: Sinus 700 → 900 Hz, 70 ms (der Sockel spielt 1–3 mit Tonhöhen-Streuung)
- kling    Erschrecken: Sinus 2,1 kHz mit Obertönen, 120 ms Ausklang (Kiesel stößt an die Wand)

Die Töne werden als WAV gerechnet und mit ffmpeg (libvorbis) zu OGG. Beim Bau macht
avatar_bauen.py daraus wieder WAV für den Sockel.
Benötigt: numpy, scipy, ffmpeg (nur zum Erzeugen).
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np
from scipy import signal

WURZEL = Path(__file__).resolve().parents[1]
ZIEL = WURZEL / "quellen" / "kiesel" / "toene"
RATE = 44100


def _zeit(dauer_s: float) -> np.ndarray:
    return np.arange(int(RATE * dauer_s)) / RATE


def _gleiten(f0: float, f1: float, dauer_s: float) -> np.ndarray:
    """Sinus mit Frequenzverlauf f0 → f1 (exponentiell), phasenrichtig."""
    t = _zeit(dauer_s)
    f = f0 * (f1 / f0) ** (t / dauer_s)
    return np.sin(2 * np.pi * np.cumsum(f) / RATE)


def _huelle(n: int, an_s: float = 0.004, form: float = 4.0) -> np.ndarray:
    an = np.minimum(1.0, np.arange(n) / (RATE * an_s))
    return an * np.exp(-form * np.arange(n) / n)


def plopp() -> np.ndarray:
    s = _gleiten(520, 260, 0.09)
    return 0.45 * s * _huelle(len(s), 0.003, 3.5)


def platsch(rng: np.random.Generator) -> np.ndarray:
    n = int(RATE * 0.06)
    rauschen = rng.uniform(-1, 1, n)
    b, a = signal.butter(2, [800, 1700], btype="bandpass", fs=RATE)
    s = signal.lfilter(b, a, rauschen)
    s /= np.abs(s).max() or 1
    tropf = _gleiten(900, 500, 0.06) * 0.25                 # etwas „Wasser“ darunter
    return 0.6 * (s + tropf) * _huelle(n, 0.002, 5.0)


def blubb() -> np.ndarray:
    s = _gleiten(700, 900, 0.07)
    s = s + 0.18 * _gleiten(1400, 1800, 0.07)
    return 0.4 * s * _huelle(len(s), 0.006, 2.6)


def kling() -> np.ndarray:
    t = _zeit(0.16)
    s = sum(g * np.sin(2 * np.pi * 2100 * k * t) for k, g in ((1, 1.0), (2.76, 0.42), (5.4, 0.18)))
    huelle = np.minimum(1.0, t / 0.002) * np.exp(-t / 0.035)    # ≈ 120 ms hörbarer Ausklang
    return 0.32 * s / 1.6 * huelle


def wav_schreiben(pfad: Path, s: np.ndarray) -> None:
    pause = np.zeros(int(RATE * 0.01))
    daten = (np.clip(np.concatenate([s, pause]), -1, 1) * 32767).astype("<i2")
    with wave.open(str(pfad), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(daten.tobytes())


def als_ogg(wav: Path, ogg: Path) -> None:
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise SystemExit("ffmpeg fehlt – zum Erzeugen der OGG-Dateien wird ffmpeg gebraucht")
    erg = subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", str(wav), "-c:a", "libvorbis",
                          "-q:a", "5", str(ogg)], capture_output=True, text=True)
    if erg.returncode != 0:
        raise SystemExit(f"ffmpeg: {erg.stderr.strip()[:300]}")


def main() -> None:
    rng = np.random.default_rng(5)
    ZIEL.mkdir(parents=True, exist_ok=True)
    toene = {"plopp": plopp(), "platsch": platsch(rng), "blubb": blubb(), "kling": kling()}
    with tempfile.TemporaryDirectory() as tmp:
        for name, s in toene.items():
            wav = Path(tmp) / f"{name}.wav"
            wav_schreiben(wav, s)
            als_ogg(wav, ZIEL / f"{name}.ogg")
            print(f"  {name}.ogg ({len(s) / RATE * 1000:.0f} ms)")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
