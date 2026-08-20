"""Fifteen explicit NESW river-stamp slots and border-port validation."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntFlag
from typing import Iterable, Mapping

from PIL import Image, ImageDraw

from .contract import Manifest, RiverStampSpec, ports_for_mask


class Direction(IntFlag):
    N = 1
    E = 2
    S = 4
    W = 8


@dataclass(frozen=True)
class RiverMask:
    value: int

    def __post_init__(self) -> None:
        if isinstance(self.value, bool) or not 1 <= self.value <= 15:
            raise ValueError("river mask must be between 1 and 15")

    @property
    def ports(self) -> tuple[str, ...]:
        return ports_for_mask(self.value)

    @property
    def key(self) -> str:
        return "river_" + "".join(port.lower() for port in self.ports)


def border_profile(image: Image.Image, port: str) -> tuple[int, ...]:
    """Return alpha values along a border, oriented clockwise.

    N/S profiles run left-to-right; E/W profiles run top-to-bottom.  Opposite ports
    are therefore directly comparable for exact neighbor joins.
    """

    alpha = image.convert("RGBA").getchannel("A")
    width, height = alpha.size
    pixels = alpha.load()
    if port == "N":
        return tuple(pixels[x, 0] for x in range(width))
    if port == "S":
        return tuple(pixels[x, height - 1] for x in range(width))
    if port == "E":
        return tuple(pixels[width - 1, y] for y in range(height))
    if port == "W":
        return tuple(pixels[0, y] for y in range(height))
    raise ValueError(f"invalid port: {port}")


def _has_center_port(profile: tuple[int, ...], half_width: int, threshold: int) -> bool:
    center = len(profile) // 2
    start = max(0, center - half_width)
    end = min(len(profile), center + half_width + 1)
    return all(value >= threshold for value in profile[start:end])


def validate_river_ports(
    image: Image.Image,
    expected_ports: Iterable[str],
    *,
    port_half_width: int = 3,
    threshold: int = 8,
) -> list[str]:
    """Validate exact declared exits and reject accidental border leakage."""

    expected = set(expected_ports)
    issues: list[str] = []
    for port in ("N", "E", "S", "W"):
        profile = border_profile(image, port)
        has_any = any(value >= threshold for value in profile)
        if port in expected:
            if not _has_center_port(profile, port_half_width, threshold):
                issues.append(f"{port} port does not cover the centered contract width")
        elif has_any:
            issues.append(f"undeclared {port} border contains visible river pixels")
    return issues


def geometry_mask(
    river_mask: RiverMask | int,
    *,
    size: tuple[int, int] = (96, 96),
    width: int = 8,
) -> Image.Image:
    """Generate a non-art connectivity mask for tests and authoring guides only."""

    value = river_mask.value if isinstance(river_mask, RiverMask) else river_mask
    contract = RiverMask(value)
    image = Image.new("L", size, 0)
    draw = ImageDraw.Draw(image)
    image_width, image_height = size
    center = (image_width // 2, image_height // 2)
    endpoints = {
        "N": (center[0], 0),
        "E": (image_width - 1, center[1]),
        "S": (center[0], image_height - 1),
        "W": (0, center[1]),
    }
    for port in contract.ports:
        draw.line((center, endpoints[port]), fill=255, width=width)
    radius = max(1, width // 2)
    draw.ellipse(
        (
            center[0] - radius,
            center[1] - radius,
            center[0] + radius,
            center[1] + radius,
        ),
        fill=255,
    )
    # Pillow rasterizes the two endpoints of an even-width line one pixel
    # differently depending on direction.  Authoring guides must not inherit that
    # ambiguity: clear every border, then stamp one canonical centered profile.
    pixels = image.load()
    for x in range(image_width):
        pixels[x, 0] = 0
        pixels[x, image_height - 1] = 0
    for y in range(image_height):
        pixels[0, y] = 0
        pixels[image_width - 1, y] = 0
    horizontal_start = center[0] - width // 2
    vertical_start = center[1] - width // 2
    if "N" in contract.ports:
        for x in range(horizontal_start, horizontal_start + width):
            pixels[x, 0] = 255
    if "S" in contract.ports:
        for x in range(horizontal_start, horizontal_start + width):
            pixels[x, image_height - 1] = 255
    if "E" in contract.ports:
        for y in range(vertical_start, vertical_start + width):
            pixels[image_width - 1, y] = 255
    if "W" in contract.ports:
        for y in range(vertical_start, vertical_start + width):
            pixels[0, y] = 255
    return image


class RiverStampRegistry:
    """Manifest-backed registry that guarantees all 15 masks are addressable."""

    def __init__(self, specs: Mapping[int, RiverStampSpec]):
        missing = sorted(set(range(1, 16)) - set(specs))
        if missing:
            raise ValueError(f"missing river masks: {missing}")
        self._specs = dict(specs)

    @classmethod
    def from_manifest(cls, manifest: Manifest) -> "RiverStampRegistry":
        return cls(manifest.river_stamps)

    def spec(self, mask: RiverMask | int) -> RiverStampSpec:
        value = mask.value if isinstance(mask, RiverMask) else RiverMask(mask).value
        return self._specs[value]

    def all(self) -> tuple[RiverStampSpec, ...]:
        return tuple(self._specs[mask] for mask in range(1, 16))

    @staticmethod
    def neighbor_ports_match(
        first: Image.Image,
        first_port: str,
        second: Image.Image,
        second_port: str,
    ) -> bool:
        opposites = {("N", "S"), ("S", "N"), ("E", "W"), ("W", "E")}
        if (first_port, second_port) not in opposites:
            raise ValueError("ports must face each other")
        return border_profile(first, first_port) == border_profile(second, second_port)
