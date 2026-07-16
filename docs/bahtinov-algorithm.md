# Bahtinov optical algorithm

SelfLensBahtinov generates Bahtinov aperture-plane geometry in Python. OpenSCAD receives Python-calculated candidate slot rectangles and clips them against the circular aperture and assigned region boundaries for export; it does not choose grating pitch, slot width, density, or optical constants.

## Physical model

A Bahtinov mask is three rectangular transmission gratings assigned to different parts of the entrance aperture:

1. a reference grating;
2. a side grating rotated by `+60°`;
3. a side grating rotated by `-60°`.

Each grating is a periodic aperture function with effective pitch `p` and open slot width `w`. The opaque bar width is `p - w`, and the open fraction is `w / p`. Slot direction, grating-vector direction, and diffraction-spike direction are different quantities:

- the slot direction is the long axis of each rectangular opening;
- the grating vector is perpendicular to the slot family and has magnitude `1 / p`;
- the first-order diffraction spike is perpendicular to the slot family in the rendered star image.

The scalar diffraction relationship used for metadata and validation is the Fraunhofer grating equation:

```text
sin(theta_m) = m * lambda / p
```

For focusing masks the useful visual cue is the first order (`m = 1`). SelfLensBahtinov uses a green reference wavelength of `550 nm`, a conventional photopic midpoint. The approximate first-order displacement at the image plane is:

```text
x ~= f * tan(theta_1)
```

where `f` is the selected focal length. The production generator does not render a point-spread function. V1 tests verify the slot/grating/spike orientation convention, but they do not claim to be a scalar-diffraction simulation.

## Default pitch selection

The default geometry is a physics-informed printable heuristic, not a full optical derivation. Python computes the pitch implied by a target first-order sensor offset, then applies practical aperture-size clamps and printer limits. Therefore the generated mask remains a real three-grating Bahtinov pattern, but the default pitch may be determined by the practical clamp rather than solely by the grating equation. Explicit `--slot-spacing` and `--slot-width` are the way to request a specific physical grating.

## Configurable dimensions

The CLI exposes the grating parameters:

- `--slot-spacing`: physical pitch in millimetres before density scaling.
- `--slot-width`: open slot width in millimetres.
- `--slot-density`: slot-count density multiplier. The effective pitch is `slot_spacing / slot_density`. If slot width is omitted, Python chooses width from the effective pitch; if slot width is explicit, the user is intentionally changing the open fraction.
- `--show-grating-info`: print the rounded base pitch, effective pitch, slot width, bar width, open fraction, density, reference wavelength, first-order angle, sensor-plane offset, and pitch-selection source used for the generated full mask.

The generator rejects non-manufacturable or non-physical geometry, including NaN, infinity, microscopic pitch, microscopic open slots, microscopic opaque bars, excessive slot counts, duplicate slots, and regions that would receive no candidate slots. Validation is applied after output-precision rounding so values that quantize into invalid geometry are rejected.

## References

The model follows standard scalar diffraction and Bahtinov-mask design principles:

- Diffraction grating equation: a periodic aperture with pitch `p` sends order `m` to angles satisfying `sin(theta_m) = m * lambda / p`.
- Fraunhofer approximation: a mask at the entrance aperture of a focused lens maps small angular diffraction offsets to image-plane offsets with `x ~= f tan(theta)`.
- Bahtinov-mask geometry: Pavel Bahtinov's focusing mask combines three linear grating regions at different orientations; focus is read when the reference spike lies symmetrically between the two side spikes.

These references justify why the generated pattern is not an arbitrary family of clipped lines. It is a set of three assigned transmission gratings whose pitch and duty cycle define real first-order diffraction spikes.
