from __future__ import annotations
import argparse, logging
from pathlib import Path
from selflensbahtinov.generator import generate, geometry_for
from selflensbahtinov.models import GenerationRequest, MaskType, MountType, OutputFormat
from selflensbahtinov.openscad import OpenScadError, UnsupportedFormatError
from selflensbahtinov.validation import (
    ProfileValidationError,
    load_profile,
    resolve_profile,
    search_profiles,
)

LOG = logging.getLogger(__name__)


def _mask(v):
    return MaskType(v)


def _mount(v):
    return MountType(v.replace("-", "_"))


def _fmt(v):
    return OutputFormat(v.lower())


def parser():
    p = argparse.ArgumentParser(
        description="Generate printable Bahtinov and TriBahtinov camera-lens masks."
    )
    p.add_argument("--verbose", action="store_true")
    sp = p.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("search")
    s.add_argument("term", nargs="?", default="")
    for c in ("show", "validate"):
        sp.add_parser(c).add_argument("profile")

    def gen(name):
        g = sp.add_parser(name)
        g.add_argument("profile")
        g.add_argument("--mask", type=_mask, choices=list(MaskType))
        g.add_argument("--mount", type=_mount, choices=list(MountType))
        g.add_argument(
            "--format",
            dest="formats",
            type=_fmt,
            action="append",
            choices=list(OutputFormat),
        )
        g.add_argument("--focal-length", type=float)
        g.add_argument("--aperture", type=float)
        g.add_argument("--clearance", type=float)
        g.add_argument("--pattern-border", type=float)
        g.add_argument("--slot-width", type=float)
        g.add_argument("--slot-spacing", type=float)
        g.add_argument("--slot-density", type=float, default=1.0)
        lab = g.add_mutually_exclusive_group()
        lab.add_argument("--label", action="store_true")
        lab.add_argument("--no-label", action="store_true")
        g.add_argument("--output-dir", type=Path, default=Path("generated"))
        g.add_argument("--openscad", default="openscad")
        g.add_argument("--dry-run", action="store_true")
        g.add_argument("--show-grating-info", action="store_true")
        return g

    gen("generate")
    gen("generate-test-ring")
    gen("generate-bundle")
    return p


def _req(a, prof):
    return GenerationRequest(
        profile=prof,
        mask_type=a.mask or prof.defaults.mask_type,
        mount_type=a.mount or prof.defaults.mount_type,
        formats=tuple(a.formats or [OutputFormat.SCAD]),
        focal_length_mm=(
            a.focal_length
            if a.focal_length is not None
            else prof.recommended_focus.focal_length_mm
        ),
        aperture_f_number=(
            a.aperture
            if a.aperture is not None
            else prof.recommended_focus.aperture_f_number
        ),
        clearance_mm=a.clearance if a.clearance is not None else prof.defaults.fit_clearance_mm,
        pattern_border_mm=(
            a.pattern_border
            if a.pattern_border is not None
            else prof.defaults.pattern_border_mm
        ),
        label=False if a.no_label else (True if a.label else prof.defaults.engrave_label),
        slot_width_mm=a.slot_width,
        slot_spacing_mm=a.slot_spacing,
        slot_density=a.slot_density,
        output_dir=a.output_dir,
        openscad=a.openscad,
        dry_run=a.dry_run,
    )


def main(argv=None):
    args = parser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    try:
        if args.cmd == "search":

            for pr in search_profiles(args.term):
                print(f"{pr.slug}\t{pr.label}\t{pr.model}")
            return 0
        prof = load_profile(resolve_profile(args.profile))
        if args.cmd == "show":
            print(
                f"{prof.slug}: {prof.manufacturer} {prof.model}\nfilter-thread slip-fit diameter: {prof.mounting.filter_thread_mm} mm\nnotes: {'; '.join(prof.notes)}"
            )
            return 0
        if args.cmd == "validate":
            print(f"OK: {prof.slug} ({prof.model})")
            return 0
        req = _req(args, prof)
        if args.show_grating_info and args.cmd != "generate-test-ring":
            grating = geometry_for(req).grating
            if grating is not None:
                print(
                    "grating: "
                    f"base_pitch={grating.base_pitch_mm:.4f}mm "
                    f"effective_pitch={grating.effective_pitch_mm:.4f}mm "
                    f"slot_width={grating.open_slot_width_mm:.4f}mm "
                    f"bar_width={grating.opaque_bar_width_mm:.4f}mm "
                    f"open_fraction={grating.open_fraction:.4f} "
                    f"density={grating.density:.4f} "
                    f"lambda={grating.reference_wavelength_nm:.1f}nm "
                    f"theta={grating.first_order_angle_rad:.8f}rad "
                    f"sensor_offset={grating.first_order_sensor_offset_mm:.6f}mm "
                    f"source={grating.pitch_selection_source}"
                )
        outputs = []
        if args.cmd == "generate-bundle":
            req = GenerationRequest(
                profile=req.profile,
                mask_type=req.mask_type,
                mount_type=req.mount_type,
                formats=(OutputFormat.SCAD, OutputFormat.STL, OutputFormat.THREEMF),
                focal_length_mm=req.focal_length_mm,
                aperture_f_number=req.aperture_f_number,
                clearance_mm=req.clearance_mm,
                pattern_border_mm=req.pattern_border_mm,
                label=req.label,
                slot_width_mm=req.slot_width_mm,
                slot_spacing_mm=req.slot_spacing_mm,
                slot_density=req.slot_density,
                output_dir=req.output_dir,
                openscad=req.openscad,
                dry_run=req.dry_run,
            )
            try:
                outputs += generate(req, test_ring=False)
                outputs += generate(req, test_ring=True)
            except UnsupportedFormatError:
                req = GenerationRequest(
                    profile=req.profile,
                    mask_type=req.mask_type,
                    mount_type=req.mount_type,
                    formats=(OutputFormat.SCAD, OutputFormat.STL),
                    focal_length_mm=req.focal_length_mm,
                    aperture_f_number=req.aperture_f_number,
                    clearance_mm=req.clearance_mm,
                    pattern_border_mm=req.pattern_border_mm,
                    label=req.label,
                    slot_width_mm=req.slot_width_mm,
                    slot_spacing_mm=req.slot_spacing_mm,
                    slot_density=req.slot_density,
                    output_dir=req.output_dir,
                    openscad=req.openscad,
                    dry_run=req.dry_run,
                )
                outputs += generate(req)
                outputs += generate(req, test_ring=True)
        else:
            outputs = generate(req, test_ring=args.cmd == "generate-test-ring")
        for o in outputs:
            print(("DRY-RUN would create: " if args.dry_run else "created: ") + str(o))
        return 0
    except (
        OSError,
        ValueError,
        ProfileValidationError,
        OpenScadError,
        NotImplementedError,
    ) as e:
        LOG.error("%s", e)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
