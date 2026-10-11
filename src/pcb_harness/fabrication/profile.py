from pcb_harness.circuit.bundle import validate_document
from .capabilities import NATIVE_RULES

CATEGORIES = {"track_width", "clearance", "via_drill", "via_diameter", "annular_ring",
    "inner_drill_clearance", "pth_size", "npth_size", "hole_to_hole", "copper_edge",
    "slots", "mask_opening", "mask_web", "silk_width", "silk_height", "silk_clearance", "assembly_spacing"}


def review_profile(profile, facts):
    issues, unknowns = [], []
    try:
        validate_document("fabrication", profile)
    except ValueError as error:
        return {"passed": False, "release_eligible": False, "issues": [str(error)], "unknowns": []}
    categories = profile["categories"]
    if {category["id"] for category in categories} != CATEGORIES or len(categories) != len(CATEGORIES):
        issues.append("fabrication category coverage incomplete or duplicated")
    if len(profile["copper_oz"]) != profile["layers"]:
        issues.append("copper stackup does not cover every layer")
    fact_map = {fact["id"]: fact for fact in facts["facts"]}
    for identifier in profile["source_fact_ids"]:
        if identifier not in fact_map:
            issues.append(f"profile source fact missing: {identifier}")
    for category in categories:
        if not category["applicable"]:
            if not category["reason"].strip():
                issues.append(f"not-applicable category lacks reason: {category['id']}")
            continue
        if category["units"] != "mm":
            issues.append(f"dimensional fabrication category needs mm: {category['id']}")
        sources = [fact_map.get(identifier) for identifier in category["fact_ids"]]
        if not sources or any(source is None for source in sources):
            issues.append(f"category source fact missing: {category['id']}")
        floor = category["manufacturer_floor"]
        target = category["design_target"]
        if floor is not None and target is not None and target < floor:
            issues.append(f"target below manufacturing floor: {category['id']}")
        if category["status"] == "confirmed" and floor is not None and not any(
            fact and fact["status"] == "confirmed" and fact["value"] == floor and fact["units"] == category["units"] for fact in sources):
            issues.append(f"confirmed floor lacks exact numeric source: {category['id']}")
        if (category["status"] != "confirmed" or floor is None or category["evaluator"] != "rule"
                or category["id"] not in NATIVE_RULES
                or any(fact and fact["status"] != "confirmed" for fact in sources)):
            unknowns.append({"id": category["id"], "critical": category["critical"], "status": "unknown"})
    return {"passed": not issues, "release_eligible": not issues and not any(item["critical"] for item in unknowns),
        "issues": issues, "unknowns": unknowns}
