from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path

import pytest

from selflensbahtinov.assembly_config import (
    MechanicalMount,
    MechanicalProfile,
    PrintPreset,
    load_mechanical_profile,
    load_print_preset,
    render_json,
)
from selflensbahtinov.complete_mask import (
    assemble_bundle,
    build_complete_mask,
    load_scientific_contract,
    prepare_report_bundle,
    render_scientific_contract,
)
from selflensbahtinov.design_report import DesignInputs, recommend
from selflensbahtinov.models import GratingRegion


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


def mechanical(*, status: str = "measured") -> MechanicalProfile:
    return MechanicalProfile(
        schema_version=3,
        manufacturer="Fujifilm",
        model="Fujinon XF100-400mmF4.5-5.6 R LM OIS WR",
        slug="fujifilm-xf100-400",
        label="XF100-400",
        mounts=(
            MechanicalMount(
                name="hood-front-outer",
                type="outer-slip-fit",
                diameter_mm=92.6,
                usable_depth_mm=8.0,
                status=status,
                preferred=True,
            ),
        ),
    )


def preset() -> PrintPreset:
    return PrintPreset()


def test_simple_configuration_contracts_round_trip(tmp_path):
    profile_path = tmp_path / "mechanical.json"
    preset_path = tmp_path / "print.json"
    profile_path.write_text(render_json(mechanical()), encoding="utf-8")
    preset_path.write_text(render_json(preset()), encoding="utf-8")

    loaded_profile = load_mechanical_profile(profile_path)
    loaded_preset = load_print_preset(preset_path)

    assert loaded_profile == mechanical()
    assert loaded_profile.select_mount().name == "hood-front-outer"
    assert loaded_preset == preset()


def test_prepare_report_emits_frozen_contract_and_follow_up_templates(tmp_path):
    outputs = prepare_report_bundle(inputs(), output_dir=tmp_path)
    assert {path.name for path in outputs} == {
        "bahtinov-design-report.md",
        "bahtinov-scientific-design.json",
        "mechanical-profile.template.json",
        "print-preset.proposed.json",
        "next-step.md",
    }
    assert load_scientific_contract(
        tmp_path / "bahtinov-scientific-design.json"
    ) == recommend(inputs())
    template = json.loads(
        (tmp_path / "mechanical-profile.template.json").read_text(encoding="utf-8")
    )
    assert template["schema_version"] == 3
    assert template["mounts"][0]["diameter_mm"] is None
    assert "report workflow run ID" in (tmp_path / "next-step.md").read_text(
        encoding="utf-8"
    )


def test_scientific_contract_detects_edited_recommendation(tmp_path):
    recommendation = recommend(inputs())
    payload = json.loads(render_scientific_contract(recommendation))
    payload["recommendation"]["printable_pitch_mm"] += 0.1
    path = tmp_path / "edited.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="recommendation drift"):
        load_scientific_contract(path)


def test_complete_build_combines_science_mechanics_and_print_preset():
    scientific = recommend(inputs(side_angle=30.0))
    build = build_complete_mask(scientific, mechanical(), preset())

    assert build.full_geometry is not None
    assert build.full_geometry.clear_aperture_mm == pytest.approx(76.7)
    assert build.test_ring_geometry.test_ring is True
    assert build.test_ring_geometry.ring.depth_mm == pytest.approx(4.0)
    assert build.full_geometry.ring.depth_mm == pytest.approx(8.0)
    assert build.full_geometry.label is not None
    assert build.pattern_border_mm == pytest.approx((93.3 - 76.7) / 2)
    by_region = {
        region: {slot.angle_deg for slot in build.full_geometry.slots if slot.region is region}
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
    assert build.full_geometry.grating is not None
    assert build.full_geometry.grating.pitch_selection_source == (
        "scientific-report-contract"
    )


def test_estimated_mount_generates_test_ring_only():
    build = build_complete_mask(recommend(inputs()), mechanical(status="estimated"), preset())
    assert build.test_ring_geometry.test_ring is True
    assert build.full_geometry is None


def test_mechanical_geometry_must_preserve_report_clear_diameter():
    tiny = replace(
        mechanical(),
        mounts=(
            replace(
                mechanical().mounts[0],
                diameter_mm=70.0,
            ),
        ),
    )
    with pytest.raises(ValueError, match="less clear diameter"):
        build_complete_mask(recommend(inputs()), tiny, preset())


def test_scad_only_assembly_emits_real_mask_ring_and_cartridge(tmp_path):
    scientific_path = tmp_path / "science.json"
    mechanical_path = tmp_path / "mechanical.json"
    preset_path = tmp_path / "preset.json"
    scientific_path.write_text(
        render_scientific_contract(recommend(inputs())), encoding="utf-8"
    )
    mechanical_path.write_text(render_json(mechanical()), encoding="utf-8")
    preset_path.write_text(render_json(preset()), encoding="utf-8")

    outputs = assemble_bundle(
        scientific_contract=scientific_path,
        mechanical_profile=mechanical_path,
        print_preset=preset_path,
        output_dir=tmp_path / "out",
        openscad="openscad",
        mount_name="hood-front-outer",
        confirmed=True,
        scad_only=True,
    )
    names = {path.name for path in outputs}
    assert any(name.endswith("-bahtinov-mask.scad") for name in names)
    assert any(name.endswith("-fit-test-ring.scad") for name in names)
    assert any(name.endswith("-label-cartridge.scad") for name in names)
    mask = next(path for path in outputs if path.name.endswith("-bahtinov-mask.scad"))
    scad = mask.read_text(encoding="utf-8")
    assert "label_holder_clock_position=3" in scad
    assert '20.000, "right-upper"' in scad
    assert '-20.000, "right-lower"' in scad


def test_assembly_requires_explicit_confirmation(tmp_path):
    with pytest.raises(ValueError, match="explicit confirmation"):
        assemble_bundle(
            scientific_contract=tmp_path / "science.json",
            mechanical_profile=tmp_path / "mechanical.json",
            print_preset=tmp_path / "preset.json",
            output_dir=tmp_path / "out",
            openscad="openscad",
            confirmed=False,
            scad_only=True,
        )


def test_workflows_form_a_two_stage_handoff():
    report = Path(".github/workflows/recommend-mask.yml").read_text(encoding="utf-8")
    assembly = Path(".github/workflows/generate-scientific-mask.yml").read_text(
        encoding="utf-8"
    )

    assert "prepare-report" in report
    assert "generated/" in report
    assert "github.run_id" in report
    assert "report_run_id:" in assembly
    assert "confirm_scientific_report:" in assembly
    assert "actions/download-artifact@v5" in assembly
    assert "run-id: ${{ inputs.report_run_id }}" in assembly
    assert "mechanical-profile.json" in assembly
    assert "print-preset.json" in assembly
    assert "--confirm" in assembly
    assert "mount_diameter_mm:" in assembly
    assert "fit_clearance_mm:" in assembly
    assert "engrave_label:" in assembly
