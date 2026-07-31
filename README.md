# SelfLensBahtinov

SelfLensBahtinov generates printable Bahtinov masks by composing three independent inputs:

```text
Scientific report  -> optical grating
Mechanical profile -> mounting diameter and usable depth
Print preset       -> clearance, thicknesses, and edge treatment
All three          -> complete mask, fit-test ring, and label cartridge
```

The project generates SCAD, STL, and 3MF when the installed OpenSCAD version supports the requested export.

## Profile schema

Mechanical profiles use **schema version 3 only**. Schema versions 1 and 2, their migration code, and the former combined optical/mechanical/default profile format have been removed.

A profile now describes only the physical surface on which the mask mounts:

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

Official catalog profiles live in `mechanical-profiles/`. Bundled profiles with no trustworthy physical measurement contain an empty `mounts` array. They can be searched and completed, but cannot generate a ring or mask until a mounting surface is measured.

### Mount fields

| Field | Meaning |
|---|---|
| `name` | Human-readable name of the exact measured surface |
| `type` | `outer-slip-fit` or `inner-slip-fit` |
| `diameter_mm` | Physical caliper measurement at the mounting position |
| `usable_depth_mm` | Straight unobstructed axial length available for the skirt |
| `status` | `estimated`, `measured`, or `verified` |
| `preferred` | Default surface when several mounts exist |

`estimated` may generate a short fit-test ring only. `measured` may generate a complete mask after explicit confirmation. `verified` means a printed test ring has already fitted the actual lens or hood.

## Print presets

Printer- and material-dependent choices live separately in `print-presets/`:

```json
{
  "schema_version": 1,
  "name": "default-pla",
  "fit_clearance_mm": 0.35,
  "mask_thickness_mm": 2.0,
  "ring_wall_thickness_mm": 3.0,
  "region_gap_mm": 2.0,
  "lead_in_chamfer_mm": 1.0,
  "outer_edge_radius_mm": 0.5,
  "outer_face_fillet_radius_mm": 0.0,
  "engrave_label": true
}
```

These values are proposed manufacturing settings, not lens measurements and not optical constants.

## GitHub Actions workflow

### 1. Recommend Bahtinov mask parameters

Run **Recommend Bahtinov mask parameters** and provide the scientific inputs:

- focal length and working f-number;
- physical clear diameter reserved for the grating;
- wavelength and optional filter bandwidth;
- sensor pixel pitch and binning;
- visual or software-assisted focus mode;
- requested first-order offset;
- minimum printable slot and bar widths;
- side-grating angle.

The artifact contains:

- `bahtinov-design-report.md`;
- `bahtinov-scientific-design.json`;
- `mechanical-profile.template.json`;
- `print-preset.proposed.json`;
- `next-step.md`.

The workflow summary displays the report run ID.

### 2. Assemble complete mask from scientific report

Run **Assemble complete mask from scientific report** with the prior run ID. Review the scientific report, enter or validate the mechanical measurement, review the print preset, and check the explicit confirmation box.

For a measured or verified mount, the artifact contains:

- complete mask in SCAD, STL, and 3MF when supported;
- matching short fit-test ring;
- matching rear-loading label cartridge when enabled;
- normalized scientific, mechanical, print, and assembly JSON contracts;
- Markdown reports and summaries.

A report workflow cannot pause and dynamically open a second arbitrary form, so review and assembly deliberately use two runs.

## CLI setup

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install OpenSCAD separately. If it is not available on `PATH`, pass its executable with `--openscad` during assembly.

## Mechanical profile commands

Search and inspect the official catalog:

```powershell
selflensbahtinov search Fuji
selflensbahtinov show fujifilm-xf100-400
selflensbahtinov validate fujifilm-xf100-400
```

Create a new empty profile:

```powershell
selflensbahtinov create-profile `
  --manufacturer Fujifilm `
  --model "Fujinon XF100-400mmF4.5-5.6 R LM OIS WR" `
  --label XF100-400 `
  --output mechanical-profiles/fujifilm-xf100-400.json
```

Add a measured mounting surface:

```powershell
selflensbahtinov add-mount fujifilm-xf100-400 `
  --name hood-front-outer `
  --type outer-slip-fit `
  --diameter-mm 92.6 `
  --usable-depth-mm 8.0 `
  --status measured `
  --preferred
```

Measure with digital calipers in at least three rotational orientations. For an outside fit, record the largest reading. Print the short test ring before trusting a full-depth skirt, because plastic remains unimpressed by confident JSON.

## Print preset commands

```powershell
selflensbahtinov presets
selflensbahtinov show-preset default-pla
selflensbahtinov validate-preset default-pla
```

## Local scientific report

```powershell
selflensbahtinov prepare-report `
  --focal-length-mm 400 `
  --f-number 5.6 `
  --mask-clear-diameter-mm 76.7 `
  --pixel-pitch-um 3.76 `
  --side-groove-angle-deg 20 `
  --output-dir generated-report
```

## Local assembly

```powershell
selflensbahtinov assemble `
  --scientific-contract generated-report/bahtinov-scientific-design.json `
  --mechanical-profile fujifilm-xf100-400 `
  --print-preset default-pla `
  --mount-name hood-front-outer `
  --output-dir generated `
  --confirm
```

## Measurement formulas

For an outer slip fit:

```text
ring_inner_diameter = measured_outer_diameter + 2 * radial_clearance
```

For an inner slip fit:

```text
ring_outer_diameter = measured_inner_diameter - 2 * radial_clearance
```

The nominal filter-thread size is not used as either measurement and is no longer part of the profile schema.

See:

- `docs/measurements.md` for physical measurement guidance;
- `docs/scientific-design-report.md` for the optical model;
- `docs/scientific-mask-action.md` for the two-stage assembly flow;
- `docs/bahtinov-algorithm.md` for generated grating geometry.

## Current scope

- Bahtinov report and complete lens-mounted Bahtinov assembly;
- smooth outer and inner slip fits;
- schema-v3 mechanical profiles only;
- independent print presets;
- SCAD, STL, and 3MF output when supported;
- no printed threads, screw mounts, GUI, network profile registry, or slicer automation.

Run the tests with:

```powershell
pytest -q
```
