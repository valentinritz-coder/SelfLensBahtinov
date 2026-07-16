# Measurements required

SelfLensBahtinov intentionally avoids invented lens dimensions. Measure each lens/hood with calipers before generating a hood or barrel mounted mask.

## Required for all masks

- Confirm the filter thread diameter printed on the lens or lens cap.
- Choose the intended mount type: `filter_thread`, `hood_outer`, or `barrel_outer`.
- Measure printer/material fit and tune `fit_clearance_mm` with a test ring.

## Required for hood-mounted masks

- `hood_outer_diameter_mm`: outside diameter of the hood where the mask will slip over it.
- Confirm the hood has enough straight wall depth for `ring_depth_mm`.

## Required for barrel-mounted masks

- `barrel_outer_diameter_mm`: outside diameter of the lens barrel at the mounting point.
- Confirm the mask will not interfere with zoom, focus, aperture rings, switches, or lens extension.

## Recommended measurement workflow

1. Measure the diameter in at least three rotational positions.
2. Use the largest measured diameter as the profile value.
3. Generate a `--test-ring` first.
4. Adjust `fit_clearance_mm` in 0.1 mm increments until the ring slides on securely without forcing.
