"""
Civilization 1 map generator, ported from OpenCivOne.

Source: src/Game/CodeObjects/MapInitAndIntro.cs, F7_0000_0012_GenerateMap()
Original by MicroProse 1991; reconstruction by Rajko Horvat (MIT).

The map is always 80x50 and wraps horizontally. Four stages:

  1. Continents  — random-walk blobs stamped as plus shapes
  2. Latitude    — desert near the middle, tundra and ice near the poles
  3. Climate     — moisture accumulates over water and drains inland,
                   producing rain shadows; run west-to-east then east-to-west
  4. Age         — a random walk that "ages" cells: plains become hills,
                   hills become mountains, grassland becomes forest, and so on

Everything derives from the seed, so the same seed always yields the same map.
"""

import random
from enum import IntEnum

MAP_W = 80
MAP_H = 50


class Terrain(IntEnum):
    """Order matches OpenCivOne's TerrainTypeEnum and civagain's ETerrainType."""
    DESERT = 0
    PLAINS = 1
    GRASSLAND = 2
    FOREST = 3
    HILLS = 4
    MOUNTAINS = 5
    TUNDRA = 6
    ARCTIC = 7
    SWAMP = 8
    JUNGLE = 9
    WATER = 10
    RIVER = 11


# The four world parameters Civ1 asks for at game start. 0..2 each
# (age also accepts 2 = "5 billion years").
DEFAULT_PARAMS = dict(land_mass=1, temperature=1, climate=1, age=1)

# 8 directions, index 1..8 as in the original's MoveDirections table.
_MOVE8 = [(0, 0), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1), (-1, 0), (-1, -1)]


def _wrap_x(x):
    return x % MAP_W


def _clamp_y(y):
    return max(0, min(MAP_H - 1, y))


def generate(seed, land_mass=1, temperature=1, climate=1, age=1):
    """Returns a MAP_H x MAP_W list of lists of Terrain."""
    grid, _metadata = generate_with_metadata(
        seed,
        land_mass=land_mass,
        temperature=temperature,
        climate=climate,
        age=age,
    )
    return grid


def generate_with_metadata(seed, land_mass=1, temperature=1, climate=1, age=1):
    """Generate the map and retain exact coast-first river terminal data.

    ``generate`` deliberately keeps the historical grid-only API.  Renderers
    that need a pixel-exact mouth asset use this companion entry point instead
    of inferring a direction from the finished RIVER cells.
    """
    rng = random.Random(seed)
    grid = [[Terrain.WATER] * MAP_W for _ in range(MAP_H)]

    _stage1_continents(grid, rng, land_mass)
    _stage2_latitude(grid, rng, temperature)
    _stage3_climate(grid, rng, climate)
    _stage4_age(grid, rng, age)
    river_mouths = _stage5_rivers(grid, rng, land_mass, climate)

    return grid, {
        "schema": "civ-mapproto.mapgen-rivers/v2-mouth-first",
        "river_mouths": river_mouths,
    }


# ---------------------------------------------------------------- stage 1

def _stage1_continents(grid, rng, land_mass):
    """
    Random-walk blobs. This is what gives Civ1 its ragged coastlines —
    noise-based generators never look like this.
    """
    total_cells = land_mass * 320 + 640
    placed = 0

    while placed < total_cells:
        # Start well inside the map: the east/west edges and the polar caps
        # stay water, which is why Civ1 maps never touch the border.
        x = rng.randrange(72) + 4
        y = rng.randrange(34) + 8
        cloud_size = rng.randrange(64) + 1

        for _ in range(cloud_size):
            # Plus-shaped stamp.
            for dx, dy in ((0, 0), (0, -1), (1, 0), (0, 1), (-1, 0)):
                cx = _wrap_x(x + dx)
                cy = y + dy
                if 0 <= cy < MAP_H and grid[cy][cx] == Terrain.WATER:
                    grid[cy][cx] = Terrain.PLAINS
                    placed += 1

            step = rng.randrange(4)
            if step == 0:
                y -= 1
            elif step == 1:
                x += 1
            elif step == 2:
                y += 1
            else:
                x -= 1

            x = _wrap_x(x)
            y = _clamp_y(y)

            if placed >= total_cells:
                break


