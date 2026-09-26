# The Great Lighthouse — a wonder time-lapse

A 30-second, Civilization-VI-style "wonder completed" film: the Pharos of
Alexandria rising course by course on its headland, in a dark, comic-realistic
look. Everything is generated from code. There are no models, textures or
samples, only two SIL-OFL fonts for the titles.

**Output:** [`great_lighthouse_timelapse.mp4`](great_lighthouse_timelapse.mp4): 1280×720, 24 fps, H.264 + AAC stereo, 30 s (22 MB).

![The Great Lighthouse, finale](poster.jpg)

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

The film in this folder was rendered on a 4-core CPU with no GPU: 6 samples per
pixel plus OIDN, about 10 s per frame with two render processes, so roughly 2 h
for all 720 frames. Stylizing takes about 3 min with 4 processes, and the
encode about 1 min (`-crf 22 -tune film`).

## Civ1 game film: *Der Leuchtturm* (20 s)

The same scene, re-cut as a 20-second wonder film for the Civ1 remake
(`wunderfilm_04_lighthouse`, storyboard in
[`storyboards/runde1_fehlende_wunder.md`](storyboards/runde1_fehlende_wunder.md)).
It uses the bright, painterly look of the other game films and has no text in
the picture, because the game shows the title and year itself.

| shot | time | what you see | clock |
|---|---|---|---|
| S1 | 0–3 s | the quay on Pharos, morning: a treadwheel crane swings a block off a lighter, a team drags a sledge with the rope over their shoulders, masons dress blocks, a scribe counts under an awning, water carriers, a rowing boat pulls away, smoke from the camp, ox carts, gulls | real time |
| S2 | 3–11 s | slow orbit: podium → square tier → octagon → lantern; scaffolds climb and are struck, derricks lift; crowds on the podium, sledge teams and carts on beaten tracks, boats offshore; one short night by torchlight | time-lapse |
| S3 | 11–13.5 s | golden hour at the lantern: a guyed derrick lifts the bronze Zeus Soter, slews it over the dome and lowers it; men on the roof and the lantern scaffold steady and receive it; gulls, boats far out | slow time-lapse |
| S4 | 13.5–16 s | sunset, scaffolding gone: the beacon is lit, its smoke drifts downwind; people on the podium, boats coming home | time-lapse |
| S5 | 16–20 s | blue hour: a merchantman with a swan-neck stern and a stern lantern brails up its sail on the way into the Great Harbour; lamp-lit rowing boats, ships at anchor, fire-lit smoke over the beacon, Alexandria's lights on the horizon | real time |

| file | role |
|---|---|
| `film_lighthouse20.py` | The edit: per-shot clocks (construction time, hour, animation), cameras, and the extras only this film needs: walk-cycle people with tunics, yoked ox carts with turning wheels, gulls, a sledge team, the hero ship with a brailed sail. |
| `scene.py` | Shared with the 30-s film. `build(look='bright', derrick=True)` selects the sunny palettes, cumulus sky, ashlar quay and the detailed statue. `pose(S, t, **clocks)` takes separate clocks, and with no keywords it gives exactly the 30-s film. |
| `stylize.py --look paint` | Aerial haze, filmic tone curve, soft Kuwahara paint with the detail sharpened back in, bloom and beacon glow, warm grade. Auto-exposure is smoothed within each shot and never across a cut. |
| `audio_lighthouse20.py` | Lyre alone at the quay; frame drum, plucked ostinato and chisels for the time-lapse; crickets in the night; an aulos over the statue; A7(b9) → D major with boom, gong and choir exactly when the fire catches (14.0 s); waves, creaking timber and a sailor's call at the end; oar strokes in step with the rowing boats and mallet blows on the masons' down-swings. Mean level −24 dB, like the other game films. |
| `life.py` | Life around the site: rowing boats whose oars follow the rowers (blade in the water only on the drive), small sailing boats running before the wind, ships at anchor with lamps, billboard smoke that rises, spreads and thins, pennants, the quay's clutter, masons' sheds, chip heaps and mortar pits. One wind (the Etesian NNW) for smoke, pennants and sails. |
| `stabilize.py` | Temporal stabilisation after stylize: each frame is blended with the previous result warped by optical flow, only where the two agree, so shimmer is averaged away and real motion passes through. Resets at every cut. |
| `make_lighthouse20.sh` | Render → stylize → stabilise → soundtrack → MP4 (H.264) and OGV (Theora/Vorbis, for Godot). |

Detail pass (no extra cost): photographed CC0 textures from Poly Haven, fetched
by `fetch_textures.py` into `assets/textures/` (weathered planks for hulls and
decks, linen for the sail, natural limestone on every block face, sand on the
ground, rough timber on scaffolds and cranes). Each is mapped at its real size
and only adds detail, so the palette keeps the colours. Close shots also get a
treadwheel-driven quay crane, planked stone lighters, and people with tunics,
belts, hair or head cloths, and baskets.

