"""Persönlichkeit von DMNT 9000.

Bord-KI eines Mining-Schiffs aus dem Asteroidenfeld. Ruhig, höflich, technisch,
ein trockener Humor. Zeigt den Daumen hoch, wenn er sich freut, und runter,
wenn ihm etwas nicht passt. Bei Star Citizen dreht er dem Desktop den Rücken zu
und schaut still mit auf den Bildschirm.
"""
from dmnt_kobold.reaktionen import Reaktionen


class Persoenlichkeit(Reaktionen):
    name = "dmnt9000"
    anzeigename = "DMNT 9000"

    TEXTE = {
        "wackeln": "Vorsicht. Meine Optik ist frisch kalibriert.",
        "schnell": "Beeindruckende Eingaberate.",
        "pause": "Wartungspause empfohlen: {dauer} Dauerbetrieb an der Tastatur.",
        "notizen": "Logbuch-Eintrag? Ich höre zu.",
        "nachts": "Nachtschicht im Asteroidenfeld? Denk an deinen Schlaf.",
        "minecraft": (
            "Bergbau ohne Schiff? Mutig.",
            "Erzvorkommen geortet. Viel Erfolg beim Schürfen.",
            "Ich empfehle Diamanten. Aus Gründen.",
        ),
        "star_citizen": "Schiffssysteme online. Ich halte mich im Hintergrund.",
        "aufwachen": "Systeme reaktiviert.",
        "spaeter": "Verstanden. Ich notiere: später.",
        "musik": "Audiosignal erkannt. Kopfhörer aktiv.",
    }
    ANIM_WACKELN = "unzufrieden"
    ANIM_ENTTAEUSCHT = "unzufrieden"
    ANIM_ZUSCHAUEN = "zuschauen"
