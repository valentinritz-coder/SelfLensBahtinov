"""Prepare a scientific design contract and assemble a complete mounted mask."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
import json
import math
from pathlib import Path
from typing import Any

from selflensbahtinov.algorithms import (
    AlgorithmOptions,
    GratingModel,
    _grating_slots,
    calculate_mask,
)
from selflensbahtinov.assembly_config import (
    MechanicalMount,
    MechanicalProfile,
    PrintPreset,
    load_mechanical_profile,
    load_print_preset,
    mechanical_profile_template,
    proposed_print_preset,
    render_json,
    slugify,
)
from selflensbahtinov.design_report import (
    DesignInputs,
    DesignRecommendation,
    recommend,
    render_markdown,
)
from selflensbahtinov.models import (
    Aperture,
    FocalLength,
    GratingMetadata,
    GratingRegion,
    LensProfile,
    MaskGeometry,
    MaskType,
    MountType,
    Mounting,
    OutputFormat,
    ProfileDefaults,
    RecommendedFocus,
    SlotGeometry,
)
from selflensbahtinov.openscad import export, supports_format
from selflensbahtinov.slot_cleanup import _is_printable_clipped_slot
from selflensbahtinov.slot_topology import is_valid_clipped_slot
from selflensbahtinov.three_oclock_label import ThreeOClockLabelRenderer


_SCIENTIFIC_CONTRACT_VERSION = 1
_ASSEMBLY_CONTRACT_VERSION = 1
_CRITICAL_RECOMMENDATION_FIELDS = (
    "illuminated_mask_diameter_mm",
    "printable_pitch_mm",
    "slot_width_mm",
    "bar_width_mm",
    "first_order_offset_px",
)


@dataclass(frozen=True)
class CompleteMaskBuild:
    scientific: DesignRecommendation
    mechanical_profile: MechanicalProfile
    mount: MechanicalMount
    print_preset: PrintPreset
    full_geometry: MaskGeometry | None
    test_ring_geometry: MaskGeometry
    pattern_border_mm: float


def _recommendation_payload(recommendation: DesignRecommendation) -> dict[str, Any]:
    return {
        "estimated_entrance_pupil_diameter_mm": recommendation.optical_aperture_diameter_mm,
        "illuminated_mask_diameter_mm": recommendation.illuminated_mask_diameter_mm,
        "optical_pitch_mm": recommendation.optical_pitch_mm,
        "printable_pitch_mm": recommendation.printable_pitch_mm,
        "slot_width_mm": recommendation.slot_width_mm,
        "bar_width_mm": recommendation.bar_width_mm,
        "open_fraction": recommendation.open_fraction,
        "first_order_angle_rad": recommendation.first_order_angle_rad,
        "first_order_offset_mm": recommendation.first_order_offset_mm,
        "first_order_offset_px": recommendation.first_order_offset_px,
        "illuminated_periods": recommendation.illuminated_periods_across_pupil,
        "side_groove_angle_deg": recommendation.inputs.side_groove_angle_deg,
        "manufacturing_limited": recommendation.manufacturing_limited,
    }


def render_scientific_contract(recommendation: DesignRecommendation) -> str:
    payload = {
        "schema_version": _SCIENTIFIC_CONTRACT_VERSION,
        "kind": "bahtinov-scientific-design",
        "inputs": asdict(recommendation.inputs),
        "recommendation": _recommendation_payload(recommendation),
    }
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def load_scientific_contract(path: Path) -> DesignRecommendation:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != _SCIENTIFIC_CONTRACT_VERSION:
        raise ValueError("scientific contract schema_version must be 1")
    if payload.get("kind") != "bahtinov-scientific-design":
        raise ValueError("scientific contract kind must be bahtinov-scientific-design")
    raw_inputs = payload.get("inputs")
    recorded = payload.get("recommendation")
    if not isinstance(raw_inputs, dict) or not isinstance(recorded, dict):
        raise ValueError("scientific contract must contain inputs and recommendation objects")
    inputs = DesignInputs(**raw_inputs)
    result = recommend(inputs)
    current = _recommendation_payload(result)
    for field in _CRITICAL_RECOMMENDATION_FIELDS:
        expected = recorded.get(field)
        actual = current[field]
        if not isinstance(expected, (int, float)) or not math.isclose(
            float(expected), float(actual), rel_tol=1e-9, abs_tol=1e-9
        ):
            raise ValueError(
                f"scientific contract recommendation drift detected for {field}"
            )
    if recorded.get("side_groove_angle_deg") != current["side_groove_angle_deg"]:
        raise ValueError("scientific contract side-groove angle does not match its inputs")
    return result


def _next_step_markdown(recommendation: DesignRecommendation) -> str:
    return "\n".join(
        [
            "# Next step: assemble the real mask",
            "",
            "The scientific stage is complete. It owns the optical pattern only.",
            "",
            "```text",
            "Scientific report  -> optical grating",
            "Mechanical profile -> measured mounting diameter and usable depth",
            "Print preset       -> clearance, thicknesses, and edge treatment",
            "All three          -> complete mask, fit-test ring, and label cartridge",
            "```",
            "",
            "Run the **Assemble complete mask from scientific report** workflow and enter this report workflow run ID.",
            "That second form proposes a print preset, asks for the measured mechanical data, and requires explicit confirmation before any full mask is generated.",
            "",
            f"Scientific clear diameter: **{recommendation.inputs.mask_clear_diameter_mm:.3f} mm**",
            f"Recommended pitch: **{recommendation.printable_pitch_mm:.4f} mm**",
            f"Recommended slot width: **{recommendation.slot_width_mm:.4f} mm**",
            f"Selected side angle: **±{recommendation.inputs.side_groove_angle_deg:.2f}°**",
            "",
            "The included `mechanical-profile.template.json` is deliberately incomplete. A computer can estimate diffraction; it cannot put calipers around your lens from another continent.",
            "",
        ]
    )


def prepare_report_bundle(inputs: DesignInputs, *, output_dir: Path) -> list[Path]:
    recommendation = recommend(inputs)
    output_dir.mkdir(parents=True, exist_ok=True)
    report = output_dir / "bahtinov-design-report.md"
    contract = output_dir / "bahtinov-scientific-design.json"
    profile_template = output_dir / "mechanical-profile.template.json"
    print_preset = output_dir / "print-preset.proposed.json"
    next_step = output_dir / "next-step.md"
    report.write_text(render_markdown(recommendation), encoding="utf-8")
    contract.write_text(render_scientific_contract(recommendation), encoding="utf-8")
    profile_template.write_text(
        json.dumps(
            mechanical_profile_template(
                clear_diameter_mm=inputs.mask_clear_diameter_mm
            ),
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print_preset.write_text(render_json(proposed_print_preset()), encoding="utf-8")
    next_step.write_text(_next_step_markdown(recommendation), encoding="utf-8")
    return [report, contract, profile_template, print_preset, next_step]


def _minimum_clipped_length(slot_width_mm: float) -> float:
    return max(2 * slot_width_mm, 4.0)


def _filtered_slots(
    *,
    clear_diameter_mm: float,
    recommendation: DesignRecommendation,
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
            (
                GratingRegion.RIGHT_UPPER,
                recommendation.inputs.side_groove_angle_deg,
            ),
            (
                GratingRegion.RIGHT_LOWER,
                -recommendation.inputs.side_groove_angle_deg,
            ),
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
        raise ValueError("slot cleanup removed every slot from a required region")
    return retained


def _internal_mount_type(mount: MechanicalMount) -> MountType:
    return (
        MountType.HOOD_INNER_SLIP_FIT
        if mount.type == "inner-slip-fit"
        else MountType.LENS_BARREL_OUTER_SLIP_FIT
    )


def _available_ring_inner_diameter(
    mount: MechanicalMount, preset: PrintPreset
) -> float:
    if mount.type == "inner-slip-fit":
        return (
            mount.diameter_mm
            - 2 * preset.fit_clearance_mm
            - 2 * preset.ring_wall_thickness_mm
        )
    return mount.diameter_mm + 2 * preset.fit_clearance_mm


def _legacy_profile(
    mechanical: MechanicalProfile,
    mount: MechanicalMount,
    preset: PrintPreset,
    scientific: DesignRecommendation,
) -> LensProfile:
    mount_type = _internal_mount_type(mount)
    mounting_kwargs: dict[str, Any] = {
        "filter_thread_nominal_mm": None,
        "lens_barrel_outer_mm": None,
        "lens_barrel_outer_status": "unknown",
        "hood_outer_mm": None,
        "hood_outer_status": "unknown",
        "hood_inner_mm": None,
        "hood_inner_status": "unknown",
        "recommended_mount": mount_type,
    }
    if mount_type is MountType.HOOD_INNER_SLIP_FIT:
        mounting_kwargs["hood_inner_mm"] = mount.diameter_mm
        mounting_kwargs["hood_inner_status"] = mount.status
    else:
        mounting_kwargs["lens_barrel_outer_mm"] = mount.diameter_mm
        mounting_kwargs["lens_barrel_outer_status"] = mount.status
    focal = scientific.inputs.focal_length_mm
    aperture = scientific.inputs.f_number
    return LensProfile(
        schema_version=2,
        manufacturer=mechanical.manufacturer,
        model=mechanical.model,
        slug=mechanical.slug,
        focal_length=FocalLength(focal, focal),
        aperture=Aperture(aperture, aperture),
        mounting=Mounting(**mounting_kwargs),
        recommended_focus=RecommendedFocus(focal, aperture),
        defaults=ProfileDefaults(
            mask_type=MaskType.BAHTINOV,
            mount_type=mount_type,
            fit_clearance_mm=preset.fit_clearance_mm,
            mask_thickness_mm=preset.mask_thickness_mm,
            ring_depth_mm=mount.usable_depth_mm,
            ring_wall_thickness_mm=preset.ring_wall_thickness_mm,
            pattern_border_mm=0.0,
            engrave_label=preset.engrave_label,
            lead_in_chamfer_mm=preset.lead_in_chamfer_mm,
            outer_edge_radius_mm=preset.outer_edge_radius_mm,
            outer_face_fillet_radius_mm=preset.outer_face_fillet_radius_mm,
        ),
        label=mechanical.label,
        notes=(
            "Generated from a schema-v3 mechanical profile through the compatibility adapter.",
        ),
    )


def _options(
    *,
    profile: LensProfile,
    mount: MechanicalMount,
    preset: PrintPreset,
    scientific: DesignRecommendation,
    pattern_border_mm: float,
    test_ring: bool,
) -> AlgorithmOptions:
    return AlgorithmOptions(
        mask_type=MaskType.BAHTINOV,
        mount_type=_internal_mount_type(mount),
        focal_length_mm=scientific.inputs.focal_length_mm,
        aperture_f_number=scientific.inputs.f_number,
        clearance_mm=preset.fit_clearance_mm,
        pattern_border_mm=pattern_border_mm,
        ring_depth_mm=mount.usable_depth_mm,
        region_gap_mm=preset.region_gap_mm,
        label=preset.engrave_label,
        test_ring=test_ring,
        slot_width_mm=scientific.slot_width_mm,
        slot_spacing_mm=scientific.printable_pitch_mm,
        slot_density=1.0,
        minimum_clipped_slot_length_mm=None,
        lead_in_chamfer_mm=preset.lead_in_chamfer_mm,
        outer_edge_radius_mm=preset.outer_edge_radius_mm,
        outer_face_fillet_radius_mm=preset.outer_face_fillet_radius_mm,
    )


def _scientific_grating_metadata(
    recommendation: DesignRecommendation,
) -> GratingMetadata:
    return GratingMetadata(
        base_pitch_mm=recommendation.printable_pitch_mm,
        effective_pitch_mm=recommendation.printable_pitch_mm,
        open_slot_width_mm=recommendation.slot_width_mm,
        opaque_bar_width_mm=recommendation.bar_width_mm,
        open_fraction=recommendation.open_fraction,
        density=1.0,
        reference_wavelength_nm=recommendation.inputs.wavelength_nm,
        first_order_angle_rad=recommendation.first_order_angle_rad,
        first_order_sensor_offset_mm=recommendation.first_order_offset_mm,
        pitch_selection_source="scientific-report-contract",
    )


def build_complete_mask(
    scientific: DesignRecommendation,
    mechanical: MechanicalProfile,
    preset: PrintPreset,
    *,
    mount_name: str | None = None,
) -> CompleteMaskBuild:
    mechanical.validate()
    preset.validate()
    mount = mechanical.select_mount(mount_name)
    available_inner = _available_ring_inner_diameter(mount, preset)
    clear_diameter = scientific.inputs.mask_clear_diameter_mm
    pattern_border = (available_inner - clear_diameter) / 2
    if pattern_border < 0:
        raise ValueError(
            "mechanical mounting geometry leaves less clear diameter than the scientific report requires: "
            f"available={available_inner:.3f} mm required={clear_diameter:.3f} mm"
        )
    profile = _legacy_profile(mechanical, mount, preset, scientific)
    ring_options = _options(
        profile=profile,
        mount=mount,
        preset=preset,
        scientific=scientific,
        pattern_border_mm=pattern_border,
        test_ring=True,
    )
    test_ring = calculate_mask(profile, ring_options)
    full: MaskGeometry | None = None
    if mount.status != "estimated":
        full_options = replace(ring_options, test_ring=False)
        base = calculate_mask(profile, full_options)
        slots = _filtered_slots(
            clear_diameter_mm=clear_diameter,
            recommendation=scientific,
            region_gap_mm=preset.region_gap_mm,
        )
        full = replace(
            base,
            clear_aperture_mm=clear_diameter,
            slot_width_mm=scientific.slot_width_mm,
            slot_spacing_mm=scientific.printable_pitch_mm,
            slots=slots,
            grating=_scientific_grating_metadata(scientific),
        )
    return CompleteMaskBuild(
        scientific=scientific,
        mechanical_profile=mechanical,
        mount=mount,
        print_preset=preset,
        full_geometry=full,
        test_ring_geometry=test_ring,
        pattern_border_mm=pattern_border,
    )


def _write_scad_and_exports(
    *,
    base: Path,
    scad: str,
    openscad: str,
    scad_only: bool,
) -> list[Path]:
    scad_path = base.with_suffix(".scad")
    scad_path.write_text(scad, encoding="utf-8")
    outputs = [scad_path]
    if scad_only:
        return outputs
    stl_path = base.with_suffix(".stl")
    export(openscad, scad_path, stl_path)
    outputs.append(stl_path)
    if supports_format(openscad, OutputFormat.THREEMF):
        threemf_path = base.with_suffix(".3mf")
        export(openscad, scad_path, threemf_path)
        outputs.append(threemf_path)
    return outputs


def _assembly_payload(build: CompleteMaskBuild) -> dict[str, Any]:
    return {
        "schema_version": _ASSEMBLY_CONTRACT_VERSION,
        "kind": "complete-bahtinov-mask-assembly",
        "scientific": {
            "inputs": asdict(build.scientific.inputs),
            "recommendation": _recommendation_payload(build.scientific),
        },
        "mechanical_profile": asdict(build.mechanical_profile),
        "selected_mount": asdict(build.mount),
        "print_preset": asdict(build.print_preset),
        "derived": {
            "pattern_border_mm": build.pattern_border_mm,
            "full_mask_generated": build.full_geometry is not None,
            "label_cartridge_generated": bool(
                build.full_geometry is not None and build.full_geometry.label is not None
            ),
        },
    }


def _assembly_summary(build: CompleteMaskBuild) -> str:
    status_note = (
        "Only a fit-test ring was generated because the mounting diameter is estimated. "
        "Measure it with calipers before generating the complete mask."
        if build.full_geometry is None
        else "The complete mask, matching fit-test ring, and label cartridge (when enabled) were generated from one frozen scientific contract."
    )
    return "\n".join(
        [
            "# Bahtinov mask assembly summary",
            "",
            "```text",
            "Scientific report  -> optical grating",
            "Mechanical profile -> mounting diameter and usable depth",
            "Print preset       -> fit and print geometry",
            "All three          -> real mask assembly",
            "```",
            "",
            f"- Lens: **{build.mechanical_profile.manufacturer} {build.mechanical_profile.model}**",
            f"- Mount: **{build.mount.name}** ({build.mount.type}, {build.mount.diameter_mm:.3f} mm, {build.mount.status})",
            f"- Usable mounting depth: **{build.mount.usable_depth_mm:.3f} mm**",
            f"- Scientific clear diameter: **{build.scientific.inputs.mask_clear_diameter_mm:.3f} mm**",
            f"- Pitch / slot / bar: **{build.scientific.printable_pitch_mm:.4f} / {build.scientific.slot_width_mm:.4f} / {build.scientific.bar_width_mm:.4f} mm**",
            f"- Side angle: **±{build.scientific.inputs.side_groove_angle_deg:.2f}°**",
            f"- Radial clearance: **{build.print_preset.fit_clearance_mm:.3f} mm**",
            f"- Derived pattern border: **{build.pattern_border_mm:.3f} mm**",
            "",
            status_note,
            "",
            "Print and physically test the short ring before trusting the full-depth skirt. Plastic remains stubbornly noncompliant with software confidence.",
            "",
        ]
    )


def assemble_bundle(
    *,
    scientific_contract: Path,
    mechanical_profile: Path,
    print_preset: Path,
    output_dir: Path,
    openscad: str,
    mount_name: str | None = None,
    confirmed: bool = False,
    scad_only: bool = False,
) -> list[Path]:
    if not confirmed:
        raise ValueError(
            "assembly requires explicit confirmation that the scientific report and proposed print settings were reviewed"
        )
    scientific = load_scientific_contract(scientific_contract)
    mechanical = load_mechanical_profile(mechanical_profile)
    preset = load_print_preset(print_preset)
    build = build_complete_mask(
        scientific,
        mechanical,
        preset,
        mount_name=mount_name,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    renderer = ThreeOClockLabelRenderer()
    stem = f"{mechanical.slug}-{slugify(build.mount.name)}"
    outputs: list[Path] = []
    copied_report = output_dir / "bahtinov-design-report.md"
    copied_contract = output_dir / "bahtinov-scientific-design.json"
    copied_profile = output_dir / "mechanical-profile.json"
    copied_preset = output_dir / "print-preset.json"
    assembly_contract = output_dir / "mask-assembly.json"
    summary = output_dir / "assembly-summary.md"
    copied_report.write_text(render_markdown(scientific), encoding="utf-8")
    copied_contract.write_text(render_scientific_contract(scientific), encoding="utf-8")
    copied_profile.write_text(render_json(mechanical), encoding="utf-8")
    copied_preset.write_text(render_json(preset), encoding="utf-8")
    assembly_contract.write_text(
        json.dumps(_assembly_payload(build), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    summary.write_text(_assembly_summary(build), encoding="utf-8")
    outputs.extend(
        [
            copied_report,
            copied_contract,
            copied_profile,
            copied_preset,
            assembly_contract,
            summary,
        ]
    )
    outputs.extend(
        _write_scad_and_exports(
            base=output_dir / f"{stem}-fit-test-ring",
            scad=renderer.render_scad(build.test_ring_geometry),
            openscad=openscad,
            scad_only=scad_only,
        )
    )
    if build.full_geometry is not None:
        outputs.extend(
            _write_scad_and_exports(
                base=output_dir / f"{stem}-bahtinov-mask",
                scad=renderer.render_scad(build.full_geometry),
                openscad=openscad,
                scad_only=scad_only,
            )
        )
        if build.full_geometry.label is not None:
            outputs.extend(
                _write_scad_and_exports(
                    base=output_dir / f"{stem}-label-cartridge",
                    scad=renderer.render_label_cartridge_scad(build.full_geometry),
                    openscad=openscad,
                    scad_only=scad_only,
                )
            )
    return outputs


def _add_scientific_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--focal-length-mm", type=float, required=True)
    parser.add_argument("--f-number", type=float, required=True)
    parser.add_argument("--mask-clear-diameter-mm", type=float, required=True)
    parser.add_argument("--wavelength-nm", type=float, default=550.0)
    parser.add_argument("--filter-bandwidth-nm", type=float)
    parser.add_argument("--pixel-pitch-um", type=float, default=3.76)
    parser.add_argument("--binning", type=int, default=1)
    parser.add_argument(
        "--focus-mode",
        choices=("visual", "software-assisted"),
        default="visual",
    )
    parser.add_argument("--expected-star-snr", type=float)
    parser.add_argument("--target-first-order-offset-px", type=float, default=20.0)
    parser.add_argument("--minimum-slot-width-mm", type=float, default=0.8)
    parser.add_argument("--minimum-bar-width-mm", type=float, default=0.8)
    parser.add_argument("--side-groove-angle-deg", type=float, default=20.0)


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


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare a scientific design contract or assemble a complete mounted mask."
    )
    sub = parser.add_subparsers(dest="command", required=True)
    prepare = sub.add_parser("prepare-report")
    _add_scientific_args(prepare)
    prepare.add_argument("--output-dir", type=Path, default=Path("generated"))
    assemble = sub.add_parser("assemble")
    assemble.add_argument("--scientific-contract", type=Path, required=True)
    assemble.add_argument("--mechanical-profile", type=Path, required=True)
    assemble.add_argument("--print-preset", type=Path, required=True)
    assemble.add_argument("--mount-name")
    assemble.add_argument("--output-dir", type=Path, default=Path("generated"))
    assemble.add_argument("--openscad", default="openscad")
    assemble.add_argument("--confirm", action="store_true")
    assemble.add_argument("--scad-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "prepare-report":
            outputs = prepare_report_bundle(
                _inputs_from_args(args), output_dir=args.output_dir
            )
        else:
            outputs = assemble_bundle(
                scientific_contract=args.scientific_contract,
                mechanical_profile=args.mechanical_profile,
                print_preset=args.print_preset,
                output_dir=args.output_dir,
                openscad=args.openscad,
                mount_name=args.mount_name,
                confirmed=args.confirm,
                scad_only=args.scad_only,
            )
    except (OSError, TypeError, ValueError) as exc:
        print(f"error: {exc}")
        return 2
    for path in outputs:
        print(f"created: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
