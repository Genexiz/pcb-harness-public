"""Independent upstream functional checks, separate from native connectivity."""
from collections import Counter
from copy import deepcopy
import hashlib
import json
import re

from .bundle import validate_document, bundle_hashes
from .provenance import audit_provenance
from pcb_harness.fabrication.capabilities import supports_constraint


def canonical_peripheral(name):
    normalized = name.upper()
    match = re.fullmatch(r"(USB|CAN)(?:[0-9]+|_(?:FS|HS|OTG_FS|OTG_HS))?", normalized)
    return match[1] if match else normalized


def review_circuit(bundle, root, checklist):
    issues, unknowns = [], []
    def issue(code, identifier, message):
        issues.append({"code": code, "id": identifier, "message": message})
    effective = {**bundle, "checklist": deepcopy(checklist)}
    try:
        for kind, data in effective.items():
            validate_document(kind, data)
    except ValueError as error:
        return {"passed": False, "release_eligible": False, "issues": [{"code": "INVALID_SCHEMA", "id": "bundle", "message": str(error)}], "unknowns": [], "coverage": {}, "input_sha256": {}}
    provenance = audit_provenance(effective, root)
    issues.extend(provenance["issues"])
    unknowns.extend(provenance["unknowns"])
    circuit = bundle["circuit"]
    parts = {part["id"]: part for part in bundle["parts"]["parts"]}
    instances = {instance["id"]: instance for instance in circuit["instances"]}
    facts = {fact["id"]: fact for fact in bundle["facts"]["facts"]}
    for domain, entries in (("instances", circuit["instances"]), ("parts", bundle["parts"]["parts"]), ("nets", circuit["nets"]), ("facts", bundle["facts"]["facts"]), ("constraints", bundle["constraints"]["constraints"])):
        if len({entry["id"] for entry in entries}) != len(entries):
            issue("DUPLICATE_ID", domain, "stable IDs are not unique")
    refs = Counter(instance["ref"] for instance in circuit["instances"])
    if any(count != 1 for count in refs.values()):
        issue("DUPLICATE_REF", "instances", "reference designators are not unique")
    assignments = {}
    net_ranges = {}
    for net in circuit["nets"]:
        voltage = net["voltage_range_v"]
        if voltage and voltage[0] > voltage[1]:
            issue("VOLTAGE_MISMATCH", net["id"], "voltage range is reversed")
        for endpoint in net["endpoints"]:
            key = (endpoint["instance_id"], endpoint["pin_id"])
            if key in assignments:
                issue("ENDPOINT_CONFLICT", str(key), "electrical endpoint used more than once")
            assignments[key] = net["name"]
            net_ranges[key] = voltage
    declared_nc = {(endpoint["instance_id"], endpoint["pin_id"]) for endpoint in circuit["no_connect"]}
    expected_nc = {(endpoint["instance_id"], endpoint["pin_id"]) for endpoint in checklist["no_connect"]}
    if declared_nc != expected_nc or declared_nc.intersection(assignments) or len(declared_nc) != len(circuit["no_connect"]):
        issue("NO_CONNECT_MISMATCH", "no_connect", "intentional no-connect differs from checklist or is connected")
    for endpoint in circuit["no_connect"]:
        if endpoint["fact_id"] not in facts:
            issue("FACT_MISSING", endpoint["fact_id"], "no-connect explanation lacks source")
    valid_endpoints = set()
    required_facts = set(checklist["required_fact_ids"])
    required_errata = set(checklist["required_errata_ids"])
    for instance in instances.values():
        part = parts.get(instance["part_id"])
        if not part:
            issue("PART_MISSING", instance["id"], "instance part ID is absent")
            continue
        required_facts.update(part["required_fact_ids"])
        required_errata.update(part["errata_fact_ids"])
        for identifier in instance["fact_ids"]:
            if identifier not in facts:
                issue("FACT_MISSING", identifier, "instance source fact is absent")
        for pin in part["pins"]:
            key = (instance["id"], pin["id"])
            valid_endpoints.add(key)
            if key not in assignments and key not in declared_nc:
                issue("PIN_UNASSIGNED", str(key), "pin lacks net or approved no-connect")
            operating = pin["operating_range_v"]
            voltage = net_ranges.get(key)
            if operating:
                if operating[0] > operating[1] or (voltage and not (operating[0] <= voltage[0] <= voltage[1] <= operating[1])):
                    issue("VOLTAGE_MISMATCH", str(key), "net voltage exceeds recommended operating range")
                elif key in assignments and voltage is None:
                    unknowns.append({"code": "VOLTAGE_UNKNOWN", "id": str(key)})
    if (set(assignments) | declared_nc) - valid_endpoints:
        issue("PIN_UNKNOWN", "endpoints", "endpoint references nonexistent instance/pin")
    expected_instances = checklist["expected_instances"]
    if set(refs) != {expected["ref"] for expected in expected_instances}:
        issue("INSTANCE_COVERAGE", "instances", "required reference set differs")
    for expected in expected_instances:
        candidates = [instance for instance in instances.values() if instance["ref"] == expected["ref"]]
        if len(candidates) != 1:
            continue
        instance = candidates[0]
        part = parts.get(instance["part_id"])
        if part is None:
            continue
        if any(part[field] != expected[field] for field in ("mpn", "package", "footprint_id")):
            issue("FOOTPRINT_MISMATCH", expected["ref"], "independent part/package/footprint identity differs")
        observed = {pin["number"]: assignments.get((instance["id"], pin["id"])) for pin in part["pins"]
            if (instance["id"], pin["id"]) not in declared_nc}
        if observed != expected["pin_nets"]:
            issue("PINOUT_MISMATCH", expected["ref"], "pin-to-net mapping differs from independent checklist")
    requirements = bundle["requirements"]
    expected_interfaces = {interface["id"]: interface for interface in checklist["interfaces"]}
    required_interfaces = {interface["id"]: interface for interface in requirements["interfaces"]}
    if required_interfaces != expected_interfaces:
        issue("INTERFACE_MISSING", "requirements", "interface contract differs from independent checklist")
    actual_counts = Counter(assignment["id"] for assignment in circuit["interfaces"])
    if actual_counts != Counter({identifier: value["count"] for identifier, value in expected_interfaces.items()}):
        issue("INTERFACE_MISSING", "circuit", "required interface count differs")
    allocated = set()
    for assignment in circuit["interfaces"]:
        instance = instances.get(assignment["instance_id"])
        if not instance or assignment["id"] not in expected_interfaces or assignment["kind"] != expected_interfaces[assignment["id"]]["kind"]:
            issue("INTERFACE_MISSING", assignment["id"], "assignment has wrong kind/instance")
        if instance:
            part = parts.get(instance["part_id"])
            peripheral = canonical_peripheral(assignment["peripheral"])
            if (part and part["mpn"] == "STM32F103C8T6" and assignment["kind"] in ("USB", "CAN")
                    and peripheral != assignment["kind"] and not peripheral.startswith("EXTERNAL_")):
                issue("PERIPHERAL_UNKNOWN", assignment["id"], "native peripheral identity is not recognized")
        for pin_id in assignment["pin_ids"]:
            key = (assignment["instance_id"], pin_id)
            if key not in valid_endpoints or key in allocated:
                issue("PIN_ALLOCATION_CONFLICT", str(key), "interface pin missing or already allocated")
            allocated.add(key)
    groups = {frozenset(group) for group in requirements["concurrent_groups"]}
    if groups != {frozenset(group) for group in checklist["concurrent_groups"]}:
        issue("CONCURRENCY_MISSING", "requirements", "concurrent groups differ from checklist")
    for group in groups:
        grouped = [assignment for assignment in circuit["interfaces"] if assignment["id"] in group]
        if not group.issubset(expected_interfaces):
            issue("CONCURRENCY_MISSING", "requirements", "concurrency references absent interface")
        for instance in instances.values():
            part = parts.get(instance["part_id"])
            peripherals = {canonical_peripheral(assignment["peripheral"]) for assignment in grouped if assignment["instance_id"] == instance["id"]}
            for conflict in checklist["conflicts"]:
                if part and part["mpn"] == conflict["mpn"] and {canonical_peripheral(name) for name in conflict["peripherals"]}.issubset(peripherals):
                    issue("PERIPHERAL_CONFLICT", instance["id"], "concurrent native peripherals share an exclusive resource")
    for identifier in required_facts:
        if identifier not in facts:
            issue("FACT_MISSING", identifier, "independent required fact is absent")
    mitigated = {mitigation["fact_id"] for mitigation in circuit["errata_mitigations"] if mitigation["evidence"]}
    for identifier in required_errata - mitigated:
        issue("ERRATA_UNRESOLVED", identifier, "required errata has no mitigation evidence")
    required_constraints = set(checklist["required_constraint_ids"])
    for requirement in requirements["functional"]:
        required_constraints.update(requirement["required_constraint_ids"])
    constraints = {constraint["id"]: constraint for constraint in bundle["constraints"]["constraints"]}
    for identifier in required_constraints - constraints.keys():
        issue("CONSTRAINT_MISSING", identifier, "independent required constraint is omitted")
    for constraint in constraints.values():
        if any(identifier not in facts for identifier in constraint["fact_ids"]):
            issue("FACT_MISSING", constraint["id"], "constraint references absent fact")
        if constraint["mandatory"] and (constraint["status"] != "confirmed" or not supports_constraint(constraint) or not constraint["evidence"]):
            unknowns.append({"code": "CONSTRAINT_UNVERIFIED", "id": constraint["id"]})
    hashes = bundle_hashes(root)
    hashes["semantic_bundle"] = hashlib.sha256(json.dumps(effective, sort_keys=True, allow_nan=False).encode()).hexdigest()
    return {"passed": not issues, "release_eligible": not issues and not unknowns and provenance["release_eligible"],
        "issues": issues, "unknowns": unknowns, "coverage": {"required": sorted(required_constraints),
            "missing": sorted(required_constraints - constraints.keys())}, "input_sha256": hashes}
