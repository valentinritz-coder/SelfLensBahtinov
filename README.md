# SelfLensBahtinov

SelfLensBahtinov V1 is a focused, one-developer Python CLI for generating reproducible, printable Bahtinov and TriBahtinov focusing masks for camera lenses. It starts with two local Fujifilm profiles: the Fujinon XF100-400mmF4.5-5.6 R LM OIS WR and Fujinon XF16-80mmF4 R OIS WR.

Python owns the optical and pattern calculations. OpenSCAD is only the first rendering/export backend: it receives already-calculated slot, aperture, ring, and label geometry and exports SCAD, STL, or 3MF when the installed OpenSCAD supports that format.

## Scope

V1 supports exactly:

- Mask algorithms: Bahtinov and TriBahtinov.
- Output formats: `.scad`, `.stl`, and `.3mf`.
- Mount modes: `filter-thread`, `hood-outer`, and `barrel-outer`.
- Planned-but-not-generated mount mode: `universal-screws`.
- Local JSON profiles only; there is no database, network registry, plugin system, GUI, slicer automation, or generic CAD framework.

Bahtinov and TriBahtinov are included because they are practical focusing aids for real lens use: Bahtinov masks are simple and robust, while TriBahtinov masks add three-sector diagnostic behavior for collimation/focus interpretation without requiring a broader mask framework.

## Important filter-thread warning

`filter-thread` is a user-facing alias for an internal filter-diameter slip-fit mount. It sizes a plain slip-fit ring from the nominal filter diameter plus clearance. It does **not** model ISO screw threads and should not be described or printed as a threaded filter mount.

## Setup on Windows PowerShell

```powershell
git clone <repo-url>
cd SelfLensBahtinov
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
```

Install OpenSCAD separately from <https://openscad.org/>. Then verify it is available:

```powershell
openscad --version
```

If `openscad.exe` is not on `PATH`, pass it with `--openscad "C:\Program Files\OpenSCAD\openscad.exe"`. STL and 3MF exports are only claimed when OpenSCAD is actually available and supports the requested format; older OpenSCAD builds may not export 3MF.

## CLI usage

Search local profiles:

```powershell
selflensbahtinov search Fuji
```

Show a profile:

```powershell
selflensbahtinov show fujifilm-xf100-400
```

Validate a profile:

```powershell
selflensbahtinov validate fujifilm-xf100-400
```

Generate a fit-test ring before printing a full mask:

```powershell
selflensbahtinov generate-test-ring fujifilm-xf16-80 --mount filter-thread --clearance 0.35 --format stl
```

Generate Bahtinov SCAD, STL, and 3MF:

```powershell
selflensbahtinov generate fujifilm-xf100-400 --mask bahtinov --mount filter-thread --format scad --format stl --format 3mf
```

Tune the physical grating if your printer or observing setup needs different diffraction spikes:

```powershell
selflensbahtinov generate fujifilm-xf100-400 --mask bahtinov --slot-spacing 5.0 --slot-width 1.2 --slot-density 1.5 --show-grating-info
```

Generate TriBahtinov outputs:

```powershell
selflensbahtinov generate fujifilm-xf100-400 --mask tribahtinov --mount filter-thread --format scad --format stl --format 3mf
```

Generate the V1 bundle: selected full mask plus matching test ring in SCAD/STL and 3MF when supported.

```powershell
selflensbahtinov generate-bundle fujifilm-xf16-80 --mask bahtinov --mount filter-thread
```

Run tests:

```powershell
pytest
```

## Profile model

Profiles use schema version 1 and strict validation. Unknown fields, invalid enum values, inconsistent focal/aperture ranges, impossible clearances, pattern borders, wall thicknesses, and missing selected mount dimensions are rejected. The two bundled profiles keep unknown hood and barrel dimensions as `null` with TODO notes.

The generation flow is:

```text
LensProfile -> generation options -> MaskAlgorithm -> MaskGeometry -> OpenScadRenderer -> SCAD / STL / 3MF
```

The geometry model is deliberately small: `Point2D`, `SlotGeometry`, `RingGeometry`, `LabelGeometry`, `GratingMetadata`, and `MaskGeometry`. The clear aperture is the slip-fit inner diameter minus twice `pattern_border_mm`. Python computes the Bahtinov transmission gratings from a Fraunhofer-equation, physics-informed printable heuristic; focal length and f-number choose the default grating pitch when explicit slot controls are not provided. Python produces candidate rectangles and optical metadata; OpenSCAD still performs circular and sector clipping. Unsupported 3MF export support causes a controlled SCAD/STL bundle fallback, while actual export failures remain errors. See `docs/bahtinov-algorithm.md` for the mathematical model and references.

## Measurements and test-ring workflow

Before using `hood-outer` or `barrel-outer`, edit the profile with real measurements. Print a short test ring first, then adjust clearance in small increments until the fit is secure but not forced. See [docs/measurements.md](docs/measurements.md).

## Current limitations

- Filter-thread mode is a slip fit, not a true threaded mount.
- Hood and barrel dimensions for the bundled lenses are unknown until measured.
- Universal screw mounting is an enum value only; selecting it returns a clear not-implemented error.
- 3MF export depends on OpenSCAD capability.
- The algorithm is intentionally V1-focused and not a general CAD kernel.

## Roadmap

- Add measured hood/barrel dimensions after the user measures them.
- Add more lens profiles with strict schema validation.
- Tune mask constants from real printed tests.
- Consider Hartmann masks, focus targets, STEP, FreeCAD, Fusion 360, or printer/slicer workflows later, but not in V1.
