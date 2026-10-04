"""Event-Bus: Beobachter senden abstrahierte Ereignisse, Module und
Persönlichkeit hören zu.

Muster: exakter Name ("maus.klick"), Präfix ("maus.*") oder alles ("*").
Fehler in einem Abonnenten werden abgefangen und geloggt; hat der Besitzer
eine Methode ``bei_fehler()``, wird sie aufgerufen (Modul deaktiviert sich).
Ereignisdaten werden nie geloggt (können z. B. Fenstertitel enthalten).
"""
from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Callable

log = logging.getLogger(__name__)
DEBUG = os.environ.get("DMNT_KOBOLD_DEBUG") == "1"


@dataclass(frozen=True)
class Ereignis:
    name: str
    daten: dict[str, Any] = field(default_factory=dict)
    zeit: float = field(default_factory=time.monotonic)


Rueckruf = Callable[[Ereignis], None]


def passt(muster: str, name: str) -> bool:
    if muster == "*" or muster == name:
        return True
    return muster.endswith(".*") and name.startswith(muster[:-1])


class EventBus:
    def __init__(self) -> None:
        self._abos: list[tuple[str, Rueckruf, object]] = []

    def abonnieren(self, muster: str, rueckruf: Rueckruf, besitzer: object = None) -> None:
        self._abos.append((muster, rueckruf, besitzer))

    def abbestellen(self, besitzer: object) -> None:
        self._abos = [a for a in self._abos if a[2] is not besitzer]

    def senden(self, name: str, /, **daten: Any) -> Ereignis:
        e = Ereignis(name, daten)
        if DEBUG:
            log.info("Ereignis %s", name)
        for muster, rueckruf, besitzer in list(self._abos):
            if not passt(muster, name):
                continue
            try:
                rueckruf(e)
            except Exception:  # noqa: BLE001 – ein Abonnent darf den Rest nie stören
                log.exception("Fehler bei Ereignis %s in %r", name, besitzer or rueckruf)
                bei_fehler = getattr(besitzer, "bei_fehler", None)
                if callable(bei_fehler):
                    try:
                        bei_fehler()
                    except Exception:  # noqa: BLE001
                        log.exception("bei_fehler fehlgeschlagen")
        return e
