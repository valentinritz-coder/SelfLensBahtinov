"""Shared pytest fixtures for generated/exported geometry tests."""

from __future__ import annotations

import pytest

from selflensbahtinov.models import MaskType
from selflensbahtinov.slot_cleanup import remove_clipped_slot_slivers
from selflensbahtinov.slot_topology import remove_malformed_slots

_EXPORT_GEOMETRY_TESTS = {
    "test_all_export_formats_use_same_filtered_slot_set_and_test_ring_is_unchanged",
    "test_scad_stl_and_3mf_exports_share_filtered_scad_slot_set",
}


@pytest.fixture(autouse=True)
def export_tests_compare_printable_geometry(request, monkeypatch):
    """Make legacy export assertions compare against the final printable slots.

    ``calculate_mask()`` intentionally returns the algorithm output. Exporting
    then applies the topology and sliver-cleanup passes in ``geometry_for()``.
    These two tests validate exported SCAD, so their expected slot count must use
    that same printable pipeline rather than the pre-cleanup algorithm result.

    The fixture is deliberately scoped to the two legacy assertions. Other
    algorithm tests continue to exercise ``calculate_mask()`` directly.
    """
    if request.node.name not in _EXPORT_GEOMETRY_TESTS:
        return

    test_module = request.module
    calculate_mask = test_module.calculate_mask

    def calculate_printable_mask(profile, options):
        geometry = remove_malformed_slots(calculate_mask(profile, options))
        if geometry.test_ring or geometry.mask_type is not MaskType.BAHTINOV:
            return geometry

        minimum_length = options.minimum_clipped_slot_length_mm
        if minimum_length is None:
            minimum_length = max(2 * geometry.slot_width_mm, 4.0)
        return remove_clipped_slot_slivers(
            geometry,
            minimum_length_mm=minimum_length,
        )

    monkeypatch.setattr(test_module, "calculate_mask", calculate_printable_mask)
