"""Component-wide Forest/Jungle V4 drawing pass.

This module deliberately owns *presentation only*.  The Civ-cell authority,
world-space foot positions, exposed-edge retreats and component grammar remain
the responsibility of :mod:`work.terrain_lab.forest_regions_v3`.

The V4.1 renderer consumes every role-aware V3 foot: 6--8 trees at exposed
cells and 8--10 in junction/interior cells, with Jungle one denser.  A
distance-field under-canopy wash rises organically from the exact woodland
boundary to a continuous interior mass.  It is calculated on an internal
one-cell halo and clipped to FOREST/JUNGLE authority; therefore full-world,
crop and horizontal-wrap renders agree at their shared pixels and no
rectangular cluster stamp is required.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageOps
from scipy.ndimage import distance_transform_edt

from work.terrain_lab.forest_regions_v3 import (
    TreePlacement,
    WoodlandComponentPlan,
    plan_forest_regions_v3,
)
from work.terrain_lab.world import FOREST, JUNGLE


ROOT = Path(__file__).resolve().parent
DEFAULT_ASSET_ROOT = ROOT / "assets" / "forest_v4"
DEFAULT_QA_PATH = DEFAULT_ASSET_ROOT / "forest_v4_qa.json"

_GREEN_BROADLEAF_VARIANTS = (0, 1, 2, 3, 6, 7)
_AUTUMN_BROADLEAF_VARIANTS = (4, 5)


def _hash(seed: int, x: int, y: int, salt: int = 0) -> int:
    """Stable 32-bit mix; intentionally mirrors the planner's hash family."""

    value = (int(seed) ^ (x * 0x9E3779B1) ^ (y * 0x85EBCA77) ^ (salt * 0xC2B2AE3D)) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


@dataclass(frozen=True, slots=True)
class SelectedTreeV4:
    """One V3 foot record plus its deterministic V4 art decision."""

    point: TreePlacement
    sprite_variant: int
    crown_diameter_px: int
    autumn_accent: bool


@dataclass(frozen=True, slots=True)
class ForestRenderV4Report:
    """Small, JSON-friendly audit returned by the drawing pass."""

    component_count: int
    woodland_cell_count: int
    selected_tree_count: int
    forest_tree_count: int
    jungle_tree_count: int
    autumn_accent_count: int
    trees_per_cell_min: int
    trees_per_cell_max: int
    crown_min_px: int
    crown_max_px: int
    exposed_retreat_min_px: int
    exposed_retreat_max_px: int
    under_canopy_clipped_to_authority: bool
    understory_edge_target_min: int
    understory_edge_target_max: int
    understory_interior_target_min: int
    understory_interior_target_max: int
    rendered_tree_instances: int

    def as_dict(self) -> dict[str, int | bool]:
        return {
            field: getattr(self, field)
            for field in self.__dataclass_fields__
        }


@dataclass(frozen=True, slots=True)
class _SpriteRecord:
    image: Image.Image
    anchor_px: tuple[int, int]
    alpha_bbox: tuple[int, int, int, int]