# ---------------------------------------------------------------- stage 2

def _stage2_latitude(grid, rng, temperature):
    """
    Bands by distance from row 29. The rng.randrange(8) is what frays the
    band edges — without it you get straight stripes across the map.
    """
    for y in range(MAP_H):
        for x in range(MAP_W):
            if grid[y][x] != Terrain.PLAINS:
                continue

            band = (abs(rng.randrange(8) + y - 29) + (1 - temperature)) // 6 + 1

            if band <= 1:
                grid[y][x] = Terrain.DESERT
            elif band in (4, 5):
                grid[y][x] = Terrain.TUNDRA
            elif band in (6, 7):
                grid[y][x] = Terrain.ARCTIC
            # bands 2 and 3 stay plains


# ---------------------------------------------------------------- stage 3

def _stage3_climate(grid, rng, climate):
    """
    Moisture model. Sweeping each row twice — once from the west, once from
    the east — builds up a climate value over open water and spends it as it
    crosses land. Coasts end up wet, interiors dry, and mountains block it.
    """
    drain_max = max(1, -(climate * 2 - 7))

    for y in range(MAP_H):
        median_y = abs(25 - y)

        # West to east
        climate_value = 0
        for x in range(MAP_W):
            cell = grid[y][x]
            if cell != Terrain.WATER:
                if climate_value > 0:
                    climate_value -= rng.randrange(drain_max)
                    if cell == Terrain.PLAINS:
                        grid[y][x] = Terrain.GRASSLAND
                    elif cell == Terrain.TUNDRA:
                        grid[y][x] = Terrain.ARCTIC
                    elif cell == Terrain.HILLS:
                        grid[y][x] = Terrain.FOREST
                    elif cell == Terrain.MOUNTAINS:
                        climate_value -= 3
            else:
                if median_y // 2 + climate > climate_value:
                    climate_value += 1

        # East to west — this pass creates jungle and swamp
        climate_value = 0
        for x in range(MAP_W - 1, -1, -1):
            cell = grid[y][x]
            if cell != Terrain.WATER:
                if climate_value > 0:
                    climate_value -= rng.randrange(drain_max)
                    if cell in (Terrain.SWAMP, Terrain.HILLS):
                        grid[y][x] = Terrain.FOREST
                    elif cell == Terrain.PLAINS:
                        grid[y][x] = Terrain.GRASSLAND
                    elif cell == Terrain.GRASSLAND:
                        grid[y][x] = Terrain.JUNGLE if median_y < 10 else Terrain.SWAMP
                        climate_value = -2
                    elif cell == Terrain.MOUNTAINS:
                        climate_value -= 3
                        grid[y][x] = Terrain.FOREST
                    elif cell == Terrain.DESERT:
                        grid[y][x] = Terrain.PLAINS
            else:
                if median_y // 2 + climate > climate_value:
                    climate_value += 1


# ---------------------------------------------------------------- stage 4

