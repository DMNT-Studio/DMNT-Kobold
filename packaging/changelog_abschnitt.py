"""Schreibt den Abschnitt einer Version aus CHANGELOG.md in eine Datei (Release-Text).

Aufruf: python packaging/changelog_abschnitt.py v0.7.0 build/release_text.md
Vorab-Versionen (v0.7.1-test.1) nehmen den Abschnitt ihrer Grundversion, falls es ihn gibt.
"""
import re
import sys
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent

FUSS = """
---
**Herunterladen:** `DMNT-Kobold-Setup.exe` (Installation ohne Admin-Rechte) oder
`DMNT-Kobold-Portable.zip` (ohne Installation). Prüfsummen in `SHA256SUMS.txt`.
Schon installiert? Der Kobold meldet sich von selbst mit „Aktualisieren“.
"""


def abschnitt(text: str, version: str) -> str | None:
    muster = re.compile(rf"^## \[?{re.escape(version)}\]?.*?$(.*?)(?=^## |\Z)", re.M | re.S)
    m = muster.search(text)
    return m.group(1).strip() if m else None


def main() -> None:
    tag, ziel = sys.argv[1], Path(sys.argv[2])
    version = tag.lstrip("v")
    text = (WURZEL / "CHANGELOG.md").read_text(encoding="utf-8")
    inhalt = abschnitt(text, version) or abschnitt(text, version.split("-")[0])
    if inhalt is None:
        inhalt = "Testversion." if "-" in version else f"Version {version}."
    if "-" in version:
        inhalt = f"**Vorab-Version zum Testen.**\n\n{inhalt}"
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_text(inhalt + "\n" + FUSS, encoding="utf-8")
    print(f"Release-Text für {version}: {len(inhalt)} Zeichen")


if __name__ == "__main__":
    main()
