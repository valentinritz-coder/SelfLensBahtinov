# Bahtinov optical algorithm

SelfLensBahtinov generates Bahtinov aperture-plane geometry in Python. OpenSCAD receives Python-calculated slot rectangles and performs the final boolean clipping against the circular clear aperture and assigned grating region. It does not choose the optical pitch, slot width, side angle, mechanical mounting diameter, or printer tolerances.

Those responsibilities are separated:

```text
Scientific report  -> pitch, slot width, bar width, clear diameter, side angle
Mechanical profile -> mounting diameter, fit direction, usable depth
Print preset       -> clearance, thicknesses, separator, edge treatment
```

## Physical model

A normal Bahtinov mask contains three parallel rectangular transmission gratings assigned to explicit parts of the entrance aperture:

1. `LEFT_REFERENCE`, the reference grating on the left;
2. `RIGHT_UPPER`, an oblique grating on the upper right;
3. `RIGHT_LOWER`, the opposite oblique grating on the lower right.

Each grating has pitch `p`, open slot width `w`, opaque bar width `p - w`, and open fraction `w / p`. Slots inside one region remain parallel. They do not individually converge toward the optical centre.

The first-order grating relation is:

```text
p sin(theta_1) = lambda
```

The exact sensor-plane offset used by the scientific report is:

```text
x_1 = F tan(asin(lambda / p))
```

The report chooses a pitch from the requested sensor offset and wavelength, then clamps it only when the declared minimum printable slot and bar widths require a coarser grating. A 50% open fraction is the unconstrained starting point for a rectangular binary amplitude grating.

## Variable side angle

The central family is defined at `0°`; the side families are placed at `+alpha` and `-alpha`. The report-selected `side_groove_angle_deg` is applied directly to the complete mask.

Pitch controls the radial location of the diffraction order. Groove orientation controls its direction. The project does not claim one angle is universally optimal without a declared focus estimator, seeing, signal-to-noise ratio, and objective function.

## Effective clear diameter

The scientific report distinguishes:

```text
physical printed clear diameter
estimated entrance pupil = F / N
effectively illuminated diameter = min(printed diameter, F / N)
```

The physical mask keeps the requested printed clear diameter. The mechanical assembly rejects a mount that cannot preserve it. It does not silently shrink the optical aperture to rescue incompatible measurements.

## Region topology and separator bands

The three regions use a physical separator gap `region_gap_mm`:

```text
LEFT_REFERENCE: x <= -region_gap_mm / 2
RIGHT_UPPER:    x >=  region_gap_mm / 2 and y >=  region_gap_mm / 2
RIGHT_LOWER:    x >=  region_gap_mm / 2 and y <= -region_gap_mm / 2
```

The central vertical band and right-side horizontal band remain solid for mechanical support. Separator width is a print-preset decision, not a lens-profile field and not an optical measurement.

## Clipped-slot manufacturing cleanup

Candidate slots are intentionally longer than the clear aperture and are clipped to:

```text
clear aperture ∩ assigned region ∩ candidate rectangle
```

A curved end caused by the circular aperture is normal. Python performs two cleanup passes before export:

- topology validation rejects disconnected or doubly curved malformed remnants;
- printability filtering rejects short or strongly tapered slivers while retaining useful rectangular and singly clipped slots.

The default minimum useful projected length is:

```text
max(2 * slot_width_mm, 4.0 mm)
```

All SCAD, STL, and 3MF exports use the same retained slot set.

## Mechanical assembly

The schema-v3 mechanical profile contains no focal length, aperture, optical recommendation, clearance, face thickness, or edge treatment. It contributes only the selected measured mount:

- outer or inner slip-fit direction;
- physical diameter;
- usable straight depth;
- measurement status.

The print preset contributes radial clearance, skirt wall thickness, face thickness, separator width, chamfer, outer-edge treatment, optional front-face fillet, and label choice.

## Output geometry

The complete assembly retains:

- the rear-loading label holder at 3 o'clock;
- a coplanar slotted build face;
- a solid full-width crown root beneath the holder;
- a short matching fit-test ring;
- the same mounting cross-section for test ring and full mask;
- the scientific pitch, slot width, clear diameter, and side angle.

## References

The generated scientific report records the evidential role of:

- van den Born, Jellema, and Dijkstra, MNRAS 512 (2022), DOI `10.1093/mnras/stac845`, for grating density, orientation, and entrance-pupil treatment;
- Zandvliet (2017), University of Groningen, for a practical Bahtinov focus-estimation case study;
- Perrin and Montgomery (2018), arXiv `1802.07161`, for the general Fourier-optics framework.
