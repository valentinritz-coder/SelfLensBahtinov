"""Simple mechanical-profile and print-preset contracts for mask assembly."""

from __future__ import annotations

from dataclasses import MISSING, asdict, dataclass, fields
import json
import math
from pathlib import Path
import re
from typing import Any


_MEASUREMENT_STATUSES = {"estimated", "measured", "verified"}
_MOUNT_TYPES = {"outer-slip-fit", "inner-slip-fit"}


def _positive_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f"{name} must be a positive finite number")


def _non_negative_finite(name: str, value: float) -> None:
    if not math.isfinite(value) or value < 0:
        raise ValueError(f"{name} must be a non-negative finite number")


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    if not slug:
        raise ValueError("slug source must contain at least one letter or digit")
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
        raise ValueError(f"unknown fields for {cls.__name__}: {sorted(unknown)}")
    if missing:
        raise ValueError(f"missing fields for {cls.__name__}: {sorted(missing)}")
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
        if not self.name.strip():
            raise ValueError("mount name must not be empty")
        if self.type not in _MOUNT_TYPES:
            raise ValueError("mount type must be outer-slip-fit or inner-slip-fit")
        _positive_finite("diameter_mm", self.diameter_mm)
        _positive_finite("usable_depth_mm", self.usable_depth_mm)
        if self.status not in _MEASUREMENT_STATUSES:
            raise ValueError("mount status must be estimated, measured, or verified")
        if not isinstance(self.preferred, bool):
            raise ValueError("mount preferred must be a boolean")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MechanicalMount":
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
        if self.schema_version != 3:
            raise ValueError("mechanical profile schema_version must be 3")
        for name, value in (
            ("manufacturer", self.manufacturer),
            ("model", self.model),
            ("slug", self.slug),
            ("label", self.label),
        ):
            if not value.strip():
                raise ValueError(f"mechanical profile {name} must not be empty")
        if self.slug != slugify(self.slug):
            raise ValueError("mechanical profile slug must already be URL/file safe")
        if not self.mounts:
            raise ValueError("mechanical profile must contain at least one mount")
        names: set[str] = set()
        preferred = 0
        for mount in self.mounts:
            mount.validate()
            if mount.name in names:
                raise ValueError(f"duplicate mechanical mount name: {mount.name}")
            names.add(mount.name)
            preferred += int(mount.preferred)
        if preferred > 1:
            raise ValueError("only one mechanical mount may be preferred")

    def select_mount(self, name: str | None = None) -> MechanicalMount:
        self.validate()
        if name:
            for mount in self.mounts:
                if mount.name == name:
                    return mount
            raise ValueError(f"mechanical mount not found: {name}")
        preferred = [mount for mount in self.mounts if mount.preferred]
        if len(preferred) == 1:
            return preferred[0]
        if len(self.mounts) == 1:
            return self.mounts[0]
        raise ValueError("select --mount-name because the profile has no unique preferred mount")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "MechanicalProfile":
        data = dict(payload)
        mounts = data.get("mounts")
        if not isinstance(mounts, list):
            raise ValueError("mechanical profile mounts must be a JSON array")
        data["mounts"] = tuple(MechanicalMount.from_dict(item) for item in mounts)
        profile = cls(**_strict_dataclass_kwargs(cls, data))
        profile.validate()
        return profile


@dataclass(frozen=True)
class PrintPreset:
    schema_version: int = 1
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
        if self.schema_version != 1:
            raise ValueError("print preset schema_version must be 1")
        if not self.name.strip():
            raise ValueError("print preset name must not be empty")
        _non_negative_finite("fit_clearance_mm", self.fit_clearance_mm)
        _positive_finite("mask_thickness_mm", self.mask_thickness_mm)
        _positive_finite("ring_wall_thickness_mm", self.ring_wall_thickness_mm)
        _non_negative_finite("region_gap_mm", self.region_gap_mm)
        _non_negative_finite("lead_in_chamfer_mm", self.lead_in_chamfer_mm)
        _non_negative_finite("outer_edge_radius_mm", self.outer_edge_radius_mm)
        _non_negative_finite(
            "outer_face_fillet_radius_mm", self.outer_face_fillet_radius_mm
        )
        if not isinstance(self.engrave_label, bool):
            raise ValueError("engrave_label must be a boolean")

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "PrintPreset":
        preset = cls(**_strict_dataclass_kwargs(cls, dict(payload)))
        preset.validate()
        return preset


def load_mechanical_profile(path: Path) -> MechanicalProfile:
    return MechanicalProfile.from_dict(json.loads(path.read_text(encoding="utf-8")))


def load_print_preset(path: Path) -> PrintPreset:
    return PrintPreset.from_dict(json.loads(path.read_text(encoding="utf-8")))


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
        "schema_version": 3,
        "manufacturer": "REPLACE_ME",
        "model": "REPLACE_ME",
        "slug": "replace-me",
        "label": "REPLACE_ME",
        "mounts": [
            {
                "name": "hood-front-outer",
                "type": "outer-slip-fit",
                "diameter_mm": None,
                "usable_depth_mm": 8.0,
                "status": "measured",
                "preferred": True,
            }
        ],
    }
