"""Component-wide, deterministic Civ river centreline metadata.

The v2/v3 prototypes authored each 96 px cell in isolation.  Their border
profiles were safe, but shape, width and material phase restarted in every
cell.  This module moves those decisions to the complete authoritative river
graph while retaining the non-negotiable Civ contract: every connection
crosses a cell boundary at its exact cardinal midpoint.

This is deliberately a geometry/planning module, not a renderer.  Callers pass
the authoritative river terrain cells plus the flow edges they want to retain
(the current OpenCivOne tree, or every cardinal raw adjacency).  The result is
world-space cubic Bezier metadata with:

* exact NESW midpoint ports;
* equal, collinear derivatives on both sides of every shared port (C1);
* component-wide station, phase and channel/bank width values;
* explicit source and mouth nodes;
* horizontal-world-wrap support; and
* deterministic crop views computed from the full component plan.

Cycle policy
------------
All supplied edges are retained.  A deterministic shortest-path scalar
potential from authored mouths (or a canonical fallback root) supplies station
and phase.  It is continuous at every graph node, including cycle closures, so
there is never a tile-border reset.  On a cyclic graph it is not possible to
interpret one scalar as unique downstream arclength around every loop.  Such
components therefore expose their cycle rank and deterministic cycle chords in
``GraphLimitationReport``.  A renderer may still use the continuous potential,
or later consume authored directed/discharge metadata without changing the
Bezier port contract.

Chunk determinism requires full component authority.  Plan once from the full
world graph and use :meth:`RiverPlan.crop`, or pass ``window=`` to
:func:`plan_river_components` (which performs the same full plan first).
Planning an isolated crop without the outside graph cannot in general recover
the same roots, cycles or station values and is intentionally not claimed to
be equivalent.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, replace
import heapq
import math
from typing import Final, Iterable, Mapping, Sequence

import numpy as np


Cell = tuple[int, int]
Direction = tuple[int, int]
Point = tuple[float, float]

N: Final[int] = 1
E: Final[int] = 2
S: Final[int] = 4
W: Final[int] = 8

BIT_DIRECTIONS: Final[dict[int, Direction]] = {
    N: (0, -1),
    E: (1, 0),
    S: (0, 1),
    W: (-1, 0),
}
DIRECTION_BITS: Final[dict[Direction, int]] = {
    direction: bit for bit, direction in BIT_DIRECTIONS.items()
}
CARDINAL_ORDER: Final[tuple[int, ...]] = (N, E, S, W)
_DIRECTION_NAMES: Final[dict[Direction, str]] = {
    (0, -1): "N",
    (1, 0): "E",
    (0, 1): "S",
    (-1, 0): "W",
}
_NAME_DIRECTIONS: Final[dict[str, Direction]] = {
    name: direction for direction, name in _DIRECTION_NAMES.items()
}


def _cell_key(cell: Cell) -> tuple[int, int]:
    return int(cell[1]), int(cell[0])


def _point_add(a: Point, b: Point) -> Point:
    return float(a[0] + b[0]), float(a[1] + b[1])


def _point_sub(a: Point, b: Point) -> Point:
    return float(a[0] - b[0]), float(a[1] - b[1])


def _point_scale(point: Point, scale: float) -> Point:
    return float(point[0] * scale), float(point[1] * scale)


def _point_length(point: Point) -> float:
    return math.hypot(float(point[0]), float(point[1]))


def _normalise(point: Point, fallback: Point = (1.0, 0.0)) -> Point:
    length = _point_length(point)
    if length <= 1.0e-12:
        return fallback
    return float(point[0] / length), float(point[1] / length)


def _rotate(point: Point, angle: float) -> Point:
    cosine = math.cos(angle)
    sine = math.sin(angle)
    return (
        float(point[0] * cosine - point[1] * sine),
        float(point[0] * sine + point[1] * cosine),
    )


def _hash32(seed: int, x: int, y: int, salt: int = 0) -> int:
    """Small stable integer hash; never use Python's process-randomised hash."""
    value = (
        int(seed)
        ^ (int(x) * 0x9E3779B1)
        ^ (int(y) * 0x85EBCA77)
        ^ (int(salt) * 0xC2B2AE3D)
    ) & 0xFFFFFFFF
    value ^= value >> 16
    value = (value * 0x7FEB352D) & 0xFFFFFFFF
    value ^= value >> 15
    value = (value * 0x846CA68B) & 0xFFFFFFFF
    return (value ^ (value >> 16)) & 0xFFFFFFFF


def _unit_hash(seed: int, x: int, y: int, salt: int) -> float:
    return _hash32(seed, x, y, salt) / 4294967295.0


@dataclass(frozen=True, order=True)
class FlowEdge:
    """One retained undirected cardinal connection between river cells."""

    a: Cell
    b: Cell


@dataclass(frozen=True, order=True)
class MouthSpec:
    """An authored river-cell exit toward one adjacent sea cell."""

    cell: Cell
    direction: Direction


@dataclass(frozen=True)
class CellWindow:
    """A non-wrapping Y / horizontally wrapping world-cell window."""

    x0: int
    y0: int
    width: int
    height: int

    def validate(self, world_width: int) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("window width and height must be positive")
        if self.width > world_width:
            raise ValueError("window width cannot exceed horizontal world width")

    def contains(self, cell: Cell, world_width: int) -> bool:
        self.validate(world_width)
        dx = (int(cell[0]) - int(self.x0)) % int(world_width)
        return dx < self.width and self.y0 <= int(cell[1]) < self.y0 + self.height


@dataclass(frozen=True)
class RiverNode:
    """A port, junction or source with component-continuous paint metadata."""

    node_id: str
    component_id: str
    kind: str
    point_px: Point
    cells: tuple[Cell, ...]
    station_px: float
    phase: float
    channel_width_px: float
    bank_width_px: float


