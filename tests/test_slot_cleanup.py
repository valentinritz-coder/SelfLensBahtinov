from selflensbahtinov.models import GratingRegion, Point2D, SlotGeometry
from selflensbahtinov.slot_cleanup import _is_printable_clipped_slot


def slot(*, useful_length, area, width=1.2):
    return SlotGeometry(
        center=Point2D(0.0, 0.0),
        length_mm=90.0,
        width_mm=width,
        angle_deg=60.0,
        region=GratingRegion.RIGHT_UPPER,
        useful_length_mm=useful_length,
        clipped_area_mm2=area,
    )


def test_long_tapered_triangle_is_rejected_even_when_projected_length_passes():
    fragment = slot(useful_length=10.0, area=4.0)
    assert not _is_printable_clipped_slot(fragment, minimum_length_mm=4.0)


def test_normal_clipped_slot_with_substantial_width_is_kept():
    clipped = slot(useful_length=10.0, area=10.5)
    assert _is_printable_clipped_slot(clipped, minimum_length_mm=4.0)


def test_short_fragment_is_rejected():
    fragment = slot(useful_length=3.9, area=8.0)
    assert not _is_printable_clipped_slot(fragment, minimum_length_mm=4.0)


def test_zero_threshold_preserves_explicit_filter_disable_behavior():
    fragment = slot(useful_length=1.0, area=0.1)
    assert _is_printable_clipped_slot(fragment, minimum_length_mm=0.0)
