# Lens and hood measurements

SelfLensBahtinov supports smooth slip-fit caps. Printed threads and screw-in mounts remain out of scope. A nominal filter-thread size is product metadata; it is not necessarily the outside diameter of the lens barrel or hood and is not part of the mechanical profile schema.

All measurements are recorded in a schema-v3 mechanical profile. It deliberately stores only real mounting facts:

```json
{
  "schema_version": 3,
  "manufacturer": "Fujifilm",
  "model": "Fujinon XF100-400mmF4.5-5.6 R LM OIS WR",
  "slug": "fujifilm-xf100-400",
  "label": "XF100-400",
  "mounts": [
    {
      "name": "hood-front-outer",
      "type": "outer-slip-fit",
      "diameter_mm": 92.6,
      "usable_depth_mm": 8.0,
      "status": "measured",
      "preferred": true
    }
  ]
}
```

Schema versions 1 and 2 are no longer loaded or migrated. See [scientific-mask-action.md](scientific-mask-action.md) for the complete report, mechanical-profile, print-preset, and assembly workflow.

## General measurement method

Use digital calipers and measure the intended mounting surface in at least three rotational orientations.

- For an outside diameter, record the largest reading because the printed ring must clear the largest point.
- For an inside diameter, measure at the actual axial insertion position.
- Confirm that the contact surface is cylindrical and does not move during zooming or focusing.
- Avoid controls, switches, moving rings, extension seams, bayonet tabs, petal edges, tapers, and heavily textured areas.
- Measure the usable straight axial depth separately from the diameter.

## Outer slip fit

Use `type: outer-slip-fit` when the mask slides over the outside of a lens barrel or hood.

Measure the outside diameter exactly where the skirt will grip. The generated nominal fit is:

```text
ring_inner_diameter = measured_outer_diameter + 2 * radial_clearance
```

The generic schema does not need separate `hood_outer_mm` and `lens_barrel_outer_mm` fields. Give the surface a clear name such as `hood-front-outer` or `fixed-barrel-outer`.

## Inner slip fit

Use `type: inner-slip-fit` when the mask inserts into a measured hood opening.

Measure the inside diameter at the intended insertion depth. The skirt outside diameter is:

```text
ring_outer_diameter = measured_inner_diameter - 2 * radial_clearance
```

The ring wall is then built inward from that outside diameter.

## Usable mounting depth

`usable_depth_mm` is the straight, unobstructed axial length available for the mounting skirt. It is a measured mechanical limit, not a stylistic preference.

Leave room for bayonet tabs, tapers, lens caps, control rings, and moving sections. The complete mask uses this value as its skirt depth. The matching fit-test ring is intentionally capped at 4 mm so diameter and edge geometry can be checked cheaply before printing the full skirt.

## Measurement status

- `estimated`: rough or catalogue-derived value. It may generate a fit-test ring only.
- `measured`: value taken with calipers on the actual lens or hood. It may generate a complete mask, but the fit-test ring should still be printed first.
- `verified`: a printed test ring has physically fitted the actual mounting surface.

Do not mark a catalogue dimension as verified merely because the internet presented it with several decimal places. Typography is not metrology.

## Recommended physical workflow

1. Complete and review the scientific report.
2. Select one safe cylindrical mounting surface.
3. Measure diameter in at least three orientations.
4. Measure usable straight depth.
5. Add the surface to the corresponding file in `mechanical-profiles/`, or enter it in the assembly action.
6. Review or edit the proposed print preset, especially radial clearance.
7. Use `estimated` when uncertain so only a test ring is generated.
8. Print and test the short ring.
9. Change the status to `verified` after a successful physical fit.
10. Generate and print the complete mask.

A useful starting clearance matrix is 0.20, 0.30, 0.40, and 0.50 mm. Real fit depends on printer calibration, material shrinkage, elephant foot, slicer settings, surface texture, and measurement accuracy.
