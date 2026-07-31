"""Schema-v3 mechanical profiles and independent print presets.

A profile describes only the physical object on which the mask mounts. Optical
values belong to the scientific report; printer-dependent choices belong to a
print preset. Schema versions 1 and 2 are deliberately not migrated or accepted.
"""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, fields
import json
import math
from pathlib import Path
import re
from typing import Any


MECHANICAL_PROFILE_SCHEMA_VERSION = 3
PRINT_PRESET_SCHEMA_VERSION = 1
_MEASUREMENT_STATUSES = {"estimated", "measured", "verified"}
_MOUNT_TYPES = {"outer-slip-fit", "inner-slip-fit"}


class ProfileValidationError(ValueError):
    """Raised when a mechanical profile or print preset is invalid."""


def _positive_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileValidationError(f"{name} must be a positive finite number")
    if not math.isfinite(float(value)) or float(value) <= 0:
        raise ProfileValidationError(f"{name} must be a positive finite number")


def _non_negative_finite(name: str, value: float) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ProfileValidationError(
            f"{name} must be a non-negative finite number"
        )
    if not math.isfinite(float(value)) or float(value) < 0:
        raise ProfileValidationError(
            f"{name} must be a non-negative finite number"
        )


def _non_empty_string(name: str, value: Any) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProfileValidationError(f"{name} must be a non-empty string")
    return value.strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ProfileValidationError(
            "slug source must contain at least one letter or digit"
        )
    return slug


def _strict_dataclass_kwargs(cls: type, payload: dict[str, Any]) -> dict[str, Any]:
    expected = {field.name for field in fields(cls)}
    actual = set(payload)
    unknown = actual - expected
    missing = {
        field.name
        for field in fields(cls)
        if field.default is MISSING
        and field.default_factory is MISSING
        and field.name not in payload
    }
    if unknown:
        raise ProfileValidationError(
            f"unknown fields for {cls.__name__}: {sorted(unknown)}"
        )
    if missing:
        raise ProfileValidationError(
            f"missing fields for {cls.__name__}: {sorted(missing)}"
        )
    return payload


@dataclass(frozen=True)
class MechanicalMount:
    name: str
    type: str
    diameter_mm: float
    usable_depth_mm: float
    status: str
    preferred: bool = False

    def validate(self) -> None:
        _non_empty_string("mount name", self.name)
        if self.type not in _MOUNT_TYPES:
            raise ProfileValidationError(
                "mount type must be outer-slip-fit or inner-slip-fit"
            )
        _positive_finite("diameter_mm", self.diameter_mm)
        _positive_finite("usable_depth_mm", self.usable_depth_mm)
        if self.status not in _MEASUREMENT_STATUSES:
            raise ProfileValidationError(
                "mount status must be estimated, measured, or verified"
            )
        if not isinstance(self.preferred, bool):
            raise ProfileValidationError("mount preferred must be a boolean")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MechanicalMount":
        if not isinstance(payload, dict):
            raise ProfileValidationError("each mount must be a JSON object")
        mount = cls(**_strict_dataclass_kwargs(cls, dict(payload)))
        mount.validate()
        return mount


@dataclass(frozen=True)
class MechanicalProfile:
    schema_version: int
    manufacturer: str
    model: str
    slug: str
    label: str
    mounts: tuple[MechanicalMount, ...]

    def validate(self) -> None:
        if self.schema_version != MECHANICAL_PROFILE_SCHEMA_VERSION:
            raise ProfileValidationError(
                "mechanical profile schema_version must be 3; "
                "schema versions 1 and 2 are no longer supported"
            )
        _non_empty_string("mechanical profile manufacturer", self.manufacturer)
        _non_empty_string("mechanical profile model", self.model)
        _non_empty_string("mechanical profile slug", self.slug)
        _non_empty_string("mechanical profile label", self.label)
        if self.slug != slugify(self.slug):
            raise ProfileValidationError(
                "mechanical profile slug must already be URL/file safe"
            )

        names: set[str] = set()
        preferred = 0
        for mount in self.mounts:
            mount.validate()
            if mount.name in names:
                raise ProfileValidationError(
                    f"duplicate mechanical mount name: {mount.name}"
                )
            names.add(mount.name)
            preferred += int(mount.preferred)
        if preferred > 1:
            raise ProfileValidationError(
                "only one mechanical mount may be preferred"
            )

    @property
    def is_complete(self) -> bool:
        return bool(self.mounts)

    def select_mount(self, name: str | None = None) -> MechanicalMount:
        self.validate()
        if not self.mounts:
            raise ProfileValidationError(
                "mechanical profile contains no measured mounting surface; "
                "measure a diameter and usable depth before assembly"
            )
        if name:
            for mount in self.mounts:
                if mount.name == name:
                    return mount
            raise ProfileValidationError(f"mechanical mount not found: {name}")
        preferred = [mount for mount in self.mounts if mount.preferred]
        if len(preferred) == 1:
            return preferred[0]
        if len(self.mounts) == 1:
            return self.mounts[0]
        raise ProfileValidationError(
            "select --mount-name because the profile has no unique preferred mount"
        )

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MechanicalProfile":
        if not isinstance(payload, dict):
            raise ProfileValidationError(
                "mechanical profile root must be a JSON object"
            )
        version = payload.get("schema_version")
        if version != MECHANICAL_PROFILE_SCHEMA_VERSION:
            raise ProfileValidationError(
                f"unsupported mechanical profile schema_version {version!r}; "
                "only schema version 3 is accepted"
            )
        data = dict(payload)
        mounts = data.get("mounts")
        if not isinstance(mounts, list):
            raise ProfileValidationError(
                "mechanical profile mounts must be a JSON array"
            )
        data["mounts"] = tuple(MechanicalMount.from_dict(item) for item in mounts)
        profile = cls(**_strict_dataclass_kwargs(cls, data))
        profile.validate()
        return profile


