"""Source-bound engineering screening; does not certify a circuit or firmware."""
from jsonschema import Draft202012Validator

from pcb_harness.circuit.bundle import finite_tree
from pcb_harness.orchestration.stm32_feasibility import (
    obj, array, TEXT, POSITIVE, NUMBER, BOOL, REQUIRED_INTERFACES, validate_design,
)

ERRATA_ITEMS = ("2.2.8", "2.2.9", "2.3.7", "2.3.10", "2.4.1", "2.4.2",
                "2.8.1", "2.8.2", "2.8.4", "2.8.5", "2.8.7", "2.9.2",
                "2.10.2", "2.12.1", "2.12.2", "2.12.3", "2.12.4")
NULL_TEXT = {"type": ["string", "null"], "minLength": 1}
HASH = {"type": ["string", "null"], "pattern": "^[0-9a-f]{64}$"}
NULL_VALUE = {"type": ["number", "null"], "minimum": 0}
COUNT = {"type": "integer", "minimum": 1, "maximum": 32}
SUPPLY_DOMAIN = {"enum": ["VDD", "VIO", None]}
TIMING = obj({"brp": {"type": "integer", "minimum": 1, "maximum": 256},
              "tseg1": {"type": "integer", "minimum": 1, "maximum": 256},
              "tseg2": {"type": "integer", "minimum": 1, "maximum": 128},
              "sjw": {"type": "integer", "minimum": 1, "maximum": 128}, "target_bps": POSITIVE})
SCHEMA = obj({
    "schema_version": {"const": 1}, "design_id": TEXT,
    "facts": array(obj({"id": TEXT, "part": TEXT, "metric": {"enum": ["clock", "supply", "current", "length", "width", "height"]},
        "unit": {"enum": ["Hz", "V", "A", "mm"]}, "supply_domain": SUPPLY_DOMAIN,
        "minimum": NULL_VALUE, "maximum": NULL_VALUE,
        "coverage": {"enum": ["operating-range", "full-workload", "no-load", "specific-condition", "typical", "unavailable"]},
        "source_id": NULL_TEXT, "source_sha256": HASH, "locator": TEXT, "conditions": TEXT})),
    "controllers": array(obj({"interface": TEXT, "part": TEXT, "sysclk_hz": POSITIVE, "clock_fact": TEXT,
        "rx_slots": COUNT, "tx_slots": COUNT, "tef_slots": COUNT,
        "payload_bytes": {"enum": [8, 12, 16, 20, 24, 32, 48, 64]},
        "rx_timestamp": BOOL, "tef_timestamp": BOOL, "nominal": TIMING,
        "data": {"anyOf": [TIMING, {"type": "null"}]}})),
    "power": obj({"rails": array(obj({"voltage_v": POSITIVE, "minimum_v": POSITIVE, "maximum_v": POSITIVE})),
        "loads": array(obj({"id": TEXT, "part": TEXT, "quantity": {"type": "integer", "minimum": 1},
            "rail_v": POSITIVE, "supply_domain": {"enum": ["VDD", "VIO"]},
            "reserve_per_device_a": NUMBER, "supply_fact": TEXT, "current_fact": TEXT}))}),
    "mechanical": obj({"module_part": TEXT, "length_facts": {"type": "array", "items": TEXT, "minItems": 1, "uniqueItems": True},
        "width_fact": TEXT, "height_fact": TEXT, "screening_length_mm": POSITIVE,
        "screening_width_mm": POSITIVE, "screening_height_mm": POSITIVE,
        "connectors": array(obj({"interface": TEXT, "part": NULL_TEXT,
            "length_mm": NULL_VALUE, "width_mm": NULL_VALUE, "height_mm": NULL_VALUE,
            "source_id": NULL_TEXT, "source_sha256": HASH, "locator": TEXT}))}),
    "errata": obj({"source_id": NULL_TEXT, "source_sha256": HASH, "locator": TEXT,
        "device_marking": NULL_TEXT, "rev_id": NULL_TEXT,
        "items": array(obj({"id": TEXT, "policy": TEXT}))}),
})


