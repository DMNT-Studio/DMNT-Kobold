# DMNT-Kobold

Ein Desktop-Begleiter für Windows. Ein kleiner Kobold lebt auf deiner Taskleiste,
läuft herum, lässt sich packen und werfen und fällt wieder herunter. Alles hinter
ihm bleibt normal anklickbar.

Stand: **M1 „Er lebt"** – Platzhalter-Blob, Physik, alle Monitore, Rechtsklick-Menü, Tray-Icon.

## Starten (PowerShell, lokal)

```powershell
cd dmnt-kobold
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e .[dev]
python -m dmnt_kobold
```

Tests: `pytest`

## Bedienung

- **Ziehen:** Kobold mit links packen und bewegen. Loslassen in Bewegung = werfen.
- **Klick:** kleiner Hüpfer.
- **Rechtsklick:** Menü (Nicht stören, Auf diesem Monitor bleiben, Beenden).
- **Tray-Icon:** Notausgang – „Kobold zurückholen" setzt ihn auf den Hauptmonitor (auch per Doppelklick).

## Grenzen

- **Exklusives Vollbild:** Über Spielen im exklusiven Vollbild kann Windows kein Overlay
  zeigen. Im Fenster- oder Borderless-Modus ist der Kobold sichtbar.
- Daten: Logs liegen in `%APPDATA%\DMNT-Kobold\logs\`. Es werden keine Eingaben protokolliert.
- Fehlersuche Durchklicken: Umgebungsvariable `DMNT_KOBOLD_OHNE_MASKE=1` schaltet die
  Fenstermaske ab.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
