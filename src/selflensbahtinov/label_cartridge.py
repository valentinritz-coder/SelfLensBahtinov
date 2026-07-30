"""Parametric rear-loading label cartridge geometry and rendering."""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass

from selflensbahtinov.models import MaskGeometry
from selflensbahtinov.renderer import OpenScadRenderer, _EPSILON

_LABEL_TAB_MIN_WIDTH_MM = 24.0
_LABEL_TAB_TEXT_PADDING_MM = 8.0
_LABEL_TAB_OVERLAP_MM = 3.0


@dataclass(frozen=True)
class LabelCartridgeDimensions:
    tab_width_mm: float
    tab_depth_mm: float
    tab_thickness_mm: float
    side_wall_mm: float
    front_skin_mm: float
    rear_rail_mm: float
    clearance_mm: float
    pocket_width_mm: float
    pocket_depth_mm: float
    pocket_height_mm: float
    cartridge_width_mm: float
    cartridge_depth_mm: float
    cartridge_thickness_mm: float


def _number(name: str, default: float | None) -> float | None:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a valid number") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be finite")
    return value


def dimensions_for(g: MaskGeometry) -> LabelCartridgeDimensions | None:
    if g.label is None or g.test_ring:
        return None

    automatic_width = max(
        _LABEL_TAB_MIN_WIDTH_MM,
        g.label.reserved_width_mm + _LABEL_TAB_TEXT_PADDING_MM,
    )
    width = _number("SLB_LABEL_TAB_WIDTH_MM", automatic_width)
    depth = _number("SLB_LABEL_TAB_DEPTH_MM", 12.0)
    thickness = max(g.thickness_mm, _number("SLB_LABEL_TAB_THICKNESS_MM", 3.0))
    side_wall = _number("SLB_LABEL_TAB_SIDE_WALL_MM", 1.2)
    front_skin = _number("SLB_LABEL_TAB_FRONT_SKIN_MM", 1.2)
    rear_rail = _number("SLB_LABEL_TAB_REAR_RAIL_MM", 0.6)
    clearance = _number("SLB_LABEL_CARTRIDGE_CLEARANCE_MM", 0.25)

    values = {
        "label tab width": width,
        "label tab depth": depth,
        "label tab thickness": thickness,
        "label tab side wall": side_wall,
        "label tab front skin": front_skin,
        "label tab rear rail": rear_rail,
        "label cartridge clearance": clearance,
    }
    for label, value in values.items():
        if value is None or value <= 0:
            raise ValueError(f"{label} must be greater than zero")

    if thickness >= g.ring.depth_mm:
        raise ValueError(
            f"label tab thickness ({thickness:.4f} mm) must be smaller than "
            f"ring overlap/depth ({g.ring.depth_mm:.4f} mm)"
        )
    if depth <= _LABEL_TAB_OVERLAP_MM + clearance:
        raise ValueError("label tab depth is too small for rim overlap and clearance")
    if width <= 2 * side_wall + 1.0:
        raise ValueError("label tab width leaves no printable cartridge pocket")
    if thickness <= front_skin + rear_rail + 0.4:
        raise ValueError(
            "label tab thickness must exceed front skin + rear rail by at least 0.4 mm"
        )

    pocket_width = width - 2 * side_wall
    pocket_depth = depth - _LABEL_TAB_OVERLAP_MM - clearance
    pocket_height = thickness - front_skin - rear_rail
    cartridge_width = pocket_width - 2 * clearance
    cartridge_depth = pocket_depth - 2 * clearance
    cartridge_thickness = pocket_height - 2 * clearance
    if min(cartridge_width, cartridge_depth, cartridge_thickness) <= 0:
        raise ValueError("label cartridge clearance leaves no printable cartridge")

    return LabelCartridgeDimensions(
        tab_width_mm=round(width, 4),
        tab_depth_mm=round(depth, 4),
        tab_thickness_mm=round(thickness, 4),
        side_wall_mm=round(side_wall, 4),
        front_skin_mm=round(front_skin, 4),
        rear_rail_mm=round(rear_rail, 4),
        clearance_mm=round(clearance, 4),
        pocket_width_mm=round(pocket_width, 4),
        pocket_depth_mm=round(pocket_depth, 4),
        pocket_height_mm=round(pocket_height, 4),
        cartridge_width_mm=round(cartridge_width, 4),
        cartridge_depth_mm=round(cartridge_depth, 4),
        cartridge_thickness_mm=round(cartridge_thickness, 4),
    )


