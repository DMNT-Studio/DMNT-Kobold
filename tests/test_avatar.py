import random

from dmnt_kobold.beobachter import AudioAnalyse
from dmnt_kobold.bus import EventBus
from dmnt_kobold.eigenleben import Eigenleben
from dmnt_kobold.motor import Verhaltensmotor


def aufbau(qapp):
    from dmnt_kobold.avatar import avatar_laden, persoenlichkeit_laden
    darsteller, avatar = avatar_laden("dmnt9000")
    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    p = persoenlichkeit_laden(avatar, bus, m)
    return darsteller, avatar, bus, m, p


def test_dmnt9000_laedt_mit_allen_animationen(qapp):
    darsteller, avatar, *_ = aufbau(qapp)
    assert avatar is not None and avatar.name == "DMNT 9000"
    for name in ("ruhe", "bewegen", "sprechen", "anschauen", "freuen", "unzufrieden",
                 "erschrecken", "sitzen", "schlafen", "zuschauen"):
        assert name in avatar.animationen, name
    assert avatar.herkunft.exists() and avatar.portraet.exists()
    assert set(avatar.koerper_toene) >= {"sprechen", "landen", "freude", "alarm", "aufwachen", "huepfen"}
    assert 90 < darsteller.hoehe < 140


def test_rueckfall_auf_ruhe_und_laufen_heisst_bewegen(qapp):
    _, avatar, *_ = aufbau(qapp)
    assert avatar.animation("gibtsnicht") is avatar.animationen["ruhe"]
    assert avatar.animation("laufen") is avatar.animationen["bewegen"]


def test_maske_ist_nicht_leer_und_kleiner_als_fenster(qapp):
    from dmnt_kobold.avatar import Zustand
    darsteller, *_ = aufbau(qapp)
    r = darsteller.maske(Zustand(animation="ruhe")).boundingRect()
    assert r.width() > 40 and r.height() > 80
    assert r.width() < darsteller.fenster_b


def test_blob_rueckfall_bei_fehlendem_avatar(qapp):
    from dmnt_kobold.avatar import BlobDarsteller, avatar_laden
    darsteller, avatar = avatar_laden("gibtsnicht")
    assert avatar is None and isinstance(darsteller, BlobDarsteller)


def test_persoenlichkeit_star_citizen_dreht_sich_um(qapp):
    _, avatar, bus, m, p = aufbau(qapp)
    assert type(p).__name__ == "RegelPersoenlichkeit" and avatar.ohne_code   # seit 0.5.0: verhalten.json
    bus.senden("programm.gestartet", name="starcitizen.exe")
    a = m.tick(0.1)
    assert a.sprechblase is not None and "Hintergrund" in a.sprechblase[1]
    for _ in range(45):
        a = m.tick(0.1)
    assert a.animation == "zuschauen" and a.ziel == "rand_rechts"


def test_persoenlichkeit_daumen_runter_beim_wackeln(qapp):
    _, _, bus, m, _ = aufbau(qapp)
    bus.senden("maus.wackelt")
    assert m.tick(0.1).animation == "unzufrieden"


def test_spaeter_gibt_daumen_runter(qapp):
    _, _, bus, m, _ = aufbau(qapp)
    bus.senden("tastatur.tippt")
    bus.senden("tastatur.pause", sitzung_s=600)
    wid = m.tick(0.1).sprechblase[0]
    m.knopf(wid, "Später")
    assert m.tick(0.1).animation == "unzufrieden"


def test_musik_kopfhoerer_auf_und_ab(qapp):
    _, _, bus, m, _ = aufbau(qapp)
    bus.senden("audio.laeuft")
    assert "kopfhoerer" in m.tick(0.1).zubehoer
    bus.senden("audio.still")
    assert "kopfhoerer" not in m.tick(0.1).zubehoer


def test_audio_analyse():
    a = AudioAnalyse()
    ev = []
    for i in range(80):                         # 8 s Musik mit kurzer Lücke
        laut = 0.3 if not 30 <= i < 40 else 0.0
        ev += a.update(i / 10, laut)
    assert [n for n, _ in ev] == ["audio.laeuft"]
    for i in range(80, 160):                    # 8 s Stille
        ev += a.update(i / 10, 0.0)
    assert [n for n, _ in ev] == ["audio.laeuft", "audio.still"]


def test_kurzer_ton_ist_keine_musik():
    a = AudioAnalyse()
    ev = []
    for i in range(100):
        ev += a.update(i / 10, 0.5 if i < 20 else 0.0)   # 2 s Ton, dann still
    assert ev == []


def test_eigene_zubehoer_frames_haben_vorrang(qapp):
    from dmnt_kobold.avatar import Zustand
    darsteller, avatar, *_ = aufbau(qapp)
    z = Zustand(animation="laufen", zubehoer=frozenset({"kopfhoerer"}))
    _, a, rest = darsteller._frame(z)
    assert a is avatar.animationen["bewegen"] and rest == {"kopfhoerer"}   # Platzhalter
    avatar.animationen["bewegen@kopfhoerer"] = avatar.animationen["freuen"]
    _, a, rest = darsteller._frame(z)
    assert a is avatar.animationen["freuen"] and rest == frozenset()


def test_varianten(qapp):
    from dmnt_kobold.avatar import avatar_laden

    darsteller, avatar = avatar_laden("dmnt9000")
    assert darsteller.varianten("laufen") == ["bewegen"]
    assert darsteller.varianten("gibtsnicht") == ["gibtsnicht"]
    assert "sprechen" in darsteller.varianten("sprechen")


def test_eigenes_zubehoer_mit_platzierung(qapp):
    from PySide6.QtGui import QImage, QPainter

    from dmnt_kobold.avatar import Zustand, avatar_laden

    darsteller, avatar = avatar_laden("dmnt9000")
    assert {"kopfhoerer", "zylinder"} <= set(avatar.zubehoer_bilder)
    a = avatar.animationen["ruhe"]
    assert len(a.zubehoer["zylinder"]) == len(a.bilder)

    def deckung(zubehoer):
        img = QImage(darsteller.fenster_b, darsteller.fenster_h, QImage.Format.Format_ARGB32)
        img.fill(0)
        p = QPainter(img)
        darsteller.zeichnen(p, Zustand(animation="ruhe", zubehoer=frozenset(zubehoer), schatten=False))
        p.end()
        return sum(1 for y in range(0, img.height(), 2) for x in range(0, img.width(), 2)
                   if img.pixelColor(x, y).alpha() > 0)

    assert deckung({"zylinder"}) > deckung(set())