def _stage4_age(grid, rng, age):
    """
    Erosion / uplift pass. Older planets get more hills and mountains, and
    occasionally a mountain collapses into an inland sea.
    """
    steps = 800 + 800 * age
    cx = cy = 0

    for i in range(steps):
        if i & 1:
            dx, dy = _MOVE8[rng.randrange(8) + 1]
            cx = _wrap_x(cx + dx)
            cy = _clamp_y(cy + dy)
        else:
            cx = rng.randrange(MAP_W)
            cy = rng.randrange(MAP_H)

        cell = grid[cy][cx]

        if cell == Terrain.FOREST:
            grid[cy][cx] = Terrain.JUNGLE
        elif cell == Terrain.SWAMP:
            grid[cy][cx] = Terrain.GRASSLAND
        elif cell in (Terrain.PLAINS, Terrain.TUNDRA):
            grid[cy][cx] = Terrain.HILLS
        elif cell == Terrain.GRASSLAND:
            grid[cy][cx] = Terrain.FOREST
        elif cell == Terrain.JUNGLE:
            grid[cy][cx] = Terrain.SWAMP
        elif cell in (Terrain.HILLS, Terrain.ARCTIC):
            grid[cy][cx] = Terrain.MOUNTAINS
        elif cell == Terrain.MOUNTAINS:
            # Only drown a mountain if it is not on the coast.
            diag_dry = all(
                grid[_clamp_y(cy + dy)][_wrap_x(cx + dx)] != Terrain.WATER
                for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1))
            )
            if diag_dry:
                grid[cy][cx] = Terrain.WATER
        elif cell == Terrain.DESERT:
            grid[cy][cx] = Terrain.PLAINS


# ---------------------------------------------------------------- stage 5

_CARDINAL = ((0, -1), (1, 0), (0, 1), (-1, 0))
_PORT_NAMES = ("north", "east", "south", "west")


def _coast_first_mouth_candidates(grid):
    """Return straight three-cell coast profiles with a clear inland runway.

    A candidate owns a 3x2 coast metatile: three land frontage cells, their
    three sea neighbours, and three relief-free approach cells inward from
    the mouth.  The art may use the lower half of the final land cell and at
    most half of the first sea cell; this is metadata, never a terrain edit.
    """

    candidates = []
    blocked = (Terrain.WATER, Terrain.HILLS, Terrain.MOUNTAINS)
    for y in range(MAP_H):
        for x in range(MAP_W):
            if grid[y][x] in blocked:
                continue
            for exit_index, (dx, dy) in enumerate(_CARDINAL):
                sea_y = y + dy
                sea_x = _wrap_x(x + dx)
                if not (0 <= sea_y < MAP_H) or grid[sea_y][sea_x] != Terrain.WATER:
                    continue

                approach = []
                approach_original = []
                valid = True
                for depth in range(3):
                    ay = y - dy * depth
                    ax = _wrap_x(x - dx * depth)
                    if not (0 <= ay < MAP_H) or grid[ay][ax] in blocked:
                        valid = False
                        break
                    approach.append((ax, ay))
                    approach_original.append(int(grid[ay][ax]))
                if not valid:
                    continue

                tangent_x, tangent_y = -dy, dx
                frontage_land = []
                frontage_sea = []
                for offset in (-1, 0, 1):
                    land_y = y + tangent_y * offset
                    land_x = _wrap_x(x + tangent_x * offset)
                    water_y = land_y + dy
                    water_x = _wrap_x(land_x + dx)
                    if (
                        not (0 <= land_y < MAP_H)
                        or not (0 <= water_y < MAP_H)
                        or grid[land_y][land_x] == Terrain.WATER
                        or grid[water_y][water_x] != Terrain.WATER
                    ):
                        valid = False
                        break
                    frontage_land.append((land_x, land_y))
                    frontage_sea.append((water_x, water_y))
                if not valid:
                    continue

                candidates.append({
                    "river_cell": (x, y),
                    "water_cell": (sea_x, sea_y),
                    "exit_index": exit_index,
                    "exit_port": _PORT_NAMES[exit_index],
                    "inward_direction": (exit_index * 2 + 4) & 0x7,
                    "approach_cells": tuple(approach),
                    "approach_original_terrain": tuple(approach_original),
                    "frontage_land": tuple(frontage_land),
                    "frontage_water": tuple(frontage_sea),
                })
    return candidates


def _wrapped_manhattan(first, second):
    dx = abs(first[0] - second[0])
    return min(dx, MAP_W - dx) + abs(first[1] - second[1])


