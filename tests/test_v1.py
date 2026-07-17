from __future__ import annotations

import json
import math
import struct
import zipfile
from dataclasses import replace
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

from selflensbahtinov.algorithms import AlgorithmOptions, calculate_mask
from selflensbahtinov.generator import generate, geometry_for, openscad_command_for
from selflensbahtinov.models import GenerationRequest, GratingRegion, MaskType, MountType, OutputFormat
from selflensbahtinov.openscad import (
    OpenScadError,
    UnsupportedFormatError,
    output_path,
    supports_format,
)
from selflensbahtinov.renderer import OpenScadRenderer
from selflensbahtinov.validation import (
    ProfileValidationError,
    load_profile,
    search_profiles,
    validate_profile_data,
    migrate_profile_data,
)

PROFILE_PATHS = [
    Path("profiles/fujifilm-xf100-400.json"),
    Path("profiles/fujifilm-xf16-80.json"),
]
P = PROFILE_PATHS[0]


def prof(path: Path = P):
    p = load_profile(path)
    return replace(
        p,
        mounting=replace(
            p.mounting,
            lens_barrel_outer_mm=82.0,
            lens_barrel_outer_status="measured",
            hood_outer_mm=96.0,
            hood_outer_status="measured",
            hood_inner_mm=88.0,
            hood_inner_status="measured",
        ),
        defaults=replace(p.defaults, mount_type=MountType.HOOD_OUTER_SLIP_FIT),
    )


def opts(
    profile=None,
    mt=MaskType.BAHTINOV,
    mount=MountType.LENS_BARREL_OUTER_SLIP_FIT,
    test=False,
):
    p = profile or prof()
    return AlgorithmOptions(
        mask_type=mt,
        mount_type=mount,
        focal_length_mm=p.recommended_focus.focal_length_mm,
        aperture_f_number=p.recommended_focus.aperture_f_number,
        clearance_mm=p.defaults.fit_clearance_mm,
        pattern_border_mm=p.defaults.pattern_border_mm,
        label=True,
        test_ring=test,
    )


def request(tmp_path: Path, fmt: tuple[OutputFormat, ...] = (OutputFormat.SCAD,)):
    p = prof()
    return GenerationRequest(
        profile=p,
        mask_type=MaskType.BAHTINOV,
        mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
        formats=fmt,
        focal_length_mm=p.recommended_focus.focal_length_mm,
        aperture_f_number=p.recommended_focus.aperture_f_number,
        clearance_mm=p.defaults.fit_clearance_mm,
        pattern_border_mm=p.defaults.pattern_border_mm,
        label=True,
        slot_width_mm=None,
        slot_spacing_mm=None,
        slot_density=1.0,
        output_dir=tmp_path,
        openscad="openscad",
    )


def test_loading_both_profiles():
    p1 = load_profile(PROFILE_PATHS[0])
    p2 = load_profile(PROFILE_PATHS[1])
    assert p1.mounting.filter_thread_nominal_mm == 77.0 and p2.mounting.filter_thread_nominal_mm == 72.0
    assert p1.schema_version == p2.schema_version == 2


def legacy_v1_profile_data():
    d = json.loads(P.read_text())
    d["schema_version"] = 1
    d["mounting"] = {
        "filter_thread_mm": d["mounting"]["filter_thread_nominal_mm"],
        "hood_outer_diameter_mm": None,
        "hood_inner_diameter_mm": None,
        "barrel_outer_diameter_mm": None,
        "recommended_mount": "filter_thread",
    }
    d["defaults"]["mount_type"] = "filter_thread"
    return d


def test_loading_valid_v1_profile_migrates_to_v2_without_nominal_reinterpretation(tmp_path):
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps(legacy_v1_profile_data()), encoding="utf-8")

    with pytest.warns(DeprecationWarning, match="schema version 1"):
        profile = load_profile(path)

    assert profile.schema_version == 2
    assert profile.mounting.filter_thread_nominal_mm == 77.0
    assert profile.mounting.lens_barrel_outer_mm is None
    assert profile.mounting.lens_barrel_outer_status == "unknown"
    assert profile.mounting.recommended_mount is None
    assert profile.defaults.mount_type is None


def test_v1_migration_preserves_non_null_old_dimensions_as_estimated_not_default():
    legacy = legacy_v1_profile_data()
    legacy["mounting"]["hood_outer_diameter_mm"] = 96.0
    with pytest.warns(DeprecationWarning):
        migrated = migrate_profile_data(legacy)

    assert migrated["schema_version"] == 2
    assert migrated["mounting"]["hood_outer_mm"] == 96.0
    assert migrated["mounting"]["hood_outer_status"] == "estimated"
    assert migrated["mounting"]["recommended_mount"] is None
    assert migrated["defaults"]["mount_type"] is None


def test_loading_native_v2_profiles_does_not_warn():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        profile = load_profile(P)

    assert profile.schema_version == 2
    assert caught == []


def test_rejects_unsupported_future_schema_version():
    d = json.loads(P.read_text())
    d["schema_version"] = 999
    with pytest.raises(ProfileValidationError, match="unsupported schema_version"):
        validate_profile_data(d)


def test_bundled_profiles_keep_unknown_mount_dimensions_null():
    for path in PROFILE_PATHS:
        profile = load_profile(path)
        assert profile.mounting.recommended_mount is None
        assert profile.mounting.lens_barrel_outer_mm is None
        assert profile.mounting.hood_outer_mm is None
        assert profile.mounting.hood_inner_mm is None
        assert profile.defaults.mount_type is None


def test_strict_profile_validation_unknown_field():
    d = json.loads(P.read_text())
    d["extra"] = 1
    with pytest.raises(ProfileValidationError, match="unknown fields"):
        validate_profile_data(d)




def measured_profile_data(mount="hood_outer_slip_fit", status="measured", default_mount=None):
    d = json.loads(P.read_text())
    d["mounting"]["hood_outer_mm"] = 96.0
    d["mounting"]["hood_outer_status"] = status
    d["mounting"]["recommended_mount"] = mount
    d["defaults"]["mount_type"] = default_mount
    return d


def test_null_recommended_mount_is_valid():
    d = json.loads(P.read_text())
    d["mounting"]["recommended_mount"] = None
    validate_profile_data(d)


def test_recommended_mount_with_null_dimension_fails_validation():
    d = json.loads(P.read_text())
    d["mounting"]["recommended_mount"] = "hood_outer_slip_fit"
    with pytest.raises(ProfileValidationError, match="recommended_mount hood_outer_slip_fit requires mounting.hood_outer_mm"):
        validate_profile_data(d)


@pytest.mark.parametrize("status", ["unknown", "estimated"])
def test_recommended_mount_requires_measured_or_verified_status(status):
    d = measured_profile_data(status=status)
    if status == "unknown":
        with pytest.raises(ProfileValidationError, match="hood_outer_mm is set.*status must be estimated"):
            validate_profile_data(d)
    else:
        with pytest.raises(ProfileValidationError, match="recommended_mount hood_outer_slip_fit requires mounting.hood_outer_status"):
            validate_profile_data(d)


@pytest.mark.parametrize("status", ["measured", "verified"])
def test_recommended_mount_with_measured_or_verified_status_succeeds(status):
    validate_profile_data(measured_profile_data(status=status))


def test_default_mount_requires_measured_dimension_and_status():
    d = json.loads(P.read_text())
    d["defaults"]["mount_type"] = "lens_barrel_outer_slip_fit"
    with pytest.raises(ProfileValidationError, match="defaults.mount_type lens_barrel_outer_slip_fit requires mounting.lens_barrel_outer_mm"):
        validate_profile_data(d)


def test_generation_without_mount_or_measured_default_fails_clearly(caplog):
    import selflensbahtinov.cli as cli

    rc = cli.main(["generate", "fujifilm-xf100-400", "--dry-run"])

    assert rc == 2
    assert "No measured mounting method is available" in caplog.text
    assert "Measure lens_barrel_outer_mm, hood_outer_mm, or hood_inner_mm" in caplog.text


def test_generation_with_explicit_measured_mount_succeeds(capsys, monkeypatch):
    import selflensbahtinov.cli as cli

    monkeypatch.setattr(cli, "load_profile", lambda path: prof())
    rc = cli.main(["generate", "fujifilm-xf100-400", "--mount", "hood-outer-slip-fit", "--dry-run"])

    assert rc == 0
    assert "DRY-RUN would create:" in capsys.readouterr().out


