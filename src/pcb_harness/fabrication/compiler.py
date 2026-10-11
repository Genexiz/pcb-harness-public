"""Compile explicit minima; unsupported/manual rules remain visible."""
import hashlib
import json
import re
from pcb_harness.circuit.bundle import validate_document
from pcb_harness.circuit.sexpr import Atom, dump_sexpr
from .profile import CATEGORIES
from .capabilities import NATIVE_RULES, supports_constraint


def compile_rules(profile, constraints):
    validate_document("fabrication", profile)
    validate_document("constraints", constraints)
    if {item["id"] for item in profile["categories"]} != CATEGORIES or len(profile["categories"]) != len(CATEGORIES):
        raise ValueError("incomplete fabrication profile")
    rules = ["(version 1)"]
    minima = []
    compliance = []
    effective = {}
    def emit(identifier, quantity, value, scope="all"):
        native, condition = NATIVE_RULES[quantity]
        if scope != "all":
            if not scope.startswith("net:") or not re.fullmatch(r"[A-Za-z0-9_./+-]+", scope[4:]):
                raise ValueError("unsupported/unsafe rule scope")
            net_condition = f"A.NetName == '{scope[4:]}'"
            condition = f"({condition}) && ({net_condition})" if condition else net_condition
        node = [Atom("rule"), f"M3 {identifier}"]
        if condition:
            node.append([Atom("condition"), condition])
        node.append([Atom("constraint"), Atom(native), [Atom("min"), Atom(f"{value:g}mm")]])
        minima.append((value, dump_sexpr(node)))
    for category in profile["categories"]:
        identifier = category["id"]
        floor, target = category["manufacturer_floor"], category["design_target"]
        if any(value is not None and value < 0 for value in (floor, target)):
            raise ValueError("negative manufacturing threshold")
        if floor is not None and target is not None and target < floor:
            raise ValueError(f"target below manufacturing floor: {identifier}")
        emitted = False
        if category["applicable"] and category["evaluator"] == "rule" and identifier in NATIVE_RULES and target is not None:
            # An unconfirmed manufacturer number is never silently made authoritative.
            value = max(target, floor if floor is not None and category["status"] == "confirmed" else 0)
            emit(identifier, identifier, value)
            effective[identifier] = value
            emitted = True
        status = "not_applicable" if not category["applicable"] else (
            "compiled" if emitted and category["status"] == "confirmed" and floor is not None else "unknown")
        compliance.append({"id": identifier, "status": status, "emitted": emitted,
            "evaluator": category["evaluator"], "fact_ids": category["fact_ids"], "manufacturer_floor": floor,
            "design_target": target, "native_verified": False})
    for constraint in constraints["constraints"]:
        emitted = False
        if supports_constraint(constraint):
            emit(constraint["id"], constraint["quantity"], max(constraint["value"], effective.get(constraint["quantity"], 0)), constraint["scope"])
            emitted = True
        compliance.append({"id": constraint["id"], "status": "compiled" if emitted else "unknown",
            "emitted": emitted, "evaluator": constraint["evaluator"], "fact_ids": constraint["fact_ids"], "native_verified": False})
    # KiCad uses the last matching rule of each constraint type. All emitted
    # constraints are minima, so the strictest matching value must come last.
    rules.extend(text for value, text in sorted(minima, key=lambda item: item[0]))
    settings = {"meta": {"filename": "board.kicad_pro", "version": 1},
        "board": {"design_settings": {"rules": {"min_clearance": effective.get("clearance", 0.2),
            "min_track_width": effective.get("track_width", 0.2), "min_through_hole_diameter": effective.get("via_drill", 0.3),
            "min_via_diameter": effective.get("via_diameter", 0.6), "min_copper_edge_clearance": effective.get("copper_edge", 0.5)}}},
        "net_settings": {"version": 4, "classes": [{"name": "Default", "clearance": effective.get("clearance", 0.2),
            "track_width": effective.get("track_width", 0.2), "via_drill": effective.get("via_drill", 0.3), "via_diameter": effective.get("via_diameter", 0.6)}]}}
    digest = hashlib.sha256(json.dumps({"profile": profile, "constraints": constraints}, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {"settings": settings, "rules": "\n".join(rules) + "\n", "compliance": compliance,
        "input_sha256": digest, "release_eligible": False}
