# Parametric removable label cartridge

Full masks with labels generate a matching removable cartridge in every requested output format. Cartridge files use the suffix `-label-cartridge` and are written to the same output directory, so GitHub Actions includes them in the same artifact ZIP as the mask and test ring.

The cartridge text is engraved into the generated insert. Its dimensions are calculated from the actual receiver pocket and include the configured sliding clearance.

The receiver can be configured with environment variables, in millimetres:

- `SLB_LABEL_TAB_WIDTH_MM`: total tangential width; empty selects an automatic width from the label text.
- `SLB_LABEL_TAB_DEPTH_MM`: radial projection, default `12.0`.
- `SLB_LABEL_TAB_THICKNESS_MM`: total receiver thickness, default `3.0` and never below the mask face thickness.
- `SLB_LABEL_TAB_FRONT_SKIN_MM`: solid impact-resistant floor against the Bahtinov face, default `1.2`.
- `SLB_LABEL_TAB_SIDE_WALL_MM`: side-wall thickness, default `1.2`.
- `SLB_LABEL_TAB_REAR_RAIL_MM`: retaining-rail thickness, default `0.6`.
- `SLB_LABEL_CARTRIDGE_CLEARANCE_MM`: clearance on each cartridge side, default `0.25`.

The receiver thickness must remain strictly smaller than the mounting ring overlap/depth. Invalid or non-printable combinations fail before OpenSCAD export with a clear error.
