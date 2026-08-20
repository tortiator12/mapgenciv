"""Isolated terrain-guided sub-cell presentation for the immutable V7 DAG.

V9 keeps V7's rules graph, hierarchy, mouths and exact shared-edge midpoint
ports.  Unlike V8, cell centres are not interpolation constraints.  Every
occupied river cell receives a free inset anchor selected from the continuous
height/potential field plus deterministic world-periodic cost.  Junction
anchors are biased toward their downstream port so tributaries form acute,
off-centre Y merges.

The centreline stays inside the union of its legal river cells.  Rasterization
is window-independent and horizontally periodic.  Mouths are coast-field
fans, not capped sea splines: the bilinear WATER field supplies a smooth coast
SDF, open-water bias bends the sediment lobe, and the overlay fades into the
existing ocean without a nozzle end-cap.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable, Sequence

import numpy as np
from PIL import Image

from .modern_hydrology_v6 import _stable_hash
from .modern_hydrology_v7 import BasinHydrologyWorldV7, FlowCellV7


Point = tuple[float, float]
Cell = tuple[int, int]
Edge = tuple[Cell, Cell]


@dataclass(frozen=True)
class PixelWindowV9:
    x0: int
    y0: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("pixel window must be positive")


@dataclass(frozen=True)
class CubicSegmentV9:
    p0: Point
    p1: Point
    p2: Point
    p3: Point
    width0: float
    width1: float
    role: str
    logical_edge: Edge | None
    half: str
    owner_cell: Cell
    owner_unwrapped_x: int


@dataclass(frozen=True)
class PortConstraintV9:
    logical_edge: Edge
    point: Point
    tangent: Point
    upstream_segment: int
    downstream_segment: int


@dataclass(frozen=True)
class JunctionGeometryV9:
    cell: Cell
    point: Point
    tangent: Point
    incoming: tuple[Cell, ...]
    downstream: Cell
    approach_angles_degrees: tuple[float, ...]
    offcentre_px: float


@dataclass(frozen=True)
class SourceGeometryV9:
    cell: Cell
    point: Point
    direction: Point
    width: float
    wet_major: float
    wet_minor: float


@dataclass(frozen=True)
class MouthGeometryV9:
    river_cell: Cell
    water_cell: Cell
    shoreline_port: Point
    direction: Point
    normal: Point
    start_width: float
    end_width: float
    depth: float
    asymmetry: float
    upstream_area: int
    strahler: int
    land_segment: CubicSegmentV9


@dataclass(frozen=True)
class ComponentGeometryV9:
    component_id: int
    cells: tuple[Cell, ...]
    unwrapped_x: tuple[tuple[Cell, int], ...]
    anchors: tuple[tuple[Cell, Point], ...]
    segments: tuple[CubicSegmentV9, ...]
    ports: tuple[PortConstraintV9, ...]
    junctions: tuple[JunctionGeometryV9, ...]
    sources: tuple[SourceGeometryV9, ...]
    mouths: tuple[MouthGeometryV9, ...]


@dataclass(frozen=True)
class RiverPresentationPlanV9:
    components: tuple[ComponentGeometryV9, ...]
    tile_px: int
    world_width: int
    world_height: int
    seed: int
    water_mask: tuple[tuple[bool, ...], ...]

    @property
    def world_width_px(self) -> int:
        return self.tile_px * self.world_width


@dataclass(frozen=True)
class PresentationAuditV9:
    valid: bool
    errors: tuple[str, ...]
    components: int
    segments: int
    ports: int
    junctions: int
    sources: int
    mouths: int
    illegal_centerline_samples: int
    min_junction_offcentre_px: float
    max_junction_approach_degrees: float
    min_source_width: float
    max_source_width: float
    min_mouth_asymmetry_px: float
    max_mouth_asymmetry_px: float


def _add(a: Point, b: Point) -> Point:
    return a[0] + b[0], a[1] + b[1]


def _sub(a: Point, b: Point) -> Point:
    return a[0] - b[0], a[1] - b[1]


def _scale(a: Point, value: float) -> Point:
    return a[0] * value, a[1] * value


def _length(a: Point) -> float:
    return math.hypot(a[0], a[1])


def _unit(a: Point, fallback: Point = (1.0, 0.0)) -> Point:
    length = _length(a)
    if length <= 1e-12:
        return fallback
    return a[0] / length, a[1] / length


def _dot(a: Point, b: Point) -> float:
    return a[0] * b[0] + a[1] * b[1]


def _unwrap_delta(x0: int, x1: int, world_width: int) -> int:
    forward = (x1 - x0) % world_width
    if forward == 1:
        return 1
    if forward == world_width - 1:
        return -1
    if forward == 0:
        return 0
    raise ValueError(f"cells {x0}->{x1} are not horizontally cardinal")


def _component_sets(cells: Iterable[Cell], edges: Iterable[Edge]) -> tuple[tuple[Cell, ...], ...]:
    adjacency = {cell: set() for cell in cells}
    for start, end in edges:
        adjacency[start].add(end)
        adjacency[end].add(start)
    result = []
    seen = set()
    for root in sorted(adjacency, key=lambda item: (item[1], item[0])):
        if root in seen:
            continue
        queue = [root]
        seen.add(root)
        component = []
        while queue:
            cell = queue.pop(0)
            component.append(cell)
            for neighbor in sorted(adjacency[cell], key=lambda item: (item[1], item[0])):
                if neighbor not in seen:
                    seen.add(neighbor)
                    queue.append(neighbor)
        result.append(tuple(sorted(component, key=lambda item: (item[1], item[0]))))
    return tuple(result)


def _unwrap_component(component: Sequence[Cell], edges: Sequence[Edge], world_width: int) -> dict[Cell, int]:
    wanted = set(component)
    adjacency = {cell: set() for cell in component}
    for start, end in edges:
        if start in wanted and end in wanted:
            adjacency[start].add(end)
            adjacency[end].add(start)
    root = min(component, key=lambda item: (item[1], item[0]))
    unwrapped = {root: int(root[0])}
    queue = [root]
    while queue:
        cell = queue.pop(0)
        for neighbor in sorted(adjacency[cell], key=lambda item: (item[1], item[0])):
            candidate = unwrapped[cell] + _unwrap_delta(cell[0], neighbor[0], world_width)
            if neighbor in unwrapped:
                if unwrapped[neighbor] != candidate:
                    raise ValueError("component has inconsistent horizontal unwrap")
                continue
            unwrapped[neighbor] = candidate
            queue.append(neighbor)
    if set(unwrapped) != wanted:
        raise ValueError("component unwrap missed cells")
    return unwrapped


def _center(cell: Cell, unwrapped: dict[Cell, int], tile_px: int) -> Point:
    return (unwrapped[cell] + 0.5) * tile_px, (cell[1] + 0.5) * tile_px


def _edge_direction(start: Cell, end: Cell, unwrapped: dict[Cell, int]) -> Point:
    return _unit((float(unwrapped[end] - unwrapped[start]), float(end[1] - start[1])))


def _edge_port(start: Cell, end: Cell, unwrapped: dict[Cell, int], tile_px: int) -> Point:
    a, b = _center(start, unwrapped, tile_px), _center(end, unwrapped, tile_px)
    return (a[0] + b[0]) * 0.5, (a[1] + b[1]) * 0.5


def _hydraulic_width(meta: FlowCellV7) -> float:
    root = math.sqrt(max(1, meta.upstream_area))
    order = max(0, meta.strahler - 1)
    if meta.role == "tributary":
        return 3.15 + min(2.65, root * 0.48 + order * 0.75)
    return 4.55 + min(5.75, root * 0.68 + order * 1.15)


def _field_sample(field: np.ndarray, point: Point, tile_px: int, world_width: int) -> float:
    x = point[0] / tile_px - 0.5
    y = point[1] / tile_px - 0.5
    x0 = math.floor(x)
    y0 = math.floor(y)
    tx, ty = x - x0, y - y0
    xa, xb = x0 % world_width, (x0 + 1) % world_width
    ya = min(max(y0, 0), field.shape[0] - 1)
    yb = min(max(y0 + 1, 0), field.shape[0] - 1)
    top = float(field[ya, xa]) * (1.0 - tx) + float(field[ya, xb]) * tx
    bottom = float(field[yb, xa]) * (1.0 - tx) + float(field[yb, xb]) * tx
    return top * (1.0 - ty) + bottom * ty


def _subcell_noise(seed: int, point: Point, tile_px: int, world_width: int, salt: int) -> float:
    x = (point[0] / tile_px) % world_width
    y = point[1] / tile_px
    phase1 = _stable_hash(seed, salt, 0, 1709) / 2**32 * math.tau
    phase2 = _stable_hash(seed, salt, 0, 1721) / 2**32 * math.tau
    return (
        math.sin(math.tau * (7.0 * x / world_width + y * 0.37) + phase1) * 0.62
        + math.cos(math.tau * (13.0 * x / world_width - y * 0.23) + phase2) * 0.38
    )


def _downstream_steps(component: Sequence[Cell], downstream: dict[Cell, Cell | None]) -> dict[Cell, int]:
    result: dict[Cell, int] = {}

    def visit(cell: Cell) -> int:
        if cell in result:
            return result[cell]
        nxt = downstream[cell]
        result[cell] = 0 if nxt is None else visit(nxt) + 1
        return result[cell]

    for cell in component:
        visit(cell)
    return result


def _candidate_anchor(
    cell: Cell,
    *,
    unwrapped_x: int,
    incoming_ports: Sequence[Point],
    outgoing_port: Point,
    junction: bool,
    source: bool,
    steps: int,
    height: np.ndarray,
    potential: np.ndarray,
    seed: int,
    tile_px: int,
    world_width: int,
) -> Point:
    origin = (unwrapped_x * tile_px, cell[1] * tile_px)
    centre = (origin[0] + tile_px * 0.5, origin[1] + tile_px * 0.5)
    fractions = (0.22, 0.29, 0.36, 0.43, 0.50, 0.57, 0.64, 0.71, 0.78)
    phase = _stable_hash(seed, cell[0], cell[1], 1801) / 2**32 * math.tau
    if junction:
        out_from_centre = _unit(_sub(outgoing_port, centre))
        normal = (-out_from_centre[1], out_from_centre[0])
        lateral = math.sin(phase) * tile_px * 0.055
        target = _add(_add(centre, _scale(out_from_centre, tile_px * 0.275)), _scale(normal, lateral))
    elif source:
        out_from_centre = _unit(_sub(outgoing_port, centre))
        normal = (-out_from_centre[1], out_from_centre[0])
        target = _add(
            _sub(centre, _scale(out_from_centre, tile_px * 0.17)),
            _scale(normal, math.sin(phase) * tile_px * 0.13),
        )
    else:
        entry = incoming_ports[0]
        chord = _scale(_add(entry, outgoing_port), 0.5)
        flow = _unit(_sub(outgoing_port, entry))
        normal = (-flow[1], flow[0])
        amplitude = tile_px * (0.115 + 0.035 * math.sin(phase * 0.43 + steps * 0.21))
        meander = math.sin(phase * 0.35 + steps * 0.79) * amplitude
        target = _add(chord, _scale(normal, meander))

    p_min, p_span = float(potential.min()), max(1e-9, float(np.ptp(potential)))
    h_min, h_span = float(height.min()), max(1e-9, float(np.ptp(height)))
    best = None
    for u in fractions:
        for v in fractions:
            if u == 0.50 and v == 0.50:
                continue
            point = (origin[0] + u * tile_px, origin[1] + v * tile_px)
            distance_score = ((_length(_sub(point, target)) / tile_px) ** 2) * (12.0 if not junction else 8.0)
            pn = (_field_sample(potential, point, tile_px, world_width) - p_min) / p_span
            hn = (_field_sample(height, point, tile_px, world_width) - h_min) / h_span
            terrain_cost = (-0.34 * pn - 0.22 * hn) if source else (0.19 * pn + 0.11 * hn)
            noise_cost = -0.13 * _subcell_noise(seed, point, tile_px, world_width, 1811)
            score = distance_score + terrain_cost + noise_cost
            if junction:
                outgoing = _unit(_sub(outgoing_port, point))
                for entry in incoming_ports:
                    approach = _unit(_sub(point, entry))
                    cosine = _dot(approach, outgoing)
                    score += max(0.0, 0.50 - cosine) ** 2 * 34.0
                score += max(0.0, 0.145 * tile_px - _length(_sub(outgoing_port, point))) ** 2 / tile_px**2 * 20.0
            key = (score, _stable_hash(seed, round(u * 100), round(v * 100), cell[0] * 97 + cell[1] * 193))
            if best is None or key < best[0]:
                best = (key, point)
    return best[1]


def _ray_distance_to_inset(point: Point, direction: Point, origin_x: float, origin_y: float, tile_px: int) -> float:
    margin = tile_px * 0.045
    bounds = (origin_x + margin, origin_x + tile_px - margin, origin_y + margin, origin_y + tile_px - margin)
    values = []
    if direction[0] > 1e-12:
        values.append((bounds[1] - point[0]) / direction[0])
    elif direction[0] < -1e-12:
        values.append((bounds[0] - point[0]) / direction[0])
    if direction[1] > 1e-12:
        values.append((bounds[3] - point[1]) / direction[1])
    elif direction[1] < -1e-12:
        values.append((bounds[2] - point[1]) / direction[1])
    return min((value for value in values if value >= 0.0), default=tile_px)


def _node_handle(point: Point, tangent: Point, owner_x: int, owner_y: int, tile_px: int) -> float:
    plus = _ray_distance_to_inset(point, tangent, owner_x * tile_px, owner_y * tile_px, tile_px)
    minus = _ray_distance_to_inset(point, _scale(tangent, -1.0), owner_x * tile_px, owner_y * tile_px, tile_px)
    return max(tile_px * 0.055, min(tile_px * 0.145, plus * 0.64, minus * 0.64))


def _water_sample(water: np.ndarray, point_cell_units: Point, world_width: int) -> float:
    x, y = point_cell_units[0] - 0.5, point_cell_units[1] - 0.5
    x0, y0 = math.floor(x), math.floor(y)
    tx, ty = x - x0, y - y0
    xa, xb = x0 % world_width, (x0 + 1) % world_width
    ya = min(max(y0, 0), water.shape[0] - 1)
    yb = min(max(y0 + 1, 0), water.shape[0] - 1)
    top = float(water[ya, xa]) * (1.0 - tx) + float(water[ya, xb]) * tx
    bottom = float(water[yb, xa]) * (1.0 - tx) + float(water[yb, xb]) * tx
    return top * (1.0 - ty) + bottom * ty


def _coast_fan_parameters(
    shoreline: Point,
    cardinal: Point,
    water: np.ndarray,
    *,
    seed: int,
    mouth_cell: Cell,
    tile_px: int,
    world_width: int,
) -> tuple[Point, Point, float]:
    shore_cell = (shoreline[0] / tile_px, shoreline[1] / tile_px)
    epsilon = 0.045
    gx = _water_sample(water, (shore_cell[0] + epsilon, shore_cell[1]), world_width) - _water_sample(
        water, (shore_cell[0] - epsilon, shore_cell[1]), world_width
    )
    gy = _water_sample(water, (shore_cell[0], shore_cell[1] + epsilon), world_width) - _water_sample(
        water, (shore_cell[0], shore_cell[1] - epsilon), world_width
    )
    gradient = _unit((gx, gy), cardinal)
    if _dot(gradient, cardinal) < 0.0:
        gradient = _scale(gradient, -1.0)
    direction = _unit(_add(_scale(cardinal, 0.62), _scale(gradient, 0.38)), cardinal)
    normal = (-direction[1], direction[0])
    probe = _add(shore_cell, _scale(direction, 0.34))
    left = _water_sample(water, _add(probe, _scale(normal, 0.30)), world_width)
    right = _water_sample(water, _add(probe, _scale(normal, -0.30)), world_width)
    open_water_bias = left - right
    seed_bias = _stable_hash(seed, mouth_cell[0], mouth_cell[1], 1901) / 2**32 * 2.0 - 1.0
    asymmetry = max(-0.22, min(0.22, open_water_bias * 0.24 + seed_bias * 0.055)) * tile_px
    return direction, normal, asymmetry


def plan_river_presentation_v9(
    world: BasinHydrologyWorldV7,
    *,
    tile_px: int = 96,
    world_width: int = 80,
) -> RiverPresentationPlanV9:
    if tile_px <= 0 or world_width <= 0:
        raise ValueError("invalid presentation dimensions")
    world_height = len(world.terrain)
    flow_by_cell = {item.cell: item for item in world.flow_cells}
    downstream = {item.cell: item.downstream for item in world.flow_cells}
    incoming = {cell: [] for cell in flow_by_cell}
    for start, end in downstream.items():
        if end is not None:
            incoming[end].append(start)
    edge_meta = {(item.start, item.end): item for item in world.flow_edges}
    components = _component_sets(flow_by_cell, world.river_edges)
    height, potential, _distance = world.fields.arrays()
    mouth_water_code = int(world.stage4_terrain[world.mouths[0].water_cell[1]][world.mouths[0].water_cell[0]])
    stage4 = np.asarray(world.stage4_terrain, dtype=np.int16)
    water = stage4 == mouth_water_code
    result = []

    for component_id, component in enumerate(components):
        component_set = set(component)
        component_edges = tuple(
            (start, end) for start, end in downstream.items() if end is not None and start in component_set
        )
        unwrapped = _unwrap_component(component, component_edges, world_width)
        mouths_here = [mouth for mouth in world.mouths if mouth.river_cell in component_set]
        if len(mouths_here) != 1:
            raise ValueError("each directed component must own exactly one mouth")
        mouth_meta = mouths_here[0]
        steps = _downstream_steps(component, downstream)
        edge_ports = {edge: _edge_port(edge[0], edge[1], unwrapped, tile_px) for edge in component_edges}
        in_ports = {
            cell: [edge_ports[(parent, cell)] for parent in sorted(incoming[cell], key=lambda item: (item[1], item[0]))]
            for cell in component
        }

        river_center = _center(mouth_meta.river_cell, unwrapped, tile_px)
        cardinal = _unit(
            (
                float(_unwrap_delta(mouth_meta.river_cell[0], mouth_meta.water_cell[0], world_width))
                if mouth_meta.river_cell[1] == mouth_meta.water_cell[1]
                else 0.0,
                float(mouth_meta.water_cell[1] - mouth_meta.river_cell[1]),
            )
        )
        water_unwrapped_x = unwrapped[mouth_meta.river_cell] + int(round(cardinal[0]))
        water_center = ((water_unwrapped_x + 0.5) * tile_px, (mouth_meta.water_cell[1] + 0.5) * tile_px)
        shoreline = _scale(_add(river_center, water_center), 0.5)
        mouth_direction, mouth_normal, mouth_asymmetry = _coast_fan_parameters(
            shoreline,
            cardinal,
            water.astype(np.float32),
            seed=world.seed,
            mouth_cell=mouth_meta.river_cell,
            tile_px=tile_px,
            world_width=world_width,
        )
        out_ports = {}
        for cell in component:
            nxt = downstream[cell]
            out_ports[cell] = shoreline if nxt is None else edge_ports[(cell, nxt)]

        anchors = {}
        for cell in component:
            anchors[cell] = _candidate_anchor(
                cell,
                unwrapped_x=unwrapped[cell],
                incoming_ports=in_ports[cell],
                outgoing_port=out_ports[cell],
                junction=len(incoming[cell]) >= 2,
                source=not incoming[cell],
                steps=steps[cell],
                height=height,
                potential=potential,
                seed=world.seed,
                tile_px=tile_px,
                world_width=world_width,
            )

        node_tangents = {}
        for cell in component:
            parents = incoming[cell]
            if len(parents) >= 2:
                node_tangents[cell] = _unit(_sub(out_ports[cell], anchors[cell]))
            elif len(parents) == 1:
                chord = _unit(_sub(out_ports[cell], in_ports[cell][0]))
                if downstream[cell] is None:
                    node_tangents[cell] = _unit(_add(_scale(chord, 0.58), _scale(mouth_direction, 0.42)), chord)
                else:
                    local = _unit(_sub(out_ports[cell], anchors[cell]))
                    node_tangents[cell] = _unit(_add(_scale(chord, 0.68), _scale(local, 0.32)), chord)
            else:
                node_tangents[cell] = _unit(_sub(out_ports[cell], anchors[cell]))

        source_cells = {cell for cell in component if not incoming[cell]}
        node_width = {cell: _hydraulic_width(flow_by_cell[cell]) for cell in component}
        source_width = {
            cell: 0.85 + 0.35 * (_stable_hash(world.seed, cell[0], cell[1], 2003) / 2**32)
            for cell in source_cells
        }
        segments = []
        ports = []
        port_handle = tile_px * 0.132
        for edge in component_edges:
            start, end = edge
            point0, point1 = anchors[start], anchors[end]
            tangent0, tangent1 = node_tangents[start], node_tangents[end]
            port = edge_ports[edge]
            direction = _edge_direction(start, end, unwrapped)
            raw = _unit(_sub(point1, point0), direction)
            port_tangent = _unit(_add(_scale(direction, 0.62), _scale(raw, 0.38)), direction)
            if _dot(port_tangent, direction) < 0.72:
                port_tangent = direction
            handle0 = _node_handle(point0, tangent0, unwrapped[start], start[1], tile_px)
            handle1 = _node_handle(point1, tangent1, unwrapped[end], end[1], tile_px)
            width0 = source_width.get(start, node_width[start])
            width1 = node_width[end]
            port_width = (width0 + width1) * 0.5
            upstream = CubicSegmentV9(
                point0,
                _add(point0, _scale(tangent0, handle0)),
                _sub(port, _scale(port_tangent, port_handle)),
                port,
                width0,
                port_width,
                edge_meta[edge].role,
                edge,
                "upstream",
                start,
                unwrapped[start],
            )
            downstream_half = CubicSegmentV9(
                port,
                _add(port, _scale(port_tangent, port_handle)),
                _sub(point1, _scale(tangent1, handle1)),
                point1,
                port_width,
                width1,
                edge_meta[edge].role,
                edge,
                "downstream",
                end,
                unwrapped[end],
            )
            index = len(segments)
            segments.extend((upstream, downstream_half))
            ports.append(PortConstraintV9(edge, port, port_tangent, index, index + 1))

        junctions = []
        for cell in component:
            if len(incoming[cell]) < 2 or downstream[cell] is None:
                continue
            outgoing = _unit(_sub(out_ports[cell], anchors[cell]))
            angles = []
            for entry in in_ports[cell]:
                approach = _unit(_sub(anchors[cell], entry))
                cosine = max(-1.0, min(1.0, _dot(approach, outgoing)))
                angles.append(math.degrees(math.acos(cosine)))
            centre = _center(cell, unwrapped, tile_px)
            junctions.append(
                JunctionGeometryV9(
                    cell,
                    anchors[cell],
                    node_tangents[cell],
                    tuple(sorted(incoming[cell], key=lambda item: (item[1], item[0]))),
                    downstream[cell],
                    tuple(angles),
                    _length(_sub(anchors[cell], centre)),
                )
            )

        sources = tuple(
            SourceGeometryV9(
                cell,
                anchors[cell],
                node_tangents[cell],
                source_width[cell],
                tile_px * (0.115 + 0.025 * (_stable_hash(world.seed, cell[0], cell[1], 2011) / 2**32)),
                tile_px * (0.055 + 0.018 * (_stable_hash(world.seed, cell[0], cell[1], 2017) / 2**32)),
            )
            for cell in sorted(source_cells, key=lambda item: (item[1], item[0]))
        )

        terminal = mouth_meta.river_cell
        terminal_tangent = node_tangents[terminal]
        terminal_handle = _node_handle(anchors[terminal], terminal_tangent, unwrapped[terminal], terminal[1], tile_px)
        shore_handle = tile_px * 0.145
        mouth_width = node_width[terminal]
        land_segment = CubicSegmentV9(
            anchors[terminal],
            _add(anchors[terminal], _scale(terminal_tangent, terminal_handle)),
            _sub(shoreline, _scale(mouth_direction, shore_handle)),
            shoreline,
            mouth_width,
            mouth_width * 1.16,
            "mouth_land",
            None,
            "mouth_land",
            terminal,
            unwrapped[terminal],
        )
        fan_depth = tile_px * (0.48 + min(0.17, math.sqrt(mouth_meta.upstream_area) * 0.014))
        fan_end_width = min(tile_px * 0.43, mouth_width * 2.45 + math.sqrt(mouth_meta.upstream_area) * 0.72)
        mouth = MouthGeometryV9(
            terminal,
            mouth_meta.water_cell,
            shoreline,
            mouth_direction,
            mouth_normal,
            mouth_width * 1.16,
            fan_end_width,
            fan_depth,
            mouth_asymmetry,
            mouth_meta.upstream_area,
            mouth_meta.strahler,
            land_segment,
        )
        result.append(
            ComponentGeometryV9(
                component_id,
                tuple(component),
                tuple(sorted(unwrapped.items(), key=lambda item: (item[0][1], item[0][0]))),
                tuple(sorted(anchors.items(), key=lambda item: (item[0][1], item[0][0]))),
                tuple(segments),
                tuple(ports),
                tuple(junctions),
                sources,
                (mouth,),
            )
        )

    plan = RiverPresentationPlanV9(
        tuple(result),
        int(tile_px),
        int(world_width),
        int(world_height),
        int(world.seed),
        tuple(tuple(bool(value) for value in row) for row in water),
    )
    audit = validate_presentation_plan_v9(plan, world)
    if not audit.valid:
        raise AssertionError("invalid River Presentation V9: " + "; ".join(audit.errors))
    return plan


def _cubic_samples(segment: CubicSegmentV9, count: int = 21) -> tuple[np.ndarray, np.ndarray]:
    t = np.linspace(0.0, 1.0, count, dtype=np.float64)
    one = 1.0 - t
    points = (
        (one**3)[:, None] * np.asarray(segment.p0)
        + (3.0 * one**2 * t)[:, None] * np.asarray(segment.p1)
        + (3.0 * one * t**2)[:, None] * np.asarray(segment.p2)
        + (t**3)[:, None] * np.asarray(segment.p3)
    )
    widths = segment.width0 * one + segment.width1 * t
    return points, widths


def _derivative_start(segment: CubicSegmentV9) -> Point:
    return _scale(_sub(segment.p1, segment.p0), 3.0)


def _derivative_end(segment: CubicSegmentV9) -> Point:
    return _scale(_sub(segment.p3, segment.p2), 3.0)


def _point_close(a: Point, b: Point, tolerance: float = 1e-7) -> bool:
    return abs(a[0] - b[0]) <= tolerance and abs(a[1] - b[1]) <= tolerance


def validate_presentation_plan_v9(plan: RiverPresentationPlanV9, world: BasinHydrologyWorldV7) -> PresentationAuditV9:
    errors = []
    expected_edges = {(item.start, item.end) for item in world.flow_edges}
    seen_edges = set()
    illegal = 0
    junction_offsets = []
    junction_angles = []
    source_widths = []
    mouth_asymmetries = []
    for component in plan.components:
        unwrap = dict(component.unwrapped_x)
        anchors = dict(component.anchors)
        for cell, anchor in anchors.items():
            centre = _center(cell, unwrap, plan.tile_px)
            if _point_close(anchor, centre, plan.tile_px * 0.015):
                errors.append("free subcell anchor collapsed to a cell centre")
        for port in component.ports:
            if port.logical_edge in seen_edges:
                errors.append("duplicate logical edge")
            seen_edges.add(port.logical_edge)
            first, second = component.segments[port.upstream_segment], component.segments[port.downstream_segment]
            if not _point_close(first.p3, port.point) or not _point_close(second.p0, port.point):
                errors.append("edge misses exact midpoint port")
            if not _point_close(_derivative_end(first), _derivative_start(second)):
                errors.append("edge port is not C1")
            start, end = port.logical_edge
            expected = _edge_port(start, end, unwrap, plan.tile_px)
            if not _point_close(port.point, expected):
                errors.append("port is not exact shared-edge midpoint")
        for segment in (*component.segments, *(mouth.land_segment for mouth in component.mouths)):
            points, _widths = _cubic_samples(segment, 41)
            x0 = segment.owner_unwrapped_x * plan.tile_px
            x1 = x0 + plan.tile_px
            y0 = segment.owner_cell[1] * plan.tile_px
            y1 = y0 + plan.tile_px
            outside = (points[:, 0] < x0 - 1e-7) | (points[:, 0] > x1 + 1e-7) | (points[:, 1] < y0 - 1e-7) | (points[:, 1] > y1 + 1e-7)
            illegal += int(np.count_nonzero(outside))
        for junction in component.junctions:
            junction_offsets.append(junction.offcentre_px)
            junction_angles.extend(junction.approach_angles_degrees)
            if junction.offcentre_px < plan.tile_px * 0.12:
                errors.append("junction is insufficiently off-centre")
            if junction.approach_angles_degrees and max(junction.approach_angles_degrees) > 78.0:
                errors.append("junction retains a near-right-angle macro approach")
            arriving = [
                segment for segment in component.segments
                if segment.logical_edge is not None and segment.logical_edge[1] == junction.cell and segment.half == "downstream"
            ]
            leaving = [
                segment for segment in component.segments
                if segment.logical_edge is not None and segment.logical_edge[0] == junction.cell and segment.half == "upstream"
            ]
            if len(arriving) != len(junction.incoming) or len(leaving) != 1:
                errors.append("junction degree mismatch")
            derivatives = [_unit(_derivative_end(segment)) for segment in arriving] + [_unit(_derivative_start(segment)) for segment in leaving]
            if any(not _point_close(item, junction.tangent) for item in derivatives):
                errors.append("junction branches do not share one downstream tangent")
        for source in component.sources:
            source_widths.append(source.width)
            if source.width >= _hydraulic_width(next(item for item in world.flow_cells if item.cell == source.cell)) * 0.45:
                errors.append("source does not materially taper")
        for mouth in component.mouths:
            mouth_asymmetries.append(abs(mouth.asymmetry))
            if not _point_close(mouth.land_segment.p3, mouth.shoreline_port):
                errors.append("mouth land curve misses shoreline port")
            shore_derivative = _unit(_derivative_end(mouth.land_segment))
            if not _point_close(shore_derivative, mouth.direction):
                errors.append("mouth land tangent does not enter coast fan")
            if mouth.end_width <= mouth.start_width * 1.5:
                errors.append("estuary fan does not materially expand")
    if illegal:
        errors.append("centreline leaves legal river-cell union")
    if seen_edges != expected_edges:
        errors.append("logical flow-edge coverage mismatch")
    return PresentationAuditV9(
        not errors,
        tuple(errors),
        len(plan.components),
        sum(len(component.segments) + len(component.mouths) for component in plan.components),
        sum(len(component.ports) for component in plan.components),
        sum(len(component.junctions) for component in plan.components),
        sum(len(component.sources) for component in plan.components),
        sum(len(component.mouths) for component in plan.components),
        illegal,
        min(junction_offsets, default=0.0),
        max(junction_angles, default=0.0),
        min(source_widths, default=0.0),
        max(source_widths, default=0.0),
        min(mouth_asymmetries, default=0.0),
        max(mouth_asymmetries, default=0.0),
    )


def _shift_range(min_x: float, max_x: float, window: PixelWindowV9, period: int, margin: float) -> range:
    first = math.floor((window.x0 - max_x - margin) / period)
    last = math.ceil((window.x0 + window.width - min_x + margin) / period)
    return range(first, last + 1)


def _update_segment_sdf(
    sdf: np.ndarray,
    window: PixelWindowV9,
    p0: Point,
    p1: Point,
    width0: float,
    width1: float,
    *,
    padding: float,
) -> None:
    radius = max(width0, width1) * 0.5 + padding
    min_x, max_x = min(p0[0], p1[0]) - radius, max(p0[0], p1[0]) + radius
    min_y, max_y = min(p0[1], p1[1]) - radius, max(p0[1], p1[1]) + radius
    x0 = max(0, int(math.floor(min_x - window.x0)))
    x1 = min(window.width, int(math.ceil(max_x - window.x0)) + 1)
    y0 = max(0, int(math.floor(min_y - window.y0)))
    y1 = min(window.height, int(math.ceil(max_y - window.y0)) + 1)
    if x0 >= x1 or y0 >= y1:
        return
    xs = window.x0 + np.arange(x0, x1, dtype=np.float64) + 0.5
    ys = window.y0 + np.arange(y0, y1, dtype=np.float64) + 0.5
    xx, yy = np.meshgrid(xs, ys)
    vx, vy = p1[0] - p0[0], p1[1] - p0[1]
    denominator = vx * vx + vy * vy
    projection = np.zeros_like(xx) if denominator <= 1e-12 else np.clip(((xx - p0[0]) * vx + (yy - p0[1]) * vy) / denominator, 0.0, 1.0)
    nearest_x, nearest_y = p0[0] + projection * vx, p0[1] + projection * vy
    distance = np.sqrt((xx - nearest_x) ** 2 + (yy - nearest_y) ** 2)
    local_width = width0 + projection * (width1 - width0)
    target = sdf[y0:y1, x0:x1]
    np.minimum(target, (distance - local_width * 0.5).astype(np.float32), out=target)


def _raster_cubic(sdf: np.ndarray, segment: CubicSegmentV9, window: PixelWindowV9, period: int, seed: int) -> None:
    points, widths = _cubic_samples(segment, 25)
    min_x, max_x = float(points[:, 0].min()), float(points[:, 0].max())
    for cycle in _shift_range(min_x, max_x, window, period, 16.0 + float(widths.max())):
        shift = cycle * period
        for index in range(len(points) - 1):
            midpoint_x = (points[index, 0] + points[index + 1, 0]) * 0.5
            midpoint_y = (points[index, 1] + points[index + 1, 1]) * 0.5
            modulation = 1.0 + 0.065 * math.sin(
                midpoint_x / period * math.tau * 23.0 + midpoint_y / 181.0 + (seed & 1023) * 0.013
            )
            _update_segment_sdf(
                sdf,
                window,
                (float(points[index, 0] + shift), float(points[index, 1])),
                (float(points[index + 1, 0] + shift), float(points[index + 1, 1])),
                float(widths[index] * modulation),
                float(widths[index + 1] * modulation),
                padding=13.0,
            )


def _update_source_wet_sdf(sdf: np.ndarray, source: SourceGeometryV9, window: PixelWindowV9, period: int) -> None:
    direction, normal = source.direction, (-source.direction[1], source.direction[0])
    radius = source.wet_major + 10.0
    for cycle in _shift_range(source.point[0], source.point[0], window, period, radius):
        cx = source.point[0] + cycle * period
        x0 = max(0, int(math.floor(cx - radius - window.x0)))
        x1 = min(window.width, int(math.ceil(cx + radius - window.x0)) + 1)
        y0 = max(0, int(math.floor(source.point[1] - radius - window.y0)))
        y1 = min(window.height, int(math.ceil(source.point[1] + radius - window.y0)) + 1)
        if x0 >= x1 or y0 >= y1:
            continue
        xs = window.x0 + np.arange(x0, x1, dtype=np.float64) + 0.5 - cx
        ys = window.y0 + np.arange(y0, y1, dtype=np.float64) + 0.5 - source.point[1]
        xx, yy = np.meshgrid(xs, ys)
        along = xx * direction[0] + yy * direction[1]
        across = xx * normal[0] + yy * normal[1]
        normalized = np.sqrt((along / source.wet_major) ** 2 + (across / source.wet_minor) ** 2)
        signed = (normalized - 1.0) * source.wet_minor
        target = sdf[y0:y1, x0:x1]
        np.minimum(target, signed.astype(np.float32), out=target)


def _water_fraction(plan: RiverPresentationPlanV9, window: PixelWindowV9) -> np.ndarray:
    water = np.asarray(plan.water_mask, dtype=np.float32)
    xs = ((window.x0 + np.arange(window.width, dtype=np.float64) + 0.5) % plan.world_width_px) / plan.tile_px - 0.5
    ys = (window.y0 + np.arange(window.height, dtype=np.float64) + 0.5) / plan.tile_px - 0.5
    x0 = np.floor(xs).astype(np.int64)
    y0 = np.floor(ys).astype(np.int64)
    tx, ty = xs - x0, ys - y0
    xa, xb = x0 % plan.world_width, (x0 + 1) % plan.world_width
    ya = np.clip(y0, 0, plan.world_height - 1)
    yb = np.clip(y0 + 1, 0, plan.world_height - 1)
    top = water[ya[:, None], xa[None, :]] * (1.0 - tx[None, :]) + water[ya[:, None], xb[None, :]] * tx[None, :]
    bottom = water[yb[:, None], xa[None, :]] * (1.0 - tx[None, :]) + water[yb[:, None], xb[None, :]] * tx[None, :]
    return (top * (1.0 - ty[:, None]) + bottom * ty[:, None]).astype(np.float32)


def _raster_mouth_fields(
    estuary: np.ndarray,
    plume: np.ndarray,
    foam: np.ndarray,
    mouth: MouthGeometryV9,
    plan: RiverPresentationPlanV9,
    window: PixelWindowV9,
    water_fraction: np.ndarray,
    noise: np.ndarray,
) -> None:
    yy, xx = np.mgrid[0:window.height, 0:window.width]
    world_x = window.x0 + xx + 0.5
    world_y = window.y0 + yy + 0.5
    margin = mouth.depth + mouth.end_width
    for cycle in _shift_range(mouth.shoreline_port[0], mouth.shoreline_port[0], window, plan.world_width_px, margin):
        shore_x = mouth.shoreline_port[0] + cycle * plan.world_width_px
        dx, dy = world_x - shore_x, world_y - mouth.shoreline_port[1]
        along = dx * mouth.direction[0] + dy * mouth.direction[1]
        across = dx * mouth.normal[0] + dy * mouth.normal[1]
        q = np.clip(along / mouth.depth, 0.0, 1.0)
        active = (along >= -1.5) & (along <= mouth.depth)
        centre_shift = mouth.asymmetry * q**1.28 + plan.tile_px * 0.024 * np.sin(q * math.tau + plan.seed * 0.017) * q
        half_width = mouth.start_width * 0.5 + (mouth.end_width * 0.5 - mouth.start_width * 0.5) * q**0.74
        transverse = np.abs(across - centre_shift)
        open_water = np.clip((water_fraction - 0.42) / 0.34, 0.0, 1.0)
        fade = np.clip((1.0 - q) / 0.42, 0.0, 1.0)
        body = np.exp(-((transverse / np.maximum(half_width, 0.5)) ** 4))
        estuary_strength = body * np.sqrt(fade) * open_water * active
        np.maximum(estuary, estuary_strength.astype(np.float32), out=estuary)

        lobe_width = half_width * (1.38 + 0.13 * np.sin(q * math.tau * 2.0 + plan.seed * 0.031))
        lobe = np.exp(-((transverse / np.maximum(lobe_width, 0.5)) ** 2.8))
        breakup = np.clip(0.78 + noise * 0.22, 0.38, 1.0)
        plume_strength = lobe * (1.0 - q) ** 0.82 * open_water * active * breakup
        np.maximum(plume, plume_strength.astype(np.float32), out=plume)

        coast_band = np.exp(-(((water_fraction - 0.5) / 0.045) ** 2))
        local = np.exp(-((transverse / max(2.0, mouth.start_width * 1.34)) ** 3.0))
        foam_strength = coast_band * local * active * np.clip(0.78 + noise * 0.26, 0.25, 1.0)
        np.maximum(foam, foam_strength.astype(np.float32), out=foam)


def _alpha_over(rgb: np.ndarray, alpha: np.ndarray, color: np.ndarray, source_alpha: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    source_alpha = np.clip(source_alpha, 0.0, 1.0).astype(np.float32)
    out_alpha = source_alpha + alpha * (1.0 - source_alpha)
    numerator = color * source_alpha[..., None] + rgb * alpha[..., None] * (1.0 - source_alpha[..., None])
    out_rgb = np.divide(numerator, np.maximum(out_alpha[..., None], 1e-8), out=np.zeros_like(numerator), where=out_alpha[..., None] > 1e-8)
    return out_rgb, out_alpha


def render_river_layer_v9(plan: RiverPresentationPlanV9, window: PixelWindowV9) -> Image.Image:
    shape = (window.height, window.width)
    river_sdf = np.full(shape, np.inf, dtype=np.float32)
    source_wet_sdf = np.full(shape, np.inf, dtype=np.float32)
    period = plan.world_width_px
    for component in plan.components:
        for segment in component.segments:
            _raster_cubic(river_sdf, segment, window, period, plan.seed)
        for source in component.sources:
            _update_source_wet_sdf(source_wet_sdf, source, window, period)
        for mouth in component.mouths:
            _raster_cubic(river_sdf, mouth.land_segment, window, period, plan.seed)

    yy, xx = np.mgrid[0:window.height, 0:window.width]
    world_x = (window.x0 + xx) % period
    world_y = window.y0 + yy
    phase = (plan.seed & 0xFFFF) / 65536.0 * math.tau
    noise = (
        np.sin(math.tau * (world_x / period * 19.0 + world_y / (plan.tile_px * 4.7)) + phase) * 0.56
        + np.cos(math.tau * (world_x / period * 31.0 - world_y / (plan.tile_px * 7.3)) - phase * 0.61) * 0.44
    ).astype(np.float32)
    water_fraction = _water_fraction(plan, window)
    estuary = np.zeros(shape, dtype=np.float32)
    plume = np.zeros(shape, dtype=np.float32)
    foam = np.zeros(shape, dtype=np.float32)
    for component in plan.components:
        for mouth in component.mouths:
            _raster_mouth_fields(estuary, plume, foam, mouth, plan, window, water_fraction, noise)

    rgb = np.zeros((window.height, window.width, 3), dtype=np.float32)
    alpha = np.zeros(shape, dtype=np.float32)

    wet_alpha = 0.17 * np.exp(-((np.maximum(source_wet_sdf, 0.0) / 5.8) ** 2))
    wet_alpha[~np.isfinite(source_wet_sdf)] = 0.0
    wet_color = np.stack((65.0 + noise * 4.0, 78.0 + noise * 5.0, 45.0 + noise * 3.0), axis=-1)
    rgb, alpha = _alpha_over(rgb, alpha, wet_color, wet_alpha)

    outside = np.maximum(river_sdf, 0.0)
    bank_alpha = 0.25 * np.exp(-((outside / 5.6) ** 2)) * np.clip(0.78 + noise * 0.18, 0.48, 1.0)
    bank_alpha[~np.isfinite(river_sdf)] = 0.0
    bank_color = np.stack((58.0 + noise * 4.0, 69.0 + noise * 5.0, 43.0 + noise * 3.0), axis=-1)
    rgb, alpha = _alpha_over(rgb, alpha, bank_color, bank_alpha)

    edge_alpha = 0.13 * np.exp(-(((river_sdf - 0.7) / 3.0) ** 2)) * np.clip(0.72 + noise * 0.28, 0.32, 1.0)
    edge_alpha[~np.isfinite(river_sdf)] = 0.0
    edge_color = np.stack((127.0 + noise * 8.0, 108.0 + noise * 5.0, 66.0 + noise * 3.0), axis=-1)
    rgb, alpha = _alpha_over(rgb, alpha, edge_color, edge_alpha)

    plume_alpha = 0.31 * plume
    plume_color = np.stack((169.0 + noise * 9.0, 142.0 + noise * 6.0, 79.0 + noise * 4.0), axis=-1)
    rgb, alpha = _alpha_over(rgb, alpha, plume_color, plume_alpha)

    water_alpha = np.clip(0.5 - river_sdf / 1.35, 0.0, 1.0)
    water_alpha[~np.isfinite(river_sdf)] = 0.0
    estuary_alpha = 0.52 * estuary
    combined_water_alpha = np.maximum(water_alpha, estuary_alpha)
    boundary = np.exp(-((river_sdf / 3.0) ** 2))
    boundary[~np.isfinite(river_sdf)] = 0.0
    water_color = np.stack(
        (
            17.0 + noise * 5.0 + boundary * 5.0,
            100.0 + noise * 7.0 + boundary * 11.0,
            142.0 + noise * 9.0 + boundary * 10.0,
        ),
        axis=-1,
    )
    rgb, alpha = _alpha_over(rgb, alpha, water_color, combined_water_alpha)

    foam_alpha = 0.46 * foam
    foam_color = np.stack((205.0 + noise * 3.0, 226.0 + noise * 2.0, 215.0 + noise * 2.0), axis=-1)
    rgb, alpha = _alpha_over(rgb, alpha, foam_color, foam_alpha)

    rgba = np.concatenate((np.clip(rgb, 0.0, 255.0), np.clip(alpha[..., None] * 255.0, 0.0, 255.0)), axis=-1)
    return Image.fromarray(np.rint(rgba).astype(np.uint8), "RGBA")


def composite_rivers_v9(
    base: Image.Image,
    world: BasinHydrologyWorldV7,
    window: PixelWindowV9,
    *,
    plan: RiverPresentationPlanV9 | None = None,
) -> Image.Image:
    if base.size != (window.width, window.height):
        raise ValueError("base image size must equal pixel window")
    plan = plan or plan_river_presentation_v9(world, tile_px=96, world_width=80)
    result = base.convert("RGBA")
    result.alpha_composite(render_river_layer_v9(plan, window))
    return result


__all__ = [
    "ComponentGeometryV9",
    "CubicSegmentV9",
    "JunctionGeometryV9",
    "MouthGeometryV9",
    "PixelWindowV9",
    "PortConstraintV9",
    "PresentationAuditV9",
    "RiverPresentationPlanV9",
    "SourceGeometryV9",
    "composite_rivers_v9",
    "plan_river_presentation_v9",
    "render_river_layer_v9",
    "validate_presentation_plan_v9",
]