def test_show_displays_none_for_missing_recommendation_and_default(capsys):
    import selflensbahtinov.cli as cli

    assert cli.main(["show", "fujifilm-xf100-400"]) == 0
    out = capsys.readouterr().out
    assert "recommended mount: none" in out
    assert "default mount: none" in out


def test_deprecated_filter_thread_alias_does_not_bypass_missing_measurement(capsys, caplog):
    import selflensbahtinov.cli as cli

    rc = cli.main(["generate", "fujifilm-xf100-400", "--mount", "filter-thread", "--dry-run"])

    err = capsys.readouterr().err
    assert rc == 2
    assert "deprecated" in err
    assert "requires a physically measured diameter" in caplog.text


def test_github_action_mount_has_no_misleading_default():
    workflow = Path(".github/workflows/generate-mask.yml").read_text(
        encoding="utf-8"
    )

    mount_block = (
        workflow
        .split("      mount:", 1)[1]
        .split("      mount_diameter:", 1)[0]
    )

    assert "default:" not in mount_block
    assert "Smooth slip-fit mounting surface" in mount_block

    option_lines = [
        line.strip()[2:]
        for line in mount_block.splitlines()
        if line.strip().startswith("- ")
    ]

    assert option_lines == [
        "lens-barrel-outer-slip-fit",
        "hood-outer-slip-fit",
        "hood-inner-slip-fit",
    ]

    assert "filter-thread" not in mount_block
    assert "- hood-outer\n" not in mount_block
    assert "- barrel-outer\n" not in mount_block
    assert '--mount "${{ inputs.mount }}"' in workflow



def test_github_action_exposes_outer_face_fillet_without_physical_default():
    workflow = Path(".github/workflows/generate-mask.yml").read_text(encoding="utf-8")
    input_block = (
        workflow
        .split("      outer_face_fillet_radius:", 1)[1]
        .split("      region_gap:", 1)[0]
    )
    assert "Optional fillet radius on the outside edge of the slotted front face" in input_block
    assert "required: false" in input_block
    assert 'default: ""' in input_block
    assert "type: string" in input_block


def test_github_action_passes_outer_face_fillet_and_records_metadata():
    workflow = Path(".github/workflows/generate-mask.yml").read_text(encoding="utf-8")
    assert 'if [[ -n "${{ inputs.outer_face_fillet_radius }}" ]]; then' in workflow
    assert "--outer-face-fillet-radius" in workflow
    assert '"${{ inputs.outer_face_fillet_radius }}"' in workflow
    assert "Outer front-face fillet radius: ${{ inputs.outer_face_fillet_radius || 'profile default' }}" in workflow
    assert "outer_face_fillet_radius_mm=" in workflow


def test_github_action_keeps_zero_outer_face_fillet_as_explicit_value():
    workflow = Path(".github/workflows/generate-mask.yml").read_text(encoding="utf-8")
    assert 'if [[ -n "${{ inputs.outer_face_fillet_radius }}" ]]; then' in workflow
    conditional = workflow.split('if [[ -n "${{ inputs.outer_face_fillet_radius }}" ]]; then', 1)[1].split("          fi", 1)[0]
    assert "!= 0" not in conditional
    assert "profile default" not in conditional

def test_search_local_profiles():
    assert [p.slug for p in search_profiles("Fuji")] == [
        "fujifilm-xf100-400",
        "fujifilm-xf16-80",
    ]


def test_geometry_invariants_and_slot_counts_for_bundled_profiles():
    for path in PROFILE_PATHS:
        profile = prof(path)
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
    assert {s.region for s in b.slots} == {
        GratingRegion.LEFT_REFERENCE,
        GratingRegion.RIGHT_UPPER,
        GratingRegion.RIGHT_LOWER,
    }
    assert b.region_gap_mm == pytest.approx(2.0)
    assert len({s.region for s in t.slots}) == 6
    assert all(s.region.value.startswith("tribahtinov-") for s in t.slots)
    assert t.region_gap_mm == pytest.approx(0.0)


def test_bahtinov_region_topology_snapshot_and_symmetry():
    g = calculate_mask(prof(), opts(mt=MaskType.BAHTINOV))
    by_region = {region: [s for s in g.slots if s.region is region] for region in {s.region for s in g.slots}}
    assert {r.value: sorted({s.angle_deg for s in slots}) for r, slots in by_region.items()} == {
        "left-reference": [0],
        "right-upper": [60.0],
        "right-lower": [-60.0],
    }
    assert len(by_region[GratingRegion.LEFT_REFERENCE]) > 0
    assert len(by_region[GratingRegion.RIGHT_UPPER]) == len(by_region[GratingRegion.RIGHT_LOWER])
    upper = sorted((s.center.x, s.center.y, s.angle_deg) for s in by_region[GratingRegion.RIGHT_UPPER])
    lower = sorted((s.center.x, -s.center.y, -s.angle_deg) for s in by_region[GratingRegion.RIGHT_LOWER])
    assert upper == lower


def test_region_gap_validation_and_separator_clip_are_explicit():
    with pytest.raises(ValueError, match="region_gap_mm must be greater than or equal to zero"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "region_gap_mm": -0.1}))
    with pytest.raises(ValueError, match="printable minimum"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "region_gap_mm": 0.5}))
    with pytest.raises(ValueError, match="leaves no usable area"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "region_gap_mm": 200.0}))
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts()))
    assert 'region_gap_mm = 2.0000;' in scad
    assert 'region == "left-reference" ? [[-r, -r], [-g, -r], [-g, r], [-r, r]]' in scad
    assert 'region == "right-upper" ? [[g, g], [r, g], [r, r], [g, r]]' in scad
    assert 'region == "right-lower" ? [[g, -g], [r, -g], [r, -r], [g, -r]]' in scad
    assert "sector_clip(start_deg, end_deg)" not in scad
    assert "-60.000, 60.000" not in scad


def test_region_gap_validation_applies_only_to_normal_bahtinov():
    invalid = {**opts().__dict__, "region_gap_mm": 200.0}
    with pytest.raises(ValueError, match="leaves no usable area"):
        calculate_mask(prof(), AlgorithmOptions(**invalid))
    tri = calculate_mask(
        prof(),
        AlgorithmOptions(**{**invalid, "mask_type": MaskType.TRIBAHTINOV}),
    )
    assert tri.region_gap_mm == pytest.approx(0.0)
    assert {s.region for s in tri.slots} == {
        GratingRegion.TRIBAHTINOV_0,
        GratingRegion.TRIBAHTINOV_1,
        GratingRegion.TRIBAHTINOV_2,
        GratingRegion.TRIBAHTINOV_3,
        GratingRegion.TRIBAHTINOV_4,
        GratingRegion.TRIBAHTINOV_5,
    }


def test_tribahtinov_scad_ignores_region_gap_and_remains_deterministic():
    base = {**opts(mt=MaskType.TRIBAHTINOV).__dict__}
    scad_a = OpenScadRenderer().render_scad(
        calculate_mask(prof(), AlgorithmOptions(**{**base, "region_gap_mm": -1.0}))
    )
    scad_b = OpenScadRenderer().render_scad(
        calculate_mask(prof(), AlgorithmOptions(**{**base, "region_gap_mm": 200.0}))
    )
    assert scad_a == scad_b
    assert "region_gap_mm = 0.0000;" in scad_a
    assert "tribahtinov-0" in scad_a


def test_configurable_bahtinov_grating_dimensions():
    g = calculate_mask(
        prof(),
        AlgorithmOptions(
            mask_type=MaskType.BAHTINOV,
            mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
            focal_length_mm=400,
            aperture_f_number=5.6,
            clearance_mm=0.35,
            pattern_border_mm=3.0,
            label=True,
            test_ring=False,
            slot_width_mm=1.1,
            slot_spacing_mm=5.0,
            slot_density=2.0,
        ),
    )
    assert g.slot_width_mm == pytest.approx(1.1)
    assert g.slot_spacing_mm == pytest.approx(2.5)
    assert len(g.slots) > 65


def test_slot_width_must_be_smaller_than_effective_pitch():
    with pytest.raises(ValueError, match="slot_width_mm must be smaller"):
        calculate_mask(
            prof(),
            AlgorithmOptions(
                mask_type=MaskType.BAHTINOV,
                mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
                focal_length_mm=400,
                aperture_f_number=5.6,
                clearance_mm=0.35,
                pattern_border_mm=3.0,
                label=True,
                test_ring=False,
                slot_width_mm=2.0,
                slot_spacing_mm=2.0,
                slot_density=1.0,
            ),
        )


