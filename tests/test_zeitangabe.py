from datetime import datetime

import pytest

from dmnt_kobold.zeitangabe import zeit_parsen, zeit_text

JETZT = datetime(2026, 10, 5, 13, 0)


@pytest.mark.parametrize("text,erwartet", [
    ("10", datetime(2026, 10, 5, 13, 10)),
    ("in 10 minuten", datetime(2026, 10, 5, 13, 10)),
    ("1,5 h", datetime(2026, 10, 5, 14, 30)),
    ("30 sek", datetime(2026, 10, 5, 13, 0, 30)),
    ("14:30", datetime(2026, 10, 5, 14, 30)),
    ("14.30", datetime(2026, 10, 5, 14, 30)),
    ("12:00", datetime(2026, 10, 6, 12, 0)),
    ("um 9", datetime(2026, 10, 6, 9, 0)),
    ("morgen um 9:15", datetime(2026, 10, 6, 9, 15)),
    ("übermorgen", datetime(2026, 10, 7, 9, 0)),
    ("6.10. 9:00", datetime(2026, 10, 6, 9, 0)),
    ("06.10.2026 14:30", datetime(2026, 10, 6, 14, 30)),
])
def test_erkannt(text, erwartet):
    assert zeit_parsen(text, JETZT) == erwartet


@pytest.mark.parametrize("text", ["", "quatsch", "25:00", "0", "1.1.2020"])
def test_abgelehnt(text):
    assert zeit_parsen(text, JETZT) is None


def test_zeit_text():
    assert zeit_text(datetime(2026, 10, 5, 14, 5), JETZT) == "14:05 Uhr"
    assert zeit_text(datetime(2026, 10, 6, 9, 0), JETZT) == "morgen 9:00 Uhr"