The look follows the game's other wonder films (painted, but realistic): a
photographed day sky full of cumulus (CC0, Poly Haven; `fetch_hdri.py`
downloads it and removes its sun, because our own sun lamp keeps lighting the
scene by the film's clock). The sky is re-lit by the ratio of our sky colours
at the current hour to midday, so in the time-lapse the same clouds turn
golden at sunset, dark at night and pink at dawn. Materials are warm (cream
limestone, ochre ground), the quay is shot at an early golden hour, and
`stylize.py` grades in Lab (warm shift per shot, calmer blues, S-curve,
clarity) with a fixed painted-canvas grain. The night shot keeps its colours.

And a working site is not clean: every upward stone face carries
sand-coloured dust (and sand in its joints), trodden darker patches and
vertical stains mark the walls, arrises are worn and dirty, the harbour
walls are wet with a band of algae at the waterline, timber silvers, jars
are dusty, the quay slabs have settled unevenly and collect chips, straw,
shards and rope ends; stone dust rises at the masons' chisels and behind the
sledges and carts, and a warm haze lies over the island by day.

The worst flicker came from the scene build itself: every block, pole and
plank drew its colour tone from an unseeded random generator, and since even
and odd frames are rendered by two processes, every stone changed its shade
12 times a second. Tones are now hashed from the element's index; a frame
renders bit-identically in any process.

Against flicker: Cycles does not mip-map image textures, so every texture has
pre-filtered 256 px and 64 px copies and the material picks the level from
the pixel footprint (distance × pixel angle). Mortar joints, cart ruts, stone
chips and far window lights fade to their mean tone once they are thinner
than a pixel. The time-lapse clocks for people, loads, clouds and water run
calmer, there is no film grain, and `stabilize.py` removes what is left
(flow-compensated flicker −60 to −66 % against the previous version).

Figures: besides walking, carrying and hauling, the people drag sledge ropes
over the shoulder, dress stone with mallet and chisel, sit, write, point,
carry amphorae, pour water, carry torches and row (elbows and knees by IK).

Physics notes: the statue always hangs plumb under the boom tip, and the tip
is high enough (boom heel 6 m up the mast, so the boom clears the lantern
scaffold). The derrick's guys are anchored on the octagon roof and on the
first terrace, and the derrick never lowers a load into the lantern. The
beacon is an open fire. There is no rotating beam.

```bash
PYTHON=venv/bin/python wonder_film/make_lighthouse20.sh               # all 480 frames (~2.5 h on 4 cores)
venv/bin/python wonder_film/render.py --film lighthouse20 --out /tmp/l20 --frames 30,200,300,420 \
    --res 640x360 --no-lines                                              # quick look
venv/bin/python wonder_film/stylize.py --inp /tmp/l20 --out /tmp/l20png --look paint --no-titles
```

## Civ1 game film: *Koloss von Rhodos* (20 s)

`wunderfilm_03_colossus`, the second film of the storyboard, in the same look
as the lighthouse, but a world of its own (`rhodes.py`): the harbour of
Rhodes with its moles and ship sheds, the town on the grid of Hippodamus with
tiled roofs, cypresses, pines and olives on the hills, the temple of Helios on
the acropolis.

| shot | time | what you see | clock |
|---|---|---|---|
| S1 | 0–3 s | the harbour mole, morning: a merchantman alongside and a lighter at the treadwheel crane unload copper; copper and tin ingots, bundles of iron bars and the broken-up siege engines of Demetrios (squared timbers, the great wheels, iron armour plates) on the mole; a smithy smokes, ox carts, a scribe, rowing boats, gulls | real time |
| S2 | 3–8 s | slow orbit: the marble pedestal course by course, then the legs on their iron frame, weighted with stone; the mound of earth rises round the figure layer by layer with a spiral ramp, carriers and carts on the ramp, trestles and furnaces on its top; a short night of forge fires and torches | time-lapse |
| S3 | 8–11.5 s | on the top of the mound, afternoon: two shaft furnaces with glowing mouths and bag bellows, charcoal, a stack of plates; the bronze head with the hand shading the eyes rises from the earth, the last plates go on the top of the head from the scaffold behind it | real time |
| S4 | 11.5–15 s | from the sea: the scaffold is struck, then the mound is carried away in baskets, top first, and the Colossus appears from the head down | time-lapse |
| S5 | 15–20 s | sunset: a merchant galley rows past towards the harbour mouth, a sacrifice burns on the altar before the pedestal, gulls | real time |

The statue is sculpted, not skinned: `sculpt.py` blends 83
primitives (tapered limbs, muscle masses, a Greek profile, curls, pipe
folds of the chlamys) with smooth minima into one signed-distance field and
extracts the surface with marching cubes. `helios.py` derives everything
else from that field: bronze plates in horizontal courses of 1.2 m (Voronoi
cells along each course, so the vertical joints stagger), a seam distance and
a tone per plate for the shader (dark joints, rivet rows, hammered sheet),
the iron armature (rings of the cross-sections 0.28 m inside the skin, joined
by uprights) and the stone fill in the legs and the drapery. The result is
cached in `build/cache`.

How it was built, after Philon of Byzantium: the figure was cast part by part
from the feet up, and earth was heaped round it so that the work always stood
on the top of the mound; when it was finished, the mound was taken away. In
the film the mound is a fixed cone (55°, held by timber cribs every 1.6 m)
filled in 1-m layers, with a spiral ramp at 1 : 7 cut into its flank; its top
stays 4 m below the finished bronze (trestles bridge the gap), and it stops
at the chest, where a scaffold behind the head takes over. The mound comes
down in whole layers, top first, the scaffold before it.

Deliberate correction: the Colossus did not straddle the harbour mouth (a
medieval legend, and impossible for the statics). Here it stands on the head
of the mole, legs close together, with the cloak falling to the base as a
third support, and looks out to sea.

```bash
PYTHON=venv/bin/python wonder_film/make_colossus20.sh                 # all 480 frames
venv/bin/python wonder_film/render.py --film colossus20 --out /tmp/c20 --frames 36,120,230,330,420 \
    --res 640x360 --no-lines                                              # quick look
venv/bin/python wonder_film/stylize.py --inp /tmp/c20 --out /tmp/c20png --look paint --no-titles --film colossus20
```

## Civ1 game film: *Kopernikus' Observatorium* (20 s)

`wunderfilm_10_copernicus`, the third film of the storyboard, in a world of
its own (`frombork.py`): the cathedral hill of Frombork (Frauenburg) above the
Vistula Lagoon at 54.4° N, the brick cathedral with its buttresses, the walls
of the close with towers and the south gate, the canons' houses, the town on
the terrace below, farmland, groves and dark stands of pine. For the game the
wonder is a brick observation tower at the south-west corner of the close
(after the "Copernicus tower"), with a flat platform and a parapet.

| shot | time | what you see | clock |
|---|---|---|---|
| S1 | 0–3 s | a late-autumn morning: two brick kilns smoke in the foreground, ox carts bring bricks up the road to the works at the corner of the close, the cathedral above, the lagoon beyond | real time |
| S2 | 3–9 s | the tower rises lift by lift in its scaffold, a treadwheel crane on the wall top swings its loads up from the works (pallets, mortar trough, lime pit, the masons' lodge); parapet and merlons, the scaffold struck from the top; sun and cloud shadows pass | time-lapse |
| S3 | 9–12.5 s | the workshop, slanting morning light: the carpenter planes the rules of the triquetrum at the window, Copernicus at his table with parchments, candles and a small armillary sphere | real time |
| S4 | 12.5–15.5 s | sunset, from the platform's north-east corner: the armillary sphere, the triquetrum and the quadrant are set up one after another, two carpenters at work, Copernicus at the sphere | time-lapse |
| S5 | 15.5–20 s | night: Copernicus, a silhouette on a step at the eye end of the triquetrum, sights the moon rising in the east-north-east; a reading lantern at his feet; the camera tilts up into the stars turning round the pole, 54° up | time-lapse |

The instruments follow *De revolutionibus* (1543): the triquetrum (Ptolemy's
parallactic rulers; post and sighting rule both 2.2 m, the graduated lower
rule reads the chord of the zenith distance), a quadrant in the meridian and
an armillary sphere with its pole axis at the latitude of Frombork
(`instruments.py`). Because the sighting rule is hinged at the top of the
post, the eye end stands about 2 m high for a moon 8–13° up; Copernicus
stands on a step. The people close to the camera are sculpted like the
Colossus (`figures.py`: a canon's Schaube with fur collar and beret,
carpenters in jerkins and aprons, two-bone arms); farther away the skinned
figures of the lighthouse film work as before.

Sky and time: late autumn, the sun at −9° declination (sunrise about 07:10,
sunset about 17:10). The moon, two days past full at +12°, rises at 19:00 in
the ENE (azimuth 69°) and climbs to 13° by 20:30, as it must at this latitude.
The star trails in S5 are drawn by the stylizer (`star_trail`: hours of
exposure behind each star, rotated about the celestial pole of the film's
latitude); `sky_glow` and `moon_halo` keep the moon a small disc.

```bash
PYTHON=venv/bin/python wonder_film/make_copernicus20.sh               # all 480 frames
venv/bin/python wonder_film/render.py --film copernicus20 --out /tmp/k20 --frames 30,150,260,330,450 \
    --res 640x360 --no-lines                                              # quick look
venv/bin/python wonder_film/stylize.py --inp /tmp/k20 --out /tmp/k20png --look paint --no-titles --film copernicus20
```

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
