"""Rectangular-safe orthographic composition and diagnostic grid rendering."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from PIL import Image, ImageDraw

from .assets import LoadedSprite


def composite_anchored(
    canvas: Image.Image,
    sprite: LoadedSprite,
    anchor_x: float,
    anchor_y: float,
) -> tuple[int, int, int, int] | None:
    """Alpha-composite a sprite and return the clipped destination rectangle.

    Width and height are handled independently.  This avoids the classic bug where
    square assumptions cut off wide forests or tall mountain ridges.
    """

    if canvas.mode != "RGBA":
        raise ValueError("canvas must be RGBA")
    image = sprite.image.convert("RGBA")
    left = round(anchor_x - sprite.anchor_px[0])
    top = round(anchor_y - sprite.anchor_px[1])
    right = left + image.width
    bottom = top + image.height

    clip_left = max(0, left)
    clip_top = max(0, top)
    clip_right = min(canvas.width, right)
    clip_bottom = min(canvas.height, bottom)
    if clip_left >= clip_right or clip_top >= clip_bottom:
        return None

    source_box = (
        clip_left - left,
        clip_top - top,
        clip_right - left,
        clip_bottom - top,
    )
    canvas.alpha_composite(image.crop(source_box), (clip_left, clip_top))
    return clip_left, clip_top, clip_right, clip_bottom


@dataclass(frozen=True)
class SpritePlacement:
    sprite: LoadedSprite
    anchor_x: float
    anchor_y: float
    layer: int = 0
    stable_order: int = 0


class OrthographicCompositor:
    """Painter-order compositor for overhanging AA terrain objects."""

    def __init__(self, canvas: Image.Image):
        if canvas.mode != "RGBA":
            raise ValueError("canvas must be RGBA")
        self.canvas = canvas
        self._placements: list[SpritePlacement] = []
        self._next_order = 0

    def place(
        self,
        sprite: LoadedSprite,
        *,
        anchor_x: float,
        anchor_y: float,
        layer: int = 0,
    ) -> None:
        self._placements.append(
            SpritePlacement(sprite, anchor_x, anchor_y, layer, self._next_order)
        )
        self._next_order += 1

    def flush(self) -> list[tuple[int, int, int, int] | None]:
        """Paint low layers first, then back-to-front by bottom anchor."""

        ordered = sorted(
            self._placements,
            key=lambda placement: (
                placement.layer,
                placement.anchor_y,
                placement.anchor_x,
                placement.stable_order,
            ),
        )
        results = [
            composite_anchored(
                self.canvas,
                placement.sprite,
                placement.anchor_x,
                placement.anchor_y,
            )
            for placement in ordered
        ]
        self._placements.clear()
        return results


def _grid_positions(length: int, cell: int, offset: int) -> Iterable[int]:
    first = offset % cell
    if first != 0:
        first -= cell
    position = first
    while position <= length:
        if position >= 0:
            yield position
        position += cell


def draw_grid_overlay(
    image: Image.Image,
    *,
    tile_size: tuple[int, int] = (96, 96),
    world_offset_px: tuple[int, int] = (0, 0),
    dark: tuple[int, int, int, int] = (7, 18, 22, 118),
    light: tuple[int, int, int, int] = (214, 230, 214, 28),
) -> Image.Image:
    """Return an orthographic square-grid overlay aligned to world coordinates."""

    tile_w, tile_h = tile_size
    if tile_w <= 0 or tile_h <= 0:
        raise ValueError("tile dimensions must be positive")
    result = image.convert("RGBA")
    overlay = Image.new("RGBA", result.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    offset_x, offset_y = world_offset_px
    for x in _grid_positions(result.width, tile_w, -offset_x):
        draw.line((x, 0, x, result.height - 1), fill=dark, width=1)
        if x + 1 < result.width:
            draw.line((x + 1, 0, x + 1, result.height - 1), fill=light, width=1)
    for y in _grid_positions(result.height, tile_h, -offset_y):
        draw.line((0, y, result.width - 1, y), fill=dark, width=1)
        if y + 1 < result.height:
            draw.line((0, y + 1, result.width - 1, y + 1), fill=light, width=1)
    result.alpha_composite(overlay)
    return result
