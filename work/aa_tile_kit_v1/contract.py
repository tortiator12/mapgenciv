"""Manifest data model and strict, dependency-free validation."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any, Mapping


class ManifestError(ValueError):
    """Raised when the tile-kit contract is incomplete or inconsistent."""


@dataclass(frozen=True)
class TileContract:
    width: int
    height: int
    projection: str
    pixels_per_tile: int

    @property
    def size(self) -> tuple[int, int]:
        return self.width, self.height


@dataclass(frozen=True)
class MaterialSpec:
    key: str
    file: str
    sampling: str
    required: bool = True


@dataclass(frozen=True)
class SpriteSpec:
    key: str
    file: str
    anchor: tuple[float, float]
    required: bool = True


@dataclass(frozen=True)
class RiverStampSpec:
    mask: int
    key: str
    file: str
    ports: tuple[str, ...]
    required: bool = True


@dataclass(frozen=True)
class CoastContract:
    ocean_material: str
    beach_material: str | None
    foam_material: str | None
    transition_px: int
    beach_px: int
    foam_px: int


@dataclass(frozen=True)
class Manifest:
    source: Path
    version: str
    tile: TileContract
    materials: Mapping[str, MaterialSpec]
    sprites: Mapping[str, SpriteSpec]
    river_stamps: Mapping[int, RiverStampSpec]
    coast: CoastContract

    @property
    def root(self) -> Path:
        return self.source.parent


_PORT_ORDER = ("N", "E", "S", "W")
_PORT_BITS = {"N": 1, "E": 2, "S": 4, "W": 8}


def ports_for_mask(mask: int) -> tuple[str, ...]:
    return tuple(port for port in _PORT_ORDER if mask & _PORT_BITS[port])


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, dict):
        raise ManifestError(f"{label} must be an object")
    return value


def _positive_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ManifestError(f"{label} must be a positive integer")
    return value


def _relative_file(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ManifestError(f"{label} must be a non-empty relative path")
    candidate = Path(value)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ManifestError(f"{label} must stay inside the tile-kit root")
    return value.replace("\\", "/")


def _required(value: Any, label: str) -> bool:
    if value is None:
        return True
    if not isinstance(value, bool):
        raise ManifestError(f"{label} must be a boolean")
    return value


def _parse_tile(raw: Mapping[str, Any]) -> TileContract:
    width = _positive_int(raw.get("width"), "tile.width")
    height = _positive_int(raw.get("height"), "tile.height")
    projection = raw.get("projection")
    if projection != "orthographic":
        raise ManifestError("tile.projection must be 'orthographic'")
    pixels_per_tile = _positive_int(
        raw.get("pixels_per_tile"), "tile.pixels_per_tile"
    )
    if width != pixels_per_tile or height != pixels_per_tile:
        raise ManifestError(
            "AA v1 requires square tiles whose dimensions equal pixels_per_tile"
        )
    return TileContract(width, height, projection, pixels_per_tile)


def _parse_materials(raw: Mapping[str, Any]) -> dict[str, MaterialSpec]:
    result: dict[str, MaterialSpec] = {}
    for key, item_value in raw.items():
        item = _mapping(item_value, f"materials.{key}")
        sampling = item.get("sampling", "world_periodic")
        if sampling != "world_periodic":
            raise ManifestError(
                f"materials.{key}.sampling must be 'world_periodic'"
            )
        result[key] = MaterialSpec(
            key=key,
            file=_relative_file(item.get("file"), f"materials.{key}.file"),
            sampling=sampling,
            required=_required(item.get("required"), f"materials.{key}.required"),
        )
    if not result:
        raise ManifestError("materials must contain at least one material")
    return result


def _parse_sprites(raw: Mapping[str, Any]) -> dict[str, SpriteSpec]:
    result: dict[str, SpriteSpec] = {}
    for key, item_value in raw.items():
        item = _mapping(item_value, f"sprites.{key}")
        anchor = item.get("anchor", [0.5, 1.0])
        if (
            not isinstance(anchor, list)
            or len(anchor) != 2
            or any(isinstance(v, bool) or not isinstance(v, (int, float)) for v in anchor)
            or any(v < 0.0 or v > 1.0 for v in anchor)
        ):
            raise ManifestError(
                f"sprites.{key}.anchor must be two normalized numbers"
            )
        result[key] = SpriteSpec(
            key=key,
            file=_relative_file(item.get("file"), f"sprites.{key}.file"),
            anchor=(float(anchor[0]), float(anchor[1])),
            required=_required(item.get("required"), f"sprites.{key}.required"),
        )
    return result


def _parse_rivers(raw: list[Any]) -> dict[int, RiverStampSpec]:
    if not isinstance(raw, list):
        raise ManifestError("river_stamps must be an array")
    result: dict[int, RiverStampSpec] = {}
    for index, item_value in enumerate(raw):
        item = _mapping(item_value, f"river_stamps[{index}]")
        mask = _positive_int(item.get("mask"), f"river_stamps[{index}].mask")
        if mask > 15:
            raise ManifestError(f"river_stamps[{index}].mask must be between 1 and 15")
        if mask in result:
            raise ManifestError(f"duplicate river mask {mask}")
        ports = item.get("ports")
        expected_ports = ports_for_mask(mask)
        if not isinstance(ports, list) or tuple(ports) != expected_ports:
            raise ManifestError(
                f"river mask {mask} ports must be {list(expected_ports)} in NESW order"
            )
        key = item.get("key")
        if not isinstance(key, str) or not key:
            raise ManifestError(f"river_stamps[{index}].key must be non-empty")
        result[mask] = RiverStampSpec(
            mask=mask,
            key=key,
            file=_relative_file(item.get("file"), f"river_stamps[{index}].file"),
            ports=expected_ports,
            required=_required(
                item.get("required"), f"river_stamps[{index}].required"
            ),
        )
    missing = sorted(set(range(1, 16)) - set(result))
    if missing:
        raise ManifestError(f"river_stamps must define all masks 1..15; missing {missing}")
    return result


def _parse_coast(raw: Mapping[str, Any], materials: Mapping[str, MaterialSpec]) -> CoastContract:
    ocean = raw.get("ocean_material")
    beach = raw.get("beach_material")
    foam = raw.get("foam_material")
    if ocean not in materials:
        raise ManifestError("coast.ocean_material must reference a material")
    if beach is not None and beach not in materials:
        raise ManifestError("coast.beach_material must be null or reference a material")
    if foam is not None and foam not in materials:
        raise ManifestError("coast.foam_material must be null or reference a material")
    transition_px = _positive_int(raw.get("transition_px"), "coast.transition_px")
    beach_px = _positive_int(raw.get("beach_px"), "coast.beach_px")
    foam_px = _positive_int(raw.get("foam_px"), "coast.foam_px")
    if beach_px + foam_px >= transition_px:
        raise ManifestError(
            "coast beach_px + foam_px must be smaller than transition_px"
        )
    return CoastContract(ocean, beach, foam, transition_px, beach_px, foam_px)


def load_manifest(path: str | Path) -> Manifest:
    """Load and validate a production tile-kit manifest.

    File existence is deliberately validated by :class:`AssetLoader`, allowing the
    art team to commit the contract before all generated assets have landed.
    """

    source = Path(path).resolve()
    try:
        raw_value = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManifestError(f"cannot read manifest {source}: {exc}") from exc
    raw = _mapping(raw_value, "manifest")
    if raw.get("version") != "1.0":
        raise ManifestError("version must be '1.0'")
    tile = _parse_tile(_mapping(raw.get("tile"), "tile"))
    materials = _parse_materials(_mapping(raw.get("materials"), "materials"))
    sprites = _parse_sprites(_mapping(raw.get("sprites", {}), "sprites"))
    rivers = _parse_rivers(raw.get("river_stamps"))
    coast = _parse_coast(_mapping(raw.get("coast"), "coast"), materials)
    return Manifest(source, "1.0", tile, materials, sprites, rivers, coast)
