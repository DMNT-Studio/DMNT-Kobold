# DMNT-Kobold

Ein Desktop-Begleiter für Windows. Ein kleiner Kobold lebt auf deiner Taskleiste,
läuft herum, lässt sich packen und werfen und fällt wieder herunter. Alles hinter
ihm bleibt normal anklickbar.

Stand: **M2 „Er reagiert"** – Platzhalter-Blob, Physik, alle Monitore, Rechtsklick-Menü, Tray-Icon,
Event-Bus, Verhaltensmotor, Sprechblase mit Knöpfen, Töne, Reaktionen auf Maus, Tippen, Leerlauf und Programme.

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

Grundsatz: Am Kobold gibt es nur, was ihn selbst betrifft. Alles, was das Programm betrifft, liegt im Tray.

- **Klick:** gehört dem Kobold – er reagiert nach seinem Wesen (Regel `maus.klick`), ohne passende
  Regel mit einem kleinen Hüpfer. Ein Klick öffnet nie das Einrichten.
- **Ziehen:** Kobold mit links packen und bewegen. Loslassen in Bewegung = werfen.
- **Rechtsklick:** nur sein Verhalten – Nicht stören, Auf diesem Monitor bleiben (mit Häkchen).
- **Tray-Icon** (unten rechts in der Taskleiste): Einrichten, Tricks (z. B. „Erinnern …“),
  Kobold zurückholen (auch per Doppelklick), Nicht stören, Beenden. Windows 11 versteckt neue
  Symbole im Überlaufmenü (Pfeil ^) – zum Anpinnen das Symbol auf die Taskleiste ziehen.
  Beim ersten Start sagt der Kobold einmal, wo das Symbol ist.

## Was er bemerkt (M2)

- **Maus in der Nähe:** schaut dich an und dreht sich zu dir. Wackeln erschreckt ihn.
- **Tippen:** setzt sich und wartet. Nach langer Tipp-Sitzung und Pause schlägt er eine Pause vor.
- **Leerlauf:** schläft nach 5 Minuten ein, wacht bei der nächsten Eingabe auf.
- **Programme:** freut sich über den Editor und Minecraft; bei Star Citizen geht er an den rechten Rand und schaut still zu.

Datenschutz: Es gibt **keine globalen Tastatur- oder Maus-Hooks**. Tippen wird nur daran erkannt,
dass Windows eine Eingabe meldet, während die Maus stillsteht. Welche Taste – das weiß das Programm nie.
Fenstertitel werden nur zur Programmerkennung gelesen und nie gespeichert oder geloggt.

Zum Ausprobieren: `$env:DMNT_KOBOLD_SCHNELLTEST="1"` verkürzt die Wartezeiten,
`$env:DMNT_KOBOLD_DEBUG="1"` schreibt die Ereignisnamen ins Log.

## Verhalten (für Avatar-Autoren)

Was ein Avatar tut, steht in `quellen/<id>/verhalten.json`: Regeln „Wenn … → Dann …“ und
Werte (z. B. Einschlafzeit, Laufgeschwindigkeit). Bearbeitet wird das im Avatar-Editor,
Reiter **Verhalten** (Werte, Regeln, Können). Der Bau prüft alles gegen den Katalog des
Sockels und bricht bei Fehlern mit Regel und Feld ab.

- Katalog aller Ereignisse, Aktionen und Werte: `python -m dmnt_kobold --katalog`
- Ohne eigene `verhalten.json` gilt `src/dmnt_kobold/standard_verhalten.json` (auch Vorlage).
- Sonderlogik, die sich nicht als Regel ausdrücken lässt, kommt in `persoenlichkeit.py`
  (Klasse `Persoenlichkeit`, ein `Modul` mit `SONDERLOGIK = [(Name, Beschreibung)]`) und läuft
  zusätzlich. Ein Avatar ohne `persoenlichkeit.py` ist „ohne Code“ – DMNT 9000 ist es.
- Endnutzer stellen weiterhin nur Name, Tricks und Lautstärke ein.

## Hüpf-Avatare (ab 0.6.0)

Aussehen steht im Bauplan, Temperament in den Werten – nichts doppelt.

- **Bewegung:** `bewegung.art` = `gehen`, `gleiten` oder `huepfen`. Hüpfer laufen nie: hocken →
  absprung → flug (echte Parabel) → landen → Pause. Weite, Höhe und Pausen sind Werte
  (`sprungweite_px`, `sprunghoehe_px`, `hupf_pause_min_s`/`_max_s`), die Form beim Stauchen und
  Strecken steht im Bauplan. Die Laufgeschwindigkeit ist nur noch der Wert `laufgeschwindigkeit`
  (`bewegung.tempo` gibt es nicht mehr – der Bau sagt es).
- **Aktionen:** `freuen_huepfend` (drei Hüpfer auf der Stelle mit einer Drehung) und `innen`
  (Variante des Innenlebens, z. B. `tnt@froh`, solange der Wunsch läuft).
- **Drehen:** Animation `drehen` mit fünf Ansichten, sonst Pseudo-Drehung.
- **Partikel und Körper-Töne** je Moment (Kern-Animation), z. B. Spritzer und Schmatzen beim
  Landen; Töne aus .wav/.ogg mit Tonhöhen-Streuung und Wiederholungen.
- **Innenleben:** Zubehör-Sitz „im Körper“, zwischen Rückwand und Körper, wackelt nach.
- Neuer Hüpf-Avatar: `python werkzeuge/avatar_bauen.py --vorlagen quellen/<name> [--innen <gegenstand>]`
  legt leere Rahmen, Bauplan, Start-Verhalten und LIESMICH an; Bilder dann im Avatar-Editor
  („Bilder“ → „Ersetzen“).
- Prüf-Figur (nur Entwickler): `python tests/daten/huepf_probe/zeichnen.py`,
  `python werkzeuge/avatar_bauen.py tests/daten/huepf_probe --ziel build/huepf_probe`,
  `python -m dmnt_kobold --avatar-pfad build/huepf_probe` (eigene Daten, läuft neben dem
  normalen Kobold; Einrichten und Beenden über sein Tray-Icon).

## Grenzen

- **Exklusives Vollbild:** Über Spielen im exklusiven Vollbild kann Windows kein Overlay
  zeigen. Im Fenster- oder Borderless-Modus ist der Kobold sichtbar.
- Daten: alles liegt in `Dokumente\DMNT-Kobold\` (daten, module, sicherungen, logs, cache). Jede Änderung wird sofort atomar geschrieben, täglich entsteht eine ZIP-Sicherung (7 Stück). Es werden keine Eingaben protokolliert.
- Tricks: „Erinnern“ (Strg+Alt+E oder Tray-Symbol) und „Pausen anmahnen“. Fremde Tricks laufen erst nach Zustimmung; die Zustimmung gilt für eine Prüfsumme und wird bei Änderungen erneut abgefragt.
- Einrichten: Tray-Symbol → Einrichten – Tricks, Lautstärke, Programme (Eingaben ignorieren), System (Autostart, Daten sichern/laden).
- Fehlersuche Durchklicken: Umgebungsvariable `DMNT_KOBOLD_OHNE_MASKE=1` schaltet die
  Fenstermaske ab.

## Lizenz

MIT – siehe [LICENSE](LICENSE).
