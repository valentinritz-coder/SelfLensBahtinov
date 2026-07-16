"""Command-line interface for SelfLensBahtinov."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from selflensbahtinov.generator import generate_scad, generate_stl
from selflensbahtinov.models import GenerationOptions
from selflensbahtinov.validation import ProfileValidationError, load_profile

LOGGER = logging.getLogger(__name__)
DEFAULT_PROFILES_DIR = Path("profiles")
DEFAULT_OUTPUT_DIR = Path("generated")


def configure_logging(verbose: bool) -> None:
    """Configure console logging."""
    logging.basicConfig(level=logging.DEBUG if verbose else logging.INFO, format="%(levelname)s: %(message)s")


def profile_path(value: str) -> Path:
    """Resolve a profile argument as either a JSON path or a profile slug."""
    candidate = Path(value)
    if candidate.exists():
        return candidate
    return DEFAULT_PROFILES_DIR / f"{value}.json"


def list_profiles(profiles_dir: Path) -> int:
    """Print available profiles."""
    for path in sorted(profiles_dir.glob("*.json")):
        profile = load_profile(path)
        print(f"{profile.slug}\t{profile.label}\t{profile.model}")
    return 0


def validate_profile(path: Path) -> int:
    """Validate and print a profile summary."""
    profile = load_profile(path)
    print(f"OK: {profile.slug} ({profile.model})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the CLI argument parser."""
    parser = argparse.ArgumentParser(description="Generate camera-lens Bahtinov masks with OpenSCAD.")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list-profiles", help="List bundled lens profiles.")
    list_parser.add_argument("--profiles-dir", type=Path, default=DEFAULT_PROFILES_DIR)

    validate_parser = subparsers.add_parser("validate", help="Validate a lens profile JSON file or slug.")
    validate_parser.add_argument("profile")

    scad_parser = subparsers.add_parser("generate-scad", help="Generate a configured OpenSCAD file.")
    scad_parser.add_argument("profile")
    scad_parser.add_argument("--output", type=Path)
    scad_parser.add_argument("--test-ring", action="store_true", help="Generate only a fit test ring.")
    scad_parser.add_argument("--no-engraving", action="store_true", help="Disable engraved label text.")
    scad_parser.add_argument("--dry-run", action="store_true", help="Log actions without writing files.")

    stl_parser = subparsers.add_parser("generate-stl", help="Generate an STL file through the OpenSCAD CLI.")
    stl_parser.add_argument("profile")
    stl_parser.add_argument("--output", type=Path)
    stl_parser.add_argument("--openscad", default="openscad", help="OpenSCAD executable name or path.")
    stl_parser.add_argument("--test-ring", action="store_true", help="Generate only a fit test ring.")
    stl_parser.add_argument("--no-engraving", action="store_true", help="Disable engraved label text.")
    stl_parser.add_argument("--dry-run", action="store_true", help="Log actions without writing files.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Run the command-line interface."""
    parser = build_parser()
    args = parser.parse_args(argv)
    configure_logging(args.verbose)
    try:
        if args.command == "list-profiles":
            return list_profiles(args.profiles_dir)
        if args.command == "validate":
            return validate_profile(profile_path(args.profile))
        path = profile_path(args.profile)
        profile = load_profile(path)
        if args.command == "generate-scad":
            output = args.output or DEFAULT_OUTPUT_DIR / f"{profile.slug}.scad"
            generate_scad(GenerationOptions(path, output, args.test_ring, not args.no_engraving, args.dry_run))
            print(f"SCAD: {output}")
            return 0
        if args.command == "generate-stl":
            suffix = "-test-ring" if args.test_ring else ""
            output = args.output or DEFAULT_OUTPUT_DIR / f"{profile.slug}{suffix}.stl"
            generate_stl(GenerationOptions(path, output, args.test_ring, not args.no_engraving, args.dry_run, args.openscad))
            print(f"STL: {output}")
            return 0
    except (OSError, ProfileValidationError, ValueError) as exc:
        LOGGER.error("%s", exc)
        return 2
    parser.error(f"Unhandled command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
