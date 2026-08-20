"""Deterministic cardinal coast masks for material-layer composition."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from PIL import Image


_DIRECTIONS = ("N", "E", "S", "W")


def _smoothstep(value: float) -> float:
    value = max(0.0, min(1.0, value))
    return value * value * (3.0 - 2.0 * value)


@dataclass(frozen=True)
class CoastMasks:
    land: Image.Image
    beach: Image.Image
    foam: Image.Image


class CoastMaskFactory:
    """Creates 16 reusable cardinal water-edge masks at exact tile dimensions.

    A mask declares which borders are water.  The interior remains land, while a
    smooth shoreline, beach band, and water-side foam band are returned separately.
    Diagonal topology can later be added as authored variants without changing the
    renderer contract.
    """

    def __init__(
        self,
        size: tuple[int, int] = (96, 96),
        *,
        transition_px: int = 14,
        beach_px: int = 7,
        foam_px: int = 3,
    ):
        width, height = size
        if width <= 0 or height <= 0:
            raise ValueError("mask dimensions must be positive")
        if min(transition_px, beach_px, foam_px) <= 0:
            raise ValueError("coast widths must be positive")
        if beach_px + foam_px >= transition_px:
            raise ValueError("beach_px + foam_px must be less than transition_px")
        self.size = size
        self.transition_px = transition_px
        self.beach_px = beach_px
        self.foam_px = foam_px

    @staticmethod
    def normalize_edges(water_edges: Iterable[str]) -> tuple[str, ...]:
        supplied = set(water_edges)
        invalid = supplied - set(_DIRECTIONS)
        if invalid:
            raise ValueError(f"invalid coast edges: {sorted(invalid)}")
        return tuple(direction for direction in _DIRECTIONS if direction in supplied)

    def _distance_to_water_edge(self, x: int, y: int, edges: tuple[str, ...]) -> float:
        width, height = self.size
        distances: list[float] = []
        if "N" in edges:
            distances.append(float(y))
        if "E" in edges:
            distances.append(float(width - 1 - x))
        if "S" in edges:
            distances.append(float(height - 1 - y))
        if "W" in edges:
            distances.append(float(x))
        return min(distances) if distances else math.inf

    def create(self, water_edges: Iterable[str]) -> CoastMasks:
        edges = self.normalize_edges(water_edges)
        width, height = self.size
        land = Image.new("L", self.size, 255)
        beach = Image.new("L", self.size, 0)
        foam = Image.new("L", self.size, 0)
        if not edges:
            return CoastMasks(land, beach, foam)

        land_pixels = land.load()
        beach_pixels = beach.load()
        foam_pixels = foam.load()
        transition = float(self.transition_px)
        shore_center = float(self.foam_px)
        beach_end = shore_center + float(self.beach_px)
        for y in range(height):
            for x in range(width):
                distance = self._distance_to_water_edge(x, y, edges)
                land_value = round(255 * _smoothstep(distance / transition))
                land_pixels[x, y] = land_value

                if shore_center <= distance <= beach_end:
                    relative = (distance - shore_center) / max(1.0, self.beach_px)
                    peak = 1.0 - abs(relative * 2.0 - 1.0)
                    beach_pixels[x, y] = round(255 * _smoothstep(peak))

                if 0.0 <= distance <= self.foam_px * 2.0:
                    relative = abs(distance - shore_center) / max(1.0, self.foam_px)
                    foam_pixels[x, y] = round(255 * _smoothstep(1.0 - relative))
        return CoastMasks(land, beach, foam)

    def atlas(self) -> dict[int, CoastMasks]:
        """Generate every cardinal combination; bits are N=1,E=2,S=4,W=8."""

        return {
            mask: self.create(
                direction
                for bit, direction in zip((1, 2, 4, 8), _DIRECTIONS)
                if mask & bit
            )
            for mask in range(16)
        }
