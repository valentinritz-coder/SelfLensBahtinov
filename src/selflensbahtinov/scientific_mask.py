"""Generate a flat Bahtinov optical plate from scientific-report inputs only.

This module intentionally excludes lens mounting, fit clearance, labels, and
other mechanical choices.  It consumes exactly the optical and manufacturing
inputs used by :mod:`selflensbahtinov.design_report`, derives the grating from
that same recommendation, and produces a reproducible SCAD/STL/3MF bundle.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from selflensbahtinov.algorithms import GratingModel, _grating_slots
from selflensbahtinov.design_report import (
    DesignInputs,
    DesignRecommendation,
    recommend,
    render_markdown,
)
from selflensbahtinov.models import GratingRegion, OutputFormat, SlotGeometry
from selflensbahtinov.openscad import UnsupportedFormatError, export, supports_format
from selflensbahtinov.slot_cleanup import _is_printable_clipped_slot
from selflensbahtinov.slot_topology import is_valid_clipped_slot


# The action has no mechanical inputs by design.  These two choices are fixed,
# explicit implementation constants rather than hidden workflow parameters.
OPTICAL_PLATE_THICKNESS_MM = 2.0
FRAME_BAR_COUNT = 1.0


@dataclass(frozen=True)
class ScientificMaskBuild:
    inputs: DesignInputs
    recommendation: DesignRecommendation
    slots: tuple[SlotGeometry, ...]
    clear_diameter_mm: float
    outer_diameter_mm: float
    frame_width_mm: float
    region_gap_mm: float
    thickness_mm: float = OPTICAL_PLATE_THICKNESS_MM


def _minimum_clipped_length(slot_width_mm: float) -> float:
    return max(2 * slot_width_mm, 4.0)


def _filtered_slots(
    *,
    clear_diameter_mm: float,
    recommendation: DesignRecommendation,
    side_angle_deg: float,
    region_gap_mm: float,
) -> tuple[SlotGeometry, ...]:
    model = GratingModel(
        base_pitch_mm=recommendation.printable_pitch_mm,
        pitch_mm=recommendation.printable_pitch_mm,
        open_width_mm=recommendation.slot_width_mm,
        bar_width_mm=recommendation.bar_width_mm,
        open_fraction=recommendation.open_fraction,
        density=1.0,
        reference_wavelength_nm=recommendation.inputs.wavelength_nm,
        first_order_angle_rad=recommendation.first_order_angle_rad,
        first_order_sensor_offset_mm=recommendation.first_order_offset_mm,
        pitch_selection_source="scientific-report",
    )
    minimum_length = _minimum_clipped_length(recommendation.slot_width_mm)
    candidates = _grating_slots(
        clear_diameter_mm,
        model,
        (
            (GratingRegion.LEFT_REFERENCE, 0.0),
            (GratingRegion.RIGHT_UPPER, side_angle_deg),
            (GratingRegion.RIGHT_LOWER, -side_angle_deg),
        ),
        minimum_clipped_slot_length_mm=minimum_length,
        region_gap_mm=region_gap_mm,
        filter_clipped_slots=True,
    )
    radius = clear_diameter_mm / 2
    retained = tuple(
        slot
        for slot in candidates
        if is_valid_clipped_slot(
            slot,
            radius=radius,
            region_gap_mm=region_gap_mm,
        )
        and _is_printable_clipped_slot(slot, minimum_length)
    )
    required = {
        GratingRegion.LEFT_REFERENCE,
        GratingRegion.RIGHT_UPPER,
        GratingRegion.RIGHT_LOWER,
    }
    if {slot.region for slot in retained} != required:
        raise ValueError(
            "scientific-input cleanup removed every slot from a required region"
        )
    return retained


def build_mask(inputs: DesignInputs) -> ScientificMaskBuild:
    """Derive a printable flat optical plate from the report inputs."""
    recommendation = recommend(inputs)
    frame_width = recommendation.bar_width_mm * FRAME_BAR_COUNT
    region_gap = recommendation.bar_width_mm
    slots = _filtered_slots(
        clear_diameter_mm=inputs.mask_clear_diameter_mm,
        recommendation=recommendation,
        side_angle_deg=inputs.side_groove_angle_deg,
        region_gap_mm=region_gap,
    )
    return ScientificMaskBuild(
        inputs=inputs,
        recommendation=recommendation,
        slots=slots,
        clear_diameter_mm=inputs.mask_clear_diameter_mm,
        outer_diameter_mm=inputs.mask_clear_diameter_mm + 2 * frame_width,
        frame_width_mm=frame_width,
        region_gap_mm=region_gap,
    )


def render_scad(build: ScientificMaskBuild) -> str:
    """Render the report-derived optical plate as readable OpenSCAD."""
    r = build.recommendation
    radius = build.clear_diameter_mm / 2
    clip_extent = radius + r.printable_pitch_mm * 2
    lines = [
        "// Generated from Bahtinov scientific-report inputs only.",
        "// This is a flat optical plate: no mounting skirt, fit clearance, or label geometry is included.",
        f"// focal_length_mm={build.inputs.focal_length_mm:.4f} f_number={build.inputs.f_number:.4f} wavelength_nm={build.inputs.wavelength_nm:.4f}",
        f"// target_first_order_offset_px={build.inputs.target_first_order_offset_px:.4f} pixel_pitch_um={build.inputs.pixel_pitch_um:.4f} binning={build.inputs.binning}",
        f"// grating_pitch_mm={r.printable_pitch_mm:.4f} slot_width_mm={r.slot_width_mm:.4f} bar_width_mm={r.bar_width_mm:.4f}",
        f"// side_groove_angle_deg={build.inputs.side_groove_angle_deg:.4f} slot_count={len(build.slots)}",
        f"// clear_diameter_mm={build.clear_diameter_mm:.4f} outer_diameter_mm={build.outer_diameter_mm:.4f} frame_width_mm={build.frame_width_mm:.4f}",
        "$fn = 128;",
        "epsilon = 0.020;",
        f"plate_thickness_mm = {build.thickness_mm:.4f};",
        f"clear_diameter_mm = {build.clear_diameter_mm:.4f};",
        f"outer_diameter_mm = {build.outer_diameter_mm:.4f};",
        f"region_gap_mm = {build.region_gap_mm:.4f};",
        "",
        "module slot_rectangle(cx, cy, len, wid, angle) {",
        "  translate([cx, cy, plate_thickness_mm / 2])",
        "    rotate([0, 0, angle])",
        "      cube([len, wid, plate_thickness_mm + 2 * epsilon], center=true);",
        "}",
        "",
        "module aperture_clip() {",
        "  translate([0, 0, -epsilon])",
        "    cylinder(h=plate_thickness_mm + 2 * epsilon, d=clear_diameter_mm);",
        "}",
        "",
        "module region_clip(region) {",
        f"  r = {clip_extent:.4f};",
        "  g = region_gap_mm / 2;",
        "  points = region == \"left-reference\" ? [[-r, -r], [-g, -r], [-g, r], [-r, r]] :",
        "    region == \"right-upper\" ? [[g, g], [r, g], [r, r], [g, r]] :",
        "    [[g, -g], [g, -r], [r, -r], [r, -g]];",
        "  translate([0, 0, -epsilon])",
        "    linear_extrude(height=plate_thickness_mm + 2 * epsilon)",
        "      polygon(points);",
        "}",
        "",
        "module clipped_slot(cx, cy, len, wid, angle, region) {",
        "  intersection() {",
        "    slot_rectangle(cx, cy, len, wid, angle);",
        "    aperture_clip();",
        "    region_clip(region);",
        "  }",
        "}",
        "",
        "difference() {",
        "  cylinder(h=plate_thickness_mm, d=outer_diameter_mm);",
    ]
    for slot in build.slots:
        lines.append(
            f'  clipped_slot({slot.center.x:.4f}, {slot.center.y:.4f}, '
            f'{slot.length_mm:.4f}, {slot.width_mm:.4f}, '
            f'{slot.angle_deg:.4f}, "{slot.region.value}");'
        )
    lines.extend(["}", ""])
    return "\n".join(lines)


def render_design_json(build: ScientificMaskBuild) -> str:
    r = build.recommendation
    payload = {
        "schema_version": 1,
        "kind": "bahtinov-optical-plate",
        "inputs": asdict(build.inputs),
        "recommendation": {
            "estimated_entrance_pupil_diameter_mm": r.optical_aperture_diameter_mm,
            "illuminated_mask_diameter_mm": r.illuminated_mask_diameter_mm,
            "optical_pitch_mm": r.optical_pitch_mm,
            "printable_pitch_mm": r.printable_pitch_mm,
            "slot_width_mm": r.slot_width_mm,
            "bar_width_mm": r.bar_width_mm,
            "open_fraction": r.open_fraction,
            "first_order_offset_mm": r.first_order_offset_mm,
            "first_order_offset_px": r.first_order_offset_px,
            "illuminated_periods": r.illuminated_periods_across_pupil,
            "manufacturing_limited": r.manufacturing_limited,
        },
        "fixed_plate_geometry": {
            "plate_thickness_mm": build.thickness_mm,
            "frame_width_mm": build.frame_width_mm,
            "region_gap_mm": build.region_gap_mm,
            "outer_diameter_mm": build.outer_diameter_mm,
            "frame_rule": "one recommended opaque-bar width",
            "region_gap_rule": "one recommended opaque-bar width",
            "mounting_geometry_included": False,
            "label_geometry_included": False,
        },
        "slot_count": len(build.slots),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description=(
            "Generate a flat Bahtinov optical plate using only the scientific "
            "design-report inputs."
        )
    )
    p.add_argument("--focal-length-mm", type=float, required=True)
    p.add_argument("--f-number", type=float, required=True)
    p.add_argument("--mask-clear-diameter-mm", type=float, required=True)
    p.add_argument("--wavelength-nm", type=float, default=550.0)
    p.add_argument("--filter-bandwidth-nm", type=float)
    p.add_argument("--pixel-pitch-um", type=float, default=3.76)
    p.add_argument("--binning", type=int, default=1)
    p.add_argument(
        "--focus-mode",
        choices=("visual", "software-assisted"),
        default="visual",
    )
    p.add_argument("--expected-star-snr", type=float)
    p.add_argument("--target-first-order-offset-px", type=float, default=20.0)
    p.add_argument("--minimum-slot-width-mm", type=float, default=0.8)
    p.add_argument("--minimum-bar-width-mm", type=float, default=0.8)
    p.add_argument("--side-groove-angle-deg", type=float, default=20.0)
    p.add_argument("--output-dir", type=Path, default=Path("generated"))
    p.add_argument("--openscad", default="openscad")
    p.add_argument(
        "--scad-only",
        action="store_true",
        help="Write report, JSON, and SCAD without invoking OpenSCAD exports.",
    )
    return p


def _inputs_from_args(args: argparse.Namespace) -> DesignInputs:
    return DesignInputs(
        focal_length_mm=args.focal_length_mm,
        f_number=args.f_number,
        mask_clear_diameter_mm=args.mask_clear_diameter_mm,
        wavelength_nm=args.wavelength_nm,
        filter_bandwidth_nm=args.filter_bandwidth_nm,
        pixel_pitch_um=args.pixel_pitch_um,
        binning=args.binning,
        focus_mode=args.focus_mode,
        expected_star_snr=args.expected_star_snr,
        target_first_order_offset_px=args.target_first_order_offset_px,
        minimum_slot_width_mm=args.minimum_slot_width_mm,
        minimum_bar_width_mm=args.minimum_bar_width_mm,
        side_groove_angle_deg=args.side_groove_angle_deg,
    )


def generate_bundle(
    inputs: DesignInputs,
    *,
    output_dir: Path,
    openscad: str = "openscad",
    scad_only: bool = False,
) -> list[Path]:
    build = build_mask(inputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    report_path = output_dir / "bahtinov-design-report.md"
    json_path = output_dir / "bahtinov-optical-mask.json"
    scad_path = output_dir / "bahtinov-optical-mask.scad"
    report_path.write_text(render_markdown(build.recommendation), encoding="utf-8")
    json_path.write_text(render_design_json(build), encoding="utf-8")
    scad_path.write_text(render_scad(build), encoding="utf-8")
    outputs = [report_path, json_path, scad_path]
    if scad_only:
        return outputs

    for fmt in (OutputFormat.STL, OutputFormat.THREEMF):
        if not supports_format(openscad, fmt):
            raise UnsupportedFormatError(
                f"Installed OpenSCAD cannot export {fmt.value}; update OpenSCAD"
            )
        suffix = ".3mf" if fmt is OutputFormat.THREEMF else ".stl"
        output_path = output_dir / f"bahtinov-optical-mask{suffix}"
        export(openscad, scad_path, output_path)
        outputs.append(output_path)
    return outputs


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        outputs = generate_bundle(
            _inputs_from_args(args),
            output_dir=args.output_dir,
            openscad=args.openscad,
            scad_only=args.scad_only,
        )
    except (OSError, ValueError, UnsupportedFormatError) as exc:
        print(f"error: {exc}")
        return 2
    for path in outputs:
        print(f"created: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
