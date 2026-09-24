# The Great Lighthouse — a wonder time-lapse

A 30-second, Civilization-VI-style "wonder completed" film: the Pharos of
Alexandria rising course by course on its headland, in a dark, comic-realistic
look. Everything is generated from code. There are no models, textures or
samples, only two SIL-OFL fonts for the titles.

**Output:** `great_lighthouse_timelapse.mp4`: 1280×720, 24 fps, H.264 + AAC stereo, 30 s.

## What happens

| video time | time-lapse clock | construction |
|---|---|---|
| 0–1.4 s | pre-dawn → sunrise | survey stakes and ropes mark out the podium; caption *Pharos · Alexandria* |
| 1.0–4.6 s | morning | the stepped stone podium is laid, block by block |
| 4.4–14.8 s | day 1 → night → day 2 | the square first tier (≈56 m, 40 courses) with windows, great door, core shaft and floors; a climbing putlog scaffold and two derricks ride up with the work; work slows to a crawl at night, by torchlight |
| 14.5–15.6 s | afternoon | stepped cornice, roof slab, crenellated parapet, the four bronze Tritons |
| 15.4–20.6 s | day 2 → night → day 3 | the octagonal second tier (≈27 m); tier-1 scaffold is struck top-down |
| 21.0–22.8 s | day 3 | drum, eight-column lantern, entablature, stepped dome |
| 22.6–23.6 s | golden hour | a tall derrick hoists the bronze Zeus Soter onto the dome |
| 23.4–24.9 s | sunset | remaining scaffold and cranes come down |
| 25.4 s | night | the beacon is lit |
| 26.2–30 s | night | "Wonder completed: The Great Lighthouse" and the Pharos's dedication inscription |

Throughout, clouds and cloud shadows race over land and sea, the sun and moon
swing the shadows round, stone barges shuttle to the quay, ships cross the
Great Harbour, and Alexandria's lights come on across the water every night.

## How it is made

| file | role |
|---|---|
| `timeline.py` | Shared timing: construction phases, the time-lapse clock (video seconds → hour of day), sun and moon geometry for Alexandria, and a daylight-weighted work rate. |
| `geometry.py` | numpy generators: ashlar courses for tapered square, octagonal and round ring walls (staggered joints, window and door openings), slabs, beams, heightfields, a radial-LOD sea mesh. |
| `scene.py` | Blender (bpy) scene: materials (per-block tone, mortar joints from per-face UVs), procedural sky (gradient, sun glow, 2-D cloud deck, moon), Ocean-modifier sea with surf foam, the island, Alexandria, props, cranes, workers, ships, beacon; `pose(t)` sets everything for a given instant. The masonry and scaffolding are rebuilt each frame from timed elements, so the building grows block by block. Nothing morphs. |
| `render.py` | Cycles CPU render per frame: an OIDN-denoised beauty EXR, plus a 1.5× depth/normal/object-id pass turned into ink lines. |
| `lines.py` | Ink extraction: inverse-depth Laplacian (silhouettes), normal creases, object-id contacts, distance-weighted pen. |
| `stylize.py` | Graphic-novel look: haze, auto-exposure (darker at night), glow and beacon god rays, ACES tone map, Kuwahara paint, soft cel banding, spot blacks, halftone screen, inks, split-tone grade, stars that turn about the celestial pole, vignette, paper and grain. |
| `titles.py` | Opening caption and end card (Cinzel / Cormorant Garamond). |
| `audio.py` | Synthesized score and sound design (numpy/scipy): a D-Phrygian frame-drum groove whose A7(b9) → D-major cadence lands on the ignition, oud-like Karplus-Strong ostinato, pads, choir, gong; sea, wind, chisels, crickets, fire. |
| `make_film.sh` | Runs the whole pipeline. |

### Build

```bash
python3.11 -m venv venv && venv/bin/pip install -r wonder_film/requirements.txt
# Linux headless: apt install ffmpeg libegl1 libegl-mesa0
PYTHON=venv/bin/python wonder_film/make_film.sh            # all 720 frames
PYTHON=venv/bin/python wonder_film/make_film.sh --skip-existing   # resume
# quick look: a few low-res frames
venv/bin/python wonder_film/render.py --out /tmp/prev --frames 120,360,650 --res 640x360 --spp 4
venv/bin/python wonder_film/stylize.py --inp /tmp/prev --out /tmp/prev_png
```

On a 4-core CPU (no GPU), a frame takes about 10–15 s, so the whole film takes a
couple of hours.

## Historical basis

- Built c. 280–247 BC under the first Ptolemies. The architect was
  Sostratus of Cnidus. It stood on the eastern tip of Pharos island, across
  the Great Harbour from Alexandria, joined to the city by the Heptastadion
  causeway (also in the film).
- The shape follows the classic reconstruction (H. Thiersch, 1909) and the
  measurements of Ibn al-Shaykh: a stepped podium, a slightly battered
  square tier of about 56 m, an octagonal tier of about 27 m and a round
  lantern, about 105–110 m in all. Tritons stand on the corners of the first
  cornice, and a bronze Zeus Soter tops the dome.
- The quote on the end card is the dedication that Sostratus is said to
  have carved into the stone (Strabo 17.1.6; Lucian, *How to Write History*
  62): *"Sostratus of Cnidus, son of Dexiphanes, to the Saviour Gods, on
  behalf of those who sail the seas."*

The fonts in `assets/fonts` are Cinzel and Cormorant Garamond, both under the
SIL Open Font License (licence texts included). Everything else is original code.
