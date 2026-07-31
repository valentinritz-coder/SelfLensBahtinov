from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from selflensbahtinov.design_report import DesignInputs, recommend
from selflensbahtinov.models import GratingRegion
from selflensbahtinov.scientific_mask import (
    OPTICAL_PLATE_THICKNESS_MM,
    build_mask,
    generate_bundle,
    main,
    render_design_json,
    render_scad,
)


def inputs(*, side_angle: float = 20.0) -> DesignInputs:
    return DesignInputs(
        focal_length_mm=400.0,
        f_number=5.6,
        mask_clear_diameter_mm=76.7,
        wavelength_nm=550.0,
        pixel_pitch_um=3.76,
        binning=1,
        focus_mode="visual",
        target_first_order_offset_px=20.0,
        minimum_slot_width_mm=0.8,
        minimum_bar_width_mm=0.8,
        side_groove_angle_deg=side_angle,
    )


def test_build_uses_the_same_scientific_recommendation():
    source = inputs()
    expected = recommend(source)
    build = build_mask(source)

    assert build.recommendation == expected
    assert build.recommendation.printable_pitch_mm == pytest.approx(2.9255, abs=0.0001)
    assert build.recommendation.slot_width_mm == pytest.approx(1.4628, abs=0.0001)
    assert build.frame_width_mm == pytest.approx(expected.bar_width_mm)
    assert build.region_gap_mm == pytest.approx(expected.bar_width_mm)
    assert build.outer_diameter_mm == pytest.approx(
        source.mask_clear_diameter_mm + 2 * expected.bar_width_mm
    )
    assert build.thickness_mm == pytest.approx(OPTICAL_PLATE_THICKNESS_MM)
    assert build.slots


def test_side_angle_from_report_inputs_reaches_both_oblique_families():
    build = build_mask(inputs(side_angle=30.0))
    by_region = {
        region: {slot.angle_deg for slot in build.slots if slot.region is region}
        for region in {
            GratingRegion.LEFT_REFERENCE,
            GratingRegion.RIGHT_UPPER,
            GratingRegion.RIGHT_LOWER,
        }
    }
    assert by_region == {
        GratingRegion.LEFT_REFERENCE: {0.0},
        GratingRegion.RIGHT_UPPER: {30.0},
        GratingRegion.RIGHT_LOWER: {-30.0},
    }


def test_flat_plate_scad_contains_report_geometry_without_mounting_features():
    build = build_mask(inputs())
    scad = render_scad(build)

    assert "Generated from Bahtinov scientific-report inputs only" in scad
    assert f"grating_pitch_mm={build.recommendation.printable_pitch_mm:.4f}" in scad
    assert "side_groove_angle_deg=20.0000" in scad
    assert "20.0000, \"right-upper\"" in scad
    assert "-20.0000, \"right-lower\"" in scad
    assert "mounting_ring" not in scad
    assert "label_cartridge" not in scad
    assert "fit_clearance" not in scad
    assert "difference()" in scad


def test_design_json_is_a_machine_readable_contract():
    build = build_mask(inputs())
    payload = json.loads(render_design_json(build))

    assert payload["schema_version"] == 1
    assert payload["kind"] == "bahtinov-optical-plate"
    assert payload["inputs"]["side_groove_angle_deg"] == pytest.approx(20.0)
    assert payload["recommendation"]["printable_pitch_mm"] == pytest.approx(
        build.recommendation.printable_pitch_mm
    )
    fixed = payload["fixed_plate_geometry"]
    assert fixed["mounting_geometry_included"] is False
    assert fixed["label_geometry_included"] is False
    assert fixed["plate_thickness_mm"] == pytest.approx(2.0)
    assert payload["slot_count"] == len(build.slots)


def test_scad_only_bundle_writes_report_json_and_scad(tmp_path):
    outputs = generate_bundle(inputs(), output_dir=tmp_path, scad_only=True)
    assert {path.name for path in outputs} == {
        "bahtinov-design-report.md",
        "bahtinov-optical-mask.json",
        "bahtinov-optical-mask.scad",
    }
    assert all(path.exists() and path.stat().st_size > 0 for path in outputs)
    assert "Useful illuminated periods" in (
        tmp_path / "bahtinov-design-report.md"
    ).read_text(encoding="utf-8")


def test_cli_accepts_only_report_inputs_for_scad_only_generation(tmp_path):
    assert main(
        [
            "--focal-length-mm",
            "400",
            "--f-number",
            "5.6",
            "--mask-clear-diameter-mm",
            "76.7",
            "--wavelength-nm",
            "550",
            "--pixel-pitch-um",
            "3.76",
            "--binning",
            "1",
            "--focus-mode",
            "visual",
            "--target-first-order-offset-px",
            "20",
            "--minimum-slot-width-mm",
            "0.8",
            "--minimum-bar-width-mm",
            "0.8",
            "--side-groove-angle-deg",
            "20",
            "--output-dir",
            str(tmp_path),
            "--scad-only",
        ]
    ) == 0
    assert (tmp_path / "bahtinov-optical-mask.scad").exists()


def _workflow_input_names(path: Path) -> tuple[str, ...]:
    text = path.read_text(encoding="utf-8")
    block = text.split("    inputs:\n", 1)[1].split("\npermissions:", 1)[0]
    return tuple(re.findall(r"^      ([a-z0-9_]+):$", block, flags=re.MULTILINE))


def test_generation_workflow_uses_exactly_the_report_workflow_inputs():
    report_workflow = Path(".github/workflows/recommend-mask.yml")
    generation_workflow = Path(".github/workflows/generate-scientific-mask.yml")

    report_inputs = _workflow_input_names(report_workflow)
    generation_inputs = _workflow_input_names(generation_workflow)
    assert generation_inputs == report_inputs
    assert set(generation_inputs) == {
        "focal_length_mm",
        "f_number",
        "mask_clear_diameter_mm",
        "wavelength_nm",
        "filter_bandwidth_nm",
        "pixel_pitch_um",
        "binning",
        "focus_mode",
        "expected_star_snr",
        "target_first_order_offset_px",
        "minimum_slot_width_mm",
        "minimum_bar_width_mm",
        "side_groove_angle_deg",
    }

    workflow = generation_workflow.read_text(encoding="utf-8")
    assert "python -m selflensbahtinov.scientific_mask" in workflow
    assert "--mount" not in workflow
    assert "mount_diameter" not in workflow
    assert "--clearance" not in workflow
    assert "--ring-depth" not in workflow
    assert "bahtinov-optical-mask.scad" in workflow or "generated/" in workflow
