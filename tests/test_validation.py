from __future__ import annotations

import pytest

from selflensbahtinov.validation import ProfileValidationError, validate_profile_data


def valid_profile() -> dict[str, object]:
    return {
        "manufacturer": "Fujifilm",
        "model": "Example",
        "slug": "example",
        "filter_thread_mm": 72.0,
        "focal_length_min_mm": 16.0,
        "focal_length_max_mm": 80.0,
        "aperture_min": 4.0,
        "aperture_max": 4.0,
        "hood_outer_diameter_mm": None,
        "barrel_outer_diameter_mm": None,
        "mount_type": "filter_thread",
        "fit_clearance_mm": 0.35,
        "mask_thickness_mm": 2.0,
        "ring_depth_mm": 8.0,
        "label": "Example",
        "notes": "TODO: Measure hood and barrel diameters.",
    }


def test_missing_field_has_clear_error() -> None:
    data = valid_profile()
    del data["label"]
    with pytest.raises(ProfileValidationError, match="missing required fields: label"):
        validate_profile_data(data)


def test_hood_mount_requires_hood_diameter() -> None:
    data = valid_profile()
    data["mount_type"] = "hood_outer"
    with pytest.raises(ProfileValidationError, match="hood_outer_diameter_mm is required"):
        validate_profile_data(data)


def test_negative_numbers_are_rejected() -> None:
    data = valid_profile()
    data["fit_clearance_mm"] = -0.1
    with pytest.raises(ProfileValidationError, match="fit_clearance_mm must be a positive number"):
        validate_profile_data(data)
