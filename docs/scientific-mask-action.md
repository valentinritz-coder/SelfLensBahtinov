# Generate a mask from scientific report inputs

The `Generate mask from scientific report inputs` workflow turns the same input set used by the scientific recommendation report into a flat Bahtinov optical plate.

The workflow deliberately asks for no mounting or lens-profile data. Its inputs are exactly:

- focal length;
- working f-number;
- physical clear mask diameter;
- reference wavelength and optional filter bandwidth;
- sensor pixel pitch and binning;
- visual or software-assisted focus mode;
- optional expected stellar SNR;
- requested first-order offset in pixels;
- minimum printable slot and bar widths;
- side-groove angle.

The recommendation engine derives the printable pitch, open-slot width, opaque-bar width, first-order location, and illuminated period count. The selected side angle is used directly for the two oblique grating families instead of being reduced to a report-only suggestion.

## Generated artifact

The workflow uploads:

- `bahtinov-design-report.md`;
- `bahtinov-optical-mask.json`;
- `bahtinov-optical-mask.scad`;
- `bahtinov-optical-mask.stl`;
- `bahtinov-optical-mask.3mf`.

The JSON file is the machine-readable contract connecting the report inputs, derived optical recommendation, and generated plate.

## Deliberate mechanical boundary

A complete lens-mounted mask cannot be determined from the scientific report alone. Barrel or hood diameter, fit clearance, mounting depth, and label geometry are independent mechanical facts. Inventing them from focal length would be creative writing with calipers.

This action therefore produces a **flat optical plate**, not a lens-ready mounting assembly. It includes no mounting skirt and no label cartridge.

Two plate-building choices are fixed and recorded in the JSON metadata rather than exposed as extra workflow inputs:

- plate thickness: `2.0 mm`;
- outer frame width and central separator gap: one recommended opaque-bar width.

That keeps the workflow input set identical to the scientific report while producing a printable and inspectable optical pattern. A later assembly stage can combine this optical plate with independently measured mounting geometry without recomputing or silently changing the grating.

## Reproducibility

The workflow regenerates the Markdown report and the optical model in the same run from one `DesignInputs` object. The SCAD metadata and JSON contract record the selected angle, pitch, slot width, bar width, clear diameter, outer diameter, and retained slot count.

Tests compare the workflow input names against `.github/workflows/recommend-mask.yml` so the two forms cannot quietly drift apart while everyone is looking elsewhere, humanity's preferred moment for configuration drift.
