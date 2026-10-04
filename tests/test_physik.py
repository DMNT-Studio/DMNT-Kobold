import pytest

from dmnt_kobold.monitore import Monitor, Rechteck
from dmnt_kobold.physik import (
    FAELLT,
    GEDREHT,
    GELANDET,
    GERETTET,
    GEWECHSELT,
    GEZOGEN,
    MAX_FALL,
    STEHT,
    Koerper,
)

DT = 1 / 60


def mon(name, x, y, w, h, *, frei=None, dpr=1.0, haupt=False):
    g = Rechteck(x, y, w, h)
    return Monitor(name, g, frei or g, dpr, haupt)


def laufe(k, monitore, sekunden, *, bleiben=False):
    ereignisse = []
    for _ in range(int(sekunden / DT)):
        ereignisse += k.schritt(DT, monitore, laufen=True, auf_monitor_bleiben=bleiben)
    return ereignisse


def falle(k, monitore, max_s=5.0):
    ereignisse = []
    for _ in range(int(max_s / DT)):
        ereignisse += k.schritt(DT, monitore)
        if k.zustand == STEHT:
            break
    return ereignisse


# --- Fallen -----------------------------------------------------------------

def test_fallen_endet_exakt_auf_dem_boden():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    k = Koerper(500, 100)
    k.zustand = FAELLT
    ev = falle(k, [m])
    assert GELANDET in ev
    assert k.zustand == STEHT
    assert k.y == 1040


def test_fallgeschwindigkeit_ist_gedeckelt():
    m = mon("A", 0, -20000, 1920, 21080, haupt=True)
    k = Koerper(500, -19000)
    k.zustand = FAELLT
    for _ in range(300):
        k.schritt(DT, [m])
    assert k.vy <= MAX_FALL


def test_loslassen_in_der_taskleiste_setzt_auf_boden():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    k = Koerper(500, 1070)
    k.greifen()
    k.loslassen(0, 0)
    falle(k, [m])
    assert k.y == 1040 and k.zustand == STEHT


def test_wurf_prallt_am_rand_ab():
    m = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(1800, 500)
    k.greifen()
    k.loslassen(2000, 0)
    falle(k, [m])
    assert k.x + k.halbe_breite <= 1920
    assert k.zustand == STEHT


def test_wurf_wird_gedeckelt():
    k = Koerper()
    k.loslassen(10000, 10000)
    assert (k.vx ** 2 + k.vy ** 2) ** 0.5 == pytest.approx(2200)


def test_huepfer_landet_wieder():
    m = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    k = Koerper(500, 1040)
    k.huepfen()
    assert k.zustand == FAELLT
    ev = falle(k, [m])
    assert GELANDET in ev and k.y == 1040


def test_gezogen_ignoriert_physik():
    m = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(500, 300)
    k.greifen()
    k.schritt(DT, [m])
    assert k.zustand == GEZOGEN and k.y == 300


# --- Laufen über Kanten -------------------------------------------------------

def test_laufen_ueber_buendige_kante():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    b = mon("B", 1920, 0, 1920, 1080)
    k = Koerper(1900, 1080)
    ev = laufe(k, [a, b], 2)
    assert GEWECHSELT in ev
    assert k.x > 1920 and k.y == 1080 and k.zustand == STEHT


def test_laufen_ueber_kante_bei_gemischter_skalierung():
    a = mon("A", 0, 0, 1280, 720, dpr=1.5, haupt=True)  # 1920x1080 nativ bei 150 %
    b = mon("B", 1920, 0, 1920, 1080)
    k = Koerper(1270, 720)
    ev = laufe(k, [a, b], 1)
    assert GEWECHSELT in ev
    assert 1920 <= k.x < 1990 and k.y == 1080


def test_laufen_auf_tieferen_nachbarn_faellt():
    a = mon("A", 0, 0, 1920, 1040, haupt=True)
    b = mon("B", 1920, 0, 1920, 1200)
    k = Koerper(1900, 1040)
    ev = laufe(k, [a, b], 1)
    assert GEWECHSELT in ev
    assert GELANDET in ev or k.zustand == FAELLT
    falle(k, [a, b])
    assert k.y == 1200 and k.x > 1920


