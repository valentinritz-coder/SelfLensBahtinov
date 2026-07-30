"""OpenSCAD rendering for already-calculated V1 mask geometry."""

from __future__ import annotations

import json
import math
from abc import ABC, abstractmethod

from selflensbahtinov.models import MaskGeometry

_EPSILON = 0.02
_LABEL_TAB_MIN_WIDTH_MM = 24.0
_LABEL_TAB_TEXT_PADDING_MM = 8.0
_LABEL_TAB_RADIAL_DEPTH_MM = 12.0
_LABEL_TAB_OVERLAP_MM = 3.0
_LABEL_TAB_SIDE_WALL_MM = 1.2
_LABEL_TAB_FRONT_SKIN_MM = 0.6
_LABEL_TAB_REAR_RAIL_MM = 0.6
_LABEL_CARTRIDGE_CLEARANCE_MM = 0.25


class MaskRenderer(ABC):
    @abstractmethod
    def render_scad(self, geometry: MaskGeometry) -> str:
        """Render geometry as readable SCAD."""



def _outer_face_fillet_cut_profile(
    *,
    outer_radius_mm: float,
    thickness_mm: float,
    radius_mm: float,
    epsilon_mm: float = _EPSILON,
) -> tuple[tuple[float, float], ...]:
    if radius_mm <= 0:
        return ()
    cx = outer_radius_mm - radius_mm
    cz = thickness_mm - radius_mm
    segments = max(6, min(32, int(radius_mm * 12)))
    arc = tuple(
        (
            cx + radius_mm * math.cos(math.radians(angle)),
            cz + radius_mm * math.sin(math.radians(angle)),
        )
        for angle in (90 * i / segments for i in range(segments + 1))
    )
    return (
        (cx, thickness_mm + epsilon_mm),
        (outer_radius_mm + epsilon_mm, thickness_mm + epsilon_mm),
        (outer_radius_mm + epsilon_mm, cz),
        *arc,
    )


def _scad_string(value: str) -> str:
    return json.dumps(value)


