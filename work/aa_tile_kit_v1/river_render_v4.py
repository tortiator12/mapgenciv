"""Antialiased component-wide renderer for the River-V4 geometry plan."""

from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable, Mapping

from PIL import Image, ImageDraw

from work.terrain_lab.river_components_v4 import (
    CellWindow,
    FlowEdge,
    MouthSpec,
    plan_river_components,
)


_DELTA = {"N": (0, -1), "E": (1, 0), "S": (0, 1), "W": (-1, 0)}


def _normal(vector):
    length = math.hypot(float(vector[0]), float(vector[1]))
    if length <= 1.0e-9:
        return 0.0, 1.0
    return -float(vector[1]) / length, float(vector[0]) / length


def _meander_offset(segment, t: float, tile_px: int) -> float:
    """Return a component-phased lateral bend with a clamped C1 boundary.

    ``sin(pi*t)**2`` has both value and first derivative equal to zero at the
    endpoints.  The styled centreline therefore lands on every canonical Civ
    midpoint port exactly and retains the original Bezier derivative there.
    Phase still comes from the complete river component, so neighbouring
    cells do not restart a random sine texture.
    """
    t = min(1.0, max(0.0, float(t)))
    envelope = math.sin(math.pi * t) ** 2
    phase = segment.value_at(t, segment.phase_start, segment.phase_end)
    channel = segment.value_at(
        t, segment.channel_width_start_px, segment.channel_width_end_px
    )
    # At 96 px/cell this yields roughly 7--9.5 px of possible movement:
    # enough to break the ruler-straight graph without obscuring ownership.
    amplitude = min(
        float(tile_px) * 0.10,
        max(channel * 1.08, float(segment.length_px) * 0.16),
    )
    if segment.kind in {"source_arm", "branch_arm"}:
        amplitude *= 0.82
    component_wave = (
        math.sin(phase * 1.43 + 0.35) * 0.78
        + math.sin(phase * 2.71 - 0.90) * 0.28
    )
    return float(amplitude * envelope * component_wave)


def _meandered_point(segment, t: float, tile_px: int):
    point = segment.point(t)
    nx, ny = _normal(segment.derivative(t))
    offset = _meander_offset(segment, t, tile_px)
    return float(point[0] + nx * offset), float(point[1] + ny * offset)


def _sample(segment, tile_px: int, pixels_per_step: float = 2.75):
    count = max(8, int(math.ceil(segment.length_px / pixels_per_step)))
    for index in range(count):
        t0 = index / count
        t1 = (index + 1) / count
        tm = (t0 + t1) * 0.5
        yield (
            _meandered_point(segment, t0, tile_px),
            _meandered_point(segment, t1, tile_px),
            _meandered_point(segment, tm, tile_px),
            _normal(segment.derivative(tm)),
            segment.value_at(tm, segment.phase_start, segment.phase_end),
            segment.value_at(tm, segment.channel_width_start_px, segment.channel_width_end_px),
            segment.value_at(tm, segment.bank_width_start_px, segment.bank_width_end_px),
        )


def _styled_widths(
    channel: float,
    bank: float,
    phase: float,
    tile_px: int,
    *,
    channel_gain: float = 1.0,
    bank_gain: float = 1.0,
):
    # Exaggerate the authored component hierarchy just enough that a main stem
    # and a source arm no longer collapse to one uniform cable width.
    reference = max(1.0, float(tile_px) * 0.064)
    hierarchy = min(1.28, max(0.78, (float(channel) / reference) ** 0.58))
    channel_width = float(channel) * hierarchy * (
        1.25
        + 0.11 * math.sin(phase * 1.73)
        + 0.065 * math.sin(phase * 6.37 - 0.6)
    ) * float(channel_gain)
    bank_width = max(
        channel_width + tile_px * 0.055,
        float(bank)
        * (
            1.43
            + 0.10 * math.sin(phase * 1.17 - 0.4)
            + 0.055 * math.sin(phase * 5.31 + 0.2)
        )
        * float(bank_gain),
    )
    return channel_width, bank_width


