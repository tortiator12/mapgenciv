"""Exact-footprint grouping for compact Civ relief sprites."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Literal

from .regions import RegionPlacement


Orientation = Literal["single", "EW", "NS"]
E, S = 2, 4


@dataclass(frozen=True, slots=True)
class ReliefMetatile:
    """One visual relief footprint backed by one or two exact Civ cells."""

    asset_key: str
    terrain: int
    orientation: Orientation
    members: tuple[RegionPlacement, ...]

    @property
    def cells(self) -> tuple[tuple[int, int], ...]:
        return tuple(member.owner_world for member in self.members)

    @property
    def start(self) -> RegionPlacement:
        return self.members[0]


def plan_relief_metatiles(
    placements: Iterable[RegionPlacement],
    *,
    world_width: int,
) -> tuple[ReliefMetatile, ...]:
    """Pair only exact same-terrain neighbours and cover every owner once.

    Horizontal pairs are preferred because both mountain and hill EW artwork
    exists.  Residual vertical mountain runs may use separately authored NS
    artwork.  Hills remain singles vertically until a valid NS asset passes the
    same footprint gate; artwork is never rotated as a shortcut.
    """

    if world_width <= 0:
        raise ValueError("world_width must be positive")
    relief = tuple(
        placement
        for placement in placements
        if placement.family == "relief" and placement.asset_key in {"mountain", "hill"}
    )
    by_world = {placement.owner_world: placement for placement in relief}
    if len(by_world) != len(relief):
        raise ValueError("relief placements contain duplicate world owners")

    used: set[tuple[int, int]] = set()
    result: list[ReliefMetatile] = []
    ordered = sorted(relief, key=lambda item: (item.owner_world[1], item.owner_world[0]))

    for candidate in ordered:
        if candidate.owner_world in used:
            continue
        x, y = candidate.owner_world
        east_world = ((x + 1) % world_width, y)
        east = by_world.get(east_world)
        if (
            east is None
            or east_world in used
            or east.asset_key != candidate.asset_key
            or east.terrain != candidate.terrain
            or not (candidate.neighbor_mask & E)
        ):
            continue
        result.append(ReliefMetatile(candidate.asset_key, candidate.terrain, "EW", (candidate, east)))
        used.update((candidate.owner_world, east_world))

    for candidate in ordered:
        if candidate.owner_world in used or candidate.asset_key != "mountain":
            continue
        x, y = candidate.owner_world
        south_world = (x, y + 1)
        south = by_world.get(south_world)
        if (
            south is None
            or south_world in used
            or south.asset_key != candidate.asset_key
            or south.terrain != candidate.terrain
            or not (candidate.neighbor_mask & S)
        ):
            continue
        result.append(ReliefMetatile(candidate.asset_key, candidate.terrain, "NS", (candidate, south)))
        used.update((candidate.owner_world, south_world))

    for candidate in ordered:
        if candidate.owner_world not in used:
            result.append(ReliefMetatile(candidate.asset_key, candidate.terrain, "single", (candidate,)))
            used.add(candidate.owner_world)

    if used != set(by_world):
        raise AssertionError("relief metatile plan did not cover every owner exactly once")
    return tuple(
        sorted(
            result,
            key=lambda item: (
                min(member.owner_world[1] for member in item.members),
                min(member.owner_world[0] for member in item.members),
                item.orientation,
            ),
        )
    )


__all__ = ("ReliefMetatile", "plan_relief_metatiles")
