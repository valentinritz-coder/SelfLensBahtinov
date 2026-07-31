"""Place the strengthened label holder at 3 o'clock on the mask."""

from __future__ import annotations

from selflensbahtinov.models import MaskGeometry
from selflensbahtinov.solid_label_root import SolidRootOpenScadRenderer

_LABEL_POSITION_DEG = -90.0


class ThreeOClockLabelRenderer(SolidRootOpenScadRenderer):
    """Rotate the complete holder and pocket from +Y (12 h) to +X (3 h).

    The underlying strengthened-root geometry remains defined in its original
    local coordinate system.  Wrapping both the solid boss and its subtractive
    pocket in the same Z rotation preserves their fit, full-width crown root,
    flush build face, and rear-loading direction.
    """

    def _label_cartridge_modules(self, g: MaskGeometry) -> list[str]:
        lines = super()._label_cartridge_modules(g)
        renamed = [
            line.replace(
                "module label_cartridge_boss()",
                "module label_cartridge_boss_at_12()",
            ).replace(
                "module label_cartridge_pocket()",
                "module label_cartridge_pocket_at_12()",
            )
            for line in lines
        ]
        return [
            f"// label_holder_clock_position=3 label_holder_rotation_deg={_LABEL_POSITION_DEG:.1f}",
            *renamed,
            "module label_cartridge_boss() {",
            f"  rotate([0, 0, {_LABEL_POSITION_DEG:.1f}]) label_cartridge_boss_at_12();",
            "}",
            "module label_cartridge_pocket() {",
            f"  rotate([0, 0, {_LABEL_POSITION_DEG:.1f}]) label_cartridge_pocket_at_12();",
            "}",
        ]
