"""Typed models for lens mask generation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

MountType = Literal["filter_thread", "hood_outer", "barrel_outer"]


@dataclass(frozen=True)
class LensProfile:
    """Physical and generation settings for one camera lens."""

    manufacturer: str
    model: str
    slug: str
    filter_thread_mm: float
    focal_length_min_mm: float
    focal_length_max_mm: float
    aperture_min: float
    aperture_max: float
    hood_outer_diameter_mm: float | None
    barrel_outer_diameter_mm: float | None
    mount_type: MountType
    fit_clearance_mm: float
    mask_thickness_mm: float
    ring_depth_mm: float
    label: str
    notes: str

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "LensProfile":
        """Create a profile from decoded JSON data."""
        return cls(**data)

    @property
    def mount_diameter_mm(self) -> float:
        """Return the selected physical mounting diameter before clearance."""
        if self.mount_type == "filter_thread":
            return self.filter_thread_mm
        if self.mount_type == "hood_outer":
            if self.hood_outer_diameter_mm is None:
                raise ValueError("hood_outer_diameter_mm is required for hood_outer mounting")
            return self.hood_outer_diameter_mm
        if self.barrel_outer_diameter_mm is None:
            raise ValueError("barrel_outer_diameter_mm is required for barrel_outer mounting")
        return self.barrel_outer_diameter_mm

    @property
    def inner_diameter_mm(self) -> float:
        """Return the generated ring inner diameter including fit clearance."""
        return self.mount_diameter_mm + self.fit_clearance_mm


@dataclass(frozen=True)
class GenerationOptions:
    """Options controlling generated output."""

    profile_path: Path
    output_path: Path
    test_ring: bool = False
    engrave_label: bool = True
    dry_run: bool = False
    openscad_executable: str = "openscad"
