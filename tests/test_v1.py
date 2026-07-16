from __future__ import annotations

import json
import math
from dataclasses import replace
import shutil
import subprocess
import warnings
from pathlib import Path

import pytest

from selflensbahtinov.algorithms import AlgorithmOptions, calculate_mask
from selflensbahtinov.generator import generate, openscad_command_for
from selflensbahtinov.models import GenerationRequest, MaskType, MountType, OutputFormat
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
    assert {(s.sector_start_deg, s.sector_end_deg) for s in b.slots} == {
        (-60, 60),
        (60, 180),
        (180, 300),
    }
    assert len({(s.sector_start_deg, s.sector_end_deg) for s in t.slots}) == 6


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
    assert len(g.slots) > 70


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
    assert "sector_clip(start_deg, end_deg);" in scad
    assert "clipped_slot(" in scad


def test_mounting_cavity_ends_at_z_zero_and_does_not_cross_face():
    scad = OpenScadRenderer().render_scad(calculate_mask(prof(), opts()))
    assert "translate([0, 0, -8.0000]) difference()" in scad
    assert "cylinder(h=8.0000 + epsilon, d=82.7000)" in scad
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

    forbidden = ("thread", "screw", "helix", "linear_extrude(twist", "rotate_extrude")
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