def _select_mouths(grid, rng, count):
    candidates = _coast_first_mouth_candidates(grid)
    rng.shuffle(candidates)
    chosen = []
    reserved = set()
    for candidate in candidates:
        owned = set(candidate["approach_cells"])
        owned.update(candidate["frontage_land"])
        owned.update(candidate["frontage_water"])
        if owned & reserved:
            continue
        if any(_wrapped_manhattan(candidate["river_cell"], item["river_cell"]) < 5 for item in chosen):
            continue
        chosen.append(candidate)
        reserved.update(owned)
        if len(chosen) >= count:
            break
    return chosen


def _nearest_highlands(grid, cell):
    highlands = [
        (x, y)
        for y in range(MAP_H)
        for x in range(MAP_W)
        if grid[y][x] in (Terrain.HILLS, Terrain.MOUNTAINS)
    ]
    return sorted(highlands, key=lambda target: (_wrapped_manhattan(cell, target), target[1], target[0]))


def _inland_highlands(grid, cell, inward_direction):
    """Rank sources in front of the reserved mouth runway, never behind it.

    Pure nearest-distance selection can pick a hill beside or even seaward of
    the third approach cell.  The resulting legal cell path then has to curl
    back as a U.  Mouth-first generation owns the terminal direction, so source
    ranking must respect that direction before considering distance.
    """

    step_x, step_y = _direction_step(inward_direction)
    ranked = []
    for target in _nearest_highlands(grid, cell):
        raw_dx = (target[0] - cell[0]) % MAP_W
        dx = raw_dx - MAP_W if raw_dx > MAP_W // 2 else raw_dx
        dy = target[1] - cell[1]
        longitudinal = dx * step_x + dy * step_y
        lateral = abs(dx * step_y - dy * step_x)
        distance = abs(dx) + abs(dy)
        # Sources behind the runway remain a last-resort fallback only.
        behind = 1 if longitudinal < 2 else 0
        score = behind * 1000 + lateral * 9 + distance * 3 - max(0, longitudinal)
        ranked.append((score, behind, lateral, distance, target[1], target[0], target))
    ranked.sort()
    return [item[-1] for item in ranked]


def _direction_step(direction):
    return _MOVE8[direction + 1]


def _advance(cell, direction):
    dx, dy = _direction_step(direction)
    return _wrap_x(cell[0] + dx), cell[1] + dy


def _turn_options(direction, rng):
    options = [direction & 0x7, (direction - 2) & 0x7, (direction + 2) & 0x7]
    # Deterministic seed variation without ever introducing diagonals.
    if rng.randrange(2):
        options[1], options[2] = options[2], options[1]
    return options