class OpenScadRenderer(MaskRenderer):
    def _mounting_module(self, g: MaskGeometry) -> list[str]:
        pts = ", ".join(f"[{p.radius_mm:.4f}, {p.z_mm:.4f}]" for p in g.ring.cross_section)
        return [
            f"// mount_diameter_mm={g.ring.mount_diameter_mm:.4f} clearance_mm={g.ring.clearance_mm:.4f} inner_fit_diameter_mm={g.ring.inner_diameter_mm:.4f}",
            f"// ring_depth_mm={g.ring.depth_mm:.4f} lead_in_chamfer_mm={g.ring.lead_in_chamfer_mm:.4f} outer_edge_radius_mm={g.ring.outer_edge_radius_mm:.4f} straight_engagement_mm={g.ring.straight_engagement_mm:.4f}",
            f"// mounting_entry_side={g.ring.mounting_entry_side}; print with the slotted Bahtinov face on the build plate and the negative-Z mounting side facing upward.",
            "module mounting_ring() {",
            f"  rotate_extrude(convexity=4) polygon(points=[{pts}]);",
            "}",
        ]

    def _label_cartridge_modules(self, g: MaskGeometry) -> list[str]:
        if g.label is None:
            return [
                "module label_cartridge_boss() {}",
                "module label_cartridge_pocket() {}",
            ]

        outer_radius = g.ring.outer_diameter_mm / 2
        tab_width = max(
            _LABEL_TAB_MIN_WIDTH_MM,
            g.label.reserved_width_mm + _LABEL_TAB_TEXT_PADDING_MM,
        )
        tab_center_y = (
            outer_radius
            + (_LABEL_TAB_RADIAL_DEPTH_MM - _LABEL_TAB_OVERLAP_MM) / 2
        )
        pocket_width = tab_width - 2 * _LABEL_TAB_SIDE_WALL_MM
        pocket_depth = (
            _LABEL_TAB_RADIAL_DEPTH_MM
            - _LABEL_TAB_OVERLAP_MM
            - _LABEL_CARTRIDGE_CLEARANCE_MM
        )
        pocket_center_y = outer_radius + pocket_depth / 2
        pocket_floor_z = _LABEL_TAB_FRONT_SKIN_MM
        pocket_top_z = max(
            pocket_floor_z + 0.2,
            g.thickness_mm - _LABEL_TAB_REAR_RAIL_MM,
        )
        pocket_height = pocket_top_z - pocket_floor_z
        entry_width = max(
            1.0,
            pocket_width - 2 * _LABEL_TAB_REAR_RAIL_MM,
        )
        entry_height = pocket_top_z + _EPSILON

        return [
            f"// rear_loading_label_cartridge=true tab_width_mm={tab_width:.4f} tab_depth_mm={_LABEL_TAB_RADIAL_DEPTH_MM:.4f}",
            f"// cartridge_pocket_width_mm={pocket_width:.4f} cartridge_pocket_depth_mm={pocket_depth:.4f} suggested_cartridge_thickness_mm={max(0.2, pocket_height - _LABEL_CARTRIDGE_CLEARANCE_MM):.4f}",
            "// The cartridge channel opens on the negative-Z mounting side and at the outer radial end.",
            "// With the slotted Bahtinov face on the build plate, the pocket faces upward and needs no generated supports.",
            "module label_cartridge_boss() {",
            f"  translate([0, {tab_center_y:.4f}, mask_thickness_mm / 2]) cube([{tab_width:.4f}, {_LABEL_TAB_RADIAL_DEPTH_MM:.4f}, mask_thickness_mm], center=true);",
            "}",
            "module label_cartridge_pocket() {",
            "  union() {",
            "    // Main cartridge cavity, leaving a solid skin against the printed Bahtinov face.",
            f"    translate([0, {pocket_center_y:.4f}, {pocket_floor_z + pocket_height / 2:.4f}]) cube([{pocket_width:.4f}, {pocket_depth + 2 * _EPSILON:.4f}, {pocket_height:.4f}], center=true);",
            "    // Narrower rear opening leaves two longitudinal retaining rails.",
            f"    translate([0, {pocket_center_y + _LABEL_CARTRIDGE_CLEARANCE_MM:.4f}, {entry_height / 2 - _EPSILON:.4f}]) cube([{entry_width:.4f}, {pocket_depth + 2 * _LABEL_CARTRIDGE_CLEARANCE_MM + 2 * _EPSILON:.4f}, {entry_height + 2 * _EPSILON:.4f}], center=true);",
            "  }",
            "}",
        ]

    def _outer_face_fillet_module(self, g: MaskGeometry) -> list[str]:
        radius = g.outer_face_fillet_radius_mm
        if radius <= 0:
            return ["module outer_face_fillet_cut() {}"]
        profile = _outer_face_fillet_cut_profile(
            outer_radius_mm=g.ring.outer_diameter_mm / 2,
            thickness_mm=g.thickness_mm,
            radius_mm=radius,
        )
        pts = ", ".join(f"[{r:.4f}, {z:.4f}]" for r, z in profile)
        return [
            f"// outer_face_fillet_radius_mm={radius:.4f}",
            "module outer_face_fillet_cut() {",
            f"  rotate_extrude(convexity=4) polygon(points=[{pts}]);",
            "}",
        ]

    def render_scad(self, geometry: MaskGeometry) -> str:
        if geometry.test_ring:
            return self._render_test_ring(geometry)
        return self._render_full_mask(geometry)

    def _common_modules(self, geometry: MaskGeometry) -> list[str]:
        radius = geometry.clear_aperture_mm / 2
        return [
            "$fn = 128;",
            f"epsilon = {_EPSILON:.3f};",
            "module slot_rectangle(cx, cy, len, wid, angle) {",
            "  translate([cx, cy, mask_thickness_mm / 2]) rotate([0, 0, angle]) cube([len, wid, mask_thickness_mm + 2 * epsilon], center=true);",
            "}",
            "module aperture_clip() {",
            f"  translate([0, 0, -epsilon]) cylinder(h=mask_thickness_mm + 2 * epsilon, d={geometry.clear_aperture_mm:.4f});",
            "}",
            f"region_gap_mm = {geometry.region_gap_mm:.4f};",
            "module region_clip(region) {",
            f"  r = {radius + geometry.slot_spacing_mm * 2:.4f};",
            "  g = region_gap_mm / 2;",
            "  points = region == \"left-reference\" ? [[-r, -r], [-g, -r], [-g, r], [-r, r]] :",
            "    region == \"right-upper\" ? [[g, g], [r, g], [r, r], [g, r]] :",
            "    region == \"right-lower\" ? [[g, -g], [r, -g], [r, -r], [g, -r]] :",
            "    region == \"tribahtinov-0\" ? concat([[0, 0]], [for (i = [0:8]) [r * cos(-60 + 60 * i / 8), r * sin(-60 + 60 * i / 8)]]) :",
            "    region == \"tribahtinov-1\" ? concat([[0, 0]], [for (i = [0:8]) [r * cos(0 + 60 * i / 8), r * sin(0 + 60 * i / 8)]]) :",
            "    region == \"tribahtinov-2\" ? concat([[0, 0]], [for (i = [0:8]) [r * cos(60 + 60 * i / 8), r * sin(60 + 60 * i / 8)]]) :",
            "    region == \"tribahtinov-3\" ? concat([[0, 0]], [for (i = [0:8]) [r * cos(120 + 60 * i / 8), r * sin(120 + 60 * i / 8)]]) :",
            "    region == \"tribahtinov-4\" ? concat([[0, 0]], [for (i = [0:8]) [r * cos(180 + 60 * i / 8), r * sin(180 + 60 * i / 8)]]) :",
            "    concat([[0, 0]], [for (i = [0:8]) [r * cos(240 + 60 * i / 8), r * sin(240 + 60 * i / 8)]]);",
            "  translate([0, 0, -epsilon]) linear_extrude(height=mask_thickness_mm + 2 * epsilon) polygon(points);",
            "}",
            "module clipped_slot(cx, cy, len, wid, angle, region) {",
            "  intersection() {",
            "    slot_rectangle(cx, cy, len, wid, angle);",
            "    aperture_clip();",
            "    region_clip(region);",
            "  }",
            "}",
        ]

    def _render_full_mask(self, g: MaskGeometry) -> str:
        lines = [
            "// Generated by SelfLensBahtinov V1. Python calculated all mask geometry.",
            f"// profile={g.profile_slug} mask={g.mask_type.value} clear_aperture_mm={g.clear_aperture_mm:.3f} pattern_border_mm={g.pattern_border_mm:.3f} outer_face_fillet_radius_mm={g.outer_face_fillet_radius_mm:.4f}",
            f"mask_thickness_mm = {g.thickness_mm:.4f};",
            *self._common_modules(g),
            *self._mounting_module(g),
            *self._label_cartridge_modules(g),
            *self._outer_face_fillet_module(g),
            "difference() {",
            "  union() {",
            "    // Solid front face. Do not subtract a circular clear-aperture hole.",
            f"    cylinder(h=mask_thickness_mm, d={g.ring.outer_diameter_mm:.4f});",
            "    // Shared Python cross-section mounting skirt: lead-in chamfer and external edge treatment.",
            "    mounting_ring();",
            "    // Optional radial boss containing the replaceable rear-loaded label cartridge.",
            "    label_cartridge_boss();",
            "  }",
        ]
        for slot in g.slots:
            lines.append(
                f'  clipped_slot({slot.center.x:.4f}, {slot.center.y:.4f}, {slot.length_mm:.4f}, {slot.width_mm:.4f}, {slot.angle_deg:.3f}, "{slot.region.value}");'
            )
        if g.outer_face_fillet_radius_mm > 0:
            lines.append("  outer_face_fillet_cut();")
        if g.label:
            lines.extend(
                [
                    "  // Rear-loading cartridge pocket replaces the former engraved face label.",
                    "  label_cartridge_pocket();",
                ]
            )
        lines.extend(["}", ""])
        return "\n".join(lines)

    def _render_test_ring(self, g: MaskGeometry) -> str:
        return "\n".join(
            [
                "// Generated by SelfLensBahtinov V1 fit-test ring.",
                "$fn = 128;",
                f"epsilon = {_EPSILON:.3f};",
                f"// test_ring_depth_mm={g.ring.depth_mm:.3f}",
                *self._mounting_module(g),
                "mounting_ring();",
                "",
            ]
        )
