# Scientific Bahtinov design report

The `Recommend Bahtinov mask parameters` workflow generates a Markdown report before a printable model is produced. Its purpose is to make optical assumptions and manufacturing trade-offs visible instead of hiding them behind unexplained defaults.

## Workflow inputs

The workflow asks for:

- working focal length and f-number;
- physical clear diameter available for the slotted pattern;
- reference wavelength or filter central wavelength;
- camera pixel pitch and binning;
- desired first-order diffraction offset in effective pixels;
- minimum printable open-slot and opaque-bar widths;
- side-groove angle relative to the central groove family.

The optical aperture diameter is derived as `focal_length / f_number`. The physical clear mask diameter is separate: it determines how many grating periods can physically fit across the printed mask.

## Calculated recommendations

The generated report contains:

- optical and printable grating pitch;
- open-slot width, opaque-bar width, and duty cycle;
- first-order angle and sensor offset in millimetres and pixels;
- offset relative to the Airy radius;
- number of grating periods across the clear diameter;
- 12, 20, and 30 pixel offset alternatives;
- side-groove angle alternatives with their spike separation and simplified crossing magnification;
- explicit assumptions, limits, and scientific references.

The report uses the exact first-order grating relation and only clamps the result when the requested pitch is smaller than the declared manufacturing limits.

## Running locally

```bash
python -m selflensbahtinov.design_report \
  --focal-length-mm 400 \
  --f-number 5.6 \
  --mask-clear-diameter-mm 76.7 \
  --wavelength-nm 550 \
  --pixel-pitch-um 3.76 \
  --binning 1 \
  --target-first-order-offset-px 20 \
  --minimum-slot-width-mm 0.8 \
  --minimum-bar-width-mm 0.8 \
  --side-groove-angle-deg 20 \
  --output generated/bahtinov-design-report.md
```

## Deliberate limitation

The workflow recommends a side-groove angle but does not yet change the mask generator's fixed angle. The report identifies this as the future `--side-grating-angle` parameter. Keeping recommendation and geometry changes separate prevents an optical design choice from silently changing existing masks.

A later optimization stage can use FFT or Fresnel propagation over the complete aperture and optimize a declared metric such as focus-estimation variance at a specified signal-to-noise ratio. Until such an objective function exists, the workflow presents angle trade-offs rather than claiming a universal optimum.
