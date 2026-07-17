# SelfLensBahtinov

SelfLensBahtinov V1 is a focused Python CLI for generating reproducible, printable Bahtinov and TriBahtinov focusing masks for camera lenses. Python owns the optical and pattern calculations; OpenSCAD is currently the rendering/export backend for SCAD, STL, and 3MF.

## Scope

V1 supports exactly:

- Mask algorithms: Bahtinov and TriBahtinov.
- Output formats: `.scad`, `.stl`, and `.3mf`.
- Smooth slip-fit mounting only: `lens-barrel-outer-slip-fit`, `hood-outer-slip-fit`, and `hood-inner-slip-fit`.
- Local JSON profiles only; there is no database, network registry, plugin system, GUI, slicer automation, printed thread generator, screw mount, or generic CAD framework.

Printed threads are intentionally out of scope for V1. The deprecated CLI value `filter-thread` is accepted only as a temporary compatibility alias for `lens-barrel-outer-slip-fit` and prints a warning. It does not create a threaded or screw-in mount.

## Mounting model

For a Bahtinov mask, the preferred physical design is a removable cap that slips on and off quickly in the dark. Prefer the outside of the lens hood (`hood-outer-slip-fit`) or the outside of the lens barrel (`lens-barrel-outer-slip-fit`) when there is a straight, safe cylindrical surface. `hood-inner-slip-fit` is available when you deliberately want the ring to fit inside a measured hood opening.

Profiles store `filter_thread_nominal_mm` only as product metadata. A nominal filter-thread size is not necessarily the outside diameter of the lens barrel or hood, and SelfLensBahtinov does not reinterpret it as a printable thread, barrel diameter, or hood diameter.

Clearance is configurable radial clearance in millimetres:

- Outer slip fit over a lens barrel or hood: `ring_inner_diameter = measured_outer_diameter + 2 * radial_clearance`.
- Inner slip fit inside a hood opening: radial clearance reduces the printable outside diameter of the skirt, so `ring_outer_diameter = measured_hood_inner_diameter - 2 * radial_clearance`.

Real fit depends on printer calibration, material shrinkage, elephant foot, slicer settings, surface texture, and measurement accuracy.


### Production mounting-ring edge geometry

The production mounting skirt is generated from one Python-owned radial/z cross-section that is rendered to SCAD and then exported to STL and 3MF. The fit-test ring and complete mask use the same mounting cross-section, so a test ring remains a valid mechanical proxy for the final mask.

The axial overlap/engagement length on the lens barrel or hood is controlled by `ring_depth_mm` in a profile and can be overridden during generation with `--ring-depth <mm>`. Fit-test rings intentionally stay short and cap this depth at 4.0 mm, so they validate diameter and edge geometry without printing a full-depth skirt.

Two manufacturing/ergonomic defaults are applied unless a profile or CLI override changes them:

- `lead_in_chamfer_mm = 1.0`: adds an internal lead-in on the mounting-entry side. The entry side is the negative-Z/bottom side of the mounting skirt: the side first presented to the barrel or hood. The chamfer flares only the entry edge outward; deeper inside the ring the straight cylindrical engagement still uses the nominal slip-fit diameter, so it guides insertion without loosening the final fit. Set `--lead-in-chamfer 0` to disable it.
- `outer_edge_radius_mm = 0.5`: applies a deterministic support-free faceted edge treatment to exposed outside skirt edges to remove sharp handling edges and reduce burr/chip sensitivity. Set `--outer-edge-radius 0` to disable it.

Validation rejects non-finite, negative, self-intersecting, or mechanically incompatible values. The lead-in must leave at least 2.0 mm of straight cylindrical engagement and must be smaller than the ring height. The outer edge radius must fit within both the wall thickness and the ring height. The nominal mounting diameter, radial clearance, and resulting internal fit diameter remain separate from both edge-treatment parameters.

Recommended print orientation: place the mounting ring flat on the build plate with the negative-Z mounting-entry side down. This keeps the skirt stable, prints the 45° lead-in without supports, and leaves the diffraction slots in the intended face orientation.

```text
        external rounded edge
              ╭──────
             /       │
entry  →    /        │  straight cylindrical engagement at nominal fit diameter
           │         │
           │         │
           └─────────┘
```