def test_deterministic_geometry_and_scad():
    g1 = calculate_mask(prof(), opts())
    g2 = calculate_mask(prof(), opts())
    assert g1 == g2
    renderer = OpenScadRenderer()
    assert renderer.render_scad(g1) == renderer.render_scad(g2)


def test_null_mount_dimension_fails_clearly():
    profile = load_profile(P)
    with pytest.raises(ValueError, match="physically measured diameter"):
        calculate_mask(profile, opts(profile, mount=MountType.HOOD_OUTER_SLIP_FIT))
    with pytest.raises(ValueError, match="nominal filter-thread size is metadata only"):
        calculate_mask(profile, opts(profile, mount=MountType.LENS_BARREL_OUTER_SLIP_FIT))


def test_full_mask_scad_preserves_front_face_and_clips_slots():
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts()))
    assert "Do not subtract a circular clear-aperture hole" in scad
    assert "cylinder(h=mask_thickness_mm" in scad
    assert (
        "aperture_clip();" in scad
    )  # clear aperture is used only inside slot intersections
    assert "intersection()" in scad
    assert "aperture_clip();" in scad
    assert "region_clip(region);" in scad
    assert "clipped_slot(" in scad


def test_mounting_cavity_ends_at_z_zero_and_does_not_cross_face():
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts()))
    assert "mounting_ring();" in scad
    assert "[-8.0000]" not in scad
    assert "inner_fit_diameter_mm=82.7000" in scad
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
    expected_base = tmp_path / "fujifilm-xf100-400-bahtinov-lens-barrel-outer-slip-fit"
    assert openscad_command_for(r, OutputFormat.STL) == [
        "openscad",
        "-o",
        str(expected_base.with_suffix(".stl")),
        str(expected_base.with_suffix(".scad")),
    ]
    assert output_path(Path("x"), OutputFormat.THREEMF).name == "x.3mf"


def test_hood_inner_slip_fit_uses_measured_inner_opening_and_reduces_outer_diameter():
    g = calculate_mask(prof(), opts(mount=MountType.HOOD_INNER_SLIP_FIT))
    assert g.ring.mount_diameter_mm == 88.0
    assert g.ring.outer_diameter_mm == pytest.approx(88.0 - 2 * 0.35)
    assert g.ring.inner_diameter_mm == pytest.approx(g.ring.outer_diameter_mm - 2 * 3.0)


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
                profile=prof(),
                mask_type=MaskType.BAHTINOV,
                mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
                formats=(OutputFormat.STL,),
                focal_length_mm=400,
                aperture_f_number=5.6,
                clearance_mm=0.35,
                pattern_border_mm=3.0,
                label=True,
                slot_width_mm=None,
                slot_spacing_mm=None,
                slot_density=1.0,
                output_dir=tmp_path,
                openscad="missing-openscad",
            )
        )

def test_manufacturing_constraints_reject_tiny_bars_and_non_finite_values():
    with pytest.raises(ValueError, match="opaque bar width"):
        calculate_mask(
            prof(),
            AlgorithmOptions(
                mask_type=MaskType.BAHTINOV,
                mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
                focal_length_mm=400,
                aperture_f_number=5.6,
                clearance_mm=0.35,
                pattern_border_mm=3.0,
                label=True,
                slot_width_mm=1.3,
                slot_spacing_mm=2.0,
            ),
        )
    with pytest.raises(ValueError, match="finite"):
        calculate_mask(
            prof(),
            AlgorithmOptions(
                mask_type=MaskType.BAHTINOV,
                mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
                focal_length_mm=float("nan"),
                aperture_f_number=5.6,
                clearance_mm=0.35,
                pattern_border_mm=3.0,
                label=True,
            ),
        )


def test_test_ring_does_not_validate_irrelevant_slot_parameters():
    g = calculate_mask(
        prof(),
        AlgorithmOptions(
            mask_type=MaskType.BAHTINOV,
            mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
            focal_length_mm=400,
            aperture_f_number=5.6,
            clearance_mm=0.35,
            pattern_border_mm=3.0,
            label=True,
            test_ring=True,
            slot_width_mm=float("nan"),
            slot_spacing_mm=0.0,
            slot_density=-1.0,
        ),
    )
    assert g.test_ring
    assert g.slots == ()


def test_slot_pitch_is_perpendicular_to_each_grating_angle_and_has_no_duplicates():
    g = calculate_mask(prof(), opts())
    assert len(set(g.slots)) == len(g.slots)
    for angle in {slot.angle_deg for slot in g.slots}:
        centers = [slot.center for slot in g.slots if slot.angle_deg == angle]
        normal = math.radians(angle + 90)
        offsets = sorted(round(c.x * math.cos(normal) + c.y * math.sin(normal), 4) for c in centers)
        diffs = [b - a for a, b in zip(offsets, offsets[1:])]
        assert diffs
        assert all(d == pytest.approx(g.slot_spacing_mm, abs=0.0002) for d in diffs)


def test_orientation_convention_for_diffraction_spike_families():
    # Orientation convention only: a slot family at angle alpha produces a
    # diffraction spike along alpha + 90 degrees. This is not a PSF simulation.
    spike_angles = {0: 90, 60: 150, -60: 30}
    assert spike_angles[0] == 90
    assert spike_angles[60] - spike_angles[0] == 60
    assert spike_angles[0] - spike_angles[-60] == 60


@pytest.mark.parametrize("flag,bad", [
    ("--focal-length", "0"),
    ("--focal-length", "-1"),
    ("--focal-length", "nan"),
    ("--focal-length", "inf"),
    ("--aperture", "0"),
    ("--aperture", "-1"),
    ("--aperture", "nan"),
    ("--aperture", "inf"),
])
def test_cli_rejects_invalid_optical_values_without_default_fallback(flag, bad):
    import selflensbahtinov.cli as cli

    assert cli.main(["generate", "fujifilm-xf100-400", flag, bad, "--dry-run"]) == 2


def test_cli_omitted_optical_values_use_profile_defaults(capsys, monkeypatch):
    import selflensbahtinov.cli as cli
    monkeypatch.setattr(cli, "load_profile", lambda path: prof())

    assert cli.main(["generate", "fujifilm-xf100-400", "--mount", "lens-barrel-outer-slip-fit", "--dry-run", "--show-grating-info"]) == 0
    out = capsys.readouterr().out
    assert "source=aperture_minimum_clamp" in out


@pytest.mark.parametrize("border", [-1, float("nan"), float("inf"), 1000])
def test_pattern_border_validation_for_full_masks_and_test_rings(border):
    with pytest.raises(ValueError, match="pattern_border_mm|clear aperture"):
        calculate_mask(
            prof(),
            AlgorithmOptions(
                mask_type=MaskType.BAHTINOV,
                mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
                focal_length_mm=400,
                aperture_f_number=5.6,
                clearance_mm=0.35,
                pattern_border_mm=border,
                label=True,
            ),
        )
    with pytest.raises(ValueError, match="pattern_border_mm|clear aperture"):
        calculate_mask(
            prof(),
            AlgorithmOptions(
                mask_type=MaskType.BAHTINOV,
                mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
                focal_length_mm=400,
                aperture_f_number=5.6,
                clearance_mm=0.35,
                pattern_border_mm=border,
                label=True,
                test_ring=True,
            ),
        )


def test_generate_bundle_3mf_export_failure_does_not_trigger_fallback(monkeypatch, tmp_path):
    import selflensbahtinov.generator as generator
    import selflensbahtinov.cli as cli

    monkeypatch.setattr(generator, "supports_format", lambda openscad, fmt: True)
    export_calls = []

    def fail_3mf(openscad, scad_path, out, dry_run=False):
        export_calls.append(out.suffix)
        if out.suffix == ".3mf":
            raise OpenScadError("actual .3mf export failed")
        out.write_text("exported", encoding="utf-8")

    monkeypatch.setattr(generator, "export", fail_3mf)

    monkeypatch.setattr(cli, "load_profile", lambda path: prof())

    rc = cli.main(
        [
            "generate-bundle",
            "fujifilm-xf100-400",
            "--output-dir",
            str(tmp_path),
            "--openscad",
            "fake-openscad",
        ]
    )
    assert rc == 2
    assert ".3mf" in export_calls
    assert "fujifilm-xf100-400-test-ring-hood-outer-slip-fit.scad" not in {p.name for p in tmp_path.iterdir()}


