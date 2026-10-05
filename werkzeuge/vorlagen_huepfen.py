"""Neuen Hüpf-Avatar anlegen: leere Rahmen je Pose, Bauplan, Start-Verhalten, LIESMICH.

Aufruf (über das Bau-Werkzeug):
    python werkzeuge/avatar_bauen.py --vorlagen quellen/<name> [--innen <gegenstand>]

Es entstehen nur Rahmen mit Größe und Fußpunkt-Markierung – keine Figur. Die eigenen
Bilder setzt man danach im Avatar-Editor ein (Reiter „Bilder“ → „Ersetzen“). Vorhandene
Dateien bleiben unangetastet; neu geschrieben werden nur _uebersicht.png und LIESMICH.txt.
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WURZEL = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(WURZEL / "src"))
from dmnt_kobold.regeln import standard_verhalten  # noqa: E402

RAHMEN = (256, 256)          # Pixel je Pose (Skalierung 2 → 128 × 128 logische Pixel)
KOERPER = (150, 150)         # Richtgröße des Körpers im Rahmen
INNEN_RAHMEN = (64, 64)

#: Pose → (wofür, Bilder pro Sekunde)
POSEN: dict[str, tuple[str, float]] = {
    "ruhe": ("Stehen ohne Anlass – Pflicht", 1),
    "hocken": ("vor dem Hüpfer zusammenziehen", 4),
    "absprung": ("abspringen, gestreckt", 4),
    "flug": ("im Bogen fliegen", 4),
    "landen": ("aufkommen, gestaucht", 4),
    "freuen": ("Freude (Klick, Musik …)", 4),
    "erschrecken": ("Erschrecken (Wackeln mit der Maus)", 4),
    "schlafen": ("Schlafen", 1),
    "sprechen": ("Reden (Sprechblase)", 4),
}
DREHEN = ["vorne", "dreiviertel", "seite", "dreiviertel_hinten", "hinten"]


def _schrift(groesse: int):
    for name in ("segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"):
        try:
            return ImageFont.truetype(name, groesse)
        except OSError:
            continue
    return ImageFont.load_default()


def _gestrichelt(d: ImageDraw.ImageDraw, box, farbe, laenge: int = 8) -> None:
    x0, y0, x1, y1 = box
    for x in range(x0, x1, laenge * 2):
        d.line([(x, y0), (min(x + laenge, x1), y0)], fill=farbe, width=2)
        d.line([(x, y1), (min(x + laenge, x1), y1)], fill=farbe, width=2)
    for y in range(y0, y1, laenge * 2):
        d.line([(x0, y), (x0, min(y + laenge, y1))], fill=farbe, width=2)
        d.line([(x1, y), (x1, min(y + laenge, y1))], fill=farbe, width=2)


def rahmen(titel: str, unter: str = "", groesse: tuple[int, int] = RAHMEN, koerper: bool = True) -> Image.Image:
    """Leerer Rahmen: Umriss, Richtgröße des Körpers, Fußpunkt unten in der Mitte."""
    b, h = groesse
    im = Image.new("RGBA", (b, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rectangle([0, 0, b - 1, h - 1], outline=(150, 160, 170, 200), width=2)
    if koerper:
        kb, kh = KOERPER
        _gestrichelt(d, ((b - kb) // 2, h - kh - 1, (b + kb) // 2, h - 2), (120, 200, 170, 230))
    fx = b // 2                                   # Fußpunkt
    d.polygon([(fx - 9, h - 1), (fx + 9, h - 1), (fx, h - 13)], fill=(230, 90, 70, 255))
    d.text((8, 6), titel, fill=(60, 70, 80, 255), font=_schrift(22 if b > 100 else 12))
    if unter:
        d.text((8, 34), unter, fill=(110, 120, 130, 255), font=_schrift(13))
    return im


def _schreiben(pfad: Path, inhalt, neu: list[str]) -> None:
    """Nur anlegen, nie überschreiben (Stefans Bilder und Einstellungen bleiben)."""
    if pfad.exists():
        return
    pfad.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(inhalt, Image.Image):
        inhalt.save(pfad)
    else:
        pfad.write_text(json.dumps(inhalt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    neu.append(pfad.name)


def bauplan(ordner: Path) -> dict:
    quellen = {n: {"datei": f"{n}.png"} for n in POSEN}
    quellen.update({f"drehen_{i}": {"datei": f"drehen_{i}_{a}.png"} for i, a in enumerate(DREHEN, 1)})
    animationen = {n: {"fps": fps, "bilder": [[n, 0, "normal"]]} for n, (_w, fps) in POSEN.items()}
    animationen["drehen"] = {"fps": 6, "bilder": [[f"drehen_{i}", 0, "normal"] for i in range(1, 6)]}
    return {
        "id": ordner.name, "name": ordner.name.capitalize(), "skalierung": 2,
        "ausrichtung": "rahmen", "rahmen_px": list(RAHMEN), "blickrichtung": 1,
        "bewegung": {"art": "huepfen", "hocken_ms": 260,
                     "stauchen": {"breite": 1.18, "hoehe": 0.78}, "strecken": {"breite": 0.88, "hoehe": 1.16}},
        "koerper_deckkraft": 1.0,
        "partikel": {"landen": {"farbe": "#F2E36B", "deckkraft": 0.55, "anzahl": [6, 10], "groesse_px": [3, 4],
                                "reichweite_px": 22, "dauer_ms": 380, "form": "quadrat"}},
        "toene": {"landen": {"dateien": ["toene/schmatz_1.ogg", "toene/schmatz_2.ogg"], "tonhoehe": 0.08},
                  "sprechen": {"dateien": ["toene/pieps.ogg"], "tonhoehe": 0.15, "wiederholen": [1, 3]}},
        "quellen": quellen, "referenz": ["ruhe", 0], "animationen": animationen,
    }


def verhalten(name: str, innen: str | None) -> dict:
    """Standard-Verhalten, dazu Hüpf-Werte, freuen_huepfend bei Klick, Innenleben
    „froh“ beim Freuen und „erschreckt“ beim Wackeln."""
    v = copy.deepcopy(standard_verhalten())
    v["beschreibung"] = f"{name} – hüpfender Avatar (aus der Hüpf-Vorlage, ohne Code)."
    v["werte"] = {"sprungweite_px": 36, "sprunghoehe_px": 26, "hupf_pause_min_s": 0.8, "hupf_pause_max_s": 1.6}
    for r in v["regeln"]:
        dann = r["dann"]
        if r["id"] == "klick":
            dann[:] = [{"aktion": "freuen_huepfend"}]
            r["dauer_s"] = 2.8
        if not innen:
            continue
        if r["id"] == "klick" or any(a.get("aktion") == "animation" and a.get("name") == "freuen" for a in dann):
            dann.append({"aktion": "innen", "variante": "froh"})
        elif r["id"] in ("wackeln", "wackeln_kurz"):
            dann.append({"aktion": "innen", "variante": "erschreckt"})
    return v


def zubehoer(innen: str) -> dict:
    return {innen: {"datei": f"zubehoer/{innen}.png", "sitz": "innen", "gruppe": "innen", "immer": True,
                    "posen": {},
                    "varianten": {"froh": {"datei": f"zubehoer/{innen}@froh.png", "x": 0, "y": 0},
                                  "erschreckt": {"datei": f"zubehoer/{innen}@erschreckt.png", "x": 0, "y": 0}}}}


LIESMICH = """{name} – Hüpf-Avatar: Bilder einsetzen
==========================================

