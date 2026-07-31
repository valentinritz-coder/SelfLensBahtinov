"""Strengthened label-holder root joined across its full width to the crown."""

from __future__ import annotations

import json
import math

from selflensbahtinov.label_cartridge import (
    ParametricOpenScadRenderer,
    dimensions_for,
)
from selflensbahtinov.models import MaskGeometry
from selflensbahtinov.renderer import _EPSILON

_LABEL_TAB_OVERLAP_MM = 3.0
_LABEL_ROOT_CORNER_PENETRATION_MM = 1.0


class SolidRootOpenScadRenderer(ParametricOpenScadRenderer):
    """Render a label boss whose two inner corners are part of the crown.

    The rectangular holder by itself only intersectsed the circular crown near
    its centre.  At the holder's left and right edges, the circle curves away,
    leaving two weak, visually separated corners.  This renderer adds a solid
    root block extending inward until both full-width corners penetrate the
    crown by a controlled amount.  The cartridge pocket still begins outside
    the crown, so this root remains solid.
    """

    def _label_cartridge_modules(self, g: MaskGeometry) -> list[str]:
        dims = dimensions_for(g)
        if dims is None:
            return [
                "module label_cartridge_boss() {}",
                "module label_cartridge_pocket() {}",
            ]

        outer_radius = g.ring.outer_diameter_mm / 2
        half_width = dims.tab_width_mm / 2
        if half_width >= outer_radius:
            raise ValueError(
                "label tab width is too large to form a full-width solid root on the mounting crown"
            )

        # At x = +/- half_width, this is the Y coordinate of the circular crown.
        # Move farther inward so both rectangular root corners overlap the crown
        # by a real printable amount rather than meeting at an edge or point.
        crown_y_at_corner = math.sqrt(outer_radius**2 - half_width**2)
        root_inner_y = crown_y_at_corner - _LABEL_ROOT_CORNER_PENETRATION_MM
        root_outer_y = outer_radius + _EPSILON
        root_depth = root_outer_y - root_inner_y
        root_center_y = (root_inner_y + root_outer_y) / 2

        tab_center_y = outer_radius + (dims.tab_depth_mm - _LABEL_TAB_OVERLAP_MM) / 2
        pocket_center_y = outer_radius + dims.pocket_depth_mm / 2

        # Keep the complete build-plate face coplanar with the slotted mask.
        tab_top_z = g.thickness_mm
        tab_bottom_z = tab_top_z - dims.tab_thickness_mm
        tab_center_z = (tab_top_z + tab_bottom_z) / 2

        pocket_top_z = tab_top_z - dims.front_skin_mm
        pocket_bottom_z = tab_bottom_z + dims.rear_rail_mm
        pocket_center_z = (pocket_top_z + pocket_bottom_z) / 2

        entry_width = max(1.0, dims.pocket_width_mm - 2 * dims.rear_rail_mm)
        entry_bottom_z = tab_bottom_z - _EPSILON
        entry_top_z = pocket_top_z
        entry_height = entry_top_z - entry_bottom_z
        entry_center_z = (entry_top_z + entry_bottom_z) / 2

        return [
            f"// rear_loading_label_cartridge=true label_text={json.dumps(g.label.text)} tab_width_mm={dims.tab_width_mm:.4f} tab_depth_mm={dims.tab_depth_mm:.4f} tab_thickness_mm={dims.tab_thickness_mm:.4f}",
            f"// label_tab_front_skin_mm={dims.front_skin_mm:.4f} label_tab_side_wall_mm={dims.side_wall_mm:.4f} label_tab_rear_rail_mm={dims.rear_rail_mm:.4f} cartridge_clearance_mm={dims.clearance_mm:.4f}",
            f"// label_tab_build_face_z_mm={tab_top_z:.4f} label_tab_back_z_mm={tab_bottom_z:.4f}",
            f"// label_root_full_width=true label_root_inner_y_mm={root_inner_y:.4f} label_root_corner_penetration_mm={_LABEL_ROOT_CORNER_PENETRATION_MM:.4f}",
            f"// generated_cartridge_width_mm={dims.cartridge_width_mm:.4f} generated_cartridge_depth_mm={dims.cartridge_depth_mm:.4f} generated_cartridge_thickness_mm={dims.cartridge_thickness_mm:.4f}",
            "// Pocket opens opposite the Bahtinov face and at the outer radial end.",
            "module label_cartridge_boss() {",
            "  union() {",
            "    // Main cartridge holder.",
            f"    translate([0, {tab_center_y:.4f}, {tab_center_z:.4f}]) cube([{dims.tab_width_mm:.4f}, {dims.tab_depth_mm:.4f}, {dims.tab_thickness_mm:.4f}], center=true);",
            "    // Full-width solid root: both inner corners penetrate the circular crown.",
            f"    translate([0, {root_center_y:.4f}, {tab_center_z:.4f}]) cube([{dims.tab_width_mm:.4f}, {root_depth:.4f}, {dims.tab_thickness_mm:.4f}], center=true);",
            "  }",
            "}",
            "module label_cartridge_pocket() {",
            "  union() {",
            "    // Pocket starts outside the crown, leaving the strengthened root solid.",
            f"    translate([0, {pocket_center_y:.4f}, {pocket_center_z:.4f}]) cube([{dims.pocket_width_mm:.4f}, {dims.pocket_depth_mm + 2 * _EPSILON:.4f}, {dims.pocket_height_mm:.4f}], center=true);",
            "    // Negative-Z rear opening leaves retaining rails.",
            f"    translate([0, {pocket_center_y + dims.clearance_mm:.4f}, {entry_center_z:.4f}]) cube([{entry_width:.4f}, {dims.pocket_depth_mm + 2 * dims.clearance_mm + 2 * _EPSILON:.4f}, {entry_height:.4f}], center=true);",
            "  }",
            "}",
        ]
