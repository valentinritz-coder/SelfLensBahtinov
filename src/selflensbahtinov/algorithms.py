"""Python-owned optical mask pattern calculations for V1."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
import math
from collections.abc import Iterable

from selflensbahtinov.models import (
    GratingMetadata,
    GratingRegion,
    LabelGeometry,
    LensProfile,
    MaskGeometry,
    MaskType,
    MountType,
    Point2D,
    RingGeometry,
    SlotGeometry,
)

BAHTINOV_GRATING_ANGLE_DEG = 60.0
DEFAULT_OPEN_FRACTION = 0.45
MIN_PRINTABLE_SLOT_WIDTH_MM = 0.8
MAX_PRACTICAL_SLOT_WIDTH_MM = 2.2
MIN_OPAQUE_BAR_WIDTH_MM = 0.8
MIN_EFFECTIVE_PITCH_MM = 1.6
MAX_PRACTICAL_SLOT_COUNT = 1000
REFERENCE_WAVELENGTH_NM = 550.0
TARGET_SPIKE_OFFSET_AT_SENSOR_MM = 0.060
DEFAULT_REGION_GAP_MM = 2.0


@dataclass(frozen=True, kw_only=True)
class AlgorithmOptions:
    mask_type: MaskType
    mount_type: MountType
    focal_length_mm: float
    aperture_f_number: float
    clearance_mm: float
    pattern_border_mm: float
    region_gap_mm: float = DEFAULT_REGION_GAP_MM
    label: bool = True
    test_ring: bool = False
    slot_width_mm: float | None = None
    slot_spacing_mm: float | None = None
    slot_density: float = 1.0

    def __post_init__(self) -> None:
        if not isinstance(self.mount_type, MountType):
            raise TypeError("AlgorithmOptions.mount_type must be a concrete MountType")


@dataclass(frozen=True)
class GratingModel:
    """Transmission-grating parameters used to lay out one aperture region."""

    base_pitch_mm: float
    pitch_mm: float
    open_width_mm: float
    bar_width_mm: float
    open_fraction: float
    density: float
    reference_wavelength_nm: float
    first_order_angle_rad: float
    first_order_sensor_offset_mm: float
    pitch_selection_source: str


class MaskAlgorithm(ABC):
    @abstractmethod
    def calculate(
        self, profile: LensProfile, options: AlgorithmOptions
    ) -> MaskGeometry:
        """Calculate all V1 mask geometry before rendering."""


def _ring(profile: LensProfile, options: AlgorithmOptions) -> RingGeometry:
    mount_diameter, mount_status = profile.mount_measurement(options.mount_type)
    if mount_status == "unknown":
        raise ValueError(f"{options.mount_type.value} has unknown measurement status")
    if mount_status == "estimated" and not options.test_ring:
        raise ValueError(
            f"{options.mount_type.value} has estimated measurement status; "
            "estimated mounts may generate test rings only"
        )
    wall = profile.defaults.ring_wall_thickness_mm
    if options.mount_type is MountType.HOOD_INNER_SLIP_FIT:
        # Hood-inner slip fit inserts into a hood opening, so radial clearance
        # reduces the printable outside diameter of the skirt.
        outer_diameter = mount_diameter - 2 * options.clearance_mm
        inner_diameter = outer_diameter - 2 * wall
    else:
        # Lens-barrel and hood-outer slip fits slide over an outside surface.
        inner_diameter = mount_diameter + 2 * options.clearance_mm
        outer_diameter = inner_diameter + 2 * wall
    depth = (
        min(profile.defaults.ring_depth_mm, 4.0)
        if options.test_ring
        else profile.defaults.ring_depth_mm
    )
    for name, value in (
        ("mount_diameter_mm", mount_diameter),
        ("clearance_mm", options.clearance_mm),
        ("ring_wall_thickness_mm", wall),
        ("ring_depth_mm", depth),
        ("ring_inner_diameter_mm", inner_diameter),
        ("ring_outer_diameter_mm", outer_diameter),
        ("pattern_border_mm", options.pattern_border_mm),
    ):
        _validate_finite(name, value)
    if mount_diameter <= 0:
        raise ValueError("mount diameter must be greater than zero")
    if options.clearance_mm < 0:
        raise ValueError("clearance_mm must be greater than or equal to zero")
    if options.pattern_border_mm < 0:
        raise ValueError("pattern_border_mm must be greater than or equal to zero")
    if wall <= 0 or depth <= 0:
        raise ValueError("ring dimensions must be greater than zero")
    if inner_diameter <= 0 or outer_diameter <= inner_diameter:
        raise ValueError("ring diameters must be valid positive dimensions")
    return RingGeometry(
        mount_type=options.mount_type,
        mount_diameter_mm=mount_diameter,
        inner_diameter_mm=inner_diameter,
        outer_diameter_mm=outer_diameter,
        wall_thickness_mm=wall,
        depth_mm=depth,
        clearance_mm=options.clearance_mm,
    )


def _validate_finite(name: str, value: float | None) -> None:
    if value is not None and not math.isfinite(value):
        raise ValueError(f"{name} must be finite")


def _validate_positive(name: str, value: float | None) -> None:
    _validate_finite(name, value)
    if value is not None and value <= 0:
        raise ValueError(f"{name} must be greater than zero")


def _grating_model(clear_aperture_mm: float, options: AlgorithmOptions) -> GratingModel:
    """Build a first-order Fraunhofer grating model for a Bahtinov sector.

    A Bahtinov mask is three rectangular transmission gratings. For a slot pitch
    ``p`` and wavelength ``lambda``, first-order diffraction leaves the optical
    axis at ``sin(theta)=lambda/p``. The side gratings rotate that spike normal by
    +/-60 degrees, so focus is read from the central spike crossing the two side
    spikes. Lens focal length maps angular separation to sensor-plane separation;
    f-number is used only to choose a practical default pitch for the requested
    focal setup when the user does not override the physical slot dimensions.
    """

    for name, value in (
        ("focal_length_mm", options.focal_length_mm),
        ("aperture_f_number", options.aperture_f_number),
    ):
        _validate_positive(name, value)
    _validate_positive("slot_width_mm", options.slot_width_mm)
    _validate_positive("slot_spacing_mm", options.slot_spacing_mm)
    _validate_positive("slot_density", options.slot_density)
    if options.slot_density <= 0:
        raise ValueError("slot_density must be greater than zero")

    pitch_selection_source = "explicit"
    if options.slot_spacing_mm is not None:
        pitch = options.slot_spacing_mm
    else:
        wavelength_mm = REFERENCE_WAVELENGTH_NM * 1e-6
        target_offset = TARGET_SPIKE_OFFSET_AT_SENSOR_MM * options.aperture_f_number / 5.6
        target_angle = max(target_offset / options.focal_length_mm, 1e-6)
        diffraction_pitch = wavelength_mm / math.sin(target_angle)
        aperture_min_pitch = clear_aperture_mm / 16.0
        aperture_max_pitch = clear_aperture_mm / 7.0
        if diffraction_pitch < aperture_min_pitch:
            pitch = aperture_min_pitch
            pitch_selection_source = "aperture_minimum_clamp"
        elif diffraction_pitch > aperture_max_pitch:
            pitch = aperture_max_pitch
            pitch_selection_source = "aperture_maximum_clamp"
        else:
            pitch = diffraction_pitch
            pitch_selection_source = "optical_target"
    base_pitch = round(pitch, 4)
    pitch = base_pitch / options.slot_density

    if options.slot_width_mm is not None:
        width = options.slot_width_mm
    else:
        width = max(
            MIN_PRINTABLE_SLOT_WIDTH_MM,
            min(MAX_PRACTICAL_SLOT_WIDTH_MM, pitch * DEFAULT_OPEN_FRACTION),
        )
    pitch = round(pitch, 4)
    width = round(width, 4)
    bar_width = round(pitch - width, 4)
    if width >= pitch:
        raise ValueError(
            "slot_width_mm must be smaller than slot_spacing_mm / slot_density"
        )
    if pitch < MIN_EFFECTIVE_PITCH_MM:
        raise ValueError("effective slot pitch is below the printable minimum")
    if width < MIN_PRINTABLE_SLOT_WIDTH_MM:
        raise ValueError("slot_width_mm is below the printable minimum")
    if bar_width < MIN_OPAQUE_BAR_WIDTH_MM:
        raise ValueError("opaque bar width is below the printable minimum")

    wavelength_mm = REFERENCE_WAVELENGTH_NM * 1e-6
    theta = math.asin(min(1.0, wavelength_mm / pitch))
    return GratingModel(
        base_pitch_mm=base_pitch,
        pitch_mm=pitch,
        open_width_mm=width,
        bar_width_mm=bar_width,
        open_fraction=round(width / pitch, 4),
        density=round(options.slot_density, 4),
        reference_wavelength_nm=REFERENCE_WAVELENGTH_NM,
        first_order_angle_rad=theta,
        first_order_sensor_offset_mm=round(math.tan(theta) * options.focal_length_mm, 6),
        pitch_selection_source=pitch_selection_source,
    )


def _validate_region_gap(clear_aperture_mm: float, region_gap_mm: float) -> float:
    _validate_finite("region_gap_mm", region_gap_mm)
    gap = round(region_gap_mm, 4)
    if gap < 0:
        raise ValueError("region_gap_mm must be greater than or equal to zero")
    if 0 < gap < MIN_OPAQUE_BAR_WIDTH_MM:
        raise ValueError("region_gap_mm is below the printable minimum")
    radius = clear_aperture_mm / 2
    if gap >= radius * math.sqrt(2):
        raise ValueError("region_gap_mm leaves no usable area in every region")
    return gap


def _grating_slots(
    clear_aperture_mm: float,
    model: GratingModel,
    regions: Iterable[tuple[GratingRegion, float]],
) -> tuple[SlotGeometry, ...]:
    radius = clear_aperture_mm / 2
    length = clear_aperture_mm + 2 * model.pitch_mm
    slots: list[SlotGeometry] = []
    for region, slot_angle in regions:
        normal_angle = math.radians(slot_angle + 90)
        count = math.ceil((radius + model.open_width_mm / 2) / model.pitch_mm)
        if count * 2 + 1 > MAX_PRACTICAL_SLOT_COUNT:
            raise ValueError("slot count exceeds the practical manufacturing maximum")
        region_count = 0
        for index in range(-count, count + 1):
            offset = index * model.pitch_mm
            if abs(offset) > radius + model.open_width_mm / 2:
                continue
            region_count += 1
            slots.append(
                SlotGeometry(
                    center=Point2D(
                        round(math.cos(normal_angle) * offset, 4),
                        round(math.sin(normal_angle) * offset, 4),
                    ),
                    length_mm=round(length, 4),
                    width_mm=model.open_width_mm,
                    angle_deg=slot_angle,
                    region=region,
                )
            )
        if region_count == 0:
            raise ValueError("each assigned grating region must contain a candidate slot")
    if len({s for s in slots}) != len(slots):
        raise ValueError("duplicate slots generated for grating regions")
    return tuple(slots)


def _base(
    profile: LensProfile,
    options: AlgorithmOptions,
    mask_type: MaskType,
    regions: tuple[tuple[GratingRegion, float], ...],
) -> MaskGeometry:
    ring = _ring(profile, options)
    clear_aperture = ring.inner_diameter_mm - 2 * options.pattern_border_mm
    if clear_aperture <= 0:
        raise ValueError("pattern_border_mm leaves no usable clear aperture")
    if clear_aperture > ring.inner_diameter_mm:
        raise ValueError("clear aperture cannot exceed ring inner diameter")
    if options.test_ring:
        model = None
        metadata = None
        slots = ()
        region_gap = 0.0
    else:
        region_gap = (
            _validate_region_gap(clear_aperture, options.region_gap_mm)
            if mask_type is MaskType.BAHTINOV
            else 0.0
        )
        model = _grating_model(clear_aperture, options)
        metadata = GratingMetadata(
            base_pitch_mm=model.base_pitch_mm,
            effective_pitch_mm=model.pitch_mm,
            open_slot_width_mm=model.open_width_mm,
            opaque_bar_width_mm=model.bar_width_mm,
            open_fraction=model.open_fraction,
            density=model.density,
            reference_wavelength_nm=model.reference_wavelength_nm,
            first_order_angle_rad=model.first_order_angle_rad,
            first_order_sensor_offset_mm=model.first_order_sensor_offset_mm,
            pitch_selection_source=model.pitch_selection_source,
        )
        slots = _grating_slots(clear_aperture, model, regions)
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
        slot_width_mm=0.0 if model is None else model.open_width_mm,
        slot_spacing_mm=0.0 if model is None else model.pitch_mm,
        slots=slots,
        ring=ring,
        thickness_mm=profile.defaults.mask_thickness_mm,
        pattern_border_mm=options.pattern_border_mm,
        label=label,
        grating=metadata,
        region_gap_mm=region_gap,
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
            (
                (GratingRegion.LEFT_REFERENCE, 0),
                (GratingRegion.RIGHT_UPPER, BAHTINOV_GRATING_ANGLE_DEG),
                (GratingRegion.RIGHT_LOWER, -BAHTINOV_GRATING_ANGLE_DEG),
            ),
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
                (GratingRegion.TRIBAHTINOV_0, 0),
                (GratingRegion.TRIBAHTINOV_1, 90),
                (GratingRegion.TRIBAHTINOV_2, 60),
                (GratingRegion.TRIBAHTINOV_3, 150),
                (GratingRegion.TRIBAHTINOV_4, -60),
                (GratingRegion.TRIBAHTINOV_5, 30),
            ),
        )


ALGORITHMS = {
    MaskType.BAHTINOV: BahtinovMaskAlgorithm(),
    MaskType.TRIBAHTINOV: TriBahtinovMaskAlgorithm(),
}


def calculate_mask(profile: LensProfile, options: AlgorithmOptions) -> MaskGeometry:
    return ALGORITHMS[options.mask_type].calculate(profile, options)
