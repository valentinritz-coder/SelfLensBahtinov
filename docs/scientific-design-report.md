# Scientific Bahtinov design report

The `Recommend Bahtinov mask parameters` workflow generates a Markdown report before a printable model is produced. It makes the optical assumptions and manufacturing trade-offs visible instead of burying them in defaults, humanity's favourite habitat for accidental physics.

## Workflow inputs

The workflow asks for:

- working focal length and f-number;
- physical clear diameter available for the slotted pattern;
- reference wavelength and optional filter bandwidth;
- camera pixel pitch and binning;
- intended focus-reading mode: visual or software-assisted;
- optional expected stellar signal-to-noise ratio;
- desired first-order diffraction offset in effective pixels;
- minimum printable open-slot and opaque-bar widths;
- side-groove angle relative to the central groove family.

## Correct diameter for grating periods

The estimated entrance-pupil diameter is:

```text
D_pupil = focal_length / f_number
```

The printed mask can be larger or smaller than that pupil. The useful illuminated diameter is therefore:

```text
D_illuminated = min(D_mask, D_pupil)
```

The report uses `D_illuminated / pitch` for the useful period count and also shows the purely physical `D_mask / pitch` value for reference.

## Angle geometry

The report separates quantities that were previously conflated:

- directed separation of the two side diffraction orders: `2 alpha`;
- visible angle between their unoriented line axes: `min(2 alpha, 180° - 2 alpha)`;
- one-sided crossing displacement for a middle-spike offset `delta`: `delta / tan(alpha)`;
- total separation of the two crossings: `2 delta / tan(alpha)`.

Thus side grooves at ±60° produce 120° directed separation but 60° between the visible spike axes.

## Filter bandwidth and focus mode

When a bandwidth is supplied, the report estimates the first-order position at both passband edges and reports the resulting geometric chromatic span. The calculation assumes a symmetric passband around the supplied central wavelength.

Software-assisted mode can include an expected stellar SNR. The report cites the MeerLICHT Hough/Canny case study and labels its SNR findings as implementation-specific rather than universal thresholds.

## Running locally

```bash
python -m selflensbahtinov.design_report \
  --focal-length-mm 400 \
  --f-number 5.6 \
  --mask-clear-diameter-mm 76.7 \
  --wavelength-nm 550 \
  --filter-bandwidth-nm 100 \
  --pixel-pitch-um 3.76 \
  --binning 1 \
  --focus-mode software-assisted \
  --expected-star-snr 20 \
  --target-first-order-offset-px 20 \
  --minimum-slot-width-mm 0.8 \
  --minimum-bar-width-mm 0.8 \
  --side-groove-angle-deg 20 \
  --output generated/bahtinov-design-report.md
```

## Deliberate limitation

The workflow recommends and compares side-groove angles but does not yet change the mask generator's fixed angle. The report identifies this as a future `--side-grating-angle` parameter. A genuine optimum requires a forward diffraction model and a declared objective, such as focus-estimation variance at specified SNR.
