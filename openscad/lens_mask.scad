// Complete parametric lens Bahtinov mask. Print flat with mask face on the bed.

use <bahtinov_pattern.scad>
use <mounting_ring.scad>

module engraved_label(label_text, outer_diameter_mm, mask_thickness_mm) {
    if (label_text != "") {
        translate([0, -outer_diameter_mm * 0.32, mask_thickness_mm - 0.35])
            linear_extrude(height = 0.4)
                text(label_text, size = outer_diameter_mm * 0.055, halign = "center", valign = "center");
    }
}

module mask_face(inner_diameter_mm, outer_diameter_mm, mask_thickness_mm, label_text, engrave_label) {
    clear_aperture_mm = inner_diameter_mm - 6;
    difference() {
        cylinder(h = mask_thickness_mm, d = outer_diameter_mm, $fn = 180);
        translate([0, 0, -0.1])
            linear_extrude(height = mask_thickness_mm + 0.2)
                intersection() {
                    circle(d = clear_aperture_mm, $fn = 180);
                    bahtinov_pattern(clear_aperture_mm = clear_aperture_mm);
                }
        if (engrave_label) {
            engraved_label(label_text, outer_diameter_mm, mask_thickness_mm);
        }
    }
}

module lens_mask(
    inner_diameter_mm,
    outer_diameter_mm,
    mask_thickness_mm = 2,
    ring_depth_mm = 8,
    label_text = "",
    engrave_label = true,
    test_ring_mode = false
) {
    if (test_ring_mode) {
        test_mounting_ring(inner_diameter_mm, outer_diameter_mm, ring_depth_mm);
    } else {
        union() {
            mask_face(inner_diameter_mm, outer_diameter_mm, mask_thickness_mm, label_text, engrave_label);
            translate([0, 0, mask_thickness_mm])
                mounting_ring(inner_diameter_mm, outer_diameter_mm, ring_depth_mm);
        }
    }
}