@dataclass(frozen=True)
class PrintPreset:
    schema_version: int = PRINT_PRESET_SCHEMA_VERSION
    name: str = "default-pla"
    fit_clearance_mm: float = 0.35
    mask_thickness_mm: float = 2.0
    ring_wall_thickness_mm: float = 3.0
    region_gap_mm: float = 2.0
    lead_in_chamfer_mm: float = 1.0
    outer_edge_radius_mm: float = 0.5
    outer_face_fillet_radius_mm: float = 0.0
    engrave_label: bool = True

    def validate(self) -> None:
        if self.schema_version != PRINT_PRESET_SCHEMA_VERSION:
            raise ProfileValidationError("print preset schema_version must be 1")
        _non_empty_string("print preset name", self.name)
        _non_negative_finite("fit_clearance_mm", self.fit_clearance_mm)
        _positive_finite("mask_thickness_mm", self.mask_thickness_mm)
        _positive_finite(
            "ring_wall_thickness_mm", self.ring_wall_thickness_mm
        )
        _non_negative_finite("region_gap_mm", self.region_gap_mm)
        _non_negative_finite("lead_in_chamfer_mm", self.lead_in_chamfer_mm)
        _non_negative_finite("outer_edge_radius_mm", self.outer_edge_radius_mm)
        _non_negative_finite(
            "outer_face_fillet_radius_mm", self.outer_face_fillet_radius_mm
        )
        if self.fit_clearance_mm > 3:
            raise ProfileValidationError(
                "fit_clearance_mm is physically implausible"
            )
        if self.ring_wall_thickness_mm < 1:
            raise ProfileValidationError(
                "ring_wall_thickness_mm must be at least 1 mm"
            )
        if not isinstance(self.engrave_label, bool):
            raise ProfileValidationError("engrave_label must be a boolean")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PrintPreset":
        if not isinstance(payload, dict):
            raise ProfileValidationError("print preset root must be a JSON object")
        preset = cls(**_strict_dataclass_kwargs(cls, dict(payload)))
        preset.validate()
        return preset


def repository_root() -> Path:
    return Path(__file__).resolve().parents[2]


def mechanical_profile_dir() -> Path:
    return repository_root() / "mechanical-profiles"


def print_preset_dir() -> Path:
    return repository_root() / "print-presets"


def resolve_mechanical_profile(value: str | Path) -> Path:
    path = Path(value)
    if path.exists():
        return path
    return mechanical_profile_dir() / f"{value}.json"


def resolve_print_preset(value: str | Path) -> Path:
    path = Path(value)
    if path.exists():
        return path
    return print_preset_dir() / f"{value}.json"


def load_mechanical_profile(path: Path) -> MechanicalProfile:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileValidationError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return MechanicalProfile.from_dict(payload)
    except ProfileValidationError as exc:
        raise ProfileValidationError(f"{path}: {exc}") from exc


def load_print_preset(path: Path) -> PrintPreset:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ProfileValidationError(f"{path}: invalid JSON: {exc}") from exc
    try:
        return PrintPreset.from_dict(payload)
    except ProfileValidationError as exc:
        raise ProfileValidationError(f"{path}: {exc}") from exc


def search_mechanical_profiles(
    term: str = "", profiles_dir: Path | None = None
) -> list[MechanicalProfile]:
    profiles: list[MechanicalProfile] = []
    for path in sorted((profiles_dir or mechanical_profile_dir()).glob("*.json")):
        profile = load_mechanical_profile(path)
        haystack = " ".join(
            [profile.manufacturer, profile.model, profile.slug, profile.label]
        ).lower()
        if term.lower() in haystack:
            profiles.append(profile)
    return profiles


def search_print_presets(
    term: str = "", presets_dir: Path | None = None
) -> list[PrintPreset]:
    presets: list[PrintPreset] = []
    for path in sorted((presets_dir or print_preset_dir()).glob("*.json")):
        preset = load_print_preset(path)
        if term.lower() in preset.name.lower():
            presets.append(preset)
    return presets


def render_json(value: MechanicalProfile | PrintPreset) -> str:
    payload = asdict(value)
    if isinstance(value, MechanicalProfile):
        payload["mounts"] = [asdict(mount) for mount in value.mounts]
    return json.dumps(payload, indent=2, ensure_ascii=False) + "\n"


def proposed_print_preset() -> PrintPreset:
    preset = PrintPreset()
    preset.validate()
    return preset


def mechanical_profile_template(*, clear_diameter_mm: float) -> dict[str, Any]:
    _positive_finite("clear_diameter_mm", clear_diameter_mm)
    return {
        "schema_version": MECHANICAL_PROFILE_SCHEMA_VERSION,
        "manufacturer": "REPLACE_ME",
        "model": "REPLACE_ME",
        "slug": "replace-me",
        "label": "REPLACE_ME",
        "mounts": [
            {
                "name": "hood-front-outer",
                "type": "outer-slip-fit",
                "diameter_mm": None,
                "usable_depth_mm": None,
                "status": "measured",
                "preferred": True,
            }
        ],
    }
