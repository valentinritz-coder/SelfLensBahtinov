"""Strict nested JSON profile loading and local search."""

from __future__ import annotations
import json
import math
import warnings
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


CURRENT_SCHEMA_VERSION = 2

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
        "filter_thread_nominal_mm",
        "lens_barrel_outer_mm",
        "lens_barrel_outer_status",
        "hood_outer_mm",
        "hood_outer_status",
        "hood_inner_mm",
        "hood_inner_status",
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
        "lead_in_chamfer_mm",
        "outer_edge_radius_mm",
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
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        raise ProfileValidationError(f"{name} must be a positive finite number")
    value = float(v)
    if not math.isfinite(value) or (positive and value <= 0):
        raise ProfileValidationError(f"{name} must be a positive finite number")
    return value


def _enum(cls, v: Any, name: str):
    try:
        return cls(v)
    except Exception as e:
        raise ProfileValidationError(f"{name} has invalid value {v!r}") from e


def _nullable_enum(cls, v: Any, name: str):
    return None if v is None else _enum(cls, v, name)


def migrate_profile_data(data: dict[str, Any], source: Path | None = None) -> dict[str, Any]:
    version = data.get("schema_version")
    p = f"{source}: " if source else ""
    if version == CURRENT_SCHEMA_VERSION:
        if "defaults" in data:
            data = {**data, "defaults": {"lead_in_chamfer_mm": 1.0, "outer_edge_radius_mm": 0.5, **data["defaults"]}}
        return data
    if version != 1:
        raise ProfileValidationError(
            p + f"unsupported schema_version {version!r}; expected 1 or {CURRENT_SCHEMA_VERSION}"
        )
    warnings.warn(
        p + "migrating deprecated profile schema version 1 to version 2",
        DeprecationWarning,
        stacklevel=2,
    )
    old_mounting = data["mounting"]
    old_defaults = data["defaults"]

    def old_value(name: str) -> Any:
        return old_mounting.get(name)

    def migrated_status(value: Any) -> str:
        return "unknown" if value is None else "estimated"

    migrated = {**data, "schema_version": CURRENT_SCHEMA_VERSION}
    migrated["mounting"] = {
        "filter_thread_nominal_mm": old_value("filter_thread_mm"),
        "lens_barrel_outer_mm": old_value("barrel_outer_diameter_mm"),
        "lens_barrel_outer_status": migrated_status(old_value("barrel_outer_diameter_mm")),
        "hood_outer_mm": old_value("hood_outer_diameter_mm"),
        "hood_outer_status": migrated_status(old_value("hood_outer_diameter_mm")),
        "hood_inner_mm": old_value("hood_inner_diameter_mm"),
        "hood_inner_status": migrated_status(old_value("hood_inner_diameter_mm")),
        "recommended_mount": None,
    }
    migrated["defaults"] = {**old_defaults, "mount_type": None, "lead_in_chamfer_mm": 1.0, "outer_edge_radius_mm": 0.5}
    return migrated


