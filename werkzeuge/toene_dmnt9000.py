"""DMNT 9000: Töne synthetisieren → quellen/dmnt9000/toene/*.ogg (eigene Klänge, MIT).

Aufruf:  python werkzeuge/toene_dmnt9000.py [--hoerprobe]

Bord-KI im Laderaum eines Mining-Schiffs: Rechteck-Piepser, Ringmodulation, etwas
Bit-Körnung, dazu Hall wie in einer Stahlhalle (frühe Reflexionen, Nachhall ca. 1,1–1,5 s,
Höhen klingen schneller ab).

- sprechen_1..4   Datenzwitschern: 3–5 kurze Piepser aus einer festen Skala (Sprechblase)
- landen_1..2     Aufsetzen: metallisches Klonk und kurzes Servo-Nachregeln
- freude          Daumen hoch: steigendes Arpeggio mit Triller (Aktion „ton“: freude)
- alarm           Wackeln/Erschrecken: zwei Sirenen-Bögen und ein Störgeräusch (Aktion „ton“: alarm)
- aufwachen       Hochfahren: Brummen steigt, Sweep, Zwei-Ton-Gong
- huepfen         Hüpfer (Klick ohne Regel, Sprung): kurzes Servo-Surren nach oben

--hoerprobe schreibt zusätzlich build/dmnt9000_hoerprobe.wav (alles hintereinander).
Gerechnet als WAV, mit ffmpeg (libvorbis) zu OGG. Beim Bau macht avatar_bauen.py daraus
wieder WAV für den Sockel. Benötigt: numpy, scipy, ffmpeg (nur zum Erzeugen).
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
ZIEL = WURZEL / "quellen" / "dmnt9000" / "toene"
RATE = 44100
SKALA = (523.3, 587.3, 659.3, 784.0, 880.0, 1046.5, 1174.7)   # C5 D5 E5 G5 A5 C6 D6


# --- Bausteine ---------------------------------------------------------------------------

def _zeit(dauer_s: float) -> np.ndarray:
    return np.arange(int(RATE * dauer_s)) / RATE


def _gleiten(f0: float, f1: float, dauer_s: float) -> np.ndarray:
    """Frequenzverlauf f0 → f1 (exponentiell) als Array."""
    t = _zeit(dauer_s)
    return f0 * (f1 / f0) ** (t / dauer_s)


def _phase(f: np.ndarray) -> np.ndarray:
    return 2 * np.pi * np.cumsum(f) / RATE


def _puls(f: np.ndarray, breite: float = 0.5, haerte: float = 6.0) -> np.ndarray:
    """Weiches Rechteck/Puls (breite 0.5 = Rechteck, kleiner = schmaler Puls, nasaler)."""
    s = np.tanh(haerte * (np.sin(_phase(f)) - np.cos(np.pi * breite)))
    return s - s.mean()


def _huelle(n: int, an_s: float = 0.003, ab_s: float = 0.015) -> np.ndarray:
    i = np.arange(n) / RATE
    return np.clip(np.minimum(i / an_s, (n / RATE - i) / ab_s), 0, 1)


def _ring(s: np.ndarray, f: float, anteil: float) -> np.ndarray:
    """Ringmodulation (metallisch, „Roboterstimme“), anteilig beigemischt."""
    traeger = np.sin(2 * np.pi * f * np.arange(len(s)) / RATE)
    return s * (1 - anteil) + 1.4 * anteil * s * traeger


def _koernen(s: np.ndarray, anteil: float, bits: int = 6, rate: int = 11025) -> np.ndarray:
    """Bit-Körnung: grobe Abtastung + wenige Bits, tiefpassgefiltert beigemischt."""
    spitze = np.abs(s).max() or 1.0
    schritt = RATE // rate
    grob = np.repeat(s[::schritt] / spitze, schritt)[: len(s)]
    stufen = 2 ** (bits - 1)
    grob = np.round(grob * stufen) / stufen * spitze
    b, a = signal.butter(2, 8000, btype="lowpass", fs=RATE)
    return s * (1 - anteil) + signal.lfilter(b, a, grob) * anteil


def _mischen(ziel: np.ndarray, teil: np.ndarray, start_s: float, pegel: float) -> None:
    i = int(start_s * RATE)
    j = min(len(ziel), i + len(teil))
    if i < j:
        ziel[i:j] += pegel * teil[: j - i]


def _normal(s: np.ndarray, spitze: float) -> np.ndarray:
    m = np.abs(s).max()
    return s / m * spitze if m else s


def _hall(s: np.ndarray, rng: np.random.Generator, nachhall_s: float = 1.3,
          anteil: float = 0.4, vorverz_s: float = 0.018) -> np.ndarray:
    """Stahlhalle: frühe Reflexionen + Rauschfahne (RT60 = nachhall_s), Höhen klingen
    schneller ab. Ergebnis inkl. Fahne, Spitze 0.6."""
    n = int(RATE * nachhall_s)
    t = np.arange(n) / RATE
    rauschen = rng.standard_normal(n) * np.exp(-6.9 * t / nachhall_s)
    b, a = signal.butter(2, 2200, btype="lowpass", fs=RATE)
    dumpf = signal.lfilter(b, a, rauschen) * 2.2
    hell = np.exp(-t / 0.22)                      # anfangs hell, dann dumpf
    ir = rauschen * hell + dumpf * (1 - hell)
    ir[: int(vorverz_s * RATE)] = 0
    for ms, g in ((7, 9.0), (13, -7.0), (19, 6.0), (29, -4.5), (41, 3.5), (57, -2.5)):
        ir[int((vorverz_s + ms / 1000) * RATE)] += g          # Stahlwände: frühe Reflexionen
    b, a = signal.butter(1, 160, btype="highpass", fs=RATE)
    nass = signal.lfilter(b, a, signal.fftconvolve(s, ir))
    trocken = np.concatenate([s, np.zeros(len(nass) - len(s))])
    nass = _normal(nass, np.abs(s).max())
    aus = trocken + anteil * nass
    leise = np.nonzero(np.abs(aus) > 0.002 * np.abs(aus).max())[0]   # Fahne kürzen, sanft enden
    aus = aus[: leise[-1] + 1]
    aus[-int(RATE * 0.04):] *= np.linspace(1, 0, int(RATE * 0.04))
    return _normal(aus, 0.6)


# --- Klänge ------------------------------------------------------------------------------

def sprechen(rng: np.random.Generator) -> np.ndarray:
    teile = []
    for _ in range(rng.integers(3, 6)):
        f = float(rng.choice(SKALA))
        dauer = rng.uniform(0.04, 0.075)
        f_ende = f * float(rng.choice((1.0, 1.0, 1.12, 0.89)))   # manche Piepser biegen ab
        s = _puls(_gleiten(f, f_ende, dauer), breite=float(rng.choice((0.5, 0.3))))
        teile += [s * _huelle(len(s), 0.003, 0.012), np.zeros(int(RATE * rng.uniform(0.012, 0.03)))]
    s = _ring(np.concatenate(teile), 95, 0.35)
    return _hall(_koernen(s, 0.3), rng, 1.1, 0.38)


def freude(rng: np.random.Generator) -> np.ndarray:
    teile = []
    for f in (523.3, 659.3, 784.0, 1046.5):                  # C-Dur aufwärts
        s = _puls(np.full(int(RATE * 0.06), f), 0.4)
        teile += [s * _huelle(len(s), 0.002, 0.015), np.zeros(int(RATE * 0.015))]
    t = _zeit(0.22)
    f = np.where((t * 26) % 1 < 0.5, 1046.5, 1318.5)        # Triller C6/E6
    teile.append(_puls(f, 0.5) * _huelle(len(t), 0.002, 0.06) * np.exp(-t / 0.18))
    s = _ring(np.concatenate(teile), 120, 0.25)
    return _hall(_koernen(s, 0.25), rng, 1.3, 0.42)


def alarm(rng: np.random.Generator) -> np.ndarray:
    teile = []
    for _ in range(2):
        f = np.concatenate([_gleiten(1250, 520, 0.09), _gleiten(520, 900, 0.06)])
        s = _puls(f, 0.5, 8.0)
        teile += [s * _huelle(len(s), 0.002, 0.01), np.zeros(int(RATE * 0.02))]
    s = _ring(np.concatenate(teile), 73, 0.5)
    stoerung = rng.uniform(-1, 1, int(RATE * 0.05))
    b, a = signal.butter(2, [2000, 5000], btype="bandpass", fs=RATE)
    stoerung = signal.lfilter(b, a, stoerung) * np.exp(-np.arange(len(stoerung)) / RATE / 0.015)
    _mischen(s, _normal(stoerung, 1.0), 0.0, 0.5)
    return _hall(_koernen(s, 0.4, bits=5), rng, 1.2, 0.4)


def aufwachen(rng: np.random.Generator) -> np.ndarray:
    d = 0.45
    t = _zeit(d)
    brumm = _puls(_gleiten(70, 180, d), 0.5, 3.0) * 0.5
    sweep = _ring(np.sin(_phase(_gleiten(220, 1400, d))), 60, 0.5) * 0.6
    hoch = (brumm + sweep) * np.minimum(1, t / 0.25) * _huelle(len(t), 0.01, 0.03)
    tg = _zeit(0.5)

    def gong(f: float) -> np.ndarray:
        s = sum(p * np.sin(2 * np.pi * f * k * tg) * np.exp(-tg / ab)
                for k, p, ab in ((1, 1.0, 0.2), (2.01, 0.4, 0.12), (3.0, 0.2, 0.07)))
        return s * np.minimum(1, tg / 0.003)

    aus = np.zeros(int(RATE * 1.05))
    _mischen(aus, hoch, 0.0, 1.0)
    _mischen(aus, gong(784.0), 0.47, 0.55)
    _mischen(aus, gong(1174.7), 0.62, 0.55)
    return _hall(_koernen(aus, 0.2), rng, 1.5, 0.45)


def huepfen(rng: np.random.Generator) -> np.ndarray:
    s = signal.sawtooth(_phase(_gleiten(280, 950, 0.11)))
    b, a = signal.butter(2, 3000, btype="lowpass", fs=RATE)
    s = _ring(signal.lfilter(b, a, s), 150, 0.3)
    return _hall(s * _huelle(len(s), 0.004, 0.03), rng, 0.9, 0.3)


def landen(rng: np.random.Generator) -> np.ndarray:
    aus = np.zeros(int(RATE * 0.35))
    t = _zeit(0.25)
    grund = rng.uniform(190, 230)
    klonk = sum(p * np.sin(2 * np.pi * grund * k * t + rng.uniform(0, 6.3)) * np.exp(-t / ab)
                for k, p, ab in ((1, 1.0, 0.09), (2.63, 0.6, 0.05), (4.71, 0.35, 0.03), (7.1, 0.2, 0.018)))
    _mischen(aus, klonk * np.minimum(1, t / 0.001), 0.0, 0.7)
    stoss = rng.uniform(-1, 1, int(RATE * 0.03))
    b, a = signal.butter(2, 1800, btype="lowpass", fs=RATE)
    stoss = signal.lfilter(b, a, stoss) * np.exp(-np.arange(len(stoss)) / RATE / 0.008)
    _mischen(aus, _normal(stoss, 1.0), 0.0, 0.5)
    servo = _puls(_gleiten(520, 380, 0.07), 0.5, 3.0)
    _mischen(aus, servo * _huelle(len(servo), 0.005, 0.03), rng.uniform(0.11, 0.15), 0.18)
    return _hall(_koernen(aus, 0.2), rng, 1.3, 0.4)


def alle_toene(seed: int = 9000) -> dict[str, np.ndarray]:
    rng = np.random.default_rng(seed)
    toene = {f"sprechen_{i}": sprechen(rng) for i in (1, 2, 3, 4)}
    toene |= {f"landen_{i}": landen(rng) for i in (1, 2)}
    toene |= {"freude": freude(rng), "alarm": alarm(rng), "aufwachen": aufwachen(rng),
              "huepfen": huepfen(rng)}
    return toene


# --- Ausgabe -----------------------------------------------------------------------------

def wav_schreiben(pfad: Path, s: np.ndarray) -> None:
    daten = (np.clip(s, -1, 1) * 32767).astype("<i2")
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
        stille = np.zeros(int(RATE * 0.3))
        folge = []
        for name in ("aufwachen", "sprechen_1", "sprechen_2", "sprechen_3", "sprechen_4",
                     "freude", "alarm", "huepfen", "landen_1", "landen_2"):
            folge += [toene[name], stille]
        pfad = WURZEL / "build" / "dmnt9000_hoerprobe.wav"
        pfad.parent.mkdir(exist_ok=True)
        wav_schreiben(pfad, np.concatenate(folge))
        print(f"  Hörprobe: {pfad}")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