@dataclass(frozen=True)
class BezierSegment:
    """One cubic centreline owned by exactly one authoritative Civ cell."""

    segment_id: str
    component_id: str
    owner_cell: Cell
    kind: str
    start_node: str
    end_node: str
    p0: Point
    p1: Point
    p2: Point
    p3: Point
    length_px: float
    station_start_px: float
    station_end_px: float
    phase_start: float
    phase_end: float
    channel_width_start_px: float
    channel_width_end_px: float
    bank_width_start_px: float
    bank_width_end_px: float

    def point(self, t: float) -> Point:
        """Evaluate the cubic at ``t`` in ``[0, 1]``."""
        t = min(1.0, max(0.0, float(t)))
        u = 1.0 - t
        x = (
            u * u * u * self.p0[0]
            + 3.0 * u * u * t * self.p1[0]
            + 3.0 * u * t * t * self.p2[0]
            + t * t * t * self.p3[0]
        )
        y = (
            u * u * u * self.p0[1]
            + 3.0 * u * u * t * self.p1[1]
            + 3.0 * u * t * t * self.p2[1]
            + t * t * t * self.p3[1]
        )
        return float(x), float(y)

    def derivative(self, t: float) -> Point:
        """Evaluate the first derivative of the cubic."""
        t = min(1.0, max(0.0, float(t)))
        u = 1.0 - t
        first = _point_scale(_point_sub(self.p1, self.p0), 3.0 * u * u)
        second = _point_scale(_point_sub(self.p2, self.p1), 6.0 * u * t)
        third = _point_scale(_point_sub(self.p3, self.p2), 3.0 * t * t)
        return _point_add(_point_add(first, second), third)

    def node_endpoint(self, node_id: str) -> tuple[Point, Point, str]:
        """Return ``(endpoint, adjacent_control, side)`` for one endpoint."""
        if node_id == self.start_node:
            return self.p0, self.p1, "start"
        if node_id == self.end_node:
            return self.p3, self.p2, "end"
        raise KeyError(f"segment {self.segment_id} does not touch node {node_id}")

    def value_at(self, t: float, start: float, end: float) -> float:
        """Linearly interpolate station-derived metadata along this segment."""
        t = min(1.0, max(0.0, float(t)))
        return float(start * (1.0 - t) + end * t)


@dataclass(frozen=True)
class PortContinuity:
    """Inspectable C1 contract at one shared cell boundary."""

    node_id: str
    edge: FlowEdge
    canonical_point_px: Point
    segment_a: str
    segment_b: str
    outward_derivative_a: Point
    outward_derivative_b: Point
    error_px: float


@dataclass(frozen=True)
class SourceEndpoint:
    cell: Cell
    node_id: str
    point_px: Point
    is_phase_root: bool


@dataclass(frozen=True)
class MouthEndpoint:
    cell: Cell
    direction: Direction
    node_id: str
    point_px: Point
    is_phase_root: bool


@dataclass(frozen=True)
class GraphLimitationReport:
    """Honest topology facts a later flow/discharge model must resolve."""

    cycle_rank: int
    cycle_edges: tuple[FlowEdge, ...]
    has_authored_mouth: bool
    mouth_count: int
    root_policy: str
    phase_policy: str
    notes: tuple[str, ...]


@dataclass(frozen=True)
class RiverComponentGeometry:
    component_id: str
    cells: tuple[Cell, ...]
    visible_cells: tuple[Cell, ...]
    flow_edges: tuple[FlowEdge, ...]
    mouths: tuple[MouthEndpoint, ...]
    sources: tuple[SourceEndpoint, ...]
    nodes: tuple[RiverNode, ...]
    segments: tuple[BezierSegment, ...]
    port_continuity: tuple[PortContinuity, ...]
    phase_origin: float
    wavelength_px: float
    roots: tuple[str, ...]
    limitations: GraphLimitationReport

    def node_map(self) -> dict[str, RiverNode]:
        return {node.node_id: node for node in self.nodes}

    def segment_map(self) -> dict[str, BezierSegment]:
        return {segment.segment_id: segment for segment in self.segments}


@dataclass(frozen=True)
class RiverPlan:
    """Complete or cropped deterministic geometry for one authoritative world."""

    tile_px: int
    world_width: int
    seed: int
    components: tuple[RiverComponentGeometry, ...]
    window: CellWindow | None = None

    @property
    def segments(self) -> tuple[BezierSegment, ...]:
        return tuple(segment for component in self.components for segment in component.segments)

    @property
    def nodes(self) -> tuple[RiverNode, ...]:
        return tuple(node for component in self.components for node in component.nodes)

    @property
    def cycle_rank(self) -> int:
        return sum(component.limitations.cycle_rank for component in self.components)

    def crop(self, window: CellWindow | tuple[int, int, int, int]) -> "RiverPlan":
        """Return a view without recomputing topology, roots, phase or widths."""
        window = _coerce_window(window)
        window.validate(self.world_width)
        cropped_components: list[RiverComponentGeometry] = []
        for component in self.components:
            visible = tuple(
                cell for cell in component.cells if window.contains(cell, self.world_width)
            )
            if not visible:
                continue
            visible_set = set(visible)
            segments = tuple(
                segment for segment in component.segments if segment.owner_cell in visible_set
            )
            referenced = {
                node_id
                for segment in segments
                for node_id in (segment.start_node, segment.end_node)
            }
            # Preserve an isolated source node even though it has no segment.
            referenced.update(
                source.node_id for source in component.sources if source.cell in visible_set
            )
            nodes = tuple(node for node in component.nodes if node.node_id in referenced)
            mouths = tuple(mouth for mouth in component.mouths if mouth.cell in visible_set)
            sources = tuple(source for source in component.sources if source.cell in visible_set)
            continuity = tuple(
                item for item in component.port_continuity if item.node_id in referenced
            )
            cropped_components.append(
                replace(
                    component,
                    visible_cells=visible,
                    mouths=mouths,
                    sources=sources,
                    nodes=nodes,
                    segments=segments,
                    port_continuity=continuity,
                )
            )
        return RiverPlan(
            tile_px=self.tile_px,
            world_width=self.world_width,
            seed=self.seed,
            components=tuple(cropped_components),
            window=window,
        )


