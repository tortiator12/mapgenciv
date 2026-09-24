# Leuchtturm-Film: Details mit KI-Video nachschärfen (Hybrid)

Stand: 24.09.2026. Idee: Die 3D-Szene liefert Aufbau, Kamera, Bewegung und
Physik. Ein Video-KI-Werkzeug malt nur Oberflächen und Details darüber. So
kommen Morphing und Physikfehler nicht zurück, weil die KI die Bewegung nicht
neu erfinden muss.

## 1. Welches Werkzeug?

Die Angaben zu den Werkzeugen sind mein Wissensstand und können sich geändert haben. Bitte kurz selbst prüfen.

| Werkzeug | Eingang | Passt, weil | Haken |
|---|---|---|---|
| **Luma „Modify Video“** (Ray2/Ray3) | unser Clip, bis ca. 10 s | Stufen „Adhere / Flex / Reimagine“: *Adhere* hält Bewegung und Aufbau fest und ändert nur die Oberfläche. Ausdrücklich auch für 3D-Rohrenders gedacht. | eigenes Abo |
| **Runway „Aleph“** | unser Clip, ca. 5 s pro Durchgang | Video-zu-Video-Bearbeitung per Text („mehr Details, gleiche Szene“) | eigenes Abo; S2 (8 s) nur in Teilen |
| **Veo 3.1** (Gemini/Flow) | nur **Bilder** (Start- und Endbild, bis 3 Referenzbilder) plus Text | Hast du schon. Gut bei „normalen“ Szenen mit Menschen, Wasser und Licht. | Nimmt (nach meinem Stand) kein fertiges Video zum Überarbeiten an. Die Bewegung zwischen Start- und Endbild erfindet Veo selbst, und genau dort entstehen Morphing und Physikfehler. |

**Empfehlung:** Für echtes Nachschärfen ein Video-zu-Video-Werkzeug mit
Strukturtreue (Luma *Adhere* oder Runway Aleph). Veo 3.1 nur für die
Einstellungen, in denen die Bewegung einfach ist (S1 Kai, S5 Schiff), und zwar
über Start- und Endbild.

## 2. Ablauf

1. **Ich liefere pro Einstellung:**
   - den Clip als MP4, 1280×720, **ohne Malfilter** (Rohbild, mehr Textur für die KI),
   - das Start- und das Endbild als PNG,
   - ein sauberes Referenzbild des fertigen Leuchtturms,
   - den Prompt unten.
2. **Du** lädst den Clip (oder bei Veo die Bilder) hoch, fügst den Prompt ein und erzeugst 2–3 Varianten. Die Ergebnisse schickst du mir.
3. **Ich prüfe jede Variante automatisch** gegen unser 3D-Bild: stimmt die Turm-Silhouette Bild für Bild, verschmelzen keine Figuren, hängt die Statue immer unter dem Seil, gibt es keine zusätzlichen Schiffe, keinen Text und kein Flackern? Dazu gleiche ich die Farben an unser Grading an.
4. **Ich schneide den Film neu zusammen:** Pro Einstellung nehme ich die beste KI-Variante oder, wenn keine besteht, unseren Render. Dazu kommen unser Ton, die Schnitte und die Ausgabe als OGV/MP4.

Einstellungen und Längen: S1 0–3 s · S2 3–11 s · S3 11–13,5 s · S4 13,5–16 s · S5 16–20 s.

**Einschätzung pro Einstellung:**
- **S1, S3, S5:** gute Kandidaten.
- **S4:** nur Stein und Feuer.
- **S2 (Zeitraffer, Block für Block):** am riskantesten. Nur mit der schwächsten Stufe oder gar nicht, denn KI-Modelle „glätten“ gern das stufenweise Wachsen und lassen den Turm dann wachsen wie beim Morphing.

## 3. Prompts (Englisch, damit arbeiten die Modelle zuverlässiger)

