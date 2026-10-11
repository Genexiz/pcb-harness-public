"""Dimensional constraints backed by retained KiCad native negative probes."""

NATIVE_RULES = {"track_width": ("track_width", "A.Type == 'Track'"),
    "clearance": ("clearance", None), "via_drill": ("hole_size", "A.Type == 'Via'"),
    "via_diameter": ("via_diameter", "A.Type == 'Via'"),
    "annular_ring": ("annular_width", None), "inner_drill_clearance": ("hole_clearance", None),
    "hole_to_hole": ("hole_to_hole", None), "copper_edge": ("edge_clearance", None)}


def supports_constraint(constraint):
    quantity = constraint["quantity"]
    return (constraint["kind"] == "rule" and quantity in NATIVE_RULES
        and constraint["evaluator"] in (quantity, NATIVE_RULES[quantity][0])
        and constraint["value"] is not None and constraint["value"] >= 0
        and constraint["units"] == "mm")
