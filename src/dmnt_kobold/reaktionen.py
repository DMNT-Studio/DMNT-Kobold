"""Standard-Persönlichkeit: Grundreaktionen für Avatare ohne eigene ``verhalten.json``
(z. B. den Platzhalter-Blob).

Die Regeln stehen in ``standard_verhalten.json`` und werden wie bei jedem Avatar von
``regeln.RegelPersoenlichkeit`` ausgewertet. Die Datei ist zugleich die Vorlage für
neue Avatare.

Zum schnellen Ausprobieren: Umgebungsvariable ``DMNT_KOBOLD_SCHNELLTEST=1``
verkürzt die Wartezeiten (Tipp-Sitzung 10 s statt 60 s, Leerlauf 1 statt 5 min,
Abklingzeiten durch 30).
"""
from __future__ import annotations

import random

from . import katalog
from .regeln import RegelPersoenlichkeit, standard_verhalten

LANGE_SITZUNG_S = katalog.standard("lange_tippsitzung_s")
SCHLAF_NACH_MIN = katalog.standard("einschlafen_nach_min")


class Reaktionen(RegelPersoenlichkeit):
    name = "reaktionen"
    anzeigename = "Reaktionen"

    def __init__(self, bus, motor, rng: random.Random | None = None) -> None:
        super().__init__(bus, motor, standard_verhalten(), rng)
