"""Post-process clipped Bahtinov slots to remove fragile tapered remnants."""

from __future__ import annotations

from dataclasses import replace

from selflensbahtinov.models import MaskGeometry, MaskType, SlotGeometry

_MIN_MEAN_WIDTH_RATIO = 0.65


def _is_printable_clipped_slot(slot: SlotGeometry, minimum_length_mm: float) -> bool:
    """Keep slots that retain both useful length and a substantial width.

    Projected length alone lets long, needle-shaped triangles survive clipping.
    Requiring sufficient area and mean retained width removes those residues
    while preserving normal rectangular and gently clipped boundary slots.
    """
    if minimum_length_mm <= 0 or slot.clipped_area_mm2 is None:
        return True
    if slot.useful_length_mm < minimum_length_mm:
        return False

    minimum_area = minimum_length_mm * slot.width_mm
    if slot.clipped_area_mm2 < minimum_area:
        return False

    if slot.useful_length_mm <= 0:
        return False
    mean_width = slot.clipped_area_mm2 / slot.useful_length_mm
    return mean_width >= slot.width_mm * _MIN_MEAN_WIDTH_RATIO


def remove_clipped_slot_slivers(
    geometry: MaskGeometry,
    *,
    minimum_length_mm: float,
) -> MaskGeometry:
    """Return geometry without tiny triangular slot fragments at clip edges."""
    if geometry.test_ring or geometry.mask_type is not MaskType.BAHTINOV:
        return geometry
    if minimum_length_mm <= 0:
        return geometry

    retained = tuple(
        slot
        for slot in geometry.slots
        if _is_printable_clipped_slot(slot, minimum_length_mm)
    )
    if not retained:
        raise ValueError("clipped-slot cleanup removed every Bahtinov slot")

    regions_before = {slot.region for slot in geometry.slots}
    regions_after = {slot.region for slot in retained}
    if regions_after != regions_before:
        raise ValueError("clipped-slot cleanup removed every slot from a required region")

    return replace(geometry, slots=retained)
