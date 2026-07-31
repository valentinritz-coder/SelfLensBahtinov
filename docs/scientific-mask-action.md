# From scientific report to a real lens-mounted mask

A printable Bahtinov mask is the composition of three independent contracts:

```text
Scientific report  -> optical grating
Mechanical profile -> mounting diameter and usable depth
Print preset       -> clearance, thicknesses, and edge treatment
All three          -> complete mask, fit-test ring, and label cartridge
```

This separation prevents focal length from pretending it knows the diameter of a lens hood, and prevents printer calibration values from masquerading as optical science.

Mechanical profiles use schema version 3 only. There is no schema-v2 loader, migration path, combined optical profile, or legacy generation action.

## Why there are two GitHub Actions runs

A `workflow_dispatch` form is fixed before a run starts. The report workflow cannot stop halfway through, inspect its own calculation, and then open a new dynamic form containing arbitrary follow-up fields.

The user flow is deliberately split:

1. Run **Recommend Bahtinov mask parameters**.
2. Read the Markdown report in the workflow summary.
3. Copy the displayed report run ID.
4. Run **Assemble complete mask from scientific report**.
5. Enter or validate the mechanical profile and proposed print preset.
6. Tick the explicit report-confirmation checkbox.
7. Download the complete artifact bundle.

The second workflow downloads the frozen scientific contract from the selected report run. It does not reconstruct the recommendation from loosely copied numbers.

## Stage 1: scientific report

The report action asks only for optical and observation inputs:

- focal length and working f-number;
- clear diameter reserved for the grating;
- wavelength and optional filter bandwidth;
- pixel pitch and binning;
- visual or software-assisted focus mode;
- optional expected stellar SNR;
- desired first-order offset;
- minimum printable slot and bar widths;
- side-groove angle.

It produces:

- `bahtinov-design-report.md`;
- `bahtinov-scientific-design.json`;
- `mechanical-profile.template.json`;
- `print-preset.proposed.json`;
- `next-step.md`.

The scientific JSON stores the original inputs and the derived pitch, slot width, bar width, offset, clear diameter, and angle. Assembly recomputes and compares critical values before accepting it, so an edited or stale contract fails instead of quietly changing the mask.

## Stage 2: schema-v3 mechanical profile

A mechanical profile describes only the real object on which the mask must fit:

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

Official profiles live in `mechanical-profiles/`. An identity-only catalog profile may contain an empty `mounts` array until a trustworthy measurement is available. Such a profile is valid catalog data but cannot assemble a mask or test ring.

### Mechanical fields

| Field | Meaning |
|---|---|
| `name` | Human-readable identifier for the exact measured surface |
| `type` | `outer-slip-fit` slides over an outside diameter; `inner-slip-fit` inserts into an opening |
| `diameter_mm` | Physical caliper measurement at the mounting position |
| `usable_depth_mm` | Straight unobstructed axial length available for the skirt |
| `status` | `estimated`, `measured`, or `verified` |
| `preferred` | Default mount when a profile contains several alternatives |

Measure in at least three rotational orientations. For an outside fit, record the largest reading. Check that the selected surface is straight and does not move during zooming or focusing.

An `estimated` diameter generates only the short fit-test ring. A full mask requires `measured` or `verified`. `verified` means a printed test ring has already fitted the actual lens or hood.

## Stage 3: print preset

Print presets live in `print-presets/` and own printer- and material-dependent decisions:

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

The assembly action proposes these values in its form. They are not treated as measurements or scientific constants. The user reviews or edits them before confirmation, because plastic tolerances remain distressingly uninterested in elegant equations.

## CLI profile workflow

Inspect the official catalog:

```powershell
selflensbahtinov search Fuji
selflensbahtinov show fujifilm-xf100-400
selflensbahtinov validate fujifilm-xf100-400
```

Create a profile and add a measured surface:

```powershell
selflensbahtinov create-profile `
  --manufacturer Fujifilm `
  --model "Fujinon XF100-400mmF4.5-5.6 R LM OIS WR" `
  --label XF100-400 `
  --output mechanical-profiles/fujifilm-xf100-400.json

selflensbahtinov add-mount fujifilm-xf100-400 `
  --name hood-front-outer `
  --type outer-slip-fit `
  --diameter-mm 92.6 `
  --usable-depth-mm 8.0 `
  --status measured `
  --preferred
```

## Complete generated bundle

For a `measured` or `verified` mount, assembly generates:

- the scientific report and frozen scientific contract;
- the normalized mechanical profile and print preset;
- `mask-assembly.json` recording the three inputs and derived values;
- `assembly-summary.md`;
- complete mask in SCAD, STL, and 3MF when supported;
- short matching fit-test ring;
- matching rear-loading label cartridge when labels are enabled.

The complete mask uses the established 3-o'clock holder, flush slotted face, strengthened crown root, slot-topology cleanup, and tapered-sliver cleanup.

## Derived border and compatibility check

The scientific report owns the requested clear grating diameter. The mechanical profile and print preset determine the inner diameter available behind the mounting ring. Assembly derives the radial solid border from their difference.

If the mounting geometry cannot provide the requested optical clear diameter, generation stops with both values in the error. It does not shrink the scientifically selected aperture while hoping nobody notices.
