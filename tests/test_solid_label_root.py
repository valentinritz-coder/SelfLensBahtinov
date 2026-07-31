import math
import re

import pytest

from selflensbahtinov.models import (
    LabelGeometry,
    MaskGeometry,
    MaskType,
    MountType,
    Point2D,
    RingGeometry,
)
from selflensbahtinov.solid_label_root import SolidRootOpenScadRenderer


def geometry():
    return MaskGeometry(
        profile_slug="test-lens",
        mask_type=MaskType.BAHTINOV,
        clear_aperture_mm=80.0,
        slot_width_mm=1.2,
        slot_spacing_mm=5.0,
        slots=(),
        ring=RingGeometry(
            mount_type=MountType.HOOD_OUTER_SLIP_FIT,
            mount_diameter_mm=90.0,
            inner_diameter_mm=90.7,
            outer_diameter_mm=96.7,
            wall_thickness_mm=3.0,
            depth_mm=15.0,
            clearance_mm=0.35,
        ),
        thickness_mm=2.0,
        pattern_border_mm=3.0,
        region_gap_mm=3.0,
        label=LabelGeometry("400mm", Point2D(0, 0), 3.0, 0.0, 11.25),
        grating=None,
    )


def test_label_holder_root_connects_both_corners_to_circular_crown():
    g = geometry()
    scad = SolidRootOpenScadRenderer().render_scad(g)

    assert "label_root_full_width=true" in scad
    assert "Full-width solid root" in scad

    match = re.search(
        r"label_root_inner_y_mm=([0-9.]+).*label_root_corner_penetration_mm=([0-9.]+)",
        scad,
    )
    assert match is not None
    root_inner_y = float(match.group(1))
    penetration = float(match.group(2))

    outer_radius = g.ring.outer_diameter_mm / 2
    tab_width = 24.0
    crown_y_at_corner = math.sqrt(outer_radius**2 - (tab_width / 2) ** 2)

    # Both +/- width/2 corners are inside the circular crown by a real amount,
    # not merely tangent or connected only around the holder centreline.
    assert root_inner_y == pytest.approx(crown_y_at_corner - penetration, abs=1e-4)
    assert penetration >= 1.0


def test_root_keeps_build_face_flush_and_pocket_outside_crown():
    scad = SolidRootOpenScadRenderer().render_scad(geometry())
    assert "label_tab_build_face_z_mm=2.0000" in scad
    assert "label_tab_back_z_mm=-1.0000" in scad
    assert "Pocket starts outside the crown, leaving the strengthened root solid" in scad
