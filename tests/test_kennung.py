"""Technische Namen: „Kopfhörer“ aus dem Editor passt zur Regel „kopfhoerer“."""
import json
import sys
from pathlib import Path

from dmnt_kobold import katalog

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "werkzeuge"))


def test_kennung():
    assert katalog.kennung("Kopfhörer") == "kopfhoerer"
    assert katalog.kennung(" Große Mütze ") == "grosse_muetze"
    assert katalog.kennung("hut-2") == "hut_2"
    assert katalog.kennung("✨") == ""


def test_bau_liest_umlaut_zubehoer_als_kennung(tmp_path, capsys):
    import avatar_bauen

    (tmp_path / "zubehoer.json").write_text(json.dumps(
        {"kopfhörer": {"datei": "zubehoer/kopfhörer.png", "sitz": "ueber_kopf", "gruppe": "Kopfhörer"}},
        ensure_ascii=False), encoding="utf-8")
    plan = avatar_bauen.zubehoer_laden(tmp_path)
    assert list(plan) == ["kopfhoerer"] and plan["kopfhoerer"]["gruppe"] == "kopfhoerer"
    assert plan["kopfhoerer"]["datei"] == "zubehoer/kopfhörer.png"        # Datei bleibt, wie sie heißt
    assert "kopfhoerer" in capsys.readouterr().out


def test_regel_mit_umlaut_setzt_kennung():
    import random

    from dmnt_kobold.bus import Ereignis, EventBus
    from dmnt_kobold.eigenleben import Eigenleben
    from dmnt_kobold.motor import Verhaltensmotor
    from dmnt_kobold.regeln import RegelPersoenlichkeit

    bus = EventBus()
    m = Verhaltensmotor(bus, Eigenleben(random.Random(1)))
    v = {"regeln": [{"id": "musik", "wenn": {"ereignis": "audio.laeuft"},
                     "dann": [{"aktion": "zubehoer", "name": "Kopfhörer", "an": True}]}]}
    p = RegelPersoenlichkeit(bus, m, v)
    p.on_event(Ereignis("audio.laeuft", {}, 0.0))
    assert m.zubehoer == frozenset({"kopfhoerer"})
