"""Python-owned mask pattern calculations for V1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from collections.abc import Iterable

from selflensbahtinov.models import (
    LabelGeometry,
    LensProfile,
    MaskGeometry,
    MaskType,
    MountType,
    Point2D,
    RingGeometry,
    SlotGeometry,
)


@dataclass(frozen=True)
class AlgorithmOptions:
    mask_type: MaskType
    mount_type: MountType
    focal_length_mm: float
    aperture_f_number: float
    clearance_mm: float
    pattern_border_mm: float
    label: bool
    test_ring: bool = False


class MaskAlgorithm(ABC):
    @abstractmethod
    def calculate(
        self, profile: LensProfile, options: AlgorithmOptions
    ) -> MaskGeometry:
        """Calculate all V1 mask geometry before rendering."""


def _ring(profile: LensProfile, options: AlgorithmOptions) -> RingGeometry:
    mount_diameter = profile.mount_diameter_mm(options.mount_type)
    inner_diameter = mount_diameter + 2 * options.clearance_mm
    wall = profile.defaults.ring_wall_thickness_mm
    depth = (
        min(profile.defaults.ring_depth_mm, 4.0)
        if options.test_ring
        else profile.defaults.ring_depth_mm
    )
    return RingGeometry(
        mount_type=options.mount_type,
        mount_diameter_mm=mount_diameter,
        inner_diameter_mm=inner_diameter,
        outer_diameter_mm=inner_diameter + 2 * wall,
        wall_thickness_mm=wall,
        depth_mm=depth,
        clearance_mm=options.clearance_mm,
    )


def _slot_dimensions(
    clear_aperture_mm: float, options: AlgorithmOptions
) -> tuple[float, float, float]:
    # The clear aperture is mechanical. Focus settings only tune pitch modestly.
    focal_ratio = max(options.aperture_f_number, 1.0)
    width = max(0.8, min(2.2, clear_aperture_mm / (28.0 + focal_ratio * 2.0)))
    spacing = width * 2.4
    length = clear_aperture_mm + 2 * spacing
    return round(width, 4), round(spacing, 4), round(length, 4)


def _candidate_slots(
    clear_aperture_mm: float,
    width: float,
    spacing: float,
    length: float,
    sectors: Iterable[tuple[float, float, float]],
) -> tuple[SlotGeometry, ...]:
    radius = clear_aperture_mm / 2
    slots: list[SlotGeometry] = []
    for sector_start, sector_end, slot_angle in sectors:
        normal_angle = math.radians(slot_angle + 90)
        # Cover the aperture with a regular family of parallel candidate slots.
        # The renderer clips each candidate against its circular aperture sector.
        count = math.ceil(radius / spacing) + 1
        for index in range(-count, count + 1):
            offset = index * spacing
            if abs(offset) > radius + width:
                continue
            x = math.cos(normal_angle) * offset
            y = math.sin(normal_angle) * offset
            slots.append(
                SlotGeometry(
                    center=Point2D(round(x, 4), round(y, 4)),
                    length_mm=length,
                    width_mm=width,
                    angle_deg=slot_angle,
                    sector_start_deg=sector_start,
                    sector_end_deg=sector_end,
                )
            )
    return tuple(slots)


def _base(
    profile: LensProfile,
    options: AlgorithmOptions,
    mask_type: MaskType,
    sectors: tuple[tuple[float, float, float], ...],
) -> MaskGeometry:
    ring = _ring(profile, options)
    clear_aperture = ring.inner_diameter_mm - 2 * options.pattern_border_mm
    if clear_aperture <= 0:
        raise ValueError("pattern_border_mm leaves no usable clear aperture")
    width, spacing, length = _slot_dimensions(clear_aperture, options)
    slots = (
        ()
        if options.test_ring
        else _candidate_slots(clear_aperture, width, spacing, length, sectors)
    )
    label = None
    if options.label and not options.test_ring:
        label_radius = clear_aperture / 2 + max(
            1.0, (ring.outer_diameter_mm - clear_aperture) / 4
        )
        label = LabelGeometry(
            profile.label, Point2D(0, round(-label_radius, 4)), 3.0, 0
        )
    return MaskGeometry(
        profile_slug=profile.slug,
        mask_type=mask_type,
        clear_aperture_mm=round(clear_aperture, 4),
        slot_width_mm=width,
        slot_spacing_mm=spacing,
        slots=slots,
        ring=ring,
        thickness_mm=profile.defaults.mask_thickness_mm,
        pattern_border_mm=options.pattern_border_mm,
        label=label,
        test_ring=options.test_ring,
    )


class BahtinovMaskAlgorithm(MaskAlgorithm):
    def calculate(
        self, profile: LensProfile, options: AlgorithmOptions
    ) -> MaskGeometry:
        return _base(
            profile,
            options,
            MaskType.BAHTINOV,
            ((-60, 60, 0), (60, 180, 60), (180, 300, -60)),
        )


class TriBahtinovMaskAlgorithm(MaskAlgorithm):
    def calculate(
        self, profile: LensProfile, options: AlgorithmOptions
    ) -> MaskGeometry:
        return _base(
            profile,
            options,
            MaskType.TRIBAHTINOV,
            (
                (-60, 0, 0),
                (0, 60, 90),
                (60, 120, 60),
                (120, 180, 150),
                (180, 240, -60),
                (240, 300, 30),
            ),
        )


ALGORITHMS = {
    MaskType.BAHTINOV: BahtinovMaskAlgorithm(),
    MaskType.TRIBAHTINOV: TriBahtinovMaskAlgorithm(),
}


def calculate_mask(profile: LensProfile, options: AlgorithmOptions) -> MaskGeometry:
    if options.mount_type is MountType.UNIVERSAL_SCREWS:
        raise NotImplementedError(
            "universal-screws mounting is planned but not implemented in V1"
        )
    return ALGORITHMS[options.mask_type].calculate(profile, options)