def _local(point, owner_cell, window: CellWindow, tile_px: int, world_width: int):
    local_cell_x = (int(owner_cell[0]) - int(window.x0)) % int(world_width)
    local_x = local_cell_x * tile_px + (float(point[0]) - int(owner_cell[0]) * tile_px)
    local_y = float(point[1]) - int(window.y0) * tile_px
    return local_x, local_y


def _line(draw, p0, p1, *, scale, fill, width, x_offsets=(0.0,)):
    for x_offset in x_offsets:
        draw.line(
            (
                (p0[0] + x_offset) * scale,
                p0[1] * scale,
                (p1[0] + x_offset) * scale,
                p1[1] * scale,
            ),
            fill=fill,
            width=max(1, int(round(width * scale))),
        )


def _dab(draw, point, *, scale, fill, radius, x_offsets=(0.0,)):
    y = float(point[1]) * scale
    r = max(0.5, float(radius) * scale)
    for x_offset in x_offsets:
        x = (float(point[0]) + x_offset) * scale
        draw.ellipse((x - r, y - r, x + r, y + r), fill=fill)


def _render_estuary_stamp_v5(
    direction: str,
    tile_px: int,
    *,
    seed: int,
    world_cell: tuple[int, int],
) -> Image.Image:
    """Build a connected river-to-sea fan in the adjacent sea cell.

    The river and the stamp share the exact Civ midpoint port.  The fan then
    reaches well into the sea tile, so a valid logical mouth can no longer
    disappear as a tiny border nub.  It is generated at 4x resolution and is
    therefore independent from the old fixed 96 px mouth PNGs.
    """
    direction = str(direction).upper()
    if direction not in _DELTA:
        raise ValueError(f"invalid mouth direction: {direction}")
    scale = 4
    size = int(tile_px) * scale
    stamp = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(stamp, "RGBA")
    t = float(tile_px)
    if direction == "E":
        entry, forward = (0.0, t * 0.5), (1.0, 0.0)
    elif direction == "W":
        entry, forward = (t, t * 0.5), (-1.0, 0.0)
    elif direction == "S":
        entry, forward = (t * 0.5, 0.0), (0.0, 1.0)
    else:
        entry, forward = (t * 0.5, t), (0.0, -1.0)
    normal = (-forward[1], forward[0])
    code = (
        int(seed) * 1103515245
        + int(world_cell[0]) * 2654435761
        + int(world_cell[1]) * 2246822519
        + ord(direction) * 3266489917
    ) & 0xFFFFFFFF
    handed = -1.0 if code & 1 else 1.0

    def point(progress: float, lateral: float = 0.0):
        return (
            (entry[0] + forward[0] * progress + normal[0] * lateral) * scale,
            (entry[1] + forward[1] * progress + normal[1] * lateral) * scale,
        )

    # Turquoise mixing plume under the sediment.  It is deliberately broad
    # and translucent so the underlying ocean texture remains visible.
    plume = [
        point(0.0, -t * 0.11),
        point(t * 0.18, -t * 0.19),
        point(t * 0.62, -t * (0.31 + 0.025 * handed)),
        point(t * 0.72, t * 0.02 * handed),
        point(t * 0.58, t * (0.28 - 0.025 * handed)),
        point(t * 0.16, t * 0.18),
    ]
    draw.polygon(plume, fill=(23, 137, 157, 105))

    # Two asymmetric sandy deposition lobes frame the continuing water.
    for side, strength in ((-1.0, 1.0), (1.0, 0.82)):
        bend = handed * side
        lobe = [
            point(0.0, side * t * 0.075),
            point(t * 0.18, side * t * 0.105),
            point(t * 0.47, side * t * (0.19 + 0.025 * bend)),
            point(t * 0.59, side * t * (0.12 + 0.018 * bend)),
            point(t * 0.32, side * t * 0.055),
            point(t * 0.08, side * t * 0.045),
        ]
        draw.polygon(lobe, fill=(205, 166, 79, int(188 * strength)))

    def water_path(points, width, fill):
        draw.line(
            [point(progress, lateral) for progress, lateral in points],
            fill=fill,
            width=max(1, int(round(width * scale))),
            joint="curve",
        )

    # A continuous wet shoulder and core cross the border before splitting.
    water_path(
        ((0.0, 0.0), (t * 0.18, handed * t * 0.012), (t * 0.37, handed * t * 0.035)),
        t * 0.175,
        (39, 101, 115, 155),
    )
    water_path(
        ((0.0, 0.0), (t * 0.18, handed * t * 0.012), (t * 0.38, handed * t * 0.035)),
        t * 0.125,
        (18, 102, 148, 245),
    )
    for side, width in ((-1.0, t * 0.067), (1.0, t * 0.058)):
        water_path(
            (
                (t * 0.24, handed * t * 0.02),
                (t * 0.42, side * t * 0.085 + handed * t * 0.02),
                (t * 0.62, side * t * 0.17 + handed * t * 0.04),
            ),
            width,
            (21, 111, 153, 218),
        )

    # Short broken foam accents make the mouth legible without a neon ring.
    for side in (-1.0, 1.0):
        water_path(
            (
                (t * 0.31, side * t * 0.09),
                (t * 0.46, side * t * 0.145 + handed * t * 0.015),
            ),
            max(1.0, t * 0.018),
            (221, 226, 184, 125),
        )
    return stamp.resize((tile_px, tile_px), Image.Resampling.LANCZOS)