def test_grating_metadata_for_bundled_profiles_and_custom_pitch(capsys, monkeypatch):
    expected_sources = {
        "fujifilm-xf100-400": "aperture_minimum_clamp",
        "fujifilm-xf16-80": "aperture_minimum_clamp",
    }
    for path in PROFILE_PATHS:
        profile = prof(path)
        g = calculate_mask(profile, opts(profile))
        assert g.grating is not None
        assert g.grating.base_pitch_mm == pytest.approx(g.grating.effective_pitch_mm)
        assert g.grating.effective_pitch_mm == pytest.approx(g.slot_spacing_mm)
        assert g.grating.open_slot_width_mm == pytest.approx(g.slot_width_mm)
        assert g.grating.opaque_bar_width_mm == pytest.approx(
            g.grating.effective_pitch_mm - g.grating.open_slot_width_mm
        )
        assert g.grating.open_fraction == pytest.approx(
            g.grating.open_slot_width_mm / g.grating.effective_pitch_mm, abs=0.0001
        )
        assert g.grating.pitch_selection_source == expected_sources[profile.slug]

    custom = calculate_mask(
        prof(),
        AlgorithmOptions(
            mask_type=MaskType.BAHTINOV,
            mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
            focal_length_mm=400,
            aperture_f_number=5.6,
            clearance_mm=0.35,
            pattern_border_mm=3.0,
            label=True,
            slot_width_mm=1.2,
            slot_spacing_mm=5.0,
            slot_density=1.25,
        ),
    )
    assert custom.grating is not None
    assert custom.grating.base_pitch_mm == pytest.approx(5.0)
    assert custom.grating.effective_pitch_mm == pytest.approx(4.0)
    assert custom.grating.open_slot_width_mm == pytest.approx(1.2)
    assert custom.grating.opaque_bar_width_mm == pytest.approx(2.8)
    assert custom.grating.pitch_selection_source == "explicit"

    import selflensbahtinov.cli as cli
    monkeypatch.setattr(cli, "load_profile", lambda path: prof())
    rc = cli.main(["generate", "fujifilm-xf100-400", "--mount", "lens-barrel-outer-slip-fit", "--dry-run", "--show-grating-info"])
    assert rc == 0
    assert "grating:" in capsys.readouterr().out


def test_test_ring_validates_mechanical_clearance_but_ignores_slot_controls():
    with pytest.raises(ValueError, match="clearance_mm must be finite"):
        calculate_mask(
            prof(),
            AlgorithmOptions(
                mask_type=MaskType.BAHTINOV,
                mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
                focal_length_mm=400,
                aperture_f_number=5.6,
                clearance_mm=float("nan"),
                pattern_border_mm=3.0,
                label=True,
                test_ring=True,
                slot_width_mm=float("nan"),
                slot_spacing_mm=0.0,
                slot_density=-1.0,
            ),
        )

    g = calculate_mask(
        prof(),
        AlgorithmOptions(
            mask_type=MaskType.BAHTINOV,
            mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
            focal_length_mm=400,
            aperture_f_number=5.6,
            clearance_mm=0.35,
            pattern_border_mm=3.0,
            label=True,
            test_ring=True,
            slot_width_mm=float("nan"),
            slot_spacing_mm=0.0,
            slot_density=-1.0,
        ),
    )
    assert g.grating is None
    assert g.slots == ()


@pytest.mark.parametrize("field,bad", [
    ("focal_length_mm", 0),
    ("focal_length_mm", -1),
    ("focal_length_mm", float("nan")),
    ("focal_length_mm", float("inf")),
    ("aperture_f_number", 0),
    ("aperture_f_number", -1),
    ("aperture_f_number", float("nan")),
    ("aperture_f_number", float("inf")),
])
def test_optical_inputs_must_be_positive_finite(field, bad):
    kwargs = dict(
        mask_type=MaskType.BAHTINOV,
        mount_type=MountType.LENS_BARREL_OUTER_SLIP_FIT,
        focal_length_mm=400,
        aperture_f_number=5.6,
        clearance_mm=0.35,
        pattern_border_mm=3.0,
        label=True,
    )
    kwargs[field] = bad
    with pytest.raises(ValueError, match=field):
        calculate_mask(prof(), AlgorithmOptions(**kwargs))


def test_generate_bundle_real_3mf_fallback_path(monkeypatch, tmp_path):
    import selflensbahtinov.generator as generator
    import selflensbahtinov.cli as cli

    support_calls = []
    export_calls = []

    def fake_supports_format(openscad, fmt):
        support_calls.append((openscad, fmt))
        return fmt is not OutputFormat.THREEMF

    def fake_export(openscad, scad_path, out, dry_run=False):
        export_calls.append((openscad, scad_path, out, dry_run))
        out.write_text("exported", encoding="utf-8")

    monkeypatch.setattr(generator, "supports_format", fake_supports_format)
    monkeypatch.setattr(generator, "export", fake_export)

    monkeypatch.setattr(cli, "load_profile", lambda path: prof())

    rc = cli.main(
        [
            "generate-bundle",
            "fujifilm-xf100-400",
            "--slot-width",
            "1.2",
            "--slot-spacing",
            "5.0",
            "--slot-density",
            "1.5",
            "--region-gap",
            "3.5",
            "--output-dir",
            str(tmp_path),
            "--openscad",
            "fake-openscad",
        ]
    )

    assert rc == 0
    assert ("fake-openscad", OutputFormat.THREEMF) in support_calls
    assert all(call[0] == "fake-openscad" for call in export_calls)
    assert all(call[3] is False for call in export_calls)
    outputs = sorted(path.name for path in tmp_path.iterdir())
    assert "fujifilm-xf100-400-bahtinov-hood-outer-slip-fit.scad" in outputs
    assert "fujifilm-xf100-400-bahtinov-hood-outer-slip-fit.stl" in outputs
    assert "fujifilm-xf100-400-test-ring-hood-outer-slip-fit.scad" in outputs
    assert "fujifilm-xf100-400-test-ring-hood-outer-slip-fit.stl" in outputs



def _assert_bundle_ring_depth_scad(tmp_path: Path):
    full = (tmp_path / "fujifilm-xf100-400-bahtinov-lens-barrel-outer-slip-fit.scad").read_text(encoding="utf-8")
    test_ring = (tmp_path / "fujifilm-xf100-400-test-ring-lens-barrel-outer-slip-fit.scad").read_text(encoding="utf-8")

    assert "ring_depth_mm=70.0000" in full
    assert "straight_engagement_mm=69.0000" in full
    assert ", -70.0000]" in full

    assert "test_ring_depth_mm=4.000" in test_ring
    assert "ring_depth_mm=4.0000" in test_ring
    assert "straight_engagement_mm=3.0000" in test_ring
    assert ", -4.0000]" in test_ring


def test_generate_bundle_ring_depth_override_reaches_rendered_scad(monkeypatch, tmp_path):
    import selflensbahtinov.generator as generator
    import selflensbahtinov.cli as cli

    exported_scad = []

    monkeypatch.setattr(generator, "supports_format", lambda openscad, fmt: True)

    def fake_export(openscad, scad_path, out, dry_run=False):
        exported_scad.append(scad_path.read_text(encoding="utf-8"))
        out.write_text("exported", encoding="utf-8")

    monkeypatch.setattr(generator, "export", fake_export)
    monkeypatch.setattr(cli, "load_profile", lambda path: prof())

    rc = cli.main(
        [
            "generate-bundle",
            "fujifilm-xf100-400",
            "--mount",
            "lens-barrel-outer-slip-fit",
            "--ring-depth",
            "70",
            "--output-dir",
            str(tmp_path),
            "--openscad",
            "fake-openscad",
        ]
    )

    assert rc == 0
    _assert_bundle_ring_depth_scad(tmp_path)
    assert len(exported_scad) == 4
    assert "ring_depth_mm=70.0000" in exported_scad[0]
    assert "ring_depth_mm=70.0000" in exported_scad[1]
    assert "ring_depth_mm=4.0000" in exported_scad[2]
    assert "ring_depth_mm=4.0000" in exported_scad[3]


