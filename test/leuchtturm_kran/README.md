# Leuchtturm v6: Kran-Vorlage (für Codex, Runway und Blender)

Ja, es gibt das Render-Skript samt Krananimation. Eine gespeicherte 3D-Szene (.blend) gab
es bisher nicht, weil die Szene bei jedem Rendern per Skript neu aufgebaut wird. Hier liegt
sie jetzt, exportiert aus genau diesem Skript, dazu die Krandaten pro Bild und S1 ohne die
Anfangsblende.

## Inhalt

| Datei | Was |
|---|---|
| `leuchtturm_S1_kran.blend` | Einstellung S1 (0–3 s, Bild 0–71) als Blender-4.5-Szene mit gekoppeltem Kran-Rig (unten). Im Repo lädt sie die Texturen aus `../../wonder_film/assets/`. Die Texturen liegen im Git, der Himmel (HDRI) nicht: `python wonder_film/fetch_hdri.py`. Im ZIP-Paket lädt sie alles aus `assets/` daneben (Teil 2). |
| `kran5_daten.csv` | der Kran am Kai (Kran 5, mit Tretrad) für alle 480 Bilder: Schwenk, Auslegerspitze, Seillänge, aufgewickeltes Seil, Last, Radwinkel, gekoppelter Radwinkel und Abweichung. Trennzeichen `;`. |
| `alle_kraene.csv` | alle sechs Kräne, alle 480 Bilder: Sichtbarkeit, Schwenk, Spitze, Seil, Last |
| `kran_geometrie.json` | Maße von Kran, Rad und Trommel, Einstellungen, Formeln |
| `s1_ohne_blende/` | S1 ohne Anfangsblende: Clip, Start-, Mittel- und Endbild, Tiefen- und Kantenvideo, Kranmaske (Video und PNG je Bild), außerdem der ganze Film ohne Blende mit Ton |
| `export_kran.py` | erzeugt die .blend, die CSVs und die JSON aus dem Original-Skript (`--pack` legt zusätzlich eine Fassung mit eingepackten Texturen an) |
| `mache_s1_material.py` | erzeugt `s1_ohne_blende/` |

## Wo die Krananimation im Original-Skript steht

Repo `mapgenciv`, Branch `claude/alexandria-lighthouse-video-qv1p8h`, Ordner `wonder_film/`:

- `film_lighthouse20.py`
  - `WHEEL_C`, `WHEEL_R`, `DRUM_R`: Radachse im Kranrahmen, Radradius 1,6 m, Trommelradius 0,25 m
  - `build_quay_crane()`: Kran mit Drehteller, Mast, Ausleger, Tretrad, Seiltrommel, Gegengewicht
  - `pose_treadwheel()`: Rad drehen, Männer ins Rad stellen
  - `shot_S1()`, Abschnitt „quay crane“: Schwenk, Hub, Pendel, Seil, Rad, Männer, Führungsleine
  - `pose()`: in S2 bis S5 `pose_treadwheel(S, 0.8 * v)`, dort dreht das Rad unabhängig vom Seil
- `scene.py`: `crane_mesh()` (Kran), Kräne anlegen (`S.cranes`), Kräne pro Bild in `pose()`
  (Lasten gehen dort mit `hop()` auf und ab)
- `render.py`: Rendern mit Cycles; `make_lighthouse20.sh`: der ganze Ablauf, darin die
  Anfangsblende `stylize.py --fade-in 0.35`

## Die Mechanik (S1 im Film und im Rig)

Ein einziger Wert treibt alles: **hub** = Seil, das seit Bild 0 auf die Trommel gewickelt wurde.

| Größe | Formel |
|---|---|
| Radwinkel | θ = θ₀ + hub / 0,25 m, also 1 m Hub = 4 rad = 229° |
| Seillänge | L = L₀ − hub |
| Lasthöhe | z = z₀ + hub |
| Gehgeschwindigkeit der Männer | v = 1,54 m · dθ/dt (Laufradius = Radradius − 6 cm) |
| Schrittphase | Gehzyklen = hub · 1,54 / (0,25 · 1,45) (1,45 m je Gehzyklus) |

Drehrichtung: θ dreht positiv um die lokale y-Achse. Unten läuft die Trittfläche nach hinten
(−x), die Männer schauen nach vorn zum Ausleger (+x) und stehen 0,3 m vor der tiefsten
Stelle. Ihr Gewicht dreht das Rad also in +θ, und das hebt die Last.

Im Film (S1): hub = 0,5 m · t / 3 s (etwa 0,17 m/s, typisch für Treträder), das Rad dreht
115° in 3 s, die Männer machen gut 2 Gehzyklen, der Kran schwenkt von 15° auf 60°. In
`kran5_daten.csv` ist die Abweichung in S1 deshalb 0 (höchstens 0,0001°).

## Das Rig in der .blend

- Objekt **`Kran5_Steuerung`** (Pfeil-Empty über dem Kran), Objekteigenschaften →
  Custom Properties:
  - `hub_m`: aufgewickeltes Seil in m
  - `schwenk_grad`: Schwenk des Krans um den Mast
  - `pendel_m`: Auslenkung der Last in Welt-x (wie im Film)

  Alle drei sind mit den Filmwerten Bild für Bild verkeyt (linear).
- Treiber, alle als einfache Ausdrücke, also ohne „Auto Run Python Scripts“:
  - `Crane5` Drehung z = radians(schwenk_grad)
  - `Treadwheel` Drehung y = hub_m / 0,25
  - `Load5` Position: z = z₀ + hub_m, x/y = Auslegerspitze + Pendel
  - `Kran5_Laeufer0_00…11` und `Kran5_Laeufer1_00…11`: je 12 Gehphasen, sichtbar ist die
    Phase, die zur Radstellung passt