def render_river_components_v4(
    image: Image.Image,
    full_grid,
    flow_edges: Iterable[FlowEdge | tuple[tuple[int, int], tuple[int, int]]],
    mouths: Mapping[tuple[int, int], str] | Iterable[MouthSpec],
    *,
    seed: int,
    window: CellWindow | tuple[int, int, int, int],
    tile_px: int = 96,
    world_width: int = 80,
    mouth_asset_root: Path | None = None,
    channel_gain: float = 1.0,
    bank_gain: float = 1.0,
    procedural_estuary: bool = False,
) -> object:
    """Paint one continuous V4 river network and return its immutable plan."""
    if not isinstance(window, CellWindow):
        window = CellWindow(*window)
    expected = (window.width * tile_px, window.height * tile_px)
    if image.size != expected:
        raise ValueError(f"river canvas {image.size} != window pixels {expected}")
    plan = plan_river_components(
        full_grid,
        flow_edges,
        mouths=mouths,
        tile_px=tile_px,
        seed=seed,
        world_width=world_width,
        window=window,
    )

    scale = 2
    # Draw one periodic copy into both sides of a padded full-world canvas.
    # This makes the wrap seam's overlap and Lanczos filtering byte-identical
    # to the same world seam when it lies inside a crop.
    periodic = window.width == world_width
    padding_px = tile_px if periodic else 0
    overlay = Image.new(
        "RGBA",
        ((image.width + padding_px * 2) * scale, image.height * scale),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(overlay, "RGBA")
    if periodic:
        x_offsets = (
            float(padding_px - image.width),
            float(padding_px),
            float(padding_px + image.width),
        )
    else:
        x_offsets = (0.0,)

    # Broad floodplain stain first.  It is deliberately low contrast: it
    # settles the river into every biome without drawing a second hard tube.
    for segment in plan.segments:
        for p0, p1, pm, normal, phase, channel, bank in _sample(segment, tile_px):
            a = _local(p0, segment.owner_cell, window, tile_px, world_width)
            b = _local(p1, segment.owner_cell, window, tile_px, world_width)
            warmth = 0.5 + 0.5 * math.sin(phase * 0.61 + 0.8)
            channel_width, bank_width = _styled_widths(
                channel,
                bank,
                phase,
                tile_px,
                channel_gain=channel_gain,
                bank_gain=bank_gain,
            )
            flood_color = (
                int(91 + warmth * 13),
                int(79 + warmth * 10),
                int(46 + warmth * 8),
                42,
            )
            _line(
                draw,
                a,
                b,
                scale=scale,
                fill=flood_color,
                width=bank_width * 1.52,
                x_offsets=x_offsets,
            )
            color = (
                int(85 + warmth * 16),
                int(70 + warmth * 12),
                int(40 + warmth * 9),
                108,
            )
            _line(
                draw,
                a,
                b,
                scale=scale,
                fill=color,
                width=bank_width,
                x_offsets=x_offsets,
            )

            # Sparse mineral/silt dabs live toward alternating outer banks.
            # Their trigger is component phase, not a per-cell PRNG.
            fleck = math.sin(phase * 14.3 + 0.7)
            if fleck > 0.72:
                local_mid = _local(pm, segment.owner_cell, window, tile_px, world_width)
                side = 1.0 if math.sin(phase * 5.9) >= 0.0 else -1.0
                dab_point = (
                    local_mid[0] + normal[0] * bank_width * 0.40 * side,
                    local_mid[1] + normal[1] * bank_width * 0.40 * side,
                )
                _dab(
                    draw,
                    dab_point,
                    scale=scale,
                    fill=(151, 127, 77, 42),
                    radius=0.65 + 0.65 * fleck,
                    x_offsets=x_offsets,
                )

    for segment in plan.segments:
        for p0, p1, pm, normal, phase, channel, _bank in _sample(segment, tile_px):
            a = _local(p0, segment.owner_cell, window, tile_px, world_width)
            b = _local(p1, segment.owner_cell, window, tile_px, world_width)
            channel_width, _bank_width = _styled_widths(
                channel,
                _bank,
                phase,
                tile_px,
                channel_gain=channel_gain,
                bank_gain=bank_gain,
            )
            wave = 0.5 + 0.5 * math.sin(phase * 0.93)
            # A translucent wet shoulder feathers the water into sediment;
            # unlike V14/V15 it is not a dark contour outline.
            _line(
                draw,
                a,
                b,
                scale=scale,
                fill=(43, 83, 82, 82),
                width=channel_width * 1.34,
                x_offsets=x_offsets,
            )
            water = (
                int(15 + wave * 14),
                int(84 + wave * 26),
                int(129 + wave * 30),
                240,
            )
            _line(
                draw,
                a,
                b,
                scale=scale,
                fill=water,
                width=channel_width * 0.96,
                x_offsets=x_offsets,
            )

            # Rare off-centre shimmer dabs texturise water without creating a
            # longitudinal centre stripe or the repeated cross-ties of V14.
            ripple = math.sin(phase * 12.7 - 0.25)
            if ripple > 0.965:
                local_mid = _local(pm, segment.owner_cell, window, tile_px, world_width)
                side = 1.0 if math.sin(phase * 4.13 + 0.3) >= 0.0 else -1.0
                shimmer = (
                    local_mid[0] + normal[0] * channel_width * 0.22 * side,
                    local_mid[1] + normal[1] * channel_width * 0.22 * side,
                )
                _dab(
                    draw,
                    shimmer,
                    scale=scale,
                    fill=(140, 181, 178, 48),
                    radius=max(0.45, channel_width * 0.075),
                    x_offsets=x_offsets,
                )

    overlay = overlay.resize(
        (image.width + padding_px * 2, image.height), Image.Resampling.LANCZOS
    )
    if periodic:
        overlay = overlay.crop((padding_px, 0, padding_px + image.width, image.height))
    image.alpha_composite(overlay)

    if procedural_estuary or mouth_asset_root is not None:
        root = Path(mouth_asset_root) if mouth_asset_root is not None else None
        mouth_mapping = mouths.items() if isinstance(mouths, Mapping) else (
            (item.cell, item.direction) for item in mouths
        )
        cache: dict[str, Image.Image] = {}
        for (world_x, world_y), direction in mouth_mapping:
            direction = str(direction).upper()
            if direction not in _DELTA:
                continue
            dx, dy = _DELTA[direction]
            sea_x, sea_y = (int(world_x) + dx) % world_width, int(world_y) + dy
            local_x = (sea_x - window.x0) % world_width
            local_y = sea_y - window.y0
            if not (0 <= local_x < window.width and 0 <= local_y < window.height):
                continue
            if procedural_estuary:
                stamp = _render_estuary_stamp_v5(
                    direction,
                    tile_px,
                    seed=seed,
                    world_cell=(int(world_x), int(world_y)),
                )
            else:
                if direction not in cache:
                    if root is None:
                        raise RuntimeError("mouth asset root is required for PNG mouths")
                    with Image.open(root / f"mouth_{direction.lower()}.png") as source:
                        cache[direction] = source.convert("RGBA")
                stamp = cache[direction]
            image.alpha_composite(stamp, (local_x * tile_px, local_y * tile_px))
    return plan


__all__ = ["render_river_components_v4", "_render_estuary_stamp_v5"]
