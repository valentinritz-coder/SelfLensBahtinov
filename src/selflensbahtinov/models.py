"""Small typed domain model for V1 mask generation."""

from __future__ import annotations
from dataclasses import dataclass
from enum import Enum
from pathlib import Path


class MaskType(str, Enum):
    BAHTINOV = "bahtinov"
    TRIBAHTINOV = "tribahtinov"


class MountType(str, Enum):
    FILTER_DIAMETER_SLIP_FIT = "filter_thread"
    HOOD_OUTER = "hood_outer"
    BARREL_OUTER = "barrel_outer"
    UNIVERSAL_SCREWS = "universal_screws"


class OutputFormat(str, Enum):
    SCAD = "scad"
    STL = "stl"
    THREEMF = "3mf"


@dataclass(frozen=True)
class FocalLength:
    min_mm: float
    max_mm: float


@dataclass(frozen=True)
class Aperture:
    min_f_number: float
    max_f_number: float


@dataclass(frozen=True)
class Mounting:
    filter_thread_mm: float | None
    hood_outer_diameter_mm: float | None
    hood_inner_diameter_mm: float | None
    barrel_outer_diameter_mm: float | None
    recommended_mount: MountType


@dataclass(frozen=True)
class RecommendedFocus:
    focal_length_mm: float
    aperture_f_number: float


@dataclass(frozen=True)
class ProfileDefaults:
    mask_type: MaskType
    mount_type: MountType
    fit_clearance_mm: float
    mask_thickness_mm: float
    ring_depth_mm: float
    ring_wall_thickness_mm: float
    pattern_border_mm: float
    engrave_label: bool


@dataclass(frozen=True)
class LensProfile:
    schema_version: int
    manufacturer: str
    model: str
    slug: str
    focal_length: FocalLength
    aperture: Aperture
    mounting: Mounting
    recommended_focus: RecommendedFocus
    defaults: ProfileDefaults
    label: str
    notes: tuple[str, ...]

    def mount_diameter_mm(self, mount: MountType) -> float:
        if mount is MountType.UNIVERSAL_SCREWS:
            raise NotImplementedError(
                "universal-screws mounting is planned but not implemented in V1"
            )
        value = {
            MountType.FILTER_DIAMETER_SLIP_FIT: self.mounting.filter_thread_mm,
            MountType.HOOD_OUTER: self.mounting.hood_outer_diameter_mm,
            MountType.BARREL_OUTER: self.mounting.barrel_outer_diameter_mm,
        }[mount]
        if value is None:
            raise ValueError(
                f"{mount.value} requires a measured diameter in the profile"
            )
        return value


@dataclass(frozen=True)
class Point2D:
    x: float
    y: float


@dataclass(frozen=True)
class SlotGeometry:
    center: Point2D
    length_mm: float
    width_mm: float
    angle_deg: float
    sector_start_deg: float | None = None
    sector_end_deg: float | None = None


@dataclass(frozen=True)
class RingGeometry:
    mount_type: MountType
    mount_diameter_mm: float
    inner_diameter_mm: float
    outer_diameter_mm: float
    wall_thickness_mm: float
    depth_mm: float
    clearance_mm: float


@dataclass(frozen=True)
class LabelGeometry:
    text: str
    position: Point2D
    size_mm: float
    angle_deg: float


@dataclass(frozen=True)
class GratingMetadata:
    base_pitch_mm: float
    effective_pitch_mm: float
    open_slot_width_mm: float
    opaque_bar_width_mm: float
    open_fraction: float
    density: float
    reference_wavelength_nm: float
    first_order_angle_rad: float
    first_order_sensor_offset_mm: float
    pitch_selection_source: str


@dataclass(frozen=True)
class MaskGeometry:
    profile_slug: str
    mask_type: MaskType
    clear_aperture_mm: float
    slot_width_mm: float
    slot_spacing_mm: float
    slots: tuple[SlotGeometry, ...]
    ring: RingGeometry
    thickness_mm: float
    pattern_border_mm: float
    label: LabelGeometry | None
    grating: GratingMetadata | None
    test_ring: bool = False


@dataclass(frozen=True, kw_only=True)
class GenerationRequest:
    profile: LensProfile
    mask_type: MaskType
    mount_type: MountType
    formats: tuple[OutputFormat, ...]
    focal_length_mm: float
    aperture_f_number: float
    clearance_mm: float
    pattern_border_mm: float
    label: bool
    slot_width_mm: float | None
    slot_spacing_mm: float | None
    slot_density: float
    output_dir: Path
    openscad: str
    dry_run: bool = False
