"""Topology-aware filtering for clipped Bahtinov slot fragments."""

from __future__ import annotations

from dataclasses import replace
import math

from selflensbahtinov.models import GratingRegion, MaskGeometry, Point2D, SlotGeometry

_CIRCLE_SEGMENTS = 256
_BOUNDARY_TOLERANCE_MM = 0.03
_COLLINEAR_TOLERANCE = 1e-7
_MIN_STRAIGHT_EDGE_MM = 0.05

Polygon = tuple[Point2D, ...]


def _candidate_slot_polygon(slot: SlotGeometry) -> Polygon:
    angle = math.radians(slot.angle_deg)
    ux, uy = math.cos(angle), math.sin(angle)
    vx, vy = -math.sin(angle), math.cos(angle)
    return tuple(
        Point2D(
            slot.center.x + sx * ux * slot.length_mm / 2 + sy * vx * slot.width_mm / 2,
            slot.center.y + sx * uy * slot.length_mm / 2 + sy * vy * slot.width_mm / 2,
        )
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )


def _circle_polygon(radius: float) -> Polygon:
    return tuple(
        Point2D(
            radius * math.cos(2 * math.pi * index / _CIRCLE_SEGMENTS),
            radius * math.sin(2 * math.pi * index / _CIRCLE_SEGMENTS),
        )
        for index in range(_CIRCLE_SEGMENTS)
    )


def _region_polygon(region: GratingRegion, radius: float, gap: float) -> Polygon:
    extent = radius * 3
    half_gap = gap / 2
    if region is GratingRegion.LEFT_REFERENCE:
        points = [(-extent, -extent), (-half_gap, -extent), (-half_gap, extent), (-extent, extent)]
    elif region is GratingRegion.RIGHT_UPPER:
        points = [(half_gap, half_gap), (extent, half_gap), (extent, extent), (half_gap, extent)]
    elif region is GratingRegion.RIGHT_LOWER:
        points = [(half_gap, -half_gap), (half_gap, -extent), (extent, -extent), (extent, -half_gap)]
    else:
        return ()
    return tuple(Point2D(x, y) for x, y in points)


def _cross(a: Point2D, b: Point2D, c: Point2D) -> float:
    return (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)


def _intersection(p1: Point2D, p2: Point2D, q1: Point2D, q2: Point2D) -> Point2D:
    dx1, dy1 = p2.x - p1.x, p2.y - p1.y
    dx2, dy2 = q2.x - q1.x, q2.y - q1.y
    denominator = dx1 * dy2 - dy1 * dx2
    if abs(denominator) < 1e-12:
        return p2
    t = ((q1.x - p1.x) * dy2 - (q1.y - p1.y) * dx2) / denominator
    return Point2D(p1.x + t * dx1, p1.y + t * dy1)


def _clip_polygon(subject: Polygon, clipper: Polygon) -> Polygon:
    output = list(subject)
    for a, b in zip(clipper, clipper[1:] + clipper[:1]):
        incoming = output
        output = []
        if not incoming:
            break
        previous = incoming[-1]
        previous_inside = _cross(a, b, previous) >= -1e-9
        for current in incoming:
            current_inside = _cross(a, b, current) >= -1e-9
            if current_inside:
                if not previous_inside:
                    output.append(_intersection(previous, current, a, b))
                output.append(current)
            elif previous_inside:
                output.append(_intersection(previous, current, a, b))
            previous = current
            previous_inside = current_inside
    return tuple(output)


def _clipped_polygon(slot: SlotGeometry, radius: float, gap: float) -> Polygon:
    polygon = _clip_polygon(_candidate_slot_polygon(slot), _circle_polygon(radius))
    region = _region_polygon(slot.region, radius, gap)
    return _clip_polygon(polygon, region) if region else polygon


def _is_on_circle(point: Point2D, radius: float) -> bool:
    return abs(math.hypot(point.x, point.y) - radius) <= _BOUNDARY_TOLERANCE_MM


def _circular_run_count(polygon: Polygon, radius: float) -> int:
    if not polygon:
        return 0
    flags = [_is_on_circle(point, radius) for point in polygon]
    if all(flags):
        return 1
    return sum(flag and not flags[index - 1] for index, flag in enumerate(flags))


def _straight_edge_group_count(polygon: Polygon, radius: float) -> int:
    """Count meaningful non-circular contour directions after clipping."""
    directions: list[float] = []
    for first, second in zip(polygon, polygon[1:] + polygon[:1]):
        if _is_on_circle(first, radius) and _is_on_circle(second, radius):
            continue
        dx, dy = second.x - first.x, second.y - first.y
        length = math.hypot(dx, dy)
        if length < _MIN_STRAIGHT_EDGE_MM:
            continue
        angle = math.atan2(dy, dx) % math.pi
        if not any(abs(math.sin(angle - existing)) <= _COLLINEAR_TOLERANCE for existing in directions):
            directions.append(angle)
    return len(directions)


def is_valid_clipped_slot(slot: SlotGeometry, *, radius: float, region_gap_mm: float) -> bool:
    """Return whether a clipped slot still has a usable slot-like contour.

    A valid slot may be untouched or have one end replaced by the aperture arc.
    Fragments with two separate circular boundary runs, or too little remaining
    straight structure, are rejected regardless of the configured length limit.
    """
    if slot.region not in {
        GratingRegion.LEFT_REFERENCE,
        GratingRegion.RIGHT_UPPER,
        GratingRegion.RIGHT_LOWER,
    }:
        return True
    polygon = _clipped_polygon(slot, radius, region_gap_mm)
    if len(polygon) < 3:
        return False
    if _circular_run_count(polygon, radius) > 1:
        return False
    return _straight_edge_group_count(polygon, radius) >= 2


def remove_malformed_slots(geometry: MaskGeometry) -> MaskGeometry:
    """Remove malformed clipped fragments while preserving length filtering.

    The existing minimum useful length remains a printability threshold. This
    topology pass is unconditional, so setting that threshold to zero still
    removes fragments with two curved ends or insufficient straight structure.
    """
    if geometry.test_ring or geometry.mask_type.value != "bahtinov":
        return geometry
    radius = geometry.clear_aperture_mm / 2
    retained = tuple(
        slot
        for slot in geometry.slots
        if is_valid_clipped_slot(
            slot,
            radius=radius,
            region_gap_mm=geometry.region_gap_mm,
        )
    )
    if not retained:
        raise ValueError("topology-aware slot filtering removed every Bahtinov slot")
    regions = {slot.region for slot in retained}
    required = {
        GratingRegion.LEFT_REFERENCE,
        GratingRegion.RIGHT_UPPER,
        GratingRegion.RIGHT_LOWER,
    }
    if not required.issubset(regions):
        raise ValueError("topology-aware slot filtering left a required grating region empty")
    return replace(geometry, slots=retained)