Was liegt hier?
  bauplan.json      Aussehen: Posen, Hüpf-Form, Spritzer, Töne
  verhalten.json    Verhalten: Werte (Sprungweite, -höhe, Pausen) und Regeln
  {innen_datei}*.png       Platzhalter-Rahmen je Pose – werden durch deine Bilder ersetzt
  _uebersicht.png   alle Posen auf einen Blick

Jede Pose ist ein Rahmen von {b} × {h} Pixeln. Der rote Pfeil unten in der Mitte ist
der Fußpunkt: dort steht die Figur auf der Taskleiste. Das gestrichelte Feld zeigt die
Richtgröße des Körpers. Andere Bildgrößen werden auf die Rahmenbreite skaliert und
unten bündig gesetzt.

Körper
  - halbtransparentes PNG (die Deckkraft steckt im Bild selbst)
  - ist dein Bild deckend, stelle in bauplan.json "koerper_deckkraft" z. B. auf 0.7,
    damit das Innenleben durchscheint
  - Gefühle zeigen nur Augen, Mund und Innenleben – je Animation ein eigenes Bild

Posen
{posen}
  drehen_1 … drehen_5: vorne → ¾ → Seite → ¾ hinten → hinten (optional; ohne diese
  Bilder: im Editor unter „Animationen“ die Animation „drehen“ löschen – dann dreht
  er sich mit einer Pseudo-Drehung)
{innen_text}
Töne (kommen automatisch)
  toene/schmatz_1.ogg, toene/schmatz_2.ogg   beim Landen (zufällig, Tonhöhe ±8 %)
  toene/pieps.ogg                            beim Sprechen (1–3 Mal, Tonhöhe ±15 %)
  .ogg oder .wav. Fehlt eine Datei, entfällt der Ton (der Bau warnt nur).

