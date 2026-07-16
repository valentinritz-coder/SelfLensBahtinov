// Parametric Bahtinov diffraction slot pattern.

module bahtinov_slot(length_mm, width_mm, angle_deg, offset_mm) {
    rotate([0, 0, angle_deg])
        translate([offset_mm, 0, 0])
            square([width_mm, length_mm], center = true);
}

module bahtinov_pattern(clear_aperture_mm, slot_width_mm = 2.0, slot_spacing_mm = 6.0) {
    pattern_span = clear_aperture_mm * 1.6;
    slot_count = floor(pattern_span / slot_spacing_mm);

    for (i = [-slot_count : slot_count]) {
        bahtinov_slot(pattern_span, slot_width_mm, 0, i * slot_spacing_mm);
    }
    for (i = [-slot_count : slot_count]) {
        bahtinov_slot(pattern_span, slot_width_mm, 60, i * slot_spacing_mm);
    }
    for (i = [-slot_count : slot_count]) {
        bahtinov_slot(pattern_span, slot_width_mm, -60, i * slot_spacing_mm);
    }
}
