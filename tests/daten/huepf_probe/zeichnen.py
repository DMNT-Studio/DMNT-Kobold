"""Prüf-Figur für den Hüpf-Sockel – nur für Tests, wird nicht ausgeliefert.

Kreis in Hellgrau (70 % Deckkraft) mit zwei Punktaugen, innen ein kleines Quadrat in
zwei Farben (Innenleben ``probe`` und ``probe@froh``), synthetisierte Töne.
Erzeugt die Quellbilder und Töne neben dieser Datei:

    python tests/daten/huepf_probe/zeichnen.py
    python werkzeuge/avatar_bauen.py tests/daten/huepf_probe --ziel build/huepf_probe
    python -m dmnt_kobold --avatar-pfad build/huepf_probe
"""
from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

HIER = Path(__file__).resolve().parent
sys.path.insert(0, str(HIER.parents[2] / "src"))
from dmnt_kobold.toene import schreibe_wav, synthese  # noqa: E402

GROESSE = 192
KOERPER = (216, 220, 222, 178)          # Hellgrau, 70 % Deckkraft
AUGE = (40, 46, 52, 255)


def figur(augen: str = "punkt", mund: str = "") -> Image.Image:
    im = Image.new("RGBA", (GROESSE, GROESSE), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = 58
    cx, cy = GROESSE // 2, GROESSE - r - 2
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=KOERPER, outline=(170, 176, 180, 220), width=3)
    for ax in (cx - 20, cx + 20):
        ay = cy - 14
        if augen == "punkt":
            d.ellipse([ax - 6, ay - 6, ax + 6, ay + 6], fill=AUGE)
        elif augen == "gross":
            d.ellipse([ax - 10, ay - 10, ax + 10, ay + 10], fill=(255, 255, 255, 255), outline=AUGE, width=3)
            d.ellipse([ax - 4, ay - 4, ax + 4, ay + 4], fill=AUGE)
        elif augen == "froh":
            d.arc([ax - 8, ay - 6, ax + 8, ay + 8], 200, 340, fill=AUGE, width=4)
        elif augen == "zu":
            d.line([ax - 8, ay + 2, ax + 8, ay + 2], fill=AUGE, width=4)
    if mund == "offen":
        d.ellipse([cx - 8, cy + 4, cx + 8, cy + 18], fill=AUGE)
    return im


def quadrat(farbe: tuple[int, int, int]) -> Image.Image:
    im = Image.new("RGBA", (48, 48), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    dunkel = tuple(int(c * 0.6) for c in farbe)
    d.rectangle([2, 2, 45, 45], fill=farbe + (255,), outline=dunkel + (255,), width=4)
    d.rectangle([14, 18, 33, 29], fill=dunkel + (255,))
    return im


def main() -> None:
    posen = {"ruhe": figur(), "freuen": figur("froh"), "erschrecken": figur("gross", "offen"),
             "schlafen": figur("zu"), "sprechen": figur(mund="offen")}
    for name, bild in posen.items():
        bild.save(HIER / f"{name}.png")
    (HIER / "zubehoer").mkdir(exist_ok=True)
    quadrat((224, 90, 60)).save(HIER / "zubehoer" / "probe.png")
    quadrat((242, 194, 48)).save(HIER / "zubehoer" / "probe@froh.png")
    (HIER / "toene").mkdir(exist_ok=True)
    schreibe_wav(HIER / "toene" / "landen_1.wav", synthese([(240, 90, 0.09)], 0.9))
    schreibe_wav(HIER / "toene" / "landen_2.wav", synthese([(300, 110, 0.08)], 0.9))
    schreibe_wav(HIER / "toene" / "pieps.wav", synthese([(1500, 1600, 0.05)], 0.8, welle="rechteck"))
    print(f"Prüf-Figur gezeichnet: {HIER}")


if __name__ == "__main__":
    main()
