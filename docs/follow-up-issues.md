# Follow-up issues

## Verify Bahtinov grating angle convention

The current patch intentionally does not change `BAHTINOV_GRATING_ANGLE_DEG`. A separate review should compare the repository's angle convention with Pavel Bahtinov's original/AstroJargon-derived generator and document whether any product default should change.

That review must distinguish three different directions:

- slot longitudinal direction: the long axis of each rectangular aperture slot;
- grating normal / grating-vector direction: perpendicular to the slot family and used to measure physical pitch;
- diffraction-spike direction: the focal-plane spike direction produced by the slot family.

Any future default-angle change should be made as a separately reviewed design decision, not as an incidental topology or clipping fix.
