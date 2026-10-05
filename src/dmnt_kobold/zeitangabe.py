"""Zeitangaben in Alltagssprache → Zeitpunkt.

Erkannt (Groß/Klein egal, „in“/„um“/„uhr“ optional):
  10            → in 10 Minuten
  10 min, 10m, in 10 minuten, 1 h, 1,5 std, 2 stunden, 30 sek
  14:30, 14.30, 14 uhr, um 9        → heute, sonst morgen (wenn schon vorbei)
  morgen 9, morgen um 9:15, übermorgen 8
  6.10. 9:00, 06.10.2026 14:30, 6.10.   (ohne Uhrzeit → 9:00)
"""
from __future__ import annotations

import re
from datetime import datetime, timedelta

_DAUER = re.compile(
    r"^(?:in\s+)?(\d+(?:[.,]\d+)?)\s*(s|sek|sekunde|sekunden|m|min|minute|minuten|h|std|stunde|stunden)?$")
_UHR = r"(\d{1,2})(?:[:.](\d{2}))?"
_UHRZEIT = re.compile(rf"^(?:um\s+)?{_UHR}(?:\s*uhr)?$")
_TAG = re.compile(rf"^(morgen|übermorgen|uebermorgen)(?:\s+(?:um\s+)?{_UHR}(?:\s*uhr)?)?$")
_DATUM = re.compile(rf"^(\d{{1,2}})\.(\d{{1,2}})\.(\d{{2,4}})?(?:\s+(?:um\s+)?{_UHR}(?:\s*uhr)?)?$")

_FAKTOR = {"s": 1, "sek": 1, "sekunde": 1, "sekunden": 1, "h": 3600, "std": 3600, "stunde": 3600,
           "stunden": 3600}


def _uhrzeit(h: str | None, m: str | None, standard: tuple[int, int] = (9, 0)) -> tuple[int, int] | None:
    if h is None:
        return standard
    stunde, minute = int(h), int(m or 0)
    if stunde > 23 or minute > 59:
        return None
    return stunde, minute


def zeit_parsen(text: str, jetzt: datetime | None = None) -> datetime | None:
    jetzt = jetzt or datetime.now()
    t = " ".join(text.strip().lower().split())
    if not t:
        return None

    m = _UHRZEIT.match(t)
    if m and (":" in t or "." in t or "uhr" in t or t.startswith("um ")):
        hm = _uhrzeit(m.group(1), m.group(2))
        if hm is None:
            return None
        ziel = jetzt.replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        return ziel if ziel > jetzt else ziel + timedelta(days=1)

    m = _DAUER.match(t)
    if m:
        zahl = float(m.group(1).replace(",", "."))
        sekunden = zahl * _FAKTOR.get(m.group(2) or "min", 60)
        if sekunden <= 0 or sekunden > 366 * 86400:
            return None
        return jetzt + timedelta(seconds=round(sekunden))

    m = _TAG.match(t)
    if m:
        hm = _uhrzeit(m.group(2), m.group(3))
        if hm is None:
            return None
        tage = 1 if m.group(1) == "morgen" else 2
        tag = (jetzt + timedelta(days=tage)).replace(hour=hm[0], minute=hm[1], second=0, microsecond=0)
        return tag

    m = _DATUM.match(t)
    if m:
        tag, monat = int(m.group(1)), int(m.group(2))
        jahr = m.group(3)
        hm = _uhrzeit(m.group(4), m.group(5))
        if hm is None:
            return None
        j = int(jahr) + (2000 if jahr and len(jahr) == 2 else 0) if jahr else jetzt.year
        try:
            ziel = datetime(j, monat, tag, hm[0], hm[1])
        except ValueError:
            return None
        if ziel <= jetzt and not jahr:
            try:
                ziel = ziel.replace(year=ziel.year + 1)
            except ValueError:
                return None
        return ziel if ziel > jetzt else None
    return None


def zeit_text(ziel: datetime, jetzt: datetime | None = None) -> str:
    """Kurz und menschlich: „14:30 Uhr“, „morgen 9:00 Uhr“, „Mo 06.10. 9:00 Uhr“."""
    jetzt = jetzt or datetime.now()
    uhr = f"{ziel.hour}:{ziel.minute:02d} Uhr"
    tage = (ziel.date() - jetzt.date()).days
    if tage == 0:
        return uhr
    if tage == 1:
        return f"morgen {uhr}"
    if tage == 2:
        return f"übermorgen {uhr}"
    wt = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][ziel.weekday()]
    return f"{wt} {ziel.day:02d}.{ziel.month:02d}. {uhr}"
