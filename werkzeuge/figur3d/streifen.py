"""render/<anim>/ → Comic-Kontur → halbe Größe → 8er-Streifen in quellen/dmnt9000_3d/<anim>.png.
Aufruf (im Ordner werkzeuge/figur3d): python streifen.py [anim ...]"""
import os, sys
from pathlib import Path
from PIL import Image
sys.path.insert(0, str(Path(__file__).parent))
os.chdir(Path(__file__).parent)
from post import ordner  # noqa: E402

ZIEL = Path(__file__).resolve().parents[2] / "quellen" / "dmnt9000_3d"
STANDARD = ("stehen gehen rennen tragen minen freuen unzufrieden sitzen schlafen fallen gezogen springen "
            "schweben anschauen sprechen sprechen_vorne erschrecken zuschauen musik").split()

def streifen(anim: str, ziel: Path = ZIEL, n: int = 8) -> Path:
    ordner(anim)
    bs = [Image.open(f"fertig/{anim}/{i:02d}.png") for i in range(n)]
    w, h = bs[0].size
    if w % 2:                                   # gerade Breite → Fußpunkt bleibt auf halben Pixeln exakt
        neu = []
        for b in bs:
            c = Image.new("RGBA", (w + 1, h)); c.paste(b, (0, 0)); neu.append(c)
        bs, w = neu, w + 1
    bs = [b.resize((w // 2, h // 2), Image.LANCZOS) for b in bs]
    s = Image.new("RGBA", (w // 2 * n, h // 2))
    for i, b in enumerate(bs):
        s.paste(b, (i * (w // 2), 0))
    ziel.mkdir(parents=True, exist_ok=True)
    s.save(ziel / f"{anim}.png", optimize=True)
    return ziel / f"{anim}.png"

if __name__ == "__main__":
    for a in sys.argv[1:] or STANDARD:
        print(streifen(a))
