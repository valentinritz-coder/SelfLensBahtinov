from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from selflensbahtinov.algorithms import AlgorithmOptions, calculate_mask
from selflensbahtinov.generator import generate, openscad_command_for
from selflensbahtinov.models import GenerationRequest, MaskType, MountType, OutputFormat
from selflensbahtinov.openscad import OpenScadError, output_path, supports_format
from selflensbahtinov.renderer import OpenScadRenderer
from selflensbahtinov.validation import (
    ProfileValidationError,
    load_profile,
    search_profiles,
    validate_profile_data,
)

PROFILE_PATHS = [
    Path("profiles/fujifilm-xf100-400.json"),
    Path("profiles/fujifilm-xf16-80.json"),
]
P = PROFILE_PATHS[0]


def prof(path: Path = P):
    return load_profile(path)


def opts(
    profile=None,
    mt=MaskType.BAHTINOV,
    mount=MountType.FILTER_DIAMETER_SLIP_FIT,
    test=False,
):
    p = profile or prof()
    return AlgorithmOptions(
        mt,
        mount,
        p.recommended_focus.focal_length_mm,
        p.recommended_focus.aperture_f_number,
        p.defaults.fit_clearance_mm,
        p.defaults.pattern_border_mm,
        True,
        test,
    )


def request(tmp_path: Path, fmt: tuple[OutputFormat, ...] = (OutputFormat.SCAD,)):
    p = prof()
    return GenerationRequest(
        p,
        MaskType.BAHTINOV,
        MountType.FILTER_DIAMETER_SLIP_FIT,
        fmt,
        p.recommended_focus.focal_length_mm,
        p.recommended_focus.aperture_f_number,
        p.defaults.fit_clearance_mm,
        p.defaults.pattern_border_mm,
        True,
        tmp_path,
        "openscad",
    )


def test_loading_both_profiles():
    p1 = load_profile(PROFILE_PATHS[0])
    p2 = load_profile(PROFILE_PATHS[1])
    assert p1.mounting.filter_thread_mm == 77.0 and p2.mounting.filter_thread_mm == 72.0
    assert p1.schema_version == p2.schema_version == 1


def test_bundled_profiles_do_not_recommend_missing_mounts():
    for path in PROFILE_PATHS:
        profile = load_profile(path)
        assert profile.mounting.recommended_mount is MountType.FILTER_DIAMETER_SLIP_FIT
        assert profile.mount_diameter_mm(profile.mounting.recommended_mount) > 0


def test_strict_profile_validation_unknown_field():
    d = json.loads(P.read_text())
    d["extra"] = 1
    with pytest.raises(ProfileValidationError, match="unknown fields"):
        validate_profile_data(d)


def test_search_local_profiles():
    assert [p.slug for p in search_profiles("Fuji")] == [
        "fujifilm-xf100-400",
        "fujifilm-xf16-80",
    ]


def test_geometry_invariants_and_slot_counts_for_bundled_profiles():
    for path in PROFILE_PATHS:
        profile = load_profile(path)
        b = calculate_mask(profile, opts(profile, MaskType.BAHTINOV))
        t = calculate_mask(profile, opts(profile, MaskType.TRIBAHTINOV))
        assert b.clear_aperture_mm == pytest.approx(
            b.ring.inner_diameter_mm - 2 * profile.defaults.pattern_border_mm
        )
        assert len(b.slots) > 15
        assert len(t.slots) > 20
        assert b.slot_width_mm > 0
        assert b.ring.outer_diameter_mm > b.ring.inner_diameter_mm
        assert b.ring.wall_thickness_mm >= 3
        assert t.slots != b.slots


def test_bahtinov_and_tribahtinov_physical_regions():
    b = calculate_mask(prof(), opts(mt=MaskType.BAHTINOV))
    t = calculate_mask(prof(), opts(mt=MaskType.TRIBAHTINOV))
    assert {(s.sector_start_deg, s.sector_end_deg) for s in b.slots} == {
        (-60, 60),
        (60, 180),
        (180, 300),
    }
    assert len({(s.sector_start_deg, s.sector_end_deg) for s in t.slots}) == 6


