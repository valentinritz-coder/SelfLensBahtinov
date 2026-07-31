from selflensbahtinov.models import (
    LabelGeometry,
    MaskGeometry,
    MaskType,
    MountType,
    Point2D,
    RingGeometry,
)
from selflensbahtinov.three_oclock_label import ThreeOClockLabelRenderer


def geometry(*, labelled=True, test_ring=False):
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
        label=(
            LabelGeometry("400mm", Point2D(0, 0), 3.0, 0.0, 11.25)
            if labelled
            else None
        ),
        grating=None,
        test_ring=test_ring,
    )


def test_holder_and_pocket_are_rotated_from_12_to_3_oclock():
    scad = ThreeOClockLabelRenderer().render_scad(geometry())

    assert "label_holder_clock_position=3" in scad
    assert "label_holder_rotation_deg=-90.0" in scad
    assert "module label_cartridge_boss_at_12()" in scad
    assert "module label_cartridge_pocket_at_12()" in scad
    assert "rotate([0, 0, -90.0]) label_cartridge_boss_at_12();" in scad
    assert "rotate([0, 0, -90.0]) label_cartridge_pocket_at_12();" in scad


def test_rotation_preserves_strengthened_root_and_flush_build_face():
    scad = ThreeOClockLabelRenderer().render_scad(geometry())

    assert "label_root_full_width=true" in scad
    assert "label_root_corner_penetration_mm=1.0000" in scad
    assert "label_tab_build_face_z_mm=2.0000" in scad
    assert "label_tab_back_z_mm=-1.0000" in scad


def test_unlabelled_mask_keeps_empty_rotated_modules():
    scad = ThreeOClockLabelRenderer().render_scad(geometry(labelled=False))

    assert "module label_cartridge_boss_at_12() {}" in scad
    assert "module label_cartridge_pocket_at_12() {}" in scad
