"""Kiesels Töne synthetisieren → quellen/kiesel/toene/*.ogg (eigene Klänge, MIT).

Aufruf:  python werkzeuge/toene_kiesel.py [--hoerprobe]

Pfütze statt Gummiball, Stimme wie ein Glöckchen unter Wasser:

- plitsch_1..2   Absprung: kurzes Schmatzen beim Herausziehen aus der Pfütze (gedämpftes
                 Rauschen, weich rein) und ein kleiner aufsteigender Tropfen
- platsch_1..3   Landen: Pfützen-Platscher – heller Rauschstoß, der schnell dumpfer wird,
                 darunter ein tiefer „Plumps“, danach 3–5 nachfallende Tröpfchen
                 (Wassertropfen steigen in der Tonhöhe). Drei Fassungen, der Sockel wählt zufällig.
- glocke_1..3    Sprechen: Glöckchen mit unharmonischen Obertönen, weich angeschlagen,
                 dumpf gefiltert und leicht wabernd (wie unter Wasser), dazu ein winziges
                 Bläschen. Drei Tonhöhen, der Sockel spielt 1–3 hintereinander.
- kling          Erschrecken: helles Kling (Kiesel stößt an die Wand), unverändert

--hoerprobe schreibt zusätzlich build/kiesel_hoerprobe.wav (alles hintereinander).
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


def _tropfen(f0: float, dauer_s: float = 0.035) -> np.ndarray:
    """Wassertropfen: kurze Resonanz, deren Tonhöhe steigt (Luftblase schrumpft)."""
    s = _gleiten(f0, f0 * 1.9, dauer_s)
    return s * _huelle(len(s), 0.0015, 6.0)


def _mischen(ziel: np.ndarray, teil: np.ndarray, start_s: float, pegel: float) -> None:
    i = int(start_s * RATE)
    j = min(len(ziel), i + len(teil))
    if i < j:
        ziel[i:j] += pegel * teil[: j - i]


def _tiefpass_gleitend(s: np.ndarray, f0: float, f1: float, stuecke: int = 24) -> np.ndarray:
    """Rauschen, das über die Dauer dumpfer wird (Grenzfrequenz f0 → f1, stückweise)."""
    aus = np.zeros_like(s)
    zi = None
    for k, teil in enumerate(np.array_split(np.arange(len(s)), stuecke)):
        fc = f0 * (f1 / f0) ** (k / max(1, stuecke - 1))
        b, a = signal.butter(2, fc, btype="lowpass", fs=RATE)
        if zi is None:
            zi = signal.lfilter_zi(b, a) * 0
        aus[teil], zi = signal.lfilter(b, a, s[teil], zi=zi)
    return aus


def _normal(s: np.ndarray, spitze: float) -> np.ndarray:
    m = np.abs(s).max()
    return s / m * spitze if m else s


def platsch(rng: np.random.Generator) -> np.ndarray:
    """Pfützen-Platscher, ca. 260 ms."""
    n = int(RATE * 0.26)
    s = np.zeros(n)
    stoss_n = int(RATE * 0.11)                         # Aufschlag: hell, wird in 90 ms dumpf
    stoss = _tiefpass_gleitend(rng.uniform(-1, 1, stoss_n), 5200, 650)
    stoss = _normal(stoss, 1.0) * _huelle(stoss_n, 0.0015, 5.5)
    _mischen(s, stoss, 0.0, 0.75)
    plumps = _gleiten(rng.uniform(210, 260), 95, 0.07)  # Wasser wird verdrängt
    _mischen(s, plumps * _huelle(len(plumps), 0.002, 4.5), 0.0, 0.45)
    for _ in range(rng.integers(3, 6)):                 # nachfallende Tröpfchen
        _mischen(s, _tropfen(rng.uniform(700, 1500), rng.uniform(0.025, 0.045)),
                 rng.uniform(0.045, 0.2), rng.uniform(0.12, 0.3))
    return _normal(s, 0.62)


def plitsch(rng: np.random.Generator) -> np.ndarray:
    """Absprung: Schmatzen beim Herausziehen + ein kleiner Tropfen, ca. 120 ms."""
    n = int(RATE * 0.12)
    s = np.zeros(n)
    schmatz_n = int(RATE * 0.06)
    b, a = signal.butter(2, [350, 1400], btype="bandpass", fs=RATE)
    schmatz = signal.lfilter(b, a, rng.uniform(-1, 1, schmatz_n))
    an = np.minimum(1.0, np.arange(schmatz_n) / (RATE * 0.012))       # weich rein (Saugen)
    schmatz = _normal(schmatz, 1.0) * an * np.exp(-3.5 * np.arange(schmatz_n) / schmatz_n)
    _mischen(s, schmatz, 0.0, 0.35)
    _mischen(s, _tropfen(rng.uniform(900, 1250), 0.04), 0.035, 0.3)
    return _normal(s, 0.38)


def glocke(grund: float, rng: np.random.Generator) -> np.ndarray:
    """Glöckchen unter Wasser, ca. 190 ms."""
    t = _zeit(0.19)
    wabern = 1 + 0.012 * np.sin(2 * np.pi * 7.5 * t + rng.uniform(0, 6.3))   # Tonhöhe wabert leicht
    s = np.zeros_like(t)
    for faktor, pegel, abkling in ((1.0, 1.0, 0.07), (2.76, 0.35, 0.035), (5.4, 0.12, 0.018)):
        phase = 2 * np.pi * np.cumsum(grund * faktor * wabern) / RATE
        s += pegel * np.sin(phase) * np.exp(-t / abkling)
    s *= np.minimum(1.0, t / 0.006)                                      # weicher Anschlag
    s *= 1 - 0.18 * (0.5 + 0.5 * np.sin(2 * np.pi * 11 * t))            # Wasser bewegt den Klang
    b, a = signal.butter(2, 2600, btype="lowpass", fs=RATE)             # dumpf wie unter Wasser
    s = signal.lfilter(b, a, s)
    _mischen(s, _tropfen(grund * 0.55, 0.03), 0.012, 0.18)              # winziges Bläschen
    return _normal(s, 0.3)                       # etwas leiser als das Platschen (klingt dichter)


def kling() -> np.ndarray:
    t = _zeit(0.16)
    s = sum(g * np.sin(2 * np.pi * 2100 * k * t) for k, g in ((1, 1.0), (2.76, 0.42), (5.4, 0.18)))
    huelle = np.minimum(1.0, t / 0.002) * np.exp(-t / 0.035)    # ≈ 120 ms hörbarer Ausklang
    return 0.32 * s / 1.6 * huelle


def alle_toene(seed: int = 7) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    toene = {f"plitsch_{i}": plitsch(rng) for i in (1, 2)}
    toene |= {f"platsch_{i}": platsch(rng) for i in (1, 2, 3)}
    for i, grund in enumerate((1568.0, 1760.0, 2093.0), 1):            # G6, A6, C7
        toene[f"glocke_{i}"] = glocke(grund, rng)
    toene["kling"] = kling()
    return toene


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
    ZIEL.mkdir(parents=True, exist_ok=True)
    toene = alle_toene()
    with tempfile.TemporaryDirectory() as tmp:
        for name, s in toene.items():
            wav = Path(tmp) / f"{name}.wav"
            wav_schreiben(wav, s)
            als_ogg(wav, ZIEL / f"{name}.ogg")
            print(f"  {name}.ogg ({len(s) / RATE * 1000:.0f} ms)")
    if "--hoerprobe" in sys.argv:
        stille = np.zeros(int(RATE * 0.35))
        folge = []
        for name in ("plitsch_1", "platsch_1", "plitsch_2", "platsch_2", "platsch_3",
                     "glocke_1", "glocke_2", "glocke_3", "glocke_2", "glocke_1"):
            folge += [toene[name], stille]
        pfad = WURZEL / "build" / "kiesel_hoerprobe.wav"
        pfad.parent.mkdir(exist_ok=True)
        wav_schreiben(pfad, np.concatenate(folge))
        print(f"  Hörprobe: {pfad}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