def test_generate_bundle_ring_depth_override_survives_3mf_fallback_scad(monkeypatch, tmp_path):
    import selflensbahtinov.generator as generator
    import selflensbahtinov.cli as cli

    support_calls = []

    def fake_supports_format(openscad, fmt):
        support_calls.append(fmt)
        return fmt is not OutputFormat.THREEMF

    def fake_export(openscad, scad_path, out, dry_run=False):
        out.write_text("exported", encoding="utf-8")

    monkeypatch.setattr(generator, "supports_format", fake_supports_format)
    monkeypatch.setattr(generator, "export", fake_export)
    monkeypatch.setattr(cli, "load_profile", lambda path: prof())

    rc = cli.main(
        [
            "generate-bundle",
            "fujifilm-xf100-400",
            "--mount",
            "lens-barrel-outer-slip-fit",
            "--ring-depth",
            "70",
            "--output-dir",
            str(tmp_path),
            "--openscad",
            "fake-openscad",
        ]
    )

    assert rc == 0
    assert OutputFormat.THREEMF in support_calls
    _assert_bundle_ring_depth_scad(tmp_path)

def test_generate_bundle_does_not_treat_stl_failures_as_3mf_fallback(monkeypatch, tmp_path):
    import selflensbahtinov.generator as generator
    import selflensbahtinov.cli as cli

    monkeypatch.setattr(generator, "supports_format", lambda openscad, fmt: True)

    def fail_stl(openscad, scad_path, out, dry_run=False):
        if out.suffix == ".stl":
            raise OpenScadError("stl export failed")

    monkeypatch.setattr(generator, "export", fail_stl)

    rc = cli.main(
        [
            "generate-bundle",
            "fujifilm-xf100-400",
            "--output-dir",
            str(tmp_path),
            "--openscad",
            "fake-openscad",
        ]
    )
    assert rc == 2


def test_generate_bundle_3mf_fallback_preserves_slot_controls(monkeypatch, tmp_path):
    import selflensbahtinov.cli as cli

    calls = []

    def fake_generate(req, *, test_ring=False):
        calls.append((req, test_ring))
        if OutputFormat.THREEMF in req.formats:
            raise UnsupportedFormatError("3mf unsupported")
        assert req.slot_width_mm == pytest.approx(1.2)
        assert req.slot_spacing_mm == pytest.approx(5.0)
        assert req.slot_density == pytest.approx(1.5)
        assert req.region_gap_mm == pytest.approx(3.5)
        assert req.output_dir == tmp_path
        assert req.openscad == "fake-openscad"
        assert req.dry_run is True
        suffix = "test-ring" if test_ring else "mask"
        return [tmp_path / f"{suffix}.scad", tmp_path / f"{suffix}.stl"]

    monkeypatch.setattr(cli, "generate", fake_generate)
    monkeypatch.setattr(cli, "load_profile", lambda path: prof())

    rc = cli.main(
        [
            "generate-bundle",
            "fujifilm-xf100-400",
            "--format",
            "scad",
            "--slot-width",
            "1.2",
            "--slot-spacing",
            "5.0",
            "--slot-density",
            "1.5",
            "--region-gap",
            "3.5",
            "--output-dir",
            str(tmp_path),
            "--openscad",
            "fake-openscad",
            "--dry-run",
        ]
    )

    assert rc == 0
    assert len(calls) == 3
    assert calls[0][0].formats == (OutputFormat.SCAD, OutputFormat.STL, OutputFormat.THREEMF)
    assert calls[1][0].formats == (OutputFormat.SCAD, OutputFormat.STL)
    assert calls[2][1] is True


@pytest.mark.skipif(
    shutil.which("openscad") is None, reason="OpenSCAD is not installed"
)
def test_openscad_stl_export_integration(tmp_path):
    out = generate(request(tmp_path, (OutputFormat.STL,)))
    assert out[0].suffix == ".stl"
    assert out[0].stat().st_size > 0


def test_deprecated_filter_thread_cli_alias_maps_to_lens_barrel_and_warns(capsys):
    import selflensbahtinov.cli as cli

    mount = cli._mount("filter-thread")

    captured = capsys.readouterr()
    assert mount is MountType.LENS_BARREL_OUTER_SLIP_FIT
    assert "deprecated" in captured.err
    assert "smooth slip fit" in captured.err
    assert "not a threaded or screw-in mount" in captured.err


@pytest.mark.parametrize(
    "mount,expected_diameter",
    [
        (MountType.LENS_BARREL_OUTER_SLIP_FIT, 82.0),
        (MountType.HOOD_OUTER_SLIP_FIT, 96.0),
        (MountType.HOOD_INNER_SLIP_FIT, 88.0),
    ],
)
def test_test_ring_generation_works_for_each_smooth_mount(mount, expected_diameter):
    g = calculate_mask(prof(), opts(mount=mount, test=True))
    scad = OpenScadRenderer().render_scad(g)

    assert g.test_ring is True
    assert g.ring.mount_diameter_mm == expected_diameter
    assert "test_ring_depth_mm=4.000" in scad


def test_scad_contains_no_thread_or_screw_geometry():
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts()))

    forbidden = ("thread", "screw", "helix", "linear_extrude(twist")
    assert all(term not in scad.lower() for term in forbidden)


def set_nested(data, dotted, value):
    target = data
    parts = dotted.split(".")
    for part in parts[:-1]:
        target = target[part]
    target[parts[-1]] = value


@pytest.mark.parametrize(
    "field",
    [
        "focal_length.min_mm",
        "focal_length.max_mm",
        "aperture.min_f_number",
        "aperture.max_f_number",
        "recommended_focus.focal_length_mm",
        "recommended_focus.aperture_f_number",
        "mounting.filter_thread_nominal_mm",
        "mounting.lens_barrel_outer_mm",
        "mounting.hood_outer_mm",
        "mounting.hood_inner_mm",
        "defaults.fit_clearance_mm",
        "defaults.mask_thickness_mm",
        "defaults.ring_depth_mm",
        "defaults.ring_wall_thickness_mm",
        "defaults.pattern_border_mm",
    ],
)
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_profile_numeric_fields_reject_non_finite_values(field, bad):
    d = json.loads(P.read_text())
    if field.endswith("_mm") and field.startswith("mounting.") and field != "mounting.filter_thread_nominal_mm":
        status_field = field.rsplit("_mm", 1)[0] + "_status"
        set_nested(d, status_field, "measured")
    set_nested(d, field, bad)

    with pytest.raises(ProfileValidationError, match="finite"):
        validate_profile_data(d)


def profile_with_mount_status(status):
    p = prof()
    return replace(
        p,
        mounting=replace(
            p.mounting,
            hood_outer_mm=96.0,
            hood_outer_status=status,
        ),
        defaults=replace(p.defaults, mount_type=MountType.HOOD_OUTER_SLIP_FIT),
    )


def test_estimated_mount_allows_test_ring_generation_only():
    profile = profile_with_mount_status("estimated")

    ring = calculate_mask(profile, opts(profile, mount=MountType.HOOD_OUTER_SLIP_FIT, test=True))
    assert ring.test_ring is True
    with pytest.raises(ValueError, match="estimated mounts may generate test rings only"):
        calculate_mask(profile, opts(profile, mount=MountType.HOOD_OUTER_SLIP_FIT, test=False))


def test_estimated_mount_rejects_generate_and_bundle_cli(monkeypatch, caplog, tmp_path):
    import selflensbahtinov.cli as cli

    monkeypatch.setattr(cli, "load_profile", lambda path: profile_with_mount_status("estimated"))
    assert cli.main(["generate", "fujifilm-xf100-400", "--mount", "hood-outer-slip-fit", "--dry-run"]) == 2
    assert "estimated mounts may generate test rings only" in caplog.text
    caplog.clear()
    assert cli.main([
        "generate-bundle",
        "fujifilm-xf100-400",
        "--mount",
        "hood-outer-slip-fit",
        "--output-dir",
        str(tmp_path),
        "--dry-run",
    ]) == 2
    assert "estimated mounts may generate test rings only" in caplog.text


@pytest.mark.parametrize("status", ["measured", "verified"])
def test_measured_and_verified_mounts_allow_full_generation(status):
    profile = profile_with_mount_status(status)
    mask = calculate_mask(profile, opts(profile, mount=MountType.HOOD_OUTER_SLIP_FIT))
    assert mask.test_ring is False
    assert mask.ring.mount_diameter_mm == pytest.approx(96.0)


