from __future__ import annotations
import argparse, logging
from pathlib import Path
from selflensbahtinov.generator import generate
from selflensbahtinov.models import GenerationRequest, MaskType, MountType, OutputFormat
from selflensbahtinov.openscad import OpenScadError
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
        lab = g.add_mutually_exclusive_group()
        lab.add_argument("--label", action="store_true")
        lab.add_argument("--no-label", action="store_true")
        g.add_argument("--output-dir", type=Path, default=Path("generated"))
        g.add_argument("--openscad", default="openscad")
        g.add_argument("--dry-run", action="store_true")
        return g

    gen("generate")
    gen("generate-test-ring")
    gen("generate-bundle")
    return p


def _req(a, prof):
    return GenerationRequest(
        prof,
        a.mask or prof.defaults.mask_type,
        a.mount or prof.defaults.mount_type,
        tuple(a.formats or [OutputFormat.SCAD]),
        a.focal_length or prof.recommended_focus.focal_length_mm,
        a.aperture or prof.recommended_focus.aperture_f_number,
        a.clearance if a.clearance is not None else prof.defaults.fit_clearance_mm,
        (
            a.pattern_border
            if a.pattern_border is not None
            else prof.defaults.pattern_border_mm
        ),
        False if a.no_label else (True if a.label else prof.defaults.engrave_label),
        a.output_dir,
        a.openscad,
        a.dry_run,
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
        outputs = []
        if args.cmd == "generate-bundle":
            req = GenerationRequest(
                req.profile,
                req.mask_type,
                req.mount_type,
                (OutputFormat.SCAD, OutputFormat.STL, OutputFormat.THREEMF),
                req.focal_length_mm,
                req.aperture_f_number,
                req.clearance_mm,
                req.pattern_border_mm,
                req.label,
                req.output_dir,
                req.openscad,
                req.dry_run,
            )
            try:
                outputs += generate(req, test_ring=False)
                outputs += generate(req, test_ring=True)
            except OpenScadError:
                req = GenerationRequest(
                    req.profile,
                    req.mask_type,
                    req.mount_type,
                    (OutputFormat.SCAD, OutputFormat.STL),
                    req.focal_length_mm,
                    req.aperture_f_number,
                    req.clearance_mm,
                    req.pattern_border_mm,
                    req.label,
                    req.output_dir,
                    req.openscad,
                    req.dry_run,
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