def validate_profile_data(data: dict[str, Any], source: Path | None = None) -> None:
    data = migrate_profile_data(data, source)
    p = f"{source}: " if source else ""
    _strict(data, ROOT, p + "profile")
    if data["schema_version"] != CURRENT_SCHEMA_VERSION:
        raise ProfileValidationError(p + f"schema_version must be {CURRENT_SCHEMA_VERSION}")
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
        "filter_thread_nominal_mm",
        "lens_barrel_outer_mm",
        "hood_outer_mm",
        "hood_inner_mm",
    ):
        if mt[k] is not None:
            _num(mt[k], p + "mounting." + k)
    statuses = {"unknown", "estimated", "measured", "verified"}
    for field in ("lens_barrel_outer", "hood_outer", "hood_inner"):
        diameter = mt[f"{field}_mm"]
        status = mt[f"{field}_status"]
        if status not in statuses:
            raise ProfileValidationError(p + f"mounting.{field}_status has invalid value {status!r}")
        if diameter is None and status != "unknown":
            raise ProfileValidationError(p + f"mounting.{field}_mm is null so mounting.{field}_status must be 'unknown'")
        if diameter is not None and status == "unknown":
            raise ProfileValidationError(p + f"mounting.{field}_mm is set so mounting.{field}_status must be estimated, measured, or verified")
    recommended = _nullable_enum(MountType, mt["recommended_mount"], p + "mounting.recommended_mount")
    _enum(MaskType, de["mask_type"], p + "defaults.mask_type")
    default_mount = _nullable_enum(MountType, de["mount_type"], p + "defaults.mount_type")
    for k in (
        "fit_clearance_mm",
        "mask_thickness_mm",
        "ring_depth_mm",
        "ring_wall_thickness_mm",
        "pattern_border_mm",
    ):
        _num(de[k], p + "defaults." + k)
    for k in ("lead_in_chamfer_mm", "outer_edge_radius_mm"):
        _num(de[k], p + "defaults." + k, positive=False)
        if de[k] < 0:
            raise ProfileValidationError(p + f"defaults.{k} must be greater than or equal to zero")
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

    def require_measured_mount(mount: MountType | None, label: str) -> None:
        if mount is None:
            return
        field = {
            MountType.LENS_BARREL_OUTER_SLIP_FIT: "lens_barrel_outer",
            MountType.HOOD_OUTER_SLIP_FIT: "hood_outer",
            MountType.HOOD_INNER_SLIP_FIT: "hood_inner",
        }[mount]
        diameter_field = f"{field}_mm"
        status_field = f"{field}_status"
        if mt[diameter_field] is None:
            raise ProfileValidationError(
                p + f"{label} {mount.value} requires mounting.{diameter_field}"
            )
        if mt[status_field] not in {"measured", "verified"}:
            raise ProfileValidationError(
                p + f"{label} {mount.value} requires mounting.{status_field} to be measured or verified"
            )

    require_measured_mount(recommended, "recommended_mount")
    require_measured_mount(default_mount, "defaults.mount_type")


def profile_from_dict(d: dict[str, Any]) -> LensProfile:
    d = migrate_profile_data(d)
    return LensProfile(
        d["schema_version"],
        d["manufacturer"],
        d["model"],
        d["slug"],
        FocalLength(**d["focal_length"]),
        Aperture(**d["aperture"]),
        Mounting(
            d["mounting"]["filter_thread_nominal_mm"],
            d["mounting"]["lens_barrel_outer_mm"],
            d["mounting"]["lens_barrel_outer_status"],
            d["mounting"]["hood_outer_mm"],
            d["mounting"]["hood_outer_status"],
            d["mounting"]["hood_inner_mm"],
            d["mounting"]["hood_inner_status"],
            _nullable_enum(MountType, d["mounting"]["recommended_mount"], "recommended_mount"),
        ),
        RecommendedFocus(**d["recommended_focus"]),
        ProfileDefaults(
            _enum(MaskType, d["defaults"]["mask_type"], "mask_type"),
            _nullable_enum(MountType, d["defaults"]["mount_type"], "mount_type"),
            d["defaults"]["fit_clearance_mm"],
            d["defaults"]["mask_thickness_mm"],
            d["defaults"]["ring_depth_mm"],
            d["defaults"]["ring_wall_thickness_mm"],
            d["defaults"]["pattern_border_mm"],
            d["defaults"]["engrave_label"],
            d["defaults"]["lead_in_chamfer_mm"],
            d["defaults"]["outer_edge_radius_mm"],
        ),
        d["label"],
        tuple(d["notes"]),
    )


def load_profile(path: Path) -> LensProfile:
    raw = json.loads(path.read_text(encoding="utf-8"))
    data = migrate_profile_data(raw, path)
    validate_profile_data(data, path)
    return profile_from_dict(data)


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