@dataclass(frozen=True)
class _PortRef:
    node_id: str
    direction: Direction
    local_point: Point
    canonical_point: Point
    handle_px: float
    kind: str


@dataclass(frozen=True)
class _NodeDraft:
    node_id: str
    kind: str
    point_px: Point
    cells: tuple[Cell, ...]


@dataclass(frozen=True)
class _SegmentDraft:
    segment_id: str
    owner_cell: Cell
    kind: str
    start_node: str
    end_node: str
    p0: Point
    p1: Point
    p2: Point
    p3: Point
    length_px: float


def _coerce_window(window: CellWindow | tuple[int, int, int, int]) -> CellWindow:
    if isinstance(window, CellWindow):
        return window
    if len(window) != 4:
        raise ValueError("window must be CellWindow or (x0, y0, width, height)")
    return CellWindow(*(int(value) for value in window))


def _coerce_direction(value: Direction | str) -> Direction:
    if isinstance(value, str):
        try:
            return _NAME_DIRECTIONS[value.upper()]
        except KeyError as exc:
            raise ValueError(f"unknown mouth direction {value!r}") from exc
    direction = int(value[0]), int(value[1])
    if direction not in DIRECTION_BITS:
        raise ValueError(f"direction must be cardinal NESW, got {direction}")
    return direction


def _terrain_cells(
    raw_grid: np.ndarray,
    river_value: int,
    world_x0: int,
    world_y0: int,
    world_width: int,
) -> tuple[set[Cell], dict[Cell, int]]:
    terrain = np.asarray(raw_grid)
    if terrain.ndim != 2:
        raise ValueError("raw_grid must be a 2-D terrain array")
    if terrain.shape[1] > world_width:
        raise ValueError("raw_grid width cannot exceed horizontal world width")
    mapping: dict[Cell, int] = {}
    for local_y in range(terrain.shape[0]):
        for local_x in range(terrain.shape[1]):
            cell = (
                (int(world_x0) + local_x) % world_width,
                int(world_y0) + local_y,
            )
            if cell in mapping:
                raise ValueError("raw_grid maps duplicate horizontal world cells")
            mapping[cell] = int(terrain[local_y, local_x])
    rivers = {cell for cell, value in mapping.items() if value == int(river_value)}
    return rivers, mapping


def _cardinal_direction(a: Cell, b: Cell, world_width: int) -> Direction:
    ax, ay = a
    bx, by = b
    if ay == by:
        if (ax + 1) % world_width == bx:
            return 1, 0
        if (ax - 1) % world_width == bx:
            return -1, 0
    if ax == bx and by - ay in (-1, 1):
        return 0, int(by - ay)
    raise ValueError(f"flow edge {a!r} -> {b!r} is not cardinal (with X wrap)")


def _canonical_edge(a: Cell, b: Cell, world_width: int) -> FlowEdge:
    _cardinal_direction(a, b, world_width)
    return FlowEdge(a, b) if _cell_key(a) <= _cell_key(b) else FlowEdge(b, a)


def _normalise_edges(
    flow_edges: Iterable[FlowEdge | Sequence[Cell] | frozenset[Cell]],
    river_cells: set[Cell],
    world_width: int,
) -> tuple[FlowEdge, ...]:
    result: set[FlowEdge] = set()
    for raw_edge in flow_edges:
        if isinstance(raw_edge, FlowEdge):
            a, b = raw_edge.a, raw_edge.b
        else:
            cells = tuple(raw_edge)
            if len(cells) != 2:
                raise ValueError(f"flow edge must contain exactly two cells, got {raw_edge!r}")
            a, b = cells
        a = int(a[0]) % world_width, int(a[1])
        b = int(b[0]) % world_width, int(b[1])
        if a == b:
            raise ValueError(f"flow edge cannot connect a cell to itself: {a}")
        if a not in river_cells or b not in river_cells:
            raise ValueError(f"flow edge {a!r}-{b!r} must connect two river cells")
        result.add(_canonical_edge(a, b, world_width))
    return tuple(sorted(result, key=lambda edge: (_cell_key(edge.a), _cell_key(edge.b))))


def _normalise_mouths(
    mouths: Mapping[Cell, Direction | str] | Iterable[MouthSpec] | None,
    river_cells: set[Cell],
    terrain: Mapping[Cell, int],
    world_width: int,
    water_value: int,
) -> tuple[MouthSpec, ...]:
    if mouths is None:
        return ()
    if isinstance(mouths, Mapping):
        values = (MouthSpec(cell, _coerce_direction(direction)) for cell, direction in mouths.items())
    else:
        values = (
            item if isinstance(item, MouthSpec) else MouthSpec(item[0], _coerce_direction(item[1]))
            for item in mouths
        )
    result: set[MouthSpec] = set()
    for item in values:
        cell = int(item.cell[0]) % world_width, int(item.cell[1])
        direction = _coerce_direction(item.direction)
        if cell not in river_cells:
            raise ValueError(f"mouth owner {cell!r} is not a river cell")
        neighbour = (
            (cell[0] + direction[0]) % world_width,
            cell[1] + direction[1],
        )
        if neighbour in river_cells:
            raise ValueError(f"mouth {cell!r} {direction!r} points into another river cell")
        if neighbour in terrain and int(terrain[neighbour]) != int(water_value):
            raise ValueError(
                f"mouth {cell!r} {direction!r} must face water value {water_value}, "
                f"got {terrain[neighbour]}"
            )
        result.add(MouthSpec(cell, direction))
    return tuple(sorted(result, key=lambda mouth: (_cell_key(mouth.cell), DIRECTION_BITS[mouth.direction])))