**Immer anhängen (Klammer):**

```
Keep exactly: the camera path, framing, timing, and the position and motion of every object and person.
Keep the lighthouse architecture unchanged: stepped stone podium, tall square lower tier with rows of
small windows, octagonal middle tier, round lantern with eight columns and a stepped dome, bronze statue
on top. Do not add or remove buildings, cranes, ships or people. No text, no logos, no watermark, no
modern objects. Ancient Alexandria, Egypt, about 280 BC. Bright, warm, richly detailed cinematic look
like a high-end strategy-game wonder video, natural light.
```

**S1 – Kai am Morgen (3 s, Echtzeit)**

```
Add realistic detail to this harbour scene: rough-hewn limestone blocks with chisel marks, chipped
edges and pale dust on the stone quay; wet dark stone and green algae at the waterline; a wooden cargo
barge with visible planks, tar, rope coils and wear; labourers in off-white and ochre linen tunics with
tanned skin, natural gait and posture; a crane of lashed timber with hemp ropes lifting a block; oxen
with hide texture pulling a wooden two-wheeled cart; seagulls; clear turquoise Mediterranean water with
small ripples and reflections; palm trees and white tents in the background.
```

**S2 – Zeitraffer (8 s), nur schwächste Stufe**

```
Time-lapse of an ancient construction site. Add surface detail only: texture on the limestone courses,
wooden scaffolding of lashed poles and planks, ropes and dust, torches glowing during the short night.
The tower must grow course by course exactly as in the input video: never add stones that are not
there, never change its height at any moment, no smooth growing. Clouds and shadows move as in the input.
```

**S3 – Statue wird aufgesetzt (2,5 s, goldene Stunde)**

```
Golden-hour close shot: a timber derrick crane lowers a bronze statue of Zeus holding a long sceptre
onto the stepped dome of the lantern. Give the statue realistic cast bronze with warm metallic
highlights and a draped cloak; give the crane weathered timber, iron fittings and taut hemp ropes; a
wooden scaffold around the lantern; workers on the roof hold guide ropes. The statue hangs vertically
under the crane tip at all times.
```

**S4 – Das Feuer wird entzündet (2,5 s, Sonnenuntergang)**

```
Sunset over the sea. The finished lighthouse stands without scaffolding. At the top an open wood fire
is lit and grows into bright flames with sparks and a little smoke drifting with the wind; warm light on
the upper tower, the first reflection of the fire on the water. Add weathered stone detail and gentle surf.
```

**S5 – Handelsschiff in der Nacht (4 s, Echtzeit)**

```
Blue hour, night harbour. A Hellenistic merchant ship with a single square linen sail, a curved
swan-neck stern post and two steering oars sails slowly past; sailors on deck haul the brail lines and
the sail gathers upward; an oil lantern glows at the stern and reflects on the dark water. Behind, the
lighthouse fire burns with a warm glow; small warm city lights of Alexandria on the horizon; first
stars. Add wooden planking, rope and sailcloth texture; calm, realistic waves.
```

**Nur für Veo 3.1 (Start- und Endbild statt Video):** vor den Prompt setzen:

```
Use the first image as the first frame and the second image as the last frame. The camera moves
smoothly and slowly between them; all motion is slow, real-time and physically plausible; nothing
appears, disappears or changes shape.
```

## 4. Einstellungen im Werkzeug

- Luma Modify Video: **Adhere 1–2**. Flex nur, wenn Adhere zu wenig Details bringt. Reimagine nie.
- Runway Aleph: den Prompt mit „Keep everything the same, only add detail:“ beginnen.
- Veo 3.1: 16:9, kürzeste passende Länge (4/6/8 s); ich schneide auf die Einstellungslänge. Den Veo-Ton ersetzen wir durch unseren Soundtrack.
- Keine Aufwertung auf 4K im Werkzeug; das machst du später mit deinem Upscaler.