class _SpriteLibrary:
    def __init__(self, asset_root: Path, qa_path: Path) -> None:
        payload = json.loads(Path(qa_path).read_text(encoding="utf-8"))
        records: dict[tuple[str, int], _SpriteRecord] = {}
        for item in payload.get("assets", ()):  # staging audit is authoritative
            family = str(item["family"])
            asset_name = str(item["asset"])
            index = int(asset_name.rsplit("_", 1)[1]) - 1
            path = Path(asset_root) / f"{asset_name}.png"
            with Image.open(path) as source:
                image = source.convert("RGBA")
            build = item["build"]
            anchor = tuple(int(value) for value in build["anchor_px"])
            bbox = tuple(int(value) for value in item["alpha_bbox_xyxy"])
            records[(family, index)] = _SpriteRecord(image, anchor, bbox)
        missing = {
            (family, index)
            for family in ("broadleaf", "conifer")
            for index in range(8)
            if (family, index) not in records
        }
        if missing:
            raise ValueError(f"forest V4 sprite audit is incomplete: {sorted(missing)!r}")
        self._records = records
        self._cache: dict[tuple[object, ...], tuple[Image.Image, tuple[int, int]]] = {}

    def sprite(
        self,
        tree: SelectedTreeV4,
        *,
        terrain: int,
    ) -> tuple[Image.Image, tuple[int, int]]:
        point = tree.point
        # Planner height scale controls silhouette height only.  The visible
        # crown width remains within the audited 24--34 px gameplay scale.
        height_q = round(float(point.height_scale), 3)
        tint_q = round(float(point.tint), 3)
        key = (
            point.asset_key,
            point.cell_role,
            tree.sprite_variant,
            tree.crown_diameter_px,
            height_q,
            tint_q,
            bool(point.mirror),
            int(terrain),
            bool(tree.autumn_accent),
        )
        cached = self._cache.get(key)
        if cached is not None:
            return cached

        record = self._records[(point.asset_key, tree.sprite_variant)]
        left, top, right, bottom = record.alpha_bbox
        visible_width = max(1, right - left)
        isotropic = tree.crown_diameter_px / float(visible_width)
        width = max(1, int(round(record.image.width * isotropic)))
        height = max(1, int(round(record.image.height * isotropic * height_q)))
        sprite = _resize_rgba_premultiplied(record.image, (width, height))
        anchor = (
            int(round(record.anchor_px[0] * isotropic)),
            int(round(record.anchor_px[1] * isotropic * height_q)),
        )
        if point.mirror:
            sprite = ImageOps.mirror(sprite)
            anchor = (sprite.width - 1 - anchor[0], anchor[1])
        sprite = _grade_sprite(
            sprite,
            terrain=terrain,
            tint=tint_q,
            autumn=tree.autumn_accent,
            family=point.asset_key,
            interior=point.cell_role in {"junction", "interior"},
        )
        result = (sprite, anchor)
        self._cache[key] = result
        return result