def test_direct_generation_request_rejects_missing_mount(tmp_path):
    with pytest.raises(TypeError, match="GenerationRequest.mount_type must be a concrete MountType"):
        GenerationRequest(
            profile=prof(),
            mask_type=MaskType.BAHTINOV,
            mount_type=None,
            formats=(OutputFormat.SCAD,),
            focal_length_mm=400,
            aperture_f_number=5.6,
            clearance_mm=0.35,
            pattern_border_mm=3.0,
            label=True,
            slot_width_mm=None,
            slot_spacing_mm=None,
            slot_density=1.0,
            output_dir=tmp_path,
            openscad="openscad",
        )


def test_algorithm_options_rejects_missing_mount():
    with pytest.raises(TypeError, match="AlgorithmOptions.mount_type must be a concrete MountType"):
        AlgorithmOptions(
            mask_type=MaskType.BAHTINOV,
            mount_type=None,
            focal_length_mm=400,
            aperture_f_number=5.6,
            clearance_mm=0.35,
            pattern_border_mm=3.0,
            label=True,
        )


def test_clipped_slot_filter_snapshot_for_xf100_400_profile():
    g = calculate_mask(prof(), opts())
    assert {r.value: sum(1 for s in g.slots if s.region is r) for r in {s.region for s in g.slots}} == {
        "left-reference": 17,
        "right-upper": 10,
        "right-lower": 10,
    }
    assert min(s.useful_length_mm for s in g.slots) == pytest.approx(8.0189)


def test_clipped_slot_filter_retains_arc_and_diagonal_slots_but_rejects_tiny_fragments():
    disabled = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "minimum_clipped_slot_length_mm": 0.0}))
    filtered = calculate_mask(prof(), opts())

    assert len(disabled.slots) > len(filtered.slots)
    assert any(s.useful_length_mm == pytest.approx(0.0) for s in disabled.slots)
    assert all(s.useful_length_mm >= max(2 * s.width_mm, 4.0) for s in filtered.slots)

    # Long slots with circular aperture ends and diagonal region clipping remain.
    assert any(s.region is GratingRegion.LEFT_REFERENCE and s.useful_length_mm > 30 for s in filtered.slots)
    assert any(s.region is GratingRegion.RIGHT_UPPER and s.useful_length_mm > 20 for s in filtered.slots)

    # The decision is not based on the original candidate rectangle length.
    assert {s.length_mm for s in disabled.slots} == {s.length_mm for s in filtered.slots}
    assert len([s for s in disabled.slots if s.length_mm > 80 and s.useful_length_mm < 4.0]) > 0


def test_clipped_slot_threshold_changes_marginal_slots_and_keeps_regions_non_empty():
    base = calculate_mask(prof(), opts())
    stricter = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "minimum_clipped_slot_length_mm": 10.0}))
    assert len(stricter.slots) < len(base.slots)
    assert {s for s in stricter.slots}.issubset(set(base.slots))
    assert {s.region for s in stricter.slots} == {
        GratingRegion.LEFT_REFERENCE,
        GratingRegion.RIGHT_UPPER,
        GratingRegion.RIGHT_LOWER,
    }
    assert len(set(stricter.slots)) == len(stricter.slots)
    assert calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "minimum_clipped_slot_length_mm": 10.0})).slots == stricter.slots


def test_clipped_slot_threshold_zero_disables_filter_and_invalid_values_are_rejected():
    unfiltered = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "minimum_clipped_slot_length_mm": 0.0}))
    filtered = calculate_mask(prof(), opts())
    assert len(unfiltered.slots) > len(filtered.slots)
    assert min(s.useful_length_mm for s in unfiltered.slots) == pytest.approx(0.0)

    for bad in (float("nan"), float("inf"), -0.1):
        with pytest.raises(ValueError, match="minimum_clipped_slot_length_mm"):
            calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "minimum_clipped_slot_length_mm": bad}))
    with pytest.raises(ValueError, match="required grating region"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "minimum_clipped_slot_length_mm": 1000.0}))


def test_all_export_formats_use_same_filtered_slot_set_and_test_ring_is_unchanged(tmp_path):
    req = request(tmp_path, (OutputFormat.SCAD,))
    normal = generate(req)
    scad = normal[0].read_text(encoding="utf-8")
    geom = calculate_mask(prof(), opts())
    assert scad.count("clipped_slot(") == len(geom.slots) + 1  # includes module definition

    ring_req = GenerationRequest(**{**req.__dict__, "minimum_clipped_slot_length_mm": 1000.0})
    ring = generate(ring_req, test_ring=True)[0].read_text(encoding="utf-8")
    assert "clipped_slot" not in ring
    assert "test_ring_depth_mm=4.000" in ring


def test_tribahtinov_topology_is_unchanged_by_clipped_slot_filter_option():
    tri_default = calculate_mask(prof(), opts(mt=MaskType.TRIBAHTINOV))
    tri_strict = calculate_mask(
        prof(),
        AlgorithmOptions(**{**opts(mt=MaskType.TRIBAHTINOV).__dict__, "minimum_clipped_slot_length_mm": 1000.0}),
    )
    assert tri_default == tri_strict
    assert len({s.region for s in tri_default.slots}) == 6


def test_scad_stl_and_3mf_exports_share_filtered_scad_slot_set(monkeypatch, tmp_path):
    exported = []

    monkeypatch.setattr("selflensbahtinov.generator.supports_format", lambda openscad, fmt: True)

    def fake_export(openscad, scad_path, out, dry_run=False):
        exported.append((scad_path.read_text(encoding="utf-8"), out.suffix))
        out.write_text("exported", encoding="utf-8")

    monkeypatch.setattr("selflensbahtinov.generator.export", fake_export)
    req = request(tmp_path, (OutputFormat.SCAD, OutputFormat.STL, OutputFormat.THREEMF))
    outputs = generate(req)
    scad = outputs[0].read_text(encoding="utf-8")
    expected_slots = len(calculate_mask(prof(), opts()).slots)
    assert scad.count("clipped_slot(") == expected_slots + 1
    assert [(text.count("clipped_slot("), suffix) for text, suffix in exported] == [
        (expected_slots + 1, ".stl"),
        (expected_slots + 1, ".3mf"),
    ]


def test_default_mounting_cross_section_has_lead_in_chamfer_and_outer_edge_rounding():
    g = calculate_mask(prof(), opts())
    ri = g.ring.inner_diameter_mm / 2
    ro = g.ring.outer_diameter_mm / 2
    assert g.ring.lead_in_chamfer_mm == pytest.approx(1.0)
    assert g.ring.outer_edge_radius_mm == pytest.approx(0.5)
    assert g.ring.cross_section[0].radius_mm == pytest.approx(ri + 1.0)
    assert any(p.radius_mm == pytest.approx(ro - 0.5) and p.z_mm == pytest.approx(-g.ring.depth_mm) for p in g.ring.cross_section)
    assert any(p.radius_mm == pytest.approx(ro) and p.z_mm == pytest.approx(-g.ring.depth_mm + 0.5) for p in g.ring.cross_section)
    assert g.ring.straight_engagement_mm >= 2.0


def test_zero_chamfer_and_zero_radius_disable_mounting_edge_treatments():
    base = {**opts().__dict__}
    g = calculate_mask(prof(), AlgorithmOptions(**{**base, "lead_in_chamfer_mm": 0.0, "outer_edge_radius_mm": 0.0}))
    ri = g.ring.inner_diameter_mm / 2
    ro = g.ring.outer_diameter_mm / 2
    assert g.ring.cross_section[0].radius_mm == pytest.approx(ri)
    assert g.ring.cross_section[1].radius_mm == pytest.approx(ro)
    assert g.ring.cross_section[1].z_mm == pytest.approx(-g.ring.depth_mm)
    assert g.ring.straight_engagement_mm == pytest.approx(g.ring.depth_mm)


def test_chamfer_preserves_nominal_fit_diameter_and_only_increases_entry():
    plain = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "lead_in_chamfer_mm": 0.0}))
    chamfered = calculate_mask(prof(), opts())
    assert chamfered.ring.inner_diameter_mm == pytest.approx(plain.ring.inner_diameter_mm)
    ri = chamfered.ring.inner_diameter_mm / 2
    assert chamfered.ring.cross_section[0].radius_mm > ri
    assert [p for p in chamfered.ring.cross_section if p.radius_mm == pytest.approx(ri)]


def test_test_ring_and_full_mask_share_mounting_cross_section():
    full = calculate_mask(prof(), opts())
    ring = calculate_mask(prof(), opts(test=True))
    assert full.ring.inner_diameter_mm == pytest.approx(ring.ring.inner_diameter_mm)
    assert full.ring.clearance_mm == pytest.approx(ring.ring.clearance_mm)
    assert full.ring.lead_in_chamfer_mm == pytest.approx(ring.ring.lead_in_chamfer_mm)
    assert full.ring.outer_edge_radius_mm == pytest.approx(ring.ring.outer_edge_radius_mm)
    assert ring.ring.cross_section == calculate_mask(prof(), opts(test=True)).ring.cross_section


