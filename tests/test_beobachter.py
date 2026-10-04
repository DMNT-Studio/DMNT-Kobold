from dmnt_kobold.beobachter import LeerlaufAnalyse, TippAnalyse, WackelAnalyse, tageszeit


def namen(liste):
    return [n for n, _ in liste]


def tippen(a, t0, sekunden, jeder=1):
    """Füttert 10 Takte pro Sekunde; jeder n-te Takt ist aktiv."""
    ev = []
    for i in range(int(sekunden * 10)):
        ev += a.update(t0 + i / 10, i % jeder == 0)
    return ev


def test_tippen_sitzung_und_pause():
    a = TippAnalyse()
    ev = tippen(a, 0.0, 20, jeder=2)            # mäßiges Tempo, 20 s
    assert namen(ev) == ["tastatur.tippt"]
    ev = tippen(a, 20.0, 6, jeder=10**9)         # 6 s nichts
    ev = [e for e in ev if e[0] == "tastatur.pause"] or ev
    assert namen(ev) == ["tastatur.pause"]
    assert 19 <= ev[0][1]["sitzung_s"] <= 20.1
    assert not a.tippt


def test_einzelne_taste_ist_kein_tippen():
    a = TippAnalyse()
    ev = a.update(0.0, True) + tippen(a, 0.1, 5, jeder=10**9)
    assert ev == []


def test_schnelles_tippen():
    a = TippAnalyse()
    ev = tippen(a, 0.0, 5, jeder=1)              # jeder Takt aktiv
    assert namen(ev) == ["tastatur.tippt", "tastatur.schnell"]
    ev = tippen(a, 5.0, 5, jeder=1)
    assert ev == []                              # nur einmal pro Sitzung


def test_wackeln():
    w = WackelAnalyse()
    t, x, erkannt = 0.0, 500.0, False
    for i in range(12):
        x += 60 if i % 2 == 0 else -60
        t += 0.08
        erkannt = w.update(t, x) or erkannt
    assert erkannt


def test_ruhige_maus_wackelt_nicht():
    w = WackelAnalyse()
    assert not any(w.update(i * 0.1, 500 + i * 15) for i in range(30))
    assert not any(w.update(5 + i * 0.1, 500 + (i % 2) * 5) for i in range(30))  # zittern < 25 px


def test_leerlauf():
    a = LeerlaufAnalyse()
    assert a.update(30) == []
    assert a.update(61) == [("leerlauf.1", {"minuten": 1})]
    assert a.update(70) == []
    assert a.update(301) == [("leerlauf.5", {"minuten": 5})]
    assert a.update(0.5) == [("leerlauf.ende", {"minuten": 5})]
    assert a.update(0.5) == []


def test_tageszeit():
    assert [tageszeit(h) for h in (4, 5, 10, 11, 16, 17, 21, 22)] == [
        "nachts", "morgens", "morgens", "mittags", "mittags", "abends", "abends", "nachts"]