def _stage5_rivers(grid, rng, land_mass, climate):
    """Grow every river from an authored coast terminal back into the land.

    Sea connection is structural: mouth and three-cell approach are reserved
    before the first inland step.  Branches are upstream tributaries, so every
    RIVER cell is connected to a mouth by construction.
    """

    river_target = (land_mass + climate) * 2 + 6
    mouths = _select_mouths(grid, rng, river_target)
    global_guard = set()
    for mouth in mouths:
        # Keep the final two cells free of confluences and relief.  The third
        # cell is where a left/right turn may begin.
        for cell in mouth["approach_cells"][:2]:
            for dx, dy in _CARDINAL:
                ny = cell[1] + dy
                if 0 <= ny < MAP_H:
                    global_guard.add((_wrap_x(cell[0] + dx), ny))
        global_guard.difference_update(mouth["approach_cells"])

    records = []
    for system_id, mouth in enumerate(mouths):
        approach = mouth["approach_cells"]
        for x, y in approach:
            grid[y][x] = Terrain.RIVER

        system_cells = set(approach)
        system_budget = 9 + land_mass + climate
        branch_probability = 0.10
        source_cells = []
        confluences = []
        arms = [(approach[-1], mouth["inward_direction"], 0)]
        next_arm_id = 1

        while arms and len(system_cells) < system_budget:
            current, direction, arm_id = arms.pop(0)
            target_candidates = _inland_highlands(grid, current, direction)
            target = target_candidates[0] if target_candidates else None
            arm_steps = 0
            max_arm_length = 12 + land_mass * 2 + climate * 2

            while arm_steps < max_arm_length and len(system_cells) < system_budget:
                ranked = []
                for rank, option in enumerate(_turn_options(direction, rng)):
                    next_cell = _advance(current, option)
                    nx, ny = next_cell
                    if not (0 <= ny < MAP_H):
                        continue
                    terrain = grid[ny][nx]
                    if terrain == Terrain.WATER or next_cell in global_guard:
                        continue
                    distance = _wrapped_manhattan(next_cell, target) if target is not None else 0
                    # Prefer forward motion, then a turn, while still moving
                    # toward the selected highland source.
                    ranked.append((distance * 4 + rank, option, next_cell, terrain))
                if not ranked:
                    break
                ranked.sort(key=lambda item: item[0])
                _score, new_direction, next_cell, terrain = ranked[0]
                turned = new_direction != direction

                if terrain in (Terrain.HILLS, Terrain.MOUNTAINS):
                    source_cells.append(next_cell)
                    break
                if terrain == Terrain.RIVER:
                    confluences.append(next_cell)
                    break

                if turned and rng.random() < branch_probability and len(system_cells) + 2 < system_budget:
                    alternatives = [
                        option
                        for option in ((direction - 2) & 0x7, (direction + 2) & 0x7)
                        if option != new_direction
                    ]
                    for branch_direction in alternatives:
                        branch_cell = _advance(current, branch_direction)
                        bx, by = branch_cell
                        if (
                            0 <= by < MAP_H
                            and branch_cell not in global_guard
                            and grid[by][bx] not in (Terrain.WATER, Terrain.RIVER, Terrain.HILLS, Terrain.MOUNTAINS)
                        ):
                            arms.append((current, branch_direction, next_arm_id))
                            next_arm_id += 1
                            break

                nx, ny = next_cell
                grid[ny][nx] = Terrain.RIVER
                system_cells.add(next_cell)
                current = next_cell
                direction = new_direction
                arm_steps += 1

        # Forest beside any retained system becomes jungle, as before.
        for x, y in tuple(system_cells):
            for dx, dy in _CARDINAL:
                ny = y + dy
                if 0 <= ny < MAP_H:
                    nx = _wrap_x(x + dx)
                    if grid[ny][nx] == Terrain.FOREST:
                        grid[ny][nx] = Terrain.JUNGLE

        records.append({
            "system_id": system_id,
            "river_cell": mouth["river_cell"],
            "water_cell": mouth["water_cell"],
            "exit_port": mouth["exit_port"],
            "inward_direction": mouth["inward_direction"],
            "approach_cells": mouth["approach_cells"],
            "approach_original_terrain": mouth["approach_original_terrain"],
            "frontage_land": mouth["frontage_land"],
            "frontage_water": mouth["frontage_water"],
            "source_cells": tuple(source_cells),
            "confluences": tuple(confluences),
            "river_cells": tuple(sorted(system_cells, key=lambda cell: (cell[1], cell[0]))),
            "asset_contract": {
                "profile": "straight_coast_3x2",
                "river_split_at_land_tile": 0.50,
                "max_offshore_sea_tile": 0.50,
                "allowed_incoming": ("left", "straight", "right"),
            },
        })
    return tuple(records)


# ---------------------------------------------------------------- helpers

def river_cells(grid):
    """All river cells as a set of (x, y) — the renderer builds its graph from this."""
    return {(x, y) for y in range(MAP_H) for x in range(MAP_W)
            if grid[y][x] == Terrain.RIVER}


def land_ratio(grid):
    land = sum(1 for row in grid for c in row if c != Terrain.WATER)
    return land / (MAP_W * MAP_H)


def terrain_counts(grid):
    counts = {t: 0 for t in Terrain}
    for row in grid:
        for c in row:
            counts[c] += 1
    return counts
