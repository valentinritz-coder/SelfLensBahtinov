"""Profile loading and validation helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from selflensbahtinov.models import LensProfile, MountType

REQUIRED_FIELDS: tuple[str, ...] = (
    "manufacturer",
    "model",
    "slug",
    "filter_thread_mm",
    "focal_length_min_mm",
    "focal_length_max_mm",
    "aperture_min",
    "aperture_max",
    "hood_outer_diameter_mm",
    "barrel_outer_diameter_mm",
    "mount_type",
    "fit_clearance_mm",
    "mask_thickness_mm",
    "ring_depth_mm",
    "label",
    "notes",
)
MOUNT_TYPES: set[MountType] = {"filter_thread", "hood_outer", "barrel_outer"}


class ProfileValidationError(ValueError):
    """Raised when a lens profile is missing or physically invalid."""


def load_profile(path: Path) -> LensProfile:
    """Load and validate a lens profile JSON file."""
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileValidationError(f"{path}: invalid JSON: {exc.msg}") from exc
    if not isinstance(raw, dict):
        raise ProfileValidationError(f"{path}: profile root must be a JSON object")
    validate_profile_data(raw, source=path)
    return LensProfile.from_dict(raw)


def validate_profile_data(data: dict[str, Any], source: Path | None = None) -> None:
    """Validate decoded profile data with clear field-level errors."""
    prefix = f"{source}: " if source else ""
    missing = [field for field in REQUIRED_FIELDS if field not in data]
    if missing:
        raise ProfileValidationError(f"{prefix}missing required fields: {', '.join(missing)}")

    for field in ("manufacturer", "model", "slug", "label", "notes"):
        if not isinstance(data[field], str) or not data[field].strip():
            raise ProfileValidationError(f"{prefix}{field} must be a non-empty string")

    mount_type = data["mount_type"]
    if mount_type not in MOUNT_TYPES:
        raise ProfileValidationError(
            f"{prefix}mount_type must be one of {sorted(MOUNT_TYPES)}, got {mount_type!r}"
        )

    positive_fields = (
        "filter_thread_mm",
        "focal_length_min_mm",
        "focal_length_max_mm",
        "aperture_min",
        "aperture_max",
        "fit_clearance_mm",
        "mask_thickness_mm",
        "ring_depth_mm",
    )
    for field in positive_fields:
        if not isinstance(data[field], int | float) or data[field] <= 0:
            raise ProfileValidationError(f"{prefix}{field} must be a positive number")

    for field in ("hood_outer_diameter_mm", "barrel_outer_diameter_mm"):
        value = data[field]
        if value is not None and (not isinstance(value, int | float) or value <= 0):
            raise ProfileValidationError(f"{prefix}{field} must be null or a positive number")

    if data["focal_length_min_mm"] > data["focal_length_max_mm"]:
        raise ProfileValidationError(f"{prefix}focal_length_min_mm must be <= focal_length_max_mm")
    if data["aperture_min"] > data["aperture_max"]:
        raise ProfileValidationError(f"{prefix}aperture_min must be <= aperture_max")
    if mount_type == "hood_outer" and data["hood_outer_diameter_mm"] is None:
        raise ProfileValidationError(f"{prefix}hood_outer_diameter_mm is required for hood_outer mounting")
    if mount_type == "barrel_outer" and data["barrel_outer_diameter_mm"] is None:
        raise ProfileValidationError(f"{prefix}barrel_outer_diameter_mm is required for barrel_outer mounting")
