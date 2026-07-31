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
        "filter_bandwidth_nm": None,
        "pixel_pitch_um": 3.76,
        "binning": 1,
        "target_first_order_offset_px": 20.0,
        "minimum_slot_width_mm": 0.8,
        "minimum_bar_width_mm": 0.8,
        "side_groove_angle_deg": 20.0,
        "focus_mode": "visual",
        "expected_star_snr": None,
    }
    values.update(overrides)
    return DesignInputs(**values)


def test_recommendation_uses_illuminated_pupil_for_useful_period_count():
    result = recommend(inputs())

    assert result.optical_aperture_diameter_mm == pytest.approx(400 / 5.6)
    assert result.illuminated_mask_diameter_mm == pytest.approx(400 / 5.6)
    assert result.effective_pixel_pitch_mm == pytest.approx(0.00376)
    assert result.optical_pitch_mm == pytest.approx(2.92553197)
    assert result.printable_pitch_mm == pytest.approx(result.optical_pitch_mm)
    assert result.slot_width_mm == pytest.approx(result.printable_pitch_mm / 2)
    assert result.bar_width_mm == pytest.approx(result.printable_pitch_mm / 2)
    assert result.open_fraction == pytest.approx(0.5)
    assert result.first_order_offset_px == pytest.approx(20.0)
    assert result.illuminated_periods_across_pupil == pytest.approx(
        (400 / 5.6) / result.printable_pitch_mm
    )
    assert result.physical_periods_across_mask == pytest.approx(
        76.7 / result.printable_pitch_mm
    )
    assert result.illuminated_periods_across_pupil == pytest.approx(24.416, abs=0.001)
    assert result.manufacturing_limited is False


def test_mask_smaller_than_pupil_limits_illuminated_diameter():
    result = recommend(inputs(mask_clear_diameter_mm=60.0))
    assert result.illuminated_mask_diameter_mm == pytest.approx(60.0)
    assert result.illuminated_periods_across_pupil == pytest.approx(
        result.physical_periods_across_mask
    )


def test_angle_metrics_distinguish_directed_and_visible_line_separation():
    result = recommend(inputs(side_groove_angle_deg=60.0))

    assert result.directed_side_order_separation_deg == pytest.approx(120.0)
    assert result.visible_side_axis_separation_deg == pytest.approx(60.0)
    assert result.one_sided_crossing_offset_gain == pytest.approx(
        1 / math.tan(math.radians(60.0))
    )
    assert result.total_crossing_separation_gain == pytest.approx(
        2 / math.tan(math.radians(60.0))
    )


def test_bandwidth_estimates_chromatic_first_order_span():
    result = recommend(inputs(filter_bandwidth_nm=100.0))

    assert result.bandpass_low_nm == pytest.approx(500.0)
    assert result.bandpass_high_nm == pytest.approx(600.0)
    assert result.bandpass_offset_low_px < result.first_order_offset_px
    assert result.bandpass_offset_high_px > result.first_order_offset_px
    assert result.bandpass_chromatic_span_px == pytest.approx(
        result.bandpass_offset_high_px - result.bandpass_offset_low_px
    )


def test_manufacturing_minimum_clamps_unprintable_pitch():
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


def test_report_exposes_corrected_geometry_and_source_limits():
    report = render_markdown(
        recommend(
            inputs(
                side_groove_angle_deg=60.0,
                filter_bandwidth_nm=100.0,
                focus_mode="software-assisted",
                expected_star_snr=12.0,
            )
        )
    )

    assert "Effectively illuminated mask diameter" in report
    assert "Useful illuminated periods" in report
    assert "min(D_mask, F / N) / p" in report
    assert "120.0° | 60.0°" in report
    assert "2 delta / tan(alpha)" in report
    assert "Geometric chromatic span" in report
    assert "10 < SNR < 15" in report
    assert "case-study thresholds, not universal limits" in report
    assert "Peer-reviewed design basis" in report
    assert "https://doi.org/10.1093/mnras/stac845" in report
    assert "https://fse.studenttheses.ub.rug.nl/16216/" in report
    assert "https://arxiv.org/abs/1802.07161" in report


def test_visual_mode_does_not_claim_a_universal_angle():
    report = render_markdown(recommend(inputs(focus_mode="visual")))
    assert "Visual mode selected" in report
    assert "does not claim one angle" in report
    assert "No single angle is scientifically optimal" in report


def test_offset_presets_keep_requested_order_and_print_constraints():
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
        ("filter_bandwidth_nm", -1.0),
        ("filter_bandwidth_nm", 1100.0),
        ("pixel_pitch_um", 0.0),
        ("target_first_order_offset_px", -1.0),
        ("minimum_slot_width_mm", 0.0),
        ("minimum_bar_width_mm", -0.1),
        ("side_groove_angle_deg", 4.9),
        ("side_groove_angle_deg", 85.0),
        ("focus_mode", "automatic-magic"),
        ("expected_star_snr", 0.0),
    ],
)
def test_invalid_inputs_are_rejected(field, value):
    with pytest.raises(ValueError, match=field):
        recommend(inputs(**{field: value}))


@pytest.mark.parametrize("binning", [0, -1, 1.5, True])
def test_binning_must_be_a_positive_integer(binning):
    with pytest.raises(ValueError, match="binning"):
        recommend(inputs(binning=binning))


def test_module_cli_writes_corrected_markdown_report(tmp_path: Path):
    output = tmp_path / "report.md"
    rc = main(
        [
            "--focal-length-mm", "400",
            "--f-number", "5.6",
            "--mask-clear-diameter-mm", "76.7",
            "--wavelength-nm", "550",
            "--filter-bandwidth-nm", "100",
            "--pixel-pitch-um", "3.76",
            "--side-groove-angle-deg", "20",
            "--focus-mode", "software-assisted",
            "--expected-star-snr", "20",
            "--output", str(output),
        ]
    )
    assert rc == 0
    text = output.read_text(encoding="utf-8")
    assert text.startswith("# Bahtinov mask scientific design report")
    assert "Useful illuminated periods" in text
    assert "Geometric chromatic span" in text


def test_workflow_collects_corrected_scientific_inputs():
    workflow = Path(".github/workflows/recommend-mask.yml").read_text(
        encoding="utf-8"
    )
    for input_name in (
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
    ):
        assert f"      {input_name}:" in workflow
    assert "--focus-mode" in workflow
    assert "--filter-bandwidth-nm" in workflow
    assert "--expected-star-snr" in workflow
    assert "python -m selflensbahtinov.design_report" in workflow
    assert "generated/bahtinov-design-report.md" in workflow