@pytest.mark.parametrize("field,bad", [("lead_in_chamfer_mm", -0.1), ("outer_edge_radius_mm", -0.1), ("lead_in_chamfer_mm", float("nan")), ("outer_edge_radius_mm", float("inf"))])
def test_mounting_edge_parameters_reject_invalid_values(field, bad):
    with pytest.raises(ValueError, match=field):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, field: bad}))


def test_excessive_chamfer_and_outer_radius_are_rejected():
    with pytest.raises(ValueError, match="straight engagement"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "lead_in_chamfer_mm": 7.0}))
    with pytest.raises(ValueError, match="wall thickness"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "outer_edge_radius_mm": 2.0}))
    with pytest.raises(ValueError, match="ring height"):
        calculate_mask(replace(prof(), defaults=replace(prof().defaults, ring_wall_thickness_mm=8.0)), AlgorithmOptions(**{**opts(test=True).__dict__, "outer_edge_radius_mm": 2.1}))


def test_renderer_uses_shared_mounting_profile_for_scad_stl_and_3mf_exports(tmp_path, monkeypatch):
    import selflensbahtinov.generator as generator
    calls = []
    monkeypatch.setattr(generator, "supports_format", lambda openscad, fmt: True)
    def fake_export(openscad, scad_path, out, dry_run=False):
        calls.append((scad_path.read_text(encoding="utf-8"), out.suffix))
        out.write_text("ok", encoding="utf-8")
    monkeypatch.setattr(generator, "export", fake_export)
    req = request(tmp_path, (OutputFormat.SCAD, OutputFormat.STL, OutputFormat.THREEMF))
    out = generator.generate(req)
    scad = (tmp_path / "fujifilm-xf100-400-bahtinov-lens-barrel-outer-slip-fit.scad").read_text(encoding="utf-8")
    assert "lead_in_chamfer_mm=1.0000" in scad
    assert "outer_edge_radius_mm=0.5000" in scad
    assert all("rotate_extrude" in text and "lead_in_chamfer_mm=1.0000" in text for text, _ in calls)
    assert {p.suffix for p in out} == {".scad", ".stl", ".3mf"}


def test_cli_overrides_mounting_edge_geometry_and_metadata(capsys, monkeypatch, tmp_path):
    import selflensbahtinov.cli as cli
    monkeypatch.setattr(cli, "load_profile", lambda path: prof())
    rc = cli.main(["generate", "fujifilm-xf100-400", "--mount", "lens-barrel-outer-slip-fit", "--lead-in-chamfer", "0", "--outer-edge-radius", "0", "--output-dir", str(tmp_path)])
    assert rc == 0
    scad = next(tmp_path.glob("*.scad")).read_text(encoding="utf-8")
    assert "lead_in_chamfer_mm=0.0000" in scad
    assert "outer_edge_radius_mm=0.0000" in scad



def test_ring_depth_override_controls_full_mask_engagement_length():
    g = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "ring_depth_mm": 9.5}))
    assert g.ring.depth_mm == pytest.approx(9.5)
    assert g.ring.straight_engagement_mm == pytest.approx(8.5)


def test_test_ring_depth_override_is_capped_to_short_fit_sample():
    g = calculate_mask(prof(), AlgorithmOptions(**{**opts(test=True).__dict__, "ring_depth_mm": 9.5, "lead_in_chamfer_mm": 0.5}))
    assert g.ring.depth_mm == pytest.approx(4.0)
    assert g.ring.straight_engagement_mm == pytest.approx(3.5)


def test_cli_overrides_ring_depth(capsys, monkeypatch, tmp_path):
    import selflensbahtinov.cli as cli
    monkeypatch.setattr(cli, "load_profile", lambda path: prof())
    rc = cli.main(["generate", "fujifilm-xf100-400", "--mount", "lens-barrel-outer-slip-fit", "--ring-depth", "9.5", "--output-dir", str(tmp_path)])
    assert rc == 0
    scad = next(tmp_path.glob("*.scad")).read_text(encoding="utf-8")
    assert "ring_depth_mm=9.5000" in scad

def test_support_free_print_orientation_is_documented_in_metadata():
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts(test=True)))
    assert "negative-Z entry side down" in scad
    assert "no supports" in scad


def test_outer_face_fillet_zero_preserves_geometry_and_scad_body():
    base = calculate_mask(prof(), opts())
    fillet0 = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "outer_face_fillet_radius_mm": 0.0}))
    assert fillet0 == base
    scad = OpenScadRenderer().render_scad(fillet0)
    assert "outer_face_fillet_radius_mm=0.0000" in scad
    assert "outer_face_fillet_cut();" not in scad


@pytest.mark.parametrize("radius", [0.5, 1.0, 2.0])
def test_outer_face_fillet_preserves_functional_dimensions_and_slots(radius):
    base = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "label": False}))
    g = calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "label": False, "outer_face_fillet_radius_mm": radius}))
    assert g.outer_face_fillet_radius_mm == pytest.approx(radius)
    assert g.ring.outer_diameter_mm == pytest.approx(base.ring.outer_diameter_mm)
    assert g.clear_aperture_mm == pytest.approx(base.clear_aperture_mm)
    assert g.ring.inner_diameter_mm == pytest.approx(base.ring.inner_diameter_mm)
    assert g.slots == base.slots
    scad = OpenScadRenderer().render_scad(g)
    assert f"outer_face_fillet_radius_mm={radius:.4f}" in scad
    assert "module outer_face_fillet_cut()" in scad
    assert "outer_face_fillet_cut();" in scad
    assert "rotate_extrude(convexity=4) polygon" in scad


@pytest.mark.parametrize("bad", [-0.1, float("nan"), float("inf")])
def test_outer_face_fillet_rejects_negative_and_non_finite_values(bad):
    with pytest.raises(ValueError, match="outer_face_fillet_radius_mm"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "outer_face_fillet_radius_mm": bad}))



def test_outer_face_fillet_rejects_positive_radius_below_serialization_precision():
    with pytest.raises(ValueError, match="too small to serialize safely"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "outer_face_fillet_radius_mm": 0.00001}))

def test_outer_face_fillet_rejects_excessive_radius_with_maximum():
    with pytest.raises(ValueError, match="outer_face_fillet_radius_mm=99.0000 mm exceeds maximum 2.0000 mm"):
        calculate_mask(prof(), AlgorithmOptions(**{**opts().__dict__, "outer_face_fillet_radius_mm": 99.0}))


def test_outer_face_fillet_cli_reaches_model_metadata_and_grating_info(capsys, monkeypatch, tmp_path):
    import selflensbahtinov.cli as cli

    monkeypatch.setattr(cli, "load_profile", lambda path: prof())
    rc = cli.main([
        "generate",
        "fujifilm-xf100-400",
        "--mount",
        "lens-barrel-outer-slip-fit",
        "--outer-face-fillet-radius",
        "1.0",
        "--show-grating-info",
        "--output-dir",
        str(tmp_path),
    ])
    assert rc == 0
    out = capsys.readouterr().out
    assert "outer_face_fillet_radius=1.0000mm" in out
    scad = (tmp_path / "fujifilm-xf100-400-bahtinov-lens-barrel-outer-slip-fit.scad").read_text(encoding="utf-8")
    assert "outer_face_fillet_radius_mm=1.0000" in scad
    assert "outer_face_fillet_cut();" in scad


def test_outer_face_fillet_shared_scad_for_stl_and_3mf_exports(monkeypatch, tmp_path):
    import selflensbahtinov.generator as generator

    exported = []
    monkeypatch.setattr(generator, "supports_format", lambda openscad, fmt: True)

    def fake_export(openscad, scad_path, out, dry_run=False):
        exported.append((out.suffix, scad_path.read_text(encoding="utf-8")))
        out.write_text("exported", encoding="utf-8")

    monkeypatch.setattr(generator, "export", fake_export)
    req = replace(request(tmp_path, (OutputFormat.SCAD, OutputFormat.STL, OutputFormat.THREEMF)), outer_face_fillet_radius_mm=1.0)
    outputs = generate(req)
    assert {p.suffix for p in outputs} == {".scad", ".stl", ".3mf"}
    assert [suffix for suffix, _ in exported] == [".stl", ".3mf"]
    assert all("outer_face_fillet_radius_mm=1.0000" in scad for _, scad in exported)


