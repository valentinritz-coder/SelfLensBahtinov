"""Strict nested JSON profile loading and local search."""

from __future__ import annotations
import json
from pathlib import Path
from typing import Any
from selflensbahtinov.models import (
    Aperture,
    FocalLength,
    LensProfile,
    Mounting,
    MountType,
    ProfileDefaults,
    RecommendedFocus,
    MaskType,
)


class ProfileValidationError(ValueError):
    pass


ROOT = {
    "schema_version",
    "manufacturer",
    "model",
    "slug",
    "focal_length",
    "aperture",
    "mounting",
    "recommended_focus",
    "defaults",
    "label",
    "notes",
}
NEST = {
    "focal_length": {"min_mm", "max_mm"},
    "aperture": {"min_f_number", "max_f_number"},
    "mounting": {
        "filter_thread_mm",
        "hood_outer_diameter_mm",
        "hood_inner_diameter_mm",
        "barrel_outer_diameter_mm",
        "recommended_mount",
    },
    "recommended_focus": {"focal_length_mm", "aperture_f_number"},
    "defaults": {
        "mask_type",
        "mount_type",
        "fit_clearance_mm",
        "mask_thickness_mm",
        "ring_depth_mm",
        "ring_wall_thickness_mm",
        "pattern_border_mm",
        "engrave_label",
    },
}


def _strict(d: dict[str, Any], allowed: set[str], name: str):
    missing = allowed - d.keys()
    extra = d.keys() - allowed
    if missing:
        raise ProfileValidationError(
            f"{name}: missing fields: {', '.join(sorted(missing))}"
        )
    if extra:
        raise ProfileValidationError(
            f"{name}: unknown fields: {', '.join(sorted(extra))}"
        )


def _num(v: Any, name: str, positive=True) -> float:
    if not isinstance(v, (int, float)) or isinstance(v, bool) or (positive and v <= 0):
        raise ProfileValidationError(f"{name} must be a positive number")
    return float(v)


def _enum(cls, v: Any, name: str):
    try:
        return cls(v)
    except Exception as e:
        raise ProfileValidationError(f"{name} has invalid value {v!r}") from e