def all_cardinal_flow_edges(
    raw_grid: np.ndarray,
    *,
    river_value: int = 11,
    world_x0: int = 0,
    world_y0: int = 0,
    world_width: int | None = None,
    horizontal_wrap: bool = True,
) -> tuple[FlowEdge, ...]:
    """Return every E/S raw river adjacency exactly once.

    This helper is useful for auditing rectangular/cyclic raw components.  It
    does not claim those adjacencies are authored hydrological flow.
    """
    grid = np.asarray(raw_grid)
    if grid.ndim != 2:
        raise ValueError("raw_grid must be a 2-D terrain array")
    if world_width is None:
        world_width = int(grid.shape[1])
    if world_width <= 1:
        raise ValueError("world_width must be at least 2")
    river_cells, _ = _terrain_cells(grid, river_value, world_x0, world_y0, world_width)
    edges: set[FlowEdge] = set()
    for cell in sorted(river_cells, key=_cell_key):
        x, y = cell
        east = ((x + 1) % world_width, y)
        south = (x, y + 1)
        if east in river_cells and (horizontal_wrap or x + 1 < world_width):
            edges.add(_canonical_edge(cell, east, world_width))
        if south in river_cells:
            edges.add(_canonical_edge(cell, south, world_width))
    return tuple(sorted(edges, key=lambda edge: (_cell_key(edge.a), _cell_key(edge.b))))


def _components(river_cells: set[Cell], edges: tuple[FlowEdge, ...]) -> list[tuple[Cell, ...]]:
    neighbours: dict[Cell, set[Cell]] = {cell: set() for cell in river_cells}
    for edge in edges:
        neighbours[edge.a].add(edge.b)
        neighbours[edge.b].add(edge.a)
    unseen = set(river_cells)
    result: list[tuple[Cell, ...]] = []
    while unseen:
        start = min(unseen, key=_cell_key)
        unseen.remove(start)
        queue = deque([start])
        found: list[Cell] = []
        while queue:
            cell = queue.popleft()
            found.append(cell)
            for neighbour in sorted(neighbours[cell], key=_cell_key):
                if neighbour in unseen:
                    unseen.remove(neighbour)
                    queue.append(neighbour)
        result.append(tuple(sorted(found, key=_cell_key)))
    return result


def _edge_node_id(edge: FlowEdge) -> str:
    return (
        f"port:y{edge.a[1]}x{edge.a[0]}"
        f"-y{edge.b[1]}x{edge.b[0]}"
    )


def _mouth_node_id(mouth: MouthSpec) -> str:
    return f"mouth:y{mouth.cell[1]}x{mouth.cell[0]}:{_DIRECTION_NAMES[mouth.direction]}"


def _junction_node_id(cell: Cell) -> str:
    return f"junction:y{cell[1]}x{cell[0]}"


def _source_node_id(cell: Cell) -> str:
    return f"source:y{cell[1]}x{cell[0]}"


def _canonical_port_point(cell: Cell, direction: Direction, tile_px: int, world_width: int) -> Point:
    x, y = cell
    dx, dy = direction
    world_px = float(world_width * tile_px)
    px = ((x + 0.5 + dx * 0.5) * tile_px) % world_px
    py = (y + 0.5 + dy * 0.5) * tile_px
    if abs(px - world_px) < 1.0e-9:
        px = 0.0
    return float(px), float(py)


def _local_port_point(cell: Cell, direction: Direction, tile_px: int) -> Point:
    x, y = cell
    dx, dy = direction
    return (
        float((x + 0.5 + dx * 0.5) * tile_px),
        float((y + 0.5 + dy * 0.5) * tile_px),
    )


def _port_handle(seed: int, tile_px: int, edge: FlowEdge | None, mouth: MouthSpec | None) -> float:
    if edge is not None:
        value = _hash32(
            seed,
            edge.a[0] * 257 + edge.b[0],
            edge.a[1] * 257 + edge.b[1],
            3101,
        )
    elif mouth is not None:
        bit = DIRECTION_BITS[mouth.direction]
        value = _hash32(seed, mouth.cell[0], mouth.cell[1], 3203 + bit * 17)
    else:
        raise ValueError("edge or mouth required for a port handle")
    unit = value / 4294967295.0
    return float(tile_px * (0.225 + unit * 0.040))


def _component_cycle_edges(cells: tuple[Cell, ...], edges: tuple[FlowEdge, ...]) -> tuple[FlowEdge, ...]:
    parent = {cell: cell for cell in cells}

    def find(cell: Cell) -> Cell:
        while parent[cell] != cell:
            parent[cell] = parent[parent[cell]]
            cell = parent[cell]
        return cell

    cycle: list[FlowEdge] = []
    for edge in edges:
        a_root, b_root = find(edge.a), find(edge.b)
        if a_root == b_root:
            cycle.append(edge)
            continue
        if _cell_key(a_root) <= _cell_key(b_root):
            parent[b_root] = a_root
        else:
            parent[a_root] = b_root
    return tuple(cycle)


