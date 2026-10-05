"""Erzeugt packaging/kobold.ico und die Bilder der Webseite aus Kiesels Porträt.

Nur nötig, wenn sich Kiesels Porträt ändert. Braucht Pillow (pip install -e .[bauen]).
Aufruf lokal auf dem PC: python packaging/icon_bauen.py
"""
from pathlib import Path

from PIL import Image

WURZEL = Path(__file__).resolve().parent.parent
PORTRAET = WURZEL / "src" / "dmnt_kobold" / "avatare" / "kiesel" / "portraet.png"


def quadratisch(bild: Image.Image) -> Image.Image:
    bild = bild.convert("RGBA")
    box = bild.getbbox() or (0, 0, *bild.size)
    bild = bild.crop(box)
    seite = int(max(bild.size) * 1.08)
    leer = Image.new("RGBA", (seite, seite), (0, 0, 0, 0))
    leer.paste(bild, ((seite - bild.width) // 2, (seite - bild.height) // 2), bild)
    return leer


def main() -> None:
    bild = quadratisch(Image.open(PORTRAET))
    gross = bild.resize((256, 256), Image.LANCZOS)
    gross.save(WURZEL / "packaging" / "kobold.ico",
               sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    web = WURZEL / "website" / "bilder"
    web.mkdir(parents=True, exist_ok=True)
    bild.resize((360, 360), Image.LANCZOS).save(web / "kiesel.png", optimize=True)
    bild.resize((64, 64), Image.LANCZOS).save(web / "favicon.png", optimize=True)
    print("kobold.ico, website/bilder/kiesel.png und favicon.png geschrieben")


if __name__ == "__main__":
    main()
