# Lens and hood measurements

SelfLensBahtinov V1 supports smooth slip-fit caps only. Printed threads and screw-in mounts are intentionally out of scope. The bundled profiles intentionally have no recommended mount until the relevant barrel or hood diameter is measured. The nominal filter-thread size in a profile is product metadata; it is not necessarily the outside diameter of the lens barrel or hood.

Use digital calipers and measure in at least three rotational orientations. Record the largest value for outside slip-fit diameters, because the printed ring must clear the largest point.

## Lens barrel outer slip fit

Measure the outside diameter of the lens barrel at the intended mounting point. Confirm that the selected point does not move during zooming or focusing and does not cover controls, switches, focus rings, aperture rings, or lens extension seams.

Formula: `ring_inner_diameter = lens_barrel_outer_mm + 2 * radial_clearance_mm`.

## Hood outer slip fit

Measure the outside diameter of the lens hood exactly where the mask ring will slide over the hood. Avoid flared, tapered, petal-cut, or textured areas unless that is the intended contact surface. Measure near the front rim and any rearward straight section you might use, then choose a straight cylindrical section with enough depth.

Formula: `ring_inner_diameter = hood_outer_mm + 2 * radial_clearance_mm`.

## Hood inner slip fit

Measure the inside diameter of the hood opening at the axial location where the ring will insert. For this inner fit, radial clearance is subtracted from the printable outside of the skirt so it can enter the opening.

Formula: `ring_outer_diameter = hood_inner_mm - 2 * radial_clearance_mm`.

## Usable straight mounting depth

Measure the axial length of straight, unobstructed surface available for the ring to grip. This value constrains `ring_depth_mm`. Leave clearance for hood bayonet tabs, lens caps, control rings, and any taper. If the straight section is shorter than the configured ring depth, reduce `ring_depth_mm` before generating the model.

## Recommended workflow

1. Measure each diameter in at least three orientations with digital calipers.
2. Enter unknown profile dimensions only after measuring them; use `estimated` for rough dimensions that should be limited to test rings, `measured` for caliper measurements, and `verified` only after a printed test ring has fit the actual lens or hood.
3. Set `recommended_mount` only for a physically recommended mount whose dimension is `measured` or `verified`.
4. Generate a `generate-test-ring` model with the intended mount and clearance.
5. Print the test ring before the full mask.
6. Try a small clearance matrix such as 0.20 mm, 0.30 mm, 0.40 mm, and 0.50 mm, generating one ring at a time.
7. Choose the smallest clearance that slips on securely without force.

Real fit depends on printer calibration, material shrinkage, elephant foot, slicer settings, surface texture, and measurement accuracy.
