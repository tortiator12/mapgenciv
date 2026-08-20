"""Terminal-aware hydrology contract (isolated V27 pilot).

This module addresses the river-mouth failure *before* presentation.  New
worlds reserve a clean two-cell approach and a mouth/sea port before a river
centreline is rasterized.  The final River cell therefore cannot contain a
confluence or a 90-degree turn that an authored delta would later have to
hide.

Legacy Civ/OpenCivOne snapshots are deliberately different.  Their saved
``RIVER`` cells are gameplay authority and are never rewritten here.  A
legacy 90-degree mouth may receive a deterministic sub-cell tangent fit for
presentation, but the result is explicitly labelled ``legacy_subcell_fit``;
it is never misreported as generator-canonical.

The intended V11 insertion point is immediately after a fine A* route reaches
a coast goal and before ``_shoreline_from_goal``, ``_smooth_land_path`` and
``rasterize_centerline_v11``.  V12 is too late because it already consumes a
raster-authoritative V11 corridor.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any, Iterable, Mapping, Sequence

import numpy as np


Cell = tuple[int, int]
Point = tuple[float, float]

CARDINAL_PORTS: Mapping[str, Cell] = {
    "north": (0, -1),
    "east": (1, 0),
    "south": (0, 1),
    "west": (-1, 0),
}
OCTANT_PORTS: Mapping[str, Point] = {
    "north": (0.0, -1.0),
    "northeast": (math.sqrt(0.5), -math.sqrt(0.5)),
    "east": (1.0, 0.0),
    "southeast": (math.sqrt(0.5), math.sqrt(0.5)),
    "south": (0.0, 1.0),
    "southwest": (-math.sqrt(0.5), math.sqrt(0.5)),
    "west": (-1.0, 0.0),
    "northwest": (-math.sqrt(0.5), -math.sqrt(0.5)),
}
OPPOSITE_PORT: Mapping[str, str] = {
    "north": "south",
    "northeast": "southwest",
    "east": "west",
    "southeast": "northwest",
    "south": "north",
    "southwest": "northeast",
    "west": "east",
    "northwest": "southeast",
}


@dataclass(frozen=True)
class RiverTerminalSpecV27:
    """Stable generator-to-renderer terminal metadata."""

    mode: str
    trace_id: int | None
    source_id: str
    river_cell: Cell
    sea_cell: Cell
    approach_cells: tuple[Cell, ...]
    entry_port: str
    entry_reciprocal_port: str
    exit_port: str
    sea_reciprocal_port: str
    entry_point: Point
    split_point: Point
    shoreline_point: Point
    incoming_tangent: Point
    width_px: float
    stream_order: int
    asset_direction: str
    approach_angle_degrees: float
    coarse_port_turn_degrees: float
    final_cell_confluences: int
    strict_generator_contract: bool
    terrain_cells_changed: bool
    compatibility_reason: str | None


@dataclass(frozen=True)
class TerminalReservationV27:
    """A mouth tail owned before rasterization begins."""

    spec: RiverTerminalSpecV27
    route_tail: tuple[Cell, ...]
    reserved_cells: tuple[Cell, ...]
    guard_cells: tuple[Cell, ...]
    selected_before_rasterization: bool = True


@dataclass(frozen=True)
class LegacyTerminalNormalizationV27:
    """Sub-cell-only compatibility result for one immutable saved trace."""

    spec: RiverTerminalSpecV27
    before_points: tuple[Point, ...]
    after_body_points: tuple[Point, ...]
    original_river_cells: tuple[Cell, ...]
    normalized_river_cells: tuple[Cell, ...]
    repair_status: str
    repair_actions: tuple[str, ...]
    target_trace_cycle_before: bool
    target_trace_cycle_after: bool


@dataclass(frozen=True)
class SourceTerminalSpecV27:
    """Round spring-lake source contract; no source art is generated here."""

    source_id: str
    source_cell: Cell
    outflow_cell: Cell
    lake_center: Point
    lake_radius_cells: float
    outflow_port: str
    outflow_reciprocal_port: str
    outflow_point: Point
    outgoing_tangent: Point
    width_px: float
    stream_order: int
    asset_direction: str


@dataclass(frozen=True)
class TerminalAuditV27:
    valid: bool
    errors: tuple[str, ...]
    reciprocal_ports: bool
    approach_angle_degrees: float
    final_cell_confluences: int
    terrain_cells_changed: bool


def _stable_hash(seed: int, *values: int) -> int:
    value = int(seed) & 0xFFFFFFFFFFFFFFFF
    for item in values:
        value ^= (int(item) + 0x9E3779B97F4A7C15 + (value << 6) + (value >> 2)) & 0xFFFFFFFFFFFFFFFF
        value = (value * 0xBF58476D1CE4E5B9) & 0xFFFFFFFFFFFFFFFF
        value ^= value >> 27
    return value & 0xFFFFFFFFFFFFFFFF


def _neighbor(cell: Cell, port: str, width: int, height: int) -> Cell | None:
    dx, dy = CARDINAL_PORTS[port]
    y = cell[1] + dy
    if not 0 <= y < height:
        return None
    return (cell[0] + dx) % width, y


def _wrapped_step(start: Cell, end: Cell, width: int) -> Cell:
    dx = end[0] - start[0]
    dx -= round(dx / float(width)) * width
    return int(dx), int(end[1] - start[1])


def _port_for_step(step: Cell) -> str:
    for name, vector in CARDINAL_PORTS.items():
        if tuple(step) == vector:
            return name
    raise ValueError(f"non-cardinal terminal step {step}")


def _unit(vector: Sequence[float]) -> Point:
    length = max(math.hypot(float(vector[0]), float(vector[1])), 1e-12)
    return float(vector[0]) / length, float(vector[1]) / length


def _angle(first: Sequence[float], second: Sequence[float]) -> float:
    a, b = _unit(first), _unit(second)
    dot = max(-1.0, min(1.0, a[0] * b[0] + a[1] * b[1]))
    return math.degrees(math.acos(dot))


def _octant(vector: Sequence[float]) -> str:
    names = ("east", "southeast", "south", "southwest", "west", "northwest", "north", "northeast")
    degrees = math.degrees(math.atan2(float(vector[1]), float(vector[0]))) % 360.0
    return names[int(math.floor((degrees + 22.5) / 45.0)) % 8]


def _cell_center(cell: Cell, anchor_x: float | None = None, width: int | None = None) -> Point:
    x = float(cell[0]) + 0.5
    if anchor_x is not None and width is not None:
        x += round((float(anchor_x) - x) / float(width)) * float(width)
    return x, float(cell[1]) + 0.5


def _wrapped_manhattan(first: Cell, second: Cell, width: int) -> int:
    dx = abs(first[0] - second[0])
    dx = min(dx, width - dx)
    return int(dx + abs(first[1] - second[1]))


def _bezier(p0: Point, p1: Point, p2: Point, p3: Point, count: int = 161) -> tuple[Point, ...]:
    result: list[Point] = []
    for q in np.linspace(0.0, 1.0, int(count)):
        r = 1.0 - float(q)
        x = r**3 * p0[0] + 3.0 * r * r * q * p1[0] + 3.0 * r * q * q * p2[0] + q**3 * p3[0]
        y = r**3 * p0[1] + 3.0 * r * r * q * p1[1] + 3.0 * r * q * q * p2[1] + q**3 * p3[1]
        result.append((float(x), float(y)))
    return tuple(result)


def _is_land(grid: np.ndarray, cell: Cell, water_code: int) -> bool:
    return int(grid[cell[1], cell[0]]) != int(water_code)


def reserve_terminal_before_rasterization_v27(
    stage4_terrain: Sequence[Sequence[int]],
    *,
    water_code: int,
    source_id: str,
    width_px: float,
    stream_order: int,
    seed: int,
    blocked_cells: Iterable[Cell] = (),
    preferred_near: Cell | None = None,
    preferred_tangent_bias_degrees: float = 0.0,
) -> TerminalReservationV27:
    """Select the final straight coast cell before routing/rasterization.

    The route search should target ``route_tail[0]`` and append the owned tail
    verbatim.  The mouth, its previous cell and its guard ring are unavailable
    to all other traces, which makes a confluence in the final cell impossible.
    """

    if abs(float(preferred_tangent_bias_degrees)) > 45.0 + 1e-9:
        raise ValueError("terminal tangent fallback must stay within +/-45 degrees")
    grid = np.asarray(stage4_terrain, dtype=np.int16)
    if grid.ndim != 2:
        raise ValueError("stage4 terrain must be a 2-D grid")
    height, width = grid.shape
    blocked = {(int(x) % width, int(y)) for x, y in blocked_cells}
    candidates: list[tuple[tuple[int, int, int, int, int], tuple[Cell, Cell, Cell, str]]] = []
    for y in range(height):
        for x in range(width):
            mouth = (x, y)
            if mouth in blocked or not _is_land(grid, mouth, water_code):
                continue
            for exit_index, exit_port in enumerate(CARDINAL_PORTS):
                sea = _neighbor(mouth, exit_port, width, height)
                if sea is None or int(grid[sea[1], sea[0]]) != int(water_code):
                    continue
                entry_port = OPPOSITE_PORT[exit_port]
                previous = _neighbor(mouth, entry_port, width, height)
                if previous is None or previous in blocked or not _is_land(grid, previous, water_code):
                    continue
                # Prefer a simple coast (one cardinal sea contact) because it
                # gives an authored delta one unambiguous outward normal.
                sea_contacts = sum(
                    _neighbor(mouth, name, width, height) is not None
                    and int(grid[_neighbor(mouth, name, width, height)[1], _neighbor(mouth, name, width, height)[0]]) == int(water_code)  # type: ignore[index]
                    for name in CARDINAL_PORTS
                )
                distance = 0 if preferred_near is None else _wrapped_manhattan(mouth, preferred_near, width)
                score = (
                    distance,
                    abs(sea_contacts - 1),
                    _stable_hash(seed, x, y, exit_index) & 0x7FFFFFFF,
                    y,
                    x,
                )
                candidates.append((score, (previous, mouth, exit_port)))
    if not candidates:
        raise ValueError("no land mouth owns a straight two-cell terminal corridor")
    _score, (previous, mouth, exit_port) = min(candidates, key=lambda item: item[0])
    sea = _neighbor(mouth, exit_port, width, height)
    assert sea is not None
    entry_port = OPPOSITE_PORT[exit_port]
    sea_ux, sea_uy = OCTANT_PORTS[exit_port]
    angle = math.radians(float(preferred_tangent_bias_degrees))
    ux = sea_ux * math.cos(angle) - sea_uy * math.sin(angle)
    uy = sea_ux * math.sin(angle) + sea_uy * math.cos(angle)
    ux, uy = _unit((ux, uy))
    center = _cell_center(mouth)
    entry_point = (center[0] - sea_ux * 0.5, center[1] - sea_uy * 0.5)
    shoreline = (center[0] + sea_ux * 0.5, center[1] + sea_uy * 0.5)
    split = (shoreline[0] - ux * 0.32, shoreline[1] - uy * 0.32)
    guards = []
    for name in CARDINAL_PORTS:
        item = _neighbor(mouth, name, width, height)
        if item is not None and item not in {previous, sea}:
            guards.append(item)
    spec = RiverTerminalSpecV27(
        mode="new_pre_raster_reserved",
        trace_id=None,
        source_id=str(source_id),
        river_cell=mouth,
        sea_cell=sea,
        approach_cells=(previous,),
        entry_port=entry_port,
        entry_reciprocal_port=exit_port,
        exit_port=exit_port,
        sea_reciprocal_port=OPPOSITE_PORT[exit_port],
        entry_point=entry_point,
        split_point=split,
        shoreline_point=shoreline,
        incoming_tangent=(ux, uy),
        width_px=float(width_px),
        stream_order=int(stream_order),
        asset_direction=_octant((ux, uy)),
        approach_angle_degrees=abs(float(preferred_tangent_bias_degrees)),
        coarse_port_turn_degrees=0.0,
        final_cell_confluences=0,
        strict_generator_contract=True,
        terrain_cells_changed=False,
        compatibility_reason=None,
    )
    reserved = tuple(dict.fromkeys((previous, mouth, *guards)))
    result = TerminalReservationV27(spec, (previous, mouth), reserved, tuple(guards), True)
    audit = audit_terminal_spec_v27(spec, width, height)
    if not audit.valid:
        raise AssertionError("invalid pre-raster terminal reservation: " + "; ".join(audit.errors))
    return result


def rasterize_reserved_route_v27(
    stage4_terrain: Sequence[Sequence[int]],
    route_prefix: Sequence[Cell],
    reservation: TerminalReservationV27,
    *,
    water_code: int,
    river_code: int,
) -> tuple[tuple[tuple[int, ...], ...], tuple[Cell, ...]]:
    """Rasterize a route only after its terminal tail has been reserved."""

    if not reservation.selected_before_rasterization:
        raise ValueError("terminal reservation must predate rasterization")
    grid = np.asarray(stage4_terrain, dtype=np.int16).copy()
    height, width = grid.shape
    route = [(int(x) % width, int(y)) for x, y in route_prefix]
    for cell in reservation.route_tail:
        if not route or route[-1] != cell:
            route.append(cell)
    if len(route) != len(set(route)):
        raise ValueError("reserved route contains a directed cycle/reused cell")
    for first, second in zip(route, route[1:]):
        if _wrapped_step(first, second, width) not in CARDINAL_PORTS.values():
            raise ValueError(f"non-cardinal raster edge {first}->{second}")
    for cell in route:
        if not 0 <= cell[1] < height or int(grid[cell[1], cell[0]]) == int(water_code):
            raise ValueError(f"route attempts to rasterize illegal cell {cell}")
        grid[cell[1], cell[0]] = int(river_code)
    mouth = reservation.spec.river_cell
    river_neighbors = [
        item
        for name in CARDINAL_PORTS
        if (item := _neighbor(mouth, name, width, height)) is not None
        and int(grid[item[1], item[0]]) == int(river_code)
    ]
    if river_neighbors != [reservation.route_tail[-2]]:
        raise ValueError(f"reserved mouth acquired extra river contacts: {river_neighbors}")
    return tuple(tuple(int(value) for value in row) for row in grid), tuple(route)


def _incoming_owners(world: Any, river_cell: Cell) -> set[int]:
    result: set[int] = set()
    for trace in world.traces:
        for _start, end in trace.raster_edges:
            if tuple(end) == tuple(river_cell):
                result.add(int(trace.trace_id))
    return result


def _legacy_tail_cells(trace: Any) -> tuple[Cell, ...]:
    cells = tuple((int(x), int(y)) for x, y in trace.raster_cells)
    if len(cells) < 2:
        raise ValueError(f"trace {trace.trace_id} has no terminal approach")
    return cells[max(0, len(cells) - 3) :]


def normalize_legacy_terminal_v27(world: Any, trace_id: int) -> LegacyTerminalNormalizationV27:
    """Fit an asset-facing tangent without changing any saved River cell.

    A legacy coarse 90-degree tail remains a legacy 90-degree tail.  The cubic
    merely spreads that bend across the existing last 1--2 cells and reaches a
    split point with a tangent parallel to the selected V18 asset direction.
    """

    trace = next((item for item in world.traces if int(item.trace_id) == int(trace_id)), None)
    mouth = next((item for item in world.mouths if int(item.trace_id) == int(trace_id)), None)
    if trace is None or mouth is None:
        raise ValueError(f"trace {trace_id} is not a coastal primary")
    if trace.termination != "coast":
        raise ValueError(f"trace {trace_id} does not terminate at a coast")
    width, height = int(world.world_width), int(world.world_height)
    tail = _legacy_tail_cells(trace)
    river_cell = tuple(mouth.river_cell)
    sea_cell = tuple(mouth.water_cell)
    previous = tail[-2]
    flow_step = _wrapped_step(previous, river_cell, width)
    sea_step = _wrapped_step(river_cell, sea_cell, width)
    flow_port = _port_for_step(flow_step)
    entry_port = OPPOSITE_PORT[flow_port]
    exit_port = _port_for_step(sea_step)
    coarse_turn = _angle(flow_step, sea_step)
    owners = _incoming_owners(world, river_cell)
    confluences = max(0, len(owners) - 1)

    shoreline = tuple(float(value) / float(world.tile_px) for value in mouth.shoreline_point)
    center = _cell_center(river_cell, shoreline[0], width)
    shoreline = (
        shoreline[0] + round((center[0] - shoreline[0]) / float(width)) * float(width),
        shoreline[1],
    )
    exit_unit = OCTANT_PORTS[exit_port]
    split = (shoreline[0] - exit_unit[0] * 0.32, shoreline[1] - exit_unit[1] * 0.32)
    start = _cell_center(tail[0], split[0], width)
    incoming = _unit(flow_step)
    span = max(math.hypot(split[0] - start[0], split[1] - start[1]), 0.75)
    first_control = (start[0] + incoming[0] * min(0.72, span * 0.42), start[1] + incoming[1] * min(0.72, span * 0.42))
    second_control = (
        split[0] - exit_unit[0] * min(0.54, span * 0.30),
        split[1] - exit_unit[1] * min(0.54, span * 0.30),
    )
    fitted = _bezier(start, first_control, second_control, split)
    fitted_tangent = _unit((fitted[-1][0] - fitted[-2][0], fitted[-1][1] - fitted[-2][1]))
    approach_angle = _angle(fitted_tangent, exit_unit)

    before = tuple(_cell_center(cell, split[0], width) for cell in tail) + (shoreline,)
    river_cells = tuple((int(x), int(y)) for x, y in world.river_cells)
    strict = coarse_turn <= 45.0 + 1e-9 and confluences == 0
    status = "generator_canonical" if strict else "legacy_subcell_fit"
    reason = None if strict else (
        f"saved entry {entry_port} -> sea exit {exit_port} turns {coarse_turn:.1f} degrees; "
        "Civ RIVER cells remain immutable"
    )
    # Existing channel SDF profiles store a radius-like half-width.  The
    # terminal contract is intentionally renderer-agnostic and publishes the
    # full bank-to-bank water width expected at the authored neck.
    width_px = 2.0 * max(float(trace.samples[-1].width_px), float(mouth.start_width))
    order = int(max(trace.samples[-1].strahler, mouth.strahler))
    source_cell = tuple(trace.source_cell)
    spec = RiverTerminalSpecV27(
        mode=status,
        trace_id=int(trace_id),
        source_id=f"snapshot-{world.seed}-trace-{trace_id}-source-{source_cell[0]}-{source_cell[1]}",
        river_cell=river_cell,
        sea_cell=sea_cell,
        approach_cells=tail[:-1],
        entry_port=entry_port,
        entry_reciprocal_port=flow_port,
        exit_port=exit_port,
        sea_reciprocal_port=OPPOSITE_PORT[exit_port],
        entry_point=(center[0] - flow_step[0] * 0.5, center[1] - flow_step[1] * 0.5),
        split_point=split,
        shoreline_point=shoreline,
        incoming_tangent=exit_unit,
        width_px=width_px,
        stream_order=order,
        asset_direction=exit_port,
        approach_angle_degrees=approach_angle,
        coarse_port_turn_degrees=coarse_turn,
        final_cell_confluences=confluences,
        strict_generator_contract=strict,
        terrain_cells_changed=False,
        compatibility_reason=reason,
    )
    result = LegacyTerminalNormalizationV27(
        spec=spec,
        before_points=before,
        after_body_points=fitted,
        original_river_cells=river_cells,
        normalized_river_cells=river_cells,
        repair_status=status,
        repair_actions=(
            "preserve-saved-river-cells",
            "replace-terminal-subcell-tangent-only",
            "continue-full-width-body-to-v18-split",
            "record-incompatible-coarse-port-turn",
        ),
        target_trace_cycle_before=len(set(trace.raster_cells)) != len(trace.raster_cells),
        target_trace_cycle_after=len(set(trace.raster_cells)) != len(trace.raster_cells),
    )
    audit = audit_legacy_normalization_v27(result, width, height)
    if not audit.valid:
        raise AssertionError("invalid legacy terminal normalization: " + "; ".join(audit.errors))
    return result


def build_round_spring_source_v27(
    *,
    source_id: str,
    source_cell: Cell,
    outflow_cell: Cell,
    world_width: int,
    world_height: int,
    width_px: float,
    stream_order: int = 1,
    lake_radius_cells: float = 0.16,
) -> SourceTerminalSpecV27:
    """Declare a small round spring lake with one connected outflow."""

    step = _wrapped_step(source_cell, outflow_cell, int(world_width))
    port = _port_for_step(step)
    if not 0 <= source_cell[1] < world_height or not 0 <= outflow_cell[1] < world_height:
        raise ValueError("source/outflow lies outside vertical world bounds")
    center = _cell_center(source_cell)
    unit = OCTANT_PORTS[port]
    return SourceTerminalSpecV27(
        source_id=str(source_id),
        source_cell=(int(source_cell[0]) % world_width, int(source_cell[1])),
        outflow_cell=(int(outflow_cell[0]) % world_width, int(outflow_cell[1])),
        lake_center=center,
        lake_radius_cells=float(lake_radius_cells),
        outflow_port=port,
        outflow_reciprocal_port=OPPOSITE_PORT[port],
        outflow_point=(center[0] + unit[0] * lake_radius_cells, center[1] + unit[1] * lake_radius_cells),
        outgoing_tangent=unit,
        width_px=float(width_px),
        stream_order=int(stream_order),
        asset_direction=port,
    )


def _reciprocal_ok(spec: RiverTerminalSpecV27, width: int, height: int) -> bool:
    previous = spec.approach_cells[-1]
    return (
        _neighbor(spec.river_cell, spec.entry_port, width, height) == previous
        and _neighbor(previous, spec.entry_reciprocal_port, width, height) == spec.river_cell
        and _neighbor(spec.river_cell, spec.exit_port, width, height) == spec.sea_cell
        and _neighbor(spec.sea_cell, spec.sea_reciprocal_port, width, height) == spec.river_cell
    )


def audit_terminal_spec_v27(spec: RiverTerminalSpecV27, width: int, height: int) -> TerminalAuditV27:
    errors: list[str] = []
    reciprocal = _reciprocal_ok(spec, width, height)
    if not reciprocal:
        errors.append("entry/exit ports are not reciprocal")
    if spec.approach_angle_degrees > 45.0 + 1e-8:
        errors.append("asset attachment approach exceeds 45 degrees")
    if spec.final_cell_confluences:
        errors.append("final mouth cell contains a confluence")
    if spec.terrain_cells_changed:
        errors.append("terminal metadata changed terrain cells")
    if spec.strict_generator_contract and spec.coarse_port_turn_degrees > 45.0 + 1e-8:
        errors.append("strict generator terminal contains a coarse 90-degree turn")
    if spec.asset_direction not in OCTANT_PORTS:
        errors.append("unknown eight-way asset direction")
    return TerminalAuditV27(
        not errors,
        tuple(errors),
        reciprocal,
        float(spec.approach_angle_degrees),
        int(spec.final_cell_confluences),
        bool(spec.terrain_cells_changed),
    )


def audit_legacy_normalization_v27(
    result: LegacyTerminalNormalizationV27,
    width: int,
    height: int,
) -> TerminalAuditV27:
    base = audit_terminal_spec_v27(result.spec, width, height)
    errors = list(base.errors)
    if result.original_river_cells != result.normalized_river_cells:
        errors.append("legacy normalization changed saved River cells")
    if result.target_trace_cycle_before != result.target_trace_cycle_after:
        errors.append("legacy normalization changed directed cycle status")
    if result.after_body_points:
        tangent = (
            result.after_body_points[-1][0] - result.after_body_points[-2][0],
            result.after_body_points[-1][1] - result.after_body_points[-2][1],
        )
        # Finite proof samples approximate the exact cubic endpoint
        # derivative.  At 160 segments the chord is within one degree.
        if _angle(tangent, result.spec.incoming_tangent) > 1.0:
            errors.append("fitted body does not reach the declared asset tangent")
    return TerminalAuditV27(
        not errors,
        tuple(errors),
        base.reciprocal_ports,
        base.approach_angle_degrees,
        base.final_cell_confluences,
        base.terrain_cells_changed,
    )


def project_points_to_window_v27(
    points: Sequence[Point],
    *,
    crop_x: int,
    crop_y: int,
    world_width: int,
    tile_px: int,
) -> tuple[Point, ...]:
    """Wrap-stable projection used by proofs and eventual renderer crops."""

    result = []
    for x, y in points:
        relative = (float(x) - float(crop_x)) % float(world_width)
        if relative > world_width * 0.5:
            relative -= world_width
        result.append((relative * tile_px, (float(y) - crop_y) * tile_px))
    return tuple(result)


def terminal_spec_dict_v27(spec: RiverTerminalSpecV27) -> dict[str, Any]:
    """JSON-ready public contract with all requested fields explicit."""

    return asdict(spec)


__all__ = [
    "CARDINAL_PORTS",
    "LegacyTerminalNormalizationV27",
    "RiverTerminalSpecV27",
    "SourceTerminalSpecV27",
    "TerminalAuditV27",
    "TerminalReservationV27",
    "audit_legacy_normalization_v27",
    "audit_terminal_spec_v27",
    "build_round_spring_source_v27",
    "normalize_legacy_terminal_v27",
    "project_points_to_window_v27",
    "rasterize_reserved_route_v27",
    "reserve_terminal_before_rasterization_v27",
    "terminal_spec_dict_v27",
]
