# Lens and hood measurements

SelfLensBahtinov does not invent physical dimensions. Use digital calipers and measure in at least three rotational orientations. Record the largest value for outside slip-fit diameters, because the printed ring must clear the largest point.

## Hood outer diameter

Measure the outside diameter of the lens hood exactly where the mask ring will slide over the hood. Avoid flared, tapered, petal-cut, or textured areas unless that is the intended contact surface. Measure near the front rim and any rearward straight section you might use, then choose a straight cylindrical section with enough depth.

## Hood inner diameter

Measure the inside diameter of the hood at the same axial location. This is useful for checking that the mask face and clear aperture do not intrude into the optical path or collide with hood geometry. Do not use it as the outside slip-fit diameter.

## Barrel outer diameter

Measure the outside diameter of the lens barrel at the intended mounting point. Confirm that the selected point does not move during zooming or focusing and does not cover controls, switches, focus rings, aperture rings, or lens extension seams.

## Usable straight mounting depth

Measure the axial length of straight, unobstructed surface available for the ring to grip. This value constrains `ring_depth_mm`. Leave clearance for hood bayonet tabs, lens caps, control rings, and any taper. If the straight section is shorter than the configured ring depth, reduce `ring_depth_mm` before generating the model.

## Recommended workflow

1. Measure each diameter in at least three orientations with digital calipers.
2. Enter unknown profile dimensions only after measuring them.
3. Generate a `generate-test-ring` model with the intended mount and clearance.
4. Print the test ring before the full mask.
5. Adjust `--clearance` or the profile default in 0.05-0.10 mm increments until the ring slips on securely without force.
