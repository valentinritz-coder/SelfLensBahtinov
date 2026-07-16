# SelfLensBahtinov

SelfLensBahtinov is a reproducible, CLI-first generator for 3D-printable Bahtinov focusing masks designed for camera lenses and lens hoods. Geometry is authored in OpenSCAD, while Python loads lens profiles, validates measurements, writes configured `.scad` entrypoints, and optionally invokes OpenSCAD to produce `.stl` files.

The initial profiles target:

- Fujinon XF100-400mmF4.5-5.6 R LM OIS WR, known 77 mm filter thread.
- Fujinon XF16-80mmF4 R OIS WR, known 72 mm filter thread.

Unmeasured hood and barrel dimensions are intentionally left as `null` with TODO notes.

## Features

- Python 3.11+ CLI with pathlib-based cross-platform paths.
- JSON lens profiles with clear validation errors.
- Parametric OpenSCAD modules for the Bahtinov pattern, mounting ring, full mask, and test ring.
- Dry-run mode for generation commands.
- Logging for reproducible batch workflows.
- Pytest coverage for bundled profiles and validation rules.

## Setup

```powershell
git clone <repo-url>
cd SelfLensBahtinov
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install OpenSCAD separately and ensure `openscad.exe` is on `PATH`, or pass its location with `--openscad`.

## CLI usage

List profiles:

```powershell
selflensbahtinov list-profiles
```

Validate a bundled profile:

```powershell
selflensbahtinov validate fujifilm-xf100-400
```

Generate a configured SCAD file:

```powershell
selflensbahtinov generate-scad fujifilm-xf16-80 --output generated\xf16-80.scad
```

Generate a fit test ring STL before printing the full mask:

```powershell
selflensbahtinov generate-stl fujifilm-xf100-400 --test-ring --output generated\xf100-400-test-ring.stl
```

Generate the full STL with an explicit OpenSCAD executable path:

```powershell
selflensbahtinov generate-stl fujifilm-xf16-80 --openscad "C:\Program Files\OpenSCAD\openscad.exe" --output generated\xf16-80.stl
```

Preview actions without writing files or running OpenSCAD:

```powershell
selflensbahtinov --verbose generate-stl fujifilm-xf100-400 --dry-run
```

## Measurements required

Do not use hood or barrel mounting until these values are measured with calipers and entered into the JSON profile:

- `hood_outer_diameter_mm`: outside diameter of the lens hood at the mask mounting location.
- `barrel_outer_diameter_mm`: outside diameter of the lens barrel at the mask mounting location.
- Confirm the usable straight mounting depth for `ring_depth_mm`.
- Tune `fit_clearance_mm` for your printer/material using `--test-ring`.

See [docs/measurements.md](docs/measurements.md) for the recommended workflow.

## Profile fields

Profiles live in `profiles/*.json` and include manufacturer, model, slug, filter thread, focal length range, aperture range, optional hood/barrel diameters, mount type, fit clearance, mask thickness, ring depth, label, and notes.

Supported `mount_type` values:

- `filter_thread`: slip-fit based on the known filter thread diameter.
- `hood_outer`: slip-fit over a measured hood outside diameter.
- `barrel_outer`: slip-fit over a measured barrel outside diameter.

## OpenSCAD architecture

- `openscad/bahtinov_pattern.scad` creates configurable diffraction slots.
- `openscad/mounting_ring.scad` creates full and test mounting rings.
- `openscad/lens_mask.scad` composes the mask face, ring, optional engraving, and test ring mode.

All dimensions remain parametric so generated files can be reproduced from profiles and CLI options.

## Roadmap

- Add more lens profiles after physical measurements are available.
- Add batch generation from a manifest.
- Add printer/material calibration notes.
- Add CI for tests and generated SCAD smoke checks.
- Improve OpenSCAD pattern tuning based on focal length and aperture.
- Defer any web UI until the CLI and geometry are stable.
