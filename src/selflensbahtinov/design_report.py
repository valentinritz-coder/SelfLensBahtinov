"""Generate a scientifically grounded Bahtinov mask design report.

The model separates optical quantities from mechanical choices. It uses
first-order Fraunhofer diffraction for a binary amplitude grating and states
where the simplified model stops being authoritative.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import math
from pathlib import Path

_ARCSECONDS_PER_RADIAN = 206_264.806247
_FIRST_ORDER = 1
_REFERENCE_OFFSET_PRESETS_PX = (12.0, 20.0, 30.0)
_REFERENCE_ANGLE_PRESETS_DEG = (15.0, 20.0, 30.0, 45.0, 60.0)
_FOCUS_MODES = {"visual", "software-assisted"}


@dataclass(frozen=True)
class DesignInputs:
    focal_length_mm: float
    f_number: float
    mask_clear_diameter_mm: float
    wavelength_nm: float = 550.0
    filter_bandwidth_nm: float | None = None
    pixel_pitch_um: float = 3.76
    binning: int = 1
    target_first_order_offset_px: float = 20.0
    minimum_slot_width_mm: float = 0.8
    minimum_bar_width_mm: float = 0.8
    side_groove_angle_deg: float = 20.0
    focus_mode: str = "visual"
    expected_star_snr: float | None = None

    def validate(self) -> None:
        positive = {
            "focal_length_mm": self.focal_length_mm,
            "f_number": self.f_number,
            "mask_clear_diameter_mm": self.mask_clear_diameter_mm,
            "wavelength_nm": self.wavelength_nm,
            "pixel_pitch_um": self.pixel_pitch_um,
            "target_first_order_offset_px": self.target_first_order_offset_px,
            "minimum_slot_width_mm": self.minimum_slot_width_mm,
            "minimum_bar_width_mm": self.minimum_bar_width_mm,
        }
        for name, value in positive.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a positive finite number")
        if isinstance(self.binning, bool) or not isinstance(self.binning, int):
            raise ValueError("binning must be a positive integer")
        if self.binning <= 0:
            raise ValueError("binning must be a positive integer")
        if not math.isfinite(self.side_groove_angle_deg):
            raise ValueError("side_groove_angle_deg must be finite")
        if not 5.0 <= self.side_groove_angle_deg < 85.0:
            raise ValueError(
                "side_groove_angle_deg must be at least 5 degrees and smaller than 85 degrees"
            )
        if self.filter_bandwidth_nm is not None:
            if (
                not math.isfinite(self.filter_bandwidth_nm)
                or self.filter_bandwidth_nm <= 0
            ):
                raise ValueError("filter_bandwidth_nm must be a positive finite number")
            if self.filter_bandwidth_nm >= 2 * self.wavelength_nm:
                raise ValueError(
                    "filter_bandwidth_nm must leave a positive lower wavelength"
                )
        if self.focus_mode not in _FOCUS_MODES:
            raise ValueError("focus_mode must be visual or software-assisted")
        if self.expected_star_snr is not None:
            if (
                not math.isfinite(self.expected_star_snr)
                or self.expected_star_snr <= 0
            ):
                raise ValueError("expected_star_snr must be a positive finite number")


@dataclass(frozen=True)
class OffsetPreset:
    requested_offset_px: float
    optical_pitch_mm: float
    printable_pitch_mm: float
    slot_width_mm: float
    bar_width_mm: float
    achieved_offset_px: float
    manufacturing_limited: bool


@dataclass(frozen=True)
class DesignRecommendation:
    inputs: DesignInputs
    optical_aperture_diameter_mm: float
    illuminated_mask_diameter_mm: float
    effective_pixel_pitch_mm: float
    wavelength_mm: float
    optical_pitch_mm: float
    printable_pitch_mm: float
    slot_width_mm: float
    bar_width_mm: float
    open_fraction: float
    physical_periods_across_mask: float
    illuminated_periods_across_pupil: float
    first_order_angle_rad: float
    first_order_angle_arcsec: float
    first_order_offset_mm: float
    first_order_offset_px: float
    airy_radius_mm: float
    first_order_offset_airy_radii: float
    focal_length_to_pitch_ratio: float
    directed_side_order_separation_deg: float
    visible_side_axis_separation_deg: float
    one_sided_crossing_offset_gain: float
    total_crossing_separation_gain: float
    bandpass_low_nm: float | None
    bandpass_high_nm: float | None
    bandpass_offset_low_px: float | None
    bandpass_offset_high_px: float | None
    bandpass_chromatic_span_px: float | None
    manufacturing_limited: bool


def _pitch_for_sensor_offset(
    *, focal_length_mm: float, wavelength_mm: float, offset_mm: float
) -> float:
    theta = math.atan2(offset_mm, focal_length_mm)
    sine = math.sin(theta)
    if sine <= 0:
        raise ValueError("target sensor offset produces no valid diffraction angle")
    return _FIRST_ORDER * wavelength_mm / sine


def _printable_widths(
    optical_pitch_mm: float,
    minimum_slot_width_mm: float,
    minimum_bar_width_mm: float,
) -> tuple[float, float, float, bool]:
    minimum_pitch = minimum_slot_width_mm + minimum_bar_width_mm
    printable_pitch = max(optical_pitch_mm, minimum_pitch)
    ideal_slot = printable_pitch / 2
    slot_width = min(
        max(ideal_slot, minimum_slot_width_mm),
        printable_pitch - minimum_bar_width_mm,
    )
    bar_width = printable_pitch - slot_width
    return (
        printable_pitch,
        slot_width,
        bar_width,
        printable_pitch > optical_pitch_mm + 1e-12,
    )


def _achieved_offset(
    *, focal_length_mm: float, wavelength_mm: float, pitch_mm: float
) -> tuple[float, float]:
    argument = _FIRST_ORDER * wavelength_mm / pitch_mm
    if not 0 < argument < 1:
        raise ValueError("printable pitch is incompatible with first-order diffraction")
    theta = math.asin(argument)
    return theta, focal_length_mm * math.tan(theta)


def _visible_line_axis_separation(directed_separation_deg: float) -> float:
    """Return the angle between unoriented line axes.

    Diffraction spikes are lines, so their orientation is defined modulo 180°.
    For the supported side-angle interval, directed separation lies in (0, 180).
    """
    return min(directed_separation_deg, 180.0 - directed_separation_deg)


def recommend(inputs: DesignInputs) -> DesignRecommendation:
    inputs.validate()

    wavelength_mm = inputs.wavelength_nm * 1e-6
    effective_pixel_pitch_mm = inputs.pixel_pitch_um * inputs.binning / 1000
    requested_offset_mm = (
        inputs.target_first_order_offset_px * effective_pixel_pitch_mm
    )
    optical_pitch_mm = _pitch_for_sensor_offset(
        focal_length_mm=inputs.focal_length_mm,
        wavelength_mm=wavelength_mm,
        offset_mm=requested_offset_mm,
    )
    (
        printable_pitch_mm,
        slot_width_mm,
        bar_width_mm,
        manufacturing_limited,
    ) = _printable_widths(
        optical_pitch_mm,
        inputs.minimum_slot_width_mm,
        inputs.minimum_bar_width_mm,
    )
    first_order_angle_rad, first_order_offset_mm = _achieved_offset(
        focal_length_mm=inputs.focal_length_mm,
        wavelength_mm=wavelength_mm,
        pitch_mm=printable_pitch_mm,
    )
    first_order_offset_px = first_order_offset_mm / effective_pixel_pitch_mm
    optical_aperture_diameter_mm = inputs.focal_length_mm / inputs.f_number
    illuminated_mask_diameter_mm = min(
        inputs.mask_clear_diameter_mm, optical_aperture_diameter_mm
    )
    airy_radius_mm = 1.22 * wavelength_mm * inputs.f_number
    side_angle_rad = math.radians(inputs.side_groove_angle_deg)
    directed_separation = 2 * inputs.side_groove_angle_deg

    bandpass_low_nm = None
    bandpass_high_nm = None
    bandpass_offset_low_px = None
    bandpass_offset_high_px = None
    bandpass_chromatic_span_px = None
    if inputs.filter_bandwidth_nm is not None:
        bandpass_low_nm = inputs.wavelength_nm - inputs.filter_bandwidth_nm / 2
        bandpass_high_nm = inputs.wavelength_nm + inputs.filter_bandwidth_nm / 2
        _theta_low, offset_low_mm = _achieved_offset(
            focal_length_mm=inputs.focal_length_mm,
            wavelength_mm=bandpass_low_nm * 1e-6,
            pitch_mm=printable_pitch_mm,
        )
        _theta_high, offset_high_mm = _achieved_offset(
            focal_length_mm=inputs.focal_length_mm,
            wavelength_mm=bandpass_high_nm * 1e-6,
            pitch_mm=printable_pitch_mm,
        )
        bandpass_offset_low_px = offset_low_mm / effective_pixel_pitch_mm
        bandpass_offset_high_px = offset_high_mm / effective_pixel_pitch_mm
        bandpass_chromatic_span_px = (
            bandpass_offset_high_px - bandpass_offset_low_px
        )

    return DesignRecommendation(
        inputs=inputs,
        optical_aperture_diameter_mm=optical_aperture_diameter_mm,
        illuminated_mask_diameter_mm=illuminated_mask_diameter_mm,
        effective_pixel_pitch_mm=effective_pixel_pitch_mm,
        wavelength_mm=wavelength_mm,
        optical_pitch_mm=optical_pitch_mm,
        printable_pitch_mm=printable_pitch_mm,
        slot_width_mm=slot_width_mm,
        bar_width_mm=bar_width_mm,
        open_fraction=slot_width_mm / printable_pitch_mm,
        physical_periods_across_mask=(
            inputs.mask_clear_diameter_mm / printable_pitch_mm
        ),
        illuminated_periods_across_pupil=(
            illuminated_mask_diameter_mm / printable_pitch_mm
        ),
        first_order_angle_rad=first_order_angle_rad,
        first_order_angle_arcsec=(
            first_order_angle_rad * _ARCSECONDS_PER_RADIAN
        ),
        first_order_offset_mm=first_order_offset_mm,
        first_order_offset_px=first_order_offset_px,
        airy_radius_mm=airy_radius_mm,
        first_order_offset_airy_radii=first_order_offset_mm / airy_radius_mm,
        focal_length_to_pitch_ratio=inputs.focal_length_mm / printable_pitch_mm,
        directed_side_order_separation_deg=directed_separation,
        visible_side_axis_separation_deg=_visible_line_axis_separation(
            directed_separation
        ),
        one_sided_crossing_offset_gain=1 / math.tan(side_angle_rad),
        total_crossing_separation_gain=2 / math.tan(side_angle_rad),
        bandpass_low_nm=bandpass_low_nm,
        bandpass_high_nm=bandpass_high_nm,
        bandpass_offset_low_px=bandpass_offset_low_px,
        bandpass_offset_high_px=bandpass_offset_high_px,
        bandpass_chromatic_span_px=bandpass_chromatic_span_px,
        manufacturing_limited=manufacturing_limited,
    )


def offset_presets(inputs: DesignInputs) -> tuple[OffsetPreset, ...]:
    inputs.validate()
    wavelength_mm = inputs.wavelength_nm * 1e-6
    effective_pixel_pitch_mm = inputs.pixel_pitch_um * inputs.binning / 1000
    presets: list[OffsetPreset] = []
    for requested_px in _REFERENCE_OFFSET_PRESETS_PX:
        optical_pitch = _pitch_for_sensor_offset(
            focal_length_mm=inputs.focal_length_mm,
            wavelength_mm=wavelength_mm,
            offset_mm=requested_px * effective_pixel_pitch_mm,
        )
        printable, slot, bar, limited = _printable_widths(
            optical_pitch,
            inputs.minimum_slot_width_mm,
            inputs.minimum_bar_width_mm,
        )
        _theta, offset_mm = _achieved_offset(
            focal_length_mm=inputs.focal_length_mm,
            wavelength_mm=wavelength_mm,
            pitch_mm=printable,
        )
        presets.append(
            OffsetPreset(
                requested_offset_px=requested_px,
                optical_pitch_mm=optical_pitch,
                printable_pitch_mm=printable,
                slot_width_mm=slot,
                bar_width_mm=bar,
                achieved_offset_px=offset_mm / effective_pixel_pitch_mm,
                manufacturing_limited=limited,
            )
        )
    return tuple(presets)


def _format_bool(value: bool) -> str:
    return "yes" if value else "no"


def _format_optional(value: float | None, unit: str = "") -> str:
    return "not supplied" if value is None else f"{value:.4f}{unit}"


def _software_focus_note(inputs: DesignInputs) -> str:
    if inputs.focus_mode != "software-assisted":
        return (
            "Visual mode selected. The report exposes geometric trade-offs but "
            "does not claim one angle or pixel offset is universally easiest to judge."
        )
    if inputs.expected_star_snr is None:
        return (
            "Software-assisted mode selected, but no expected stellar SNR was supplied. "
            "Automated precision cannot be assessed from geometry alone."
        )
    snr = inputs.expected_star_snr
    if snr > 15:
        case_note = (
            "Zandvliet's specific Hough/Canny case study reported successful "
            "best-focus measurements for stars with SNR > 15."
        )
    elif snr >= 10:
        case_note = (
            "In Zandvliet's specific Hough/Canny case study, 10 < SNR < 15 "
            "required very good seeing and no nearby image artifacts."
        )
    else:
        case_note = (
            "Zandvliet's specific Hough/Canny case study considered stars with "
            "SNR < 10 unsuitable for that software pipeline."
        )
    return (
        f"Software-assisted mode selected with expected SNR {snr:.2f}. "
        f"{case_note} These are case-study thresholds, not universal limits."
    )


def render_markdown(recommendation: DesignRecommendation) -> str:
    r = recommendation
    i = r.inputs
    presets = offset_presets(i)
    angles = sorted(set(_REFERENCE_ANGLE_PRESETS_DEG + (i.side_groove_angle_deg,)))

    lines = ["# Bahtinov mask scientific design report", ""]
    if r.manufacturing_limited:
        lines.extend(
            [
                "> **Manufacturing limit active.** The requested diffraction offset "
                "would require a pitch smaller than the declared printable slot plus "
                "bar widths. The smallest printable pitch is used, so the achieved "
                "sensor offset is lower than requested.",
                "",
            ]
        )

    lines.extend(
        [
            "## Input data",
            "",
            "| Quantity | Value | Role |",
            "|---|---:|---|",
            f"| Focal length | {i.focal_length_mm:.4f} mm | Maps diffraction angle to sensor distance |",
            f"| Working f-number | f/{i.f_number:.4f} | Determines entrance-pupil estimate and Airy scale |",
            f"| Physical clear mask diameter | {i.mask_clear_diameter_mm:.4f} mm | Mechanical area available for the grating |",
            f"| Reference wavelength | {i.wavelength_nm:.2f} nm | Central wavelength used for the pitch recommendation |",
            f"| Filter bandwidth | {_format_optional(i.filter_bandwidth_nm, ' nm')} | Estimates chromatic spreading when supplied |",
            f"| Native pixel pitch | {i.pixel_pitch_um:.4f} µm | Sensor sampling |",
            f"| Binning | {i.binning}× | Effective pixel-pitch multiplier |",
            f"| Focus mode | {i.focus_mode} | Selects visual or software-oriented interpretation |",
            f"| Expected stellar SNR | {_format_optional(i.expected_star_snr)} | Context for software-assisted focusing |",
            f"| Requested first-order offset | {i.target_first_order_offset_px:.4f} px | Engineering target, not a universal optical constant |",
            f"| Minimum printable slot | {i.minimum_slot_width_mm:.4f} mm | Manufacturing constraint |",
            f"| Minimum printable bar | {i.minimum_bar_width_mm:.4f} mm | Manufacturing constraint |",
            f"| Side groove angle | ±{i.side_groove_angle_deg:.4f}° | Sets spike directions and crossing geometry |",
            "",
            "The entrance-pupil diameter is estimated as `D_pupil = F / N`. The illuminated mask diameter is `min(D_mask, D_pupil)`, because unilluminated printed area does not contribute grating periods to the diffraction pattern.",
            "",
            "## Recommended grating parameters",
            "",
            "| Parameter | Recommendation |",
            "|---|---:|",
            f"| Estimated entrance-pupil diameter | {r.optical_aperture_diameter_mm:.4f} mm |",
            f"| Physical clear mask diameter | {i.mask_clear_diameter_mm:.4f} mm |",
            f"| Effectively illuminated mask diameter | **{r.illuminated_mask_diameter_mm:.4f} mm** |",
            f"| Optical pitch required for requested offset | {r.optical_pitch_mm:.4f} mm |",
            f"| Printable grating pitch | **{r.printable_pitch_mm:.4f} mm** |",
            f"| Open slot width | **{r.slot_width_mm:.4f} mm** |",
            f"| Opaque bar width | **{r.bar_width_mm:.4f} mm** |",
            f"| Open fraction | {r.open_fraction:.4f} |",
            f"| Useful illuminated periods | **{r.illuminated_periods_across_pupil:.2f}** |",
            f"| Physical periods if the whole mask were illuminated | {r.physical_periods_across_mask:.2f} |",
            f"| `F / pitch` ratio | {r.focal_length_to_pitch_ratio:.2f} |",
            f"| Manufacturing clamp applied | {_format_bool(r.manufacturing_limited)} |",
            "",
            "For the current generator, keep `--slot-density 1.0`, pass the printable pitch as `--slot-spacing`, and pass the open width as `--slot-width`.",
            "",
            "## Predicted first-order location",
            "",
            "| Quantity | Prediction |",
            "|---|---:|",
            f"| Diffraction angle | {r.first_order_angle_rad:.8f} rad |",
            f"| Diffraction angle | {r.first_order_angle_arcsec:.3f} arcsec |",
            f"| Sensor-plane offset | {r.first_order_offset_mm:.6f} mm |",
            f"| Sensor-plane offset | **{r.first_order_offset_px:.3f} px** |",
            f"| Airy radius at reference wavelength | {r.airy_radius_mm:.6f} mm |",
            f"| Offset in Airy radii | {r.first_order_offset_airy_radii:.2f} |",
            "",
        ]
    )

    if i.filter_bandwidth_nm is None:
        lines.extend(
            [
                "### Chromatic spread",
                "",
                "No filter bandwidth was supplied. The prediction above is monochromatic at the reference wavelength; broadband light will spread the diffraction feature radially.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "### Chromatic spread across the supplied passband",
                "",
                "This estimate treats the passband as symmetric around the reference wavelength and reports only the first-order geometric displacement at its two edges.",
                "",
                "| Quantity | Prediction |",
                "|---|---:|",
                f"| Lower wavelength | {r.bandpass_low_nm:.2f} nm |",
                f"| Upper wavelength | {r.bandpass_high_nm:.2f} nm |",
                f"| First-order offset at lower edge | {r.bandpass_offset_low_px:.3f} px |",
                f"| First-order offset at upper edge | {r.bandpass_offset_high_px:.3f} px |",
                f"| Geometric chromatic span | **{r.bandpass_chromatic_span_px:.3f} px** |",
                "",
            ]
        )

    lines.extend(
        [
            "## Offset alternatives",
            "",
            "These presets change grating pitch, not groove orientation. A larger first-order offset separates the diffraction structure from the stellar core but demands a finer pitch.",
            "",
            "| Requested offset | Optical pitch | Printable pitch | Slot | Bar | Achieved offset | Limited |",
            "|---:|---:|---:|---:|---:|---:|:---:|",
        ]
    )
    for preset in presets:
        lines.append(
            f"| {preset.requested_offset_px:.0f} px | {preset.optical_pitch_mm:.4f} mm | "
            f"{preset.printable_pitch_mm:.4f} mm | {preset.slot_width_mm:.4f} mm | "
            f"{preset.bar_width_mm:.4f} mm | {preset.achieved_offset_px:.2f} px | "
            f"{_format_bool(preset.manufacturing_limited)} |"
        )

    lines.extend(
        [
            "",
            "## Groove-angle alternatives",
            "",
            "Grating orientation rotates the diffraction structure; pitch sets its radial distance from the star. No single angle is scientifically optimal for every camera, seeing condition, SNR, and estimator.",
            "",
            "For a middle spike displaced laterally by `delta` in a simplified 2D line-intersection model, one crossing moves by `delta / tan(alpha)` from the centre and the total distance between the two crossings is `2 delta / tan(alpha)`.",
            "",
            "Diffraction spikes are unoriented lines. Their visible axis angle is therefore defined modulo 180°, so ±60° gives 120° directed order separation but only 60° between the visible line axes.",
            "",
            "| Side angle α | Directed order separation | Visible line-axis separation | One-sided crossing offset gain | Total crossing separation gain | Interpretation |",
            "|---:|---:|---:|---:|---:|---|",
        ]
    )
    for angle in angles:
        directed = 2 * angle
        visible = _visible_line_axis_separation(directed)
        one_sided = 1 / math.tan(math.radians(angle))
        total = 2 * one_sided
        if angle <= 20:
            interpretation = "high crossing displacement; spike axes closer together"
        elif angle <= 35:
            interpretation = "balanced visual separation and crossing displacement"
        elif angle <= 50:
            interpretation = "wide visible axis separation; lower crossing displacement"
        else:
            interpretation = "directed orders diverge, but visible line axes fold modulo 180°"
        selected = " **(selected)**" if angle == i.side_groove_angle_deg else ""
        lines.append(
            f"| ±{angle:.1f}°{selected} | {directed:.1f}° | {visible:.1f}° | "
            f"{one_sided:.3f}× | {total:.3f}× | {interpretation} |"
        )

    lines.extend(
        [
            "",
            "With this convention, central grooves are at 0°, side grooves are at ±α, and diffraction-spike directions are perpendicular to the groove families. The generator still fixes the side-family angle in code; the report exposes it for a future `--side-grating-angle` option.",
            "",
            "## Focus-mode interpretation",
            "",
            _software_focus_note(i),
            "",
            "## Scientific model",
            "",
            "For a transmission amplitude grating at near-normal incidence:",
            "",
            "```text",
            "p sin(theta_m) = m lambda",
            "```",
            "",
            "For first order, the sensor-plane distance is:",
            "",
            "```text",
            "x_1 = F tan(asin(lambda / p))",
            "```",
            "",
            "The implementation uses the exact trigonometric forms. The useful number of illuminated periods is approximately `min(D_mask, F / N) / p`.",
            "",
            "A rectangular binary amplitude grating with open fraction `q` has a first-order Fourier coefficient proportional to `sin(pi q) / pi`; its magnitude is maximal at `q = 0.5`. The recommendation starts at a 50% duty cycle and departs from it only when manufacturing minima require that.",
            "",
            "## Assumptions and limits",
            "",
            "- Scalar Fraunhofer diffraction, normal incidence, and first diffraction order.",
            "- The entrance-pupil diameter is approximated by `F / N`; real photographic lenses can have pupil magnification and internal vignetting not represented here.",
            "- A supplied filter bandwidth is treated as a symmetric passband and used only to estimate edge-to-edge geometric chromatic spread.",
            "- The report does not simulate the complete defocused PSF, aberrations, seeing, sensor MTF, star SNR statistics, sector-area imbalance, or obstruction geometry.",
            "- Pitch and duty cycle are optical recommendations. Region gap, pattern border, mounting clearance, ring depth, label geometry, and clipped-slot filtering remain mechanical or manufacturing decisions.",
            "- A global optimum for angle and sector layout requires an FFT/Fresnel forward model and a declared objective such as focus-estimation variance at specified SNR.",
            "",
            "## Sources and evidential role",
            "",
            "1. **Peer-reviewed design basis:** J. A. van den Born, W. Jellema, and E. Dijkstra, *Demonstration of an imaging technique for the measurement of PSF elongation caused by Atmospheric Dispersion*, MNRAS 512 (2022), DOI: https://doi.org/10.1093/mnras/stac845. It identifies line density and orientation as primary design parameters and rewrites grating period using entrance-pupil diameter and line count.",
            "2. **Bahtinov software case study:** M. Zandvliet, *The Bahtinov Mask, a Focusing Technique for the MeerLICHT Telescope and the Commissioning at Sutherland, South Africa* (2017), University of Groningen: https://fse.studenttheses.ub.rug.nl/16216/. Its SNR findings apply to that particular Hough/Canny implementation and observing setup.",
            "3. **General Fourier-optics framework:** S. Perrin and P. Montgomery, *Fourier optics: basic concepts* (2018), arXiv:1802.07161, https://arxiv.org/abs/1802.07161. It supports the pupil-mask and diffraction framework but does not establish a universal Bahtinov optimum.",
            "",
            "---",
            "",
            "This report is a reproducible engineering recommendation based on an explicit optical model. It is not a claim that one pitch, offset, or groove angle is universally optimal.",
            "",
        ]
    )
    return "\n".join(lines)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a scientific Markdown recommendation for a Bahtinov mask."
    )
    parser.add_argument("--focal-length-mm", type=float, required=True)
    parser.add_argument("--f-number", type=float, required=True)
    parser.add_argument("--mask-clear-diameter-mm", type=float, required=True)
    parser.add_argument("--wavelength-nm", type=float, default=550.0)
    parser.add_argument("--filter-bandwidth-nm", type=float)
    parser.add_argument("--pixel-pitch-um", type=float, required=True)
    parser.add_argument("--binning", type=int, default=1)
    parser.add_argument("--target-first-order-offset-px", type=float, default=20.0)
    parser.add_argument("--minimum-slot-width-mm", type=float, default=0.8)
    parser.add_argument("--minimum-bar-width-mm", type=float, default=0.8)
    parser.add_argument("--side-groove-angle-deg", type=float, default=20.0)
    parser.add_argument(
        "--focus-mode", choices=sorted(_FOCUS_MODES), default="visual"
    )
    parser.add_argument("--expected-star-snr", type=float)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        recommendation = recommend(
            DesignInputs(
                focal_length_mm=args.focal_length_mm,
                f_number=args.f_number,
                mask_clear_diameter_mm=args.mask_clear_diameter_mm,
                wavelength_nm=args.wavelength_nm,
                filter_bandwidth_nm=args.filter_bandwidth_nm,
                pixel_pitch_um=args.pixel_pitch_um,
                binning=args.binning,
                target_first_order_offset_px=args.target_first_order_offset_px,
                minimum_slot_width_mm=args.minimum_slot_width_mm,
                minimum_bar_width_mm=args.minimum_bar_width_mm,
                side_groove_angle_deg=args.side_groove_angle_deg,
                focus_mode=args.focus_mode,
                expected_star_snr=args.expected_star_snr,
            )
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(render_markdown(recommendation), encoding="utf-8")
        print(f"created: {args.output}")
        return 0
    except (OSError, ValueError) as exc:
        print(f"error: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
