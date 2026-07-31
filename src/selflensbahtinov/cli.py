"""Command line interface for the schema-v3 assembly pipeline."""

from __future__ import annotations

import argparse
from dataclasses import replace
import logging
from pathlib import Path

from selflensbahtinov.assembly_config import (
    MechanicalMount,
    MechanicalProfile,
    PrintPreset,
    ProfileValidationError,
    load_mechanical_profile,
    load_print_preset,
    render_json,
    resolve_mechanical_profile,
    resolve_print_preset,
    search_mechanical_profiles,
    search_print_presets,
    slugify,
)
from selflensbahtinov.complete_mask import assemble_bundle, prepare_report_bundle
from selflensbahtinov.design_report import DesignInputs
from selflensbahtinov.openscad import OpenScadError


LOG = logging.getLogger(__name__)


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


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(
        description=(
            "Build Bahtinov masks from a scientific report, a schema-v3 "
            "mechanical profile, and an independent print preset."
        )
    )
    root.add_argument("--verbose", action="store_true")
    commands = root.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="Search mechanical profiles")
    search.add_argument("term", nargs="?", default="")

    show = commands.add_parser("show", help="Show one mechanical profile")
    show.add_argument("profile")

    validate = commands.add_parser(
        "validate", help="Validate one schema-v3 mechanical profile"
    )
    validate.add_argument("profile")

    presets = commands.add_parser("presets", help="List or search print presets")
    presets.add_argument("term", nargs="?", default="")

    show_preset = commands.add_parser("show-preset")
    show_preset.add_argument("preset")

    validate_preset = commands.add_parser("validate-preset")
    validate_preset.add_argument("preset")

    create_profile = commands.add_parser(
        "create-profile", help="Create an empty schema-v3 mechanical profile"
    )
    create_profile.add_argument("--manufacturer", required=True)
    create_profile.add_argument("--model", required=True)
    create_profile.add_argument("--label", required=True)
    create_profile.add_argument("--slug")
    create_profile.add_argument("--output", type=Path, required=True)

    add_mount = commands.add_parser(
        "add-mount", help="Add a measured mounting surface to a profile"
    )
    add_mount.add_argument("profile")
    add_mount.add_argument("--name", required=True)
    add_mount.add_argument(
        "--type",
        required=True,
        choices=("outer-slip-fit", "inner-slip-fit"),
    )
    add_mount.add_argument("--diameter-mm", type=float, required=True)
    add_mount.add_argument("--usable-depth-mm", type=float, required=True)
    add_mount.add_argument(
        "--status",
        choices=("estimated", "measured", "verified"),
        default="measured",
    )
    add_mount.add_argument("--preferred", action="store_true")
    add_mount.add_argument("--output", type=Path)

    prepare = commands.add_parser(
        "prepare-report", help="Generate the scientific report contract"
    )
    _add_scientific_args(prepare)
    prepare.add_argument("--output-dir", type=Path, default=Path("generated"))

    assemble = commands.add_parser(
        "assemble", help="Assemble the complete real mask"
    )
    assemble.add_argument("--scientific-contract", type=Path, required=True)
    assemble.add_argument("--mechanical-profile", required=True)
    assemble.add_argument("--print-preset", default="default-pla")
    assemble.add_argument("--mount-name")
    assemble.add_argument("--output-dir", type=Path, default=Path("generated"))
    assemble.add_argument("--openscad", default="openscad")
    assemble.add_argument("--confirm", action="store_true")
    assemble.add_argument("--scad-only", action="store_true")

    return root


def _scientific_inputs(args: argparse.Namespace) -> DesignInputs:
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


def _show_profile(profile: MechanicalProfile) -> str:
    lines = [
        f"{profile.slug}: {profile.manufacturer} {profile.model}",
        f"label: {profile.label}",
    ]
    if not profile.mounts:
        lines.append("mounts: none measured yet")
    for mount in profile.mounts:
        preferred = " preferred" if mount.preferred else ""
        lines.append(
            "mount: "
            f"{mount.name} {mount.type} {mount.diameter_mm:.3f} mm "
            f"depth={mount.usable_depth_mm:.3f} mm "
            f"status={mount.status}{preferred}"
        )
    return "\n".join(lines)


def _create_profile(args: argparse.Namespace) -> Path:
    profile = MechanicalProfile(
        schema_version=3,
        manufacturer=args.manufacturer.strip(),
        model=args.model.strip(),
        slug=(args.slug or slugify(f"{args.manufacturer}-{args.model}")),
        label=args.label.strip(),
        mounts=(),
    )
    profile.validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_json(profile), encoding="utf-8")
    return args.output


def _add_mount(args: argparse.Namespace) -> Path:
    source = resolve_mechanical_profile(args.profile)
    profile = load_mechanical_profile(source)
    new_mount = MechanicalMount(
        name=args.name.strip(),
        type=args.type,
        diameter_mm=args.diameter_mm,
        usable_depth_mm=args.usable_depth_mm,
        status=args.status,
        preferred=args.preferred,
    )
    mounts = profile.mounts
    if args.preferred:
        mounts = tuple(replace(mount, preferred=False) for mount in mounts)
    updated = replace(profile, mounts=mounts + (new_mount,))
    updated.validate()
    destination = args.output or source
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(render_json(updated), encoding="utf-8")
    return destination


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    try:
        if args.command == "search":
            for profile in search_mechanical_profiles(args.term):
                status = "ready" if profile.is_complete else "needs-measurement"
                print(
                    f"{profile.slug}\t{profile.label}\t{profile.model}\t{status}"
                )
            return 0
        if args.command == "show":
            print(
                _show_profile(
                    load_mechanical_profile(resolve_mechanical_profile(args.profile))
                )
            )
            return 0
        if args.command == "validate":
            profile = load_mechanical_profile(
                resolve_mechanical_profile(args.profile)
            )
            print(f"OK schema-v3: {profile.slug} ({profile.model})")
            return 0
        if args.command == "presets":
            for preset in search_print_presets(args.term):
                print(preset.name)
            return 0
        if args.command == "show-preset":
            preset = load_print_preset(resolve_print_preset(args.preset))
            print(render_json(preset), end="")
            return 0
        if args.command == "validate-preset":
            preset = load_print_preset(resolve_print_preset(args.preset))
            print(f"OK print preset: {preset.name}")
            return 0
        if args.command == "create-profile":
            print(f"created: {_create_profile(args)}")
            return 0
        if args.command == "add-mount":
            print(f"updated: {_add_mount(args)}")
            return 0
        if args.command == "prepare-report":
            outputs = prepare_report_bundle(
                _scientific_inputs(args), output_dir=args.output_dir
            )
        else:
            outputs = assemble_bundle(
                scientific_contract=args.scientific_contract,
                mechanical_profile=resolve_mechanical_profile(
                    args.mechanical_profile
                ),
                print_preset=resolve_print_preset(args.print_preset),
                output_dir=args.output_dir,
                openscad=args.openscad,
                mount_name=args.mount_name,
                confirmed=args.confirm,
                scad_only=args.scad_only,
            )
        for path in outputs:
            print(f"created: {path}")
        return 0
    except (
        OSError,
        TypeError,
        ValueError,
        ProfileValidationError,
        OpenScadError,
    ) as exc:
        LOG.error("%s", exc)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