- `Kran5_Seil` hängt per Stretch-To gespannt von der Auslegerspitze zum Lastbalken,
  `Kran5_Fuehrungsleine` genauso vom Mann auf dem Kai zur Last. Der Wimpel an der Spitze
  (`Pennant1`) fährt über `Kran5_Wimpelhalter` mit.
- **Nur die `hub_m`-Kurve ändern**, dann bleiben Rad, Seil, Last und Schritte mechanisch
  gekoppelt. Beispiel: schneller heben heißt steilere Kurve, und das Rad dreht automatisch
  schneller.
- Animiert sind nur Kran, Kamera (Fahrt wie im Film) und Sonne. Leute, Boote, Möwen, Rauch
  und Wasser sind auf dem Stand von Bild 0 eingefroren.
- Rendern: Cycles, 6 Samples + OIDN, 1280 × 720, Mehrschicht-EXR mit Tiefe und
  Objekt-Index nach `render/`. Der gemalte Look des Films kommt erst danach mit
  `wonder_film/stylize.py --look paint` und `stabilize.py`. Direkt aus der .blend sieht es
  daher „fotografischer“ aus.
- Geprüft: In Bild 0, 36 und 71 stimmen Schwenk, Radwinkel, Last, Seillänge, Spitze und
  Gehphase mit dem Film überein (Abweichung < 1 mm bzw. 0,001 rad). Testrenderings von
  Bild 36 und 71 aus der .blend decken sich beim Kran mit dem Film-Rendering.

## Bekannte Schwächen des Original-Modells

1. **S2 bis S5: Das Rad ist nicht gekoppelt.** Es dreht stur mit 0,8 rad/s, auch wenn die
   Last steigt, sinkt oder gar keine hängt, und es gehen keine Männer darin. Laut
   `kran5_daten.csv` weicht es in S2 um bis zu 1009° vom gekoppelten Winkel ab, in S3 um
   bis zu 1617°. In S4 und S5 ist der Kran abgebaut. Korrektur in `pose()`:
   θ(f) = θ(f₀) + (L(f₀) − L(f)) / 0,25 statt `0.8 * v`. Achtung: Im Zeitraffer S2 gehen
   die Lasten schnell auf und ab, das Rad würde dann mehrere Umdrehungen hin und her
   drehen. Das ist mechanisch richtig, wirkt aber unruhig.
2. Das Seil von der Trommel zur Umlenkrolle am Mastfuß ist fest ins Kranmodell gebaut.
   Es beginnt in der Achsmitte statt tangential an der Trommel und läuft durch den Bereich,
   in dem die Männer gehen. Eine sichtbare Seilwicklung auf der Trommel gibt es nicht.
3. Die „Trommel“ ist ein quadratischer Balken (0,5 × 0,5 m), keine runde Trommel.
4. Das Rad ist mit 3,2 m Durchmesser klein; historisch waren es 4 bis 6 m. Die Köpfe der
   Männer kommen der Achse sehr nahe, bis etwa 5 cm Überschneidung sind möglich.
5. Pendel: Im Film pendelt die Last 7,5 cm in Welt-x, das Seil bleibt aber senkrecht. Im
   Rig folgt das Seil der Last. Das ist physikalisch richtig und weicht nur minimal vom
   Film ab.
6. Beim Schwenken um 45° in 3 s müsste die Last etwas nachschwingen. Im Film gibt es nur
   die kleine Sinus-Pendelbewegung.

## Anfangsblende

Der Spielfilm blendet in 0,35 s aus Schwarz auf (`make_lighthouse20.sh`:
`stylize.py --fade-in 0.35`). Deshalb war in der ersten KI-Vorlage das Startbild
`S1_kai_start.png` schwarz, und der S1-Clip begann mit einer Schwarzblende. Das war ein
Fehler in der Vorlage. `s1_ohne_blende/` ersetzt ihn: gleiche Einstellung, gleicher Look,
ohne Blende. Ab Bild 12 ist es praktisch identisch mit v6 (mittlere Abweichung unter 0,1
von 255).

## Tipps für Runway (Aleph) und andere Video-zu-Video-Werkzeuge

- Nur `S1_kai_ohne_blende.mp4` verwenden, als Startbild `S1_kai_start.png`.
- Verbiegt oder verdreht das Werkzeug das Rad, dann die **Kranmaske** nehmen und nach dem
  Durchgang den Original-Kran wieder einsetzen: außen das Runway-Bild, innen das
  Originalbild, Kante 1 bis 2 px weich. Die Maske enthält Kräne, Rad, Seile und Lasten,
  aber nicht die Männer im Rad (die gehören zu den Arbeitern).
- Oder den Kran aus der .blend mit geänderter `hub_m`-Kurve neu rendern und einsetzen.
- Tiefen- und Kantenvideo taugen als Strukturvorgabe (z. B. Wan VACE, ComfyUI Depth/Canny).

## Neu erzeugen

```bash
# Daten und .blend (etwa 5 min; braucht bpy 4.5, numpy, OpenEXR und die Texturen)
python test/leuchtturm_kran/export_kran.py --out test/leuchtturm_kran [--pack]

# S1 ohne Blende (braucht die EXR-Renderings aus wonder_film/build/l20v6)
cd wonder_film
python stylize.py --inp build/l20v6 --out X/png --look paint --no-titles --frames 0,1,...,71
python stabilize.py --inp X/png --meta build/l20v6 --out X/png_stab --deflicker S2 --deflicker-frames 5
python ../test/leuchtturm_kran/mache_s1_material.py --frames X/png_stab --out ../test/leuchtturm_kran/s1_ohne_blende
```
