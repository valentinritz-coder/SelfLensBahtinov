import pytest

from selflensbahtinov.label_cartridge import (
    ParametricOpenScadRenderer,
    dimensions_for,
)
from selflensbahtinov.models import (
    LabelGeometry,
    MaskGeometry,
    MaskType,
    MountType,
    Point2D,
    RingGeometry,
)


def geometry(*, labelled=True, test_ring=False, ring_depth=15.0):
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
            depth_mm=ring_depth,
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


def test_default_floor_is_thicker_and_cartridge_is_rendered(monkeypatch):
    monkeypatch.delenv("SLB_LABEL_TAB_FRONT_SKIN_MM", raising=False)
    g = geometry()
    dims = dimensions_for(g)
    assert dims.front_skin_mm == pytest.approx(1.2)
    assert dims.tab_thickness_mm == pytest.approx(3.0)

    renderer = ParametricOpenScadRenderer()
    mask_scad = renderer.render_scad(g)
    cartridge_scad = renderer.render_label_cartridge_scad(g)
    assert "label_tab_front_skin_mm=1.2000" in mask_scad
    assert "generated_cartridge_width_mm=" in mask_scad
    assert 'text("400mm"' in cartridge_scad


def test_holder_is_flush_with_bahtinov_build_face_and_extends_only_rearward():
    g = geometry()
    scad = ParametricOpenScadRenderer().render_scad(g)

    # Front plate spans z=0..2 mm. A 3 mm holder must therefore span
    # z=-1..2 mm, never z=0..3 mm, so the build-plate face remains coplanar.
    assert "label_tab_build_face_z_mm=2.0000 label_tab_back_z_mm=-1.0000" in scad
    assert "translate([0, 52.8500, 0.5000]) cube([24.0000, 12.0000, 3.0000]" in scad
    assert "translate([0, 52.7250, 0.2000]) cube([21.6000, 8.7900, 1.2000]" in scad
    assert "translate([0, 52.9750, -0.1100]) cube([20.4000, 9.2900, 1.8200]" in scad


def test_dimensions_are_configurable(monkeypatch):
    monkeypatch.setenv("SLB_LABEL_TAB_WIDTH_MM", "32")
    monkeypatch.setenv("SLB_LABEL_TAB_DEPTH_MM", "14")
    monkeypatch.setenv("SLB_LABEL_TAB_THICKNESS_MM", "4")
    monkeypatch.setenv("SLB_LABEL_TAB_FRONT_SKIN_MM", "1.6")
    monkeypatch.setenv("SLB_LABEL_TAB_SIDE_WALL_MM", "1.4")
    monkeypatch.setenv("SLB_LABEL_TAB_REAR_RAIL_MM", "0.8")
    monkeypatch.setenv("SLB_LABEL_CARTRIDGE_CLEARANCE_MM", "0.3")

    dims = dimensions_for(geometry())
    assert dims.tab_width_mm == pytest.approx(32)
    assert dims.tab_depth_mm == pytest.approx(14)
    assert dims.tab_thickness_mm == pytest.approx(4)
    assert dims.front_skin_mm == pytest.approx(1.6)
    assert dims.cartridge_width_mm == pytest.approx(28.6)


def test_tab_thickness_must_be_smaller_than_ring_overlap(monkeypatch):
    monkeypatch.setenv("SLB_LABEL_TAB_THICKNESS_MM", "15")
    with pytest.raises(ValueError, match="must be smaller than ring overlap/depth"):
        dimensions_for(geometry(ring_depth=15))


def test_no_cartridge_for_unlabelled_mask_or_test_ring():
    assert dimensions_for(geometry(labelled=False)) is None
    assert dimensions_for(geometry(test_ring=True)) is None
