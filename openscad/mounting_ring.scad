// Circular mounting ring geometry for lens hoods, barrels, and filter-thread-sized slip fits.

module mounting_ring(inner_diameter_mm, outer_diameter_mm, ring_depth_mm) {
    difference() {
        cylinder(h = ring_depth_mm, d = outer_diameter_mm, $fn = 180);
        translate([0, 0, -0.1])
            cylinder(h = ring_depth_mm + 0.2, d = inner_diameter_mm, $fn = 180);
    }
}

module test_mounting_ring(inner_diameter_mm, outer_diameter_mm, ring_depth_mm, test_height_mm = 4) {
    mounting_ring(
        inner_diameter_mm = inner_diameter_mm,
        outer_diameter_mm = outer_diameter_mm,
        ring_depth_mm = min(ring_depth_mm, test_height_mm)
    );
}