CLI example with explicit manufacturing overrides:

```powershell
selflensbahtinov generate-test-ring fujifilm-xf100-400 `
  --mount lens-barrel-outer-slip-fit `
  --clearance 0.35 `
  --lead-in-chamfer 1.0 `
  --outer-edge-radius 0.5 `
  --format stl
```

## Setup on Windows PowerShell

```powershell
git clone <repo-url>
cd SelfLensBahtinov
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install OpenSCAD separately from <https://openscad.org/>. If `openscad.exe` is not on `PATH`, pass it with `--openscad "C:\Program Files\OpenSCAD\openscad.exe"`.

## CLI usage

```powershell
selflensbahtinov search Fuji
selflensbahtinov show fujifilm-xf100-400
selflensbahtinov validate fujifilm-xf100-400
```

Generate a fit-test ring before printing a full mask:

```powershell
selflensbahtinov generate-test-ring fujifilm-xf100-400 `
  --mount lens-barrel-outer-slip-fit `
  --clearance 0.35 `
  --format 3mf
```

Generate Bahtinov SCAD, STL, and 3MF:

```powershell
selflensbahtinov generate fujifilm-xf100-400 `
  --mount hood-outer-slip-fit `
  --clearance 0.35 `
  --format scad `
  --format stl `
  --format 3mf
```

Generate TriBahtinov outputs:

```powershell
selflensbahtinov generate fujifilm-xf100-400 --mask tribahtinov --mount hood-outer-slip-fit --format scad --format stl --format 3mf
```

Generate the V1 bundle: selected full mask plus matching test ring in SCAD/STL and 3MF when supported.

```powershell
selflensbahtinov generate-bundle fujifilm-xf16-80 --mask bahtinov --mount hood-outer-slip-fit
```

Example output filenames include:

- `fujifilm-xf100-400-bahtinov-hood-outer-slip-fit.3mf`
- `fujifilm-xf100-400-test-ring-lens-barrel-outer-slip-fit.3mf`

## Profile model

Profiles use schema version 2 and strict validation. Mounting dimensions are explicit measured values with measurement status. Bundled profiles intentionally have no recommended or default mount until measured:

```json
{
  "mounting": {
    "filter_thread_nominal_mm": 77.0,
    "lens_barrel_outer_mm": null,
    "lens_barrel_outer_status": "unknown",
    "hood_outer_mm": null,
    "hood_outer_status": "unknown",
    "hood_inner_mm": null,
    "hood_inner_status": "unknown",
    "recommended_mount": null
  }
}
```

Unknown dimensions remain `null` with status `unknown`. A non-null dimension may be `estimated`, `measured`, or `verified`; `estimated` can be used for test-ring generation only, while `measured` and `verified` can be used for full masks. `recommended_mount` and `defaults.mount_type` may only point to a dimension whose status is `measured` or `verified`. `recommended_mount` means physically recommended and measured, not merely preferred in theory. `verified` means the fit has been physically tested with a printed ring on the actual lens or hood. Selecting a mount whose required physical dimension is `null` fails clearly. Deprecated schema-version-1 profiles are migrated to the version-2 in-memory model with old filter-thread recommendations/defaults cleared rather than treated as real barrel measurements.

The generation flow is:

```text
LensProfile -> generation options -> MaskAlgorithm -> MaskGeometry -> OpenScadRenderer -> SCAD / STL / 3MF
```

See `docs/bahtinov-algorithm.md` for the mathematical model.

## Measurements and test-ring workflow

Before generating a mask, measure the intended mounting surface with calipers, edit the profile, and select the corresponding `--mount` option. Print a short test ring first; this remains the mandatory first physical validation step. A useful clearance matrix is 0.20 mm, 0.30 mm, 0.40 mm, and 0.50 mm. Generate those rings one at a time unless a future dedicated matrix option is added. See [docs/measurements.md](docs/measurements.md).

Run tests:

```powershell
pytest
```

## Current limitations

- V1 supports smooth slip-fit caps only.
- Printed threads and screw-in mounting are intentionally not implemented.
- Hood and barrel dimensions for bundled lenses are unknown until measured.
- 3MF export depends on OpenSCAD capability.
