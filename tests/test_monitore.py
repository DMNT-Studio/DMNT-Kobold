from dmnt_kobold.monitore import (
    Monitor,
    Rechteck,
    auf_irgendeinem,
    boden_unter,
    hauptmonitor,
    monitor_unter_fuss,
    nachbar,
    virtuelle_grenzen,
)


def mon(name, x, y, w, h, *, frei=None, dpr=1.0, haupt=False):
    g = Rechteck(x, y, w, h)
    return Monitor(name, g, frei or g, dpr, haupt)


def test_boden_taskleiste_unten():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    assert boden_unter([m], 500, 300) == 1040
    assert monitor_unter_fuss([m], 500, 1040) is m


def test_boden_taskleiste_oben():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 40, 1920, 1040), haupt=True)
    assert boden_unter([m], 500, 300) == 1080


def test_boden_taskleiste_seitlich():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(60, 0, 1860, 1080), haupt=True)
    assert boden_unter([m], 500, 300) == 1080
    # über der Taskleiste selbst gibt es keinen Boden
    assert boden_unter([m], 30, 300) is None


def test_punkt_in_taskleiste_wird_hochgesetzt():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    assert boden_unter([m], 500, 1060) == 1040


def test_naechster_boden_bei_gestapelten_monitoren():
    oben = mon("O", 0, -1080, 1920, 1080)
    unten = mon("U", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    assert boden_unter([oben, unten], 500, -500) == 0
    assert boden_unter([oben, unten], 500, 200) == 1040


def test_hauptmonitor():
    a = mon("A", 0, 0, 100, 100)
    b = mon("B", 100, 0, 100, 100, haupt=True)
    assert hauptmonitor([a, b]) is b
    assert hauptmonitor([a]) is a


def test_nachbar_buendig_und_nicht_buendig():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    b = mon("B", 1920, 0, 1920, 1080)
    c = mon("C", 4000, 0, 1920, 1080)  # Lücke
    assert nachbar([a, b, c], a, 1, 1080) is b
    assert nachbar([a, b, c], b, -1, 1080) is a
    assert nachbar([a, b, c], b, 1, 1080) is None
    assert nachbar([a, b, c], a, -1, 1080) is None


def test_nachbar_mit_gemischter_skalierung():
    # Qt 6: linke obere Ecke nativ, Größe logisch. A ist 150 % (1920 nativ → 1280 logisch).
    a = mon("A", 0, 0, 1280, 720, dpr=1.5, haupt=True)
    b = mon("B", 1920, 0, 1920, 1080, dpr=1.0)
    boden_nativ = a.nach_nativ_y(a.boden)
    assert boden_nativ == 1080
    assert nachbar([a, b], a, 1, boden_nativ) is b
    assert nachbar([a, b], b, -1, 1080) is a


def test_virtuelle_grenzen_und_auf_irgendeinem():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    b = mon("B", -1280, 200, 1280, 1024)
    g = virtuelle_grenzen([a, b])
    assert (g.links, g.oben, g.rechts, g.unten) == (-1280, 0, 1920, 1224)
    assert auf_irgendeinem([a, b], 100, 1080)
    assert not auf_irgendeinem([a, b], 5000, 500)
