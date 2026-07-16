from __future__ import annotations
from pathlib import Path
from selflensbahtinov.algorithms import AlgorithmOptions, calculate_mask
from selflensbahtinov.models import GenerationRequest, OutputFormat
from selflensbahtinov.openscad import (
    UnsupportedFormatError,
    command_for,
    export,
    output_path,
    supports_format,
)
from selflensbahtinov.renderer import OpenScadRenderer


def base_name(req: GenerationRequest, test_ring: bool = False) -> str:
    mount = req.mount_type.value.replace("_", "-")
    suffix = (
        f"test-ring-{mount}"
        if test_ring
        else f"{req.mask_type.value}-{mount}"
    )
    return f"{req.profile.slug}-{suffix}"


def geometry_for(req: GenerationRequest, test_ring: bool = False):
    return calculate_mask(
        req.profile,
        AlgorithmOptions(
            mask_type=req.mask_type,
            mount_type=req.mount_type,
            focal_length_mm=req.focal_length_mm,
            aperture_f_number=req.aperture_f_number,
            clearance_mm=req.clearance_mm,
            pattern_border_mm=req.pattern_border_mm,
            region_gap_mm=req.region_gap_mm,
            label=req.label,
            test_ring=test_ring,
            slot_width_mm=req.slot_width_mm,
            slot_spacing_mm=req.slot_spacing_mm,
            slot_density=req.slot_density,
        ),
    )


def generate(req: GenerationRequest, *, test_ring: bool = False) -> list[Path]:
    geom = geometry_for(req, test_ring)
    req.output_dir.mkdir(parents=True, exist_ok=True) if not req.dry_run else None
    base = req.output_dir / base_name(req, test_ring)
    scad_path = output_path(base, OutputFormat.SCAD)
    scad = OpenScadRenderer().render_scad(geom)
    written = []
    need_scad = OutputFormat.SCAD in req.formats or any(
        f is not OutputFormat.SCAD for f in req.formats
    )
    if need_scad and not req.dry_run:
        scad_path.write_text(scad, encoding="utf-8")
    if OutputFormat.SCAD in req.formats:
        written.append(scad_path)
    for fmt in req.formats:
        if fmt is OutputFormat.SCAD:
            continue
        if not req.dry_run and not supports_format(req.openscad, fmt):
            raise UnsupportedFormatError(
                f"Installed OpenSCAD cannot export {fmt.value}; update OpenSCAD or request SCAD/STL only"
            )
        out = output_path(base, fmt)
        export(req.openscad, scad_path, out, req.dry_run)
        written.append(out)
    return written


def openscad_command_for(
    req: GenerationRequest, fmt: OutputFormat, test_ring: bool = False
):
    base = req.output_dir / base_name(req, test_ring)
    return command_for(
        req.openscad, output_path(base, OutputFormat.SCAD), output_path(base, fmt)
    )
