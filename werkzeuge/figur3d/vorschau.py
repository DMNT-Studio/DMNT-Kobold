"""Animierte Vorschau aller Bewegungen (GIF) aus fertig/<anim>/NN.png."""
import sys
from PIL import Image, ImageDraw, ImageFont
LISTE = [("stehen", "Stehen"), ("gehen", "Gehen"), ("rennen", "Rennen"), ("tragen", "Box schleppen"),
         ("minen_start", "Mining: zielen"), ("minen", "Mining: Strahl"), ("minen_ende", "Mining: Stein platzt"),
         ("freuen", "Daumen hoch"), ("unzufrieden", "Daumen runter"), ("anschauen", "Winken"),
         ("sprechen", "Reden"), ("sprechen_vorne", "Reden (vorn)"), ("erschrecken", "Erschrecken"),
         ("zuschauen", "Zuschauen"), ("musik", "Musik"), ("sitzen", "Sitzen"), ("schlafen", "Schlafen"),
         ("fallen", "Fallen"), ("gezogen", "Am Mauszeiger"), ("springen", "Springen"), ("schweben", "Schweben")]
SK = 0.3
SPALTEN = 6
hg = (40, 44, 56)
zellen = []
for a, titel in LISTE:
    bilder = [Image.open(f"fertig/{a}/{i:02d}.png").convert("RGBA") for i in range(8)]
    bilder = [b.resize((round(b.width * SK), round(b.height * SK)), Image.LANCZOS) for b in bilder]
    zellen.append((titel, bilder))
zb = round(762 * SK); zh = round(720 * SK) + 22
breit = lambda b: 2 if b[0].width > zb + 5 else 1
# Platzierung mit doppelt breiten Zellen
pos, x, y = [], 0, 0
for titel, b in zellen:
    w = breit(b)
    if x + w > SPALTEN: x, y = 0, y + 1
    pos.append((x, y)); x += w
zeilen = y + 1
try:
    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 15)
except OSError:
    font = ImageFont.load_default()
frames = []
for i in range(8):
    c = Image.new("RGBA", (SPALTEN * zb, zeilen * zh), hg + (255,))
    d = ImageDraw.Draw(c)
    for (titel, b), (cx, cy) in zip(zellen, pos):
        c.alpha_composite(b[i], (cx * zb, cy * zh))
        d.text((cx * zb + 8, cy * zh + zh - 20), titel, fill=(220, 225, 235), font=font)
    frames.append(c.convert("RGB").quantize(colors=255, method=Image.MEDIANCUT, dither=Image.Dither.NONE))
frames[0].save(sys.argv[1], save_all=True, append_images=frames[1:], duration=110, loop=0, optimize=True)
print(sys.argv[1], frames[0].size)