def test_deterministic_geometry_and_scad():
    g1 = calculate_mask(prof(), opts())
    g2 = calculate_mask(prof(), opts())
    assert g1 == g2
    renderer = OpenScadRenderer()
    assert renderer.render_scad(g1) == renderer.render_scad(g2)


def test_missing_hood_barrel_errors():
    with pytest.raises(ValueError):
        calculate_mask(prof(), opts(mount=MountType.HOOD_OUTER))
    with pytest.raises(ValueError):
        calculate_mask(prof(), opts(mount=MountType.BARREL_OUTER))


def test_full_mask_scad_preserves_front_face_and_clips_slots():
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts()))
    assert "Do not subtract a circular clear-aperture hole" in scad
    assert "cylinder(h=mask_thickness_mm" in scad
    assert (
        "aperture_clip();" in scad
    )  # clear aperture is used only inside slot intersections
    assert "intersection()" in scad
    assert "aperture_clip();" in scad
    assert "sector_clip(start_deg, end_deg);" in scad
    assert "clipped_slot(" in scad


def test_mounting_cavity_ends_at_z_zero_and_does_not_cross_face():
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts()))
    assert "translate([0, 0, -8.0000]) difference()" in scad
    assert "cylinder(h=8.0000 + epsilon, d=77.7000)" in scad
    assert (
        "mask_thickness_mm + 2 * epsilon" in scad
    )  # slots, not mounting cavity, cross the face


def test_test_ring_generation_has_no_face_slots_modules_or_label_and_is_short():
    g = calculate_mask(prof(), opts(test=True))
    scad = OpenScadRenderer().render_scad(g)
    assert g.test_ring
    assert g.ring.depth_mm <= 4.0
    assert "mask_thickness_mm" not in scad
    assert "slot_rectangle" not in scad
    assert "clipped_slot" not in scad
    assert "text(" not in scad
    assert "test_ring_depth_mm=4.000" in scad


def test_scad_label_escaping_and_peripheral_placement():
    profile = prof()
    g = calculate_mask(profile, opts())
    scad = OpenScadRenderer().render_scad(g)
    assert g.label is not None
    assert abs(g.label.position.y) > g.clear_aperture_mm / 2
    assert json.dumps(profile.label) in scad


def test_openscad_command_construction_and_extension(tmp_path):
    r = request(tmp_path, (OutputFormat.STL,))
    expected_base = tmp_path / "fujifilm-xf100-400-bahtinov-filter-thread"
    assert openscad_command_for(r, OutputFormat.STL) == [
        "openscad",
        "-o",
        str(expected_base.with_suffix(".stl")),
        str(expected_base.with_suffix(".scad")),
    ]
    assert output_path(Path("x"), OutputFormat.THREEMF).name == "x.3mf"


def test_universal_screws_error():
    with pytest.raises(NotImplementedError):
        calculate_mask(prof(), opts(mount=MountType.UNIVERSAL_SCREWS))


def test_unsupported_3mf_export(monkeypatch):
    monkeypatch.setattr(
        "selflensbahtinov.openscad.version_text", lambda exe: "OpenSCAD version 2019.05"
    )
    assert supports_format("openscad", OutputFormat.THREEMF) is False


def test_openscad_errors_are_wrapped(monkeypatch, tmp_path):
    def fail(*args, **kwargs):
        raise FileNotFoundError("missing")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(OpenScadError, match="executable not found"):
        supports_format("missing-openscad", OutputFormat.STL)

    with pytest.raises(OpenScadError, match="executable not found"):
        generate(
            GenerationRequest(
                prof(),
                MaskType.BAHTINOV,
                MountType.FILTER_DIAMETER_SLIP_FIT,
                (OutputFormat.STL,),
                400,
                5.6,
                0.35,
                3.0,
                True,
                tmp_path,
                "missing-openscad",
            )
        )


@pytest.mark.skipif(
    shutil.which("openscad") is None, reason="OpenSCAD is not installed"
)
def test_openscad_stl_export_integration(tmp_path):
    out = generate(request(tmp_path, (OutputFormat.STL,)))
    assert out[0].suffix == ".stl"
    assert out[0].stat().st_size > 0
