# figur3d – DMNT 9000 aus dem 3D-Modell

Das Meshy-Modell hat kein Skelett. Darum:

1. `segment.py` zerlegt das Modell einmalig in Raute, Handschuhe, Schuhe (`web/labels.bin`, `web/parts.json`).
   Arme und Beine des Originals fliegen raus.
2. `web/rig.js` setzt die Teile wieder zusammen; Arme/Beine sind biegsame Schläuche (Rubber-Hose),
   dazu eine Faust mit Daumen, Transportbox, Mining-Pistole, Stein, Strahl, Funken, Brocken.
3. `web/anims.js` beschreibt jede Bewegung als Pose je Bild (8 Bilder). Hier dreht man an Posen.
4. `render.mjs` rendert (Chromium/WebGL, kein Fenster) nach `render/<anim>/`.
5. `streifen.py` zieht die Comic-Kontur, halbiert und schreibt die 8er-Streifen nach
   `quellen/dmnt9000_3d/` – danach wie immer `python werkzeuge/avatar_bauen.py quellen/dmnt9000_3d`.

Einmalig (lokal auf dem PC, PowerShell im Ordner `werkzeuge\figur3d`):

    npm install
    npx playwright install chromium

Modell liegt unter `quellen/dmnt9000_3d/modell/dmnt9000.glb` (nicht im Repo, siehe .gitignore).

Bauplan-Besonderheit: Die Quellen nutzen `"raster": true`, `"massstab": "fest"` und
`"fusspunkt": [190.5, 340]` (Boden unter der Figur in Zellen-Pixeln) – so bleiben die
8 Bilder einer Bewegung exakt deckungsgleich.
