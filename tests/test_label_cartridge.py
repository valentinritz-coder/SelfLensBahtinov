from selflensbahtinov.models import (
    LabelGeometry,
    MaskGeometry,
    MaskType,
    MountType,
    Point2D,
    RingCrossSectionPoint,
    RingGeometry,
)
from selflensbahtinov.renderer import OpenScadRenderer


def _geometry(*, with_label: bool = True, test_ring: bool = False) -> MaskGeometry:
    ring = RingGeometry(
        mount_type=MountType.HOOD_OUTER_SLIP_FIT,
        mount_diameter_mm=90.0,
        inner_diameter_mm=90.6,
        outer_diameter_mm=96.6,
        wall_thickness_mm=3.0,
        depth_mm=8.0,
        clearance_mm=0.3,
        lead_in_chamfer_mm=1.0,
        outer_edge_radius_mm=0.5,
        straight_engagement_mm=7.0,
        cross_section=(
            RingCrossSectionPoint(46.3, -8.0),
            RingCrossSectionPoint(47.8, -8.0),
            RingCrossSectionPoint(48.3, -7.5),
            RingCrossSectionPoint(48.3, 0.0),
            RingCrossSectionPoint(45.3, 0.0),
            RingCrossSectionPoint(45.3, -7.0),
        ),
    )
    label = (
        LabelGeometry(
            text="400mm",
            position=Point2D(0.0, -43.0),
            size_mm=3.0,
            angle_deg=0.0,
            reserved_width_mm=13.5,
        )
        if with_label
        else None
    )
    return MaskGeometry(
        profile_slug="test-lens",
        mask_type=MaskType.BAHTINOV,
        clear_aperture_mm=86.0,
        slot_width_mm=2.0,
        slot_spacing_mm=4.0,
        slots=(),
        ring=ring,
        thickness_mm=2.0,
        pattern_border_mm=2.3,
        region_gap_mm=2.0,
        label=label,
        grating=None,
        test_ring=test_ring,
    )


def test_label_creates_rear_loading_cartridge_boss_and_pocket():
    scad = OpenScadRenderer().render_scad(_geometry())

    assert "rear_loading_label_cartridge=true" in scad
    assert "module label_cartridge_boss()" in scad
    assert "module label_cartridge_pocket()" in scad
    assert "label_cartridge_boss();" in scad
    assert "label_cartridge_pocket();" in scad
    assert "negative-Z mounting side" in scad
    assert "linear_extrude(height=0.4) text(" not in scad


def test_no_label_keeps_cartridge_modules_as_no_ops():
    scad = OpenScadRenderer().render_scad(_geometry(with_label=False))

    assert "module label_cartridge_boss() {}" in scad
    assert "module label_cartridge_pocket() {}" in scad
    assert "rear_loading_label_cartridge=true" not in scad


def test_fit_test_ring_does_not_include_label_cartridge():
    scad = OpenScadRenderer().render_scad(
        _geometry(with_label=False, test_ring=True)
    )

    assert "label_cartridge" not in scad