def validate_profile_data(data: dict[str, Any], source: Path | None = None) -> None:
    p = f"{source}: " if source else ""
    _strict(data, ROOT, p + "profile")
    if data["schema_version"] != 1:
        raise ProfileValidationError(p + "schema_version must be 1")
    for f in ("manufacturer", "model", "slug", "label"):
        if not isinstance(data[f], str) or not data[f].strip():
            raise ProfileValidationError(p + f"{f} must be a non-empty string")
    if not isinstance(data["notes"], list) or not all(
        isinstance(n, str) for n in data["notes"]
    ):
        raise ProfileValidationError(p + "notes must be a list of strings")
    for k, a in NEST.items():
        if not isinstance(data[k], dict):
            raise ProfileValidationError(p + f"{k} must be an object")
        _strict(data[k], a, p + k)
    fl = data["focal_length"]
    ap = data["aperture"]
    rf = data["recommended_focus"]
    mt = data["mounting"]
    de = data["defaults"]
    fmin = _num(fl["min_mm"], p + "focal_length.min_mm")
    fmax = _num(fl["max_mm"], p + "focal_length.max_mm")
    if fmin > fmax:
        raise ProfileValidationError(p + "focal_length.min_mm must be <= max_mm")
    amin = _num(ap["min_f_number"], p + "aperture.min_f_number")
    amax = _num(ap["max_f_number"], p + "aperture.max_f_number")
    if amin > amax:
        raise ProfileValidationError(
            p + "aperture.min_f_number must be <= max_f_number"
        )
    rff = _num(rf["focal_length_mm"], p + "recommended_focus.focal_length_mm")
    rfa = _num(rf["aperture_f_number"], p + "recommended_focus.aperture_f_number")
    if not fmin <= rff <= fmax:
        raise ProfileValidationError(
            p + "recommended focal length outside profile range"
        )
    if not amin <= rfa <= amax:
        raise ProfileValidationError(p + "recommended aperture outside profile range")
    for k in (
        "filter_thread_mm",
        "hood_outer_diameter_mm",
        "hood_inner_diameter_mm",
        "barrel_outer_diameter_mm",
    ):
        if mt[k] is not None:
            _num(mt[k], p + "mounting." + k)
    _enum(MountType, mt["recommended_mount"], p + "mounting.recommended_mount")
    _enum(MaskType, de["mask_type"], p + "defaults.mask_type")
    mount = _enum(MountType, de["mount_type"], p + "defaults.mount_type")
    for k in (
        "fit_clearance_mm",
        "mask_thickness_mm",
        "ring_depth_mm",
        "ring_wall_thickness_mm",
        "pattern_border_mm",
    ):
        _num(de[k], p + "defaults." + k)
    if de["fit_clearance_mm"] > 3:
        raise ProfileValidationError(p + "fit clearance is physically implausible")
    if de["pattern_border_mm"] < de["ring_wall_thickness_mm"] / 2:
        raise ProfileValidationError(
            p + "pattern border must leave enough peripheral material"
        )
    if de["ring_wall_thickness_mm"] < 1:
        raise ProfileValidationError(p + "ring wall thickness must be at least 1 mm")
    if not isinstance(de["engrave_label"], bool):
        raise ProfileValidationError(p + "defaults.engrave_label must be boolean")
    recommended_mount = _enum(
        MountType, mt["recommended_mount"], p + "mounting.recommended_mount"
    )
    if (
        recommended_mount is MountType.HOOD_OUTER
        and mt["hood_outer_diameter_mm"] is None
    ):
        raise ProfileValidationError(
            p + "recommended hood_outer mount is missing hood_outer_diameter_mm"
        )
    if (
        recommended_mount is MountType.BARREL_OUTER
        and mt["barrel_outer_diameter_mm"] is None
    ):
        raise ProfileValidationError(
            p + "recommended barrel_outer mount is missing barrel_outer_diameter_mm"
        )
    if mount is MountType.HOOD_OUTER and mt["hood_outer_diameter_mm"] is None:
        raise ProfileValidationError(
            p + "hood_outer_diameter_mm is required for hood_outer mounting"
        )
    if mount is MountType.BARREL_OUTER and mt["barrel_outer_diameter_mm"] is None:
        raise ProfileValidationError(
            p + "barrel_outer_diameter_mm is required for barrel_outer mounting"
        )


def profile_from_dict(d: dict[str, Any]) -> LensProfile:
    return LensProfile(
        d["schema_version"],
        d["manufacturer"],
        d["model"],
        d["slug"],
        FocalLength(**d["focal_length"]),
        Aperture(**d["aperture"]),
        Mounting(
            d["mounting"]["filter_thread_mm"],
            d["mounting"]["hood_outer_diameter_mm"],
            d["mounting"]["hood_inner_diameter_mm"],
            d["mounting"]["barrel_outer_diameter_mm"],
            _enum(MountType, d["mounting"]["recommended_mount"], "recommended_mount"),
        ),
        RecommendedFocus(**d["recommended_focus"]),
        ProfileDefaults(
            _enum(MaskType, d["defaults"]["mask_type"], "mask_type"),
            _enum(MountType, d["defaults"]["mount_type"], "mount_type"),
            d["defaults"]["fit_clearance_mm"],
            d["defaults"]["mask_thickness_mm"],
            d["defaults"]["ring_depth_mm"],
            d["defaults"]["ring_wall_thickness_mm"],
            d["defaults"]["pattern_border_mm"],
            d["defaults"]["engrave_label"],
        ),
        d["label"],
        tuple(d["notes"]),
    )


def load_profile(path: Path) -> LensProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    validate_profile_data(raw, path)
    return profile_from_dict(raw)


def profile_dir() -> Path:
    return Path(__file__).resolve().parents[2] / "profiles"


def resolve_profile(value: str) -> Path:
    p = Path(value)
    return p if p.exists() else profile_dir() / f"{value}.json"


def search_profiles(
    term: str = "", profiles_dir: Path | None = None
) -> list[LensProfile]:
    res = []
    for p in sorted((profiles_dir or profile_dir()).glob("*.json")):
        prof = load_profile(p)
        hay = " ".join([prof.manufacturer, prof.model, prof.slug, prof.label]).lower()
        if term.lower() in hay:
            res.append(prof)
    return res
