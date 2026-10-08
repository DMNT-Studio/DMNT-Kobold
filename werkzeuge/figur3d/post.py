"""Nachbearbeitung: Comic-Kontur (außen + Teilgrenzen) und Vorschaubögen."""
import sys, glob, os
import numpy as np
from PIL import Image
from scipy import ndimage

AUSSEN = 5   # px bei 280 px/Einheit
INNEN = 3
SPRUNG = 0.06
SPRUNG_NAHT = 0.3   # an Verbindungsstellen (Bein-Schuh, Arm-Handschuh, Körper-Glied) nur bei großem Sprung
NAHT = [(128, 64), (144, 80), (96, 32), (112, 48), (16, 96), (16, 112), (16, 128), (16, 144)]   # Tiefensprung (Einheiten), ab dem eine Innenlinie gezogen wird

def kontur(bild_pfad, id_pfad=None):
    im = np.array(Image.open(bild_pfad).convert('RGBA')).astype(np.float32)
    a = im[..., 3] / 255.0
    form = a > 0.5
    dil = ndimage.binary_dilation(form, structure=ndimage.generate_binary_structure(2, 2), iterations=AUSSEN)
    out = np.zeros_like(im)
    # Linien
    linie = dil & ~form
    if id_pfad and os.path.exists(id_pfad):
        idb = np.array(Image.open(id_pfad).convert('RGBA'))
        ids = idb[..., 0].astype(int) * (idb[..., 3] > 128)
        tiefe = (idb[..., 1].astype(np.float32) * 256 + idb[..., 2]) / 65535.0 * 8.0   # Einheiten
        kant = np.zeros_like(form)
        for dy, dx in ((0, 1), (1, 0), (1, 1), (1, -1), (0, 2), (2, 0)):
            b = np.roll(np.roll(ids, dy, 0), dx, 1)
            tb = np.roll(np.roll(tiefe, dy, 0), dx, 1)
            dz = np.abs(tiefe - tb)
            paar = np.zeros_like(form)
            for u, v in NAHT:
                paar |= ((ids == u) & (b == v)) | ((ids == v) & (b == u))
            kant |= (ids != b) & (ids > 0) & (b > 0) & (dz > np.where(paar, SPRUNG_NAHT, SPRUNG))
        kant = ndimage.binary_dilation(kant, iterations=INNEN // 2 + 0) if INNEN > 1 else kant
        innen = kant & form
    else:
        innen = np.zeros_like(form)
    rgb = im[..., :3] * a[..., None]                       # vormultipliziert
    alpha = np.maximum(a, dil.astype(np.float32))
    farbe = np.where(alpha[..., None] > 0, rgb / np.maximum(alpha[..., None], 1e-6), 0)
    farbe[linie] = (12, 12, 14)
    farbe[innen] = farbe[innen] * 0.15 + np.array([12, 12, 14]) * 0.85
    # weiche Außenkante
    alpha_w = ndimage.gaussian_filter(dil.astype(np.float32), 0.7)
    alpha = np.where(form, alpha, alpha_w)
    out = np.dstack([np.clip(farbe, 0, 255), np.clip(alpha * 255, 0, 255)]).astype(np.uint8)
    return out

def ordner(anim, ziel='fertig'):
    os.makedirs(f'{ziel}/{anim}', exist_ok=True)
    bilder = []
    for p in sorted(glob.glob(f'render/{anim}/[0-9][0-9].png')):
        o = kontur(p, p.replace('.png', '_id.png'))
        Image.fromarray(o, 'RGBA').save(f'{ziel}/{anim}/' + os.path.basename(p))
        bilder.append(o)
    return bilder

def bogen(anims, datei, hg=(52, 56, 68), skala=0.5):
    zeilen = []
    for a in anims:
        bs = ordner(a)
        zeilen.append(bs)
    w = max(sum(b.shape[1] for b in z) for z in zeilen); h = sum(max(b.shape[0] for b in z) for z in zeilen)
    c = Image.new('RGBA', (w, h), hg + (255,))
    y = 0
    for z in zeilen:
        x = 0
        for b in z:
            c.alpha_composite(Image.fromarray(b, 'RGBA'), (x, y)); x += b.shape[1]
        y += max(b.shape[0] for b in z)
    c = c.resize((int(w * skala), int(h * skala)), Image.LANCZOS)
    c.save(datei)

if __name__ == '__main__':
    bogen(sys.argv[2:], sys.argv[1], skala=float(os.environ.get('SKALA', 0.5)))
