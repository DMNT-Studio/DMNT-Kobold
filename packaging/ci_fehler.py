"""Macht fehlgeschlagene Tests in GitHub Actions als Anmerkung sichtbar (::error::).

So stehen die Fehler direkt in der Übersicht eines Laufs, ohne die Logs zu öffnen.
Aufruf in CI nach pytest --junitxml=build/tests.xml:  python packaging/ci_fehler.py build/tests.xml
"""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


def zeile(text: str) -> str:
    return text.replace("%", "%25").replace("\r", "").replace("\n", "%0A")


def main() -> None:
    datei = Path(sys.argv[1] if len(sys.argv) > 1 else "build/tests.xml")
    if not datei.exists():
        print("::error::Keine Testergebnisse gefunden (pytest lief nicht bis zum Ende)")
        return
    anzahl = 0
    for fall in ET.parse(datei).getroot().iter("testcase"):
        for art in ("failure", "error"):
            f = fall.find(art)
            if f is None:
                continue
            anzahl += 1
            name = f"{fall.get('classname', '')}::{fall.get('name', '')}"
            text = (f.get("message") or "") + "\n" + "\n".join((f.text or "").splitlines()[-25:])
            print(f"::error title={zeile(name)}::{zeile(text.strip()[:3000])}")
            if anzahl >= 10:
                return


if __name__ == "__main__":
    main()
