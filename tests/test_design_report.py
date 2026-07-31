from __future__ import annotations

import math
from pathlib import Path

import pytest

from selflensbahtinov.design_report import (
    DesignInputs,
    main,
    offset_presets,
    recommend,
    render_markdown,
)


def inputs(**overrides):
    values = {
        "focal_length_mm": 400.0,
        "f_number": 5.6,
        "mask_clear_diameter_mm": 76.7,
        "wavelength_nm": 550.0,
        "pixel_pitch_um": 3.76,
        "binning": 1,
        "target_first_order_offset_px": 20.0,
        "minimum_slot_width_mm": 0.8,
        "minimum_bar_width_mm": 0.8,
        "side_groove_angle_deg": 20.0,
    }
    values.update(overrides)
    return DesignInputs(**values)


def test_recommendation_uses_grating_equation_and_sensor_sampling():
    result = recommend(inputs())

    assert result.optical_aperture_diameter_mm == pytest.approx(400 / 5.6)
    assert result.effective_pixel_pitch_mm == pytest.approx(0.00376)
    assert result.optical_pitch_mm == pytest.approx(2.92553197)
    assert result.printable_pitch_mm == pytest.approx(result.optical_pitch_mm)
    assert result.slot_width_mm == pytest.approx(result.printable_pitch_mm / 2)
    assert result.bar_width_mm == pytest.approx(result.printable_pitch_mm / 2)
    assert result.open_fraction == pytest.approx(0.5)
    assert result.first_order_offset_px == pytest.approx(20.0)
    assert result.first_order_angle_rad == pytest.approx(
        math.asin(result.wavelength_mm / result.printable_pitch_mm)
    )
    assert result.periods_across_clear_diameter == pytest.approx(
        76.7 / result.printable_pitch_mm
    )
    assert result.side_spike_separation_deg == pytest.approx(40.0)
    assert result.crossing_magnification == pytest.approx(
        1 / math.tan(math.radians(20.0))
    )
    assert result.manufacturing_limited is False


def test_manufacturing_minimum_clamps_unprintable_short_focal_pitch():
    result = recommend(
        inputs(
            focal_length_mm=14.0,
            f_number=1.8,
            mask_clear_diameter_mm=80.0,
            target_first_order_offset_px=30.0,
        )
    )

    assert result.optical_pitch_mm < 1.6
    assert result.printable_pitch_mm == pytest.approx(1.6)
    assert result.slot_width_mm == pytest.approx(0.8)
    assert result.bar_width_mm == pytest.approx(0.8)
    assert result.first_order_offset_px < 30.0
    assert result.manufacturing_limited is True


def test_asymmetric_print_limits_preserve_both_minimum_features():
    result = recommend(
        inputs(
            focal_length_mm=20.0,
            minimum_slot_width_mm=1.0,
            minimum_bar_width_mm=0.7,
        )
    )

    assert result.printable_pitch_mm >= 1.7
    assert result.slot_width_mm >= 1.0
    assert result.bar_width_mm >= 0.7
    assert result.slot_width_mm + result.bar_width_mm == pytest.approx(
        result.printable_pitch_mm
    )


def test_report_exposes_angle_tradeoff_and_scientific_limits():
    report = render_markdown(recommend(inputs(side_groove_angle_deg=30.0)))

    assert "p sin(theta_m) = m lambda" in report
    assert "x_1 = F tan(asin(lambda / p))" in report
    assert "±30.0° **(selected)**" in report
    assert "1 / tan(α)" in report
    assert "no single scientifically established optimum angle" in report
    assert "future `--side-grating-angle` option" in report
    assert "https://doi.org/10.1093/mnras/stac845" in report
    assert "https://fse.studenttheses.ub.rug.nl/16216/" in report
    assert "https://arxiv.org/abs/1802.07161" in report
    assert "does not simulate the complete defocused PSF" in report


def test_offset_presets_keep_requested_order_and_share_print_constraints():
    presets = offset_presets(inputs())

    assert [preset.requested_offset_px for preset in presets] == [12.0, 20.0, 30.0]
    assert all(preset.slot_width_mm >= 0.8 for preset in presets)
    assert all(preset.bar_width_mm >= 0.8 for preset in presets)
    assert presets[0].printable_pitch_mm > presets[1].printable_pitch_mm
    assert presets[1].printable_pitch_mm > presets[2].printable_pitch_mm


@pytest.mark.parametrize(
    "field,value",
    [
        ("focal_length_mm", 0.0),
        ("f_number", float("nan")),
        ("mask_clear_diameter_mm", -1.0),
        ("wavelength_nm", float("inf")),
        ("pixel_pitch_um", 0.0),
        ("target_first_order_offset_px", -1.0),
        ("minimum_slot_width_mm", 0.0),
        ("minimum_bar_width_mm", -0.1),
        ("side_groove_angle_deg", 4.9),
        ("side_groove_angle_deg", 85.0),
    ],
)
def test_invalid_inputs_are_rejected(field, value):
    with pytest.raises(ValueError, match=field):
        recommend(inputs(**{field: value}))


@pytest.mark.parametrize("binning", [0, -1, 1.5, True])
def test_binning_must_be_a_positive_integer(binning):
    with pytest.raises(ValueError, match="binning"):
        recommend(inputs(binning=binning))


def test_module_cli_writes_markdown_report(tmp_path: Path):
    output = tmp_path / "report.md"
    rc = main(
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
            "--side-groove-angle-deg",
            "20",
            "--output",
            str(output),
        ]
    )

    assert rc == 0
    assert output.is_file()
    text = output.read_text(encoding="utf-8")
    assert text.startswith("# Bahtinov mask scientific design report")
    assert "Printable grating pitch" in text


def test_workflow_collects_required_optical_and_manufacturing_inputs():
    workflow = Path(".github/workflows/recommend-mask.yml").read_text(
        encoding="utf-8"
    )

    for input_name in (
        "focal_length_mm",
        "f_number",
        "mask_clear_diameter_mm",
        "wavelength_nm",
        "pixel_pitch_um",
        "binning",
        "target_first_order_offset_px",
        "minimum_slot_width_mm",
        "minimum_bar_width_mm",
        "side_groove_angle_deg",
    ):
        assert f"      {input_name}:" in workflow
    assert "python -m selflensbahtinov.design_report" in workflow
    assert "generated/bahtinov-design-report.md" in workflow
    assert 'cat generated/bahtinov-design-report.md >> "$GITHUB_STEP_SUMMARY"' in workflow
    assert "actions/upload-artifact@v7" in workflow