def _topology_distances(
    cells: tuple[Cell, ...],
    edges: tuple[FlowEdge, ...],
    mouths: tuple[MouthSpec, ...],
) -> dict[Cell, int]:
    neighbours: dict[Cell, list[Cell]] = {cell: [] for cell in cells}
    for edge in edges:
        neighbours[edge.a].append(edge.b)
        neighbours[edge.b].append(edge.a)
    degree_one = [cell for cell in cells if len(neighbours[cell]) <= 1]
    roots = sorted({mouth.cell for mouth in mouths}, key=_cell_key)
    if not roots:
        roots = [min(degree_one or list(cells), key=_cell_key)]
    distance: dict[Cell, int] = {cell: 0 for cell in roots}
    queue = deque(roots)
    while queue:
        cell = queue.popleft()
        for neighbour in sorted(neighbours[cell], key=_cell_key):
            if neighbour not in distance:
                distance[neighbour] = distance[cell] + 1
                queue.append(neighbour)
    return distance


def _clamp_to_cell(point: Point, cell: Cell, tile_px: int, margin: float = 0.18) -> Point:
    x, y = cell
    low_x = (x + margin) * tile_px
    high_x = (x + 1.0 - margin) * tile_px
    low_y = (y + margin) * tile_px
    high_y = (y + 1.0 - margin) * tile_px
    return (
        float(min(high_x, max(low_x, point[0]))),
        float(min(high_y, max(low_y, point[1]))),
    )


def _cubic_point(p0: Point, p1: Point, p2: Point, p3: Point, t: float) -> Point:
    u = 1.0 - t
    return (
        float(u**3 * p0[0] + 3.0 * u * u * t * p1[0] + 3.0 * u * t * t * p2[0] + t**3 * p3[0]),
        float(u**3 * p0[1] + 3.0 * u * u * t * p1[1] + 3.0 * u * t * t * p2[1] + t**3 * p3[1]),
    )


def _cubic_length(p0: Point, p1: Point, p2: Point, p3: Point, steps: int = 28) -> float:
    previous = p0
    total = 0.0
    for index in range(1, steps + 1):
        point = _cubic_point(p0, p1, p2, p3, index / steps)
        total += _point_length(_point_sub(point, previous))
        previous = point
    return float(total)


def _draft_segment(
    segment_id: str,
    owner_cell: Cell,
    kind: str,
    start_node: str,
    end_node: str,
    p0: Point,
    p1: Point,
    p2: Point,
    p3: Point,
) -> _SegmentDraft:
    return _SegmentDraft(
        segment_id=segment_id,
        owner_cell=owner_cell,
        kind=kind,
        start_node=start_node,
        end_node=end_node,
        p0=p0,
        p1=p1,
        p2=p2,
        p3=p3,
        length_px=_cubic_length(p0, p1, p2, p3),
    )


def _phase_geometry(
    cell: Cell,
    topology_distance: int,
    phase_origin: float,
) -> float:
    x, y = cell
    broad_world_wave = 0.19 * math.sin(x * 0.31 + y * 0.17 + phase_origin * 0.47)
    return float(phase_origin + topology_distance * 0.73 + broad_world_wave)


def _make_cell_geometry(
    component_id: str,
    cell: Cell,
    ports: list[_PortRef],
    topology_distance: int,
    phase_origin: float,
    tile_px: int,
) -> tuple[list[_NodeDraft], list[_SegmentDraft], SourceEndpoint | None]:
    """Create curves inside one cell; all port controls remain inside it."""
    ports = sorted(ports, key=lambda port: DIRECTION_BITS[port.direction])
    x, y = cell
    centre = ((x + 0.5) * tile_px, (y + 0.5) * tile_px)
    phase = _phase_geometry(cell, topology_distance, phase_origin)
    nodes: list[_NodeDraft] = []
    segments: list[_SegmentDraft] = []

    if not ports:
        source_id = _source_node_id(cell)
        source_point = _clamp_to_cell(
            (
                centre[0] + math.sin(phase) * tile_px * 0.045,
                centre[1] + math.cos(phase * 0.83) * tile_px * 0.045,
            ),
            cell,
            tile_px,
        )
        nodes.append(_NodeDraft(source_id, "isolated_source", source_point, (cell,)))
        return nodes, segments, SourceEndpoint(cell, source_id, source_point, False)

    if len(ports) == 1:
        port = ports[0]
        source_id = _source_node_id(cell)
        inward = (-port.direction[0], -port.direction[1])
        side = (-inward[1], inward[0])
        source_point = _clamp_to_cell(
            (
                centre[0] + side[0] * math.sin(phase) * tile_px * 0.055,
                centre[1] + side[1] * math.sin(phase) * tile_px * 0.055,
            ),
            cell,
            tile_px,
        )
        nodes.append(_NodeDraft(source_id, "source", source_point, (cell,)))
        p0 = port.local_point
        p1 = _point_add(p0, _point_scale(inward, port.handle_px))
        toward_port = _normalise(_point_sub(p0, source_point))
        p3 = source_point
        p2 = _point_add(p3, _point_scale(toward_port, tile_px * 0.115))
        segments.append(
            _draft_segment(
                f"seg:y{y}x{x}:source",
                cell,
                "source_arm",
                port.node_id,
                source_id,
                p0,
                p1,
                p2,
                p3,
            )
        )
        return nodes, segments, SourceEndpoint(cell, source_id, source_point, False)

    junction_id = _junction_node_id(cell)
    if len(ports) == 2:
        first, second = ports
        chord = _normalise(_point_sub(second.local_point, first.local_point))
        side = (-chord[1], chord[0])
        amplitude = tile_px * (0.035 + 0.022 * (0.5 + 0.5 * math.sin(phase * 0.61)))
        along = tile_px * 0.014 * math.cos(phase * 0.79)
        junction = _clamp_to_cell(
            (
                centre[0] + side[0] * amplitude * math.sin(phase) + chord[0] * along,
                centre[1] + side[1] * amplitude * math.sin(phase) + chord[1] * along,
            ),
            cell,
            tile_px,
        )
        tangent = _rotate(chord, 0.10 * math.sin(phase * 0.71 + 0.4))
        junction_handle = tile_px * (0.115 + 0.018 * (0.5 + 0.5 * math.cos(phase)))
        nodes.append(_NodeDraft(junction_id, "through_junction", junction, (cell,)))

        inward_first = (-first.direction[0], -first.direction[1])
        p0 = first.local_point
        p1 = _point_add(p0, _point_scale(inward_first, first.handle_px))
        p3 = junction
        p2 = _point_sub(p3, _point_scale(tangent, junction_handle))
        segments.append(
            _draft_segment(
                f"seg:y{y}x{x}:through-a",
                cell,
                "through_a",
                first.node_id,
                junction_id,
                p0,
                p1,
                p2,
                p3,
            )
        )

        inward_second = (-second.direction[0], -second.direction[1])
        p0 = junction
        p1 = _point_add(p0, _point_scale(tangent, junction_handle))
        p3 = second.local_point
        p2 = _point_add(p3, _point_scale(inward_second, second.handle_px))
        segments.append(
            _draft_segment(
                f"seg:y{y}x{x}:through-b",
                cell,
                "through_b",
                junction_id,
                second.node_id,
                p0,
                p1,
                p2,
                p3,
            )
        )
        return nodes, segments, None

    junction = _clamp_to_cell(
        (
            centre[0] + math.sin(phase) * tile_px * 0.038,
            centre[1] + math.cos(phase * 0.83) * tile_px * 0.038,
        ),
        cell,
        tile_px,
    )
    nodes.append(_NodeDraft(junction_id, "branch_junction", junction, (cell,)))
    for index, port in enumerate(ports):
        inward = (-port.direction[0], -port.direction[1])
        p0 = port.local_point
        p1 = _point_add(p0, _point_scale(inward, port.handle_px))
        toward_port = _normalise(_point_sub(p0, junction))
        side = (-toward_port[1], toward_port[0])
        bend = math.sin(phase + index * 1.37) * tile_px * 0.018
        p3 = junction
        p2 = _point_add(
            _point_add(p3, _point_scale(toward_port, tile_px * 0.105)),
            _point_scale(side, bend),
        )
        segments.append(
            _draft_segment(
                f"seg:y{y}x{x}:branch-{_DIRECTION_NAMES[port.direction].lower()}",
                cell,
                "branch_arm",
                port.node_id,
                junction_id,
                p0,
                p1,
                p2,
                p3,
            )
        )
    return nodes, segments, None