Wichtig: Dieser Ordner ist privat (steht in .gitignore) und wird nie hochgeladen.
"""


def huepf_vorlagen(ordner: Path, innen: str | None = None) -> Path:
    neu: list[str] = []
    ordner.mkdir(parents=True, exist_ok=True)
    name = ordner.name.capitalize()
    plan_datei = ordner / "bauplan.json"
    if plan_datei.exists():
        plan = json.loads(plan_datei.read_text(encoding="utf-8"))
    else:
        plan = bauplan(ordner)
        _schreiben(plan_datei, plan, neu)
    for q, d in plan["quellen"].items():
        nr = q.rsplit("_", 1)[-1]
        dreh = DREHEN[int(nr) - 1].replace("dreiviertel", "¾").replace("_", " ") if nr.isdigit() else q
        wofuer = POSEN.get(q, (f"Drehansicht: {dreh}", 0))[0]
        _schreiben(ordner / d["datei"], rahmen(q, wofuer), neu)
    _schreiben(ordner / "verhalten.json", verhalten(name, innen), neu)
    if innen:
        _schreiben(ordner / "zubehoer.json", zubehoer(innen), neu)
        for datei, titel in ((f"{innen}.png", innen), (f"{innen}@froh.png", "@froh"),
                             (f"{innen}@erschreckt.png", "@erschreckt")):
            _schreiben(ordner / "zubehoer" / datei, rahmen(titel, groesse=INNEN_RAHMEN, koerper=False), neu)
    (ordner / "toene").mkdir(exist_ok=True)

    # Übersicht
    namen = list(plan["quellen"])
    zelle, kopf = 300, 64
    spalten = 5
    zeilen = (len(namen) + spalten - 1) // spalten
    ueb = Image.new("RGB", (zelle * spalten, kopf + zelle * zeilen), (40, 44, 48))
    d = ImageDraw.Draw(ueb)
    d.text((14, 12), f"{name}: {len(namen)} Posen, je {RAHMEN[0]} × {RAHMEN[1]} px, Fußpunkt = roter Pfeil "
                     "unten Mitte", fill=(235, 238, 236), font=_schrift(20))
    for i, q in enumerate(namen):
        x, y = (i % spalten) * zelle, kopf + (i // spalten) * zelle
        bild = Image.open(ordner / plan["quellen"][q]["datei"]).convert("RGBA")
        bild.thumbnail((zelle - 40, zelle - 60))
        hg = Image.new("RGBA", bild.size, (215, 222, 226, 255))
        hg.alpha_composite(bild)
        ueb.paste(hg.convert("RGB"), (x + (zelle - bild.width) // 2, y + 36))
        d.text((x + 14, y + 8), f"{q}  ({plan['quellen'][q]['datei']})", fill=(160, 200, 185), font=_schrift(14))
    ueb.save(ordner / "_uebersicht.png")

    posen = "\n".join(f"  {q:<12} {w}" for q, (w, _f) in POSEN.items())
    innen_text = (f"\nInnenleben ({innen})\n  zubehoer/{innen}.png             Grundvariante\n"
                  f"  zubehoer/{innen}@froh.png        beim Freuen (Klick, Musik …)\n"
                  f"  zubehoer/{innen}@erschreckt.png  beim Erschrecken (Wackeln)\n"
                  "  Eigene Dateien, freigestellt. Lage und Größe im Editor: Reiter „Zubehör“,\n"
                  "  Versatz je Variante dort in der Varianten-Liste.\n") if innen else ""
    (ordner / "LIESMICH.txt").write_text(
        LIESMICH.format(name=name, b=RAHMEN[0], h=RAHMEN[1], posen=posen, innen_text=innen_text,
                        innen_datei="<pose>"), encoding="utf-8")
    print(f"  Hüpf-Vorlage in {ordner}: {len(neu)} Datei(en) neu angelegt"
          + (f" ({', '.join(neu[:6])}{' …' if len(neu) > 6 else ''})" if neu else " (alles schon da)"))
    return ordner
