from __future__ import annotations

from dataclasses import replace

import pytest

from selflensbahtinov.models import (
    GratingRegion,
    MaskGeometry,
    MaskType,
    MountType,
    Point2D,
    RingGeometry,
    SlotGeometry,
)
from selflensbahtinov.slot_topology import (
    is_valid_clipped_slot,
    remove_malformed_slots,
)


def slot(region, *, center, angle):
    return SlotGeometry(
        center=Point2D(*center),
        length_mm=90.0,
        width_mm=2.0,
        angle_deg=angle,
        region=region,
        useful_length_mm=10.0,
        clipped_area_mm2=20.0,
    )


def geometry(slots):
    return MaskGeometry(
        profile_slug="topology-test",
        mask_type=MaskType.BAHTINOV,
        clear_aperture_mm=80.0,
        slot_width_mm=2.0,
        slot_spacing_mm=6.0,
        slots=tuple(slots),
        ring=RingGeometry(
            mount_type=MountType.HOOD_OUTER_SLIP_FIT,
            mount_diameter_mm=90.0,
            inner_diameter_mm=90.7,
            outer_diameter_mm=96.7,
            wall_thickness_mm=3.0,
            depth_mm=15.0,
            clearance_mm=0.35,
        ),
        thickness_mm=2.0,
        pattern_border_mm=3.0,
        region_gap_mm=2.0,
        label=None,
        grating=None,
    )


def test_single_aperture_arc_is_kept():
    candidate = slot(
        GratingRegion.LEFT_REFERENCE,
        center=(-20.0, 0.0),
        angle=0.0,
    )
    assert is_valid_clipped_slot(candidate, radius=40.0, region_gap_mm=2.0)


def test_tangent_fragment_with_two_curved_ends_is_rejected():
    candidate = slot(
        GratingRegion.RIGHT_UPPER,
        center=(28.0, 28.0),
        angle=-45.0,
    )
    assert not is_valid_clipped_slot(candidate, radius=40.0, region_gap_mm=2.0)


def test_topology_filter_is_independent_from_length_threshold(monkeypatch):
    left = slot(GratingRegion.LEFT_REFERENCE, center=(-20.0, 0.0), angle=0.0)
    upper = slot(GratingRegion.RIGHT_UPPER, center=(10.0, 10.0), angle=60.0)
    lower = slot(GratingRegion.RIGHT_LOWER, center=(10.0, -10.0), angle=-60.0)
    malformed = slot(GratingRegion.RIGHT_UPPER, center=(28.0, 28.0), angle=-45.0)
    source = geometry((left, upper, lower, malformed))

    import selflensbahtinov.slot_topology as topology

    original = topology.is_valid_clipped_slot
    monkeypatch.setattr(
        topology,
        "is_valid_clipped_slot",
        lambda candidate, **kwargs: candidate is not malformed and original(candidate, **kwargs),
    )
    filtered = remove_malformed_slots(source)

    assert malformed not in filtered.slots
    assert len(filtered.slots) < len(source.slots)
    assert {candidate.region for candidate in filtered.slots} == {
        GratingRegion.LEFT_REFERENCE,
        GratingRegion.RIGHT_UPPER,
        GratingRegion.RIGHT_LOWER,
    }


def test_tribahtinov_geometry_is_left_unchanged():
    source = replace(geometry(()), mask_type=MaskType.TRIBAHTINOV)
    assert remove_malformed_slots(source) is source