def test_outer_face_fillet_is_not_applied_to_test_ring_without_front_face():
    g = calculate_mask(prof(), AlgorithmOptions(**{**opts(test=True).__dict__, "outer_face_fillet_radius_mm": 1.0}))
    assert g.test_ring
    assert g.outer_face_fillet_radius_mm == pytest.approx(0.0)
    assert "outer_face_fillet_radius_mm" not in OpenScadRenderer().render_scad(g)


def _orientation(a, b, c):
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _segments_intersect(a, b, c, d):
    def sign(x):
        return (x > 1e-9) - (x < -1e-9)

    o1 = sign(_orientation(a, b, c))
    o2 = sign(_orientation(a, b, d))
    o3 = sign(_orientation(c, d, a))
    o4 = sign(_orientation(c, d, b))
    return o1 != o2 and o3 != o4


@pytest.mark.parametrize("radius", [0.5, 1.0, 2.0])
def test_outer_face_fillet_cut_profile_is_simple_and_inside_nominal_envelope(radius):
    from selflensbahtinov.renderer import _outer_face_fillet_cut_profile

    outer_radius = 44.35
    thickness = 2.0
    profile = _outer_face_fillet_cut_profile(
        outer_radius_mm=outer_radius,
        thickness_mm=thickness,
        radius_mm=radius,
        epsilon_mm=0.02,
    )
    assert all(math.isfinite(coord) for point in profile for coord in point)
    assert profile[3] == pytest.approx((outer_radius, thickness - radius), abs=1e-6)
    assert profile[-1] == pytest.approx((outer_radius - radius, thickness), abs=1e-6)
    assert all(outer_radius - radius <= r <= outer_radius + 0.02 for r, _z in profile)
    assert all(thickness - radius <= z <= thickness + 0.02 for _r, z in profile)
    assert _orientation(profile[0], profile[1], profile[2]) < 0

    closed = profile + (profile[0],)
    for i, (a, b) in enumerate(zip(closed, closed[1:])):
        for j, (c, d) in enumerate(zip(closed, closed[1:])):
            if abs(i - j) <= 1 or {i, j} == {0, len(closed) - 2}:
                continue
            assert not _segments_intersect(a, b, c, d)


@pytest.mark.parametrize("path", PROFILE_PATHS)
def test_outer_face_fillet_label_reserved_box_corners_avoid_fillet_and_aperture(path):
    g = calculate_mask(
        prof(path),
        AlgorithmOptions(**{**opts(profile=prof(path)).__dict__, "outer_face_fillet_radius_mm": 1.0}),
    )
    assert g.label is not None
    outer_radius = g.ring.outer_diameter_mm / 2
    useful_radius = g.clear_aperture_mm / 2
    label_half_height = g.label.size_mm / 2
    label_half_width = g.label.reserved_width_mm / 2
    label_radius = abs(g.label.position.y)
    safe_top_radius = outer_radius - g.outer_face_fillet_radius_mm - 0.1
    corners = [
        (sx * label_half_width, -label_radius + sy * label_half_height)
        for sx in (-1, 1)
        for sy in (-1, 1)
    ]
    assert all(math.hypot(x, y) <= safe_top_radius for x, y in corners)
    assert label_radius - label_half_height >= useful_radius + 0.1


def _read_stl_vertices(path: Path):
    data = path.read_bytes()
    if len(data) >= 84:
        triangle_count = struct.unpack("<I", data[80:84])[0]
        expected_size = 84 + triangle_count * 50
        if expected_size == len(data):
            vertices = []
            offset = 84
            for _ in range(triangle_count):
                offset += 12
                for _vertex in range(3):
                    vertices.append(struct.unpack("<fff", data[offset:offset + 12]))
                    offset += 12
                offset += 2
            return vertices

    vertices = []
    text = data.decode("utf-8")
    for line in text.splitlines():
        parts = line.split()
        if len(parts) == 4 and parts[0] == "vertex":
            vertices.append(tuple(float(v) for v in parts[1:]))
    return vertices


def _stl_edge_counts(vertices):
    def key(v):
        return tuple(round(coord, 5) for coord in v)

    counts = {}
    for i in range(0, len(vertices), 3):
        tri = [key(v) for v in vertices[i:i + 3]]
        for a, b in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])):
            edge = tuple(sorted((a, b)))
            counts[edge] = counts.get(edge, 0) + 1
    return counts


@pytest.mark.skipif(shutil.which("openscad") is None, reason="OpenSCAD is not installed")
@pytest.mark.parametrize("mount", [MountType.LENS_BARREL_OUTER_SLIP_FIT, MountType.HOOD_INNER_SLIP_FIT])
@pytest.mark.parametrize("radius", [0.0, 0.5, 1.0, 2.0])
def test_outer_face_fillet_real_openscad_stl_is_manifold_and_dimensionally_stable(tmp_path, mount, radius):
    req = replace(
        request(tmp_path, (OutputFormat.SCAD, OutputFormat.STL)),
        label=False,
        mount_type=mount,
        outer_face_fillet_radius_mm=radius,
    )
    g = geometry_for(req)
    base = geometry_for(replace(req, outer_face_fillet_radius_mm=0.0))
    outputs = generate(req)
    stl = next(path for path in outputs if path.suffix == ".stl")
    assert stl.exists()
    assert stl.stat().st_size > 0

    vertices = _read_stl_vertices(stl)
    assert vertices
    edge_counts = _stl_edge_counts(vertices)
    assert edge_counts
    assert all(count == 2 for count in edge_counts.values())

    xs = [v[0] for v in vertices]
    ys = [v[1] for v in vertices]
    zs = [v[2] for v in vertices]
    nominal_outer = g.ring.outer_diameter_mm
    assert max(max(xs) - min(xs), max(ys) - min(ys)) == pytest.approx(nominal_outer, abs=0.02)
    assert max(zs) - min(zs) == pytest.approx(g.thickness_mm + g.ring.depth_mm, abs=0.02)
    assert g.clear_aperture_mm == pytest.approx(base.clear_aperture_mm)
    assert g.ring.inner_diameter_mm == pytest.approx(base.ring.inner_diameter_mm)
    assert g.ring.mount_diameter_mm == pytest.approx(base.ring.mount_diameter_mm)
    assert g.ring.outer_diameter_mm == pytest.approx(base.ring.outer_diameter_mm)
    assert g.slots == base.slots

    outer_radius = nominal_outer / 2
    top_z = max(zs)
    top_radii = [math.hypot(x, y) for x, y, z in vertices if abs(z - top_z) <= 1e-5]
    fn_tolerance = outer_radius * (1 - math.cos(math.pi / 128))
    fillet_segments = max(6, min(32, int(max(radius, 0.5) * 12)))
    fillet_tolerance = max(radius, 0.5) * (1 - math.cos(math.pi / (2 * fillet_segments)))
    tolerance = max(0.03, fn_tolerance + fillet_tolerance + 0.03)
    # The global mesh diameter remains nominal because the vertical wall and mounting ring
    # retain the outside diameter below the front-face fillet tangency.
    assert max(top_radii) == pytest.approx(outer_radius - radius, abs=tolerance)
    if radius > 0:
        tangent_z = g.thickness_mm - radius
        tangent_radii = [math.hypot(x, y) for x, y, z in vertices if abs(z - tangent_z) <= 0.04]
        assert tangent_radii
        assert max(tangent_radii) == pytest.approx(outer_radius, abs=tolerance)



@pytest.mark.skipif(shutil.which("openscad") is None, reason="OpenSCAD is not installed")
def test_outer_face_fillet_real_3mf_export_is_valid_zip_when_supported(tmp_path):
    if not supports_format("openscad", OutputFormat.THREEMF):
        pytest.skip("OpenSCAD does not support 3MF export")
    req = replace(
        request(tmp_path, (OutputFormat.THREEMF,)),
        label=False,
        outer_face_fillet_radius_mm=1.0,
    )
    outputs = generate(req)
    threemf = next(path for path in outputs if path.suffix == ".3mf")
    assert threemf.exists()
    assert threemf.stat().st_size > 0
    with zipfile.ZipFile(threemf) as archive:
        names = set(archive.namelist())
        assert "[Content_Types].xml" in names
        assert any(name.endswith(".model") for name in names)
