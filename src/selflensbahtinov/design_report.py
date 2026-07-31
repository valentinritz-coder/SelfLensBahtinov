"""Generate a scientifically grounded Bahtinov mask design report.

The model intentionally separates optical quantities from mechanical choices.
It uses first-order Fraunhofer diffraction for a binary amplitude grating and
reports where the simple model stops being authoritative.
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


@dataclass(frozen=True)
class DesignInputs:
    focal_length_mm: float
    f_number: float
    mask_clear_diameter_mm: float
    wavelength_nm: float = 550.0
    pixel_pitch_um: float = 3.76
    binning: int = 1
    target_first_order_offset_px: float = 20.0
    minimum_slot_width_mm: float = 0.8
    minimum_bar_width_mm: float = 0.8
    side_groove_angle_deg: float = 20.0

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
    effective_pixel_pitch_mm: float
    wavelength_mm: float
    optical_pitch_mm: float
    printable_pitch_mm: float
    slot_width_mm: float
    bar_width_mm: float
    open_fraction: float
    periods_across_clear_diameter: float
    first_order_angle_rad: float
    first_order_angle_arcsec: float
    first_order_offset_mm: float
    first_order_offset_px: float
    airy_radius_mm: float
    first_order_offset_airy_radii: float
    focal_length_to_pitch_ratio: float
    side_spike_separation_deg: float
    crossing_magnification: float
    manufacturing_limited: bool


def _pitch_for_sensor_offset(
    *,
    focal_length_mm: float,
    wavelength_mm: float,
    offset_mm: float,
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

    # A binary amplitude grating has its largest first-order Fourier coefficient
    # at a 50 percent open duty cycle. Move away from 50 percent only when a
    # manufacturing minimum requires it.
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
    *,
    focal_length_mm: float,
    wavelength_mm: float,
    pitch_mm: float,
) -> tuple[float, float]:
    argument = _FIRST_ORDER * wavelength_mm / pitch_mm
    if not 0 < argument < 1:
        raise ValueError("printable pitch is incompatible with first-order diffraction")
    theta = math.asin(argument)
    return theta, focal_length_mm * math.tan(theta)


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
    airy_radius_mm = 1.22 * wavelength_mm * inputs.f_number
    angle_rad = math.radians(inputs.side_groove_angle_deg)

    return DesignRecommendation(
        inputs=inputs,
        optical_aperture_diameter_mm=optical_aperture_diameter_mm,
        effective_pixel_pitch_mm=effective_pixel_pitch_mm,
        wavelength_mm=wavelength_mm,
        optical_pitch_mm=optical_pitch_mm,
        printable_pitch_mm=printable_pitch_mm,
        slot_width_mm=slot_width_mm,
        bar_width_mm=bar_width_mm,
        open_fraction=slot_width_mm / printable_pitch_mm,
        periods_across_clear_diameter=(
            inputs.mask_clear_diameter_mm / printable_pitch_mm
        ),
        first_order_angle_rad=first_order_angle_rad,
        first_order_angle_arcsec=(
            first_order_angle_rad * _ARCSECONDS_PER_RADIAN
        ),
        first_order_offset_mm=first_order_offset_mm,
        first_order_offset_px=first_order_offset_px,
        airy_radius_mm=airy_radius_mm,
        first_order_offset_airy_radii=(
            first_order_offset_mm / airy_radius_mm
        ),
        focal_length_to_pitch_ratio=(
            inputs.focal_length_mm / printable_pitch_mm
        ),
        side_spike_separation_deg=2 * inputs.side_groove_angle_deg,
        crossing_magnification=1 / math.tan(angle_rad),
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


def render_markdown(recommendation: DesignRecommendation) -> str:
    r = recommendation
    i = r.inputs
    presets = offset_presets(i)
    angles = sorted(
        set(_REFERENCE_ANGLE_PRESETS_DEG + (i.side_groove_angle_deg,))
    )

    warning = ""
    if r.manufacturing_limited:
        warning = (
            "> **Manufacturing limit active.** The requested diffraction offset "
            "would require a pitch smaller than the declared printable slot plus "
            "bar widths. The report therefore uses the smallest printable pitch; "
            "the achieved sensor offset is lower than requested.\n\n"
        )

    lines = [
        "# Bahtinov mask scientific design report",
        "",
        warning.rstrip(),
        "## Input data",
        "",
        "| Quantity | Value | Role |",
        "|---|---:|---|",
        f"| Focal length | {i.focal_length_mm:.4f} mm | Maps diffraction angle to sensor distance |",
        f"| Working f-number | f/{i.f_number:.4f} | Determines effective optical aperture and Airy scale |",
        f"| Physical clear mask diameter | {i.mask_clear_diameter_mm:.4f} mm | Determines how many grating periods fit across the mask |",
        f"| Reference wavelength | {i.wavelength_nm:.2f} nm | Use the filter central wavelength when focusing through a filter |",
        f"| Native pixel pitch | {i.pixel_pitch_um:.4f} µm | Sensor sampling |",
        f"| Binning | {i.binning}× | Effective pixel pitch multiplier |",
        f"| Requested first-order offset | {i.target_first_order_offset_px:.4f} px | Engineering target, not a universal optical constant |",
        f"| Minimum printable slot | {i.minimum_slot_width_mm:.4f} mm | Manufacturing constraint |",
        f"| Minimum printable bar | {i.minimum_bar_width_mm:.4f} mm | Manufacturing constraint |",
        f"| Side groove angle | ±{i.side_groove_angle_deg:.4f}° | Sets spike directions and crossing geometry |",
        "",
        "The effective optical aperture is computed from `D = F / N`. It is not the same thing as the physical clear diameter of the printed mask.",
        "",
        "## Recommended grating parameters",
        "",
        "| Parameter | Recommendation |",
        "|---|---:|",
        f"| Effective optical aperture diameter | {r.optical_aperture_diameter_mm:.4f} mm |",
        f"| Optical pitch required for the requested offset | {r.optical_pitch_mm:.4f} mm |",
        f"| Printable grating pitch | **{r.printable_pitch_mm:.4f} mm** |",
        f"| Open slot width | **{r.slot_width_mm:.4f} mm** |",
        f"| Opaque bar width | **{r.bar_width_mm:.4f} mm** |",
        f"| Open fraction | {r.open_fraction:.4f} |",
        f"| Approximate periods across clear diameter | {r.periods_across_clear_diameter:.2f} |",
        f"| `F / pitch` ratio | {r.focal_length_to_pitch_ratio:.2f} |",
        f"| Manufacturing clamp applied | {_format_bool(r.manufacturing_limited)} |",
        "",
        "For direct use with the current generator, keep `--slot-density 1.0`, pass the printable pitch as `--slot-spacing`, and pass the open width as `--slot-width`.",
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
        "## Offset alternatives",
        "",
        "These presets change the grating pitch, not the groove orientation. A larger first-order offset separates the diffraction structure from the stellar core but demands a finer pitch.",
        "",
        "| Requested offset | Optical pitch | Printable pitch | Slot | Bar | Achieved offset | Limited |",
        "|---:|---:|---:|---:|---:|---:|:---:|",
    ]
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
            "The grating orientation rotates the diffraction structure; it does not set its radial distance from the star. There is no single scientifically established optimum angle for every camera, seeing condition, SNR, and detection algorithm. The table therefore exposes the geometric trade-off instead of disguising a preference as a physical law.",
            "",
            "The simplified crossing magnification below is `1 / tan(α)`: for a fixed lateral displacement of the middle spike, smaller symmetric side angles produce a larger separation of the two crossings, while making the spikes more nearly parallel.",
            "",
            "| Side groove angle α | Side-spike separation | Simplified crossing magnification | Interpretation |",
            "|---:|---:|---:|---|",
        ]
    )
    for angle in angles:
        magnification = 1 / math.tan(math.radians(angle))
        if angle <= 20:
            interpretation = "high crossing magnification; spikes closer to parallel"
        elif angle <= 35:
            interpretation = "balanced visual separation and magnification"
        elif angle <= 50:
            interpretation = "wide spike separation; lower crossing magnification"
        else:
            interpretation = "very wide separation; lowest crossing magnification"
        selected = " **(selected)**" if angle == i.side_groove_angle_deg else ""
        lines.append(
            f"| ±{angle:.1f}°{selected} | {2 * angle:.1f}° | {magnification:.3f}× | {interpretation} |"
        )

    lines.extend(
        [
            "",
            "With the convention used here, central grooves are at 0°, side grooves are at ±α, and the three diffraction-spike directions are perpendicular to those groove families. The current generator fixes the side-family angle in code; this report deliberately exposes it as a design parameter for a future `--side-grating-angle` option.",
            "",
            "## Scientific model",
            "",
            "For a transmission amplitude grating at near-normal incidence, the diffraction orders obey:",
            "",
            "```text",
            "p sin(theta_m) = m lambda",
            "```",
            "",
            "where `p` is the grating pitch, `m` the diffraction order, and `lambda` the wavelength. For the first order, the sensor-plane distance is:",
            "",
            "```text",
            "x_1 = F tan(asin(lambda / p))",
            "```",
            "",
            "The implementation uses these exact trigonometric forms rather than relying on the small-angle approximation. The number of periods across a mask of clear diameter `D_mask` is approximately `D_mask / p`.",
            "",
            "A rectangular binary amplitude grating with open fraction `q` has a first-order Fourier coefficient proportional to `sin(pi q) / pi`; its magnitude is therefore maximal at `q = 0.5`. The recommendation starts at a 50% duty cycle and moves away from it only when the declared minimum printable slot or bar width requires that.",
            "",
            "## Assumptions and limits",
            "",
            "- Scalar Fraunhofer diffraction, normal incidence, and first diffraction order.",
            "- A single reference wavelength. Broadband light spreads the diffraction feature chromatically.",
            "- The report does not simulate the complete defocused PSF, aberrations, seeing, sensor MTF, star SNR, sector-area imbalance, or obstruction geometry.",
            "- Pitch and duty cycle are optical recommendations. Region gap, pattern border, mounting clearance, ring depth, label geometry, and minimum clipped-slot length remain mechanical or manufacturing decisions.",
            "- A true global optimum for angle and sector layout would require an FFT/Fresnel forward model plus a declared objective function, such as focus-estimation variance at a specified SNR.",
            "",
            "## Sources",
            "",
            "1. J. A. van den Born, W. Jellema, and E. Dijkstra, *Demonstration of an imaging technique for the measurement of PSF elongation caused by Atmospheric Dispersion*, MNRAS 512 (2022), DOI: https://doi.org/10.1093/mnras/stac845. The paper identifies line density and orientation as the primary mask design parameters and derives the grating equation for an entrance-pupil mask.",
            "2. M. Zandvliet, *The Bahtinov Mask, a Focusing Technique for the MeerLICHT Telescope and the Commissioning at Sutherland, South Africa* (2017), University of Groningen: https://fse.studenttheses.ub.rug.nl/16216/. This astronomy thesis studies practical Bahtinov focusing and image-based focus estimation.",
            "3. S. Perrin and P. Montgomery, *Fourier optics: basic concepts* (2018), arXiv:1802.07161, https://arxiv.org/abs/1802.07161. This provides the Fourier-optics framework used for pupil masks and diffraction patterns.",
            "",
            "---",
            "",
            "This report is a reproducible engineering recommendation based on an explicit optical model. It is not a claim that one pitch or groove angle is universally optimal.",
            "",
        ]
    )
    return "\n".join(line for line in lines if line is not None)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Generate a scientific Markdown recommendation for a Bahtinov mask."
    )
    parser.add_argument("--focal-length-mm", type=float, required=True)
    parser.add_argument("--f-number", type=float, required=True)
    parser.add_argument("--mask-clear-diameter-mm", type=float, required=True)
    parser.add_argument("--wavelength-nm", type=float, default=550.0)
    parser.add_argument("--pixel-pitch-um", type=float, required=True)
    parser.add_argument("--binning", type=int, default=1)
    parser.add_argument("--target-first-order-offset-px", type=float, default=20.0)
    parser.add_argument("--minimum-slot-width-mm", type=float, default=0.8)
    parser.add_argument("--minimum-bar-width-mm", type=float, default=0.8)
    parser.add_argument("--side-groove-angle-deg", type=float, default=20.0)
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
                pixel_pitch_um=args.pixel_pitch_um,
                binning=args.binning,
                target_first_order_offset_px=args.target_first_order_offset_px,
                minimum_slot_width_mm=args.minimum_slot_width_mm,
                minimum_bar_width_mm=args.minimum_bar_width_mm,
                side_groove_angle_deg=args.side_groove_angle_deg,
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