def _resize_rgba_premultiplied(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    source = np.asarray(image.convert("RGBA"), dtype=np.float32)
    alpha = source[..., 3] / 255.0
    premul = source[..., :3] * alpha[..., None]
    target_alpha = np.asarray(
        Image.fromarray(alpha, "F").resize(size, Image.Resampling.LANCZOS),
        dtype=np.float32,
    )
    target_channels = [
        np.asarray(
            Image.fromarray(premul[..., channel], "F").resize(size, Image.Resampling.LANCZOS),
            dtype=np.float32,
        )
        for channel in range(3)
    ]
    target_premul = np.stack(target_channels, axis=2)
    safe_alpha = np.maximum(target_alpha, 1.0 / 255.0)
    rgb = np.where(target_alpha[..., None] > 0.0, target_premul / safe_alpha[..., None], 0.0)
    rgba = np.dstack((np.clip(rgb, 0, 255), np.clip(target_alpha * 255.0, 0, 255))).astype(np.uint8)
    rgba[rgba[..., 3] == 0, :3] = 0
    return Image.fromarray(rgba, "RGBA")


def _grade_sprite(
    image: Image.Image,
    *,
    terrain: int,
    tint: float,
    autumn: bool,
    family: str,
    interior: bool,
) -> Image.Image:
    rgba = np.asarray(image, dtype=np.float32).copy()
    alpha = rgba[..., 3:4]
    rgb = rgba[..., :3]
    if terrain == JUNGLE:
        # A cooler, deeper broadleaf family keeps Jungle visibly distinct from
        # temperate Forest without inventing a different logical footprint.
        factors = np.asarray((0.76, 0.92, 0.74), dtype=np.float32)
        rgb *= factors * min(tint, 1.08)
        luma = rgb[..., 0:1] * 0.2126 + rgb[..., 1:2] * 0.7152 + rgb[..., 2:3] * 0.0722
        rgb = luma * 0.14 + rgb * 0.86
    elif autumn:
        rgb *= np.asarray((1.03, 0.98, 0.91), dtype=np.float32)
    elif family == "broadleaf":
        # V18 broadleaf crowns were the same yellow-green value as the ground
        # and consequently read as shrubs.  Interior crowns carry the deeper
        # approved-material green; exposed crowns stay slightly lighter so a
        # component edge still thins out instead of becoming a black wall.
        factors = (
            np.asarray((0.82, 0.91, 0.84), dtype=np.float32)
            if interior
            else np.asarray((0.88, 0.95, 0.88), dtype=np.float32)
        )
        rgb *= factors * max(0.86, min(tint, 1.04))
    else:
        rgb *= max(0.86, min(tint, 1.04))
    result = np.concatenate((np.clip(rgb, 0, 255), alpha), axis=2).astype(np.uint8)
    result[result[..., 3] == 0, :3] = 0
    return Image.fromarray(result, "RGBA")


def select_trees_v4(
    plans: Iterable[WoodlandComponentPlan],
    *,
    seed: int,
) -> tuple[SelectedTreeV4, ...]:
    """Style every immutable V4.1 foot without consuming its density budget.

    The planner already enforces the role population and 2--3-crown seam
    contract.  Presentation therefore never discards seam metadata to hit a
    smaller arbitrary per-cell cap.  Autumn is selected component-wide: at
    most one cell in twelve receives exactly one accent crown.
    """

    plan_tuple = tuple(plans)
    autumn_ids: set[tuple[object, ...]] = set()
    for plan in plan_tuple:
        if plan.terrain != FOREST:
            continue
        by_cell: dict[tuple[int, int], list[TreePlacement]] = defaultdict(list)
        for point in plan.placements:
            if point.asset_key == "broadleaf":
                by_cell[point.owner_cell].append(point)
        quota = min(len(by_cell), len(plan.cells) // 12)
        cells = sorted(
            by_cell,
            key=lambda cell: (
                _hash(seed, cell[0], cell[1], 24317 + plan.key[1] * 7 + plan.key[2] * 11),
                cell[1],
                cell[0],
            ),
        )[:quota]
        for cell in cells:
            point = min(
                by_cell[cell],
                key=lambda candidate: (
                    _hash(seed, cell[0], cell[1], 24371 + candidate.placement_id[-1] * 19),
                    candidate.placement_id,
                ),
            )
            autumn_ids.add(point.placement_id)

    selected: list[SelectedTreeV4] = []
    for plan in plan_tuple:
        for point in plan.placements:
            cell = point.owner_cell
            style_value = _hash(seed, cell[0], cell[1], 24251 + point.placement_id[-1] * 29)
            autumn = point.placement_id in autumn_ids
            if point.asset_key == "conifer":
                variant = (point.variant + ((style_value >> 8) & 7)) % 8
            elif autumn:
                variant = _AUTUMN_BROADLEAF_VARIANTS[(style_value >> 9) & 1]
            else:
                variant = _GREEN_BROADLEAF_VARIANTS[
                    (point.variant + ((style_value >> 8) & 7)) % len(_GREEN_BROADLEAF_VARIANTS)
                ]

            interior = point.cell_role in {"junction", "interior"}
            if point.asset_key == "broadleaf":
                crown = 32 + ((style_value >> 18) & 1) if interior else 27 + ((style_value >> 18) % 5)
            else:
                crown = 29 + ((style_value >> 18) % 4) if interior else 25 + ((style_value >> 18) % 5)
            selected.append(
                SelectedTreeV4(
                    point=point,
                    sprite_variant=int(variant),
                    crown_diameter_px=int(crown),
                    autumn_accent=bool(autumn),
                )
            )
    return tuple(
        sorted(
            selected,
            key=lambda tree: (
                tree.point.world_anchor_px[1],
                tree.point.depth_layer,
                tree.point.placement_id,
            ),
        )
    )


def _local_cell_copies(
    world_x: int,
    *,
    window_x0: int,
    window_width: int,
    world_width: int,
    margin_cells: int = 1,
) -> tuple[int, ...]:
    base = (int(world_x) - int(window_x0)) % world_width
    candidates = {base + offset * world_width for offset in (-1, 0, 1)}
    return tuple(
        sorted(
            candidate
            for candidate in candidates
            if -margin_cells <= candidate < window_width + margin_cells
        )
    )


def _authority_masks(
    plans: tuple[WoodlandComponentPlan, ...],
    *,
    window: tuple[int, int, int, int],
    tile_px: int,
    world_width: int,
) -> dict[int, Image.Image]:
    x0, y0, width, height = window
    size = (width * tile_px, height * tile_px)
    masks = {
        FOREST: Image.new("L", size, 0),
        JUNGLE: Image.new("L", size, 0),
    }
    draws = {terrain: ImageDraw.Draw(mask) for terrain, mask in masks.items()}
    for plan in plans:
        draw = draws[plan.terrain]
        for world_x, world_y in plan.cells:
            local_y = world_y - y0
            if not (0 <= local_y < height):
                continue
            for local_x in _local_cell_copies(
                world_x,
                window_x0=x0,
                window_width=width,
                world_width=world_width,
                margin_cells=0,
            ):
                left = local_x * tile_px
                top = local_y * tile_px
                draw.rectangle((left, top, left + tile_px - 1, top + tile_px - 1), fill=255)
    return masks


def _world_pixel_noise(
    width: int,
    height: int,
    *,
    x0_px: int,
    y0_px: int,
    world_period_px: int,
    seed: int,
) -> np.ndarray:
    xs = (np.arange(width, dtype=np.float32) + float(x0_px)) % float(world_period_px)
    ys = np.arange(height, dtype=np.float32) + float(y0_px)
    xx, yy = np.meshgrid(xs, ys)
    phase = (seed & 0xFFFF) * 0.001731
    noise = (
        np.sin(xx * 0.041 + yy * 0.019 + phase)
        + np.sin(xx * -0.017 + yy * 0.053 + phase * 1.7)
        + np.sin(xx * 0.091 + yy * -0.073 + phase * 0.37) * 0.45
    )
    return np.clip(0.88 + noise * 0.055, 0.72, 1.04).astype(np.float32)


def _smoothstep(values: np.ndarray) -> np.ndarray:
    values = np.clip(values, 0.0, 1.0)
    return values * values * (3.0 - 2.0 * values)


def _understory_layer(
    plans: tuple[WoodlandComponentPlan, ...],
    trees: tuple[SelectedTreeV4, ...],
    *,
    window: tuple[int, int, int, int],
    tile_px: int,
    world_width: int,
    seed: int,
) -> tuple[Image.Image, dict[int, Image.Image]]:
    x0, y0, width, height = window
    size = (width * tile_px, height * tile_px)
    authority = _authority_masks(
        plans,
        window=window,
        tile_px=tile_px,
        world_width=world_width,
    )
    result = Image.new("RGBA", size, (0, 0, 0, 0))
    # ``trees`` is intentionally part of the immutable render contract even
    # though V4.1 derives the continuous mass from exact component authority.
    # The individual crowns are composited later and must not restart a dark
    # circular wash below every tree.
    _ = trees

    for terrain in (FOREST, JUNGLE):
        authority_array = np.asarray(authority[terrain], dtype=np.float32) / 255.0
        inside = authority_array > 0.5
        if not np.any(inside):
            continue

        # The one-cell caller halo is much wider than the largest 22 px fade.
        # Distances in the returned core therefore agree for a full world and
        # any independently rendered wrapped crop.
        distance = distance_transform_edt(inside).astype(np.float32)
        noise = _world_pixel_noise(
            size[0],
            size[1],
            x0_px=x0 * tile_px,
            y0_px=y0 * tile_px,
            world_period_px=world_width * tile_px,
            seed=seed + terrain * 101,
        )
        organic = np.clip((noise - 0.88) / 0.16, -1.0, 1.0)
        fade_width = np.clip(18.0 + organic * 4.0, 14.0, 22.0)
        edge_target = 68.0 if terrain == FOREST else 78.0
        interior_target = 115.0 if terrain == FOREST else 125.0

        # Alpha is effectively zero at the exact authority boundary, reaches
        # the requested edge mass after an organic 14--22 px inset, then rises
        # once more to the continuous interior target.  The final authority
        # multiplication is the non-negotiable no-spill guard.
        edge_progress = _smoothstep((distance - 0.5) / fade_width)
        deep_progress = _smoothstep((distance - fade_width) / np.maximum(8.0, fade_width * 0.72))
        alpha_float = edge_target * edge_progress + (interior_target - edge_target) * deep_progress
        alpha_float *= np.clip(0.95 + organic * 0.05, 0.90, 1.00)
        alpha = np.clip(alpha_float * authority_array, 0, 255).astype(np.uint8)
        color = (10, 35, 16) if terrain == FOREST else (3, 38, 23)
        rgba = np.empty((size[1], size[0], 4), dtype=np.uint8)
        rgba[..., :3] = color
        rgba[..., 3] = alpha
        result.alpha_composite(Image.fromarray(rgba, "RGBA"))
    return result, authority


def _clip_shadow_to_authority(
    shadow: Image.Image,
    authority: Image.Image,
) -> Image.Image:
    array = np.asarray(shadow, dtype=np.uint8).copy()
    mask = np.asarray(authority, dtype=np.uint8)
    array[..., 3] = ((array[..., 3].astype(np.uint16) * mask.astype(np.uint16)) // 255).astype(np.uint8)
    return Image.fromarray(array, "RGBA")


def render_forest_regions_v4(
    image: Image.Image,
    full_grid: np.ndarray,
    *,
    seed: int,
    window: tuple[int, int, int, int],
    tile_px: int = 96,
    world_width: int | None = None,
    asset_root: Path = DEFAULT_ASSET_ROOT,
    qa_path: Path = DEFAULT_QA_PATH,
    plans: Iterable[WoodlandComponentPlan] | None = None,
) -> ForestRenderV4Report:
    """Composite the deterministic V4 forest layer into ``image``.

    ``window`` is ``(world_x0, world_y0, width_cells, height_cells)``.  It may
    cross horizontal world wrap; vertical coordinates remain non-wrapping.
    The input canvas must be exactly ``width_cells * tile_px`` by
    ``height_cells * tile_px``.
    """

    grid = np.asarray(full_grid)
    if grid.ndim != 2 or grid.size == 0:
        raise ValueError("full_grid must be a non-empty 2-D array")
    width_world = grid.shape[1] if world_width is None else int(world_width)
    if grid.shape[1] != width_world:
        raise ValueError("forest V4 planning requires the complete horizontal world")
    x0, y0, width, height = (int(value) for value in window)
    if tile_px < 24 or width <= 0 or height <= 0:
        raise ValueError("tile_px and window dimensions must be positive")
    expected_size = (width * tile_px, height * tile_px)
    if image.size != expected_size:
        raise ValueError(f"canvas {image.size} does not match forest window {expected_size}")

    plan_tuple = tuple(
        plan_forest_regions_v3(
            grid,
            seed=int(seed),
            tile_px=int(tile_px),
            world_width=width_world,
        )
        if plans is None
        else plans
    )
    trees = select_trees_v4(plan_tuple, seed=int(seed))
    by_cell: dict[tuple[int, int], list[SelectedTreeV4]] = defaultdict(list)
    for tree in trees:
        by_cell[tree.point.owner_cell].append(tree)

    # All blur kernels and crowns fit inside a one-cell halo.  Rendering that
    # halo first is what makes arbitrary chunks byte-identical to a full map.
    halo = 1
    work_window = (x0 - halo, y0 - halo, width + halo * 2, height + halo * 2)
    work_size = (work_window[2] * tile_px, work_window[3] * tile_px)
    layer = Image.new("RGBA", work_size, (0, 0, 0, 0))
    understory, authority = _understory_layer(
        plan_tuple,
        trees,
        window=work_window,
        tile_px=tile_px,
        world_width=width_world,
        seed=int(seed),
    )
    layer.alpha_composite(understory)

    library = _SpriteLibrary(Path(asset_root), Path(qa_path))
    instances: list[tuple[tuple[object, ...], SelectedTreeV4, int, int]] = []
    for tree in trees:
        point = tree.point
        local_y = point.owner_cell[1] - work_window[1]
        if not (-1 <= local_y <= work_window[3]):
            continue
        for local_cell_x in _local_cell_copies(
            point.owner_cell[0],
            window_x0=work_window[0],
            window_width=work_window[2],
            world_width=width_world,
            margin_cells=1,
        ):
            foot_x = local_cell_x * tile_px + point.anchor_px[0]
            foot_y = local_y * tile_px + point.anchor_px[1]
            sort_key = (
                point.world_anchor_px[1],
                point.depth_layer,
                point.placement_id,
                local_cell_x,
            )
            instances.append((sort_key, tree, foot_x, foot_y))

    # Contact shadows form one restrained layer below every crown.  They are
    # clipped to exact gameplay authority even when a foot is near an edge.
    shadow_layer = Image.new("RGBA", work_size, (0, 0, 0, 0))
    for _, tree, foot_x, foot_y in sorted(instances, key=lambda item: item[0]):
        diameter = tree.crown_diameter_px
        shadow_w = max(10, int(round(diameter * 0.76)))
        shadow_h = max(4, int(round(diameter * 0.19)))
        shadow = Image.new("RGBA", (shadow_w + 8, shadow_h + 8), (0, 0, 0, 0))
        draw = ImageDraw.Draw(shadow, "RGBA")
        draw.ellipse((4, 4, 4 + shadow_w, 4 + shadow_h), fill=(8, 18, 11, 48))
        shadow = shadow.filter(ImageFilter.GaussianBlur(max(1.2, diameter * 0.045)))
        left = int(round(foot_x - shadow.width * 0.5 + 2))
        top = int(round(foot_y - shadow.height * 0.52))
        shadow_layer.alpha_composite(shadow, (left, top))
    combined_authority = Image.fromarray(
        np.maximum(
            np.asarray(authority[FOREST], dtype=np.uint8),
            np.asarray(authority[JUNGLE], dtype=np.uint8),
        ),
        "L",
    )
    layer.alpha_composite(_clip_shadow_to_authority(shadow_layer, combined_authority))

    for _, tree, foot_x, foot_y in sorted(instances, key=lambda item: item[0]):
        sprite, anchor = library.sprite(tree, terrain=tree.point.terrain)
        left = int(round(foot_x - anchor[0]))
        top = int(round(foot_y - anchor[1]))
        layer.alpha_composite(sprite, (left, top))

    crop = layer.crop(
        (
            halo * tile_px,
            halo * tile_px,
            (halo + width) * tile_px,
            (halo + height) * tile_px,
        )
    )
    if image.mode != "RGBA":
        composed = image.convert("RGBA")
        composed.alpha_composite(crop)
        image.paste(composed.convert(image.mode))
    else:
        image.alpha_composite(crop)

    counts = [len(points) for points in by_cell.values()]
    retreats = [
        value
        for tree in trees
        for value in tree.point.edge_retreat_px
        if value > 0
    ]
    crowns = [tree.crown_diameter_px for tree in trees]
    return ForestRenderV4Report(
        component_count=len(plan_tuple),
        woodland_cell_count=len(by_cell),
        selected_tree_count=len(trees),
        forest_tree_count=sum(tree.point.terrain == FOREST for tree in trees),
        jungle_tree_count=sum(tree.point.terrain == JUNGLE for tree in trees),
        autumn_accent_count=sum(tree.autumn_accent for tree in trees),
        trees_per_cell_min=min(counts, default=0),
        trees_per_cell_max=max(counts, default=0),
        crown_min_px=min(crowns, default=0),
        crown_max_px=max(crowns, default=0),
        exposed_retreat_min_px=min(retreats, default=0),
        exposed_retreat_max_px=max(retreats, default=0),
        under_canopy_clipped_to_authority=True,
        understory_edge_target_min=68,
        understory_edge_target_max=78,
        understory_interior_target_min=115,
        understory_interior_target_max=125,
        rendered_tree_instances=len(instances),
    )


__all__ = (
    "DEFAULT_ASSET_ROOT",
    "DEFAULT_QA_PATH",
    "ForestRenderV4Report",
    "SelectedTreeV4",
    "render_forest_regions_v4",
    "select_trees_v4",
)
