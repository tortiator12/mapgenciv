# Details nachschärfen auf dem eigenen Laptop (kostenlos)

Für: Laptop mit RTX 4090 (16 GB Grafikspeicher). Stand: 24.09.2026.
Modellnamen und Vorlagen ändern sich schnell. Wenn etwas anders heißt, nimm
das Nächstliegende und sag mir Bescheid.

## Was im Paket ist (pro Einstellung S1–S5)

| Datei | Wofür |
|---|---|
| `Sx_farbe_960x544_NNf.mp4` | unser Film ohne Malfilter; das wird nachgeschärft |
| `Sx_tiefe_960x544_NNf.mp4` | **exakte Tiefe aus der 3D-Szene** (hell = nah). Ersetzt die Tiefenschätzung im Workflow und hält Aufbau, Bewegung und Physik fest. |
| `Sx_startbild_960x544.png` | erstes Bild, z. B. als Referenz |
| `PROMPTS.md` | Prompts pro Einstellung (Englisch) |

960×544 und die Bildzahl 8k+1 (73, 65, 97, 193) passen zu beiden Modellen
unten. Ein paar Bilder am Ende sind nur Füllung; ich schneide sie nachher weg.

## Vorbereitung (einmalig, ca. 1 h, überwiegend Downloads)

1. **Arbeitsspeicher prüfen:** Task-Manager → Leistung → Arbeitsspeicher. Die „16 GB“ sind vermutlich der Grafikspeicher der 4090. Der normale Arbeitsspeicher sollte **32 GB oder mehr** haben, weil die Modelle teilweise dorthin ausgelagert werden.
2. Rund **60–100 GB** frei auf der SSD.
3. **ComfyUI Desktop** installieren (kostenlos, comfy.org) und den NVIDIA-Treiber aktualisieren.

## Weg 1, zuerst testen: LTX-2 „Detailer“ (nur nachschärfen)

Das Detailer-IC-LoRA von Lightricks verfeinert ein vorhandenes Video und
schärft Texturen nach, **ohne den Bildaufbau zu ändern**. Das passt am besten
zu dem, was im Film fehlt.

1. In ComfyUI: **Vorlagen/Templates → Video → LTX-2** (oder LTX-2.3 / 2.5) mit
   „IC-LoRA“ bzw. „Detailer“ öffnen. Fehlende Modelle bietet ComfyUI zum
   Download an. Für 16 GB wählst du:
   - die **FP8**- oder **GGUF-Q4/Q5**-Variante des Modells,
   - den **kleinen/quantisierten Text-Encoder** (Gemma FP4/FP8),
   - falls es eine Low-VRAM-Einstellung oder CPU-Offload gibt: einschalten.
2. Die Detailer-LoRA laden (`LTX-2-19b-IC-LoRA-Detailer` o. ä.), Stärke **0,5**, später auch 0,8.
3. Als Eingangsvideo `S1_farbe_960x544_73f.mp4` wählen. Auflösung 960×544, 73 Bilder, 24 fps.
4. Den Prompt „S1“ plus die „Klammer“ aus `PROMPTS.md` einfügen.
5. Als MP4 speichern und **nicht** hochskalieren. Ich brauche die Rohausgabe.

## Weg 2, stärker: mit unserer Tiefe neu bemalen

Wenn Weg 1 zu wenig bringt: eine Vorlage mit Tiefensteuerung, entweder
**„Wan VACE … Control/Depth“** oder **LTX-2 „Depth Control“ (IC-LoRA)**.

- Als Steuervideo `S1_tiefe_…mp4` direkt verwenden. Den Knoten „Depth Anything/Depth Estimation“ im Workflow **umgehen bzw. entfernen**, denn unsere Tiefe ist schon fertig und genauer.
- Optional das Startbild als Referenz oder erstes Bild. Tipp: Das Startbild vorher in Gemini (Bildbearbeitung) „mehr Details, gleiche Komposition“ veredeln lassen. Das kostet dich nichts extra.
- Wan: die **14B-VACE als GGUF Q4/Q5** oder für schnelle Tests die **1.3B**.
- Bei „out of memory“ zuerst 832×480 probieren, dann weniger Bilder.

## Reihenfolge

1. **S1** (Kai) mit Weg 1, Stärke 0,5 und 0,8: beide Ergebnisse an mich.
2. Wenn es taugt: S5 (Schiff), S3 (Statue), S4 (Feuer).
3. S2 (Zeitraffer, 193 Bilder) zuletzt oder gar nicht. Am Stück ist er zu lang für 16 GB; bei Bedarf teile ich ihn auf.

## Zurückschicken

Die MP4-Ausgaben unverändert. Am einfachsten auf GitHub hochladen: im Repo
`mapgenciv`, Branch `claude/alexandria-lighthouse-video-qv1p8h`, Ordner
`wonder_film/ki_rueckgabe/` → „Add file → Upload files“. Die Dateien sind
jeweils unter 25 MB. Ich prüfe dann automatisch gegen unseren Render
(Turm-Silhouette, verschmelzende Figuren, Flackern), gleiche die Farben an und
baue die besten Varianten in den Film ein.

## Grenzen (ehrlich)

- Auch mit fester Tiefe können kleine Figuren „verwaschen“ oder Details flackern. Deshalb prüfe ich jede Variante und nehme sonst unseren Render.
- Die Rechenzeit auf einer Laptop-4090 schätze ich auf Minuten bis etwa eine halbe Stunde pro Clip, je nach Modell und Schritten. Das ist nicht gemessen.