def _node_stations(
    nodes: Mapping[str, _NodeDraft],
    segments: Sequence[_SegmentDraft],
    roots: tuple[str, ...],
) -> dict[str, float]:
    adjacency: dict[str, list[tuple[str, float, str]]] = defaultdict(list)
    for segment in segments:
        adjacency[segment.start_node].append((segment.end_node, segment.length_px, segment.segment_id))
        adjacency[segment.end_node].append((segment.start_node, segment.length_px, segment.segment_id))
    distance = {node_id: math.inf for node_id in nodes}
    queue: list[tuple[float, str]] = []
    for root in roots:
        distance[root] = 0.0
        heapq.heappush(queue, (0.0, root))
    while queue:
        current, node_id = heapq.heappop(queue)
        if current > distance[node_id] + 1.0e-10:
            continue
        for neighbour, length, segment_id in sorted(adjacency[node_id], key=lambda item: (item[0], item[2])):
            candidate = current + length
            if candidate + 1.0e-10 < distance[neighbour]:
                distance[neighbour] = candidate
                heapq.heappush(queue, (candidate, neighbour))
    # An isolated source is itself a root; this is defensive for malformed
    # caller topology while keeping metadata finite and inspectable.
    for node_id, value in tuple(distance.items()):
        if not math.isfinite(value):
            distance[node_id] = 0.0
    return distance


def _widths(tile_px: int, station: float, max_station: float, phase: float) -> tuple[float, float]:
    upstream = 0.0 if max_station <= 1.0e-9 else station / max_station
    # Mouth/root is broadest; upstream narrows gradually.  The low-frequency
    # phase term is evaluated from the component station, never local tile t.
    base = tile_px * (0.071 - 0.014 * upstream)
    modulation = 1.0 + 0.048 * math.sin(phase * 0.43 + 0.7)
    channel = max(2.5, base * modulation)
    bank = channel + tile_px * (0.050 + 0.006 * math.cos(phase * 0.31 - 0.4))
    return float(channel), float(bank)


def _outward_derivative(segment: _SegmentDraft | BezierSegment, node_id: str) -> Point:
    if segment.start_node == node_id:
        return _point_scale(_point_sub(segment.p0, segment.p1), 3.0)
    if segment.end_node == node_id:
        return _point_scale(_point_sub(segment.p3, segment.p2), 3.0)
    raise KeyError(f"segment {segment.segment_id} does not touch {node_id}")


