"""Avatar „Flugzeug": Bau, Pfeifen mit Mindestabstand, eigenes Körperbild bleibt lokal."""
from __future__ import annotations

import json
import random
import subprocess
from pathlib import Path

from dmnt_kobold import katalog
from dmnt_kobold.toene import KoerperTon, Toene

WURZEL = Path(__file__).resolve().parents[1]
QUELLE = WURZEL / "quellen" / "flugzeug"
GEBAUT = WURZEL / "src" / "dmnt_kobold" / "avatare" / "flugzeug"


def _toene(tmp_path, chance=1.0, abstand=25.0):
    wav = tmp_path / "p.wav"
    wav.write_bytes(b"RIFF")
    t = Toene(tmp_path / "cache", 0.0, koerper_toene={"bewegen": KoerperTon([wav], chance=chance, abstand_s=abstand)},
              rng=random.Random(1))
    jetzt = [1000.0]
    t.uhr = lambda: jetzt[0]
    return t, jetzt


def test_pfeifen_hoechstens_alle_25_s(tmp_path):
    t, jetzt = _toene(tmp_path)
    assert t.darf("bewegen")
    jetzt[0] += 10
    assert not t.darf("bewegen")
    jetzt[0] += 16
    assert t.darf("bewegen")


def test_pfeifen_chance(tmp_path):
    t, jetzt = _toene(tmp_path, chance=0.5, abstand=0)
    treffer = sum(t.darf("bewegen") for _ in range(400))
    assert 140 < treffer < 260


def test_unbekannter_ton_kommt_nicht(tmp_path):
    t, _ = _toene(tmp_path)
    assert not t.darf("freuen")


def test_bauplan_gegen_katalog():
    plan = json.loads((QUELLE / "bauplan.json").read_text(encoding="utf-8"))
    fehler, warnungen = katalog.koerper_pruefen(plan, QUELLE)
    assert fehler == [] and warnungen == []
    assert plan["toene"]["bewegen"]["abstand_s"] >= 20


def test_chance_und_abstand_werden_geprueft():
    plan = {"toene": {"bewegen": {"dateien": ["a.wav"], "chance": 2, "abstand_s": -1}}}
    fehler, _ = katalog.koerper_pruefen(plan)
    assert any("chance" in f for f in fehler) and any("abstand_s" in f for f in fehler)


def test_kein_gesicht_keine_vorlage():
    for svg in (QUELLE / "teile").glob("*.svg"):
        text = svg.read_text(encoding="utf-8")
        assert "<image" not in text, f"{svg.name}: eingebettetes Bild im Repo-Avatar"
        assert "augen" not in text and "mund" not in text


def test_gebauter_avatar_ohne_code():
    assert (GEBAUT / "avatar.json").is_file()
    assert not (GEBAUT / "persoenlichkeit.py").exists()


def test_lokaler_koerper_ist_ignoriert():
    for pfad in ("quellen/flugzeug_lokal/koerper.png", "src/dmnt_kobold/avatare/flugzeug_lokal/avatar.json"):
        r = subprocess.run(["git", "check-ignore", "-q", pfad], cwd=WURZEL)
        assert r.returncode == 0, f"{pfad} wäre nicht ignoriert"