def unique(entries, key):
    result = {e[key]: e for e in entries}
    if len(result) != len(entries):
        raise ValueError(f"duplicate {key} in engineering evidence")
    return result


def assess_engineering(design, dossier, sources, source_lock):
    validate_design(design)
    finite_tree(dossier)
    errors = list(Draft202012Validator(SCHEMA).iter_errors(dossier))
    if errors:
        raise ValueError(f"engineering dossier {list(errors[0].path)}: {errors[0].message}")
    if dossier["design_id"] != design["id"]:
        raise ValueError("engineering design ID mismatch")
    if source_lock["schema_version"] != 1:
        raise ValueError("unsupported engineering source lock")
    documents = unique(source_lock["documents"], "id")
    facts = unique(dossier["facts"], "id")
    source_issues = []

    def issue(issues, code, detail):
        issues.append({"code": code, "detail": detail})

    def bound(record):
        doc = documents.get(record["source_id"])
        digest = record["source_sha256"]
        valid = (doc is not None and digest is not None and doc.get("status") == "retrieved"
                 and digest == doc.get("sha256") == sources["hashes"].get(doc["path"]))
        if not valid:
            issue(source_issues, "SOURCE_BINDING", record.get("id", record["locator"]))
        return valid

    bindings = {fid: bound(f) for fid, f in facts.items()}
    for f in facts.values():
        if f["minimum"] is not None and f["maximum"] is not None and f["minimum"] > f["maximum"]:
            raise ValueError(f"inverted fact range: {f['id']}")

    def fact(fid, part, metric, unit, issues, supply_domain=None):
        if fid not in facts:
            raise ValueError(f"missing engineering fact: {fid}")
        f = facts[fid]
        if (f["part"], f["metric"], f["unit"], f["supply_domain"]) != (part, metric, unit, supply_domain):
            issue(issues, "FACT_APPLICABILITY", fid)
            return None
        if not bindings[fid]:
            issue(issues, "SOURCE_BINDING", fid)
        return f

    controllers = unique(dossier["controllers"], "interface")
    ci, devices = [], []
    if set(controllers) != {"can_classical", "can_fd"}:
        issue(ci, "CONTROLLER_COVERAGE", "two independent CAN networks required")
    parts = unique(design["parts"], "ref")
    controller_part = parts.get("U2/U3", {}).get("mpn")
    if controller_part != "MCP2518FD-E/SL":
        issue(ci, "CONTROLLER_MODE", "controller part differs from calibrated MCP2518FD")
    jobs = {j["interface"]: j for bus in design["buses"] for j in bus["jobs"]}

    def timing(t, phase, interface):
        tq = 1 + t["tseg1"] + t["tseg2"]
        if t["sjw"] > t["tseg2"] or (phase == "data" and (t["tseg1"] > 32 or t["tseg2"] > 16 or t["sjw"] > 16)):
            issue(ci, "BIT_TIMING", f"{interface}/{phase}: segment or SJW limit")
        rate = c["sysclk_hz"] / (t["brp"] * tq)
        if rate != t["target_bps"]:
            issue(ci, "BIT_RATE", f"{interface}/{phase}")
        if t["target_bps"] != (500000 if phase == "nominal" else 2000000):
            issue(ci, "TARGET_RATE", f"{interface}/{phase}")
        return {"bitrate_bps": rate, "sample_point": (1 + t["tseg1"]) / tq,
                "register_fields": {key: t[key] - 1 for key in ("brp", "tseg1", "tseg2", "sjw")}}

    for interface, c in controllers.items():
        if (c["part"] != controller_part or c["payload_bytes"] != (64 if interface == "can_fd" else 8)
                or (c["data"] is None) != (interface == "can_classical")):
            issue(ci, "CONTROLLER_MODE", interface)
        clock = fact(c["clock_fact"], c["part"], "clock", "Hz", ci)
        if (clock is None or clock["minimum"] is None or clock["maximum"] is None
                or not clock["minimum"] <= c["sysclk_hz"] <= clock["maximum"]
                or clock["coverage"] != "operating-range"):
            issue(ci, "CLOCK_RANGE", interface)
        if interface not in jobs or c["rx_slots"] < jobs[interface]["fifo_frames"]:
            issue(ci, "RX_FIFO_COVERAGE", interface)
        sections, offset = [], 0
        for role, slots, size in (("tef", c["tef_slots"], 8 + 4 * c["tef_timestamp"]),
                                 ("tx", c["tx_slots"], 8 + c["payload_bytes"]),
                                 ("rx", c["rx_slots"], 8 + c["payload_bytes"] + 4 * c["rx_timestamp"])):
            sections.append({"role": role, "slots": slots, "object_bytes": size,
                             "start_address": 0x400 + offset, "end_address_exclusive": 0x400 + offset + slots * size})
            offset += slots * size
        if offset > 2048:
            issue(ci, "CONTROLLER_RAM", interface)
        devices.append({"interface": interface, "sections": sections,
                        "ram_used_bytes": offset, "ram_free_bytes": 2048 - offset,
                        "nominal": timing(c["nominal"], "nominal", interface),
                        "data": timing(c["data"], "data", interface) if c["data"] else None})

    pi, unbounded, load_results = [], [], []
    rails = unique(dossier["power"]["rails"], "voltage_v")
    if set(rails) != {3.3, 5}:
        issue(pi, "RAIL_COVERAGE", "3V3 and direct 5V rails required")
    for rail in rails.values():
        if not rail["minimum_v"] <= rail["voltage_v"] <= rail["maximum_v"]:
            raise ValueError("inverted rail or nominal outside rail range")
    required = {
        "mcu": ("U1", 1, 3.3), "ethernet": ("M1", 1, 3.3), "can-controllers": ("U2/U3", 2, 3.3),
        "can-vdd": ("U4/U5", 2, 5), "can-vio": ("U4/U5", 2, 3.3),
        "rs232": ("U7", 1, 3.3), "rs485": ("U6", 1, 3.3), "support": (None, 1, 3.3)}
    accounted_refs = {ref for ref, _, _ in required.values() if ref is not None} | {"U8"}
    if (set(parts) != accounted_refs or parts.get("U8", {}).get("mpn") != "TPS62162DSGR"
            or design["power"]["regulator"] != parts.get("U8", {}).get("mpn")):
        issue(pi, "PART_COVERAGE", "calibrated device inventory and TPS62162DSGR regulator required")
    loads = unique(dossier["power"]["loads"], "id")
    if set(loads) != set(required):
        issue(pi, "LOAD_COVERAGE", "all core devices, VIO, and support/external loads required")
    totals = {3.3: 0, 5: 0}
    for lid, load in loads.items():
        ref, qty, rail_v = required.get(lid, (None, 0, 0))
        expected_part = parts.get(ref, {}).get("mpn") if ref else "LEDs/pullups/headers"
        domain = "VIO" if lid == "can-vio" else "VDD"
        if (load["part"], load["quantity"], load["rail_v"], load["supply_domain"]) != (expected_part, qty, rail_v, domain):
            issue(pi, "LOAD_IDENTITY", lid)
        if load["rail_v"] not in totals:
            issue(pi, "RAIL_COVERAGE", lid)
            continue
        totals[load["rail_v"]] += load["reserve_per_device_a"] * load["quantity"]
        supply = fact(load["supply_fact"], load["part"], "supply", "V", pi, domain)
        current = fact(load["current_fact"], load["part"], "current", "A", pi, domain)
        rail = rails.get(load["rail_v"])
        if (supply is None or supply["minimum"] is None or supply["maximum"] is None or rail is None
                or rail["minimum_v"] < supply["minimum"] or rail["maximum_v"] > supply["maximum"]
                or supply["coverage"] != "operating-range"):
            issue(pi, "SUPPLY_RANGE", lid)
        documented = (current is not None and current["coverage"] == "full-workload"
                      and current["maximum"] is not None and bindings[current["id"]])
        if not documented:
            unbounded.append(lid)
        if current is not None and current["maximum"] is not None and load["reserve_per_device_a"] < current["maximum"]:
            issue(pi, "CURRENT_RESERVE", lid)
        load_results.append({"id": lid, "rail_v": load["rail_v"], "quantity": load["quantity"],
                             "supply_domain": domain,
                             "documented_full_load_bound": documented, "current_fact": load["current_fact"]})
    if totals[3.3] > design["power"]["rated_current_a"]:
        issue(pi, "REGULATOR_CAPACITY", "engineering reserve exceeds regulator current rating")

    mi, m = [], dossier["mechanical"]
    if m["module_part"] != parts.get("M1", {}).get("mpn"):
        issue(mi, "MODULE_IDENTITY", "module revision differs from design")
    lengths = [fact(fid, m["module_part"], "length", "mm", mi) for fid in m["length_facts"]]
    width = fact(m["width_fact"], m["module_part"], "width", "mm", mi)
    height = fact(m["height_fact"], m["module_part"], "height", "mm", mi)
    known_lengths = [f["maximum"] for f in lengths if f is not None and f["maximum"] is not None]
    if len(set(known_lengths)) > 1:
        issue(mi, "MECHANICAL_CONFLICT", "publisher length observations disagree")
    for dimension, values in (("length", known_lengths), ("width", [width["maximum"]] if width else []),
                              ("height", [height["maximum"]] if height else [])):
        if not values or any(v is None or m[f"screening_{dimension}_mm"] < v for v in values):
            issue(mi, "MODULE_ENVELOPE", dimension)
    if (design["mechanical"]["width_mm"] > 100 or design["mechanical"]["height_mm"] > 100
            or design["mechanical"]["mounting_holes"] != 4
            or m["screening_length_mm"] > design["mechanical"]["width_mm"]
            or m["screening_width_mm"] > design["mechanical"]["height_mm"]):
        issue(mi, "BOARD_ENVELOPE", "target board size or module fit")
    connectors = unique(m["connectors"], "interface")
    if set(connectors) != REQUIRED_INTERFACES:
        issue(mi, "CONNECTOR_COVERAGE", "all nine external interfaces required")
    for interface, connector in connectors.items():
        binding = bound(connector)
        if not binding or connector["part"] is None or any(connector[key] is None or connector[key] <= 0
                                                         for key in ("length_mm", "width_mm", "height_mm")):
            issue(mi, "CONNECTOR_ENVELOPE", interface)
        elif (connector["length_mm"] > design["mechanical"]["width_mm"]
              or connector["width_mm"] > design["mechanical"]["height_mm"]):
            issue(mi, "CONNECTOR_ENVELOPE", interface)

    ei, e = [], dossier["errata"]
    items = unique(e["items"], "id")
    if set(items) != set(ERRATA_ITEMS):
        issue(ei, "ERRATA_COVERAGE", "all targeted ES096 policies required; full table review still needed")
    if not bound(e):
        issue(ei, "SOURCE_BINDING", "errata original snapshot not bound")
    return {"schema_version": 1, "design_id": design["id"], "human_confirmed": False,
            "source_issues": source_issues,
            "controllers": {"arithmetic_passed": not ci, "issues": ci, "devices": devices,
                            "firmware_status": "unknown", "limits": "RAM/timing arithmetic only; crystals, TDC, drivers and actual bus propagation unvalidated"},
            "power": {"status": "unknown", "passed": False, "issues": pi, "loads": load_results,
                      "unbounded_loads": unbounded, "reserve_3v3_a": totals[3.3], "reserve_5v_a": totals[5],
                      "thermal_status": "unknown", "limits": "rail targets and documented conditional limits, not load/thermal qualification"},
            "mechanical": {"passed": False, "status": "unknown", "issues": mi,
                           "screening_envelope_mm": [m["screening_length_mm"], m["screening_width_mm"], m["screening_height_mm"]],
                           "limits": "body screening only; header origins, courtyards, tolerances, assembly and enclosure unreviewed"},
            "errata": {"passed": False, "status": "unknown", "issues": ei, "policy_count": len(items),
                       "silicon_status": "unknown", "limits": "planned targeted policies only; no implemented driver proof, device marking or full errata review"}}