def _build_component(
    cells: tuple[Cell, ...],
    all_edges: tuple[FlowEdge, ...],
    all_mouths: tuple[MouthSpec, ...],
    *,
    tile_px: int,
    world_width: int,
    seed: int,
) -> RiverComponentGeometry:
    cell_set = set(cells)
    edges = tuple(edge for edge in all_edges if edge.a in cell_set and edge.b in cell_set)
    mouths = tuple(mouth for mouth in all_mouths if mouth.cell in cell_set)
    anchor = min(cells, key=_cell_key)
    component_id = f"river-y{anchor[1]:03d}-x{anchor[0]:03d}"
    phase_origin = _unit_hash(seed, anchor[0], anchor[1], 4001) * math.tau
    wavelength_px = tile_px * (
        3.6 + _unit_hash(seed, anchor[0], anchor[1], 4003) * 1.8
    )

    edge_by_cell: dict[Cell, list[tuple[FlowEdge, Direction]]] = defaultdict(list)
    for edge in edges:
        direction = _cardinal_direction(edge.a, edge.b, world_width)
        edge_by_cell[edge.a].append((edge, direction))
        edge_by_cell[edge.b].append((edge, (-direction[0], -direction[1])))
    mouth_by_cell: dict[Cell, list[MouthSpec]] = defaultdict(list)
    for mouth in mouths:
        mouth_by_cell[mouth.cell].append(mouth)

    topology_distance = _topology_distances(cells, edges, mouths)
    node_drafts: dict[str, _NodeDraft] = {}
    segment_drafts: list[_SegmentDraft] = []
    source_drafts: list[SourceEndpoint] = []
    port_refs_by_cell: dict[Cell, list[_PortRef]] = defaultdict(list)
    edge_node_ids: dict[FlowEdge, str] = {}

    for edge in edges:
        node_id = _edge_node_id(edge)
        edge_node_ids[edge] = node_id
        direction = _cardinal_direction(edge.a, edge.b, world_width)
        point = _canonical_port_point(edge.a, direction, tile_px, world_width)
        node_drafts[node_id] = _NodeDraft(node_id, "edge_port", point, (edge.a, edge.b))
        handle = _port_handle(seed, tile_px, edge, None)
        for cell, outward in (
            (edge.a, direction),
            (edge.b, (-direction[0], -direction[1])),
        ):
            port_refs_by_cell[cell].append(
                _PortRef(
                    node_id=node_id,
                    direction=outward,
                    local_point=_local_port_point(cell, outward, tile_px),
                    canonical_point=point,
                    handle_px=handle,
                    kind="edge",
                )
            )

    mouth_node_ids: dict[MouthSpec, str] = {}
    for mouth in mouths:
        node_id = _mouth_node_id(mouth)
        mouth_node_ids[mouth] = node_id
        point = _canonical_port_point(mouth.cell, mouth.direction, tile_px, world_width)
        node_drafts[node_id] = _NodeDraft(node_id, "mouth_port", point, (mouth.cell,))
        port_refs_by_cell[mouth.cell].append(
            _PortRef(
                node_id=node_id,
                direction=mouth.direction,
                local_point=_local_port_point(mouth.cell, mouth.direction, tile_px),
                canonical_point=point,
                handle_px=_port_handle(seed, tile_px, None, mouth),
                kind="mouth",
            )
        )

    for cell in cells:
        directions = [port.direction for port in port_refs_by_cell[cell]]
        if len(directions) != len(set(directions)):
            raise ValueError(f"cell {cell} has duplicate edge/mouth directions")
        new_nodes, new_segments, source = _make_cell_geometry(
            component_id,
            cell,
            port_refs_by_cell[cell],
            topology_distance.get(cell, 0),
            phase_origin,
            tile_px,
        )
        for node in new_nodes:
            node_drafts[node.node_id] = node
        segment_drafts.extend(new_segments)
        if source is not None:
            source_drafts.append(source)

    cycle_edges = _component_cycle_edges(cells, edges)
    if mouths:
        root_ids = tuple(mouth_node_ids[mouth] for mouth in mouths)
        root_policy = "all authored mouth ports (nearest-mouth scalar potential)"
    elif source_drafts:
        canonical_source = min(source_drafts, key=lambda source: (_cell_key(source.cell), source.node_id))
        root_ids = (canonical_source.node_id,)
        root_policy = "canonical source endpoint (no authored mouth supplied)"
    else:
        root_ids = (min(node_drafts),)
        root_policy = "canonical graph node (rootless cycle; no authored mouth/source)"

    stations = _node_stations(node_drafts, segment_drafts, root_ids)
    max_station = max(stations.values(), default=0.0)
    final_nodes: dict[str, RiverNode] = {}
    for node_id in sorted(node_drafts):
        draft = node_drafts[node_id]
        station = float(stations[node_id])
        phase = float(phase_origin + station * math.tau / wavelength_px)
        channel, bank = _widths(tile_px, station, max_station, phase)
        final_nodes[node_id] = RiverNode(
            node_id=node_id,
            component_id=component_id,
            kind=draft.kind,
            point_px=draft.point_px,
            cells=draft.cells,
            station_px=station,
            phase=phase,
            channel_width_px=channel,
            bank_width_px=bank,
        )

    final_segments: list[BezierSegment] = []
    for draft in sorted(segment_drafts, key=lambda segment: segment.segment_id):
        start = final_nodes[draft.start_node]
        end = final_nodes[draft.end_node]
        final_segments.append(
            BezierSegment(
                segment_id=draft.segment_id,
                component_id=component_id,
                owner_cell=draft.owner_cell,
                kind=draft.kind,
                start_node=draft.start_node,
                end_node=draft.end_node,
                p0=draft.p0,
                p1=draft.p1,
                p2=draft.p2,
                p3=draft.p3,
                length_px=draft.length_px,
                station_start_px=start.station_px,
                station_end_px=end.station_px,
                phase_start=start.phase,
                phase_end=end.phase,
                channel_width_start_px=start.channel_width_px,
                channel_width_end_px=end.channel_width_px,
                bank_width_start_px=start.bank_width_px,
                bank_width_end_px=end.bank_width_px,
            )
        )

    segment_by_cell_node: dict[tuple[Cell, str], _SegmentDraft] = {}
    shared_port_ids = set(edge_node_ids.values())
    for segment in segment_drafts:
        for node_id in (segment.start_node, segment.end_node):
            if node_id not in shared_port_ids:
                continue
            key = segment.owner_cell, node_id
            if key in segment_by_cell_node:
                raise RuntimeError(f"multiple cell curves touch the same port {key}")
            segment_by_cell_node[key] = segment
    continuity: list[PortContinuity] = []
    for edge in edges:
        node_id = edge_node_ids[edge]
        segment_a = segment_by_cell_node[(edge.a, node_id)]
        segment_b = segment_by_cell_node[(edge.b, node_id)]
        outward_a = _outward_derivative(segment_a, node_id)
        outward_b = _outward_derivative(segment_b, node_id)
        error = _point_length(_point_add(outward_a, outward_b))
        continuity.append(
            PortContinuity(
                node_id=node_id,
                edge=edge,
                canonical_point_px=final_nodes[node_id].point_px,
                segment_a=segment_a.segment_id,
                segment_b=segment_b.segment_id,
                outward_derivative_a=outward_a,
                outward_derivative_b=outward_b,
                error_px=float(error),
            )
        )

    final_sources = tuple(
        replace(source, is_phase_root=source.node_id in root_ids)
        for source in sorted(source_drafts, key=lambda source: (_cell_key(source.cell), source.node_id))
    )
    final_mouths = tuple(
        MouthEndpoint(
            cell=mouth.cell,
            direction=mouth.direction,
            node_id=mouth_node_ids[mouth],
            point_px=final_nodes[mouth_node_ids[mouth]].point_px,
            is_phase_root=mouth_node_ids[mouth] in root_ids,
        )
        for mouth in mouths
    )

    notes: list[str] = []
    if cycle_edges:
        notes.append(
            "All cycle edges are retained. Station/phase is a continuous shortest-path "
            "potential; a cycle chord may change phase derivative at a junction because "
            "undirected topology has no unique downstream arclength."
        )
    if len(mouths) > 1:
        notes.append(
            "Multiple authored mouths use a nearest-mouth potential; discharge and a "
            "single downstream direction require later authored flow metadata."
        )
    if not mouths:
        notes.append(
            "No authored mouth was supplied. The fallback root anchors visual phase only "
            "and does not invent hydrological flow."
        )
    if len(cells) == 1 and not edges:
        notes.append("Isolated river cell is represented as an explicit source/pool node.")
    limitations = GraphLimitationReport(
        cycle_rank=len(cycle_edges),
        cycle_edges=cycle_edges,
        has_authored_mouth=bool(mouths),
        mouth_count=len(mouths),
        root_policy=root_policy,
        phase_policy=(
            "unwrapped phase = component origin + shortest-path station * 2pi / "
            "component wavelength; node values are shared by every incident curve"
        ),
        notes=tuple(notes),
    )
    return RiverComponentGeometry(
        component_id=component_id,
        cells=cells,
        visible_cells=cells,
        flow_edges=edges,
        mouths=final_mouths,
        sources=final_sources,
        nodes=tuple(final_nodes[node_id] for node_id in sorted(final_nodes)),
        segments=tuple(final_segments),
        port_continuity=tuple(continuity),
        phase_origin=float(phase_origin),
        wavelength_px=float(wavelength_px),
        roots=root_ids,
        limitations=limitations,
    )


