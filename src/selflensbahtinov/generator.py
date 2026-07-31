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
from selflensbahtinov.slot_topology import remove_malformed_slots
from selflensbahtinov.slot_cleanup import remove_clipped_slot_slivers
from selflensbahtinov.three_oclock_label import ThreeOClockLabelRenderer


def base_name(req: GenerationRequest, test_ring: bool = False) -> str:
    mount = req.mount_type.value.replace("_", "-")
    suffix = (
        f"test-ring-{mount}"
        if test_ring
        else f"{req.mask_type.value}-{mount}"
    )
    return f"{req.profile.slug}-{suffix}"


def geometry_for(req: GenerationRequest, test_ring: bool = False):
    geometry = calculate_mask(
        req.profile,
        AlgorithmOptions(
            mask_type=req.mask_type,
            mount_type=req.mount_type,
            focal_length_mm=req.focal_length_mm,
            aperture_f_number=req.aperture_f_number,
            clearance_mm=req.clearance_mm,
            pattern_border_mm=req.pattern_border_mm,
            ring_depth_mm=req.ring_depth_mm,
            region_gap_mm=req.region_gap_mm,
            label=req.label,
            test_ring=test_ring,
            slot_width_mm=req.slot_width_mm,
            slot_spacing_mm=req.slot_spacing_mm,
            slot_density=req.slot_density,
            minimum_clipped_slot_length_mm=req.minimum_clipped_slot_length_mm,
            lead_in_chamfer_mm=req.lead_in_chamfer_mm,
            outer_edge_radius_mm=req.outer_edge_radius_mm,
            outer_face_fillet_radius_mm=req.outer_face_fillet_radius_mm,
        ),
    )
    geometry = remove_malformed_slots(geometry)
    if not test_ring:
        minimum_length = (
            req.minimum_clipped_slot_length_mm
            if req.minimum_clipped_slot_length_mm is not None
            else max(2 * geometry.slot_width_mm, 4.0)
        )
        geometry = remove_clipped_slot_slivers(
            geometry,
            minimum_length_mm=minimum_length,
        )
    return geometry


def _write_formats(req, base: Path, scad: str) -> list[Path]:
    scad_path = output_path(base, OutputFormat.SCAD)
    need_scad = OutputFormat.SCAD in req.formats or any(
        fmt is not OutputFormat.SCAD for fmt in req.formats
    )
    if need_scad and not req.dry_run:
        scad_path.write_text(scad, encoding="utf-8")

    written = []
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


def generate(req: GenerationRequest, *, test_ring: bool = False) -> list[Path]:
    geom = geometry_for(req, test_ring)
    req.output_dir.mkdir(parents=True, exist_ok=True) if not req.dry_run else None
    renderer = ThreeOClockLabelRenderer()
    base = req.output_dir / base_name(req, test_ring)
    return _write_formats(req, base, renderer.render_scad(geom))


def generate_label_cartridge(req: GenerationRequest) -> list[Path]:
    """Generate the removable label insert matching a labelled full mask."""
    geom = geometry_for(req, test_ring=False)
    if geom.label is None:
        return []
    req.output_dir.mkdir(parents=True, exist_ok=True) if not req.dry_run else None
    renderer = ThreeOClockLabelRenderer()
    cartridge_base = req.output_dir / f"{base_name(req)}-label-cartridge"
    return _write_formats(
        req,
        cartridge_base,
        renderer.render_label_cartridge_scad(geom),
    )


def openscad_command_for(
    req: GenerationRequest, fmt: OutputFormat, test_ring: bool = False
):
    base = req.output_dir / base_name(req, test_ring)
    return command_for(
        req.openscad, output_path(base, OutputFormat.SCAD), output_path(base, fmt)
    )
