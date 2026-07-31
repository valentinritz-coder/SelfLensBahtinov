# Clipped-slot filtering

Normal Bahtinov masks now apply two independent checks.

## Geometry check

Malformed clipped fragments are always removed. A slot may remain rectangular or have one end replaced by the circular aperture boundary. It is rejected when its final contour contains two separate circular boundary runs or no longer retains enough straight slot structure.

This check cannot be disabled because those fragments are not useful slot shapes and are often fragile to print.

## Minimum printable length

`--minimum-clipped-slot-length` remains a secondary printability threshold for geometrically valid slots.

- empty: automatic minimum of `max(2 × slot width, 4 mm)`;
- `0`: keep every geometrically valid slot, regardless of length;
- positive value: remove valid slots shorter than that length.

The length setting no longer needs to guess which curved fragments are malformed. Humanity has finally separated shape from size, an achievement normally introduced before manufacturing begins.