def plan_river_components(
    raw_grid: np.ndarray,
    flow_edges: Iterable[FlowEdge | Sequence[Cell] | frozenset[Cell]],
    *,
    mouths: Mapping[Cell, Direction | str] | Iterable[MouthSpec] | None = None,
    tile_px: int = 96,
    seed: int = 0,
    river_value: int = 11,
    water_value: int = 10,
    world_x0: int = 0,
    world_y0: int = 0,
    world_width: int | None = None,
    window: CellWindow | tuple[int, int, int, int] | None = None,
) -> RiverPlan:
    """Plan deterministic component-wide river geometry.

    ``raw_grid`` and ``flow_edges`` must together contain the complete
    components whose station/phase should be stable.  ``window`` is an output
    filter only; it never changes graph analysis or curve generation.
    """
    grid = np.asarray(raw_grid)
    if grid.ndim != 2:
        raise ValueError("raw_grid must be a 2-D terrain array")
    if tile_px < 8:
        raise ValueError("tile_px must be at least 8")
    if world_width is None:
        world_width = int(grid.shape[1])
    world_width = int(world_width)
    if world_width <= 1:
        raise ValueError("world_width must be at least 2")

    river_cells, terrain = _terrain_cells(
        grid,
        river_value,
        int(world_x0),
        int(world_y0),
        world_width,
    )
    edges = _normalise_edges(flow_edges, river_cells, world_width)
    mouth_specs = _normalise_mouths(
        mouths,
        river_cells,
        terrain,
        world_width,
        water_value,
    )
    components = tuple(
        _build_component(
            cells,
            edges,
            mouth_specs,
            tile_px=int(tile_px),
            world_width=world_width,
            seed=int(seed),
        )
        for cells in _components(river_cells, edges)
    )
    plan = RiverPlan(
        tile_px=int(tile_px),
        world_width=world_width,
        seed=int(seed),
        components=components,
    )
    return plan.crop(window) if window is not None else plan


__all__ = [
    "BIT_DIRECTIONS",
    "CARDINAL_ORDER",
    "CellWindow",
    "DIRECTION_BITS",
    "E",
    "FlowEdge",
    "GraphLimitationReport",
    "MouthEndpoint",
    "MouthSpec",
    "N",
    "PortContinuity",
    "RiverComponentGeometry",
    "RiverNode",
    "RiverPlan",
    "S",
    "SourceEndpoint",
    "W",
    "BezierSegment",
    "all_cardinal_flow_edges",
    "plan_river_components",
]
