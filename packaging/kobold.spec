# PyInstaller-Bauplan für DMNT-Kobold (onedir, Fenster-App ohne Konsole).
# Aufruf über packaging/bauen.ps1 – nicht von Hand nötig.
#
# Mitgepackt werden nur Dateien, die in Git stehen (git ls-files). So kommen lokale
# Avatare wie Sulfi (Minecraft-Figur, nur lokal) oder halbfertige Arbeit nie in ein
# Release. Sulfi und Flugzeug mit eigenem Körperbild sind zusätzlich hart ausgeschlossen.
import subprocess
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

WURZEL = Path(SPECPATH).parent
PAKET = WURZEL / "src" / "dmnt_kobold"
AUSGESCHLOSSEN = ("avatare/sulfi/", "avatare/flugzeug_lokal/")


def paketdateien():
    """(Quelle, Zielordner) für alle Nicht-Code-Dateien des Pakets und die dynamisch
    geladenen .py (persoenlichkeit.py der Avatare, modul.py der Tricks)."""
    try:
        aus_git = subprocess.run(["git", "ls-files", "src/dmnt_kobold"], cwd=WURZEL, check=True,
                                 capture_output=True, text=True).stdout.splitlines()
        dateien = [WURZEL / p for p in aus_git]
    except (OSError, subprocess.CalledProcessError):
        dateien = [p for p in PAKET.rglob("*") if p.is_file()]
    ergebnis = []
    for datei in dateien:
        rel = datei.relative_to(PAKET).as_posix()
        if "__pycache__" in rel or any(rel.startswith(a) for a in AUSGESCHLOSSEN):
            continue
        dynamisch = rel.startswith(("avatare/", "tricks/"))
        if datei.suffix == ".py" and not dynamisch:
            continue                                  # normaler Code kommt über die Analyse
        if not datei.exists():
            continue
        ergebnis.append((str(datei), str(Path("dmnt_kobold") / Path(rel).parent)))
    return ergebnis


a = Analysis(
    [str(WURZEL / "packaging" / "start.py")],
    pathex=[str(WURZEL / "src")],
    datas=paketdateien(),
    hiddenimports=collect_submodules("dmnt_kobold") + ["PySide6.QtNetwork", "PySide6.QtSvg"],
    excludes=["tkinter", "numpy", "scipy", "PIL", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="DMNT-Kobold",
    console=False,
    icon=str(WURZEL / "packaging" / "kobold.ico"),
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="DMNT-Kobold")
