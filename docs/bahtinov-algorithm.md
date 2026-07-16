# Bahtinov optical algorithm

SelfLensBahtinov generates Bahtinov aperture-plane geometry in Python. OpenSCAD receives Python-calculated candidate slot rectangles and performs the final boolean clipping against the circular clear aperture and the assigned grating region for export; it does not choose grating pitch, slot width, density, optical constants, or which clipped normal-Bahtinov slots are retained.

## Physical model

A Bahtinov mask is three parallel rectangular transmission gratings assigned to three explicit parts of the entrance aperture:

1. `LEFT_REFERENCE`, a reference grating occupying the left side of the clear aperture;
2. `RIGHT_UPPER`, a side grating on the upper-right side;
3. `RIGHT_LOWER`, an oppositely angled side grating on the lower-right side.

Each grating is a periodic aperture function with effective pitch `p` and open slot width `w`. The opaque bar width is `p - w`, and the open fraction is `w / p`. Slot direction, grating-vector direction, and diffraction-spike direction are different quantities:

- the slot direction is the long axis of each rectangular opening;
- the grating vector is perpendicular to the slot family and has magnitude `1 / p`;
- the first-order diffraction spike is perpendicular to the slot family in the rendered star image.

Slots inside a region remain parallel. They do not individually converge toward the optical centre. The centre-oriented appearance seen in common Bahtinov masks comes from clipping parallel slots to the left, upper-right, and lower-right region boundaries.

The scalar diffraction relationship used for metadata and validation is the Fraunhofer grating equation:

```text
sin(theta_m) = m * lambda / p
```

For focusing masks the useful visual cue is the first order (`m = 1`). SelfLensBahtinov uses a green reference wavelength of `550 nm`, a conventional photopic midpoint. The approximate first-order displacement at the image plane is:

```text
x ~= f * tan(theta_1)
```

where `f` is the selected focal length. The production generator does not render a point-spread function. V1 tests verify the slot/grating/spike orientation convention, but they do not claim to be a scalar-diffraction simulation.

## Region topology and separator bands

The normal Bahtinov topology follows the original/common three-region layout more closely than the former equal-sector approximation. The regions use a physical separator gap `region_gap_mm`, whose default is `2.0 mm`:

```text
LEFT_REFERENCE: x <= -region_gap_mm / 2
RIGHT_UPPER:    x >=  region_gap_mm / 2 and y >=  region_gap_mm / 2
RIGHT_LOWER:    x >=  region_gap_mm / 2 and y <= -region_gap_mm / 2
```

The central vertical band and right-side horizontal band remain solid. These separator bands provide mechanical support and isolate the three grating regions. `region_gap_mm` must be finite and non-negative, must leave usable area in every region, and any non-zero gap must meet the same minimum printable-width policy used for opaque grating bars.

Tri-Bahtinov generation keeps its existing six-region angular topology. The explicit region identifiers prevent normal Bahtinov masks from accidentally falling back to three equal 120-degree sectors.

## Default pitch selection

The default geometry is a physics-informed printable heuristic, not a full optical derivation. Python computes the pitch implied by a target first-order sensor offset, then applies practical aperture-size clamps and printer limits. Therefore the generated mask remains a real three-grating Bahtinov pattern, but the default pitch may be determined by the practical clamp rather than solely by the grating equation. Explicit `--slot-spacing` and `--slot-width` are the way to request a specific physical grating.

## Clipped-slot manufacturing cleanup

Candidate slots are intentionally longer than the clear aperture so OpenSCAD can clip each opening to:

```text
clear aperture ∩ assigned region ∩ candidate rectangle
```

A curved slot end produced by the circular clear aperture is normal and is not treated as a defect. A long slot with one circular end, a long slot clipped diagonally by a region boundary, or any non-rectangular end with enough parallel-edge length remains valid.

Before rendering a normal three-region Bahtinov mask, Python clips every candidate rectangle against a deterministic polygonal representation of the circular clear aperture and the assigned rectangular region. It then records `useful_length_mm`, the projected span of that final clipped geometry along the slot's own longitudinal axis. Slots whose useful length is below `minimum_clipped_slot_length_mm` are discarded; slots at or above the threshold are retained and still receive OpenSCAD's final boolean clipping. The circle is approximated with 256 segments for this keep/discard decision, so the result is deterministic and conservative at printer-scale tolerances while avoiding STL mesh inspection.

The default threshold is `max(2 * slot_width_mm, 4.0 mm)`, which is intended as a safe cleanup value for typical 0.4 mm-nozzle printing and current default slot widths. Passing `--minimum-clipped-slot-length 0` disables this cleanup. This parameter is a manufacturing cleanup control only: it does not change optical pitch, grating density, slot angle, separator-band topology, mounting geometry, profile schema, or test-ring generation. Tri-Bahtinov keeps its existing six-region topology and does not currently apply this cleanup rule.

## Configurable dimensions

The CLI exposes the grating and region parameters:

- `--slot-spacing`: physical pitch in millimetres before density scaling.
- `--slot-width`: open slot width in millimetres.
- `--slot-density`: slot-count density multiplier. The effective pitch is `slot_spacing / slot_density`. If slot width is omitted, Python chooses width from the effective pitch; if slot width is explicit, the user is intentionally changing the open fraction.
- `--region-gap`: full physical width of the solid separator band between normal Bahtinov regions. The default is `2.0 mm`.
- `--minimum-clipped-slot-length`: minimum useful projected length, in millimetres, required after clipping a normal Bahtinov candidate slot to the clear aperture and assigned region. The default is `max(2 * slot_width_mm, 4.0 mm)`; `0` disables the cleanup filter.
- `--show-grating-info`: print the rounded base pitch, effective pitch, slot width, bar width, open fraction, density, reference wavelength, first-order angle, sensor-plane offset, and pitch-selection source used for the generated full mask.

The generator rejects non-manufacturable or non-physical geometry, including NaN, infinity, microscopic pitch, microscopic open slots, microscopic opaque bars, non-zero separator gaps below the printable minimum, excessive slot counts, duplicate slots, and regions that would receive no retained normal-Bahtinov slots after clipped-slot cleanup. Validation is applied after output-precision rounding so values that quantize into invalid geometry are rejected.

## References

The model follows standard scalar diffraction and Bahtinov-mask design principles:

- Diffraction grating equation: a periodic aperture with pitch `p` sends order `m` to angles satisfying `sin(theta_m) = m * lambda / p`.
- Fraunhofer approximation: a mask at the entrance aperture of a focused lens maps small angular diffraction offsets to image-plane offsets with `x ~= f tan(theta)`.
- Bahtinov-mask geometry: Pavel Bahtinov's focusing mask combines three linear grating regions at different orientations; focus is read when the reference spike lies symmetrically between the two side spikes.

These references justify why the generated pattern is not an arbitrary family of clipped lines. It is a set of three assigned transmission gratings whose pitch and duty cycle define real first-order diffraction spikes.