def test_laufen_auf_hoeheren_nachbarn_dreht_um():
    a = mon("A", 0, 0, 1920, 1200, haupt=True)
    b = mon("B", 1920, 0, 1920, 1040)
    k = Koerper(1850, 1200)
    ev = laufe(k, [a, b], 3)
    assert GEDREHT in ev
    assert k.x + k.halbe_breite <= 1920 and k.richtung == -1


def test_laufen_ins_leere_dreht_um():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(1850, 1080)
    ev = laufe(k, [a], 3)
    assert GEDREHT in ev
    assert k.x + k.halbe_breite <= 1920


def test_laufen_nach_links_ins_leere_dreht_um():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(60, 1080)
    k.richtung = -1
    ev = laufe(k, [a], 3)
    assert GEDREHT in ev and k.richtung == 1
    assert k.x - k.halbe_breite >= 0


def test_auf_diesem_monitor_bleiben_verhindert_kantenwechsel():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    b = mon("B", 1920, 0, 1920, 1080)
    k = Koerper(1850, 1080)
    ev = laufe(k, [a, b], 3, bleiben=True)
    assert GEWECHSELT not in ev and GEDREHT in ev
    assert k.x < 1920


def test_seitliche_taskleiste_ist_eine_wand():
    a = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1860, 1080), haupt=True)
    b = mon("B", 1920, 0, 1920, 1080)
    k = Koerper(1800, 1080)
    ev = laufe(k, [a, b], 3)
    assert GEDREHT in ev and k.x < 1860


# --- Monitor-Änderungen -------------------------------------------------------

def test_ausserhalb_aller_monitore_auf_hauptmonitor():
    a = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    k = Koerper(3000, 1080)  # Monitor B wurde abgesteckt
    assert k.pruefe_monitore([a]) is True
    assert (k.x, k.y, k.zustand) == (960, 1040, STEHT)


def test_innerhalb_bleibt_wo_er_ist():
    a = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(500, 1080)
    assert k.pruefe_monitore([a]) is False
    assert k.x == 500


def test_taskleiste_waechst_avatar_wird_hochgesetzt():
    alt = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    neu = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1000), haupt=True)
    k = Koerper(500, 1040)
    k.schritt(DT, [alt])
    k.schritt(DT, [neu])
    assert k.y == 1000 and k.zustand == STEHT


def test_taskleiste_verschwindet_avatar_faellt():
    alt = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    neu = mon("A", 0, 0, 1920, 1080, haupt=True)
    k = Koerper(500, 1040)
    k.schritt(DT, [neu])
    assert k.zustand == FAELLT
    falle(k, [neu])
    assert k.y == 1080


def test_absturz_ins_nichts_wird_gerettet():
    a = mon("A", 0, 0, 1920, 1080, frei=Rechteck(0, 0, 1920, 1040), haupt=True)
    b = mon("B", 1920, -500, 1920, 1080)
    k = Koerper(2500, 1500)  # unter B, nichts mehr darunter
    k.zustand = FAELLT
    ev = falle(k, [a, b])
    assert GERETTET in ev
    assert (k.x, k.y) == (960, 1040)


# --- Stefans Aufbau: Ultrawide unten, zweiter Monitor versetzt darüber ---------

def stefans_monitore():
    haupt = mon("A", 0, 0, 5120, 1440, frei=Rechteck(13, 0, 5107, 1392), haupt=True)
    oben = mon("B", 1566, -1080, 1920, 1080, frei=Rechteck(1566, -1080, 1920, 1032))
    return [haupt, oben]


def test_wurf_auf_oberem_monitor_prallt_an_dessen_rand_ab():
    ms = stefans_monitore()
    k = Koerper(1700, -600)
    k.greifen()
    k.loslassen(-1500, -800)
    falle(k, ms)
    assert k.y == -48
    assert 1566 <= k.x <= 3486


def test_wurf_nach_oben_stoesst_an_die_decke_des_hauptmonitors():
    ms = stefans_monitore()
    k = Koerper(600, 900)  # links unter dem leeren Bereich neben Monitor B
    k.greifen()
    k.loslassen(0, -2000)
    tiefster = 0.0
    for _ in range(120):
        k.schritt(DT, ms)
        tiefster = min(tiefster, k.y - k.hoehe / 2)
        if k.zustand == STEHT:
            break
    assert tiefster >= -1  # Körpermitte nie oberhalb der Monitor-Oberkante
    assert k.y == 1392