class ParametricOpenScadRenderer(OpenScadRenderer):
    def _label_cartridge_modules(self, g: MaskGeometry) -> list[str]:
        dims = dimensions_for(g)
        if dims is None:
            return [
                "module label_cartridge_boss() {}",
                "module label_cartridge_pocket() {}",
            ]

        outer_radius = g.ring.outer_diameter_mm / 2
        tab_center_y = outer_radius + (dims.tab_depth_mm - _LABEL_TAB_OVERLAP_MM) / 2
        pocket_center_y = outer_radius + dims.pocket_depth_mm / 2
        pocket_floor_z = dims.front_skin_mm
        pocket_top_z = dims.tab_thickness_mm - dims.rear_rail_mm
        entry_width = max(1.0, dims.pocket_width_mm - 2 * dims.rear_rail_mm)
        entry_height = pocket_top_z + _EPSILON

        return [
            f"// rear_loading_label_cartridge=true label_text={json.dumps(g.label.text)} tab_width_mm={dims.tab_width_mm:.4f} tab_depth_mm={dims.tab_depth_mm:.4f} tab_thickness_mm={dims.tab_thickness_mm:.4f}",
            f"// label_tab_front_skin_mm={dims.front_skin_mm:.4f} label_tab_side_wall_mm={dims.side_wall_mm:.4f} label_tab_rear_rail_mm={dims.rear_rail_mm:.4f} cartridge_clearance_mm={dims.clearance_mm:.4f}",
            f"// generated_cartridge_width_mm={dims.cartridge_width_mm:.4f} generated_cartridge_depth_mm={dims.cartridge_depth_mm:.4f} generated_cartridge_thickness_mm={dims.cartridge_thickness_mm:.4f}",
            "// Pocket opens opposite the Bahtinov face and at the outer radial end.",
            "module label_cartridge_boss() {",
            f"  translate([0, {tab_center_y:.4f}, {dims.tab_thickness_mm / 2:.4f}]) cube([{dims.tab_width_mm:.4f}, {dims.tab_depth_mm:.4f}, {dims.tab_thickness_mm:.4f}], center=true);",
            "}",
            "module label_cartridge_pocket() {",
            "  union() {",
            "    // Impact-resistant floor remains against the Bahtinov face.",
            f"    translate([0, {pocket_center_y:.4f}, {pocket_floor_z + dims.pocket_height_mm / 2:.4f}]) cube([{dims.pocket_width_mm:.4f}, {dims.pocket_depth_mm + 2 * _EPSILON:.4f}, {dims.pocket_height_mm:.4f}], center=true);",
            "    // Narrower rear opening leaves retaining rails.",
            f"    translate([0, {pocket_center_y + dims.clearance_mm:.4f}, {entry_height / 2 - _EPSILON:.4f}]) cube([{entry_width:.4f}, {dims.pocket_depth_mm + 2 * dims.clearance_mm + 2 * _EPSILON:.4f}, {entry_height + 2 * _EPSILON:.4f}], center=true);",
            "  }",
            "}",
        ]

    def render_label_cartridge_scad(self, g: MaskGeometry) -> str:
        dims = dimensions_for(g)
        if dims is None:
            raise ValueError("label cartridge requires a labelled full mask")

        text_size = min(
            4.0,
            max(2.0, dims.cartridge_width_mm / max(len(g.label.text), 1) * 1.35),
        )
        engraving_depth = min(0.4, dims.cartridge_thickness_mm / 3)
        return "\n".join(
            [
                "// Generated by SelfLensBahtinov removable label cartridge.",
                "$fn = 64;",
                f"// label_text={json.dumps(g.label.text)}",
                f"// cartridge_width_mm={dims.cartridge_width_mm:.4f} cartridge_depth_mm={dims.cartridge_depth_mm:.4f} cartridge_thickness_mm={dims.cartridge_thickness_mm:.4f}",
                "difference() {",
                f"  cube([{dims.cartridge_width_mm:.4f}, {dims.cartridge_depth_mm:.4f}, {dims.cartridge_thickness_mm:.4f}], center=false);",
                f"  translate([{dims.cartridge_width_mm / 2:.4f}, {dims.cartridge_depth_mm / 2:.4f}, {dims.cartridge_thickness_mm - engraving_depth:.4f}])",
                f"    linear_extrude(height={engraving_depth + _EPSILON:.4f}) text({json.dumps(g.label.text)}, size={text_size:.4f}, halign=\"center\", valign=\"center\");",
                "}",
                "",
            ]
        )
